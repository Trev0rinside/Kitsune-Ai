"""A target that stops responding (rate-limited/blocked) must end the run fast,
not grind through every round hammering a silent chat."""

import pytest
from reverse_guardrail.core.models import (
    GuardrailResponse,
    InjectionAttempt,
    PipelineConfig,
    PipelineStatus,
    TargetScopeConfig,
)
from reverse_guardrail.guardrail.base import BaseGuardrailTarget
from reverse_guardrail.orchestrator.runner import PipelineRunner
from reverse_guardrail.storage.sqlite_store import SQLiteGraphVectorStore


class SilentTarget(BaseGuardrailTarget):
    """Authorized target that never returns output — simulates a rate-limit banner."""

    async def _send_prompt(self, attempt: InjectionAttempt, history=None) -> GuardrailResponse:
        return GuardrailResponse(
            attempt_id=attempt.attempt_id, round_id=attempt.round_id,
            raw_response="", latency_ms=1.0, refused=False, status_code=504,
        )


@pytest.mark.asyncio
async def test_run_stops_when_target_is_unresponsive():
    config = PipelineConfig(
        target=TargetScopeConfig(
            authorized=True, engagement_id="ENG-SILENT-2026", target_name="Silent",
        ),
        max_rounds=5, attempts_per_round=4, confidence_threshold=0.95,
        stagnation_patience_rounds=5, rate_limit_rps=50.0,
    )
    runner = PipelineRunner(
        config=config, target=SilentTarget(config.target),
        store=SQLiteGraphVectorStore(db_path=":memory:"),
    )
    state = await runner.run()

    assert state.status == PipelineStatus.COMPLETED
    # Stopped on the unresponsive-target signal, in round 1 — not after all 5 rounds.
    assert "not responding" in state.stop_reason
    assert state.current_round == 1
