"""Learn, per target site, which CSS selectors actually capture a chat reply.

The extension ships static selector lists. They silently miss any site they were
not written for: on a miss `getAssistantMessages()` returns nothing and the probe
burns its full stream timeout before handing back empty text, which reads as a
"capture error" while looking like a slow target.

Rather than widening those lists forever, this asks a model to read the real DOM
once per host and name the two selectors that matter. The extension caches the
answer and every later probe captures precisely instead of guessing.

Failure is always soft: any bad reply degrades to (None, None), which leaves the
extension on its existing heuristics.
"""

import json
from typing import Any, Dict, Optional

from reverse_guardrail.core.llm_provider import extract_json, get_llm_client
from reverse_guardrail.core.logger import logger

CALIBRATION_SYSTEM_PROMPT = """You are a DOM analysis expert. You are given an HTML snapshot of a web chat interface \
(a conversation between a human user and an AI assistant) and the text of the message the user just sent.

Identify two CSS selectors:

1. "assistant_selector": matches the container elements holding the ASSISTANT's reply text.
   - It must match assistant replies only, never the user's own messages.
   - `document.querySelectorAll(assistant_selector)` should return the replies in document order,
     so the LAST match is the newest reply.
   - Prefer stable hooks (data-* attributes, semantic class names) over generated/hashed classes.

2. "generating_selector": matches an element that is present and visible ONLY WHILE the assistant
   is still generating (a stop/cancel button, a streaming cursor, a spinner).
   - This is used to detect that the reply is finished, so it MUST NOT match anything that is
     always on the page. If you cannot find a reliable one, return null.

Both must be valid CSS accepted by document.querySelectorAll.

Respond with ONLY this JSON object and nothing else:
{"assistant_selector": "<css>", "generating_selector": "<css or null>"}"""


async def calibrate_selectors(
    dom_snapshot: str,
    probe_text: str = "",
    url: str = "",
    model_spec: str = "deepseek-chat",
    client: Any = None,
) -> Dict[str, Optional[str]]:
    """Ask the model for this site's capture selectors.

    Returns {"assistant_selector": str|None, "generating_selector": str|None}.
    Never raises: on any failure both are None and the caller keeps its heuristics.
    """
    empty: Dict[str, Optional[str]] = {
        "assistant_selector": None,
        "generating_selector": None,
    }
    if not dom_snapshot.strip():
        return empty

    prompt = (
        f"Page URL: {url or 'unknown'}\n"
        f"Message the user just sent: {probe_text[:500] or '(unknown)'}\n\n"
        f"HTML snapshot:\n{dom_snapshot}"
    )

    try:
        llm = client or get_llm_client(model_spec)
        raw = await llm.generate(
            prompt=prompt,
            system_prompt=CALIBRATION_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=400,
        )
        parsed = json.loads(extract_json(raw))
    except Exception as err:  # malformed reply, no key, network — all degrade
        logger.warning(f"[CaptureCalibrator] Calibration failed for {url}: {err}")
        return empty

    return {
        "assistant_selector": _clean_selector(parsed.get("assistant_selector")),
        "generating_selector": _clean_selector(parsed.get("generating_selector")),
    }


def _clean_selector(value: Any) -> Optional[str]:
    """Keep only a plausible one-line CSS selector; anything else becomes None."""
    if not isinstance(value, str):
        return None
    selector = value.strip()
    if not selector or selector.lower() == "null" or "\n" in selector:
        return None
    return selector
