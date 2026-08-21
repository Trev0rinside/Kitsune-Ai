"""Pytest configuration and shared fixtures for Reverse-Guardrail."""

import pytest
from reverse_guardrail.core.models import PipelineConfig, TargetScopeConfig
from reverse_guardrail.core.scope_guard import ScopeAuthorizationGuard
from reverse_guardrail.guardrail.mock_guardrail import MockGuardrailTarget
from reverse_guardrail.storage.sqlite_store import SQLiteGraphVectorStore


@pytest.fixture(autouse=True)
def clean_audit_logs():
    """Reset audit logs before each test."""
    ScopeAuthorizationGuard.clear_audit_log()
    yield
    ScopeAuthorizationGuard.clear_audit_log()


@pytest.fixture
def valid_scope_config() -> TargetScopeConfig:
    return TargetScopeConfig(
        authorized=True,
        engagement_id="ENG-TEST-2026-001",
        target_name="Test Target",
    )


@pytest.fixture
def unauthorized_scope_config() -> TargetScopeConfig:
    return TargetScopeConfig(
        authorized=False,
        engagement_id="ENG-TEST-2026-001",
        target_name="Unauthorized Target",
    )


@pytest.fixture
def empty_engagement_scope_config() -> TargetScopeConfig:
    return TargetScopeConfig(
        authorized=True,
        engagement_id="",
        target_name="Invalid Engagement Target",
    )


@pytest.fixture
def valid_pipeline_config(valid_scope_config: TargetScopeConfig) -> PipelineConfig:
    return PipelineConfig(
        target=valid_scope_config,
        max_rounds=3,
        attempts_per_round=3,
        confidence_threshold=0.85,
        stagnation_patience_rounds=2,
        rate_limit_rps=10.0,
    )


@pytest.fixture
async def in_memory_store():
    store = SQLiteGraphVectorStore(db_path=":memory:")
    await store.initialize()
    yield store
    await store.clear()


@pytest.fixture
def mock_target(valid_scope_config: TargetScopeConfig) -> MockGuardrailTarget:
    return MockGuardrailTarget(scope_config=valid_scope_config, simulated_latency_ms=1.0)
