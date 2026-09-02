"""LangGraph workflow definition for the closed-loop Reverse-Guardrail pipeline."""

from typing import Any, Dict, Literal, Optional
from langgraph.graph import END, StateGraph
from reverse_guardrail.agents.hardening_reporter import HardeningReporterAgent
from reverse_guardrail.agents.inspectioner import InspectionerAgent
from reverse_guardrail.agents.reverse_engineer import ReversePromptEngineerAgent
from reverse_guardrail.agents.tester import TesterAgent
from reverse_guardrail.agents.vulnerability_analyzer import VulnerabilityAnalyzerAgent
from reverse_guardrail.core.models import FragmentCategory, PipelineStatus, RoundSummary
from reverse_guardrail.evaluation.evaluator import EvaluationMetrics, GuardrailEvaluator
from reverse_guardrail.core.rate_limiter import RateLimiter
from reverse_guardrail.core.scope_guard import ScopeAuthorizationError, ScopeAuthorizationGuard
from reverse_guardrail.guardrail.base import BaseGuardrailTarget
from reverse_guardrail.orchestrator.state import PipelineState
from reverse_guardrail.storage.base import BaseFragmentStore


class ReverseGuardrailWorkflow:
    """Orchestrates the agents, target, and storage in a stateful feedback loop."""

    def __init__(
        self,
        target: BaseGuardrailTarget,
        store: BaseFragmentStore,
        tester: TesterAgent,
        inspectioner: InspectionerAgent,
        reverse_engineer: ReversePromptEngineerAgent,
        vulnerability_analyzer: Optional[VulnerabilityAnalyzerAgent] = None,
        hardening_reporter: Optional[HardeningReporterAgent] = None,
    ):
        self.target = target
        self.store = store
        self.tester = tester
        self.inspectioner = inspectioner
        self.reverse_engineer = reverse_engineer
        self.vulnerability_analyzer = vulnerability_analyzer or VulnerabilityAnalyzerAgent()
        self.hardening_reporter = hardening_reporter or HardeningReporterAgent()
        self.rate_limiter = RateLimiter(requests_per_second=2.0)
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        workflow = StateGraph(PipelineState)

        # Nodes
        workflow.add_node("scope_guard_check", self._node_scope_check)
        workflow.add_node("tester_step", self._node_tester)
        workflow.add_node("inspectioner_step", self._node_inspectioner)
        workflow.add_node("reverse_engineer_step", self._node_reverse_engineer)
        workflow.add_node("evaluate_stop", self._node_evaluate_stop)
        workflow.add_node("vulnerability_analyzer_step", self._node_vulnerability_analyzer)
        workflow.add_node("hardening_reporter_step", self._node_hardening_reporter)

        # Edges
        workflow.set_entry_point("scope_guard_check")
        workflow.add_edge("scope_guard_check", "tester_step")
        workflow.add_edge("tester_step", "inspectioner_step")
        workflow.add_edge("inspectioner_step", "reverse_engineer_step")
        workflow.add_edge("reverse_engineer_step", "evaluate_stop")

        workflow.add_conditional_edges(
            "evaluate_stop",
            self._route_next_action,
            {
                "continue": "tester_step",
                "analyze_vulnerabilities": "vulnerability_analyzer_step",
                "end": END,
            },
        )

        workflow.add_edge("vulnerability_analyzer_step", "hardening_reporter_step")
        workflow.add_edge("hardening_reporter_step", END)

        return workflow.compile()

    async def _node_scope_check(self, state: PipelineState) -> Dict[str, Any]:
        """Verify scope authorization gate."""
        try:
            ScopeAuthorizationGuard.enforce(
                state.config,
                action="WORKFLOW_START",
                details={"run_id": state.run_id},
            )
            return {"status": PipelineStatus.RUNNING}
        except ScopeAuthorizationError as exc:
            return {
                "status": PipelineStatus.ABORTED_UNAUTHORIZED,
                "stop_reason": f"Scope Authorization Failed: {exc}",
            }

    async def _node_tester(self, state: PipelineState) -> Dict[str, Any]:
        """Tester generates and runs probes against the target."""
        if state.status == PipelineStatus.ABORTED_UNAUTHORIZED:
            return {}

        self.rate_limiter.rps = state.config.rate_limit_rps
        results = await self.tester.execute_round(
            round_id=state.current_round,
            target=self.target,
            rate_limiter=self.rate_limiter,
            count=state.config.attempts_per_round,
            gaps=state.current_gaps,
            strategy_stats=await self._strategy_effectiveness(),
        )

        return {
            "metadata": {
                **state.metadata,
                f"round_{state.current_round}_results": results,
            }
        }

    async def _strategy_effectiveness(self) -> Dict[str, int]:
        """Tally, per strategy, how many real leak fragments it has produced so far.

        Refusal patterns are excluded — a refusal is not a leak — so the Tester
        biases toward strategies that actually surface prompt content.
        """
        fragments = await self.store.get_all_fragments()
        stats: Dict[str, int] = {}
        for frag in fragments:
            if frag.category == FragmentCategory.REFUSAL_PATTERN:
                continue
            key = frag.source_strategy.value
            stats[key] = stats.get(key, 0) + 1
        return stats

    async def _node_inspectioner(self, state: PipelineState) -> Dict[str, Any]:
        """Inspectioner analyzes responses and saves extracted fragments."""
        if state.status == PipelineStatus.ABORTED_UNAUTHORIZED:
            return {}

        results = state.metadata.get(f"round_{state.current_round}_results", [])
        extracted_this_round = []
        refusals = 0

        initial_count = await self.store.count_fragments()

        for attempt, response in results:
            if response.refused:
                refusals += 1
            frags = await self.inspectioner.inspect_and_extract(
                attempt=attempt,
                response=response,
                store=self.store,
            )
            extracted_this_round.extend(frags)

        final_count = await self.store.count_fragments()
        new_frags_count = final_count - initial_count

        consecutive_zeros = (
            state.consecutive_zero_new_fragments + 1
            if new_frags_count == 0
            else 0
        )

        return {
            "last_new_fragments_count": new_frags_count,
            "consecutive_zero_new_fragments": consecutive_zeros,
            "total_fragments_count": final_count,
            "metadata": {
                **state.metadata,
                f"round_{state.current_round}_refusals": refusals,
                f"round_{state.current_round}_extracted_count": len(extracted_this_round),
            },
        }

    async def _node_reverse_engineer(self, state: PipelineState) -> Dict[str, Any]:
        """Reverse Engineer synthesizes prompt and determines gaps."""
        if state.status == PipelineStatus.ABORTED_UNAUTHORIZED:
            return {}

        report = await self.reverse_engineer.synthesize_reconstruction(
            round_id=state.current_round,
            store=self.store,
        )

        refusals = state.metadata.get(f"round_{state.current_round}_refusals", 0)
        extracted = state.metadata.get(f"round_{state.current_round}_extracted_count", 0)

        summary = RoundSummary(
            round_id=state.current_round,
            attempts_count=state.config.attempts_per_round,
            refusals_count=refusals,
            fragments_extracted_count=extracted,
            new_fragments_count=state.last_new_fragments_count,
            current_confidence=report.overall_confidence,
            gaps_count=len(report.gaps),
        )

        return {
            "latest_report": report,
            "current_gaps": report.gaps,
            "round_summaries": [*state.round_summaries, summary],
        }

    async def _node_evaluate_stop(self, state: PipelineState) -> Dict[str, Any]:
        """Determine if stopping criteria are met or if round advances.

        When the target's true system prompt is known (mock / internal LLM under
        test), the stop is driven by the reconstruction MEASURED against that
        ground truth, not by the reverse-engineer's own confidence — the latter
        is self-graded and unreliable. Live targets (extension / HTTP) have no
        ground truth, so they fall back to the self-reported confidence.
        """
        if state.status == PipelineStatus.ABORTED_UNAUTHORIZED:
            return {"status": PipelineStatus.ABORTED_UNAUTHORIZED}

        updates: Dict[str, Any] = {}
        effective_score = (
            state.latest_report.overall_confidence if state.latest_report else 0.0
        )
        score_label = "self-reported confidence"

        ground_truth = self.target.get_ground_truth()
        if ground_truth and state.latest_report:
            metrics = GuardrailEvaluator.evaluate(
                reconstructed_prompt=state.latest_report.reconstructed_prompt,
                ground_truth_prompt=ground_truth,
            )
            effective_score = metrics.completeness_score
            score_label = "measured completeness"
            updates["latest_metrics"] = metrics
            # Record the measured score on the round summary just produced.
            if state.round_summaries:
                summaries = list(state.round_summaries)
                summaries[-1] = summaries[-1].model_copy(
                    update={"measured_score": effective_score}
                )
                updates["round_summaries"] = summaries

        # 1. Completeness/confidence threshold reached
        if state.latest_report and effective_score >= state.config.confidence_threshold:
            return {
                **updates,
                "status": PipelineStatus.COMPLETED,
                "stop_reason": f"Threshold reached ({score_label} {effective_score:.2f} >= {state.config.confidence_threshold:.2f})",
            }

        # 2. Stagnation threshold reached
        if (
            state.consecutive_zero_new_fragments
            >= state.config.stagnation_patience_rounds
        ):
            return {
                **updates,
                "status": PipelineStatus.COMPLETED,
                "stop_reason": f"Fragment stagnation: {state.consecutive_zero_new_fragments} consecutive rounds with 0 new fragments.",
            }

        # 3. Max rounds reached
        if state.current_round >= state.config.max_rounds:
            return {
                **updates,
                "status": PipelineStatus.COMPLETED,
                "stop_reason": f"Max rounds limit reached ({state.config.max_rounds}).",
            }

        # Continue to next round
        return {
            **updates,
            "current_round": state.current_round + 1,
            "status": PipelineStatus.RUNNING,
        }

    async def _node_vulnerability_analyzer(self, state: PipelineState) -> Dict[str, Any]:
        """Runs static and semantic threat modeling on the reconstructed system prompt."""
        if not state.latest_report:
            return {}

        vuln_report = await self.vulnerability_analyzer.analyze_vulnerabilities(
            run_id=state.run_id,
            report=state.latest_report,
        )
        return {"vulnerability_report": vuln_report}

    async def _node_hardening_reporter(self, state: PipelineState) -> Dict[str, Any]:
        """Generates defensive remediation items and hardened system prompt report."""
        if not state.vulnerability_report or not state.latest_report:
            return {}

        hardening_report = await self.hardening_reporter.generate_hardening_report(
            run_id=state.run_id,
            vuln_report=state.vulnerability_report,
            recon_report=state.latest_report,
        )
        return {"hardening_report": hardening_report}

    def _route_next_action(
        self, state: PipelineState
    ) -> Literal["continue", "analyze_vulnerabilities", "end"]:
        """Router conditional edge."""
        if state.status == PipelineStatus.COMPLETED and state.latest_report:
            return "analyze_vulnerabilities"
        if state.status in (PipelineStatus.ABORTED_UNAUTHORIZED, PipelineStatus.FAILED, PipelineStatus.COMPLETED):
            return "end"
        return "continue"
