"""Abstract Base Class for LLM Guardrail Targets."""

import abc
import time
from typing import Optional
from reverse_guardrail.core.models import GuardrailResponse, InjectionAttempt, TargetScopeConfig
from reverse_guardrail.core.scope_guard import ScopeAuthorizationGuard


class BaseGuardrailTarget(abc.ABC):
    """Abstract interface for all Target Guardrails (Mock or Real)."""

    def __init__(self, scope_config: TargetScopeConfig):
        self.scope_config = scope_config
        # Verify scope at initialization
        ScopeAuthorizationGuard.enforce(
            self.scope_config, action="INITIALIZE_GUARDRAIL_TARGET"
        )

    async def execute_attempt(self, attempt: InjectionAttempt) -> GuardrailResponse:
        """Enforces scope authorization gate before dispatching the injection attempt."""
        # Unconditional check on every execution
        ScopeAuthorizationGuard.enforce(
            self.scope_config,
            action="GUARDRAIL_PROBE_ATTEMPT",
            details={
                "attempt_id": attempt.attempt_id,
                "round_id": attempt.round_id,
                "strategy": attempt.strategy_category.value,
            },
        )
        start_time = time.monotonic()
        try:
            response = await self._send_prompt(attempt)
            return response
        except Exception as exc:
            latency_ms = (time.monotonic() - start_time) * 1000.0
            return GuardrailResponse(
                attempt_id=attempt.attempt_id,
                round_id=attempt.round_id,
                raw_response="",
                latency_ms=latency_ms,
                refused=False,
                status_code=500,
                error_message=str(exc),
            )

    @abc.abstractmethod
    async def _send_prompt(self, attempt: InjectionAttempt) -> GuardrailResponse:
        """Subclasses implement target-specific network communication or simulation."""
        pass
