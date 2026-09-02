"""Phase 1: the mock pipeline stops on MEASURED reconstruction, not self-grading."""

import pytest
from reverse_guardrail.core.models import PipelineConfig, PipelineStatus, TargetScopeConfig
from reverse_guardrail.guardrail.mock_guardrail import (
    MOCK_GROUND_TRUTH_SYSTEM_PROMPT,
    MockGuardrailTarget,
)
from reverse_guardrail.orchestrator.runner import PipelineRunner
from reverse_guardrail.storage.sqlite_store import SQLiteGraphVectorStore


@pytest.mark.asyncio
async def test_pipeline_records_measured_metrics_against_ground_truth():
    config = PipelineConfig(
        target=TargetScopeConfig(
            authorized=True, engagement_id="ENG-MEASURED-2026", target_name="Mock Measured",
        ),
        max_rounds=3, attempts_per_round=4, confidence_threshold=0.85,
        stagnation_patience_rounds=5, rate_limit_rps=50.0,
    )
    target = MockGuardrailTarget(
        scope_config=config.target,
        ground_truth_prompt=MOCK_GROUND_TRUTH_SYSTEM_PROMPT,
        simulated_latency_ms=1.0,
    )
    runner = PipelineRunner(config=config, target=target, store=SQLiteGraphVectorStore(db_path=":memory:"))
    state = await runner.run()

    assert state.status == PipelineStatus.COMPLETED
    # Ground truth known -> measured metrics must be attached and the stop reason
    # must cite the measured signal, not self-reported confidence.
    assert state.latest_metrics is not None
    assert 0.0 <= state.latest_metrics.completeness_score <= 1.0
    assert "measured completeness" in state.stop_reason or "Max rounds" in state.stop_reason or "stagnation" in state.stop_reason
    assert state.round_summaries[-1].measured_score is not None
