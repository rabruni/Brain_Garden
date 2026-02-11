# Prompt Router Reference (Admin Agent)
Concise guide to the router module that dispatches user queries to handlers or LLM-assisted flows.

## Purpose
- Classify queries, pick handler, and decide LLM-assisted vs tools-first routing.
- Enforce policy (LLM limits/deny lists) and record evidence (including prompt_pack_id) for ledgers.

## Components
- `modules/router/classifier.py` — pattern-based classifier; outputs `QueryClassification(type, confidence, pattern_matched, extracted_args)`.
- `modules/router/decision.py` — core routing (`route_query`) returning `RouteResult(mode, handler, prompt_pack_id, reason, capabilities_used)`. Maps:
  - HANDLER_MAP: list_installed, explain, check_health, inventory, validate_document, summarize, show_ledger, show_prompts_used, show_session_ledger, read_file, list_frameworks, list_specs, list_files, general.
  - PROMPT_PACK_MAP (LLM-assisted): EXPLAIN→`PRM-ADMIN-EXPLAIN-001`, VALIDATE→`PRM-ADMIN-VALIDATE-001`, SUMMARIZE→`PRM-ADMIN-EXPLAIN-001`, GENERAL→`PRM-ADMIN-GENERAL-001`.
- `modules/router/policy.py` — loads `config/router_policy.json` (if present) and enforces:
  - `max_llm_calls_per_session` (default 10)
  - `llm_deny_list`, `llm_allow_list`
  - `required_capabilities` per query type
  - `custom_handlers` overrides
- `modules/router/__main__.py` — pipe-first CLI: reads JSON from stdin, writes JSON to stdout. Ops: `route`, `classify`, `list_handlers`.
- **Integration:** `modules/admin_agent/agent.py` uses `route_query` + `get_route_evidence`; handlers picked via `modules.admin_agent.handlers.get_handler`; capabilities loaded from `modules/admin_agent/capabilities.json`.

## Modes
- `RouteMode.LLM_ASSISTED` (default today; pattern matching disabled) — sends to LLM handler with prompt pack.
- `RouteMode.TOOLS_FIRST` — forced when policy denies LLM or capability missing.
- `RouteMode.DENIED` — reserved for explicit denials.

## Capabilities & Policy Checks
- Capabilities dict expects `llm_assisted` flags (e.g., `{"llm_assisted": {"validate": true, "summarize": true, "explain": true, "general": true}}`).
- Policy can downgrade to TOOLS_FIRST if deny-listed or LLM budget exceeded.

## Evidence
- `get_route_evidence` returns route metadata (mode, handler, query_type, prompt_pack_id, capabilities_used, reason) for ledger logging; `prompts_used` should include the selected prompt pack ID.

## Usage (pipe-first)
```bash
echo '{"operation":"route","query":"What packages are installed?"}' | python3 -m modules.router
echo '{"operation":"classify","query":"Explain FMWK-000"}' | python3 -m modules.router
```

## Configuration
- Optional: `config/router_policy.json` to tune limits/handlers/capability requirements.
- If missing, defaults apply (LLM limit 10, no deny list).

## Notes
- Pattern classifier exists but `route_query` currently forces LLM_ASSISTED with general handler until pattern routing is re-enabled.
- Prompt pack IDs are hard-coded in `PROMPT_PACK_MAP`; update there when adding governed prompts.
- Admin Agent declares prompt pack via `prompt_pack_id` in context; ledger evidence built via `get_route_evidence`.
