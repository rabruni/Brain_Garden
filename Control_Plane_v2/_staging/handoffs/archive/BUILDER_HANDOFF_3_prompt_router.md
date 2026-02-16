# Builder Handoff #3: Prompt Router + Token Budgeter

## Mission

Build the prompt routing infrastructure: a "dumb" single-shot router that logs both directions to the ledger, plus a separate token budgeter/throttler for resource management. These are two distinct components that compose at runtime.

**CRITICAL CONSTRAINTS — read before doing anything:**

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** New code ships as packages in `_staging/PKG-<NAME>/` with manifest.json, SHA256 hashes, proper dependencies. Follow the pattern in `_staging/PKG-PHASE2-SCHEMAS-001/` and `_staging/PKG-KERNEL-001/`.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → install Layers 0-2 (8 packages) → install Layer 3 (`PKG-PHASE2-SCHEMAS-001`) → install YOUR new packages. All gates must pass (G0B, G0A, G1, G1-COMPLETE, G5).
5. **No hardcoding.** Every threshold, timeout, retry count, rate limit — all config-driven. This is the #1 lesson from 7 layers of prior art.
6. **No file replacement.** Packages must NEVER overwrite another package's files. Use state-gating instead.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`).

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                      CALLER                             │
│            (flow runner / agent)                        │
└────────────────────┬────────────────────────────────────┘
                     │ PromptRequest
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  PROMPT ROUTER                          │
│                                                         │
│  1. Validate input (prompt contract)                    │
│  2. AuthN/AuthZ check                                   │
│  3. Budget check (→ Token Budgeter)                     │
│  4. Pre-log (→ Ledger: PROMPT_SENT)                     │
│  5. Compute context hash                                │
│  6. Dispatch to provider                                │
│  7. Post-log (→ Ledger: PROMPT_RECEIVED)                │
│  8. Token accounting (→ Token Budgeter: debit)          │
│  9. Validate output (if structured_output defined)      │
│ 10. Return response                                     │
└──────┬──────────────────────────────────┬───────────────┘
       │                                  │
       ▼                                  ▼
┌──────────────┐                 ┌────────────────────┐
│   LEDGER     │                 │  TOKEN BUDGETER    │
│ (existing)   │                 │  (new, separate)   │
└──────────────┘                 └────────────────────┘
```

The router is **single-shot**: one prompt in, one response out. Context is already fully assembled by the attention service before reaching the router. The router does NOT assemble context — it just validates, logs, sends, logs, and returns.

---

## Component 1: Prompt Router

### What It Does

`log → send → log → return`

That's it. It's plumbing, not intelligence.

### Step-by-Step Flow

#### Step 1: Input Validation
- Validate the incoming request against `prompt_contract.schema.json`
- Check that `boundary.max_tokens` and `boundary.temperature` are present
- If `input_schema` is defined in the contract, validate template variables against it
- **FAIL-CLOSED**: invalid input → reject immediately, log rejection to ledger

#### Step 2: AuthN/AuthZ
- Use existing `auth.py` / `authz.py` patterns from `HOT/kernel/`
- Verify the caller identity (agent_id, agent_class)
- Verify the caller is authorized to use this prompt pack
- Verify the caller's framework permits LLM invocations
- Dev mode (`--dev` / passthrough auth) must work for testing
- **FAIL-CLOSED**: unauthorized → reject, log to ledger

#### Step 3: Budget Check
- Query the Token Budgeter: "Does this agent/WO/session have budget for N tokens?"
- The budgeter returns: `{allowed: bool, remaining: int, reason: string}`
- If denied, reject with budget exhaustion error, log to ledger
- This is a READ — no debit yet (debit happens after response)

#### Step 4: Pre-Log (Ledger Write)
- Write `PROMPT_SENT` entry to ledger with metadata:
  ```
  provenance: {agent_id, agent_class, framework_id, package_id, work_order_id, session_id}
  context_fingerprint: {context_hash, prompt, prompt_pack_id, model_id}
  scope: {tier, domain_tags}
  ```
- This uses the `ledger_entry_metadata.schema.json` we just built
- The ledger entry ID becomes the `parent_event_id` for the response entry
- 📝 Side effect: ledger write

#### Step 5: Context Hash
- Compute SHA256 of the assembled context (the full prompt text)
- Store in `context_fingerprint.context_hash`
- This enables deduplication detection and learning loop analysis

#### Step 6: Provider Dispatch
- Abstract provider interface: `send(model_id, prompt, boundary) → response`
- Provider implementations are pluggable (config-driven, not hardcoded)
- Capture: response text, input token count, output token count, latency_ms, model_id
- Timeout handling: respect `boundary` limits and WO-level `budget.timeout_seconds`
- → External I/O side effect

#### Step 7: Post-Log (Ledger Write)
- Write `PROMPT_RECEIVED` entry to ledger with metadata:
  ```
  provenance: {same as pre-log}
  context_fingerprint: {context_hash, prompt, prompt_pack_id, response, tokens_used: {input, output}, model_id}
  relational: {parent_event_id: <pre-log entry ID>, root_event_id}
  outcome: {status: success/failure/timeout}
  scope: {tier, domain_tags}
  ```
- Captures the FULL round-trip: what was asked, what was answered, how many tokens
- 📝 Side effect: ledger write

#### Step 8: Token Accounting (Debit)
- Tell the Token Budgeter: "Debit N input tokens + M output tokens from WO/session/agent"
- This is the WRITE — budget was checked in step 3, debited here after actual consumption
- Budgeter updates its internal state

#### Step 9: Output Validation
- If `boundary.structured_output` is defined in the prompt contract, validate response against it
- If `output_schema` is defined, validate response structure
- Validation failure → `outcome.status = "failure"`, log to ledger, but still return the response (caller decides what to do)
- ✓/✗ markers in ledger

#### Step 10: Return
- Return response to caller with metadata: tokens_used, latency_ms, ledger_entry_ids, validation_result

### Error Handling

| Condition | Behavior |
|-----------|----------|
| Provider timeout | Log timeout to ledger, return error, no token debit |
| Provider error (500, rate limit) | Log error, return error with provider detail |
| Circuit breaker open | Reject immediately, log, no provider call |
| Validation failure (input) | Reject before send, log rejection |
| Validation failure (output) | Return response anyway, mark outcome as failure |
| Budget exhausted | Reject before send, log rejection |
| AuthZ denied | Reject before send, log rejection |

Every error path logs to the ledger. No silent failures.

### Circuit Breaker

Config-driven parameters (all in a config object, not hardcoded):
- `failure_threshold`: consecutive failures before opening circuit
- `recovery_timeout_ms`: how long circuit stays open before half-open test
- `half_open_max`: requests allowed in half-open state

---

## Component 2: Token Budgeter / Throttler

### Why Separate

The user explicitly called this out as a separate component so it can be tuned independently ("gain"). The router asks the budgeter for permission and reports consumption. The budgeter owns all budget state.

### Budget Hierarchy

```
Session Budget (SES-XXXXXXXX)
  └─ Work Order Budget (WO-YYYYMMDD-NNN)
       └─ Agent Budget (per agent_id within a WO)
```

Each level can have independent limits. Lower levels are constrained by higher levels (an agent can't exceed its WO budget, a WO can't exceed its session budget).

### Core Operations

```python
class TokenBudgeter:
    def check(self, scope: BudgetScope) -> BudgetCheckResult:
        """READ: Can this scope afford N tokens? Returns allowed, remaining, reason."""

    def debit(self, scope: BudgetScope, tokens: TokenUsage) -> DebitResult:
        """WRITE: Record token consumption. Returns new remaining balance."""

    def allocate(self, scope: BudgetScope, budget: BudgetAllocation) -> AllocationResult:
        """WRITE: Set/adjust budget for a scope. Called when WO is created."""

    def get_status(self, scope: BudgetScope) -> BudgetStatus:
        """READ: Current budget state for a scope."""

    def get_session_summary(self, session_id: str) -> SessionSummary:
        """READ: Aggregate token usage across all WOs in a session."""
```

### Budget Scope

```python
@dataclass
class BudgetScope:
    session_id: str           # SES-XXXXXXXX
    work_order_id: str        # WO-YYYYMMDD-NNN
    agent_id: str | None      # Optional agent-level budget
    requested_tokens: int     # How many tokens being requested
    model_id: str             # For cost calculation
```

### What It Tracks

Per scope (session/WO/agent):
- `allocated`: total tokens allocated
- `consumed_input`: input tokens used so far
- `consumed_output`: output tokens used so far
- `remaining`: allocated - consumed (computed)
- `request_count`: number of LLM calls made
- `cost_estimate`: mapped from tokens × model pricing (config-driven rates)
- `last_request_at`: timestamp of most recent request

### Rate Limiting / Throttling

Config-driven parameters (the "gain" knobs):
- `requests_per_minute`: max LLM calls per minute per scope
- `tokens_per_minute`: max tokens per minute per scope
- `burst_allowance`: how much over-limit is tolerated in short bursts
- `cooldown_ms`: backoff period when throttled
- `provider_rpm_limit`: provider-level API rate limits (e.g., Anthropic's rate limits)

### Throttle Response

When throttled, the budgeter returns:
```python
@dataclass
class BudgetCheckResult:
    allowed: bool
    remaining: int
    reason: str              # "OK", "BUDGET_EXHAUSTED", "RATE_LIMITED", "THROTTLED"
    retry_after_ms: int | None  # How long to wait before retrying
    cost_estimate: float | None # Estimated cost for this request
```

### Persistence

Budget state is written to ledger entries (type `BUDGET_UPDATE`) so it's auditable. The budgeter can reconstruct state from ledger on restart (ledger is system truth). In-memory state is a cache of ledger-derived truth.

### Cost Tracking

Config-driven pricing table:
```json
{
  "pricing": {
    "claude-opus-4-6": {"input_per_1k": 0.015, "output_per_1k": 0.075},
    "claude-sonnet-4-5": {"input_per_1k": 0.003, "output_per_1k": 0.015}
  }
}
```

Pricing table is config, not code. New models = config update, not code change.

---

## Schemas Needed

You already have these (built in Phase 2):
- `prompt_contract.schema.json` — defines prompt boundaries, required context, I/O schemas
- `ledger_entry_metadata.schema.json` — defines provenance, context fingerprint, outcome
- `work_order.schema.json` — has budget field, authorization, tool_permissions

New schemas to create:
- `router_config.schema.json` — circuit breaker settings, provider config, retry policy
- `budget_config.schema.json` — rate limits, pricing table, allocation defaults, throttle params

---

## Package Plan

### PKG-PROMPT-ROUTER-001 (Layer 3)
- `HOT/kernel/prompt_router.py` — the router implementation
- `HOT/kernel/provider.py` — abstract provider interface + implementations
- `HOT/schemas/router_config.schema.json` — router configuration schema
- `HOT/FMWK-003_Prompt_Routing/manifest.yaml` — framework manifest (see Handoff #4 for spec)
- `HOT/tests/test_prompt_router.py` — router tests
- Dependencies: `PKG-FRAMEWORK-WIRING-001`, `PKG-PHASE2-SCHEMAS-001`, `PKG-TOKEN-BUDGETER-001`

### PKG-TOKEN-BUDGETER-001 (Layer 3)
- `HOT/kernel/token_budgeter.py` — budgeter implementation
- `HOT/schemas/budget_config.schema.json` — budget configuration schema
- `HOT/tests/test_token_budgeter.py` — budgeter tests
- Dependencies: `PKG-KERNEL-001` (for ledger_client)

### Why Two Packages
- They can be versioned, tested, and upgraded independently
- Token budgeter could be used by components other than the router (e.g., flow runner checking total WO budget before starting)
- Router depends on budgeter, not the other way around

---

## Test Plan (DTT — Tests First)

### Token Budgeter Tests (write these FIRST)
1. `test_allocate_budget` — allocate tokens to a WO, verify status
2. `test_check_within_budget` — check passes when under limit
3. `test_check_over_budget` — check fails when over limit
4. `test_debit_updates_remaining` — debit reduces remaining balance
5. `test_hierarchy_enforcement` — WO can't exceed session budget
6. `test_rate_limiting` — requests exceeding RPM are throttled
7. `test_burst_allowance` — short bursts within allowance pass
8. `test_cost_calculation` — token counts map to correct costs
9. `test_session_summary` — aggregates across WOs correctly
10. `test_budget_from_ledger` — reconstructs state from ledger entries

### Prompt Router Tests (write these FIRST)
1. `test_valid_request_round_trip` — happy path: validate → auth → budget → send → log → return
2. `test_input_validation_rejects_bad_contract` — malformed input rejected
3. `test_authz_denied` — unauthorized caller rejected, logged
4. `test_budget_exhausted` — over-budget rejected before send
5. `test_pre_log_written` — PROMPT_SENT entry in ledger before dispatch
6. `test_post_log_written` — PROMPT_RECEIVED entry in ledger after dispatch
7. `test_token_debit_after_response` — budgeter debited with actual usage
8. `test_output_validation_failure` — bad structured output marked as failure
9. `test_provider_timeout` — timeout logged, no debit
10. `test_circuit_breaker_opens` — consecutive failures open circuit
11. `test_circuit_breaker_recovery` — half-open allows test request
12. `test_context_hash_computed` — SHA256 of prompt text stored
13. `test_ledger_entry_ids_returned` — response includes both ledger entry IDs
14. `test_dev_mode_bypasses_auth` — passthrough auth works in dev mode
15. `test_latency_captured` — wall-clock time recorded in metadata

### End-to-End Test
1. Clean-room extract CP_BOOTSTRAP → install Layers 0-2 (8 packages)
2. Install PKG-PHASE2-SCHEMAS-001 (Layer 3)
3. Install PKG-TOKEN-BUDGETER-001 (Layer 3)
4. Install PKG-PROMPT-ROUTER-001 (Layer 3)
5. All gates pass at every step
6. Run unit tests for both packages
7. Run integration test: create WO with budget → send prompt → verify ledger entries + budget debit

---

## Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Auth patterns | `_staging/PKG-KERNEL-001/HOT/kernel/` (auth.py, authz.py if present) | Reuse existing auth |
| Ledger client | `_staging/PKG-KERNEL-001/HOT/kernel/` or installed `HOT/kernel/ledger_client.py` | Write entries |
| Prompt contract schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/prompt_contract.schema.json` | Validate inputs |
| Ledger metadata schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/ledger_entry_metadata.schema.json` | Structure entries |
| Work order schema | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/schemas/work_order.schema.json` | Budget/auth fields |
| Package manifest pattern | `_staging/PKG-PHASE2-SCHEMAS-001/manifest.json` | How to build manifest |
| stdlib_llm_request.json | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/schemas/stdlib_llm_request.json` | Provider request format |
| stdlib_llm_response.json | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/schemas/stdlib_llm_response.json` | Provider response format |
| Install script | `_staging/PKG-KERNEL-001/HOT/scripts/package_install.py` | For end-to-end testing |
| Genesis bootstrap | `_staging/PKG-GENESIS-000/HOT/scripts/genesis_bootstrap.py` | For clean-room setup |

---

## Design Principles (Non-Negotiable)

1. **Router is dumb.** It does not choose prompts, assemble context, or make decisions. It validates, logs, sends, logs, returns.
2. **Budgeter is separate.** It has its own package, its own tests, its own config. The router calls it but doesn't own it.
3. **Ledger is truth.** Both components write to the ledger. Budget state can be reconstructed from ledger. If it's not in the ledger, it didn't happen.
4. **No hardcoding.** Circuit breaker thresholds, rate limits, pricing, timeouts — all in config objects. New values = config change, not code change.
5. **Fail-closed.** Every error rejects the request and logs to the ledger. No silent failures, no swallowed exceptions.
6. **Dev mode works.** `--dev` bypasses auth and uses mock providers. Tests run without real LLM calls.
