# BUILDER_HANDOFF_29.1A: Structured Artifact Model + Replay-Safe Decay

## 1. Mission

Close gaps 1-4 of H-29 in HO3Memory: (1) replace free-form bias prose with a structured artifact schema, (2) make time-dependent computations replay-safe via `as_of_ts`, (3) add overlay lifecycle operations (deactivate, weight update, expiry), and (4) add idempotency via artifact_id deduplication. Modifies **PKG-HO3-MEMORY-001** only.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**.
2. **DTT: Design → Test → Then implement.**
3. **Package everything.** Use `compute_sha256()` and `pack()`.
4. **End-to-end verification.** Clean-room install → all gates pass.
5. **Tar archive format:** `tar czf ... -C dir $(ls dir)`.
6. **Results file.** `_staging/handoffs/RESULTS_HANDOFF_29_1A.md`.
7. **Full regression.** ALL staged tests. New failures are blockers.
8. **Baseline:** 22 packages, 693 installed tests, 8/8 gates.
9. **Scope:** PKG-HO3-MEMORY-001 ONLY.
10. **Backward compatible.** Existing overlays (free-form bias) must still be readable. New structured fields are optional on read but mandatory on write.
11. **Append-only invariant.** Deactivation and weight updates are NEW events, not mutations. The overlay ledger stays immutable.

## 3. Architecture / Design

### Gap 1: Structured Artifact Model

**Current overlay shape (unstructured):**
```json
{
  "overlay_id": "OVL-abc12345",
  "signal_id": "intent:tool_query",
  "salience_weight": 0.6,
  "decay_modifier": 0.95,
  "source_event_ids": ["EVT-001", "EVT-025"],
  "content": {"bias": "User prefers tool queries", "category": "tool_preference"},
  "window_start": "...",
  "window_end": "..."
}
```

**New structured artifact shape:**
```json
{
  "overlay_id": "OVL-abc12345",
  "artifact_id": "ART-<deterministic hash>",
  "signal_id": "intent:tool_query",
  "artifact_type": "topic_affinity",
  "labels": {"domain": ["system"], "task": ["inspect"]},
  "weight": 0.7,
  "scope": "agent",
  "context_line": "User frequently explores package structure and manifest contents",
  "enabled": true,
  "expires_at_event_ts": null,
  "source_signal_ids": ["domain:system", "tool:read_file"],
  "source_event_ids": ["EVT-001", "EVT-025", "EVT-040"],
  "gate_snapshot": {"count": 12, "sessions": 3},
  "model": "claude-sonnet-4-20250514",
  "prompt_pack_version": "PRM-CONSOLIDATE-001",
  "consolidation_event_ts": "2026-02-18T...",
  "salience_weight": 0.7,
  "decay_modifier": 0.95,
  "content": {"bias": "User frequently explores package structure", "category": "topic_affinity"},
  "window_start": "...",
  "window_end": "...",
  "created_at": "..."
}
```

**Artifact types** (closed vocabulary): `topic_affinity`, `interaction_style`, `task_pattern`, `constraint`.

**Backward compatibility:** `read_active_biases()` reads both old and new format. Old overlays lack `artifact_id`, `labels`, `context_line` — these default to None/empty. New overlays have all fields. The consumption model (H-29.1C) will filter on labels, so old overlays without labels are excluded from label matching but still returned if scope=global.

### Gap 2: Event-Time Decay (as_of_ts)

**Current (non-deterministic):**
```python
def read_signals(self, signal_id=None, min_count=0):
    now = datetime.now(timezone.utc)  # Wall clock — breaks replay
    ...
    hours_since = (now - last_dt).total_seconds() / 3600.0
```

**New (replay-safe):**
```python
def read_signals(self, signal_id=None, min_count=0, as_of_ts=None):
    now = datetime.fromisoformat(as_of_ts) if as_of_ts else datetime.now(timezone.utc)
    ...
```

Same pattern for `read_active_biases(as_of_ts=None)` and `_is_consolidated(signal_id, as_of_ts=None)`.

If `as_of_ts` is None, falls back to wall clock (backward compatible). HO2 passes the current turn's event timestamp for deterministic replay.

### Gap 3: Overlay Lifecycle

Two new methods on HO3Memory, both append-only:

```python
def deactivate_overlay(self, artifact_id: str, reason: str, event_ts: str) -> str:
    """Append OVERLAY_DEACTIVATED event. Sets enabled=false for this artifact_id."""

def update_overlay_weight(self, artifact_id: str, new_weight: float, reason: str, event_ts: str) -> str:
    """Append OVERLAY_WEIGHT_UPDATED event. Latest weight wins on read."""
```

New event types in overlays.jsonl:
- `HO3_OVERLAY_DEACTIVATED { artifact_id, reason, event_ts }`
- `HO3_OVERLAY_WEIGHT_UPDATED { artifact_id, new_weight, reason, event_ts }`

`read_active_biases(as_of_ts)` changes:
1. Scan overlays.jsonl for all HO3_OVERLAY entries
2. For each artifact_id, find latest lifecycle event (OVERLAY, DEACTIVATED, WEIGHT_UPDATED)
3. If latest is DEACTIVATED → skip (enabled=false)
4. If WEIGHT_UPDATED exists → use latest weight
5. If expires_at_event_ts is set and `as_of_ts > expires_at_event_ts` → skip (expired)
6. Return remaining with salience > 0

### Gap 4: Idempotency

`artifact_id` is deterministic:
```python
artifact_id = "ART-" + sha256(
    sorted(source_signal_ids) + "|" + gate_window_key + "|" + model + "|" + prompt_pack_version
).hexdigest()[:12]
```

Before `log_overlay()` writes a new overlay, check if an overlay with this `artifact_id` already exists. If so:
- If existing is active → skip (duplicate, return existing overlay_id)
- If existing is deactivated → re-activate with new weight (append WEIGHT_UPDATED event)

New helper: `_find_overlay_by_artifact_id(artifact_id) -> Optional[Dict]`

### Adversarial Analysis: Legacy Overlay Migration

**Hurdles**: Old overlays lack `artifact_id`. They can't be deactivated or deduplicated.
**Not Enough**: Ignoring them means they accumulate forever.
**Too Much**: Migrating in-place violates append-only invariant.
**Synthesis**: Old overlays are returned by `read_active_biases()` with `artifact_id=None`. They cannot be deactivated (no ID to target). The consumption model (H-29.1C) will exclude them from label matching (no labels) but include them if scope is unset (backward compatible). Eventually, their decay reduces salience below threshold and they stop being injected. No migration needed.

## 4. Implementation Steps

### Step 1: Add as_of_ts parameter to read methods

Modify `read_signals()`, `read_active_biases()`, `_is_consolidated()` to accept `as_of_ts: Optional[str] = None`. When provided, use it instead of `datetime.now()`.

### Step 2: Add structured artifact fields to log_overlay

Extend `log_overlay()` to accept and store new fields: `artifact_id`, `artifact_type`, `labels`, `weight`, `scope`, `context_line`, `enabled`, `expires_at_event_ts`, `source_signal_ids`, `gate_snapshot`, `model`, `prompt_pack_version`, `consolidation_event_ts`.

### Step 3: Add idempotency check

Add `_find_overlay_by_artifact_id(artifact_id)`. Call it in `log_overlay()` before writing.

### Step 4: Add lifecycle methods

Add `deactivate_overlay()` and `update_overlay_weight()`. These write new event types.

### Step 5: Update read_active_biases

Apply lifecycle resolution: latest event per artifact_id wins. Filter out deactivated and expired.

### Step 6: Add artifact_id computation helper

`compute_artifact_id(source_signal_ids, gate_window_key, model, prompt_pack_version) -> str`

### Step 7: Update manifest and governance cycle

Update hashes, rebuild archives, clean-room install, gates.

## 5. Package Plan

### PKG-HO3-MEMORY-001 (modified)

| Field | Value |
|-------|-------|
| Package ID | PKG-HO3-MEMORY-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HOT/kernel/ho3_memory.py` — all 4 gaps implemented
- `HOT/tests/test_ho3_memory.py` — new tests
- `manifest.json` — hash updates

## 6. Test Plan

### New tests (18)

| Test | Description | Expected |
|------|-------------|----------|
| `test_as_of_ts_deterministic_decay` | Same as_of_ts → same decay across runs | Identical decay values |
| `test_as_of_ts_none_uses_wall_clock` | as_of_ts=None → uses datetime.now() | Backward compatible |
| `test_as_of_ts_in_read_active_biases` | Biases filtered by as_of_ts | Expired excluded |
| `test_as_of_ts_in_is_consolidated` | Consolidated check uses as_of_ts | Deterministic gate |
| `test_structured_artifact_all_fields` | log_overlay with all structured fields | All fields stored |
| `test_structured_artifact_backward_read` | Old overlay still readable | Legacy format works |
| `test_artifact_type_stored` | artifact_type in overlay | Value persisted |
| `test_labels_stored` | labels dict in overlay | Labels persisted |
| `test_context_line_stored` | context_line in overlay | Text persisted |
| `test_deactivate_overlay` | Deactivate → not returned by read_active_biases | Excluded |
| `test_deactivate_nonexistent_raises` | Deactivate unknown artifact_id → ValueError | Error |
| `test_update_weight` | Update weight → latest weight returned | New weight |
| `test_expiry_filter` | Expired artifact excluded by as_of_ts | Excluded |
| `test_expiry_not_expired` | Non-expired artifact still returned | Included |
| `test_idempotency_skip_duplicate` | Same artifact_id → no duplicate | Single overlay |
| `test_idempotency_reactivate` | Same artifact_id after deactivate → weight update | Re-activated |
| `test_compute_artifact_id_deterministic` | Same inputs → same ID | Identical hash |
| `test_lifecycle_resolution_latest_wins` | Multiple events → last event determines state | Latest wins |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| ho3_memory.py | `_staging/PKG-HO3-MEMORY-001/HOT/kernel/ho3_memory.py` | File to modify |
| read_signals() | `ho3_memory.py:226-303` | Add as_of_ts |
| read_active_biases() | `ho3_memory.py:330-339` | Add lifecycle resolution |
| log_overlay() | `ho3_memory.py:169-220` | Add structured fields + idempotency |
| _is_consolidated() | `ho3_memory.py:412-444` | Add as_of_ts |
| test_ho3_memory.py | `_staging/PKG-HO3-MEMORY-001/HOT/tests/` | Test patterns |
| hashing.py | `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py` | For artifact_id hash |

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
| `ho3_memory.py` | `_staging/PKG-HO3-MEMORY-001/HOT/kernel/` | MODIFY |
| `test_ho3_memory.py` | `_staging/PKG-HO3-MEMORY-001/HOT/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO3-MEMORY-001/` | MODIFY |
| `PKG-HO3-MEMORY-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_29_1A.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Replay-safe.** All time-dependent computations accept `as_of_ts`. Same inputs → same output.
2. **Append-only.** Deactivation and weight updates are new events, not mutations. Ledger stays immutable.
3. **Backward compatible.** Old overlays still readable. New fields optional on read, mandatory on write.
4. **Deterministic IDs.** `artifact_id` computed from inputs — same consolidation produces same ID.
5. **Latest event wins.** Lifecycle resolved by scanning all events per artifact_id, last determines state.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project.

**Agent: HANDOFF-29.1A** — Structured artifacts + replay-safe decay (PKG-HO3-MEMORY-001)

Read: `Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_29_1A_structured_artifacts.md`

**Rules:** 1. _staging/ only. 2. DTT. 3. compute_sha256()+pack(). 4. sha256:<64hex>. 5. Clean-room. 6. Full regression. 7. Results file. 8. CP_BOOTSTRAP rebuild. 9. PKG-HO3-MEMORY-001 ONLY.

**10 Questions:**

1. What package? What file do you modify? What new methods do you add?
2. What 4 gaps does this handoff close? Name each.
3. What is the as_of_ts parameter? What happens if it's None?
4. Show the structured artifact fields that replace the free-form bias. Which does HO2 read for consumption?
5. What 4 artifact_type values are in the closed vocabulary?
6. How does deactivate_overlay work? Does it mutate the existing overlay entry?
7. How is artifact_id computed? Why is it deterministic?
8. What happens when log_overlay is called with an artifact_id that already exists and is active?
9. How many new tests? Name them.
10. What event types does overlays.jsonl now support (old + new)?

**Adversarial:**
11. Old overlays have no artifact_id. Can they be deactivated? What happens to them over time?
12. If as_of_ts is in the future (beyond all events), what does decay compute to?
13. _find_overlay_by_artifact_id scans ALL overlays every time. Performance concern?

STOP AFTER ANSWERING.
```

### Expected Answers

1. PKG-HO3-MEMORY-001. Modify `HOT/kernel/ho3_memory.py`. Add: `deactivate_overlay()`, `update_overlay_weight()`, `compute_artifact_id()`, `_find_overlay_by_artifact_id()`.
2. (1) Structured artifact model, (2) event-time decay via as_of_ts, (3) overlay lifecycle (deactivate/weight update/expiry), (4) idempotency via artifact_id dedup.
3. Optional timestamp parameter on read_signals, read_active_biases, _is_consolidated. If None, falls back to datetime.now(timezone.utc) for backward compatibility. If provided, uses that timestamp for deterministic decay computation — enables replay.
4. artifact_type, labels, weight, scope, context_line, enabled, expires_at_event_ts. HO2 reads: artifact_type, labels, weight, scope, enabled, expires_at_event_ts, context_line. context_line is passed through verbatim (HO2 never reads meaning).
5. topic_affinity, interaction_style, task_pattern, constraint.
6. Appends an HO3_OVERLAY_DEACTIVATED event with artifact_id and reason. Does NOT mutate the original overlay. The overlay ledger is append-only. read_active_biases resolves lifecycle: if latest event for an artifact_id is DEACTIVATED, it's excluded.
7. artifact_id = "ART-" + sha256(sorted source_signal_ids + gate_window_key + model + prompt_pack_version)[:12]. Deterministic because same consolidation inputs → same hash. Prevents duplicate overlays for the same signal pattern.
8. Skip — return existing overlay_id. No duplicate created. If existing is deactivated, re-activate via WEIGHT_UPDATED event.
9. 18 tests (list all).
10. Original: HO3_OVERLAY (consolidation result). New: HO3_OVERLAY_DEACTIVATED (lifecycle), HO3_OVERLAY_WEIGHT_UPDATED (weight change).
11. No, they cannot be deactivated (no artifact_id to target). Over time, their decay reduces salience below threshold (half-life 14 days). They eventually stop being returned by read_active_biases. No migration needed.
12. Decay approaches 0. With half_life=336 hours, as_of_ts 30 days in the future would give decay ≈ 0.25. Very far future → decay ≈ 0. The signal would be excluded from results naturally.
13. For MVP (ADMIN), overlay count is small (10-50 overlays). Scanning is negligible. For scale, could add an in-memory index keyed by artifact_id. Not needed now — YAGNI.
