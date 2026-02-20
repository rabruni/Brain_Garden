# BUILDER_HANDOFF_31C: Intent Lifecycle in HO2

## 1. Mission

Add a pure deterministic function that reads the classify output's `intent_signal` and manages intent as a first-class lifecycle entity in ho2m.jsonl. Intent transitions (DECLARED/SUPERSEDED/CLOSED) are written to the ledger. This gives the system a structured view of "what the user is trying to do" across turns. Modifies **PKG-HO2-SUPERVISOR-001** only.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**.
2. **DTT: Design → Test → Then implement.**
3. **Package everything.** Use `compute_sha256()` and `pack()`.
4. **End-to-end verification.** Clean-room install → all gates pass.
5. **Tar archive format:** `tar czf ... -C dir $(ls dir)`.
6. **Results file.** `_staging/handoffs/RESULTS_HANDOFF_31C.md`.
7. **Full regression.** ALL staged tests. New failures are blockers.
8. **Baseline:** 22 packages, 693 installed tests, 8/8 gates.
9. **Scope:** PKG-HO2-SUPERVISOR-001 ONLY.
10. **Pure function.** `resolve_intent_transition()` has NO LLM calls, NO side effects. It takes data in, returns a decision. The caller (ho2_supervisor.py) writes ledger events.
11. **Graceful degradation.** If classify doesn't return `intent_signal` (pre-H-31B or LLM omission), use bridge mode: auto-continue if active intent exists, auto-declare if none.

## 3. Architecture / Design

### New File: HO2/kernel/intent_resolver.py

Pure function module. No LLM calls. No file I/O. No imports beyond stdlib + dataclasses.

```python
@dataclass
class TransitionDecision:
    action: str  # "declare", "continue", "supersede", "close", "noop"
    new_intent: dict | None = None    # if declare or supersede
    closed_intent_id: str | None = None  # if supersede or close
    conflict_flag: dict | None = None    # if multiple active intents

def resolve_intent_transition(
    active_intents: list[dict],   # currently live intents from ledger scan
    classify_result: dict,         # includes intent_signal if present
    session_id: str,
    sequence: int,                 # next sequence number for intent ID
) -> TransitionDecision
```

### Transition Table

| Active Intents | intent_signal.action | Decision |
|---------------|---------------------|----------|
| None | new/unclear/missing | DECLARE new intent |
| None | continue | DECLARE new intent (bridge) |
| None | close | NOOP (nothing to close) |
| 1 active | new | SUPERSEDE old + DECLARE new |
| 1 active | continue | CONTINUE (no event) |
| 1 active | close | CLOSE active |
| 1 active | unclear | CONTINUE + emit CONFLICT_FLAG |
| 1 active | missing | CONTINUE (bridge mode) |
| 2+ active | any | CONTINUE most recent + emit CONFLICT_FLAG |

### Intent ID Format

`INT-<session_id_short>-<3-digit-sequence>` (e.g., `INT-F8805C46-001`)

### New Ledger Events (ho2m.jsonl)

```json
{"event_type": "INTENT_DECLARED", "metadata": {
  "intent_id": "INT-F8805C46-001",
  "scope": "session",
  "objective": "Explore installed packages",
  "parent_intent_id": null
}}

{"event_type": "INTENT_SUPERSEDED", "metadata": {
  "intent_id": "INT-F8805C46-001",
  "superseded_by_intent_id": "INT-F8805C46-002",
  "reason": "User started new topic"
}}

{"event_type": "INTENT_CLOSED", "metadata": {
  "intent_id": "INT-F8805C46-001",
  "outcome": "completed",
  "reason": "User farewell"
}}
```

### Integration in ho2_supervisor.py

In `handle_turn()`, after Step 2a (classify, line 185) and before Step 2b (attention, line 188):

```python
# Step 2a+: Intent lifecycle
active_intents = self._scan_active_intents(session_id)
intent_decision = resolve_intent_transition(
    active_intents, classification, session_id, self._intent_sequence
)
self._apply_intent_decision(intent_decision, session_id)
```

New helper methods on HO2Supervisor:
- `_scan_active_intents(session_id)` — scan ho2m.jsonl for INTENT_DECLARED not followed by CLOSED/SUPERSEDED
- `_apply_intent_decision(decision, session_id)` — write INTENT_DECLARED/SUPERSEDED/CLOSED events
- `_intent_sequence` — counter starting at 1, incremented on DECLARE

### Adversarial Analysis: Bridge Mode

**Hurdles**: Until H-31B is deployed, classify won't return intent_signal. Bridge mode must handle this gracefully — no crashes, no junk events.

**Not Enough**: If bridge mode just ignores intents, we lose the ability to track "what's the user doing" for the liveness reducer (H-31D).

**Too Much**: We could try to infer intent from speech_act alone ("command" → "new"). Fragile and not what classify was asked to do.

**Synthesis**: Bridge mode: if intent_signal is missing, auto-continue if active intent exists, auto-declare if not. The objective comes from the first classify result's speech_act + user_message[:50].

## 4. Implementation Steps

### Step 1: Create intent_resolver.py

New file: `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/intent_resolver.py`

Contains:
- `TransitionDecision` dataclass
- `resolve_intent_transition()` pure function
- `make_intent_id(session_id, sequence)` helper

### Step 2: Add intent integration to ho2_supervisor.py

After classify (line 185), before attention (line 188):
- Import `resolve_intent_transition` from `intent_resolver`
- Add `_scan_active_intents()` method
- Add `_apply_intent_decision()` method
- Add `_intent_sequence` counter (initialized in `start_session()`)
- Store `self._current_intent_id` for use by future projection

### Step 3: Add intent_resolver.py to manifest

Add new asset entry with classification "library".

### Step 4: Write tests

Tests for both intent_resolver.py (pure function tests) and the integration in ho2_supervisor.py.

### Step 5: Governance cycle

Update hashes, rebuild archives, clean-room install, gates.

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
- `HO2/kernel/intent_resolver.py` — pure function module

Modified assets:
- `HO2/kernel/ho2_supervisor.py` — intent integration at Step 2a+
- `HO2/tests/test_ho2_supervisor.py` — integration tests
- `manifest.json` — new asset + hash updates

New test file:
- `HO2/tests/test_intent_resolver.py` — pure function tests

## 6. Test Plan

### intent_resolver.py tests (12)

| Test | Description | Expected |
|------|-------------|----------|
| `test_no_active_new_declares` | No active intent + action=new → DECLARE | action="declare", new_intent set |
| `test_no_active_missing_declares` | No active intent + no intent_signal → DECLARE (bridge) | action="declare" |
| `test_no_active_close_noop` | No active + close → NOOP | action="noop" |
| `test_active_continue` | 1 active + continue → CONTINUE | action="continue" |
| `test_active_new_supersedes` | 1 active + new → SUPERSEDE + DECLARE | action="supersede", closed_intent_id set, new_intent set |
| `test_active_close` | 1 active + close → CLOSE | action="close", closed_intent_id set |
| `test_active_unclear_conflict` | 1 active + unclear → CONTINUE + CONFLICT_FLAG | action="continue", conflict_flag set |
| `test_active_missing_bridge` | 1 active + no intent_signal → CONTINUE (bridge) | action="continue" |
| `test_multiple_active_conflict` | 2 active intents → CONTINUE most recent + CONFLICT_FLAG | conflict_flag set |
| `test_intent_id_format` | make_intent_id("SES-F8805C46", 1) | "INT-F8805C46-001" |
| `test_deterministic` | Same inputs → same output | Two calls produce identical result |
| `test_objective_from_classify` | candidate_objective flows into new_intent.objective | objective matches |

### ho2_supervisor.py integration tests (4)

| Test | Description | Expected |
|------|-------------|----------|
| `test_intent_declared_on_first_turn` | First handle_turn → INTENT_DECLARED in ho2m | Event written |
| `test_intent_superseded_on_topic_switch` | Turn with action=new when active → SUPERSEDED + DECLARED | Both events |
| `test_intent_closed_on_farewell` | Turn with close → INTENT_CLOSED in ho2m | Event written |
| `test_no_intent_events_on_continue` | Turn with continue → no intent events | No INTENT_* events |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| ho2_supervisor.py | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py` | Integration point |
| handle_turn classify | `ho2_supervisor.py:156-185` | Where to insert intent logic |
| LedgerEntry | `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` | Event writing pattern |
| _log_wo_event | `ho2_supervisor.py:436-452` | Pattern for ledger event writing |
| manifest.json | `_staging/PKG-HO2-SUPERVISOR-001/manifest.json` | Asset list to update |

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
| `intent_resolver.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | CREATE |
| `ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | MODIFY |
| `test_intent_resolver.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/` | CREATE |
| `test_ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO2-SUPERVISOR-001/` | MODIFY |
| `PKG-HO2-SUPERVISOR-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_31C.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Pure function.** Intent resolution is deterministic. Same inputs → same output. No LLM calls.
2. **Bridge mode.** Works without H-31B. Missing intent_signal → auto-declare/auto-continue.
3. **Single active intent.** For ADMIN MVP. Data model supports multiple (for RESIDENT later).
4. **Append-only lifecycle.** DECLARED/SUPERSEDED/CLOSED are events, not mutations. Ledger stays immutable.
5. **Conflict visible.** Multiple active intents emit CONFLICT_FLAG. Never silently pick one.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project.

**Agent: HANDOFF-31C** — Intent lifecycle in HO2 (PKG-HO2-SUPERVISOR-001)

Read: `Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_31C_intent_lifecycle.md`

**Rules:** 1. _staging/ only. 2. DTT. 3. compute_sha256()+pack(). 4. sha256:<64hex>. 5. Clean-room. 6. Full regression. 7. Results file. 8. CP_BOOTSTRAP rebuild. 9. PKG-HO2-SUPERVISOR-001 ONLY.

**10 Questions:**

1. What package? What NEW file do you create? What EXISTING file do you modify?
2. What is resolve_intent_transition's signature? What does it return?
3. Walk through the transition table: 1 active intent + action="new" → what happens?
4. What is bridge mode? When does it activate? What does it do?
5. What 3 new event types are written to ho2m.jsonl? Show the metadata structure for each.
6. Where in handle_turn does intent resolution run? What comes before it? What comes after?
7. How does _scan_active_intents work? What makes an intent "active"?
8. How many tests total? Split between intent_resolver.py tests and integration tests.
9. What is the intent ID format? Give an example.
10. Can resolve_intent_transition make LLM calls? Can it write to the ledger? Why not?

**Adversarial:**
11. What happens if intent_resolver.py is imported but H-31B hasn't run (classify doesn't return intent_signal)?
12. If _scan_active_intents reads ALL of ho2m.jsonl every turn, what's the performance concern for long sessions?
13. INTENT_SUPERSEDED references superseded_by_intent_id — what if the new intent creation fails after the supersede event is written?

STOP AFTER ANSWERING.
```

### Expected Answers

1. PKG-HO2-SUPERVISOR-001. CREATE: `HO2/kernel/intent_resolver.py`, `HO2/tests/test_intent_resolver.py`. MODIFY: `HO2/kernel/ho2_supervisor.py`, `HO2/tests/test_ho2_supervisor.py`, `manifest.json`.
2. `resolve_intent_transition(active_intents, classify_result, session_id, sequence) -> TransitionDecision`. TransitionDecision has: action, new_intent, closed_intent_id, conflict_flag.
3. 1 active + new → action="supersede". closed_intent_id = the active intent's ID. new_intent = new intent dict with next sequence number. The caller writes INTENT_SUPERSEDED then INTENT_DECLARED.
4. Bridge mode activates when classify_result has no intent_signal (pre-H-31B or LLM omission). If active intent exists → CONTINUE. If no active intent → DECLARE (with objective from user_message[:50]).
5. INTENT_DECLARED: {intent_id, scope, objective, parent_intent_id}. INTENT_SUPERSEDED: {intent_id, superseded_by_intent_id, reason}. INTENT_CLOSED: {intent_id, outcome, reason}.
6. After Step 2a (classify, line 185), before Step 2b (attention, line 188).
7. Reads ho2m entries, filters to session_id, finds INTENT_DECLARED events not followed by INTENT_CLOSED or INTENT_SUPERSEDED for the same intent_id. An intent is "active" if its last lifecycle event is DECLARED.
8. 16 total: 12 for intent_resolver.py, 4 for integration.
9. `INT-<session_id_short>-<3-digit-sequence>`. Example: `INT-F8805C46-001`.
10. No and no. It's a pure function — takes data, returns a decision. The caller in ho2_supervisor.py writes ledger events. This separation makes it fully testable without mocks.
11. Bridge mode handles it. classify_result.get("intent_signal") returns None. resolve_intent_transition checks for None and applies bridge rules (auto-continue if active, auto-declare if not).
12. For a 50-turn session with ~100 ho2m entries, scanning is fine (~1ms). For very long sessions, could cache active intents in HO2Supervisor state. Not needed for MVP (ADMIN has turn_limit=50).
13. Both events are written by _apply_intent_decision. The supersede and declare are sequential writes. If declare fails, we have an INTENT_SUPERSEDED with no replacement. _scan_active_intents would find 0 active intents on the next turn → bridge mode auto-declares. Self-healing, no data corruption (both events are immutable in the ledger).
