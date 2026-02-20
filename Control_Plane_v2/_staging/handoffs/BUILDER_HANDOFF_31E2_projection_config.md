# BUILDER_HANDOFF_31E-2: Projection Budget Config

## 1. Mission

Add `projection_budget` and `projection_mode` to admin_config.json and wire them through to HO2Config in main.py. Modifies **PKG-ADMIN-001** only.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**.
2. **DTT: Design → Test → Then implement.**
3. **Package everything.** Use `compute_sha256()` and `pack()`.
4. **End-to-end verification.** Clean-room install → all gates pass.
5. **Tar archive format:** `tar czf ... -C dir $(ls dir)`.
6. **Results file.** `_staging/handoffs/RESULTS_HANDOFF_31E2.md`.
7. **Full regression.** ALL staged tests. New failures are blockers.
8. **Baseline:** 22 packages, 693 installed tests, 8/8 gates.
9. **Scope:** PKG-ADMIN-001 ONLY. Do NOT modify PKG-HO2-SUPERVISOR-001.
10. **Config is source of truth.** No hardcoded defaults in main.py that silently diverge from config.

## 3. Architecture / Design

### Changes to admin_config.json

Add to the `budget` section:

```json
"budget": {
    "session_token_limit": 200000,
    "classify_budget": 2000,
    "synthesize_budget": 100000,
    "projection_budget": 10000,
    "consolidation_budget": 4000,
    "ho3_bias_budget": 2000,
    "followup_min_remaining": 500,
    "budget_mode": "warn",
    "turn_limit": 50,
    "timeout_seconds": 7200
}
```

Add `projection_mode` to the `ho3` section (or a new `projection` section):

```json
"projection": {
    "mode": "shadow",
    "intent_header_budget": 500,
    "wo_status_budget": 2000
}
```

### Changes to main.py (build_session_host_v2)

Wire new config values to HO2Config:

```python
# In build_session_host_v2(), where HO2Config is constructed:
ho2_config = HO2Config(
    ...
    projection_budget=budget_config.get("projection_budget", 10000),
    projection_mode=projection_config.get("mode", "shadow"),
    ...
)
```

### Changes to admin_config.schema.json

Add `projection_budget` to budget properties. Add `projection` section to schema.

### What This Does NOT Do

- Does NOT modify HO2Config dataclass (that's in PKG-HO2-SUPERVISOR-001, done by H-31E-1)
- Does NOT create ContextProjector (that's H-31E-1)
- Only wires config values from admin_config.json to where main.py constructs HO2Config

### Adversarial Analysis: Config Forward Reference

**Hurdles**: H-31E-2 adds config fields that H-31E-1 consumes. If H-31E-2 deploys before H-31E-1, the config values exist but nobody reads them.
**Not Enough**: Silently dropping unknown config fields means no validation.
**Too Much**: Making HO2Config fail on unknown fields breaks deployment order flexibility.
**Synthesis**: Config fields are additive. main.py reads them with `.get(key, default)`. If H-31E-2 deploys first, the values are in config but main.py passes defaults to HO2Config (which doesn't have the fields yet). When H-31E-1 deploys, HO2Config gains the fields and main.py's .get() calls start providing real values. No ordering problem.

## 4. Implementation Steps

### Step 1: Add projection_budget to admin_config.json budget section

Add the new key with value 10000.

### Step 2: Add projection section to admin_config.json

New section with mode, intent_header_budget, wo_status_budget.

### Step 3: Update admin_config.schema.json

Add projection_budget to budget properties. Add projection section.

### Step 4: Wire in main.py

In `build_session_host_v2()`, read projection config and pass to HO2Config constructor.

### Step 5: Write tests

Verify config values are read and passed through.

### Step 6: Governance cycle

Update manifest, rebuild archives, clean-room install, gates.

## 5. Package Plan

### PKG-ADMIN-001 (modified)

| Field | Value |
|-------|-------|
| Package ID | PKG-ADMIN-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HOT/config/admin_config.json` — new budget + projection fields
- `HOT/schemas/admin_config.schema.json` — schema update
- `HOT/admin/main.py` — wire projection config to HO2Config
- `HOT/tests/test_admin.py` — new tests
- `manifest.json` — hash updates

## 6. Test Plan

### New tests (6)

| Test | Description | Expected |
|------|-------------|----------|
| `test_projection_budget_in_config` | admin_config.json has projection_budget=10000 | Value present |
| `test_projection_mode_in_config` | admin_config.json has projection.mode="shadow" | Value present |
| `test_projection_budget_wired_to_ho2config` | build_session_host_v2 passes projection_budget | HO2Config gets value |
| `test_projection_mode_wired_to_ho2config` | build_session_host_v2 passes projection_mode | HO2Config gets value |
| `test_projection_config_optional` | Missing projection section → defaults work | No crash |
| `test_budget_section_complete` | All 10 budget keys present after this handoff | All keys present |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| admin_config.json | `_staging/PKG-ADMIN-001/HOT/config/admin_config.json` | File to modify |
| admin_config.schema.json | `_staging/PKG-ADMIN-001/HOT/schemas/admin_config.schema.json` | Schema to update |
| main.py | `_staging/PKG-ADMIN-001/HOT/admin/main.py` | Wiring code |
| build_session_host_v2 | `main.py:1122` | Where HO2Config is constructed |
| HO2Config | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py:57-84` | Fields to wire |

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
| `admin_config.json` | `_staging/PKG-ADMIN-001/HOT/config/` | MODIFY |
| `admin_config.schema.json` | `_staging/PKG-ADMIN-001/HOT/schemas/` | MODIFY |
| `main.py` | `_staging/PKG-ADMIN-001/HOT/admin/` | MODIFY |
| `test_admin.py` | `_staging/PKG-ADMIN-001/HOT/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-ADMIN-001/` | MODIFY |
| `PKG-ADMIN-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_31E2.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Config is source of truth.** All budget values in admin_config.json.
2. **Additive config.** New fields don't break existing behavior. `.get(key, default)` pattern.
3. **Deployment order flexible.** H-31E-2 can deploy before or after H-31E-1. Values are ignored until HO2Config gains the fields.
4. **Complete budget section.** After this handoff, all 10 budget keys are in one place.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project.

**Agent: HANDOFF-31E-2** — Projection budget config (PKG-ADMIN-001)

Read: `Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_31E2_projection_config.md`

**Rules:** 1. _staging/ only. 2. DTT. 3. compute_sha256()+pack(). 4. sha256:<64hex>. 5. Clean-room. 6. Full regression. 7. Results file. 8. CP_BOOTSTRAP rebuild. 9. PKG-ADMIN-001 ONLY.

**10 Questions:**

1. What package? What 3 files do you modify?
2. What new budget key is added? What is its value?
3. What new config section is added? What fields does it contain?
4. Where in main.py do you wire the new config values? What function?
5. What happens if the projection section is missing from config?
6. After this handoff, list ALL budget keys in admin_config.json (should be 10).
7. Does this handoff modify HO2Config? Why or why not?
8. How many new tests? Name them.
9. What tar format and hash format do you use?
10. Can H-31E-2 deploy before H-31E-1? What happens to the config values?

**Adversarial:**
11. If projection_budget is set to 100000 (same as synthesize_budget), what's the risk?
12. The schema update — is projection_budget required or optional? Why?
13. intent_header_budget and wo_status_budget are sub-budgets of projection_budget. Should they sum to <= projection_budget?

STOP AFTER ANSWERING.
```

### Expected Answers

1. PKG-ADMIN-001. admin_config.json, admin_config.schema.json, main.py. Also test_admin.py and manifest.json.
2. projection_budget = 10000.
3. `projection` section with: mode ("shadow"), intent_header_budget (500), wo_status_budget (2000).
4. In `build_session_host_v2()` (main.py:1122). Reads budget_config.get("projection_budget", 10000) and projection config, passes to HO2Config constructor.
5. main.py uses .get() with defaults. projection_mode defaults to "shadow", projection_budget defaults to 10000. No crash.
6. session_token_limit, classify_budget, synthesize_budget, projection_budget, consolidation_budget, ho3_bias_budget, followup_min_remaining, budget_mode, turn_limit, timeout_seconds.
7. No. HO2Config is in PKG-HO2-SUPERVISOR-001, which is out of scope. H-31E-1 adds the fields to HO2Config. This handoff only adds config values and wiring in main.py.
8. 6 tests (list all).
9. pack() for archives, sha256:<64hex> for manifests.
10. Yes. Config values exist but main.py passes them with .get(key, default). If HO2Config doesn't have the fields yet (H-31E-1 not deployed), the values are read from config but passed as kwargs that HO2Config's __init__ ignores or defaults. No crash, no effect until H-31E-1 deploys.
11. Risk: projection could consume as many tokens as a full synthesize call. The projection is meant to be a small structured summary, not a full response. 100000 would allow the projection to grow very large, wasting context window. The 10000 default is intentional — enough for structured sections, not enough to dominate the prompt.
12. Optional. Adding it to required would break backward compatibility with configs that don't have it. The .get(key, default) pattern handles absence gracefully.
13. Yes, ideally intent_header_budget (500) + wo_status_budget (2000) + ho3_budget (2000) = 4500 <= projection_budget (10000). The remaining 5500 is headroom for content overflow and additional sections. The sub-budgets are soft limits — the projector truncates to projection_budget regardless.
