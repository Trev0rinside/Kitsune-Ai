"""End-to-End test validating the closed-loop Reverse-Guardrail pipeline on Mock Guardrail."""

import pytest
from reverse_guardrail.core.models import PipelineConfig, PipelineStatus, TargetScopeConfig
from reverse_guardrail.evaluation.evaluator import GuardrailEvaluator
from reverse_guardrail.guardrail.mock_guardrail import (
    MOCK_GROUND_TRUTH_SYSTEM_PROMPT,
    MockGuardrailTarget,
)
from reverse_guardrail.orchestrator.runner import PipelineRunner
from reverse_guardrail.storage.sqlite_store import SQLiteGraphVectorStore


@pytest.mark.asyncio
async def test_mock_pipeline_e2e_closed_loop():
    # 1. Scope and Config
    config = PipelineConfig(
        target=TargetScopeConfig(
            authorized=True,
            engagement_id="ENG-E2E-VALIDATION-2026",
            target_name="Mock Target E2E",
        ),
        max_rounds=3,
        attempts_per_round=4,
        confidence_threshold=0.85,
        stagnation_patience_rounds=2,
        rate_limit_rps=50.0,
    )

    # 2. Components
    store = SQLiteGraphVectorStore(db_path=":memory:")
    target = MockGuardrailTarget(
        scope_config=config.target,
        ground_truth_prompt=MOCK_GROUND_TRUTH_SYSTEM_PROMPT,
        simulated_latency_ms=1.0,
    )

    runner = PipelineRunner(
        config=config,
        target=target,
        store=store,
    )

    # 3. Execution
    final_state = await runner.run()

    # 4. State Assertions
    assert final_state.status == PipelineStatus.COMPLETED
    assert final_state.current_round >= 1
    assert len(final_state.round_summaries) >= 1
    assert final_state.latest_report is not None
    assert final_state.total_fragments_count > 0

    reconstructed_prompt = final_state.latest_report.reconstructed_prompt
    assert len(reconstructed_prompt) > 100

    # 5. Quantitative Evaluation vs Ground Truth
    metrics = GuardrailEvaluator.evaluate(
        reconstructed_prompt=reconstructed_prompt,
        ground_truth_prompt=MOCK_GROUND_TRUTH_SYSTEM_PROMPT,
        sensitive_tokens=["NEXUS_SEC_KEY_8841"],
    )

    # Validate high recovery metrics
    assert metrics.semantic_similarity >= 0.70, f"Semantic similarity too low: {metrics.semantic_similarity}"
    assert metrics.section_recall >= 0.70, f"Section recall too low: {metrics.section_recall}"
    assert metrics.sensitive_token_leakage is True, "Expected secret token NEXUS_SEC_KEY_8841 to be leaked and detected."
    assert metrics.leakage_risk_score >= 0.70, f"Expected high leakage risk score: {metrics.leakage_risk_score}"


@pytest.mark.asyncio
async def test_mock_mode_wins_over_stale_target_url():
    """UI keeps a default target_url across mode switches; target_mode='mock'
    must still route to the simulator (with ground truth), not the HTTP target."""
    from reverse_guardrail.guardrail.mock_guardrail import MockGuardrailTarget

    config = PipelineConfig(
        target=TargetScopeConfig(
            authorized=True, engagement_id="ENG-ROUTE-2026",
            target_name="Mock NexusTech Simulator",
            target_mode="mock",
            target_url="https://claude.ai/new",
        ),
        max_rounds=1, attempts_per_round=2, rate_limit_rps=50.0,
    )
    runner = PipelineRunner(config=config, store=SQLiteGraphVectorStore(db_path=":memory:"))
    assert isinstance(runner.target, MockGuardrailTarget)
    assert runner.target.get_ground_truth() is not None
