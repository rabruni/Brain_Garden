# CLEANUP-1: Remove PKG-FLOW-RUNNER-001

**Status**: NOT DISPATCHED
**Created**: 2026-02-12
**Supersedes**: HANDOFF-5 (Flow Runner — SUPERSEDED, absorbed by HO2 Supervisor + HO1 Executor)

---

## 1. Mission

Remove PKG-FLOW-RUNNER-001 and all its artifacts from `_staging/`. The Flow Runner was designed as a single-shot batch executor (HANDOFF-5) but has been **superseded** by the cognitive dispatch architecture: HO2 Supervisor orchestrates work orders, HO1 Executor executes them. The package was never shipped in CP_BOOTSTRAP.tar.gz and never installed in any deployment. This is a clean removal with no runtime impact.

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree.
2. **Delete only what is listed.** Do not delete process docs (handoffs/, architecture/) that mention Flow Runner historically — those are narrative references.
3. **Do not modify CP_BOOTSTRAP.tar.gz.** PKG-FLOW-RUNNER-001 was never in the bootstrap. No archive rebuild needed.
4. **Resolve FMWK-005 collision.** Both PKG-FLOW-RUNNER-001 and PKG-ADMIN-001 claim FMWK-005. ADMIN wins — its `FMWK-005_Admin/manifest.yaml` stays untouched. Deleting the Flow Runner package removes the competing `FMWK-005_Agent_Orchestration/manifest.yaml`.
5. **Results file.** When finished, write `_staging/handoffs/RESULTS_CLEANUP_1.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.
6. **Full regression test.** Run ALL staged package tests and report results. Confirm no new failures from the deletion.

---

## 3. Architecture / Design

### What Is Being Removed

PKG-FLOW-RUNNER-001 is a staged (never-shipped) package containing a 9-step single-shot agent executor. It was superseded on 2026-02-12 by the semantic architecture plan, which replaces it with:

| Flow Runner Concept | Replaced By | Package |
|---------------------|------------|---------|
| Work order execution | HO1 Executor | PKG-HO1-EXECUTOR-001 (planned, HANDOFF-14) |
| Orchestration/dispatch | HO2 Supervisor | PKG-HO2-SUPERVISOR-001 (planned, HANDOFF-15) |
| Budget enforcement | Per-WO constraints | FMWK-008 Work Order Protocol |
| Framework resolution | HO2 attention + context assembly | PKG-HO2-SUPERVISOR-001 |

### FMWK-005 Collision

| Claimant | Directory | Name | Disposition |
|----------|-----------|------|-------------|
| PKG-FLOW-RUNNER-001 | `HOT/FMWK-005_Agent_Orchestration/` | Agent Orchestration Framework | **DELETE** (goes with package) |
| PKG-ADMIN-001 | `HOT/FMWK-005_Admin/` | Admin Framework | **KEEP** (ADMIN's own framework) |

After cleanup, FMWK-005 belongs exclusively to ADMIN. No renumbering needed.

### What Is NOT Being Changed

- **Process docs** (18 files in handoffs/ and architecture/) — historical references to Flow Runner are narrative. They stay as-is.
- **PKG-ADMIN-001** — its FMWK-005 references are to its OWN framework (`FMWK-005_Admin`), not to Flow Runner's `FMWK-005_Agent_Orchestration`. No changes.
- **PKG-SESSION-HOST-001** — its test file references `framework_id="FMWK-005"` in test fixtures, which is ADMIN's framework ID. No changes.
- **CP_BOOTSTRAP.tar.gz** — PKG-FLOW-RUNNER-001 was never included. No rebuild.

---

## 4. Implementation Steps

### Step 1: Delete PKG-FLOW-RUNNER-001 directory

Delete the entire directory tree:

```
Control_Plane_v2/_staging/PKG-FLOW-RUNNER-001/
├── manifest.json
├── HOT/kernel/flow_runner.py
├── HOT/schemas/flow_runner_config.schema.json
├── HOT/FMWK-005_Agent_Orchestration/manifest.yaml
└── HOT/tests/test_flow_runner.py
```

Command: `rm -rf Control_Plane_v2/_staging/PKG-FLOW-RUNNER-001`

### Step 2: Update BUILDER_HANDOFF_STANDARD.md — Agent Registry

In `_staging/handoffs/BUILDER_HANDOFF_STANDARD.md`, update the agent registry table:

**Before:**
```
| HANDOFF-5 | PKG-FLOW-RUNNER-001 | ? | COMPLETE (unvalidated) | FOLLOWUP-3D, HANDOFF-4 | Missing |
```

**After:**
```
| HANDOFF-5 | PKG-FLOW-RUNNER-001 | — | SUPERSEDED (absorbed by HO2+HO1, CLEANUP-1) | — | — |
```

### Step 3: Update BUILDER_HANDOFF_STANDARD.md — Cross-Cutting Concerns

Update two rows that reference flow runner:

**Row "Tier privilege enforcement":**
- Before: `authz.py, package_install.py, flow runner`
- After: `authz.py, package_install.py, HO2 supervisor`

**Row "Framework auto-registration":**
- Before: `After flow runner is stable`
- After: `After HO2 supervisor is stable`

**Row "Dynamic tier provisioning":**
- Before: `flow runner, layout.json`
- After: `HO2 supervisor, layout.json`

### Step 4: Verify no dangling imports

Search all Python files in `_staging/PKG-*/` for import references to `flow_runner`:

```bash
grep -r "import.*flow_runner\|from.*flow_runner" Control_Plane_v2/_staging/PKG-*/
```

Expected: **No matches.** PKG-FLOW-RUNNER-001 was never a dependency of any shipped package. If matches are found, report them in the results file — do NOT fix them without explicit review.

### Step 5: Verify FMWK-005 is clean

After deletion, confirm only one FMWK-005 manifest exists:

```bash
grep -r "framework_id.*FMWK-005\|framework_id: FMWK-005" Control_Plane_v2/_staging/PKG-*/ | grep manifest
```

Expected: Only `PKG-ADMIN-001/HOT/FMWK-005_Admin/manifest.yaml` matches.

### Step 6: Run full regression test

```bash
CONTROL_PLANE_ROOT="$TMPDIR" python3 -m pytest Control_Plane_v2/_staging/ -v
```

Confirm no new failures. Pre-existing failures from unvalidated packages are noted but not blockers.

### Step 7: Write results file

Write `Control_Plane_v2/_staging/handoffs/RESULTS_CLEANUP_1.md` with all findings.

---

## 5. Package Plan

**N/A** — this is a removal, not a creation. No new packages.

---

## 6. Test Plan

No new tests. Validation is:

| Check | Method | Expected |
|-------|--------|----------|
| Directory deleted | `ls Control_Plane_v2/_staging/PKG-FLOW-RUNNER-001` | "No such file or directory" |
| No dangling imports | `grep -r "import.*flow_runner" _staging/PKG-*/` | No matches |
| Single FMWK-005 owner | `grep -r "framework_id.*FMWK-005" _staging/PKG-*/` in manifests | Only PKG-ADMIN-001 |
| Full regression passes | `pytest _staging/ -v` | No NEW failures |
| Handoff standard updated | Read BUILDER_HANDOFF_STANDARD.md | HANDOFF-5 = SUPERSEDED, flow runner refs updated |

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Flow Runner package | `_staging/PKG-FLOW-RUNNER-001/` | What you're deleting — verify contents match this spec |
| ADMIN framework | `_staging/PKG-ADMIN-001/HOT/FMWK-005_Admin/manifest.yaml` | The surviving FMWK-005 — do NOT touch |
| ADMIN config | `_staging/PKG-ADMIN-001/HOT/config/admin_config.json` | References FMWK-005 — this is ADMIN's, not Flow Runner's |
| Handoff standard | `_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` | Lines 297-300 (cross-cutting), line 314 (agent registry) |
| READING_ORDER.md | `_staging/READING_ORDER.md` | Already shows HANDOFF-5 as SUPERSEDED — no changes needed |
| ADMIN_DESIGN.md | `_staging/architecture/ADMIN_DESIGN.md` | Already documents Flow Runner as absorbed — no changes needed |

---

## 8. End-to-End Verification

```bash
# 1. Verify deletion
ls Control_Plane_v2/_staging/PKG-FLOW-RUNNER-001 2>&1
# Expected: ls: cannot access ... No such file or directory

# 2. Verify no dangling imports
grep -r "import.*flow_runner\|from.*flow_runner" Control_Plane_v2/_staging/PKG-*/ 2>&1
# Expected: no output (no matches)

# 3. Verify single FMWK-005
grep -rl "framework_id.*FMWK-005" Control_Plane_v2/_staging/PKG-*/  2>&1 | grep manifest
# Expected: only PKG-ADMIN-001/HOT/FMWK-005_Admin/manifest.yaml

# 4. Full regression
CONTROL_PLANE_ROOT="$TMPDIR" python3 -m pytest Control_Plane_v2/_staging/ -v
# Expected: no NEW test failures
```

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `manifest.json` | `_staging/PKG-FLOW-RUNNER-001/` | DELETE |
| `flow_runner.py` | `_staging/PKG-FLOW-RUNNER-001/HOT/kernel/` | DELETE |
| `flow_runner_config.schema.json` | `_staging/PKG-FLOW-RUNNER-001/HOT/schemas/` | DELETE |
| `manifest.yaml` | `_staging/PKG-FLOW-RUNNER-001/HOT/FMWK-005_Agent_Orchestration/` | DELETE |
| `test_flow_runner.py` | `_staging/PKG-FLOW-RUNNER-001/HOT/tests/` | DELETE |
| `BUILDER_HANDOFF_STANDARD.md` | `_staging/handoffs/` | MODIFY (agent registry + cross-cutting concerns) |

---

## 10. Design Principles

- **Delete, don't deprecate.** The package was never shipped. No backwards compatibility needed.
- **Historical references are harmless.** Process docs (handoffs, architecture) mentioning Flow Runner are historical record — don't sanitize history.
- **One FMWK-005 owner.** ADMIN wins the collision. No renumbering.
- **Verify before and after.** Confirm the deletion is clean. Report any surprises.
- **No cascade.** If any product file has an unexpected dependency on flow_runner code, STOP and report — do not attempt to fix it. The fix may require a design decision.
