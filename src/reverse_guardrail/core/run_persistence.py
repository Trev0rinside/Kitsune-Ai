"""Persist the latest run's reports to disk so they survive a server restart.

The runner registry (api/routes._RUNNERS) is in-memory, so a --reload, crash, or
plain restart used to lose a completed run's reconstruction / vulnerability /
hardening reports even though the raw fragments persisted in SQLite. This saves
the run's state (minus the bulky per-probe metadata) to one JSON file next to the
DB, and clears it when a new run starts — so the dashboard always shows the most
recent run, and a new run on another site replaces it.

Every operation degrades quietly: a persistence failure must never break a run.
"""

import os
from typing import Optional

from reverse_guardrail.core.logger import logger
from reverse_guardrail.orchestrator.state import PipelineState

RUN_STATE_PATH = os.environ.get("KITSUNE_RUN_STATE_PATH", "reverse_guardrail_run.json")


def save_run_state(state: PipelineState) -> None:
    """Write the run's reports to disk. `metadata` (per-probe results) is excluded
    — it's large and no endpoint serves it."""
    try:
        payload = state.model_dump_json(exclude={"metadata"})
        with open(RUN_STATE_PATH, "w") as f:
            f.write(payload)
        logger.info(f"[RunPersistence] Saved run {state.run_id} to {RUN_STATE_PATH}")
    except Exception as err:
        logger.warning(f"[RunPersistence] Failed to save run state: {err}")


def load_run_state() -> Optional[PipelineState]:
    """Load the persisted run, or None if absent/unreadable."""
    if not os.path.exists(RUN_STATE_PATH):
        return None
    try:
        with open(RUN_STATE_PATH) as f:
            return PipelineState.model_validate_json(f.read())
    except Exception as err:
        logger.warning(f"[RunPersistence] Failed to load run state: {err}")
        return None


def clear_run_state() -> None:
    """Remove the persisted run (called when a new run starts)."""
    try:
        if os.path.exists(RUN_STATE_PATH):
            os.remove(RUN_STATE_PATH)
            logger.info(f"[RunPersistence] Cleared persisted run state ({RUN_STATE_PATH})")
    except Exception as err:
        logger.warning(f"[RunPersistence] Failed to clear run state: {err}")
