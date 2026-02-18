# BUILDER_HANDOFF_29: HO3 Signal-Based Memory

## 1. Mission

Build the HO3 memory plane as an addressable data store with synchronous READ/LOG APIs, a bistable consolidation gate, and domain-tag provider routing. HO3 does NOT execute. HO3 does NOT participate in real-time interaction. HO3 has exactly two operations: READ and WRITE.

Three sequential waves:
- **29A**: PKG-HO3-MEMORY-001 — the store (new package)
- **29B**: PKG-HO2-SUPERVISOR-001 modification — signal wiring
- **29C**: PKG-HO1-EXECUTOR-001 + PKG-HO2-SUPERVISOR-001 + PKG-LLM-GATEWAY-001 modifications — consolidation + provider routing

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`.** Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every component gets tests before implementation.
3. **Package everything.** New code ships as packages in `_staging/PKG-<NAME>/` with manifest.json, SHA256 hashes, proper dependencies.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → `install.sh` → ALL gates must pass.
5. **No hardcoding.** Every threshold, timeout, window — all config-driven. No magic constants.
6. **No file replacement.** Packages must NEVER overwrite another package's files.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .`
8. **Results file.** Write `_staging/handoffs/RESULTS_HANDOFF_29<A|B|C>.md` per wave.
9. **Full regression test.** Run ALL staged package tests. Report results. Current baseline: **608 passed, 0 failed, 8/8 gates, 21 packages.**
10. **Baseline snapshot.** Results file must include baseline snapshot.
11. **Built-in tools.** Use `hashing.py:compute_sha256()` and `packages.py:pack()`. NEVER raw hashlib or shell tar.
12. **Hash format.** All SHA256 in manifest.json: `sha256:<64hex>` (71 chars). Bare hex fails G0A.

---

## 3. Runtime Contract (NON-NEGOTIABLE)

This contract supersedes all prior HO3 bookend designs including the deleted HANDOFF-29 (ho3_bookends).

1. HO3 is always addressable, never always-executing.
2. No daemon/background watcher/polling/interrupt/per-turn HO3 execution.
3. HO2 performs synchronous HO3.READ lookup (structured data only).
4. HO2 increments numeric signals inline during normal turn flow.
5. After turn completes, HO2 runs gate check.
6. Only if gate=true, invoke one bounded, explicit post-turn consolidation task.
7. Consolidation is out-of-band to user response and must not block delivery.
8. Overlay writes are append-only and must reference source event IDs.
9. Source ledgers remain immutable.
10. Multi-provider routing is execution-layer behavior (HO1/Gateway), not cognitive policy logic.

---

## 4. Architecture / Design

### Cognitive Hierarchy (Time-Based)

```
HO1 = T1 (in-the-moment execution)   — WORKING
HO2 = T2 (episodic planning)          — WORKING
HOT/HO3 = T3 (long-term memory)       — THIS HANDOFF
```

HO3 is a **data plane** — a memory store with a semantic interface. It is NOT a cognitive process. It does NOT make LLM calls. It does NOT participate in the Kitchener dispatch loop as an actor. Steps 1 and 5 of the canonical loop are reinterpreted as:

- **Step 1 (Ideation)**: HO2 reads overlays/biases from HO3m → injects as context into WO scoping
- **Step 5 (Synthesis)**: HO2 accumulates signals → checks gate → maybe triggers consolidation

### Data Flow

```
User message
  │
  ▼
HO2.handle_turn()
  │
  ├─ Step 2a: Classify intent (HO1 via existing WO)
  │
  ├─ Step 2b: Attention retrieval (existing)
  │        + HO3.READ active_biases → inject into context    ← 29B
  │
  ├─ Step 2c: Assemble context
  │
  ├─ Step 3: Dispatch synthesize WO to HO1 → Gateway → LLM
  │
  ├─ Step 4: Quality gate
  │
  ├─ Return response to user                                  ← user gets response HERE
  │
  ├─ Post-turn: Extract signals from turn                     ← 29B
  │     └─ HO3.LOG(signal_id, session_id, event_id)
  │
  ├─ Post-turn: Gate check                                    ← 29B
  │     └─ HO3.check_gate(signal_id)
  │
  └─ If gate crossed:                                         ← 29C
        └─ HO2 dispatches consolidation WO to HO1
              └─ HO1 → Gateway → LLM (with domain_tags routing)
              └─ Result → HO3.LOG overlay
```

### 29A: The Store (PKG-HO3-MEMORY-001)

#### Data Model

**Signal Event** (one line in `signals.jsonl`):
```json
{
  "event_id": "EVT-abc12345",
  "signal_id": "tool_usage:gate_check",
  "session_id": "SES-xyz",
  "timestamp": "2026-02-17T10:30:00+00:00",
  "metadata": {}
}
```

Signals are raw, numeric event records. Each line is an immutable event. Accumulated state (count, session_ids, last_seen) is computed from the events by READ.

**Signal Accumulation** (computed by READ, not stored):
```python
@dataclass
class SignalAccumulator:
    signal_id: str
    count: int                  # total events for this signal_id
    last_seen: str              # ISO timestamp of most recent event
    session_ids: list[str]      # unique session IDs that contributed
    event_ids: list[str]        # all event IDs (for source references)
    decay: float                # time-based decay factor (0.0 to 1.0)
```

**Overlay Entry** (one line in `overlays.jsonl`):
```json
{
  "overlay_id": "OVL-def67890",
  "signal_id": "tool_usage:gate_check",
  "salience_weight": 0.8,
  "decay_modifier": 0.95,
  "source_event_ids": ["EVT-abc12345", "EVT-abc12346", "..."],
  "content": {"bias": "User frequently checks gate status", "category": "tool_preference"},
  "created_at": "2026-02-17T11:00:00+00:00",
  "window_start": "2026-02-10T00:00:00+00:00",
  "window_end": "2026-02-17T11:00:00+00:00"
}
```

Overlays reference source_event_ids (immutable provenance chain back to signals.jsonl).

#### Storage Paths

At runtime (under plane_root):
- `HOT/memory/signals.jsonl` — append-only signal events
- `HOT/memory/overlays.jsonl` — append-only overlay entries

These are governed by LedgerClient (append-only, hash-chained).

#### API

```python
class HO3Memory:
    """HO3 memory plane — addressable data store.

    NOT a cognitive process. Two operations: READ and LOG.
    No LLM calls. No background execution.
    """

    def __init__(self, plane_root: Path, config: HO3MemoryConfig): ...

    # === HO3.READ (synchronous structured lookup) ===
    def read_signals(self, signal_id: str = None, min_count: int = 0) -> list[SignalAccumulator]: ...
    def read_overlays(self, signal_id: str = None, active_only: bool = True) -> list[dict]: ...
    def read_active_biases(self) -> list[dict]: ...

    # === HO3.LOG (synchronous signal/event append) ===
    def log_signal(self, signal_id: str, session_id: str, event_id: str, metadata: dict = None) -> str: ...
    def log_overlay(self, overlay: dict) -> str: ...

    # === Bistable Gate ===
    def check_gate(self, signal_id: str) -> GateResult: ...
```

#### Bistable Gate

Pure function. No LLM calls. No side effects.

```
crossed = (
    accumulator.count >= config.gate_count_threshold
    AND len(accumulator.session_ids) >= config.gate_session_threshold
    AND not_consolidated(signal_id, window)
)
```

`not_consolidated(signal_id, window)`: Check if an overlay entry exists for this signal_id with `window_end` within the last `config.gate_window_hours`. If yes, the signal was already consolidated in this window → gate stays closed.

#### Config

```python
@dataclass
class HO3MemoryConfig:
    memory_dir: Path                    # HOT/memory/ under plane_root
    gate_count_threshold: int = 5       # count >= N
    gate_session_threshold: int = 3     # sessions >= M
    gate_window_hours: int = 168        # 7 days — window for not_consolidated check
    decay_half_life_hours: float = 336  # 14 days — time-based signal decay
    enabled: bool = False               # MVP default: OFF (opt-in)
```

#### Adversarial Analysis: Signal Storage as Append-Only Events

**Hurdles**: Reading accumulated state requires scanning the entire signals.jsonl. For MVP this is fine (hundreds of events). At scale, an index is needed. But the existing LedgerClient already has submission-based indexing — signals can use the same pattern.

**Not Enough**: If we skip event_ids in signal events, overlays can't reference their sources. Every overlay written without source_event_ids is permanently unauditable. The event-level granularity must be in the data model from day one.

**Too Much**: We could add semantic labels, confidence scores, cross-signal relationships. All premature — no consumer exists yet. Raw counts and timestamps are sufficient for the bistable gate.

**Synthesis**: Append-only events with event_ids. Accumulated state computed on read. No semantic labels until consolidation (which is 29C's concern, not 29A's).

---

### 29B: HO2 Signal Wiring (PKG-HO2-SUPERVISOR-001 modification)

#### Changes to HO2Supervisor

1. **Constructor**: Accept optional `ho3_memory: HO3Memory = None` parameter. Store as `self._ho3_memory`.

2. **Step 2b (Attention)**: After existing attention retrieval (line 170-171), if `self._ho3_memory` and `self._ho3_memory.config.enabled`:
   ```python
   biases = self._ho3_memory.read_active_biases()
   ```
   Add biases to `assembled_context` at Step 2c.

3. **Post-turn signal accumulation**: After `self._session_mgr.add_turn()` (line 280), before constructing `TurnResult`:
   - Extract deterministic signals from the turn:
     - `intent:<classification_type>` from classify WO result (`classification` variable, line 167)
   - Call `self._ho3_memory.log_signal()` for each
   - **NOTE**: `tool:<tool_id>` signals are NOT extracted in 29B. HO1 does not expose individual tool_ids in the returned WO dict today (cost dict has `tool_calls` count only, not names). Tool signal extraction is deferred to 29C, which modifies HO1 to add `cost["tool_ids_used"]`.

4. **Post-turn gate check**: After signal accumulation:
   - For each signal logged this turn, call `self._ho3_memory.check_gate(signal_id)`
   - Collect signal_ids where `gate_result.crossed == True`

5. **TurnResult**: Add `consolidation_candidates: list[str] = field(default_factory=list)` — signal_ids that crossed the gate this turn.

#### Signal Extraction (Deterministic Only)

No LLM calls. No semantic analysis. Just structured data from existing WO results:

**29B extracts intent signals only:**

| Source | Signal ID Pattern | Example |
|--------|------------------|---------|
| Classify WO `output_result` (line 167: `classification` variable) | `intent:<value>` | `intent:tool_query` |

**29C adds tool signals** (after HO1 exposes `cost["tool_ids_used"]`):

| Source | Signal ID Pattern | Example |
|--------|------------------|---------|
| Synthesize WO `cost["tool_ids_used"]` | `tool:<tool_id>` | `tool:gate_check` |

The intent classification is available directly in the `classify_result` returned by `_dispatch_wo()`. Tool IDs require HO1 to populate `cost["tool_ids_used"]` (a 29C change at `ho1_executor.py` line 210).

#### Config Changes to HO2Config

Add these fields (all with defaults preserving existing behavior):

```python
    # HO3 memory integration (all optional, all defaulted to off)
    ho3_enabled: bool = False
    ho3_memory_dir: Optional[Path] = None
    ho3_gate_count_threshold: int = 5
    ho3_gate_session_threshold: int = 3
    ho3_gate_window_hours: int = 168
```

When `ho3_enabled` is False, no HO3 code paths execute. Existing behavior is preserved.

---

### 29C: Consolidation + Provider Routing

#### Consolidation Dispatch

When `TurnResult.consolidation_candidates` is non-empty, the caller (Shell or SH-V2) invokes consolidation. HO2 gains a new method:

```python
def run_consolidation(self, signal_ids: list[str]) -> list[dict]:
    """Dispatch bounded consolidation WOs for gate-crossing signals.

    Called AFTER the user response is delivered. Out-of-band.
    Single-shot per signal_id. Idempotent within the gate window.

    Returns list of completed consolidation WO dicts.
    """
```

For each signal_id:
1. Re-check gate (idempotency — another turn may have consolidated it)
2. Read signal accumulator from HO3.READ
3. Create consolidation WO with:
   - `wo_type: "consolidate"`
   - `prompt_contract_id: "PRC-CONSOLIDATE-001"`
   - `domain_tags: ["consolidation"]` (routes to local model if configured)
   - `input_context: {signal_id, count, session_ids, event_ids, recent_events}`
4. Dispatch to HO1 via `self._dispatch_wo()`
5. On success: call `self._ho3_memory.log_overlay()` with result + source_event_ids

#### Prompt Pack: PRM-CONSOLIDATE-001.txt

New file in `PKG-HO1-EXECUTOR-001/HO1/prompt_packs/PRM-CONSOLIDATE-001.txt`:

```
You are analyzing patterns in user interaction signals.

Signal: {{signal_id}}
Observation count: {{count}}
Across sessions: {{session_count}}
Recent events:
{{recent_events}}

Based on these observations, produce a concise bias statement that describes the user's behavioral pattern. This will be used to weight future attention retrieval.

Respond with valid JSON matching this schema:
{
  "bias": "one sentence describing the pattern",
  "category": "one of: tool_preference, topic_interest, interaction_style, workflow_pattern",
  "salience_weight": 0.0 to 1.0,
  "decay_modifier": 0.0 to 1.0
}
```

#### Contract: PRC-CONSOLIDATE-001.json

New file in `PKG-HO1-EXECUTOR-001/HO1/contracts/PRC-CONSOLIDATE-001.json`:

```json
{
  "contract_id": "PRC-CONSOLIDATE-001",
  "prompt_pack_id": "PRM-CONSOLIDATE-001",
  "boundary": {
    "max_tokens": 512,
    "temperature": 0.0
  },
  "input_schema": {
    "type": "object",
    "required": ["signal_id", "count", "session_count", "recent_events"]
  },
  "output_schema": {
    "type": "object",
    "required": ["bias", "category", "salience_weight", "decay_modifier"]
  }
}
```

#### Provider Routing (Domain Tags)

Current Gateway provider resolution (`llm_gateway.py:222`):
```python
provider_id = request.provider_id or self._config.default_provider
```

New resolution order (matches user's scope lock):
```python
provider_id = (
    request.provider_id                               # 1. explicit request
    or self._resolve_domain_tags(request.domain_tags)  # 2. domain_tags routing map
    or self._config.default_provider                   # 3. default
)
```

The routing map lives in the Gateway's config (e.g., `router_config.json`):
```json
{
  "domain_tag_routes": {
    "consolidation": {"provider_id": "local", "model_id": "llama-3-8b"},
    "classification": {"provider_id": "local", "model_id": "llama-3-8b"}
  }
}
```

`_resolve_domain_tags()` returns the first matching `provider_id` from the map, or `None` if no tags match.

#### HO1 Domain Tags Passthrough

In `ho1_executor.py:_build_prompt_request()` (lines 404-422), add `domain_tags` from WO constraints:

```python
domain_tags = wo.get("constraints", {}).get("domain_tags", [])
```

Pass to `PromptRequest(... domain_tags=domain_tags ...)`.

Currently missing — the PromptRequest dataclass already has `domain_tags: list[str]` (line 58 of llm_gateway.py) but HO1 never populates it.

#### Adversarial Analysis: Domain Tag Routing

**Hurdles**: Gateway currently ignores domain_tags. Adding routing logic means a new code path that could break existing behavior if the map isn't empty.

**Not Enough**: Without domain_tags, all LLM calls go to the default provider (Anthropic remote). Consolidation WOs are low-complexity pattern recognition — routing them to a local model saves cost and latency.

**Too Much**: We could build a full provider registry with priority queues, fallback chains, load balancing. Overkill — a simple lookup map with 3-step precedence is enough for MVP.

**Synthesis**: Add `_resolve_domain_tags()` to Gateway, populate domain_tags from HO1. Empty map = existing behavior unchanged. Non-empty map = tag-based routing active.

---

## 5. Implementation Steps

### Wave 1: HANDOFF-29A (PKG-HO3-MEMORY-001)

**Dependency**: PKG-KERNEL-001 (LedgerClient), PKG-LAYOUT-002 (directory structure)

1. Create package directory: `_staging/PKG-HO3-MEMORY-001/`
2. Create `HOT/kernel/ho3_memory.py`:
   - `HO3MemoryConfig` dataclass
   - `SignalAccumulator` dataclass
   - `GateResult` dataclass
   - `HO3Memory` class with READ/LOG/gate methods
   - Use `LedgerClient` for append-only writes to signals.jsonl and overlays.jsonl
   - Accumulated state computed on read (scan + group by signal_id)
   - Decay computed as `exp(-lambda * hours_since_last_seen)` where `lambda = ln(2) / decay_half_life_hours`
3. Write tests FIRST: `HOT/tests/test_ho3_memory.py` — 18 tests (see Test Plan)
4. Create `manifest.json` with `sha256:` hashes, dependencies on PKG-KERNEL-001 and PKG-LAYOUT-002
5. Build archive with `pack()`, compute hash with `compute_sha256()`
6. Rebuild CP_BOOTSTRAP.tar.gz (22 packages now)
7. Clean-room install, full regression, 8/8 gates

### Wave 2: HANDOFF-29B (PKG-HO2-SUPERVISOR-001 modification)

**Dependency**: 29A must be complete (PKG-HO3-MEMORY-001 installed)

1. Add `ho3_enabled`, `ho3_memory_dir`, gate threshold fields to `HO2Config` (defaults preserve existing behavior)
2. Add optional `ho3_memory` parameter to `HO2Supervisor.__init__()` — stored as `self._ho3_memory`
3. Write tests FIRST: add 10 tests to `test_ho2_supervisor.py` (see Test Plan)
4. In `handle_turn()`:
   - After attention retrieval (line 170): if enabled, call `read_active_biases()`, add to assembled context
   - After `add_turn()` (line 280): extract signals, call `log_signal()`, call `check_gate()`
5. Add `consolidation_candidates: list[str]` to `TurnResult` dataclass (default empty list)
6. Update manifest.json hashes
7. Rebuild archive, rebuild CP_BOOTSTRAP, clean-room verify

### Wave 3: HANDOFF-29C (Cross-package: HO1 + HO2 + Gateway)

**Dependency**: 29B must be complete

1. **PKG-HO1-EXECUTOR-001**:
   - Create `HO1/prompt_packs/PRM-CONSOLIDATE-001.txt`
   - Create `HO1/contracts/PRC-CONSOLIDATE-001.json`
   - In `_build_prompt_request()`: pass `domain_tags` from `wo.get("constraints", {}).get("domain_tags", [])` to PromptRequest
   - **In tool loop (line 210)**: After `cost["tool_calls"] += 1`, add `cost.setdefault("tool_ids_used", []).append(tu["tool_id"])`. This exposes individual tool_ids in the returned WO dict so HO2 can extract `tool:<tool_id>` signals.

2. **PKG-HO2-SUPERVISOR-001**:
   - Add `run_consolidation(signal_ids: list[str]) -> list[dict]` method
   - Config field: `consolidation_budget: int = 4000` in HO2Config
   - Config field: `consolidation_contract_id: str = "PRC-CONSOLIDATE-001"` in HO2Config
   - **Add tool signal extraction**: In post-turn signal accumulation (after 29B's intent extraction), read `tool_ids_used` from each WO in the chain: `for wo in wo_chain: for tid in wo.get("cost", {}).get("tool_ids_used", []): log_signal(f"tool:{tid}", ...)`

3. **PKG-LLM-GATEWAY-001**:
   - Add `domain_tag_routes: dict` to `RouterConfig` (default empty dict)
   - Add `_resolve_domain_tags(tags: list[str]) -> Optional[str]` method to `LLMGateway`
   - Modify `route()` line 222: use 3-step precedence (explicit → tag → default)
   - Add domain_tag_routes to `from_config_file()` parser

4. Write tests FIRST: 10 tests across the three packages (see Test Plan)
5. Update all three manifest.json files
6. Rebuild all three archives + CP_BOOTSTRAP
7. Clean-room install, full regression, 8/8 gates

---

## 6. Package Plan

### PKG-HO3-MEMORY-001 (new — 29A)

| Field | Value |
|-------|-------|
| Package ID | PKG-HO3-MEMORY-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

**Assets:**

| Path | Classification |
|------|---------------|
| `HOT/kernel/ho3_memory.py` | source |
| `HOT/tests/test_ho3_memory.py` | test |

**Dependencies:** PKG-KERNEL-001, PKG-LAYOUT-002

### PKG-HO2-SUPERVISOR-001 (modified — 29B)

Existing package. Modified assets:

| Path | Classification | Action |
|------|---------------|--------|
| `HO2/kernel/ho2_supervisor.py` | source | MODIFY |
| `HO2/tests/test_ho2_supervisor.py` | test | MODIFY |

**Dependencies: UNCHANGED** — remains `["PKG-KERNEL-001", "PKG-WORK-ORDER-001"]`. PKG-HO3-MEMORY-001 is an optional runtime dependency imported with a try/except fallback to `HO3Memory = None`. Not declared in manifest.

### PKG-HO1-EXECUTOR-001 (modified — 29C)

Modified/added assets:

| Path | Classification | Action |
|------|---------------|--------|
| `HO1/kernel/ho1_executor.py` | source | MODIFY (domain_tags passthrough + tool_ids_used in cost dict) |
| `HO1/prompt_packs/PRM-CONSOLIDATE-001.txt` | prompt_pack | CREATE |
| `HO1/contracts/PRC-CONSOLIDATE-001.json` | contract | CREATE |
| `HO1/tests/test_ho1_executor.py` | test | MODIFY |

### PKG-LLM-GATEWAY-001 (modified — 29C)

Modified assets:

| Path | Classification | Action |
|------|---------------|--------|
| `HOT/kernel/llm_gateway.py` | source | MODIFY |
| `HOT/tests/test_llm_gateway.py` | test | MODIFY |

---

## 7. Test Plan

### 29A: PKG-HO3-MEMORY-001 (18 tests)

| Test | Description | Expected |
|------|-------------|----------|
| `test_log_signal_creates_entry` | Call log_signal → entry appended to signals.jsonl | Event with signal_id, session_id, event_id, timestamp |
| `test_log_signal_returns_event_id` | log_signal returns the generated event_id | String starting with "EVT-" |
| `test_read_signals_accumulates_count` | Log 3 events for same signal_id → read_signals shows count=3 | `accumulator.count == 3` |
| `test_read_signals_tracks_sessions` | Log from 2 sessions → session_ids has both | `len(accumulator.session_ids) == 2` |
| `test_read_signals_tracks_event_ids` | Log 3 events → event_ids has all 3 | `len(accumulator.event_ids) == 3` |
| `test_read_signals_last_seen` | Log at time T → last_seen == T | ISO timestamp matches |
| `test_read_signals_by_id` | Read specific signal_id → returns only that signal | Single accumulator returned |
| `test_read_signals_min_count_filter` | 2 signals, counts 2 and 5, min_count=3 → only count-5 returned | 1 result |
| `test_read_signals_empty` | No events logged → empty list | `[]` |
| `test_log_overlay_creates_entry` | Call log_overlay → entry appended to overlays.jsonl | Entry with overlay_id, signal_id, content |
| `test_overlay_has_source_event_ids` | Overlay entry MUST contain source_event_ids (NON-EMPTY) | **Mandatory test #4**: `len(entry["source_event_ids"]) > 0` |
| `test_read_overlays_all` | Log 2 overlays → read_overlays returns both | 2 entries |
| `test_read_overlays_by_signal_id` | 2 overlays, different signal_ids → filter returns 1 | 1 entry |
| `test_read_active_biases` | Overlays with salience > 0 and not decayed → returned as active biases | Non-empty list |
| `test_gate_false_below_count` | count=2, threshold=5 → gate not crossed | **Mandatory test #1 (partial)**: `gate_result.crossed == False` |
| `test_gate_false_below_sessions` | count=10, sessions=1, threshold_sessions=3 → gate not crossed | `gate_result.crossed == False` |
| `test_gate_true_thresholds_met` | count=5, sessions=3, not consolidated → gate crossed | `gate_result.crossed == True` |
| `test_gate_false_already_consolidated` | Thresholds met BUT overlay exists within window → gate not crossed | **Mandatory test #3 (partial)**: `gate_result.crossed == False, gate_result.already_consolidated == True` |
| `test_source_ledger_immutability` | Log 3 signals, read, log 1 more → first 3 events unchanged | Events 1-3 have same content after 4th append |

### 29B: PKG-HO2-SUPERVISOR-001 additions (10 tests)

| Test | Description | Expected |
|------|-------------|----------|
| `test_ho3_disabled_skips_all` | ho3_memory=None → no signal logging, no gate check, no biases | Existing behavior unchanged |
| `test_ho3_enabled_flag_false_skips` | ho3_memory provided but config.ho3_enabled=False → skipped | Same as disabled |
| `test_signal_from_classification` | Classify returns intent="tool_query" → log_signal("intent:tool_query") called | Signal event in signals.jsonl |
| `test_intent_signal_missing_classification` | Classify returns empty/no intent field → no signal logged, no error | Graceful no-op |
| `test_signal_logging_does_not_affect_response` | Response text identical with and without ho3_enabled (same LLM mock) | `result.response` unchanged |
| `test_ho3_read_injects_biases` | Active biases exist → added to synthesize WO input_context | `"ho3_biases"` key in input_context |
| `test_gate_check_runs_post_turn` | Signals logged → check_gate called for each | check_gate invoked |
| `test_gate_false_empty_candidates` | Gate not crossed → consolidation_candidates is empty list | **Mandatory test #1**: `result.consolidation_candidates == []` |
| `test_gate_true_populates_candidates` | Gate crossed for signal_id X → X in consolidation_candidates | `"X" in result.consolidation_candidates` |
| `test_turn_result_has_field` | TurnResult has consolidation_candidates field | `hasattr(result, "consolidation_candidates")` |

### 29C: Cross-package (12 tests)

| Test | Description | Expected |
|------|-------------|----------|
| `test_consolidation_dispatches_wo` | run_consolidation(["sig1"]) → dispatches WO with wo_type="consolidate" | WO dispatched to HO1 |
| `test_consolidation_exactly_one` | Gate crossed → exactly one consolidation WO per signal_id | **Mandatory test #2**: 1 WO dispatched |
| `test_consolidation_idempotent` | run_consolidation twice for same signal+window → second is no-op | **Mandatory test #3**: gate re-check returns False on second call |
| `test_consolidation_overlay_has_source_ids` | Consolidation writes overlay → source_event_ids populated | **Mandatory test #4**: `len(overlay["source_event_ids"]) > 0` |
| `test_domain_tag_routes_local` | PromptRequest with domain_tags=["consolidation"], map routes to "local" → provider_id="local" | **Mandatory test #5**: `response.provider_id == "local"` |
| `test_no_tag_routes_default` | PromptRequest with no domain_tags → default provider used | **Mandatory test #6**: `response.provider_id == config.default_provider` |
| `test_explicit_provider_overrides_tags` | request.provider_id="anthropic" + domain_tags=["consolidation"] → "anthropic" wins | Precedence rule 1 |
| `test_ho1_passes_domain_tags` | WO with constraints.domain_tags=["x"] → PromptRequest.domain_tags==["x"] | domain_tags populated |
| `test_consolidation_prompt_pack_loads` | PRM-CONSOLIDATE-001.txt exists and renders with template variables | Template renders |
| `test_consolidation_contract_loads` | PRC-CONSOLIDATE-001.json loads via contract_loader | Contract with correct schema |
| `test_ho1_exposes_tool_ids_used` | HO1 tool loop populates cost["tool_ids_used"] with actual tool_id strings | `cost["tool_ids_used"] == ["gate_check"]` |
| `test_tool_signal_from_wo_chain` | WO chain has cost.tool_ids_used=["gate_check"] → log_signal("tool:gate_check") called | Signal event in signals.jsonl |

**Total new tests: 40** (18 in 29A, 10 in 29B, 12 in 29C)

---

## 8. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| LedgerClient (append-only store) | `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` | Use for signals.jsonl and overlays.jsonl — same append-only pattern |
| HO2 Supervisor (current) | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py` | Lines 133-311: handle_turn flow. Lines 50-69: HO2Config. Lines 72-79: TurnResult. |
| HO1 Executor (current) | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` | Lines 367-422: _build_prompt_request (add domain_tags). Lines 330-346: _render_template. |
| LLM Gateway (current) | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py` | Lines 214-222: route() provider resolution. Lines 36-59: PromptRequest (domain_tags at line 58). Lines 97-104: RouterConfig. |
| HO2 tests (patterns) | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py` | Test patterns, mock setup, dual-context detection |
| HO1 tests (patterns) | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py` | Test patterns for executor |
| Gateway tests (patterns) | `_staging/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py` | Test patterns for gateway |
| Layout config | `_staging/PKG-LAYOUT-002/HOT/config/layout.json` | Tier directory structure |
| Hashing tool | `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py` | compute_sha256() for manifest hashes |
| Packages tool | `_staging/PKG-KERNEL-001/HOT/kernel/packages.py` | pack() for archive builds |
| Existing prompt packs | `_staging/PKG-HO1-EXECUTOR-001/HO1/prompt_packs/` | Template patterns for PRM-CONSOLIDATE-001 |
| Existing contracts | `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/` | Contract format for PRC-CONSOLIDATE-001 |

---

## 9. End-to-End Verification

```bash
# 1. Clean-room install
TMPDIR=$(mktemp -d)
cd Control_Plane_v2/_staging
tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
cd "$TMPDIR" && bash install.sh --root "$TMPDIR" --dev

# 2. Run all tests
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 -m pytest "$TMPDIR/HOT/tests" "$TMPDIR/HO1/tests" "$TMPDIR/HO2/tests" -q

# Expected: 648+ passed (608 baseline + 40 new), 0 failed

# 3. Run gates
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 "$TMPDIR/HOT/scripts/gate_check.py" --all --enforce --root "$TMPDIR"

# Expected: 8/8 PASS

# 4. Verify HO3 memory module loads
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT" \
  python3 -c "from ho3_memory import HO3Memory, HO3MemoryConfig; print('HO3Memory loaded')"

# 5. Verify provider routing config
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT" \
  python3 -c "from llm_gateway import LLMGateway, RouterConfig; r=RouterConfig(); print(f'domain_tag_routes: {r.domain_tag_routes}')"
```

---

## 10. Files Summary

### 29A (PKG-HO3-MEMORY-001 — new)

| File | Location | Action |
|------|----------|--------|
| `ho3_memory.py` | `_staging/PKG-HO3-MEMORY-001/HOT/kernel/` | CREATE |
| `test_ho3_memory.py` | `_staging/PKG-HO3-MEMORY-001/HOT/tests/` | CREATE |
| `manifest.json` | `_staging/PKG-HO3-MEMORY-001/` | CREATE |
| `PKG-HO3-MEMORY-001.tar.gz` | `_staging/` | CREATE |

### 29B (PKG-HO2-SUPERVISOR-001 — modified)

| File | Location | Action |
|------|----------|--------|
| `ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | MODIFY |
| `test_ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO2-SUPERVISOR-001/` | MODIFY (hashes) |
| `PKG-HO2-SUPERVISOR-001.tar.gz` | `_staging/` | REBUILD |

### 29C (cross-package)

| File | Location | Action |
|------|----------|--------|
| `ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/` | MODIFY (domain_tags passthrough + tool_ids_used at line 210) |
| `PRM-CONSOLIDATE-001.txt` | `_staging/PKG-HO1-EXECUTOR-001/HO1/prompt_packs/` | CREATE |
| `PRC-CONSOLIDATE-001.json` | `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/` | CREATE |
| `test_ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO1-EXECUTOR-001/` | MODIFY (hashes) |
| `PKG-HO1-EXECUTOR-001.tar.gz` | `_staging/` | REBUILD |
| `llm_gateway.py` | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/` | MODIFY |
| `test_llm_gateway.py` | `_staging/PKG-LLM-GATEWAY-001/HOT/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-LLM-GATEWAY-001/` | MODIFY (hashes) |
| `PKG-LLM-GATEWAY-001.tar.gz` | `_staging/` | REBUILD |
| `ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | MODIFY (add run_consolidation + tool signal extraction) |
| `test_ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO2-SUPERVISOR-001/` | MODIFY (hashes) |
| `PKG-HO2-SUPERVISOR-001.tar.gz` | `_staging/` | REBUILD |

### All waves

| File | Location | Action |
|------|----------|--------|
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD (after each wave) |
| `RESULTS_HANDOFF_29A.md` | `_staging/handoffs/` | CREATE |
| `RESULTS_HANDOFF_29B.md` | `_staging/handoffs/` | CREATE |
| `RESULTS_HANDOFF_29C.md` | `_staging/handoffs/` | CREATE |

---

## 11. Design Principles

1. **HO3 is a data plane, not a cognitive process.** Two operations: READ and LOG. No LLM calls from HO3. No background execution. Always addressable, never always-executing.
2. **Append-only, immutable sources.** Signal events and overlay entries are append-only. Accumulated state is computed on read. Source ledgers are never mutated.
3. **Provenance is non-negotiable.** Every overlay entry references source_event_ids back to the signals.jsonl events that triggered it. Unauditable overlays are forbidden.
4. **Config over constants.** Gate thresholds, decay rates, windows, budgets — all come from config. No magic numbers.
5. **Default OFF.** `ho3_enabled: bool = False`. The entire HO3 integration is opt-in. Existing behavior is preserved when disabled.
6. **Consolidation is bounded and explicit.** One shot per gate crossing. Idempotent within the window. Out-of-band to user response. No daemons.
7. **3-step provider precedence.** Explicit provider_id > domain_tag route > default. Empty routing map = existing behavior unchanged.

---

## Agent Prompts

### Agent 29A: PKG-HO3-MEMORY-001

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-29A** — Build HO3 memory store (new package PKG-HO3-MEMORY-001)

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_29_ho3_signal_memory.md`
Focus on: Section 4 (29A subsection), Wave 1 in Section 5, 29A in Sections 6/7/9/10.

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` — NEVER `tar czf ... -C dir .`
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir → run install.sh → ALL gates must pass. This is NOT optional.
6. Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail, and whether you introduced new failures.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_29A.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md. MUST include: Clean-Room Verification section, Baseline Snapshot section, Full Regression section.
8. CP_BOOTSTRAP rebuild: Rebuild CP_BOOTSTRAP.tar.gz (now 22 packages) and report the new SHA256.
9. Built-in tools: Use `hashing.py:compute_sha256()` for all SHA256 hashes and `packages.py:pack()` for all archives. NEVER use raw hashlib or shell tar.
10. This package is a data store with NO LLM calls and NO background execution. If your code imports anything from the LLM pipeline, you've gone wrong.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What are the two operations HO3 supports? What does HO3 explicitly NOT do?
2. What are the two JSONL files this package creates, and where do they live at runtime?
3. How is signal accumulation (count, session_ids, last_seen) computed — stored or derived on read?
4. What three conditions must ALL be true for the bistable gate to return crossed=True?
5. What does not_consolidated(signal_id, window) check? What file does it read?
6. Why must every overlay entry contain source_event_ids? What happens if it's empty?
7. What is the decay formula? Where does decay_half_life_hours come from?
8. What dependencies does this package declare in manifest.json? Why those two specifically?
9. How many tests are you writing? Name three that test the bistable gate.
10. After your package is installed, what new directory appears under HOT/ at runtime?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

**Expected answers:**
1. READ and LOG. HO3 does NOT make LLM calls, does NOT execute, does NOT participate in real-time interaction, does NOT run background processes.
2. `HOT/memory/signals.jsonl` and `HOT/memory/overlays.jsonl` (under plane_root).
3. Derived on read. Signal events are raw immutable appends. read_signals() scans, groups by signal_id, computes count/session_ids/last_seen/event_ids.
4. `count >= gate_count_threshold` AND `len(session_ids) >= gate_session_threshold` AND `not_consolidated(signal_id, window)`.
5. Checks overlays.jsonl for an overlay entry with matching signal_id whose window_end is within the last gate_window_hours. If found → already consolidated → gate stays closed.
6. Provenance chain. Every overlay must trace back to the signal events that caused it. Empty source_event_ids = unauditable = forbidden.
7. `decay = exp(-ln(2) / decay_half_life_hours * hours_since_last_seen)`. decay_half_life_hours comes from HO3MemoryConfig.
8. PKG-KERNEL-001 (LedgerClient for append-only JSONL) and PKG-LAYOUT-002 (directory structure for HOT/).
9. 18 tests. Gate tests: test_gate_false_below_count, test_gate_true_thresholds_met, test_gate_false_already_consolidated.
10. `HOT/memory/` (created by HO3Memory.__init__ when first signal is logged).

---

### Agent 29B: PKG-HO2-SUPERVISOR-001 modification

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-29B** — Wire HO3 signals into HO2 supervisor

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_29_ho3_signal_memory.md`
Focus on: Section 4 (29B subsection), Wave 2 in Section 5, 29B in Sections 6/7/10.

**Prerequisite:** HANDOFF-29A must be VALIDATED first. PKG-HO3-MEMORY-001 must be in CP_BOOTSTRAP.

**Mandatory rules:**
1-9: Same as 29A.
10. All changes are additive and gated by ho3_enabled=False. When disabled, NO existing behavior changes. If your change alters any existing test's behavior without ho3_memory set, you've introduced a regression.

**Before writing ANY code, answer these 10 questions:**

1. What new fields are you adding to HO2Config? What are their defaults?
2. What new parameter does HO2Supervisor.__init__ accept? What happens when it's None?
3. At what line in handle_turn does HO3.READ inject biases? What key do they go under in assembled_context?
4. What deterministic signals does 29B extract from a turn? (Hint: only ONE pattern in 29B. Tool signals are 29C.) Give the signal_id pattern and its source variable.
5. At what line in handle_turn does signal accumulation happen — before or after the user gets their response?
6. What new field does TurnResult gain? What is its default value?
7. When ho3_enabled is False, how many new code paths execute? (Answer: zero)
8. How many new tests are you adding? Name the one that validates gate false → no consolidation.
9. What import do you need at the top of ho2_supervisor.py? From what package?
10. Does this modification require rebuilding CP_BOOTSTRAP? Why?

**STOP AFTER ANSWERING.**
```

**Expected answers:**
1. ho3_enabled: bool = False, ho3_memory_dir: Optional[Path] = None, ho3_gate_count_threshold: int = 5, ho3_gate_session_threshold: int = 3, ho3_gate_window_hours: int = 168.
2. `ho3_memory: HO3Memory = None`. When None, all HO3 code paths are skipped (guarded by `if self._ho3_memory and self._config.ho3_enabled`).
3. After line 171 (priority = self._attention.priority_probe()). Key: `"ho3_biases"` in assembled_context.
4. `intent:<classification_type>` from the classify WO result only. Tool signals (`tool:<tool_id>`) are deferred to 29C because HO1 does not yet expose tool_ids_used.
5. After line 280 (self._session_mgr.add_turn) — after the response text is computed but before TurnResult is constructed and returned. The response is already determined; signals are a post-processing step.
6. `consolidation_candidates: list[str]` with default `field(default_factory=list)`.
7. Zero. All HO3 code is guarded by `if self._ho3_memory and self._config.ho3_enabled`.
8. 10 tests. `test_gate_false_empty_candidates`.
9. `from ho3_memory import HO3Memory` (or try/except with `kernel.ho3_memory`). From PKG-HO3-MEMORY-001.
10. Yes — modified package archive must be rebuilt and included in bootstrap for clean-room verification.

---

### Agent 29C: Consolidation + Provider Routing

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-29C** — Consolidation dispatch + domain-tag provider routing

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_29_ho3_signal_memory.md`
Focus on: Section 4 (29C subsection), Wave 3 in Section 5, 29C in Sections 6/7/10.

**Prerequisite:** HANDOFF-29B must be VALIDATED first.

**Mandatory rules:**
1-9: Same as 29A.
10. This wave touches 3 packages. Rebuild all 3 archives + CP_BOOTSTRAP. Any gate failure is a blocker.

**Before writing ANY code, answer these 10 questions:**

1. What is the 3-step provider resolution precedence? Write the code logic.
2. What method does HO2 gain for consolidation? What does it return?
3. Why does run_consolidation re-check the gate before dispatching? (One word: idempotency)
4. What wo_type does the consolidation WO use? What contract_id?
5. What domain_tags does the consolidation WO carry? How does the Gateway use them?
6. Where in ho1_executor.py does domain_tags need to be passed? What line range?
7. Where in llm_gateway.py does the provider resolution change? What line?
8. After consolidation, what does HO2 call to write the overlay? What field must be non-empty?
9. How many tests are you adding? Which test proves domain-tag routing to a local model?
10. If the domain_tag_routes map is empty, what happens? (Answer: existing behavior, unchanged)

**STOP AFTER ANSWERING.**
```

**Expected answers:**
1. `provider_id = request.provider_id or self._resolve_domain_tags(request.domain_tags) or self._config.default_provider`
2. `run_consolidation(signal_ids: list[str]) -> list[dict]`. Returns list of completed consolidation WO dicts.
3. Idempotency — another turn may have consolidated the signal between gate crossing and consolidation invocation.
4. `wo_type: "consolidate"`, `contract_id: "PRC-CONSOLIDATE-001"`.
5. `domain_tags: ["consolidation"]`. Gateway calls `_resolve_domain_tags(["consolidation"])`, looks up "consolidation" in `domain_tag_routes` config, returns the mapped provider_id.
6. Lines 404-422 in `_build_prompt_request()` — add `domain_tags=wo.get("constraints", {}).get("domain_tags", [])` to the PromptRequest constructor.
7. Line 222 in `route()` — change `provider_id = request.provider_id or self._config.default_provider` to the 3-step precedence.
8. `self._ho3_memory.log_overlay(overlay_dict)`. `source_event_ids` must be non-empty.
9. 12 tests. `test_domain_tag_routes_local`.
10. `_resolve_domain_tags` returns None, falls through to `self._config.default_provider`. Zero behavioral change.

---

## Appendix: Dependency Graph

```
Wave 1 (no deps):
  29A: PKG-HO3-MEMORY-001 (new)

Wave 2 (depends on 29A):
  29B: PKG-HO2-SUPERVISOR-001 (modify)

Wave 3 (depends on 29B):
  29C: PKG-HO1-EXECUTOR-001 (modify)
     + PKG-HO2-SUPERVISOR-001 (modify)
     + PKG-LLM-GATEWAY-001 (modify)
```

Each wave produces its own RESULTS file and clean-room verification. Wave N+1 starts from Wave N's validated baseline.
