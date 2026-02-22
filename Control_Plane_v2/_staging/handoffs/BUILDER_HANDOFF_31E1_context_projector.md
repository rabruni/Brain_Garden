# BUILDER_HANDOFF_31E-1: Replace Attention with Context Projector

## 1. Mission

Replace the current attention.py (dumb-pipe raw JSON dump) with context_projector.py — a structured projection engine that assembles context from liveness state + HO3 learning artifacts, under budget. Starts in shadow mode (run both old and new, log divergences), then swaps to enforcement mode. Modifies **PKG-HO2-SUPERVISOR-001** only.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**.
2. **DTT: Design → Test → Then implement.**
3. **Package everything.** Use `compute_sha256()` and `pack()`.
4. **End-to-end verification.** Clean-room install → all gates pass.
5. **Tar archive format:** `tar czf ... -C dir $(ls dir)`.
6. **Results file.** `_staging/handoffs/RESULTS_HANDOFF_31E1.md`.
7. **Full regression.** ALL staged tests. New failures are blockers.
8. **Baseline:** 22 packages, 693 installed tests, 8/8 gates.
9. **Scope:** PKG-HO2-SUPERVISOR-001 ONLY.
10. **Output shape preserved.** The assembled_context dict shape (`user_input`, `classification`, `assembled_context.{context_text, context_hash, fragment_count, tokens_used}`) must not change. Only the CONTENT of context_text changes.
11. **Shadow mode first.** Initial deployment runs both old attention and new projection. Logs both. Uses old output. Config flag `projection_mode: "shadow" | "enforce"` controls which output is used.

## 3. Architecture / Design

### Current Attention System (to be replaced)

`attention.py` provides:
- `horizontal_scan(session_id)` → reads raw ho2m + ho1m entries
- `priority_probe()` → returns empty (HO3m not populated)
- `assemble_wo_context(horizontal, priority, user_message, classification)` → JSON-dumps raw entries

**Problems:**
1. Dumps raw serialized ledger entries — LLM sees JSON noise, not structured context
2. No awareness of intent lifecycle, liveness state, or learning artifacts
3. No budget control beyond a token counter
4. No integration with HO3 learning

### New Context Projector

**New file: `HO2/kernel/context_projector.py`**

```python
@dataclass
class ProjectionConfig:
    projection_budget: int = 10000    # from admin_config
    projection_mode: str = "shadow"   # "shadow" or "enforce"
    intent_header_budget: int = 500   # tokens for intent section
    wo_status_budget: int = 2000      # tokens for WO section
    ho3_budget: int = 2000            # from ho3_bias_budget

class ContextProjector:
    def __init__(self, config: ProjectionConfig):
        self._config = config

    def project(
        self,
        liveness: LivenessState,      # from H-31D
        ho3_artifacts: list[dict],     # from select_biases (H-29.1C)
        user_message: str,
        classification: dict,
        session_id: str,
    ) -> dict:
        """Build structured projection under budget.

        Returns dict with same shape as old assemble_wo_context:
        {
            "user_input": user_message,
            "classification": classification,
            "assembled_context": {
                "context_text": structured_text,
                "context_hash": sha256_hash,
                "fragment_count": N,
                "tokens_used": N,
            },
        }
        """
```

### Projection Content Structure

The `context_text` field contains structured sections instead of raw JSON:

```
## Active Intent
Objective: Explore installed packages
Status: LIVE | Declared: 2026-02-18T10:30:00Z

## Open Work Orders
- WO-abc123 (synthesize): DISPATCHED
- WO-def456 (classify): COMPLETED

## Failed Items
(none)

## Learning Context
- User frequently inspects package manifests and governance gates
- User prefers concise, structured responses
```

Each section has a sub-budget. Sections are assembled in priority order:
1. Active intent header (highest priority — defines "what are we doing")
2. Failed items (high priority — things that went wrong)
3. Open WOs (medium priority — what's in flight)
4. HO3 learning artifacts (fills remaining budget with context_lines)

### Shadow Mode

When `projection_mode = "shadow"`:
```python
# In ho2_supervisor.py handle_turn, at Step 2b:
old_context = self._attention.assemble_wo_context(horizontal, priority, user_message, classification)
new_context = self._projector.project(liveness, ho3_artifacts, user_message, classification, session_id)

# Log both for comparison
self._log_shadow_comparison(old_context, new_context, session_id)

# Use OLD context for actual synthesize WO
assembled_context = old_context
```

When `projection_mode = "enforce"`:
```python
# Use NEW context
assembled_context = new_context
# Still log for monitoring
```

### Integration in ho2_supervisor.py

Replace the 3-call attention sequence (lines 188-199) with:

```python
# Step 2b: Context projection
if self._projector and self._config.projection_mode == "enforce":
    assembled_context = self._projector.project(
        liveness, ho3_artifacts, user_message, classification, session_id
    )
elif self._projector and self._config.projection_mode == "shadow":
    # Run both, log comparison, use old
    old_context = self._attention.assemble_wo_context(...)
    new_context = self._projector.project(...)
    self._log_shadow_comparison(old_context, new_context, session_id)
    assembled_context = old_context
else:
    # Fallback: old attention only
    horizontal = self._attention.horizontal_scan(session_id)
    priority = self._attention.priority_probe()
    assembled_context = self._attention.assemble_wo_context(
        horizontal, priority, user_message, classification
    )
```

### What Does NOT Change

- attention.py stays in the package (not removed until shadow mode validates)
- PRM-SYNTHESIZE-001.txt template unchanged (same {{assembled_context}} variable)
- HO1 executor unchanged
- Output shape of assembled_context dict unchanged

### Adversarial Analysis: Output Quality

**Hurdles**: Changing what the LLM sees could degrade response quality.
**Not Enough**: Just logging shadow comparisons without validation criteria.
**Too Much**: A/B testing framework with statistical significance.
**Synthesis**: Shadow mode logs both outputs. The PROJECTION_COMPUTED overlay (H-31D) captures what the projection contained. After N sessions, compare quality gate pass rates between old and new contexts. If new passes at same or better rate, promote to enforce. Manual review of divergences before promotion.

## 4. Implementation Steps

### Step 1: Create context_projector.py

New file with `ProjectionConfig`, `ContextProjector`, and `project()` method.

### Step 2: Add projection_mode to HO2Config

Add `projection_mode: str = "shadow"` field. This will be wired from admin_config by H-31E-2.

### Step 3: Integrate in ho2_supervisor.py

Replace Step 2b attention calls with conditional projection/shadow/fallback logic. Initialize ContextProjector in constructor.

### Step 4: Add shadow comparison logging

New helper `_log_shadow_comparison(old, new, session_id)` that writes to ho2m.jsonl.

### Step 5: Write tests

Tests for context_projector.py and integration.

### Step 6: Governance cycle

Update manifest (add context_projector.py, keep attention.py), rebuild archives, gates.

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
- `HO2/kernel/context_projector.py` — projection engine

Modified assets:
- `HO2/kernel/ho2_supervisor.py` — projection integration
- `HO2/tests/test_ho2_supervisor.py` — integration tests
- `manifest.json` — new asset + hash updates

Retained assets:
- `HO2/kernel/attention.py` — kept for shadow mode fallback

New test file:
- `HO2/tests/test_context_projector.py` — projection tests

## 6. Test Plan

### context_projector.py tests (12)

| Test | Description | Expected |
|------|-------------|----------|
| `test_output_shape_matches_old` | project() returns same dict shape as assemble_wo_context | Keys match |
| `test_context_text_has_sections` | context_text contains ## headers | Sections present |
| `test_active_intent_in_projection` | LivenessState with 1 active intent → in context | Intent header present |
| `test_failed_items_high_priority` | Failed WOs appear before open WOs | Correct order |
| `test_open_wos_in_projection` | Open WOs appear in projection | WO section present |
| `test_ho3_artifacts_injected` | context_lines from artifacts in context_text | Lines present |
| `test_budget_respected` | Total tokens <= projection_budget | Under budget |
| `test_empty_liveness` | No intents, no WOs → minimal projection | Still valid output |
| `test_budget_overflow_truncates` | Too much content → truncated to budget | Exactly at budget |
| `test_classification_preserved` | classification dict passed through | In output |
| `test_user_input_preserved` | user_message in output | In output |
| `test_deterministic` | Same inputs → same output | Identical |

### Integration tests (6)

| Test | Description | Expected |
|------|-------------|----------|
| `test_shadow_mode_uses_old_context` | projection_mode=shadow → old context used for synthesize | Old context in WO |
| `test_shadow_mode_logs_comparison` | Shadow mode → comparison logged to ho2m | Event logged |
| `test_enforce_mode_uses_new_context` | projection_mode=enforce → new context used | New context in WO |
| `test_fallback_no_projector` | No projector → old attention used | Fallback works |
| `test_projection_after_liveness` | Liveness computed before projection | Correct ordering |
| `test_synthesize_output_shape_unchanged` | End-to-end: synthesize WO gets correct shape | No shape change |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| attention.py | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/attention.py` | Code being replaced |
| assemble_wo_context | `attention.py:238-270` | Output shape to match |
| ho2_supervisor.py | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py` | Integration point |
| Step 2b attention | `ho2_supervisor.py:187-201` | Lines to replace |
| liveness.py (H-31D) | `HO2/kernel/liveness.py` | LivenessState input |
| bias_selector.py (29.1C) | `HO2/kernel/bias_selector.py` | HO3 artifacts input |

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
| `context_projector.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | CREATE |
| `ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | MODIFY |
| `test_context_projector.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/` | CREATE |
| `test_ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO2-SUPERVISOR-001/` | MODIFY |
| `PKG-HO2-SUPERVISOR-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_31E1.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Structured over raw.** LLM sees sections (intent, WOs, learning) not serialized JSON.
2. **Shadow before enforce.** Validate new projection doesn't degrade quality before committing.
3. **Same output shape.** PRM-SYNTHESIZE-001.txt and HO1 don't change. Only content changes.
4. **Budget-partitioned.** Each section has a sub-budget. Priority ordering fills highest-value content first.
5. **Composable inputs.** Liveness (H-31D) + HO3 artifacts (H-29.1C) + classification → projection.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project.

**Agent: HANDOFF-31E-1** — Context projector replaces attention (PKG-HO2-SUPERVISOR-001)

Read: `Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_31E1_context_projector.md`

**Rules:** 1. _staging/ only. 2. DTT. 3. compute_sha256()+pack(). 4. sha256:<64hex>. 5. Clean-room. 6. Full regression. 7. Results file. 8. CP_BOOTSTRAP rebuild. 9. PKG-HO2-SUPERVISOR-001 ONLY.

**10 Questions:**

1. What package? What NEW file do you create? Does attention.py get DELETED?
2. What is the output shape of project()? How does it match assemble_wo_context?
3. What 4 sections appear in context_text? In what priority order?
4. What is shadow mode? What happens in shadow mode vs enforce mode?
5. What config field controls shadow/enforce? What is the default?
6. Where in handle_turn does the projection run? What 3 code paths exist (enforce/shadow/fallback)?
7. What inputs does project() take? Where does each come from?
8. How many tests total? Split between context_projector.py and integration.
9. What does _log_shadow_comparison write? Where?
10. Why doesn't PRM-SYNTHESIZE-001.txt need to change?

**Adversarial:**
11. In shadow mode, the old attention calls still happen. That means horizontal_scan still reads ho2m. Performance impact of doing both?
12. If liveness is None (H-31D not deployed), what does project() do?
13. After enforce mode is proven, how do you remove attention.py? What changes in manifest?

STOP AFTER ANSWERING.
```

### Expected Answers

1. PKG-HO2-SUPERVISOR-001. CREATE: `HO2/kernel/context_projector.py`, `HO2/tests/test_context_projector.py`. attention.py is NOT deleted — kept for shadow mode fallback. Will be removed in a future cleanup handoff after enforce mode is validated.
2. `{"user_input": str, "classification": dict, "assembled_context": {"context_text": str, "context_hash": str, "fragment_count": int, "tokens_used": int}}`. Same shape as assemble_wo_context output. Only context_text content changes.
3. (1) Active Intent header, (2) Failed Items, (3) Open Work Orders, (4) HO3 Learning Context. Priority: intent first (defines what we're doing), failures next (urgent), open WOs (in-flight), learning artifacts (fills remaining budget).
4. Shadow: run BOTH old attention and new projection. Log both. Use OLD output for actual synthesize WO. Enforce: run ONLY new projection. Use new output.
5. `projection_mode` on HO2Config. Default: `"shadow"`.
6. At Step 2b, after liveness reduction (H-31D) and bias selection (H-29.1C). Three paths: (1) enforce → use projection, (2) shadow → run both, log, use old, (3) fallback → no projector available, use old attention only.
7. liveness (from reduce_liveness, H-31D), ho3_artifacts (from select_biases, H-29.1C), user_message (from handle_turn parameter), classification (from classify WO result), session_id (from session manager).
8. 18 total: 12 for context_projector.py, 6 for integration.
9. Writes a SHADOW_COMPARISON event to ho2m.jsonl with old context hash, new context hash, old token count, new token count, session_id.
10. PRM-SYNTHESIZE-001.txt uses {{assembled_context}} variable. The assembled_context dict shape is preserved. The template doesn't care about the content of context_text — it renders whatever is there. Changing what's inside context_text doesn't require a template change.
11. In shadow mode, both horizontal_scan (reads ho2m/ho1m) and reduce_liveness (reads ho2m/ho1m) read the same ledgers. Double read. For ADMIN (50 turns, ~300 entries), this is <20ms total. Acceptable for validation period. When switching to enforce, the old attention calls are removed.
12. project() should handle liveness=None gracefully — produce a minimal projection with just user_input and classification, no intent/WO sections. The output is valid but less informative. This allows deployment before H-31D.
13. Remove attention.py from manifest.json assets. Remove the import from ho2_supervisor.py. Remove the shadow/fallback code paths, keeping only enforce. Delete attention.py file. Run governance cycle. This is a separate cleanup handoff.
