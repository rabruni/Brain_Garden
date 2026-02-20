# BUILDER_HANDOFF_31D: Liveness Reducer + Projection Snapshot

## 1. Mission

Add a pure function that reads ho2m.jsonl + ho1m.jsonl and computes what's alive (active intents, open WOs, failed items, escalations). Write PROJECTION_COMPUTED snapshots to a new overlay ledger. This gives the Context Authority a structured view of system state for each turn. Modifies **PKG-HO2-SUPERVISOR-001** only.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**.
2. **DTT: Design → Test → Then implement.**
3. **Package everything.** Use `compute_sha256()` and `pack()`.
4. **End-to-end verification.** Clean-room install → all gates pass.
5. **Tar archive format:** `tar czf ... -C dir $(ls dir)`.
6. **Results file.** `_staging/handoffs/RESULTS_HANDOFF_31D.md`.
7. **Full regression.** ALL staged tests. New failures are blockers.
8. **Baseline:** 22 packages, 693 installed tests, 8/8 gates.
9. **Scope:** PKG-HO2-SUPERVISOR-001 ONLY.
10. **Pure function.** `reduce_liveness()` has NO LLM calls, NO side effects. Takes ledger entries, returns LivenessState.
11. **"Latest event wins."** For each entity (intent, WO), gather all lifecycle events, sort by (timestamp, entry_id), last event determines state.
12. **Cross-ledger join.** WO_PLANNED in ho2m, WO_COMPLETED in ho1m, matched by work_order_id.

## 3. Architecture / Design

### New File: HO2/kernel/liveness.py

Pure function module. No LLM calls. No file I/O. No imports beyond stdlib + dataclasses.

```python
@dataclass
class LivenessState:
    intents: dict       # intent_id → {status, scope, objective, declared_at, closed_at?}
    work_orders: dict   # wo_id → {status, intent_id, wo_type, planned_at, completed_at?}
    active_intents: list[str]     # intent_ids with status=LIVE
    open_work_orders: list[str]   # wo_ids with status=OPEN
    failed_items: list[dict]      # [{wo_id, reason, timestamp}]
    escalations: list[dict]       # [{wo_id, reason, timestamp}]

def reduce_liveness(
    ho2m_entries: list[dict],
    ho1m_entries: list[dict],
) -> LivenessState
```

### Event Mapping ("latest event wins")

| Source Event | Liveness Event | Entity | Status |
|-------------|---------------|--------|--------|
| INTENT_DECLARED | OPENED | Intent | LIVE |
| INTENT_SUPERSEDED | CLOSED | Intent | SUPERSEDED |
| INTENT_CLOSED | CLOSED | Intent | CLOSED |
| WO_PLANNED | OPENED | WO | OPEN |
| WO_DISPATCHED | OPENED | WO | DISPATCHED |
| WO_COMPLETED (ho1m) | CLOSED | WO | COMPLETED |
| ESCALATION | CLOSED | WO | FAILED |

Cross-ledger join: WO_PLANNED events are in ho2m.jsonl. WO_COMPLETED events are in ho1m.jsonl (or sometimes ho2m). Match by `work_order_id` field in metadata.

### Algorithm

```
1. Collect all events from both ledgers
2. Group by entity_id (intent_id or wo_id)
3. For each entity, sort events by (timestamp, entry sequence)
4. Last event determines status:
   - LIVE/OPEN events → entity is active
   - CLOSED events → entity is not active
5. Classify: active_intents, open_work_orders, failed_items, escalations
```

### New File: HO2/kernel/overlay_writer.py

```python
def write_projection(
    liveness: LivenessState,
    session_id: str,
    turn_id: str,
    token_budget: int,
    overlay_ledger: LedgerClient,
) -> dict
```

Appends PROJECTION_COMPUTED entry to ho2_context_authority.jsonl:

```json
{
  "event_type": "PROJECTION_COMPUTED",
  "metadata": {
    "session_id": "SES-...",
    "turn_id": "TURN-...",
    "token_budget": 10000,
    "active_intents": [{"intent_id": "INT-...", "objective": "..."}],
    "open_work_orders": [{"wo_id": "WO-...", "wo_type": "synthesize"}],
    "failed_items": [],
    "escalations": [],
    "intent_count": 1,
    "open_wo_count": 0,
    "failed_count": 0,
    "computed_at": "2026-02-18T..."
  }
}
```

### Overlay Ledger Path

`HO2/ledger/ho2_context_authority.jsonl` — separate from ho2m.jsonl (source vs derived). Created by overlay_writer on first projection. Uses LedgerClient (append-only, hash-chained).

### Integration in ho2_supervisor.py

After Step 2a+ (intent lifecycle, from H-31C) and before Step 2b (attention/bias), call:

```python
# Step 2a++: Liveness reduction
ho2m_entries = self._ho2m_client.read_all()
ho1m_entries = self._ho1m_client.read_all() if self._ho1m_client else []
liveness = reduce_liveness(ho2m_entries, ho1m_entries)
write_projection(liveness, session_id, turn_id, self._config.projection_budget, self._overlay_ledger)
```

Store `self._current_liveness` for use by the context projector (H-31E).

### Adversarial Analysis: Ledger Scan Size

**Hurdles**: Reading ALL of ho2m.jsonl and ho1m.jsonl every turn could be slow for long sessions.
**Not Enough**: Just reading the last N entries misses lifecycle events that happened earlier.
**Too Much**: Building an incremental index adds complexity.
**Synthesis**: For ADMIN (turn_limit=50), ho2m.jsonl has ~200-300 entries and ho1m.jsonl ~50-100. Scanning is <10ms. If scale becomes a concern, add session-scoped filtering and incremental caching. Not needed for MVP.

## 4. Implementation Steps

### Step 1: Create liveness.py

New file with `LivenessState` dataclass and `reduce_liveness()` pure function.

### Step 2: Create overlay_writer.py

New file with `write_projection()` function. Uses LedgerClient for append.

### Step 3: Integrate in ho2_supervisor.py

Add liveness reduction + projection writing in handle_turn. Initialize overlay ledger in constructor.

### Step 4: Add ho2m/ho1m ledger client access

HO2Supervisor constructor needs access to ho2m and ho1m LedgerClients for reading. ho2m_client already exists (`self._ho2m`). Add ho1m_path to HO2Config if not already present.

### Step 5: Write tests

Tests for liveness.py (pure function), overlay_writer.py, and integration.

### Step 6: Governance cycle

Update manifest (add liveness.py, overlay_writer.py assets), rebuild archives, gates.

## 5. Package Plan

### PKG-HO2-SUPERVISOR-001 (modified)

| Field | Value |
|-------|-------|
| Package ID | PKG-HO2-SUPERVISOR-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | ho2 |

New assets:
- `HO2/kernel/liveness.py` — pure function module
- `HO2/kernel/overlay_writer.py` — projection snapshot writer

Modified assets:
- `HO2/kernel/ho2_supervisor.py` — liveness integration
- `HO2/tests/test_ho2_supervisor.py` — integration tests
- `manifest.json` — new assets + hash updates

New test files:
- `HO2/tests/test_liveness.py` — pure function tests
- `HO2/tests/test_overlay_writer.py` — writer tests

## 6. Test Plan

### liveness.py tests (12)

| Test | Description | Expected |
|------|-------------|----------|
| `test_empty_entries` | No entries → empty LivenessState | All lists empty |
| `test_intent_declared_is_live` | INTENT_DECLARED → active_intents | intent_id in active list |
| `test_intent_closed_not_live` | DECLARED then CLOSED → not active | intent_id not in active list |
| `test_intent_superseded_not_live` | DECLARED then SUPERSEDED → not active | Old intent removed |
| `test_wo_planned_is_open` | WO_PLANNED → open_work_orders | wo_id in open list |
| `test_wo_completed_not_open` | WO_PLANNED then WO_COMPLETED → closed | wo_id not in open list |
| `test_wo_failed_in_failed_items` | ESCALATION after WO → failed_items | wo_id in failed list |
| `test_cross_ledger_join` | WO_PLANNED (ho2m) + WO_COMPLETED (ho1m) → completed | Joined correctly |
| `test_latest_event_wins` | Multiple events → last determines state | Correct status |
| `test_deterministic_ordering` | Same entries different order → same result | Identical output |
| `test_multiple_intents` | 3 intents with different states → correct counts | Counts match |
| `test_session_scoped` | Only entries for target session counted | Filtered |

### overlay_writer.py tests (4)

| Test | Description | Expected |
|------|-------------|----------|
| `test_projection_written` | write_projection → PROJECTION_COMPUTED in ledger | Event written |
| `test_projection_metadata` | Projection has session_id, turn_id, counts | All fields present |
| `test_projection_budget_recorded` | token_budget in projection metadata | Value matches |
| `test_empty_liveness_writes` | Empty LivenessState → projection still written | Event created |

### Integration tests (4)

| Test | Description | Expected |
|------|-------------|----------|
| `test_liveness_computed_each_turn` | handle_turn → reduce_liveness called | Called once per turn |
| `test_projection_written_each_turn` | handle_turn → PROJECTION_COMPUTED in overlay ledger | Event exists |
| `test_liveness_available_for_context` | After liveness, self._current_liveness set | Attribute set |
| `test_ho1m_entries_joined` | HO1m WO_COMPLETED events joined with HO2m WO_PLANNED | Join works |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| ho2_supervisor.py | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py` | Integration point |
| handle_turn | `ho2_supervisor.py:151-367` | Where to insert liveness |
| LedgerClient | `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` | For overlay ledger |
| intent events (H-31C) | `intent_resolver.py` | INTENT_DECLARED/CLOSED/SUPERSEDED |
| WO events | `ho2_supervisor.py:436-452` | WO_PLANNED event structure |

## 8. End-to-End Verification

```bash
TMPDIR=$(mktemp -d)
cd Control_Plane_v2/_staging && tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
cd "$TMPDIR" && bash install.sh --root "$TMPDIR" --dev
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 -m pytest "$TMPDIR/HOT/tests" "$TMPDIR/HO1/tests" "$TMPDIR/HO2/tests" -v
python3 "$TMPDIR/HOT/scripts/gate_check.py" --root "$TMPDIR" --all --enforce
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `liveness.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | CREATE |
| `overlay_writer.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | CREATE |
| `ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | MODIFY |
| `test_liveness.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/` | CREATE |
| `test_overlay_writer.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/` | CREATE |
| `test_ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO2-SUPERVISOR-001/` | MODIFY |
| `PKG-HO2-SUPERVISOR-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_31D.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Pure function.** reduce_liveness is deterministic. No LLM. No I/O. Same entries → same state.
2. **Latest event wins.** Lifecycle resolved by event ordering, not mutation.
3. **Cross-ledger join.** WOs span ho2m (planned) and ho1m (completed). Joined by wo_id.
4. **Source vs derived.** ho2m.jsonl is source. ho2_context_authority.jsonl is derived (projections).
5. **Snapshot per turn.** Every turn gets a PROJECTION_COMPUTED entry. Full history of what the system thought was alive.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project.

**Agent: HANDOFF-31D** — Liveness reducer + projection snapshot (PKG-HO2-SUPERVISOR-001)

Read: `Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_31D_liveness_reducer.md`

**Rules:** 1. _staging/ only. 2. DTT. 3. compute_sha256()+pack(). 4. sha256:<64hex>. 5. Clean-room. 6. Full regression. 7. Results file. 8. CP_BOOTSTRAP rebuild. 9. PKG-HO2-SUPERVISOR-001 ONLY.

**10 Questions:**

1. What package? What TWO new files do you create? What existing file do you modify?
2. What is reduce_liveness' signature? What does LivenessState contain?
3. Explain "latest event wins" with an example: INTENT_DECLARED then INTENT_SUPERSEDED → what?
4. How does the cross-ledger join work? What event is in ho2m? What event is in ho1m? How are they matched?
5. What is the overlay ledger path? How is it different from ho2m.jsonl?
6. What does PROJECTION_COMPUTED contain? List the metadata fields.
7. Where in handle_turn does liveness reduction run? What comes before? What comes after?
8. How many tests total? Split between liveness.py, overlay_writer.py, and integration.
9. What makes an intent LIVE? What makes a WO OPEN? What makes a WO FAILED?
10. Can reduce_liveness make LLM calls? Can overlay_writer write to ho2m.jsonl?

**Adversarial:**
11. Reading ALL of ho2m.jsonl every turn — what's the performance for a 50-turn session?
12. If ho1m.jsonl doesn't exist (no HO1 ledger path configured), what happens?
13. A WO_PLANNED event exists but no WO_COMPLETED or ESCALATION — is this always a zombie, or could it be in-flight?

STOP AFTER ANSWERING.
```

### Expected Answers

1. PKG-HO2-SUPERVISOR-001. CREATE: `HO2/kernel/liveness.py`, `HO2/kernel/overlay_writer.py`, `HO2/tests/test_liveness.py`, `HO2/tests/test_overlay_writer.py`. MODIFY: `HO2/kernel/ho2_supervisor.py`, `HO2/tests/test_ho2_supervisor.py`, `manifest.json`.
2. `reduce_liveness(ho2m_entries, ho1m_entries) -> LivenessState`. LivenessState: intents dict, work_orders dict, active_intents list, open_work_orders list, failed_items list, escalations list.
3. INTENT_DECLARED makes intent LIVE. INTENT_SUPERSEDED comes after (later timestamp). Latest event wins → status=SUPERSEDED. Intent NOT in active_intents.
4. WO_PLANNED is in ho2m.jsonl (HO2 plans WOs). WO_COMPLETED is in ho1m.jsonl (HO1 reports completion). Matched by work_order_id field in metadata. The join merges both into the WO entity's event list.
5. `HO2/ledger/ho2_context_authority.jsonl`. It's a derived ledger (projections/snapshots), separate from ho2m.jsonl (source events). Uses LedgerClient, append-only.
6. session_id, turn_id, token_budget, active_intents (list of intent summaries), open_work_orders (list of WO summaries), failed_items, escalations, intent_count, open_wo_count, failed_count, computed_at.
7. After Step 2a+ (intent lifecycle from H-31C), before Step 2b (attention/bias). Intent events are written → liveness can see them → projection computed → context projector (H-31E) can use liveness state.
8. 20 total: 12 for liveness.py, 4 for overlay_writer.py, 4 for integration.
9. LIVE intent: last event is INTENT_DECLARED. OPEN WO: last event is WO_PLANNED or WO_DISPATCHED (no WO_COMPLETED or ESCALATION). FAILED WO: has an ESCALATION event as its latest event.
10. No and no. reduce_liveness is a pure function. overlay_writer writes to ho2_context_authority.jsonl (derived ledger), NOT to ho2m.jsonl (source ledger). Separation of source and derived.
11. 50-turn session → ~200-300 ho2m entries + ~50-100 ho1m entries. Scanning ~400 entries is <10ms on any modern hardware. Not a concern for MVP. Could add incremental caching if scale increases.
12. ho1m_entries defaults to empty list. reduce_liveness works with no HO1 entries — WOs that were WO_PLANNED but have no WO_COMPLETED are classified as OPEN (which is correct: they might still be in-flight or they might be zombies). No crash.
13. Could be either. Within the same turn, a WO_PLANNED followed by immediate _dispatch_wo would produce WO_COMPLETED in the same turn. If WO_PLANNED appears with no completion event, it could be: (a) a zombie from a crash, or (b) in-flight during the current turn. The liveness reducer reports it as OPEN — the consumer (context projector) decides whether to treat it as a problem based on age.
