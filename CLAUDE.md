# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Kitsune / Reverse-Guardrail: an authorized-red-teaming pipeline that probes an LLM guardrail, reconstructs its hidden system prompt, then threat-models and hardens it. Repo is "Kitsune"; the Python package is `reverse_guardrail` under `src/`.

## Commands

```bash
uv sync                                  # install deps (uv is the package manager)
uv run playwright install chromium       # only needed for browser target mode
uv run pytest -v                         # full suite
uv run pytest tests/unit/test_scope_guard.py::test_name -v   # single test
uv run uvicorn reverse_guardrail.api.app:app --host 127.0.0.1 --port 8888 --reload
```

Port **8888 is not arbitrary** — `extension/background.js` hardcodes `ws://127.0.0.1:8888/ws/relay`. Serving on another port silently breaks the Chrome relay.

No linter/formatter is configured. `pytest.ini_options` sets `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed) and `pythonpath = ["src"]`.

Secrets live in `.env` (gitignored): `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`. Both are optional — see "Offline defaults".

## Architecture

### The closed loop (`orchestrator/graph.py`)

LangGraph `StateGraph` over the Pydantic `PipelineState`:

```
scope_guard_check → tester → inspectioner → reverse_engineer → evaluate_stop
                        ↑__________________________________________|  (continue)
                                                                   ↓  (completed)
                                           vulnerability_analyzer → hardening_reporter → END
```

- Nodes return **partial dicts** that LangGraph merges into state; they never mutate state in place.
- Data crossing nodes within a round rides in `state.metadata` under keys `round_{n}_results`, `round_{n}_refusals`, `round_{n}_extracted_count`. Adding a node that needs round-local data follows that convention.
- Round advancement happens only in `_node_evaluate_stop`, which also owns the three stop conditions (confidence ≥ threshold, fragment stagnation, max rounds) and sets `stop_reason`.
- Every node short-circuits on `PipelineStatus.ABORTED_UNAUTHORIZED`.

### Scope kill-switch (`core/scope_guard.py`)

`authorized: true` + non-empty `engagement_id` is enforced at **three independent layers**: `PipelineRunner.__init__`, the `scope_guard_check` graph node, and `BaseGuardrailTarget.execute_attempt` on *every single probe*. Do not remove a layer to simplify — each blocks a different entry path (SDK, graph, direct target use). Every check appends to the class-level `_audit_log` (in-memory, surfaced at `/api/v1/audit/logs`; `conftest.py` clears it per test).

### Target selection (`orchestrator/runner.py`)

`PipelineRunner.__init__` picks the target via an ordered if/elif fallback chain on `TargetScopeConfig` (`target_mode`, then `target_url`/`use_browser`/name-starts-with-"mock" heuristics), importing each target module lazily. Adding a mode means editing that chain **and** `target_mode` in `core/models.py`. Modes: `extension` (Chrome relay), `internal` (direct LLM API with a system prompt under test), browser (Playwright), http, mock.

### Chrome Extension Relay

The Cloudflare-bypass path: probes are executed inside the user's real Chrome session instead of an automated browser.

`ExtensionRelayGuardrailTarget` → module-level singleton `relay_manager` (`core/relay_manager.py`) → FastAPI `/ws/relay` → `extension/background.js` → `chrome.tabs.sendMessage` → `extension/content.js` → the chat DOM.

- Request/response correlate by `attempt_id` through `_pending_probes: Dict[str, asyncio.Future]`. A timeout resolves to a synthetic 504 `GuardrailResponse`, never an exception.
- WS protocol messages: `HANDSHAKE`, `HEARTBEAT`, `PROBE_REQUEST`, `PROBE_RESPONSE`, `PING`/`PONG`; extension-internal: `EXECUTE_PROBE`.
- `content.js` is deliberately site-agnostic (heuristic input/submit/response selectors + a `MutationObserver` state machine to detect when streaming has settled). It must keep working across Claude/ChatGPT/DeepSeek/Qwen DOMs — prefer widening heuristics over per-site branches.
- Stopping a run calls `relay_manager.cancel_all_pending_probes()` so in-flight futures die immediately.

### Offline defaults (why the suite needs no API keys)

- `get_llm_client()` (`core/llm_provider.py`) returns a deterministic `MockLLMClient` for any `model_spec` starting with `mock`, and all agents default to `mock-*` specs. A new agent that needs offline behavior needs a matching role branch in `MockLLMClient`.
- `GeminiEmbeddingClient` falls back to `_local_hash_vector` when the key is absent or the call fails, so vector search degrades instead of erroring.
- `"deepseek-v4-flash"` is remapped to the real `deepseek-chat` model id inside `get_llm_client`.

### Agent LLM-output contract

Every agent asks its LLM for JSON, strips ``` / ```json fences, `json.loads`, and on **any** exception logs a warning and falls back to a deterministic built-in result (e.g. `TesterAgent._fallback_attempts`, which also top-ups short batches). Keep that shape: a malformed model response must degrade the run, never abort it.

### Storage (`storage/sqlite_store.py`)

Hybrid graph + vector store on one SQLite file (`reverse_guardrail.db` in CWD by default): `fragments` rows carry their embedding as `vector_json`, plus a `graph_edges` table built from cosine similarity. `PipelineRunner.initialize()` calls `store.clear()` — the DB holds only the current run, and results for older `run_id`s survive solely in the in-memory `_RUNNERS` dict in `api/routes.py`. Tests use `db_path=":memory:"`.

### API (`api/routes.py`)

`POST /api/v1/pipeline/start` runs the whole pipeline **synchronously** and returns the final status. The `/vulnerabilities` and `/hardening` GETs lazily generate their Phase-2 report on demand if the pipeline ended before producing one. Runner registry is a plain in-process dict, so state is lost on restart and does not survive multiple workers.

## Conventions

- All target/agent/store I/O is `async`; targets and stores are swapped by constructor injection (`PipelineRunner(config, target=..., store=...)`), which is how tests avoid the network.
- New config knobs go on the Pydantic models in `core/models.py` (`TargetScopeConfig` / `PipelineConfig`) — `config/config.example.yaml` and the dashboard in `api/static/` mirror those fields.
- This codebase is offensive-security tooling for authorized engagements; changes must not weaken the scope gate or the audit log.
