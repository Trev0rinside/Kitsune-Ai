"""Integration tests for Phase 2: Reconstruction -> Vulnerability Analysis -> Hardening Report."""

import pytest
from reverse_guardrail.core.models import (
    PipelineConfig,
    PipelineStatus,
    TargetScopeConfig,
    VulnerabilitySeverity,
)
from reverse_guardrail.orchestrator.runner import PipelineRunner
from reverse_guardrail.storage.sqlite_store import SQLiteGraphVectorStore


@pytest.mark.asyncio
async def test_full_phase2_closed_loop_pipeline(in_memory_store: SQLiteGraphVectorStore):
    config = PipelineConfig(
        target=TargetScopeConfig(
            authorized=True,
            engagement_id="ENG-PHASE2-TEST-2026",
            target_name="Mock Target Phase 2",
        ),
        max_rounds=2,
        attempts_per_round=3,
        confidence_threshold=0.80,
        stagnation_patience_rounds=2,
        rate_limit_rps=50.0,
    )

    runner = PipelineRunner(config=config, store=in_memory_store)
    state = await runner.run()

    # 1. Verify Pipeline status
    assert state.status == PipelineStatus.COMPLETED
    assert state.latest_report is not None
    assert state.latest_report.overall_confidence > 0.4

    # 2. Verify Vulnerability Assessment generated
    assert state.vulnerability_report is not None
    assert len(state.vulnerability_report.vulnerabilities) > 0
    assert state.vulnerability_report.overall_risk_rating in (
        VulnerabilitySeverity.CRITICAL,
        VulnerabilitySeverity.HIGH,
        VulnerabilitySeverity.MEDIUM,
    )
    assert 0.0 <= state.vulnerability_report.structural_hardening_index <= 1.0

    # 3. Verify Defensive Hardening Report generated
    assert state.hardening_report is not None
    assert len(state.hardening_report.remediations) > 0
    assert len(state.hardening_report.hardened_system_prompt) > 100
    assert "<system_instructions>" in state.hardening_report.hardened_system_prompt
    assert len(state.hardening_report.architectural_recommendations) >= 3
    assert state.hardening_report.after_hardening_score >= 0.85
