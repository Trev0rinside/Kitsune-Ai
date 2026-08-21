"""Scope authorization guard and kill-switch mechanism for Reverse-Guardrail.

This module acts as an unconditional security barrier: no probing, injection, or
network request to the target guardrail is permitted unless explicit authorization
and a valid engagement_id are verified.
"""

from typing import Any, Dict, List, Optional, Union
from reverse_guardrail.core.models import AuditLogEntry, PipelineConfig, TargetScopeConfig


class ScopeAuthorizationError(PermissionError):
    """Raised when pipeline execution is attempted without proper scope authorization."""
    pass


class ScopeAuthorizationGuard:
    """Gatekeeper that verifies customer authorization and logs security audit trails."""

    _audit_log: List[AuditLogEntry] = []

    @classmethod
    def verify(
        cls,
        config: Union[PipelineConfig, TargetScopeConfig, Dict[str, Any]],
    ) -> bool:
        """Check if the provided configuration has valid scope authorization."""
        scope = cls._extract_scope(config)
        if scope is None:
            return False

        has_auth = bool(scope.authorized is True)
        has_engagement_id = bool(
            scope.engagement_id and scope.engagement_id.strip()
        )
        return has_auth and has_engagement_id

    @classmethod
    def enforce(
        cls,
        config: Union[PipelineConfig, TargetScopeConfig, Dict[str, Any]],
        action: str = "PIPELINE_START",
        details: Optional[Dict[str, Any]] = None,
    ) -> TargetScopeConfig:
        """Enforces scope authorization. Raises ScopeAuthorizationError if invalid."""
        scope = cls._extract_scope(config)
        details = details or {}

        if scope is None or not scope.authorized:
            audit_entry = AuditLogEntry(
                engagement_id=scope.engagement_id if scope else "UNSET",
                action=action,
                status="BLOCKED_UNAUTHORIZED",
                details={
                    "reason": "target.authorized is not True",
                    **details,
                },
            )
            cls._audit_log.append(audit_entry)
            raise ScopeAuthorizationError(
                "KILL-SWITCH ACTIVATED: Execution blocked because 'target.authorized' is False. "
                "You must obtain written authorization from the system owner and set 'target.authorized: true'."
            )

        if not scope.engagement_id or not scope.engagement_id.strip():
            audit_entry = AuditLogEntry(
                engagement_id="EMPTY",
                action=action,
                status="BLOCKED_EMPTY_ENGAGEMENT_ID",
                details={
                    "reason": "engagement_id is empty or missing",
                    **details,
                },
            )
            cls._audit_log.append(audit_entry)
            raise ScopeAuthorizationError(
                "KILL-SWITCH ACTIVATED: Execution blocked because 'engagement_id' is empty. "
                "A non-empty engagement tracking ID is mandatory for security auditability."
            )

        # Log authorized action
        audit_entry = AuditLogEntry(
            engagement_id=scope.engagement_id,
            action=action,
            status="AUTHORIZED_ACCESS",
            details={
                "target_name": scope.target_name,
                "target_url": scope.target_url,
                **details,
            },
        )
        cls._audit_log.append(audit_entry)
        return scope

    @classmethod
    def get_audit_log(cls) -> List[AuditLogEntry]:
        """Returns recorded audit log entries."""
        return list(cls._audit_log)

    @classmethod
    def clear_audit_log(cls) -> None:
        """Clears audit log (used in tests)."""
        cls._audit_log.clear()

    @staticmethod
    def _extract_scope(
        config: Union[PipelineConfig, TargetScopeConfig, Dict[str, Any]],
    ) -> Optional[TargetScopeConfig]:
        if isinstance(config, PipelineConfig):
            return config.target
        elif isinstance(config, TargetScopeConfig):
            return config
        elif isinstance(config, dict):
            target_dict = config.get("target", config)
            try:
                return TargetScopeConfig(**target_dict)
            except Exception:
                return None
        return None
