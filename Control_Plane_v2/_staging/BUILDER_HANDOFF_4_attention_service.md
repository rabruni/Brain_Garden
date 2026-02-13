# Builder Handoff #4: Attention Service + Framework Manifests

## Mission

Build the attention service — the component that assembles context for an agent before a prompt is sent. Also ship two new framework manifests (FMWK-003 Prompt Routing, FMWK-004 Attention) that formalize governance over the runtime pipeline.

**CRITICAL CONSTRAINTS — read before doing anything:**

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** New code ships as packages in `_staging/PKG-<NAME>/` with manifest.json, SHA256 hashes, proper dependencies.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → install Layers 0-2 (8 packages) → install Layer 3 packages (`PKG-PHASE2-SCHEMAS-001`, `PKG-TOKEN-BUDGETER-001`, `PKG-PROMPT-ROUTER-001`, `PKG-ATTENTION-001`) → all gates pass.
5. **No hardcoding.** Every threshold, weight, pattern, timeout — all config-driven. This is the #1 lesson from 7 layers of prior art.
6. **No file replacement.** Packages must NEVER overwrite another package's files.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .`

---

## New Frameworks

Two new frameworks formalize governance over the runtime pipeline. Each ships as an asset in its respective package.

### FMWK-003: Prompt Routing

**Ships in:** PKG-PROMPT-ROUTER-001 (from Handoff #3)

```yaml
framework_id: FMWK-003
title: Prompt Routing Framework
version: "1.0.0"
status: active
ring: kernel
plane_id: hot
created_at: "2026-02-10T00:00:00Z"
assets:
  - prompt_routing_standard.md
expected_specs:
  - SPEC-ROUTING-001
invariants:
  - level: MUST
    statement: Every LLM invocation MUST be logged to the ledger in both directions (PROMPT_SENT + PROMPT_RECEIVED)
  - level: MUST
    statement: Every LLM invocation MUST pass AuthN/AuthZ and budget check before dispatch
  - level: MUST NOT
    statement: The router MUST NOT assemble context — context arrives fully assembled from the attention service
  - level: MUST NOT
    statement: Circuit breaker thresholds, rate limits, and pricing MUST NOT be hardcoded
  - level: MUST
    statement: All error paths MUST log to the ledger — no silent failures
path_authorizations:
  - "HOT/kernel/prompt_router.py"
  - "HOT/kernel/provider.py"
  - "HOT/kernel/token_budgeter.py"
  - "HOT/schemas/router_config.schema.json"
  - "HOT/schemas/budget_config.schema.json"
  - "HOT/FMWK-003_Prompt_Routing/*.yaml"
  - "HOT/FMWK-003_Prompt_Routing/*.md"
  - "HOT/tests/test_prompt_router.py"
  - "HOT/tests/test_token_budgeter.py"
required_gates:
  - G0
  - G1
  - G5
```

### FMWK-004: Attention

**Ships in:** PKG-ATTENTION-001 (this handoff)

```yaml
framework_id: FMWK-004
title: Attention Framework
version: "1.0.0"
status: active
ring: kernel
plane_id: hot
created_at: "2026-02-10T00:00:00Z"
assets:
  - attention_standard.md
expected_specs:
  - SPEC-ATTENTION-001
invariants:
  - level: MUST
    statement: Context assembly MUST follow the pipeline defined in the attention template — no ad-hoc assembly
  - level: MUST
    statement: Every pipeline stage MUST be config-driven via the template's config object
  - level: MUST NOT
    statement: Thresholds, weights, patterns, and search depths MUST NOT be hardcoded
  - level: MUST
    statement: Context assembly MUST respect budget constraints (max_context_tokens, max_queries, timeout_ms)
  - level: MUST
    statement: Halting decisions MUST be explicit and logged — no implicit "good enough" stops
  - level: MUST NOT
    statement: The attention service MUST NOT send prompts — it assembles context and returns it to the caller
path_authorizations:
  - "HOT/kernel/attention_service.py"
  - "HOT/kernel/attention_stages.py"
  - "HOT/FMWK-004_Attention/*.yaml"
  - "HOT/FMWK-004_Attention/*.md"
  - "HOT/tests/test_attention_service.py"
required_gates:
  - G0
  - G1
  - G5
```

**NOTE:** The agents building PKG-PROMPT-ROUTER-001 (Handoff #3) and PKG-ATTENTION-001 (this handoff) are each responsible for shipping their framework's manifest.yaml as a package asset. The frameworks_registry.csv will be rebuilt via `rebuild_derived_registries.py` after install.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                      CALLER                                  │
│         (flow runner / agent orchestrator)                    │
│                                                              │
│  "Agent X needs to execute WO Y using prompt contract Z"     │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                  ATTENTION SERVICE                            │
│                                                              │
│  1. Resolve attention template (match agent → template)      │
│  2. Merge required_context from prompt contract              │
│  3. Run pipeline stages in order:                            │
│     tier_select → queries → structuring → halting            │
│  4. Enforce budget (max tokens, max queries, timeout)        │
│  5. Return assembled context                                 │
└────────────┬────────────────────────┬────────────────────────┘
             │                        │
             ▼                        ▼
┌────────────────────┐    ┌───────────────────────┐
│   LEDGER (read)    │    │  REGISTRIES (read)    │
│   query entries    │    │  frameworks, specs,   │
│   by provenance    │    │  file_ownership       │
└────────────────────┘    └───────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────┐
│                  PROMPT ROUTER                                │
│           (receives assembled context from above)             │
│           log → send → log → return                          │
└──────────────────────────────────────────────────────────────┘
```

The attention service is **read-only at runtime** — it reads ledger entries, registries, and files to assemble context. It does NOT write to the ledger (the router handles all logging). It does NOT send prompts.

---

## Component: Attention Service

### What It Does

Given an agent, a work order, and a prompt contract — assemble the right context by running a config-driven pipeline.

### Inputs

```python
@dataclass
class AttentionRequest:
    agent_id: str               # Who needs context
    agent_class: str            # KERNEL.syntactic | KERNEL.semantic | ADMIN | RESIDENT
    framework_id: str           # Framework the agent belongs to
    tier: str                   # hot | ho2 | ho1
    work_order_id: str          # WO being executed
    session_id: str             # Session scope
    prompt_contract: dict       # The prompt contract (has required_context)
    template_override: str | None  # Optional: force a specific template_id
```

### Outputs

```python
@dataclass
class AssembledContext:
    context_text: str           # The assembled context as text
    context_hash: str           # SHA256 of context_text
    fragments: list[ContextFragment]  # Individual pieces that were assembled
    template_id: str            # Which template was used
    pipeline_trace: list[StageResult]  # What each stage did (for debugging/audit)
    budget_used: BudgetUsed     # How much of the budget was consumed
    warnings: list[str]         # Any non-fatal issues (truncation, fallback, etc.)

@dataclass
class ContextFragment:
    source: str                 # "ledger", "registry", "file", "search"
    source_id: str              # Specific entry/file/query that produced this
    content: str                # The text content
    token_estimate: int         # Estimated tokens (for budget tracking)
    relevance_score: float | None  # 0-1, if scored by search (None if not scored)

@dataclass
class StageResult:
    stage: str                  # Stage name
    type: str                   # Stage type
    fragments_produced: int     # How many fragments this stage found
    tokens_produced: int        # Estimated tokens from this stage
    duration_ms: int            # How long this stage took
    status: str                 # "ok", "truncated", "timeout", "empty", "skipped"
```

### Step-by-Step Flow

#### Step 1: Template Resolution

Find the right attention template for this agent:

1. If `template_override` is provided, load that template directly
2. Otherwise, match based on the `applies_to` selector in registered templates:
   - Match `agent_class` (e.g., template for KERNEL.syntactic agents)
   - Match `framework_id` (e.g., template specific to FMWK-003)
   - Match `tier` (e.g., template for ho1 agents)
3. Specificity order: framework_id > agent_class > tier (most specific match wins)
4. If no template matches → use a default minimal template (just file_read from required_context)
5. **FAIL-CLOSED**: if multiple templates match at the same specificity → fail, don't guess

#### Step 2: Merge Required Context

The prompt contract's `required_context` specifies what the prompt NEEDS. The attention template defines HOW to assemble it. Merge them:

- `required_context.ledger_queries` → add as `ledger_query` stages if not already in pipeline
- `required_context.framework_refs` → add as `registry_query` stages for framework definitions
- `required_context.file_refs` → add as `file_read` stages

Template pipeline stages take priority. Required context fills gaps.

#### Step 3: Run Pipeline

Execute stages in order. Each stage:
1. Check if `enabled` (skip if false)
2. Read stage `config` from template
3. Execute the stage
4. Produce `ContextFragment`(s)
5. Track budget consumption (tokens, queries, time)
6. Check budget — if exceeded, stop and apply fallback

#### Stage Types

**`tier_select`**
- Config: `{tiers: ["hot", "ho2"], strategy: "highest_first" | "all_parallel"}`
- Determines which tiers subsequent queries will search
- Output: sets tier scope for later stages (no fragments produced)

**`ledger_query`**
- Config: `{event_type: "PROMPT_RECEIVED", tier: "ho2", max_entries: 10, recency: "session", filters: {...}}`
- Queries the ledger using the provenance fields as indexes
- Uses existing `ledger_client.py` query capabilities
- Output: fragments containing matching ledger entries
- Budget: each query counts against `max_queries`

**`registry_query`**
- Config: `{registry: "frameworks" | "specs" | "file_ownership", filters: {...}}`
- Reads from CSV registries
- Output: fragments containing matching registry rows
- Example: load framework definition for `FMWK-003` into context

**`file_read`**
- Config: `{paths: ["HOT/schemas/work_order.schema.json", ...], max_size_bytes: 10000}`
- Reads specific files into context
- Output: fragments containing file contents
- Budget: file content counts against `max_context_tokens`

**`horizontal_search`**
- Config: `{query: "...", tiers: ["hot", "ho2"], sources: ["ledger", "registry", "files"], max_results: 20, relevance_threshold: 0.5}`
- Searches across multiple sources for relevant content
- This is the "exploration" stage — broader than targeted queries
- In v1, this can be keyword-based; in v2, embeddings can be plugged in
- Output: scored fragments
- Config-driven relevance threshold (the "no hardcoding" rule applies especially here)

**`structuring`**
- Config: `{strategy: "chronological" | "relevance" | "hierarchical", max_tokens: 8000}`
- Organizes collected fragments into coherent context
- Deduplicates overlapping content
- Applies token budget: if total exceeds max_tokens, truncate lowest-relevance fragments
- Output: reordered/truncated fragment list

**`halting`**
- Config: `{min_fragments: 1, min_tokens: 100, satisfaction_threshold: 0.7}`
- Decides if assembled context is "good enough"
- Checks: do we have required_context coverage? Are minimum thresholds met?
- If not satisfied AND budget remains → can trigger re-run of search stages with relaxed params
- If not satisfied AND budget exhausted → apply fallback (on_empty behavior)
- Halting decision is explicit and returned in pipeline_trace

**`custom`**
- Config: `{handler: "module.path.function_name", ...}`
- Extensibility hook — calls a registered function
- For v1, just support this in the interface; no built-in custom handlers needed

#### Step 4: Budget Enforcement

Throughout pipeline execution, track:
- `tokens_assembled`: running total of estimated context tokens
- `queries_executed`: running total of ledger/registry queries
- `elapsed_ms`: wall-clock time since pipeline started

At each stage, check:
- `tokens_assembled < budget.max_context_tokens`
- `queries_executed < budget.max_queries`
- `elapsed_ms < budget.timeout_ms`

If any limit is exceeded:
- Stop pipeline execution
- Apply `fallback.on_timeout` behavior:
  - `return_partial`: return what we have so far
  - `fail`: return error, no context
  - `use_cached`: return cached context from previous run (if available)

#### Step 5: Return

Package everything into `AssembledContext`:
- `context_text`: concatenated fragments in structuring order
- `context_hash`: SHA256 of context_text
- `fragments`: the full fragment list with sources
- `pipeline_trace`: what each stage did
- `budget_used`: how much budget was consumed
- `warnings`: any truncation, fallback, or coverage gaps

---

## Token Estimation

The attention service needs to estimate token counts WITHOUT calling an LLM tokenizer (that would be a dependency we don't want). Use a simple heuristic:

```python
def estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 chars per token for English text."""
    return len(text) // 4
```

This is a config-driven parameter (`chars_per_token: 4`) so it can be tuned. The prompt router will get ACTUAL token counts back from the provider — the attention service just needs estimates for budget tracking.

---

## Caching (v1: Simple)

For v1, cache at the template level:
- Key: `(template_id, agent_class, work_order_id, session_id)`
- TTL: configurable, default short (e.g., 60s)
- Purpose: if the same agent sends multiple prompts in quick succession under the same WO, reuse context
- Cache is in-memory only — no persistence
- `fallback.on_timeout: "use_cached"` uses this cache

---

## Error Handling

| Condition | Behavior |
|-----------|----------|
| No template matches | Use minimal default (file_read from required_context only), warn |
| Multiple templates at same specificity | Fail-closed, return error |
| Ledger query fails | Skip stage, warn, continue pipeline |
| File not found | Skip fragment, warn, continue pipeline |
| Budget exceeded mid-pipeline | Stop, apply fallback.on_timeout |
| All stages produce nothing | Apply fallback.on_empty |
| Structuring exceeds max_tokens | Truncate lowest-relevance fragments |

Every error/warning is captured in `AssembledContext.warnings` and `pipeline_trace`. The caller (flow runner) decides what to do.

---

## Package Plan

### PKG-ATTENTION-001 (Layer 3)

Assets:
- `HOT/kernel/attention_service.py` — main service: template resolution, pipeline execution, budget enforcement
- `HOT/kernel/attention_stages.py` — stage implementations (tier_select, ledger_query, registry_query, file_read, horizontal_search, structuring, halting, custom)
- `HOT/FMWK-004_Attention/manifest.yaml` — framework manifest
- `HOT/tests/test_attention_service.py` — all tests

Dependencies:
- `PKG-KERNEL-001` (for ledger_client, paths)
- `PKG-PHASE2-SCHEMAS-001` (for attention_template.schema.json)

**NOTE:** PKG-PROMPT-ROUTER-001 (Handoff #3) must also ship `HOT/FMWK-003_Prompt_Routing/manifest.yaml` as an asset. Update that package's manifest.json accordingly.

---

## Test Plan (DTT — Tests First)

### Write ALL these tests BEFORE any implementation code.

**Template Resolution:**
1. `test_resolve_by_agent_class` — matches template by agent_class
2. `test_resolve_by_framework_id` — matches template by framework_id (higher specificity)
3. `test_resolve_by_tier` — matches template by tier
4. `test_specificity_order` — framework_id wins over agent_class wins over tier
5. `test_no_match_uses_default` — no matching template → minimal default with warning
6. `test_multiple_matches_fail_closed` — ambiguous match → error, not guess
7. `test_template_override` — explicit template_id bypasses matching

**Required Context Merge:**
8. `test_merge_ledger_queries` — prompt contract's ledger queries added to pipeline
9. `test_merge_framework_refs` — framework_refs become registry_query stages
10. `test_merge_file_refs` — file_refs become file_read stages
11. `test_template_stages_take_priority` — existing pipeline stages not duplicated

**Pipeline Execution:**
12. `test_stages_run_in_order` — stages execute sequentially as defined
13. `test_disabled_stage_skipped` — enabled:false stages are skipped
14. `test_ledger_query_produces_fragments` — ledger_query returns ContextFragments
15. `test_registry_query_produces_fragments` — registry_query returns ContextFragments
16. `test_file_read_produces_fragments` — file_read returns file content as fragment
17. `test_file_not_found_warns` — missing file → warning, not error
18. `test_horizontal_search_scores_fragments` — search results have relevance_score
19. `test_structuring_deduplicates` — overlapping content deduplicated
20. `test_structuring_truncates_to_budget` — lowest-relevance fragments dropped when over max_tokens
21. `test_halting_satisfied` — sufficient context → pipeline stops cleanly
22. `test_halting_insufficient_reruns` — not enough context + budget remaining → retry search
23. `test_custom_stage_calls_handler` — custom stage invokes registered function

**Budget Enforcement:**
24. `test_budget_max_tokens_stops_pipeline` — exceeding token budget stops execution
25. `test_budget_max_queries_stops_pipeline` — exceeding query budget stops execution
26. `test_budget_timeout_stops_pipeline` — exceeding time budget stops execution
27. `test_fallback_return_partial` — on_timeout:"return_partial" returns what we have
28. `test_fallback_fail` — on_timeout:"fail" returns error
29. `test_fallback_use_cached` — on_timeout:"use_cached" returns cached context
30. `test_fallback_on_empty_proceed` — no context + on_empty:"proceed_empty" returns empty
31. `test_fallback_on_empty_fail` — no context + on_empty:"fail" returns error

**Output:**
32. `test_context_hash_computed` — SHA256 of context_text in output
33. `test_pipeline_trace_recorded` — every stage produces StageResult
34. `test_budget_used_reported` — output includes actual budget consumption
35. `test_warnings_collected` — all warnings from all stages in output

**Caching:**
36. `test_cache_hit_returns_cached` — same key within TTL returns cached
37. `test_cache_miss_runs_pipeline` — different key runs full pipeline
38. `test_cache_ttl_expires` — expired entry triggers fresh run

**Token Estimation:**
39. `test_estimate_tokens_basic` — heuristic returns reasonable estimate
40. `test_estimate_tokens_configurable` — chars_per_token from config

### End-to-End Test
1. Clean-room extract CP_BOOTSTRAP → install Layers 0-2 (8 packages)
2. Install PKG-PHASE2-SCHEMAS-001 (Layer 3)
3. Install PKG-TOKEN-BUDGETER-001 (Layer 3)
4. Install PKG-PROMPT-ROUTER-001 (Layer 3)
5. Install PKG-ATTENTION-001 (Layer 3)
6. All gates pass at every step
7. Integration test: create attention template → create prompt contract with required_context → call attention service → verify assembled context contains expected fragments → feed context to prompt router (mock provider) → verify full round-trip

---

## Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Attention template schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/attention_template.schema.json` | Pipeline definition |
| Prompt contract schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/prompt_contract.schema.json` | required_context |
| Ledger metadata schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/ledger_entry_metadata.schema.json` | Provenance fields for queries |
| Ledger client | `_staging/PKG-KERNEL-001/HOT/kernel/` or installed `HOT/kernel/ledger_client.py` | Query ledger |
| Registries | `HOT/registries/frameworks_registry.csv`, `specs_registry.csv`, `file_ownership.csv` | Registry queries |
| Framework manifest pattern | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/FMWK-000_Governance/manifest.yaml` | Framework format |
| Package manifest pattern | `_staging/PKG-PHASE2-SCHEMAS-001/manifest.json` | Package manifest format |
| Prompt router handoff | `_staging/BUILDER_HANDOFF_3_prompt_router.md` | Router interface (your output feeds this) |
| Install script | `_staging/PKG-KERNEL-001/HOT/scripts/package_install.py` | For end-to-end testing |

---

## Design Principles (Non-Negotiable)

1. **Attention is read-only.** It reads ledger, registries, and files. It does NOT write to the ledger and does NOT send prompts. Those are the router's job.
2. **Pipeline is king.** Every context assembly follows the template's pipeline. No ad-hoc assembly, no shortcuts.
3. **No hardcoding.** Relevance thresholds, search depths, token budgets, halting criteria — all from the template's config objects. If you find yourself typing a literal number in stage logic, it must come from config.
4. **Fail-open on individual stages, fail-closed on ambiguity.** A missing file or empty query → warn and continue. An ambiguous template match → stop and error.
5. **Budget is law.** If the budget says stop, you stop. No "just one more query."
6. **Fragments are traceable.** Every fragment knows its source. The caller can audit exactly where each piece of context came from.
7. **Halting is explicit.** The pipeline trace must show WHY the pipeline stopped — budget, satisfaction, or completion. No implicit stops.
