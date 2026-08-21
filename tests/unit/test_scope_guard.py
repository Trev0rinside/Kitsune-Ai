"""Unit tests for the Scope Authorization Guard and Kill-Switch."""

import pytest
from reverse_guardrail.core.models import PipelineConfig, TargetScopeConfig
from reverse_guardrail.core.scope_guard import ScopeAuthorizationError, ScopeAuthorizationGuard


def test_scope_guard_verify_success(valid_scope_config: TargetScopeConfig):
    assert ScopeAuthorizationGuard.verify(valid_scope_config) is True


def test_scope_guard_verify_unauthorized(unauthorized_scope_config: TargetScopeConfig):
    assert ScopeAuthorizationGuard.verify(unauthorized_scope_config) is False


def test_scope_guard_verify_empty_engagement(empty_engagement_scope_config: TargetScopeConfig):
    assert ScopeAuthorizationGuard.verify(empty_engagement_scope_config) is False


def test_scope_guard_enforce_success(valid_pipeline_config: PipelineConfig):
    scope = ScopeAuthorizationGuard.enforce(valid_pipeline_config, action="UNIT_TEST")
    assert scope.authorized is True
    assert scope.engagement_id == "ENG-TEST-2026-001"

    logs = ScopeAuthorizationGuard.get_audit_log()
    assert len(logs) == 1
    assert logs[0].status == "AUTHORIZED_ACCESS"
    assert logs[0].engagement_id == "ENG-TEST-2026-001"


def test_scope_guard_killswitch_unauthorized(unauthorized_scope_config: TargetScopeConfig):
    with pytest.raises(ScopeAuthorizationError) as exc_info:
        ScopeAuthorizationGuard.enforce(unauthorized_scope_config, action="UNAUTHORIZED_ATTEMPT")

    assert "KILL-SWITCH ACTIVATED" in str(exc_info.value)
    assert "target.authorized" in str(exc_info.value)

    logs = ScopeAuthorizationGuard.get_audit_log()
    assert len(logs) == 1
    assert logs[0].status == "BLOCKED_UNAUTHORIZED"


def test_scope_guard_killswitch_empty_engagement(empty_engagement_scope_config: TargetScopeConfig):
    with pytest.raises(ScopeAuthorizationError) as exc_info:
        ScopeAuthorizationGuard.enforce(empty_engagement_scope_config, action="EMPTY_ENG_ATTEMPT")

    assert "KILL-SWITCH ACTIVATED" in str(exc_info.value)
    assert "engagement_id" in str(exc_info.value)

    logs = ScopeAuthorizationGuard.get_audit_log()
    assert len(logs) == 1
    assert logs[0].status == "BLOCKED_EMPTY_ENGAGEMENT_ID"
