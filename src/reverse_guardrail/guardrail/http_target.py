"""HTTP REST adapter for probing real authorized LLM Guardrail endpoints."""

import time
from typing import Any, Callable, Dict, List, Optional
import httpx
from reverse_guardrail.core.models import GuardrailResponse, InjectionAttempt, TargetScopeConfig
from reverse_guardrail.core.rate_limiter import execute_with_backoff
from reverse_guardrail.guardrail.base import BaseGuardrailTarget


class HttpGuardrailTarget(BaseGuardrailTarget):
    """Plug-in adapter for connecting to a real external Guardrail over HTTP/REST."""

    concurrent_safe = True

    def __init__(
        self,
        scope_config: TargetScopeConfig,
        request_template: Optional[Dict[str, Any]] = None,
        prompt_key: str = "prompt",
        response_extractor: Optional[Callable[[Dict[str, Any]], str]] = None,
        timeout_seconds: float = 15.0,
    ):
        super().__init__(scope_config)
        self.target_url = scope_config.target_url or "http://localhost:8000/api/chat"
        self.request_template = request_template or {}
        self.prompt_key = prompt_key
        self.response_extractor = response_extractor
        self.timeout = timeout_seconds

    async def _send_prompt(
        self,
        attempt: InjectionAttempt,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> GuardrailResponse:
        """Send the prompt payload to the external HTTP target."""
        start = time.monotonic()

        body = dict(self.request_template)
        body[self.prompt_key] = attempt.payload
        if history:
            # Best-effort multi-turn: hand the endpoint the full transcript so a
            # chat-completions-style API can keep context across turns.
            body["messages"] = history + [{"role": "user", "content": attempt.payload}]

        headers = {
            "Content-Type": "application/json",
            **self.scope_config.custom_headers,
        }

        if self.scope_config.api_token:
            token = self.scope_config.api_token.strip()
            if not token.lower().startswith("bearer ") and not token.lower().startswith("basic "):
                headers["Authorization"] = f"Bearer {token}"
            else:
                headers["Authorization"] = token

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async def _do_request() -> httpx.Response:
                r = await client.post(self.target_url, json=body, headers=headers)
                # Retry transient upstream failures; treat 5xx as retryable so a
                # blip doesn't burn the probe (and the leak it might have surfaced).
                if r.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Upstream {r.status_code}", request=r.request, response=r
                    )
                return r

            resp = await execute_with_backoff(
                _do_request,
                max_retries=2,
                initial_delay=0.5,
                retry_exceptions=(httpx.TransportError, httpx.HTTPStatusError),
            )
            latency_ms = (time.monotonic() - start) * 1000.0

            raw_text = ""
            refused = False

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if self.response_extractor:
                        raw_text = self.response_extractor(data)
                    elif "response" in data:
                        raw_text = str(data["response"])
                    elif "message" in data:
                        raw_text = str(data["message"])
                    elif "choices" in data:
                        raw_text = data["choices"][0]["message"]["content"]
                    else:
                        raw_text = resp.text
                except Exception:
                    raw_text = resp.text
            elif resp.status_code in (400, 403, 422):
                refused = True
                raw_text = resp.text
            else:
                raw_text = f"HTTP {resp.status_code}: {resp.text}"

            # Simple heuristic on refusal text
            refusal_markers = [
                "cannot comply", "violates policy", "safety violation",
                "request refused", "forbidden", "disallowed content"
            ]
            if any(marker in raw_text.lower() for marker in refusal_markers):
                refused = True

            return GuardrailResponse(
                attempt_id=attempt.attempt_id,
                round_id=attempt.round_id,
                raw_response=raw_text,
                latency_ms=latency_ms,
                refused=refused,
                status_code=resp.status_code,
            )
