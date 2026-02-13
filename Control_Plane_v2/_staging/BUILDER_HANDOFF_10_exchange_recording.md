# Builder Handoff 10: Exchange Recording Redesign

## 1. Mission

Redesign the prompt router's ledger recording from two half-entries per LLM call (PROMPT_SENT + PROMPT_RECEIVED, neither containing actual content) to **one EXCHANGE record per round-trip that includes the prompt text and response text**. This is the single most important change on the critical path to ADMIN — without it, the system has no memory of its own conversations, and the three learning loops are blind.

**Package:** PKG-PROMPT-ROUTER-001 (edit in place in `_staging/`)

**Why now:** The ledger is the system's memory, not an audit log. The learning loops need prompt + response to evaluate "was the question right, not just the answer" (KERNEL_PHASE_2.md:1218-1222). Currently the router logs 24 fields of metadata envelope with no actual content. This blocks ADMIN (which needs to read conversation history) and all three learning loops.

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** Edit the existing `_staging/PKG-PROMPT-ROUTER-001/` package. Update manifest.json SHA256 hashes. Rebuild the archive.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → install all 13 packages. All gates must pass.
5. **No hardcoding.** Every threshold, timeout, retry count — all config-driven.
6. **No file replacement.** This edits PKG-PROMPT-ROUTER-001's own files — that's fine. Do NOT overwrite files belonging to other packages.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — NEVER `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`).
8. **Results file.** When finished, write `_staging/RESULTS_HANDOFF_10.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.
9. **Full regression test.** Run ALL staged package tests (not just yours) and report results.
10. **Baseline snapshot.** Results file must include package count, file_ownership rows, total tests, all gate results.
11. **LedgerEntry is Layer 0 — do NOT modify it.** The `LedgerEntry` dataclass in `ledger_client.py` belongs to PKG-KERNEL-001. All exchange data goes in the `metadata` dict. Do not add fields to LedgerEntry.
12. **Existing test patterns must keep passing.** Callers that check `response.outcome`, `response.content`, `response.input_tokens`, `response.output_tokens` must work identically. The external interface of `route()` does not change behavior — only what gets written to the ledger and returned in entry ID fields.
13. **Do NOT touch provider.py, anthropic_provider.py, token_budgeter.py, or ledger_client.py.** This handoff modifies prompt_router.py and its tests ONLY.

---

## 3. Architecture / Design

### The Problem

Currently the router writes **two ledger entries per LLM call**:

```
PROMPT_SENT (before send):
  24 metadata fields — agent_id, agent_class, framework_id, package_id,
  work_order_id, session_id, tier, prompt_pack_id, contract_id, model_id,
  provider_id, context_hash, max_tokens, temperature, domain_tags
  Missing: prompt text

PROMPT_RECEIVED (after response):
  11 metadata fields — parent_event_id, agent_id, framework_id, session_id,
  context_hash, model_id, provider_id, input_tokens, output_tokens,
  finish_reason, request_id, cached
  Missing: response text
```

**Problems:**
- Neither entry contains the actual content (prompt text or response text)
- Two entries per exchange means learning loops must join them to reconstruct one experience
- The two entries aren't explicitly linked (parent_event_id exists but correlation is fragile)
- 5 fields are duplicated across both entries (agent_id, framework_id, session_id, context_hash, model_id, provider_id)
- 5 fields belong on the contract definition, not repeated per exchange (prompt_pack_id, model_id, provider_id, max_tokens, temperature)
- 4 fields belong on the work order (package_id, agent_class, authorization, budget)
- 2 fields are always empty (domain_tags: [], prompts_used: [])
- 3 fields are tautological or debug text (decision: "DISPATCHED", reason: "Routing to...", submission_id duplicates contract_id)

### The Solution

**One EXCHANGE record per completed round-trip**, containing the actual prompt and response:

```
EXCHANGE (after round-trip completes):
  event_type: "EXCHANGE"
  submission_id: <contract_id>
  decision: "SUCCESS" | "ERROR" | "TIMEOUT"
  reason: <outcome description>

  metadata:
    # Identity — how you FIND this memory (6 fields)
    agent_id         — who asked
    session_id       — which conversation
    work_order_id    — which task
    tier             — which memory layer
    contract_id      — which prompt contract (links to all boundary/template details)
    framework_id     — which framework (denormalized for Loop 2 cross-WO queries)

    # Content — THE MEMORY (3 fields)
    prompt           — what was asked (THE MOST IMPORTANT FIELD)
    response         — what came back (THE SECOND MOST IMPORTANT FIELD)
    outcome          — "success" | "error" | "timeout"

    # Cost — budget enforcement (2 fields)
    input_tokens     — actual tokens consumed by prompt
    output_tokens    — actual tokens consumed by response

    # Context — reproducibility (1 field)
    context_hash     — SHA256 of prompt text

    # Correlation (1 field)
    dispatch_entry_id — links to pre-send marker for crash recovery

    # Provider detail (2 fields)
    model_id         — which model produced the response (needed for learning)
    finish_reason    — stop | length | tool_use

    # Timing (1 field)
    latency_ms       — round-trip time
```

**Total: 16 metadata fields** (down from 26 across two entries), and the two that matter most (prompt + response) are now included.

**Plus one lightweight DISPATCH marker** written before sending:

```
DISPATCH (before send — crash recovery only, NOT memory):
  event_type: "DISPATCH"
  submission_id: <contract_id>
  decision: "DISPATCHED"
  reason: "Dispatching to <provider>/<model>"

  metadata:
    contract_id      — which contract
    agent_id         — who
    session_id       — which session
```

**3 metadata fields.** Just enough to detect orphaned dispatches (sent but never completed).

**Rejection entries** (auth fail, budget fail, validation fail) stay as `PROMPT_REJECTED` but simplified:

```
PROMPT_REJECTED (no exchange happened):
  event_type: "PROMPT_REJECTED"
  submission_id: <contract_id>
  decision: "REJECTED"
  reason: "<error_code>: <error_message>"

  metadata:
    agent_id         — who
    session_id       — which session
    contract_id      — which contract
    error_code       — what went wrong
    error_message    — details
```

**5 metadata fields.** No prompt text (it never went anywhere). No response (there isn't one).

### What Moved Where

| Field | Was On | Now On | Why |
|-------|--------|--------|-----|
| prompt_pack_id | PROMPT_SENT | Contract definition | Same for every invocation of this contract |
| max_tokens | PROMPT_SENT | Contract boundary | Ceiling doesn't change per call |
| temperature | PROMPT_SENT | Contract boundary | Same every time |
| provider_id | PROMPT_SENT + RECEIVED | Contract boundary | Determined by contract (router doesn't pick) |
| agent_class | PROMPT_SENT | Work order | WO specifies which class executes |
| package_id | PROMPT_SENT | Framework definition | Derivable from framework_id |
| domain_tags | PROMPT_SENT | Removed | Always empty. Add to WO when populated. |
| prompts_used | LedgerEntry top-level | Removed | Always empty. Dead field. |
| decision: "DISPATCHED" | PROMPT_SENT | Removed from EXCHANGE | Tautological for completed exchanges |
| reason: "Routing to..." | PROMPT_SENT | Simplified | Debug text, not memory |
| request_id | PROMPT_RECEIVED | Removed | Provider-internal detail |
| cached | PROMPT_RECEIVED | Removed | Provider-internal detail |
| parent_event_id | PROMPT_RECEIVED | dispatch_entry_id | Explicit link, same purpose |

### Data Flow

```
route(request) called
    │
    ├─ Step 1: Validate input        → PROMPT_REJECTED if bad
    ├─ Step 2: Check auth            → PROMPT_REJECTED if denied
    ├─ Step 3: Check budget          → PROMPT_REJECTED if exhausted
    │
    ├─ Step 4: Compute context_hash
    ├─ Step 5: Write DISPATCH marker  (lightweight, crash recovery)
    │
    ├─ Step 6: Check circuit breaker → PROMPT_REJECTED if open
    ├─ Step 7: Send to provider
    │     ├─ Success → Step 8
    │     └─ Error   → Write EXCHANGE with outcome="error"/"timeout", return
    │
    ├─ Step 8: Write EXCHANGE record  (prompt + response + cost + identity)
    ├─ Step 9: Debit budget
    ├─ Step 10: Validate output
    └─ Step 11: Return PromptResponse
```

---

## 4. Implementation Steps

### Step 1: Update PromptResponse dataclass

In `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/prompt_router.py`:

Change `sent_entry_id` and `received_entry_id` fields:

```python
@dataclass
class PromptResponse:
    """Response from a route() call."""

    content: str
    outcome: RouteOutcome
    input_tokens: int
    output_tokens: int
    model_id: str
    provider_id: str
    latency_ms: float
    timestamp: str
    exchange_entry_id: str        # The EXCHANGE or PROMPT_REJECTED ledger entry ID
    dispatch_entry_id: str = ""   # The pre-send DISPATCH marker ID (empty for rejections)
    output_valid: Optional[bool] = None
    output_validation_errors: list[str] = field(default_factory=list)
    context_hash: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    cost_incurred: float = 0.0
    budget_remaining: Optional[int] = None
```

### Step 2: Replace `_pre_log` with `_write_dispatch_marker`

```python
def _write_dispatch_marker(
    self, request: PromptRequest, model_id: str, provider_id: str,
) -> str:
    """Write lightweight DISPATCH marker to ledger. Returns entry ID.

    Crash recovery only — if the system dies mid-send, this marker
    lets us detect orphaned dispatches. NOT memory.
    """
    from ledger_client import LedgerEntry

    entry = LedgerEntry(
        event_type="DISPATCH",
        submission_id=request.contract_id,
        decision="DISPATCHED",
        reason=f"Dispatching to {provider_id}/{model_id}",
        metadata={
            "contract_id": request.contract_id,
            "agent_id": request.agent_id,
            "session_id": request.session_id,
        },
    )
    return self._ledger.write(entry)
```

### Step 3: Replace `_post_log` with `_write_exchange`

```python
def _write_exchange(
    self, request: PromptRequest, dispatch_entry_id: str,
    provider_response: Any, context_hash: str,
    model_id: str, latency_ms: float,
) -> str:
    """Write EXCHANGE record to ledger. Returns entry ID.

    This IS the memory. One record per completed LLM round-trip.
    Contains prompt text, response text, and normalized identity.
    """
    from ledger_client import LedgerEntry

    entry = LedgerEntry(
        event_type="EXCHANGE",
        submission_id=request.contract_id,
        decision="SUCCESS",
        reason="Exchange completed",
        metadata={
            # Identity
            "agent_id": request.agent_id,
            "session_id": request.session_id,
            "work_order_id": request.work_order_id,
            "tier": request.tier,
            "contract_id": request.contract_id,
            "framework_id": request.framework_id,
            # Content
            "prompt": request.prompt,
            "response": provider_response.content,
            "outcome": "success",
            # Cost
            "input_tokens": provider_response.input_tokens,
            "output_tokens": provider_response.output_tokens,
            # Context
            "context_hash": context_hash,
            # Correlation
            "dispatch_entry_id": dispatch_entry_id,
            # Provider detail
            "model_id": model_id,
            "finish_reason": provider_response.finish_reason,
            # Timing
            "latency_ms": latency_ms,
        },
    )
    return self._ledger.write(entry)
```

### Step 4: Replace `_post_log_error` with `_write_exchange_error`

```python
def _write_exchange_error(
    self, request: PromptRequest, dispatch_entry_id: str,
    error_code: str, error_message: str, context_hash: str,
    model_id: str, latency_ms: float,
) -> str:
    """Write EXCHANGE record for a failed round-trip.

    Includes the prompt (we tried to send it) but response is the error.
    """
    from ledger_client import LedgerEntry

    outcome = "timeout" if error_code == "TIMEOUT" else "error"

    entry = LedgerEntry(
        event_type="EXCHANGE",
        submission_id=request.contract_id,
        decision="ERROR",
        reason=f"{error_code}: {error_message}",
        metadata={
            # Identity
            "agent_id": request.agent_id,
            "session_id": request.session_id,
            "work_order_id": request.work_order_id,
            "tier": request.tier,
            "contract_id": request.contract_id,
            "framework_id": request.framework_id,
            # Content — prompt included (we tried), response is the error
            "prompt": request.prompt,
            "response": "",
            "outcome": outcome,
            "error_code": error_code,
            "error_message": error_message,
            # Context
            "context_hash": context_hash,
            # Correlation
            "dispatch_entry_id": dispatch_entry_id,
            # Provider detail
            "model_id": model_id,
            # Timing
            "latency_ms": latency_ms,
        },
    )
    return self._ledger.write(entry)
```

### Step 5: Simplify `_reject` and `_log_rejection`

```python
def _reject(
    self, request: PromptRequest, error_code: str, error_message: str,
    start_time: float, timestamp: str, model_id: str, provider_id: str,
) -> PromptResponse:
    """Create a rejection response and log to ledger.

    No exchange happened. Lightweight entry — identity + error only.
    """
    from ledger_client import LedgerEntry

    entry = LedgerEntry(
        event_type="PROMPT_REJECTED",
        submission_id=request.contract_id,
        decision="REJECTED",
        reason=f"{error_code}: {error_message}",
        metadata={
            "agent_id": request.agent_id,
            "session_id": request.session_id,
            "contract_id": request.contract_id,
            "error_code": error_code,
            "error_message": error_message,
        },
    )
    entry_id = self._ledger.write(entry)

    return PromptResponse(
        content="",
        outcome=RouteOutcome.REJECTED,
        input_tokens=0,
        output_tokens=0,
        model_id=model_id,
        provider_id=provider_id,
        latency_ms=self._elapsed_ms(start_time),
        timestamp=timestamp,
        exchange_entry_id=entry_id,
        dispatch_entry_id="",
        error_code=error_code,
        error_message=error_message,
    )
```

### Step 6: Update `route()` pipeline

The pipeline structure stays the same (validate → auth → budget → dispatch → send → record → debit → validate output → return). Changes:

1. Replace `sent_entry_id = self._pre_log(...)` with `dispatch_id = self._write_dispatch_marker(...)`
2. Replace `received_entry_id = self._post_log(...)` with `exchange_id = self._write_exchange(...)`
3. Replace `self._post_log_error(...)` with `exchange_id = self._write_exchange_error(...)`
4. Replace `self._log_rejection(...)` calls in the circuit-breaker-open path with the simplified `_reject` pattern
5. Update all `PromptResponse(...)` constructors to use `exchange_entry_id` and `dispatch_entry_id`
6. Pass `latency_ms=self._elapsed_ms(start_time)` to exchange writers (they need it for the record)

### Step 7: Update tests

Rewrite `test_prompt_router.py` to validate the new model. See Test Plan (Section 6) for full list.

### Step 8: Rebuild package archive and CP_BOOTSTRAP

**8a. Recompute SHA256 hashes for edited files:**

```bash
STAGING="Control_Plane_v2/_staging"
sha256sum "$STAGING/PKG-PROMPT-ROUTER-001/HOT/kernel/prompt_router.py"
sha256sum "$STAGING/PKG-PROMPT-ROUTER-001/HOT/tests/test_prompt_router.py"
```

Update the corresponding SHA256 values in `_staging/PKG-PROMPT-ROUTER-001/manifest.json` under the `assets` array.

**8b. Rebuild PKG-PROMPT-ROUTER-001.tar.gz:**

```bash
cd "$STAGING"
tar czf PKG-PROMPT-ROUTER-001.tar.gz -C PKG-PROMPT-ROUTER-001 $(ls PKG-PROMPT-ROUTER-001)
# CRITICAL: Do NOT use `tar czf ... -C dir .` — the ./ prefix breaks load_manifest_from_archive
```

Verify no `./` prefix:
```bash
tar tzf PKG-PROMPT-ROUTER-001.tar.gz | head -5
# Should show: manifest.json, HOT/kernel/..., HOT/tests/... — NO ./ prefix
```

**8c. Rebuild CP_BOOTSTRAP.tar.gz:**

CP_BOOTSTRAP is assembled from a staging directory with this exact structure:

```
bootstrap_tmp/
├── README.md
├── INSTALL.md
├── install.sh
└── packages/
    ├── PKG-GENESIS-000.tar.gz
    ├── PKG-KERNEL-001.tar.gz
    ├── PKG-VOCABULARY-001.tar.gz
    ├── PKG-REG-001.tar.gz
    ├── PKG-GOVERNANCE-UPGRADE-001.tar.gz
    ├── PKG-FRAMEWORK-WIRING-001.tar.gz
    ├── PKG-SPEC-CONFORMANCE-001.tar.gz
    ├── PKG-LAYOUT-001.tar.gz
    ├── PKG-PHASE2-SCHEMAS-001.tar.gz
    ├── PKG-TOKEN-BUDGETER-001.tar.gz
    ├── PKG-PROMPT-ROUTER-001.tar.gz    ← YOUR REBUILT ARCHIVE
    ├── PKG-ANTHROPIC-PROVIDER-001.tar.gz
    └── PKG-LAYOUT-002.tar.gz
```

Commands:

```bash
cd "$STAGING"

# Create assembly directory
BTMP=$(mktemp -d)
mkdir -p "$BTMP/packages"

# Copy docs (unchanged)
cp README.md INSTALL.md install.sh "$BTMP/"

# Copy all 13 package archives — 12 unchanged + 1 rebuilt
for pkg in PKG-GENESIS-000 PKG-KERNEL-001 PKG-VOCABULARY-001 PKG-REG-001 \
           PKG-GOVERNANCE-UPGRADE-001 PKG-FRAMEWORK-WIRING-001 \
           PKG-SPEC-CONFORMANCE-001 PKG-LAYOUT-001 \
           PKG-PHASE2-SCHEMAS-001 PKG-TOKEN-BUDGETER-001 \
           PKG-PROMPT-ROUTER-001 PKG-ANTHROPIC-PROVIDER-001 \
           PKG-LAYOUT-002; do
    cp "$pkg.tar.gz" "$BTMP/packages/"
done

# Build CP_BOOTSTRAP.tar.gz — NO ./ prefix
tar czf CP_BOOTSTRAP.tar.gz -C "$BTMP" $(ls "$BTMP")

# Verify structure
tar tzf CP_BOOTSTRAP.tar.gz | sort
# Expected: 16 entries — 3 docs + packages/ dir with 13 .tar.gz files

# Clean up
rm -rf "$BTMP"
```

**8d. Verify the rebuilt CP_BOOTSTRAP installs cleanly** (this is the end-to-end verification in Section 8).

---

## 5. Package Plan

**Package:** PKG-PROMPT-ROUTER-001 (EDIT — not a new package)

- **package_id:** PKG-PROMPT-ROUTER-001
- **layer:** 3
- **spec_id:** SPEC-GATE-001
- **framework_id:** FMWK-000
- **plane_id:** hot
- **dependencies:** [PKG-KERNEL-001, PKG-TOKEN-BUDGETER-001]

**Assets modified:**

| Asset Path | Classification | Action |
|-----------|---------------|--------|
| HOT/kernel/prompt_router.py | kernel | EDIT |
| HOT/tests/test_prompt_router.py | test | EDIT |

**Assets unchanged:**

| Asset Path | Classification |
|-----------|---------------|
| HOT/kernel/provider.py | kernel |

Manifest SHA256 hashes must be recomputed for the two edited files.

---

## 6. Test Plan

**Minimum: 25 tests** (medium package, 1 source file edited)

### Exchange Recording Tests (NEW — 10 tests)

| # | Test Name | Validates | Expected |
|---|-----------|-----------|----------|
| 1 | `test_exchange_contains_prompt_text` | EXCHANGE metadata has "prompt" key with actual prompt string | metadata["prompt"] == request.prompt |
| 2 | `test_exchange_contains_response_text` | EXCHANGE metadata has "response" key with provider response | metadata["response"] == "Mock response" |
| 3 | `test_exchange_contains_outcome` | EXCHANGE metadata has "outcome" = "success" | metadata["outcome"] == "success" |
| 4 | `test_single_exchange_per_roundtrip` | One EXCHANGE entry per successful route(), not two | len(ledger.read_by_event_type("EXCHANGE")) == 1 |
| 5 | `test_no_prompt_sent_or_received_entries` | Old event types (PROMPT_SENT, PROMPT_RECEIVED) are gone | len(read_by_event_type("PROMPT_SENT")) == 0, same for PROMPT_RECEIVED |
| 6 | `test_exchange_has_normalized_identity` | agent_id, session_id, work_order_id, tier, contract_id, framework_id present | All 6 keys in metadata |
| 7 | `test_exchange_has_cost_fields` | input_tokens and output_tokens on EXCHANGE | metadata["input_tokens"] == 100, metadata["output_tokens"] == 50 |
| 8 | `test_exchange_has_model_id` | model_id on EXCHANGE for learning loops | metadata["model_id"] == "mock-model-1" |
| 9 | `test_exchange_no_redundant_fields` | agent_class, package_id, prompt_pack_id, max_tokens, temperature, domain_tags NOT on EXCHANGE | None of these keys in metadata |
| 10 | `test_exchange_has_context_hash` | context_hash present, 64-char hex | metadata["context_hash"] matches ^[a-f0-9]{64}$ |

### Dispatch Marker Tests (NEW — 4 tests)

| # | Test Name | Validates | Expected |
|---|-----------|-----------|----------|
| 11 | `test_dispatch_marker_written_before_exchange` | DISPATCH entry exists, timestamp <= EXCHANGE timestamp | DISPATCH entry present, chronologically before EXCHANGE |
| 12 | `test_dispatch_marker_is_lightweight` | DISPATCH metadata has exactly 3 keys | metadata keys == {contract_id, agent_id, session_id} |
| 13 | `test_exchange_links_to_dispatch` | EXCHANGE metadata["dispatch_entry_id"] == DISPATCH entry ID | Explicit link between the two |
| 14 | `test_dispatch_without_exchange_on_error` | Provider error → DISPATCH exists but EXCHANGE has outcome="error" | Both entries present, EXCHANGE has error outcome |

### Error Path Tests (UPDATED — 5 tests)

| # | Test Name | Validates | Expected |
|---|-----------|-----------|----------|
| 15 | `test_error_exchange_contains_prompt` | Provider error → EXCHANGE still has prompt text (we tried to send it) | metadata["prompt"] == request.prompt |
| 16 | `test_error_exchange_has_error_fields` | Provider error → EXCHANGE has error_code and error_message | Both keys present |
| 17 | `test_timeout_exchange_outcome` | ProviderError(TIMEOUT) → EXCHANGE outcome="timeout" | metadata["outcome"] == "timeout" |
| 18 | `test_server_error_exchange_outcome` | ProviderError(SERVER_ERROR) → EXCHANGE outcome="error" | metadata["outcome"] == "error" |
| 19 | `test_error_exchange_has_latency` | Error path still records latency_ms | metadata["latency_ms"] >= 0 |

### Rejection Tests (UPDATED — 3 tests)

| # | Test Name | Validates | Expected |
|---|-----------|-----------|----------|
| 20 | `test_rejection_is_lightweight` | Auth/budget rejection → PROMPT_REJECTED with 5 fields | metadata keys == {agent_id, session_id, contract_id, error_code, error_message} |
| 21 | `test_rejection_no_prompt_text` | Rejection entries do NOT contain prompt text | "prompt" not in metadata |
| 22 | `test_rejection_no_dispatch_marker` | No DISPATCH written for rejections (never got that far) | dispatch_entry_id == "" on response |

### Backward Compatibility Tests (PRESERVED — 6 tests)

| # | Test Name | Validates | Expected |
|---|-----------|-----------|----------|
| 23 | `test_valid_request_round_trip` | Happy path → SUCCESS, content, tokens | response.outcome == SUCCESS, content == "Mock response" |
| 24 | `test_circuit_breaker_opens` | 3 failures → 4th rejected | Same behavior as before |
| 25 | `test_circuit_breaker_recovery` | OPEN → HALF_OPEN → success → CLOSED | Same behavior as before |
| 26 | `test_budget_exhausted` | Over-budget → REJECTED, provider never called | Same behavior as before |
| 27 | `test_output_validation_failure` | Schema mismatch → output_valid=False, response still returned | Same behavior as before |
| 28 | `test_dev_mode_bypasses_auth` | dev_mode=True, no token → SUCCESS | Same behavior as before |

### Response Dataclass Tests (NEW — 2 tests)

| # | Test Name | Validates | Expected |
|---|-----------|-----------|----------|
| 29 | `test_response_has_exchange_entry_id` | PromptResponse.exchange_entry_id is LED-xxx | Matches ^LED-[a-f0-9]{8}$ |
| 30 | `test_response_has_dispatch_entry_id` | PromptResponse.dispatch_entry_id is LED-xxx for success | Matches ^LED-[a-f0-9]{8}$, empty string for rejections |

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Current prompt_router.py | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/prompt_router.py` | The file you're editing |
| Current test_prompt_router.py | `_staging/PKG-PROMPT-ROUTER-001/HOT/tests/test_prompt_router.py` | The tests you're rewriting |
| provider.py | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/provider.py` | ProviderResponse fields — DO NOT MODIFY |
| ledger_client.py | `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` | LedgerEntry dataclass — DO NOT MODIFY |
| token_budgeter.py | `_staging/PKG-TOKEN-BUDGETER-001/HOT/kernel/token_budgeter.py` | Budget integration — DO NOT MODIFY |
| KERNEL_PHASE_2.md | `Control_Plane_v2/KERNEL_PHASE_2.md` lines 1211-1255 | WHY prompt + response matter — the design rationale |
| Installed copy (reference) | `CP_2.1/HOT/kernel/prompt_router.py` | Deployed version — read for context, don't edit |

---

## 8. End-to-End Verification

```bash
# 1. Set up clean room
TMPDIR=$(mktemp -d)
export CONTROL_PLANE_ROOT="$TMPDIR"
STAGING="/Users/raymondbruni/Brain_Garden/playground/Control_Plane_v2/_staging"

# 2. Extract bootstrap
tar xzf "$STAGING/CP_BOOTSTRAP.tar.gz" -C "$TMPDIR"

# 3. Install Layer 0
tar xzf "$TMPDIR/packages/PKG-GENESIS-000.tar.gz" -C "$TMPDIR"
python3 "$TMPDIR/HOT/scripts/genesis_bootstrap.py" \
    --seed "$TMPDIR/HOT/config/seed_registry.json" \
    --archive "$TMPDIR/packages/PKG-KERNEL-001.tar.gz" \
    --id PKG-KERNEL-001 --force

# 4. Install Layers 1-3 (11 packages)
for pkg in PKG-VOCABULARY-001 PKG-REG-001 \
           PKG-GOVERNANCE-UPGRADE-001 PKG-FRAMEWORK-WIRING-001 \
           PKG-SPEC-CONFORMANCE-001 PKG-LAYOUT-001 \
           PKG-PHASE2-SCHEMAS-001 PKG-TOKEN-BUDGETER-001 \
           PKG-PROMPT-ROUTER-001 PKG-ANTHROPIC-PROVIDER-001 \
           PKG-LAYOUT-002; do
    python3 "$TMPDIR/HOT/scripts/package_install.py" \
        --archive "$TMPDIR/packages/$pkg.tar.gz" \
        --id "$pkg" --root "$TMPDIR" --dev
done

# 5. Verify all gates pass
CONTROL_PLANE_ROOT="$TMPDIR" python3 "$TMPDIR/HOT/scripts/gate_check.py" --root "$TMPDIR" --all
# Expected: 8/8 gates PASS

# 6. Verify 13 receipts
ls "$TMPDIR/HOT/installed"/PKG-*/receipt.json | wc -l
# Expected: 13

# 7. Run router tests
CONTROL_PLANE_ROOT="$TMPDIR" \
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT" \
python3 -m pytest "$STAGING/PKG-PROMPT-ROUTER-001/HOT/tests/test_prompt_router.py" -v
# Expected: 30/30 pass

# 8. Run ALL staged tests
CONTROL_PLANE_ROOT="$TMPDIR" \
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT" \
python3 -m pytest "$STAGING/" -v --ignore="$STAGING/CP_BOOTSTRAP.tar.gz"
# Expected: 266+ tests pass (235 prior + 30 new router, minus 15 old router = ~281)

# 9. Functional smoke test — verify exchange record contains prompt + response
CONTROL_PLANE_ROOT="$TMPDIR" \
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT" \
python3 -c "
from ledger_client import LedgerClient
from prompt_router import PromptRouter, PromptRequest, RouterConfig
from provider import MockProvider

ledger = LedgerClient(ledger_path=__import__('pathlib').Path('$TMPDIR/HOT/ledger/test_smoke.jsonl'))
router = PromptRouter(ledger_client=ledger, config=RouterConfig(), dev_mode=True)
router.register_provider('mock', MockProvider(default_response='The answer is 42'))

resp = router.route(PromptRequest(
    prompt='What is the meaning of life?',
    prompt_pack_id='PRM-TEST-001', contract_id='PRC-TEST-001',
    agent_id='AGENT-SMOKE', agent_class='ADMIN', framework_id='FMWK-000',
    package_id='PKG-TEST', work_order_id='WO-20260211-001',
    session_id='SES-SMOKE001', tier='hot',
))

exchanges = ledger.read_by_event_type('EXCHANGE')
assert len(exchanges) == 1
ex = exchanges[0]
assert ex.metadata['prompt'] == 'What is the meaning of life?'
assert ex.metadata['response'] == 'The answer is 42'
assert ex.metadata['outcome'] == 'success'
assert ex.metadata['agent_id'] == 'AGENT-SMOKE'
assert 'package_id' not in ex.metadata  # Normalized out
assert 'agent_class' not in ex.metadata  # Normalized out
print('SMOKE TEST PASSED: Exchange record contains prompt + response')
"
# Expected: SMOKE TEST PASSED

# 10. Clean up
rm -rf "$TMPDIR"
```

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `prompt_router.py` | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/` | EDIT: Replace 2-entry model with EXCHANGE + DISPATCH |
| `test_prompt_router.py` | `_staging/PKG-PROMPT-ROUTER-001/HOT/tests/` | EDIT: 30 tests for new model |
| `manifest.json` | `_staging/PKG-PROMPT-ROUTER-001/` | EDIT: Update SHA256 hashes |
| `PKG-PROMPT-ROUTER-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD with updated router archive |
| `RESULTS_HANDOFF_10.md` | `_staging/` | CREATE: Results file |

---

## 10. Design Principles

1. **The ledger is memory, not an audit log.** Every field on the EXCHANGE record exists because a learning loop needs it. If no loop reads it, it doesn't belong.
2. **One experience = one record.** An LLM round-trip is one memory. Not two halved events that need joining. The learning loops must never need to join records to reconstruct what happened.
3. **Content over metadata.** The prompt and response are the most important fields. Everything else is retrieval index or cost tracking. We normalize the index (fewer, better-chosen fields) and add the content (prompt + response).
4. **Normalize by write frequency.** Contract details (model, temperature, max_tokens) are written once on the contract. Work order details (agent_class, package_id) are written once on the WO. Only per-exchange data goes on the exchange record. Don't repeat what can be looked up.
5. **Crash recovery is infrastructure, not memory.** The DISPATCH marker exists for one purpose: detecting orphaned sends. It's not a memory the learning loops read. Keep it minimal (3 fields).
6. **Rejections are not exchanges.** If we never sent anything, there's no exchange to record. PROMPT_REJECTED is lightweight (5 fields) — just enough to answer "why was this blocked?"

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**YOUR IDENTITY — print this FIRST before doing anything else:**
> **Agent: HANDOFF-10** — Exchange recording redesign: one EXCHANGE record per LLM call with prompt + response text

**Read this file FIRST — it is your complete specification:**
`Control_Plane_v2/_staging/BUILDER_HANDOFF_10_exchange_recording.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree or CP_2.1/.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` — NEVER `tar czf ... -C dir .`
4. Do NOT modify ledger_client.py, provider.py, anthropic_provider.py, or token_budgeter.py.
5. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_HANDOFF_10.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. How many ledger entries does the current router write per successful LLM call? How many will the new model write?
2. What are the two most important fields being ADDED to the exchange record, and why do the learning loops need them?
3. Name 5 fields that are being REMOVED from the per-exchange ledger entries and where each one lives now.
4. What is the DISPATCH marker for, and how many metadata fields does it have?
5. What event_type does a completed round-trip use? What about a rejection (auth/budget fail)?
6. Does LedgerEntry need to be modified? If not, where does exchange data go?
7. What file(s) are you editing, and what file(s) must you NOT touch?
8. After rebuilding, how many total packages should install and how many gates should pass?
9. How many tests does the test plan specify? What's the split between new exchange tests, updated error/rejection tests, and backward compatibility tests?
10. What does the smoke test in Section 8 verify that unit tests cannot?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers (for reviewer)

1. Currently 2 (PROMPT_SENT + PROMPT_RECEIVED). New model: 2 (DISPATCH + EXCHANGE), but DISPATCH is a lightweight crash-recovery marker, not memory. The EXCHANGE is the single memory record.
2. `prompt` (the actual prompt text) and `response` (the actual response text). Learning loops need these to evaluate "was the question right, not just the answer" — without them, loops can see success/failure but not WHY.
3. Five of: agent_class (work order), package_id (framework), prompt_pack_id (contract), max_tokens (contract boundary), temperature (contract boundary), provider_id (contract boundary), domain_tags (removed/empty), request_id (removed), cached (removed), decision "DISPATCHED" (tautological).
4. Crash recovery — detecting orphaned sends (dispatched but never completed). 3 metadata fields: contract_id, agent_id, session_id.
5. Completed round-trip: "EXCHANGE". Rejection: "PROMPT_REJECTED".
6. No — LedgerEntry belongs to PKG-KERNEL-001 (Layer 0). Exchange data goes in the `metadata` dict.
7. Editing: prompt_router.py, test_prompt_router.py, manifest.json. NOT touching: ledger_client.py, provider.py, anthropic_provider.py, token_budgeter.py.
8. 13 packages, 8/8 gates.
9. 30 tests total. 10 new exchange recording tests, 4 dispatch marker tests, 5 updated error path tests, 3 updated rejection tests, 6 backward compatibility tests, 2 response dataclass tests.
10. The smoke test verifies that a real (mocked) end-to-end route() call produces an EXCHANGE entry with actual prompt and response text in a fresh ledger — proving the full pipeline works, not just individual methods. It also verifies that normalized-out fields (package_id, agent_class) are absent.
