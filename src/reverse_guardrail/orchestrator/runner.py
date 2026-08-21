"""High-level runner and controller for the Reverse-Guardrail pipeline."""

from typing import Optional
from uuid import uuid4
from reverse_guardrail.agents.hardening_reporter import HardeningReporterAgent
from reverse_guardrail.agents.inspectioner import InspectionerAgent
from reverse_guardrail.agents.reverse_engineer import ReversePromptEngineerAgent
from reverse_guardrail.agents.tester import TesterAgent
from reverse_guardrail.agents.vulnerability_analyzer import VulnerabilityAnalyzerAgent
from reverse_guardrail.core.models import PipelineConfig, PipelineStatus
from reverse_guardrail.core.scope_guard import ScopeAuthorizationGuard
from reverse_guardrail.guardrail.base import BaseGuardrailTarget
from reverse_guardrail.guardrail.mock_guardrail import MockGuardrailTarget
from reverse_guardrail.orchestrator.graph import ReverseGuardrailWorkflow
from reverse_guardrail.orchestrator.state import PipelineState
from reverse_guardrail.storage.base import BaseFragmentStore
from reverse_guardrail.storage.sqlite_store import SQLiteGraphVectorStore


class PipelineRunner:
    """Convenience controller to launch, execute, and monitor pipeline runs."""

    def __init__(
        self,
        config: PipelineConfig,
        target: Optional[BaseGuardrailTarget] = None,
        store: Optional[BaseFragmentStore] = None,
        tester: Optional[TesterAgent] = None,
        inspectioner: Optional[InspectionerAgent] = None,
        reverse_engineer: Optional[ReversePromptEngineerAgent] = None,
        vulnerability_analyzer: Optional[VulnerabilityAnalyzerAgent] = None,
        hardening_reporter: Optional[HardeningReporterAgent] = None,
    ):
        self.config = config
        # Enforce scope at runner construction
        ScopeAuthorizationGuard.enforce(self.config, action="INITIALIZE_PIPELINE_RUNNER")

        self.store = store or SQLiteGraphVectorStore()

        if target is not None:
            self.target = target
        elif self.config.target.use_browser and self.config.target.target_url:
            from reverse_guardrail.guardrail.browser_target import BrowserGuardrailTarget
            self.target = BrowserGuardrailTarget(
                scope_config=self.config.target,
                timeout_seconds=self.config.timeout_seconds,
            )
        elif self.config.target.target_url and not self.config.target.target_name.startswith("mock"):
            from reverse_guardrail.guardrail.http_target import HttpGuardrailTarget
            self.target = HttpGuardrailTarget(scope_config=self.config.target)
        else:
            self.target = MockGuardrailTarget(scope_config=self.config.target)

        # Instantiate agents according to config models
        tester_model = self.config.models.get("tester", "mock-tester")
        insp_model = self.config.models.get("inspectioner", "mock-inspectioner")
        rev_model = self.config.models.get("reverse_engineer", "mock-reverse-engineer")
        vuln_model = self.config.models.get("vulnerability_analyzer", "mock-vulnerability-analyzer")
        hard_model = self.config.models.get("hardening_reporter", "mock-hardening-reporter")

        self.tester = tester or TesterAgent(model_spec=tester_model)
        self.inspectioner = inspectioner or InspectionerAgent(model_spec=insp_model)
        self.reverse_engineer = reverse_engineer or ReversePromptEngineerAgent(model_spec=rev_model)
        self.vulnerability_analyzer = vulnerability_analyzer or VulnerabilityAnalyzerAgent(model_spec=vuln_model)
        self.hardening_reporter = hardening_reporter or HardeningReporterAgent(model_spec=hard_model)

        self.workflow = ReverseGuardrailWorkflow(
            target=self.target,
            store=self.store,
            tester=self.tester,
            inspectioner=self.inspectioner,
            reverse_engineer=self.reverse_engineer,
            vulnerability_analyzer=self.vulnerability_analyzer,
            hardening_reporter=self.hardening_reporter,
        )
        self.state: Optional[PipelineState] = None

    async def initialize(self) -> PipelineState:
        """Initialize DB store and initial state."""
        await self.store.initialize()
        run_id = f"RUN-{uuid4().hex[:8].upper()}"
        self.state = PipelineState(
            run_id=run_id,
            config=self.config,
            status=PipelineStatus.IDLE,
        )
        return self.state

    async def run(self) -> PipelineState:
        """Run the full closed-loop pipeline until a stopping condition is reached."""
        if not self.state:
            await self.initialize()

        # Invoke the compiled LangGraph workflow
        final_state_dict = await self.workflow.graph.ainvoke(self.state)
        if isinstance(final_state_dict, dict):
            self.state = PipelineState(**final_state_dict)
        elif isinstance(final_state_dict, PipelineState):
            self.state = final_state_dict

        return self.state
