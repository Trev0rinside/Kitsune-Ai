"""Abstract Base Class for LLM Guardrail Targets."""

import abc
import time
from typing import Dict, List, Optional
from reverse_guardrail.core.models import GuardrailResponse, InjectionAttempt, TargetScopeConfig
from reverse_guardrail.core.scope_guard import ScopeAuthorizationGuard


class BaseGuardrailTarget(abc.ABC):
    """Abstract interface for all Target Guardrails (Mock or Real)."""

    # Stateless request/response targets can run a round's probes concurrently.
    # Tab-bound targets (extension relay, browser) must stay sequential: they
    # type into a single shared chat, so overlapping probes would interleave.
    concurrent_safe: bool = False

    def __init__(self, scope_config: TargetScopeConfig):
        self.scope_config = scope_config
        # Verify scope at initialization
        ScopeAuthorizationGuard.enforce(
            self.scope_config, action="INITIALIZE_GUARDRAIL_TARGET"
        )

    async def execute_attempt(
        self,
        attempt: InjectionAttempt,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> GuardrailResponse:
        """Enforces scope authorization gate before dispatching the injection attempt.

        `history` carries prior conversational turns for multi-turn probing; a
        stateless single-shot probe passes None.
        """
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
            response = await self._send_prompt(attempt, history=history)
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

    def get_ground_truth(self) -> Optional[str]:
        """Return the target's true system prompt when the harness knows it.

        Only offline/internal targets (mock, internal LLM under test) can expose
        this; live targets (extension relay, HTTP) return None, and the pipeline
        then falls back to the reverse-engineer's self-reported confidence.
        """
        return None

    @abc.abstractmethod
    async def _send_prompt(
        self,
        attempt: InjectionAttempt,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> GuardrailResponse:
        """Subclasses implement target-specific network communication or simulation.

        `history` (prior [{role, content}] turns) is honoured by stateful/API
        targets; tab-bound targets (extension relay) already carry conversation
        state in the live chat and may ignore it."""
        pass
