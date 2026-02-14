# Builder Follow-Up #3A: Governance Health Tests — Ownership-Based Validation

## Mission

Fix `TestGovernanceHealth` in `PKG-SPEC-CONFORMANCE-001` to scale with the package system instead of hardcoding counts. Currently, three tests assert exact artifact counts (8 schemas, 4 frameworks, 11 specs). Every Layer 3 package that ships a schema, framework, or spec breaks these tests. Replace the brittle count assertions with ownership-based validation that uses `file_ownership.csv` — the registry the package system already maintains.

**CRITICAL CONSTRAINTS — read before doing anything:**

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree.
2. **DTT: Design → Test → Then implement.** Think through the test design before writing code. Every change must be testable.
3. **Only modify `PKG-SPEC-CONFORMANCE-001`** — one file (`HOT/tests/test_spec_conformance.py`), one manifest (`manifest.json`), one archive (`PKG-SPEC-CONFORMANCE-001.tar.gz`), and `CP_BOOTSTRAP.tar.gz`.
4. **End-to-end verification.** After modifying, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → install Layers 0-2 (8 packages) → install Layer 3 (`PKG-PHASE2-SCHEMAS-001`, `PKG-TOKEN-BUDGETER-001`, `PKG-PROMPT-ROUTER-001`). All gates must pass. All tests must pass, INCLUDING the modified governance health tests.
5. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`).
6. **No file replacement.** This is an edit to an existing Layer 2 package. Update in place, rebuild the archive.

---

## The Problem

`TestGovernanceHealth` in `test_spec_conformance.py` (lines 158-180) has three tests:

```python
def test_exactly_11_specs(self):     # hardcodes 11 spec names
def test_exactly_4_frameworks(self):  # hardcodes 4 framework names
def test_exactly_8_schemas(self):     # hardcodes 8 schema filenames
```

When Layer 3 packages install (PKG-PHASE2-SCHEMAS-001 adds 3 schemas, PKG-TOKEN-BUDGETER-001 adds 1, PKG-PROMPT-ROUTER-001 adds 1), `test_exactly_8_schemas` fails because there are now 13 schemas in `HOT/schemas/`. Future packages (attention, flow runner, etc.) will add more. The test is a snapshot, not a rule.

The same problem applies to frameworks and specs. As Layer 3+ lands FMWK-003 through FMWK-009 and potentially new specs, the other two tests will break too.

---

## The Fix: Two-Layer Validation

Replace each hardcoded-count test with TWO checks:

### Layer 1: Baseline Regression Guard

The Layer 0-2 artifacts are the governance foundation. They must ALWAYS be present. Assert they exist by name. This is a regression guard — if bootstrap is broken, this catches it.

**Baseline schemas (8):**
```python
BASELINE_SCHEMAS = [
    "attention_envelope.json", "framework.schema.json",
    "package_manifest.json", "package_manifest_l0.json",
    "spec.schema.json", "stdlib_llm_request.json",
    "stdlib_llm_response.json", "work_order.schema.json",
]
```

**Baseline frameworks (4):**
```python
BASELINE_FRAMEWORKS = ["FMWK-000", "FMWK-001", "FMWK-002", "FMWK-007"]
```

**Baseline specs (11):**
```python
BASELINE_SPECS = [
    "SPEC-CORE-001", "SPEC-GATE-001", "SPEC-GENESIS-001",
    "SPEC-INT-001", "SPEC-LEDGER-001", "SPEC-PKG-001",
    "SPEC-PLANE-001", "SPEC-POLICY-001", "SPEC-REG-001",
    "SPEC-SEC-001", "SPEC-VER-001",
]
```

### Layer 2: Ownership Validation

Every governance artifact in the filesystem must be registered in `file_ownership.csv`. No orphans allowed. This is the scalable check — new packages register their files when they install, and the test validates that registration happened.

**For schemas:** Every `*.json` file in `HOT/schemas/` must have a row in `file_ownership.csv` where `file_path` matches `HOT/schemas/<filename>`.

**For frameworks:** Every `FMWK-*` directory under `HOT/` must have at least one file registered in `file_ownership.csv` with a path starting with `HOT/FMWK-<id>/`. (Note: Layer 3 framework manifests ship as assets inside packages but the directory may not exist until framework auto-registration is built. For now, validate that any FMWK-* directory that DOES exist has registered files. This is forward-compatible.)

**For specs:** Every `SPEC-*` directory under `HOT/spec_packs/` must have at least one file registered in `file_ownership.csv`.

---

## What file_ownership.csv Looks Like

Located at `HOT/registries/file_ownership.csv`. Columns:
```
file_path,package_id,sha256,classification,installed_date,replaced_date,superseded_by
```

Example rows:
```
HOT/schemas/work_order.schema.json,PKG-FRAMEWORK-WIRING-001,sha256:ad63cb12...,schema,2026-02-10T...,,
HOT/schemas/prompt_contract.schema.json,PKG-PHASE2-SCHEMAS-001,sha256:7b2c3e...,schema,2026-02-10T...,,
```

To check ownership: load the CSV, build a set of all `file_path` values (where `replaced_date` is empty — i.e., current owner, not superseded), and check if each filesystem artifact appears in that set.

---

## Implementation Steps

### Step 1: Read the existing test file
```
Control_Plane_v2/_staging/PKG-SPEC-CONFORMANCE-001/HOT/tests/test_spec_conformance.py
```

### Step 2: Add a CSV loading helper

Add a function to load `file_ownership.csv` and return the set of currently-owned file paths:

```python
import csv

def _load_owned_files(cp_root: Path) -> set[str]:
    """Load currently-owned file paths from file_ownership.csv."""
    csv_path = cp_root / "HOT" / "registries" / "file_ownership.csv"
    if not csv_path.exists():
        return set()
    owned = set()
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Only current owners (not superseded)
            if not row.get("replaced_date"):
                owned.add(row["file_path"])
    return owned
```

### Step 3: Modify `TestGovernanceHealth`

Replace the three `test_exactly_*` methods with six methods (2 per artifact type):

```python
class TestGovernanceHealth:
    """Governance health: baseline regression + ownership validation."""

    # ── Baselines (Layer 0-2 foundation) ──

    BASELINE_SCHEMAS = [
        "attention_envelope.json", "framework.schema.json",
        "package_manifest.json", "package_manifest_l0.json",
        "spec.schema.json", "stdlib_llm_request.json",
        "stdlib_llm_response.json", "work_order.schema.json",
    ]

    BASELINE_FRAMEWORKS = ["FMWK-000", "FMWK-001", "FMWK-002", "FMWK-007"]

    BASELINE_SPECS = [
        "SPEC-CORE-001", "SPEC-GATE-001", "SPEC-GENESIS-001",
        "SPEC-INT-001", "SPEC-LEDGER-001", "SPEC-PKG-001",
        "SPEC-PLANE-001", "SPEC-POLICY-001", "SPEC-REG-001",
        "SPEC-SEC-001", "SPEC-VER-001",
    ]

    def test_baseline_schemas_present(self):
        """Layer 0-2 schemas must always exist (regression guard)."""
        schemas = {f.name for f in (HOT_ROOT / "schemas").glob("*.json")}
        for baseline in self.BASELINE_SCHEMAS:
            assert baseline in schemas, f"Baseline schema missing: {baseline}"

    def test_baseline_frameworks_present(self):
        """Layer 0-2 frameworks must always exist (regression guard)."""
        fmwk_dirs = {d.name.split("_")[0] for d in HOT_ROOT.iterdir()
                     if d.is_dir() and d.name.startswith("FMWK-")}
        for baseline in self.BASELINE_FRAMEWORKS:
            assert baseline in fmwk_dirs, f"Baseline framework missing: {baseline}"

    def test_baseline_specs_present(self):
        """Layer 0-2 specs must always exist (regression guard)."""
        spec_dirs = {d.name for d in SPEC_PACKS.iterdir()
                     if d.is_dir() and d.name.startswith("SPEC-")}
        for baseline in self.BASELINE_SPECS:
            assert baseline in spec_dirs, f"Baseline spec missing: {baseline}"

    # ── Ownership validation (scales with packages) ──

    def test_all_schemas_owned(self):
        """Every schema in HOT/schemas/ must be registered in file_ownership.csv."""
        owned = _load_owned_files(CP_ROOT)
        schemas = sorted(f for f in (HOT_ROOT / "schemas").glob("*.json"))
        orphans = []
        for schema_path in schemas:
            rel_path = f"HOT/schemas/{schema_path.name}"
            if rel_path not in owned:
                orphans.append(rel_path)
        assert not orphans, f"Unregistered schemas (no owner in file_ownership.csv): {orphans}"

    def test_all_framework_dirs_owned(self):
        """Every FMWK-* dir must have at least one registered file."""
        owned = _load_owned_files(CP_ROOT)
        fmwk_dirs = sorted(d.name for d in HOT_ROOT.iterdir()
                           if d.is_dir() and d.name.startswith("FMWK-"))
        unowned = []
        for fmwk_dir in fmwk_dirs:
            prefix = f"HOT/{fmwk_dir}/"
            has_owned_file = any(f.startswith(prefix) for f in owned)
            if not has_owned_file:
                unowned.append(fmwk_dir)
        assert not unowned, f"Framework dirs with no registered files: {unowned}"

    def test_all_spec_dirs_owned(self):
        """Every SPEC-* dir must have at least one registered file."""
        owned = _load_owned_files(CP_ROOT)
        spec_dirs = sorted(d.name for d in SPEC_PACKS.iterdir()
                           if d.is_dir() and d.name.startswith("SPEC-"))
        unowned = []
        for spec_dir in spec_dirs:
            prefix = f"HOT/spec_packs/{spec_dir}/"
            has_owned_file = any(f.startswith(prefix) for f in owned)
            if not has_owned_file:
                unowned.append(spec_dir)
        assert not unowned, f"Spec dirs with no registered files: {unowned}"
```

### Step 4: Update the docstring

Update the module docstring (line 7) from:
```
- Exactly 11 specs, 4 frameworks, 8 schemas remain
```
to:
```
- Baseline specs, frameworks, schemas present (regression guard)
- All schemas, frameworks, specs registered in file_ownership.csv (ownership validation)
```

### Step 5: Update the DEAD_SPECS / SURVIVING_SPECS constants

Keep `DEAD_SPECS` as-is (the regression check for removed specs is still valid).
Keep `SURVIVING_SPECS` as-is (used by other test classes for parametrization).

### Step 6: Rebuild the package

1. Recompute SHA256 for the modified `test_spec_conformance.py`
2. Update `PKG-SPEC-CONFORMANCE-001/manifest.json` with the new hash
3. Rebuild `PKG-SPEC-CONFORMANCE-001.tar.gz`: `tar czf ... -C PKG-SPEC-CONFORMANCE-001 $(ls PKG-SPEC-CONFORMANCE-001)`
4. Rebuild `CP_BOOTSTRAP.tar.gz` with the updated archive (it's a Layer 2 package, so it's inside the bootstrap)

### Step 7: End-to-end verification

Full clean-room test:
```bash
TMPDIR=$(mktemp -d)
export CONTROL_PLANE_ROOT="$TMPDIR"
tar xzf _staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"

# Layer 0 (genesis + kernel)
python3 "$TMPDIR/HOT/scripts/genesis_bootstrap.py" \
    --seed "$TMPDIR/packages/PKG-GENESIS-000.tar.gz" \
    --archive "$TMPDIR/packages/PKG-KERNEL-001.tar.gz" \
    --root "$TMPDIR" --dev

# Layer 1
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/packages/PKG-VOCABULARY-001.tar.gz" \
    --id PKG-VOCABULARY-001 --root "$TMPDIR" --dev
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/packages/PKG-REG-001.tar.gz" \
    --id PKG-REG-001 --root "$TMPDIR" --dev

# Layer 2
for pkg in PKG-GOVERNANCE-UPGRADE-001 PKG-FRAMEWORK-WIRING-001 PKG-SPEC-CONFORMANCE-001 PKG-LAYOUT-001; do
    python3 "$TMPDIR/HOT/scripts/package_install.py" \
        --archive "$TMPDIR/packages/$pkg.tar.gz" \
        --id "$pkg" --root "$TMPDIR" --dev
done

# Layer 3 (Phase 2 + router/budgeter)
for pkg in PKG-PHASE2-SCHEMAS-001 PKG-TOKEN-BUDGETER-001 PKG-PROMPT-ROUTER-001; do
    python3 "$TMPDIR/HOT/scripts/package_install.py" \
        --archive "Control_Plane_v2/_staging/$pkg.tar.gz" \
        --id "$pkg" --root "$TMPDIR" --dev
done

# Run gate checks
python3 "$TMPDIR/HOT/scripts/gate_check.py" --root "$TMPDIR" --all

# Run the modified test (from staging, against the installed environment)
CONTROL_PLANE_ROOT="$TMPDIR" python3 -m pytest \
    Control_Plane_v2/_staging/PKG-SPEC-CONFORMANCE-001/HOT/tests/test_spec_conformance.py -v

# Run ALL tests to confirm nothing regressed
python3 -m pytest Control_Plane_v2/_staging/ -v
```

**Expected results:**
- All 8 Layer 0-2 packages install, all gates pass
- All 3 Layer 3 packages install, all gates pass
- `test_baseline_schemas_present` passes (8 baseline schemas exist)
- `test_baseline_frameworks_present` passes (4 baseline frameworks exist)
- `test_baseline_specs_present` passes (11 baseline specs exist)
- `test_all_schemas_owned` passes (all 13 schemas registered in file_ownership.csv)
- `test_all_framework_dirs_owned` passes (all framework dirs have registered files)
- `test_all_spec_dirs_owned` passes (all spec dirs have registered files)
- Old test `test_exactly_8_schemas` is GONE (replaced by the two new tests)
- Full suite: 0 failures

---

## Files Modified

| File | Location | Action |
|------|----------|--------|
| `test_spec_conformance.py` | `_staging/PKG-SPEC-CONFORMANCE-001/HOT/tests/` | EDIT: replace 3 count tests with 6 ownership tests + add CSV helper |
| `manifest.json` | `_staging/PKG-SPEC-CONFORMANCE-001/` | EDIT: update SHA256 hash |
| `PKG-SPEC-CONFORMANCE-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD (contains PKG-SPEC-CONFORMANCE-001) |

**Not modified:** Any other package. Any Python code outside the test file. The conflated repo tree.

---

## Design Principles

1. **Baseline guards protect the foundation.** Layer 0-2 artifacts are the governance bedrock. Named, explicit, non-negotiable.
2. **Ownership validation scales with packages.** The package system already registers files in file_ownership.csv. The test reads that registry. New packages = automatic coverage. No count bumps needed.
3. **Orphan detection catches governance violations.** An unregistered schema is a governance failure — it has no provenance, no owner, no hash integrity. The test flags it.
4. **Supersession-aware.** Only check current owners (`replaced_date` is empty). Superseded files are historical records, not live governance concerns.
5. **No hardcoded counts.** The test never says "there must be N schemas." It says "every schema must be owned." That's the actual rule.
