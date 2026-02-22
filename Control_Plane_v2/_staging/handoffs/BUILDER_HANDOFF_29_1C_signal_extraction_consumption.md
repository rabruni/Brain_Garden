# BUILDER_HANDOFF_29.1C: Richer Signal Extraction + Consumption Policy

## 1. Mission

Expand HO2's post-turn signal extraction to emit domain, task, and outcome signals from classify labels and WO results. Add a pure `select_biases()` function that implements the 6-line consumption model (filter → rank → scope → budget → inject). Replace the current "dump all biases" at Step 2b+ with label-matched, budget-constrained artifact selection. Modifies **PKG-HO2-SUPERVISOR-001** only.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**.
2. **DTT: Design → Test → Then implement.**
3. **Package everything.** Use `compute_sha256()` and `pack()`.
4. **End-to-end verification.** Clean-room install → all gates pass.
5. **Tar archive format:** `tar czf ... -C dir $(ls dir)`.
6. **Results file.** `_staging/handoffs/RESULTS_HANDOFF_29_1C.md`.
7. **Full regression.** ALL staged tests. New failures are blockers.
8. **Baseline:** 22 packages, 693 installed tests, 8/8 gates.
9. **Scope:** PKG-HO2-SUPERVISOR-001 ONLY.
10. **Pure function.** `select_biases()` has NO LLM calls, NO side effects. Takes data in, returns filtered/ranked list.
11. **Backward compatible.** If classify doesn't return labels (pre-H-31B), signal extraction falls back to existing behavior. select_biases with no turn_labels returns global-scope artifacts only.

## 3. Architecture / Design

### Part A: Richer Signal Extraction

**Current signal extraction (ho2_supervisor.py:307-334):**
```python
# Intent signal from classify WO result
classification_type = classification.get("speech_act")
if classification_type:
    sig_id = f"intent:{classification_type}"
    ...
# Tool signals from WO chain cost.tool_ids_used
for wo_result in wo_chain:
    for tid in wo_result.get("cost", {}).get("tool_ids_used", []):
        sig_id = f"tool:{tid}"
        ...
```

**New signal extraction (adds 3 signal types):**
```python
# Existing: intent + tool signals

# NEW: Domain signal from classify labels
domain = classification.get("labels", {}).get("domain")
if domain:
    sig_id = f"domain:{domain}"
    evt_id = f"EVT-{hash(...)[:8]}"
    self._ho3_memory.log_signal(sig_id, session_id, evt_id)
    signals_this_turn.append(sig_id)

# NEW: Task signal from classify labels
task = classification.get("labels", {}).get("task")
if task:
    sig_id = f"task:{task}"
    evt_id = f"EVT-{hash(...)[:8]}"
    self._ho3_memory.log_signal(sig_id, session_id, evt_id)
    signals_this_turn.append(sig_id)

# NEW: Outcome signal from synthesize WO result
synth_state = synth_result.get("state", "unknown")
outcome = "success" if synth_state == "completed" else (
    "failed" if synth_state == "failed" else "unknown"
)
sig_id = f"outcome:{outcome}"
evt_id = f"EVT-{hash(...)[:8]}"
self._ho3_memory.log_signal(sig_id, session_id, evt_id)
signals_this_turn.append(sig_id)
```

After this, HO3 signals.jsonl receives 5 signal types per turn:
- `intent:<speech_act>` (existing)
- `tool:<tool_id>` (existing, 0-N per turn)
- `domain:<domain_label>` (new, 0-1 per turn)
- `task:<task_label>` (new, 0-1 per turn)
- `outcome:<success|failed|unknown>` (new, 1 per turn)

### Part B: Consumption Policy (select_biases)

**New file: `HO2/kernel/bias_selector.py`**

Pure function module. No LLM. No file I/O. No side effects.

```python
def select_biases(
    artifacts: list[dict],       # from read_active_biases(as_of_ts)
    turn_labels: dict,           # from classify result {"domain": "system", "task": "inspect"}
    ho3_bias_budget: int,        # from admin_config.json
    as_of_ts: str,               # current turn event timestamp
) -> list[dict]:
    """6-line consumption model: filter → rank → scope → budget → return.

    Returns list of artifact dicts to inject (with context_line field).
    """
```

Implementation of the 6-line contract:
1. **Filter:** `enabled=True`, not expired (`expires_at_event_ts is None or as_of_ts < expires_at_event_ts`)
2. **Scope match:** `artifact.labels ∩ turn_labels != empty` OR `scope == "global"`. Set intersection on domain and task separately — match if either dimension intersects.
3. **Rank:** Sort by `weight × decay_modifier × recency_score` descending. Recency = 1.0 for artifacts < 1 day old, decaying to 0.5 at 7 days.
4. **Budget:** Take top-k artifacts whose cumulative `len(context_line) / 4` (token estimate) fits within `ho3_bias_budget`.
5. **Return:** List of selected artifact dicts.

### Integration at Step 2b+

**Current (ho2_supervisor.py:191-201):**
```python
ho3_biases = []
if self._ho3_memory and self._config.ho3_enabled:
    ho3_biases = self._ho3_memory.read_active_biases()
...
if ho3_biases:
    assembled_context["ho3_biases"] = ho3_biases
```

**New:**
```python
ho3_biases = []
if self._ho3_memory and self._config.ho3_enabled:
    all_artifacts = self._ho3_memory.read_active_biases(as_of_ts=turn_event_ts)
    turn_labels = classification.get("labels", {})
    ho3_biases = select_biases(
        all_artifacts, turn_labels,
        self._config.ho3_bias_budget, turn_event_ts
    )
...
if ho3_biases:
    # Inject context_lines verbatim
    context_lines = [a.get("context_line", a.get("content", {}).get("bias", "")) for a in ho3_biases]
    assembled_context["ho3_biases"] = context_lines
```

### Adversarial Analysis: Empty Labels

**Hurdles**: Before H-31B, classify returns no labels. select_biases gets empty turn_labels.
**Not Enough**: If we require label match, no artifacts get injected pre-H-31B.
**Too Much**: If we skip filtering pre-H-31B, we inject everything (budget-limited but unfiltered).
**Synthesis**: When turn_labels is empty, select_biases returns only global-scope artifacts (filter by scope="global"). Old-format biases without labels are included if they have no labels field (backward compat). After H-31B, label matching activates naturally.

## 4. Implementation Steps

### Step 1: Create bias_selector.py

New file: `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/bias_selector.py`

Contains `select_biases()` pure function.

### Step 2: Expand signal extraction

In `ho2_supervisor.py`, after existing signal extraction (around line 328), add domain, task, and outcome signals.

### Step 3: Update Step 2b+ bias injection

Replace "dump all biases" with `select_biases()` call. Extract context_lines for injection.

### Step 4: Add ho3_bias_budget to HO2Config

Ensure HO2Config has `ho3_bias_budget: int = 2000` field (should already exist from H-31A-1, verify).

### Step 5: Add turn_event_ts generation

Generate `turn_event_ts = datetime.now(timezone.utc).isoformat()` at top of handle_turn for use in as_of_ts parameters.

### Step 6: Write tests

Tests for bias_selector.py and integration in ho2_supervisor.py.

### Step 7: Governance cycle

Update manifest (add bias_selector.py asset), rebuild archives, clean-room install, gates.

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
- `HO2/kernel/bias_selector.py` — pure function module

Modified assets:
- `HO2/kernel/ho2_supervisor.py` — signal extraction + consumption
- `HO2/tests/test_ho2_supervisor.py` — integration tests
- `manifest.json` — new asset + hash updates

New test file:
- `HO2/tests/test_bias_selector.py` — pure function tests

## 6. Test Plan

### bias_selector.py tests (12)

| Test | Description | Expected |
|------|-------------|----------|
| `test_filter_disabled` | enabled=false artifact excluded | Not in result |
| `test_filter_expired` | expired artifact excluded by as_of_ts | Not in result |
| `test_filter_not_expired` | non-expired artifact included | In result |
| `test_scope_match_domain` | artifact.labels.domain ∩ turn.domain ≠ empty | Included |
| `test_scope_match_task` | artifact.labels.task ∩ turn.task ≠ empty | Included |
| `test_scope_no_match` | no label intersection, not global | Excluded |
| `test_scope_global_always_included` | scope="global" included regardless of labels | Included |
| `test_rank_by_weight` | Higher weight ranked first | Correct order |
| `test_budget_limit` | 3 artifacts but budget fits 2 | Only 2 returned |
| `test_empty_turn_labels_global_only` | No turn_labels → only global artifacts | Global only |
| `test_deterministic` | Same inputs → same output | Identical result |
| `test_backward_compat_no_labels_field` | Old artifact without labels → included if no label filtering active | Included |

### ho2_supervisor.py integration tests (6)

| Test | Description | Expected |
|------|-------------|----------|
| `test_domain_signal_logged` | Classify returns labels.domain → domain signal in signals.jsonl | Signal logged |
| `test_task_signal_logged` | Classify returns labels.task → task signal logged | Signal logged |
| `test_outcome_signal_logged` | Synthesize completes → outcome signal logged | outcome:success signal |
| `test_no_domain_signal_without_labels` | Classify without labels → no domain signal | No domain signal |
| `test_select_biases_called_at_step2b` | Active biases selected via select_biases not dump-all | select_biases called |
| `test_context_lines_injected` | Selected artifacts' context_lines in assembled_context | context_lines present |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| ho2_supervisor.py | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py` | Integration point |
| Signal extraction | `ho2_supervisor.py:307-334` | Where to add new signals |
| Step 2b+ bias | `ho2_supervisor.py:191-201` | Where to add select_biases |
| HO2Config | `ho2_supervisor.py:57-84` | ho3_bias_budget field |
| HO3 read_active_biases | `_staging/PKG-HO3-MEMORY-001/HOT/kernel/ho3_memory.py:330-339` | Data source |

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
| `bias_selector.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | CREATE |
| `ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | MODIFY |
| `test_bias_selector.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/` | CREATE |
| `test_ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO2-SUPERVISOR-001/` | MODIFY |
| `PKG-HO2-SUPERVISOR-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_29_1C.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Pure function.** select_biases is deterministic. No LLM. No I/O. Same inputs → same output.
2. **6-line contract.** Filter → rank → scope → budget → inject → never read meaning.
3. **Label matching.** Set intersection between turn labels and artifact labels. No semantics.
4. **Budget-constrained.** Top-k artifacts that fit within ho3_bias_budget tokens.
5. **Graceful pre-H-31B.** Empty turn_labels → global-scope artifacts only.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project.

**Agent: HANDOFF-29.1C** — Signal extraction + consumption policy (PKG-HO2-SUPERVISOR-001)

Read: `Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_29_1C_signal_extraction_consumption.md`

**Rules:** 1. _staging/ only. 2. DTT. 3. compute_sha256()+pack(). 4. sha256:<64hex>. 5. Clean-room. 6. Full regression. 7. Results file. 8. CP_BOOTSTRAP rebuild. 9. PKG-HO2-SUPERVISOR-001 ONLY.

**10 Questions:**

1. What package? What NEW file do you create? What EXISTING file do you modify?
2. What 5 signal types does HO3 receive per turn after this handoff? Which 3 are new?
3. What is select_biases' signature? What does it return?
4. Walk through the 6-line consumption model: filter → rank → scope → budget → inject → never read meaning.
5. How does label matching work? What set operation? What if artifact has domain=["system","config"] and turn has domain="system"?
6. What happens when turn_labels is empty (pre-H-31B)? What artifacts get selected?
7. Where in handle_turn does signal extraction happen? Where does bias selection happen?
8. How many tests total? Split between bias_selector.py and integration tests.
9. What is ho3_bias_budget? Where does it come from? What does it limit?
10. How are context_lines injected into assembled_context? Are they interpreted by HO2?

**Adversarial:**
11. outcome:success fires every successful turn. That's ~50 signals per session at turn_limit=50. Is the gate threshold (5 count, 3 sessions) meaningful for outcome signals?
12. If select_biases returns 0 artifacts, what does assembled_context look like? Does the synthesize prompt break?
13. bias_selector.py imports from ho2_supervisor — or does it? What are its dependencies?

STOP AFTER ANSWERING.
```

### Expected Answers

1. PKG-HO2-SUPERVISOR-001. CREATE: `HO2/kernel/bias_selector.py`, `HO2/tests/test_bias_selector.py`. MODIFY: `HO2/kernel/ho2_supervisor.py`, `HO2/tests/test_ho2_supervisor.py`, `manifest.json`.
2. intent:<speech_act>, tool:<tool_id>, domain:<domain_label>, task:<task_label>, outcome:<success|failed|unknown>. New: domain, task, outcome.
3. `select_biases(artifacts, turn_labels, ho3_bias_budget, as_of_ts) -> list[dict]`. Returns filtered, ranked, budget-constrained list of artifact dicts.
4. (1) Filter: enabled=true, not expired. (2) Rank: weight × decay × recency, descending. (3) Scope: artifact.labels ∩ turn_labels ≠ empty OR scope=global. (4) Budget: top-k fitting within ho3_bias_budget tokens. (5) Inject: context_lines copied verbatim into assembled_context. (6) HO2 never reads the content for meaning.
5. Set intersection. artifact.labels.domain ∩ {turn.labels.domain} ≠ empty. With domain=["system","config"] and turn domain="system", intersection is {"system"} which is non-empty → match.
6. Only global-scope artifacts are selected. Old-format biases without labels are included if no label filtering is active. After H-31B deploys, label matching activates naturally.
7. Signal extraction: post-turn (lines 307-334). Bias selection: Step 2b+ (lines 191-201).
8. 18 total: 12 for bias_selector.py, 6 for integration.
9. ho3_bias_budget (default 2000 tokens, from admin_config.json). Limits the total token estimate of injected context_lines. Top-k artifacts that fit within this budget are selected.
10. context_lines = [a.get("context_line", ...) for a in selected]. Injected into assembled_context["ho3_biases"] as a list of strings. HO2 does NOT interpret them — they're opaque text written by the LLM at consolidation time, passed through to the synthesize prompt.
11. Yes, outcome:success will accumulate very fast. The gate would cross after just 1-2 sessions. This is by design for MVP — it produces an artifact like "User interactions typically succeed" which has low value but also low weight. In practice, the more interesting signals are domain and task combinations. A future refinement could exclude "outcome:success" from gate eligibility or increase the threshold for outcome signals specifically. Not a blocker for MVP.
12. assembled_context has no "ho3_biases" key (or empty list). The synthesize prompt template (PRM-SYNTHESIZE-001.txt) uses {{assembled_context}} which just doesn't contain ho3_biases. The LLM gets slightly less context but functions normally. No crash.
13. bias_selector.py has NO imports from ho2_supervisor or any Control Plane module. It's a pure function module — stdlib only (datetime, dataclasses, typing). This is intentional: it can be tested in isolation without any system dependencies.
