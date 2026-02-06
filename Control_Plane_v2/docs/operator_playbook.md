# Operator Playbook

Baseline: `ADMIN_ROUTER_BRAIN_BASELINE_FULL_GREEN` (975/975 tests passing)

## 1. Read-Only Admin Queries

These execute immediately with no confirmation required:

| Query | What it does |
|---|---|
| `Explain FMWK-000` | Show framework details, ownership, dependencies |
| `What is SPEC-CORE-001?` | Explain a spec artifact |
| `Describe PKG-KERNEL-001` | Explain a package |
| `Explain lib/merkle.py` | Show file ownership, hash, functions |
| `What packages are installed?` | List installed packages |
| `Show frameworks` | List registered frameworks |
| `Show ledger` | Display governance/audit log |
| `What is the Control Plane?` | General query (routed to brain advisory) |

General queries return a structured brain advisory with intent, confidence, suggested handler, and proposed next step.

## 2. TOOLS_FIRST Actions

Tools-first handlers (list_installed, explain, check_health, inventory, show_ledger, show_session_ledger, read_file, list_frameworks, list_specs) are gated behind authorization. Three modes:

### DRY_RUN (default)

Any tools-first query without authorization returns a dry-run proposal:

```
> check health

## Proposed Action: check_health
Check system health via trace.py --verify.
To execute, re-send with: RUN:88ce99cf87a6fd60
```

No side effects. The `RUN:` token is deterministic (sha256 of handler + query).

### Two-Turn Execution (RUN token)

Copy the token from the dry-run response and re-send:

```
> check health RUN:88ce99cf87a6fd60

# System Health
| Check       | Status |
|-------------|--------|
| Integrity   | PASS   |
| ...
```

The token is verified before execution. Mismatched tokens are rejected.

### Same-Turn Execution (A0 EXECUTE)

Include both `A0` and `EXECUTE` in the query to skip the dry-run step:

```
> list packages A0 EXECUTE

# Installed Packages
| Package ID       | Version | Status |
|------------------|---------|--------|
| PKG-KERNEL-001   | 1.0.0   | OK     |
| ...
```

Both keywords are stripped from the query before routing.

## 3. Validate / Summarize (LLM_ASSISTED)

These intents always route to LLM-assisted mode regardless of classification confidence:

| Query | Handler | Prompt Pack |
|---|---|---|
| `Validate this document` | validate_document | PRM-ADMIN-VALIDATE-001 |
| `Summarize the frameworks` | summarize | PRM-ADMIN-EXPLAIN-001 |

No dry-run gating. Requires the `llm_assisted` capability to be enabled in `modules/admin_agent/capabilities.json` (it is by default for validate and summarize).

Provider is sourced from `LLM_ASSISTED_PROVIDER` env var, falling back to system default.

## 4. Ledger Reference

When something looks wrong, check these locations:

| What to check | Path | Format |
|---|---|---|
| Governance events (today) | `ledger/governance-YYYYMMDD-*.jsonl` | One JSON object per line |
| LLM call log | `ledger/llm.jsonl` | Prompt used, model, provider, timestamps |
| Ledger index | `ledger/index.jsonl` | Cross-references all ledger files |
| Session exec log | `planes/ho1/sessions/SES-xxx/ledger/exec.jsonl` | Per-turn: query, route decision, handler result |
| Session evidence | `planes/ho1/sessions/SES-xxx/ledger/evidence.jsonl` | Route evidence, handler_executed, authorization |
| Package events | `ledger/packages-*.jsonl` | Install, verify, upgrade events |

### What to look for in evidence entries

Each turn writes an evidence record with:

- `route_decision.mode` — `tools_first` or `llm_assisted`
- `route_decision.handler` — which handler was selected
- `route_decision.confidence` — classification confidence (0.0–1.0)
- `route_decision.router_provider_id` — which LLM provider classified the query
- `handler_executed.authorization` — `dry_run`, `run_token`, `a0_execute`, or `capability`
- `handler_executed.confirmation_id` — the RUN token (present even for A0 EXECUTE path)

### Quick checks

**"Why did my query return a dry-run?"**
The handler was tools-first and no authorization signal was present. Re-send with the `RUN:` token or use `A0 EXECUTE`.

**"Why did my query go to the general handler?"**
The router classified the query with an intent that maps to `general`. Check `route_decision.reason` in the evidence for the classification reasoning.

**"Which LLM provider was used?"**
Check `route_decision.router_provider_id` for routing, and `brain_provider_id` or the `*Provider:*` line in the response for the handler's LLM call.
