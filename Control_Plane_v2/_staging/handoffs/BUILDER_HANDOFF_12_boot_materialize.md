# BUILDER_HANDOFF_12: Boot-Time Tier Materialization + Path Fix

## 1. Mission

Create `PKG-BOOT-MATERIALIZE-001` — a boot-time materializer that ensures HO2/HO1 directories, tier manifests, and GENESIS ledger chains exist before ADMIN's session loop starts. Also fix the `planes/` path artifact in `ledger_client.py` (PKG-KERNEL-001) so tier ledger helpers resolve to the correct filesystem paths defined in `layout.json`.

After this handoff, ADMIN boots into a fully materialized 3-tier system with cryptographically chained ledgers: HO1 GENESIS → HO2 → HOT.

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** New code ships as packages in `_staging/PKG-BOOT-MATERIALIZE-001/` with manifest.json, SHA256 hashes, proper dependencies. Follow existing package patterns.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → install all layers → verify boot materialization runs. All gates must pass.
5. **No hardcoding.** Tier names and subdirectory names come from `layout.json`. Do NOT hardcode `"HO2"`, `"HO1"`, or subdirectory names anywhere in `boot_materialize.py`. Read them from config.
6. **No file replacement.** Packages must NEVER overwrite another package's files. Use state-gating instead.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`).
8. **Results file.** When finished, write `_staging/RESULTS_HANDOFF_12.md` (see `BUILDER_HANDOFF_STANDARD.md`).
9. **Full regression test.** Run ALL staged package tests (not just yours) and report results.
10. **Baseline snapshot.** Your results file must include a baseline snapshot.

**Task-specific constraints:**

11. **Idempotent.** `boot_materialize()` must be safe to call on every boot. Check before creating. If directories exist, tier.json exists, and GENESIS entries exist — do nothing. Never duplicate GENESIS entries.
12. **layout.json is the single source of truth for paths.** All tier paths are derived from `HOT/config/layout.json`. The `tiers` map gives tier names → directory names. The `tier_dirs` map gives subdirectory names. Do not invent paths.
13. **GENESIS chain order matters.** HOT's GENESIS is written first (no parent). HO2's GENESIS references HOT's last entry hash. HO1's GENESIS references HO2's last entry hash. Order is: HOT → HO2 → HO1.
14. **This handoff creates ONE new package and fixes TWO existing packages.** PKG-BOOT-MATERIALIZE-001 is new. PKG-KERNEL-001 gets a 3-function path fix in `ledger_client.py`. PKG-ADMIN-001 gets one import + one function call in `main.py`. Both existing packages need updated manifests (new SHA256 for changed files). All three packages must be rebuilt into `CP_BOOTSTRAP.tar.gz`.

---

## 3. Architecture / Design

### Boot Materialization Flow

Called from `main.py` before the session host is created:

```
main() → run_cli() → boot_materialize(plane_root)
                        │
                        ├─ Step A: Materialize directories
                        │   Call materialize_layout.materialize(plane_root)
                        │   (existing function, reads layout.json, creates tier subdirs)
                        │
                        ├─ Step B: Write tier manifests
                        │   For each tier in layout.json["tiers"]:
                        │     tier_root = plane_root / tier_dir_name
                        │     if tier_root / "tier.json" does NOT exist:
                        │       Create TierManifest(tier=tier_name, tier_root=tier_root, ...)
                        │       Set parent_ledger based on tier:
                        │         HOT: parent_ledger = None
                        │         HO2: parent_ledger = str(plane_root / "HOT" / "ledger" / "governance.jsonl")
                        │         HO1: parent_ledger = str(plane_root / "HO2" / "ledger" / "governance.jsonl")
                        │       manifest.save()
                        │
                        └─ Step C: Initialize GENESIS chains
                            Process tiers in order: HOT, HO2, HO1
                            For each tier:
                              ledger_path = tier_root / "ledger" / "governance.jsonl"
                              client = LedgerClient(ledger_path=ledger_path)
                              if client.count() == 0:
                                parent_hash = get last entry hash from parent tier's ledger (None for HOT)
                                client.write_genesis(
                                    tier=tier_name,
                                    plane_root=plane_root,
                                    parent_ledger=parent_ledger_path,
                                    parent_hash=parent_hash,
                                )
```

### Path Fix in ledger_client.py

Three helper functions use `root / "planes" / tier` but layout.json defines tiers at `root / TIER_NAME`:

| Function | Line | Current (wrong) | Correct |
|----------|------|-----------------|---------|
| `get_session_ledger_path()` | 954 | `root / "planes" / tier / "sessions"` | `root / tier.upper() / "sessions"` |
| `read_recent_from_tier()` | 1019 | `root / "planes" / tier_lower / "ledger"` | `root / tier.upper() / "ledger"` |
| `list_session_ledgers()` | 1044 | `root / "planes" / tier / "sessions"` | `root / tier.upper() / "sessions"` |

Also update the docstrings at lines 941 and 967 that reference the old `planes/<tier>/...` path pattern.

**IMPORTANT:** `read_recent_from_tier()` currently normalizes tier to lowercase (`tier_lower = tier.lower()`). The fix must normalize to UPPERCASE because the filesystem directories are `HOT/`, `HO2/`, `HO1/` (uppercase). Change `tier_lower` to `tier_upper = tier.upper()` in that function.

### main.py Wiring

In `run_cli()`, add one call before `build_session_host()`:

```python
def run_cli(root, config_path, dev_mode=False, input_fn=input, output_fn=print):
    # NEW: Boot-time tier materialization
    from boot_materialize import boot_materialize
    mat_result = boot_materialize(Path(root))
    if mat_result != 0:
        output_fn(f"WARNING: Boot materialization returned {mat_result} (non-fatal)")

    host = build_session_host(root=root, config_path=config_path, dev_mode=dev_mode)
    # ... rest unchanged
```

If `boot_materialize()` fails, ADMIN still boots but prints a warning. Non-fatal.

---

## 4. Implementation Steps

### Step 1: Write tests (DTT)

Create `_staging/PKG-BOOT-MATERIALIZE-001/HOT/tests/test_boot_materialize.py` with all tests from the Test Plan (Section 6). Tests use `tmp_path` fixtures to create isolated plane roots. No real LLM calls, no real API keys.

### Step 2: Write path fix tests

Add tests for the 3 fixed functions to the same test file (or a separate `test_ledger_path_fix.py` in the same package). These verify the helper functions return paths WITHOUT the `planes/` prefix.

### Step 3: Implement boot_materialize.py

Create `_staging/PKG-BOOT-MATERIALIZE-001/HOT/scripts/boot_materialize.py`:

```python
"""Boot-time tier materialization.

Ensures HO2/HO1 directories, tier manifests (tier.json), and GENESIS
ledger chains exist before the ADMIN session loop starts.

Idempotent: checks before creating. Safe to call on every boot.

Usage:
    from boot_materialize import boot_materialize
    exit_code = boot_materialize(plane_root)
"""
```

Function signature:

```python
def boot_materialize(plane_root: Path) -> int:
    """Materialize tier directories, manifests, and GENESIS chains.

    Args:
        plane_root: Path to the control plane root directory.

    Returns:
        0 on success, 1 on config error, 2 on permission error.
    """
```

The implementation:
1. Call `materialize_layout.materialize(plane_root)` — this handles directory creation
2. Load `layout.json` to get tier names and order
3. Define tier processing order: HOT first (no parent), then HO2 (parent=HOT), then HO1 (parent=HO2)
4. For each tier: check tier.json, create TierManifest if missing
5. For each tier in order: check governance.jsonl, write GENESIS if empty, chain to parent's last hash

**Tier ordering logic:** The `tiers` map in layout.json is `{"HOT": "HOT", "HO2": "HO2", "HO1": "HO1"}`. Process in this order: HOT, HO2, HO1. This is the hierarchy order — each tier's GENESIS references the tier above it.

**Getting parent hash:** For HO2, read HOT's governance.jsonl and get the last entry hash. For HO1, read HO2's governance.jsonl and get the last entry hash. Use `LedgerClient.get_last_entry_hash_value()` (existing method, line 864 of ledger_client.py).

### Step 4: Fix ledger_client.py

In `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py`:

**Function 1: `get_session_ledger_path()`** (line 932-954)
- Line 941 docstring: change `planes/<tier>/sessions/` to `<TIER>/sessions/`
- Line 954: change `return root / "planes" / tier / "sessions" / session_id / "ledger" / f"{ledger_type}.jsonl"` to `return root / tier.upper() / "sessions" / session_id / "ledger" / f"{ledger_type}.jsonl"`

**Function 2: `read_recent_from_tier()`** (line 992-1025)
- Line 967 docstring (in `create_session_ledger_client`): change `planes/<tier>/sessions/` to `<TIER>/sessions/`
- Line 1011: change `tier_lower = tier.lower()` to `tier_upper = tier.upper()`
- Line 1015: change the HOT path from `root / "ledger" / "governance.jsonl"` to `root / "HOT" / "ledger" / "governance.jsonl"` (HOT's ledger is inside HOT/, not at root)
- Line 1019: change `root / "planes" / tier_lower / "ledger" / "governance.jsonl"` to `root / tier_upper / "ledger" / "governance.jsonl"`

**Function 3: `list_session_ledgers()`** (line 1028-1066)
- Line 1044: change `root / "planes" / tier / "sessions"` to `root / tier.upper() / "sessions"`

### Step 5: Add boot_materialize import path to main.py

In `_staging/PKG-ADMIN-001/HOT/admin/main.py`:

Add to `_ensure_import_paths()`:
```python
staging / "PKG-BOOT-MATERIALIZE-001" / "HOT" / "scripts",
staging / "PKG-LAYOUT-002" / "HOT" / "scripts",
```

Add the boot call in `run_cli()` before `build_session_host()` (see Architecture section).

### Step 6: Create manifest.json for PKG-BOOT-MATERIALIZE-001

```json
{
  "package_id": "PKG-BOOT-MATERIALIZE-001",
  "version": "1.0.0",
  "schema_version": "1.2",
  "title": "Boot-Time Tier Materializer",
  "description": "Ensure HO2/HO1 directories, tier.json manifests, and GENESIS ledger chains exist at boot",
  "spec_id": "SPEC-GATE-001",
  "framework_id": "FMWK-000",
  "plane_id": "hot",
  "layer": 3,
  "dependencies": [
    "PKG-KERNEL-001",
    "PKG-LAYOUT-002"
  ],
  "assets": [
    {
      "path": "HOT/scripts/boot_materialize.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "script"
    },
    {
      "path": "HOT/tests/test_boot_materialize.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "test"
    }
  ]
}
```

### Step 7: Update existing package manifests

**PKG-KERNEL-001/manifest.json:** Recompute SHA256 for `HOT/kernel/ledger_client.py` (the file changed).

**PKG-ADMIN-001/manifest.json:** Recompute SHA256 for `HOT/admin/main.py` (the file changed).

### Step 8: Build all modified package archives

Rebuild these three .tar.gz archives:
- `PKG-BOOT-MATERIALIZE-001.tar.gz` (new)
- `PKG-KERNEL-001.tar.gz` (updated)
- `PKG-ADMIN-001.tar.gz` (updated)

Use Python `tarfile` with explicit `arcname`:
```python
import tarfile
from pathlib import Path

def build_pkg(pkg_dir, output_path):
    with tarfile.open(output_path, "w:gz") as tf:
        for f in sorted(Path(pkg_dir).rglob("*")):
            if f.is_file() and "__pycache__" not in str(f):
                tf.add(str(f), arcname=str(f.relative_to(pkg_dir)))
```

### Step 9: Rebuild CP_BOOTSTRAP.tar.gz

The archive now contains 17 packages (16 existing + PKG-BOOT-MATERIALIZE-001). Replace the 2 updated archives (PKG-KERNEL-001, PKG-ADMIN-001) and add the new one. Rebuild using the same tar format.

Verify: `tar tzf CP_BOOTSTRAP.tar.gz | grep '.tar.gz' | wc -l` should show 17.

### Step 10: Clean-room verification

```bash
TESTDIR=$(mktemp -d)
INSTALLDIR=$(mktemp -d)
export CONTROL_PLANE_ROOT="$INSTALLDIR"
tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TESTDIR"
cd "$TESTDIR" && bash install.sh --root "$INSTALLDIR" --dev
```

Expected: 17 packages installed, 8/8 gates PASS.

Then verify materialization:
```bash
# Tier directories exist
ls "$INSTALLDIR/HO2/ledger/"
ls "$INSTALLDIR/HO1/ledger/"

# Tier manifests exist
cat "$INSTALLDIR/HO2/tier.json"
cat "$INSTALLDIR/HO1/tier.json"

# GENESIS entries exist and chain
python3 -c "
import sys; sys.path.insert(0, '$INSTALLDIR/HOT/kernel')
from ledger_client import LedgerClient
for tier in ['HOT', 'HO2', 'HO1']:
    lc = LedgerClient(ledger_path=__import__('pathlib').Path('$INSTALLDIR') / tier / 'ledger' / 'governance.jsonl')
    ok, issues = lc.verify_genesis()
    print(f'{tier}: GENESIS valid={ok}, issues={issues}')
"
```

### Step 11: Write results file

Write `_staging/RESULTS_HANDOFF_12.md` following the standard format.

---

## 5. Package Plan

### New Package

| Field | Value |
|-------|-------|
| Package ID | `PKG-BOOT-MATERIALIZE-001` |
| Layer | 3 |
| spec_id | `SPEC-GATE-001` |
| framework_id | `FMWK-000` |
| plane_id | `hot` |
| Dependencies | `PKG-KERNEL-001`, `PKG-LAYOUT-002` |
| Assets | `HOT/scripts/boot_materialize.py` (script), `HOT/tests/test_boot_materialize.py` (test) |

### Modified Packages

| Package | File Modified | Change |
|---------|--------------|--------|
| `PKG-KERNEL-001` | `HOT/kernel/ledger_client.py` | Fix 3 functions + 2 docstrings: remove `planes/` path prefix |
| `PKG-ADMIN-001` | `HOT/admin/main.py` | Add import path + one `boot_materialize()` call before session start |

---

## 6. Test Plan

**File:** `_staging/PKG-BOOT-MATERIALIZE-001/HOT/tests/test_boot_materialize.py`

All tests use `tmp_path` to create isolated plane roots. No real API calls.

### Setup Helper

Create a minimal plane root with HOT structure:
- `HOT/config/layout.json` (copy from PKG-LAYOUT-002)
- `HOT/ledger/` directory
- Optionally pre-populate HOT governance.jsonl with entries

### Boot Materialization Tests

| # | Test | Validates |
|---|------|-----------|
| 1 | `test_fresh_boot_creates_ho2_directories` | HO2 gets all 7 subdirs from layout.json tier_dirs |
| 2 | `test_fresh_boot_creates_ho1_directories` | HO1 gets all 7 subdirs from layout.json tier_dirs |
| 3 | `test_fresh_boot_creates_ho2_tier_json` | HO2/tier.json exists after boot |
| 4 | `test_fresh_boot_creates_ho1_tier_json` | HO1/tier.json exists after boot |
| 5 | `test_ho2_tier_json_parent_is_hot` | HO2 tier.json parent_ledger points to HOT/ledger/governance.jsonl |
| 6 | `test_ho1_tier_json_parent_is_ho2` | HO1 tier.json parent_ledger points to HO2/ledger/governance.jsonl |
| 7 | `test_hot_genesis_created_if_empty` | HOT governance.jsonl gets GENESIS entry when empty |
| 8 | `test_ho2_genesis_created` | HO2 governance.jsonl gets GENESIS entry |
| 9 | `test_ho1_genesis_created` | HO1 governance.jsonl gets GENESIS entry |
| 10 | `test_genesis_chain_ho2_to_hot` | HO2 GENESIS parent_hash == HOT ledger's last entry hash |
| 11 | `test_genesis_chain_ho1_to_ho2` | HO1 GENESIS parent_hash == HO2 ledger's last entry hash |
| 12 | `test_chain_verification_passes` | `verify_chain_link(HO1, HO2_ledger)` and `verify_chain_link(HO2, HOT_ledger)` both return True |
| 13 | `test_idempotent_second_boot` | Calling boot_materialize twice creates no duplicate GENESIS entries, no errors |
| 14 | `test_partial_recovery_missing_ho1_only` | If HO1 dir deleted but HO2 intact, only HO1 recreated |
| 15 | `test_paths_derived_from_layout_json` | boot_materialize reads tier names from layout.json, not hardcoded |
| 16 | `test_returns_zero_on_success` | Return code is 0 on successful materialization |
| 17 | `test_returns_one_on_missing_layout_json` | Return code is 1 if layout.json not found |

### Path Fix Tests

| # | Test | Validates |
|---|------|-----------|
| 18 | `test_read_recent_from_tier_correct_path` | `read_recent_from_tier("HO2", root=r)` reads from `r/HO2/ledger/governance.jsonl`, NOT `r/planes/ho2/...` |
| 19 | `test_read_recent_from_tier_hot_path` | `read_recent_from_tier("HOT", root=r)` reads from `r/HOT/ledger/governance.jsonl` |
| 20 | `test_get_session_ledger_path_correct` | Returns `root/HO1/sessions/SES-001/ledger/exec.jsonl`, NOT `root/planes/ho1/...` |
| 21 | `test_list_session_ledgers_correct_path` | Searches `root/HO2/sessions/`, NOT `root/planes/ho2/sessions/` |

**21 tests total.** Covers: directory creation, tier manifests, GENESIS chain integrity, idempotency, error handling, path fix verification.

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| materialize_layout.py | `_staging/PKG-LAYOUT-002/HOT/scripts/materialize_layout.py` | Directory creation logic you call in Step A |
| layout.json | `_staging/PKG-LAYOUT-002/HOT/config/layout.json` | Source of truth for tier names + subdirs |
| TierManifest | `_staging/PKG-KERNEL-001/HOT/kernel/tier_manifest.py` | Tier manifest dataclass for Step B |
| LedgerClient | `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` | GENESIS writing + chain verification for Step C. Also the file you fix (planes/ path). |
| main.py | `_staging/PKG-ADMIN-001/HOT/admin/main.py` | Where you add the boot_materialize() call |
| HANDOFF-9 example | `_staging/BUILDER_HANDOFF_9_anthropic_provider.md` | Reference handoff format |
| Builder standard | `_staging/BUILDER_HANDOFF_STANDARD.md` | Results file format, baseline snapshot format |

---

## 8. End-to-End Verification

```bash
# 1. Run package tests
cd Control_Plane_v2/_staging
CONTROL_PLANE_ROOT="/tmp/test" python3 -m pytest PKG-BOOT-MATERIALIZE-001/HOT/tests/test_boot_materialize.py -v
# Expected: 21 tests pass

# 2. Verify package archive contents
tar tzf _staging/PKG-BOOT-MATERIALIZE-001.tar.gz
# Expected:
#   manifest.json
#   HOT/scripts/boot_materialize.py
#   HOT/tests/test_boot_materialize.py

# 3. Verify CP_BOOTSTRAP contents
tar tzf _staging/CP_BOOTSTRAP.tar.gz | grep '.tar.gz' | wc -l
# Expected: 17 (16 existing + PKG-BOOT-MATERIALIZE-001)

# 4. Clean-room install
TESTDIR=$(mktemp -d)
INSTALLDIR=$(mktemp -d)
export CONTROL_PLANE_ROOT="$INSTALLDIR"
tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TESTDIR"
cd "$TESTDIR" && bash install.sh --root "$INSTALLDIR" --dev
# Expected: 17 packages installed, 8/8 gates PASS

# 5. Start ADMIN and verify boot materialization
export ANTHROPIC_API_KEY="test-key"
python3 "$INSTALLDIR/HOT/admin/main.py" --root "$INSTALLDIR" --dev <<< "exit"
# Expected: Session starts (boot_materialize ran), then exits cleanly

# 6. Verify tier structure after boot
ls "$INSTALLDIR/HO2/tier.json"   # exists
ls "$INSTALLDIR/HO1/tier.json"   # exists
ls "$INSTALLDIR/HO2/ledger/governance.jsonl"  # exists, has GENESIS
ls "$INSTALLDIR/HO1/ledger/governance.jsonl"  # exists, has GENESIS

# 7. Verify GENESIS chains
python3 -c "
import sys, pathlib
sys.path.insert(0, '$INSTALLDIR/HOT/kernel')
from ledger_client import LedgerClient
root = pathlib.Path('$INSTALLDIR')
for tier in ['HOT', 'HO2', 'HO1']:
    lc = LedgerClient(ledger_path=root / tier / 'ledger' / 'governance.jsonl')
    ok, issues = lc.verify_genesis()
    print(f'{tier}: valid={ok} issues={issues}')
# Verify cross-tier chain
ho2 = LedgerClient(ledger_path=root / 'HO2' / 'ledger' / 'governance.jsonl')
ok, issues = ho2.verify_chain_link(root / 'HOT' / 'ledger' / 'governance.jsonl')
print(f'HO2->HOT chain: valid={ok}')
ho1 = LedgerClient(ledger_path=root / 'HO1' / 'ledger' / 'governance.jsonl')
ok, issues = ho1.verify_chain_link(root / 'HO2' / 'ledger' / 'governance.jsonl')
print(f'HO1->HO2 chain: valid={ok}')
"
# Expected: All valid=True

# 8. Verify path fix
python3 -c "
import sys, pathlib
sys.path.insert(0, '$INSTALLDIR/HOT/kernel')
from ledger_client import get_session_ledger_path, read_recent_from_tier
root = pathlib.Path('$INSTALLDIR')
p = get_session_ledger_path('ho2', 'SES-001', root=root)
assert 'planes' not in str(p), f'planes/ found in path: {p}'
assert '/HO2/' in str(p), f'HO2 not in path: {p}'
print(f'get_session_ledger_path: {p} (correct)')
"
# Expected: path contains /HO2/, not /planes/

# 9. Gate check
python3 "$INSTALLDIR/HOT/scripts/gate_check.py" --root "$INSTALLDIR" --all
# Expected: 8/8 gates PASS

# 10. Full regression
cd Control_Plane_v2/_staging
python3 -m pytest . -v --ignore=PKG-FLOW-RUNNER-001
# Expected: all pass, no new failures
```

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `boot_materialize.py` | `_staging/PKG-BOOT-MATERIALIZE-001/HOT/scripts/` | CREATE |
| `test_boot_materialize.py` | `_staging/PKG-BOOT-MATERIALIZE-001/HOT/tests/` | CREATE |
| `manifest.json` | `_staging/PKG-BOOT-MATERIALIZE-001/` | CREATE |
| `ledger_client.py` | `_staging/PKG-KERNEL-001/HOT/kernel/` | MODIFY (fix 3 functions + 2 docstrings) |
| `manifest.json` | `_staging/PKG-KERNEL-001/` | MODIFY (update SHA for ledger_client.py) |
| `main.py` | `_staging/PKG-ADMIN-001/HOT/admin/` | MODIFY (add import path + boot call) |
| `manifest.json` | `_staging/PKG-ADMIN-001/` | MODIFY (update SHA for main.py) |
| `PKG-BOOT-MATERIALIZE-001.tar.gz` | `_staging/` | CREATE |
| `PKG-KERNEL-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-ADMIN-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD (17 packages) |
| `RESULTS_HANDOFF_12.md` | `_staging/` | CREATE |

**Not modified:** materialize_layout.py, tier_manifest.py, layout.json, any other existing package source file.

---

## 10. Design Principles

1. **Idempotent always.** Check before creating. `boot_materialize()` runs every boot. It must never create duplicate GENESIS entries, duplicate tier.json files, or fail on existing state.
2. **layout.json is authority.** Tier names, directory names, subdirectory names — all from config. If layout.json changes, boot_materialize adapts without code changes.
3. **GENESIS chain is sacred.** The hash chain HO1 → HO2 → HOT is a cryptographic proof of lineage. If HOT's ledger changes after HO2's GENESIS was written, the chain link will fail verification. This is by design — it detects tampering.
4. **Boot failure is non-fatal.** If materialization fails (missing layout.json, permission error), ADMIN still boots with a warning. The session loop works against HOT's existing structure. HO2/HO1 features degrade gracefully.
5. **No planes/ prefix.** Tier paths follow `root / TIER_NAME / ...` where TIER_NAME is uppercase (HOT, HO2, HO1). The `planes/` prefix was a legacy artifact. All path helpers must use the layout.json convention.
6. **Order matters for GENESIS.** HOT first (root of chain), then HO2 (references HOT), then HO1 (references HO2). Never write a child GENESIS before its parent ledger has entries to reference.
