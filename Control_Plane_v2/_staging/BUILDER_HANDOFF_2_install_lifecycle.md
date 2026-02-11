Read `Control_Plane_v2/_staging/AGENT_PROMPT_builder_qa.md` first if you haven't already — it has the full context about staging vs repo, the two-control-plane boundary, and the tar format rules.

## Task: State-Gated Install Lifecycle + Eliminate File Replacement

### Why This Changed

The original plan had GOVERNANCE-UPGRADE-001 **replacing** package_install.py and gate_check.py — overwriting the KERNEL-001 and VOCABULARY-001 versions. This breaks provenance and lineage. We're fixing the architecture:

1. **KERNEL-001's package_install.py** gets ALL capabilities from day one, state-gated
2. **VOCABULARY-001's gate_check.py** gets G1-COMPLETE merged in, already state-gated via ImportError
3. **GOVERNANCE-UPGRADE-001** stops replacing files — ships only `test_framework_completeness.py`

**State-gating means**: The code is present but dormant until the system state supports it. G1-COMPLETE checks for FrameworkCompletenessValidator via `try/except ImportError` — if it's not installed yet, the gate passes trivially. G0B checks for receipts — if none exist, it passes trivially. Auth checks for HMAC secret — if `--dev`, it's bypassed.

---

## CRITICAL RULES

- **Edit `_staging/PKG-KERNEL-001/HOT/scripts/package_install.py`** for the install lifecycle changes
- **Edit `_staging/PKG-VOCABULARY-001/HOT/scripts/gate_check.py`** to merge G1-COMPLETE in
- **Edit `_staging/PKG-GOVERNANCE-UPGRADE-001/manifest.json`** to remove package_install.py and gate_check.py assets
- **All verification happens in /tmp/** — clean install from CP_BOOTSTRAP.tar.gz
- **No half measures.** If validation fails, rollback must leave the system exactly as it was before the install attempt. Pristine.
- **Show your work.** Every change must be tested. Show the test.

---

## Phase 1: Upgrade KERNEL-001's package_install.py

You are modifying: `_staging/PKG-KERNEL-001/HOT/scripts/package_install.py` (751 lines)

### The Current Install Flow (lines 435-634)

```
install_package():
  1. Load manifest                          (line 480-482)
  2. Write INSTALL_STARTED to ledger        (line 488-494)
  3. Extract to workspace                   (line 499-504)
  4. G0A gate                               (line 506-512)
  5. G1 gate                                (line 514-520)
  6. G5 gate                                (line 522-530)
  7. Attestation check                      (line 532-542)
  8. Ownership conflict check               (line 544-553)
  9. Atomic copy files                      (line 565-575)
  10. Write receipt                          (line 577-586)
  11. Write INSTALLED to ledger             (line 588-597)
```

### The Target Install Flow

```
install_package():
  1. Load manifest
  2. Write INSTALL_STARTED to ledger (with FULL asset detail — same as receipt)
  --- PRE-INSTALL GATES ---
  3. Extract to workspace
  4. G0B: Verify existing system integrity (NEW — state-gated)
  5. G0A gate
  6. G1 gate
  7. G1-COMPLETE gate (NEW — state-gated via ImportError)
  8. G5 gate
  9. Attestation check
  10. Ownership conflict check
  --- EXECUTE ---
  11. Backup any files being overwritten (for rollback) (NEW)
  12. Atomic copy files
  --- VALIDATE ---
  13. Re-hash every installed file against manifest (NEW)
  14. If validation fails -> ROLLBACK (NEW)
  --- COMMIT (ledger first — it is system truth) ---
  15. Write INSTALLED to ledger (MOVED — now with full asset detail, AFTER validation)
  16. Append to file_ownership.csv (NEW — append-only with history columns)
  17. Write receipt
```

**Key commit order change**: Ledger is written FIRST (it is the system truth). Then file_ownership.csv. Then receipt. If validation fails, INSTALLED is never written — the except block writes INSTALL_FAILED instead.

---

### Change 1: G0B Pre-Install System Integrity Check

Insert before G0A. This is the kernel's self-model — "am I intact?"

```python
def check_g0b_system_integrity(plane_root: Path) -> Tuple[bool, List[str]]:
    """
    G0B: SYSTEM INTEGRITY - Verify existing installed files match their receipts.

    Reads all receipts from HOT/installed/*/receipt.json.
    For each file listed in each receipt, re-hash and compare.
    If no receipts exist (first install), passes trivially.

    Returns (passed, errors)
    """
    errors = []
    installed_dir = plane_root / "HOT" / "installed"

    if not installed_dir.is_dir():
        return (True, [])  # No installed packages yet — trivially passes

    receipt_count = 0
    files_checked = 0

    for pkg_dir in sorted(installed_dir.iterdir()):
        receipt_path = pkg_dir / "receipt.json"
        if not receipt_path.is_file():
            continue

        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError) as e:
            errors.append(f"Cannot read receipt {receipt_path}: {e}")
            continue

        receipt_count += 1
        files_list = receipt.get("files", [])
        if not files_list:
            continue  # Backward compat: skip receipts without files array

        for file_entry in files_list:
            file_path = plane_root / file_entry["path"]
            expected_hash = file_entry.get("sha256", "")

            if not file_path.exists():
                errors.append(f"Missing file: {file_entry['path']} (owned by {pkg_dir.name})")
                continue

            actual_hash = compute_sha256(file_path)
            expected_bare = expected_hash.removeprefix("sha256:")
            actual_bare = actual_hash.removeprefix("sha256:")

            if actual_bare != expected_bare:
                errors.append(
                    f"Integrity mismatch: {file_entry['path']} "
                    f"expected={expected_hash} actual=sha256:{actual_bare} "
                    f"(owned by {pkg_dir.name})"
                )
            files_checked += 1

    if receipt_count == 0:
        return (True, [])  # No receipts with file lists — trivially passes

    return (len(errors) == 0, errors)
```

Call in `install_package()` after INSTALL_STARTED, before G0A:
```python
# === GATE G0B: System Integrity ===
print(f"[install] Running G0B (system integrity)...", file=sys.stderr)
g0b_passed, g0b_errors = check_g0b_system_integrity(plane_root)
if not g0b_passed:
    error_msg = "G0B FAILED - system integrity compromised:\n" + "\n".join(g0b_errors[:10])
    raise GateFailure(error_msg)
print(f"[install] G0B PASSED", file=sys.stderr)
```

---

### Change 2: G1-COMPLETE Gate (state-gated)

Insert after G1 gate, before G5. This code exists in the GOVERNANCE-UPGRADE-001 version — you're merging it into KERNEL-001's version.

```python
# === GATE G1-COMPLETE: Framework Completeness (state-gated) ===
try:
    from kernel.preflight import FrameworkCompletenessValidator
    print(f"[install] Running G1-COMPLETE (framework completeness)...", file=sys.stderr)
    g1c_validator = FrameworkCompletenessValidator(plane_root=plane_root)
    g1c_result = g1c_validator.validate(manifest)
    if not g1c_result.passed:
        raise GateFailure("G1-COMPLETE FAILED:\n" + "\n".join(g1c_result.errors[:10]))
    print(f"[install] G1-COMPLETE PASSED ({g1c_result.message})", file=sys.stderr)
except ImportError:
    print(f"[install] G1-COMPLETE skipped (FrameworkCompletenessValidator not yet available)", file=sys.stderr)
```

**Why ImportError guard**: At Layer 0, FrameworkCompletenessValidator doesn't exist yet. At Layer 1+, it does. The code activates when the system state supports it — no file replacement needed.

---

### Change 3: Backup Before Overwrite (for rollback)

Before `atomic_copy_files`, save copies of any files that will be overwritten:

```python
# Before copy - backup files that will be overwritten (for rollback)
backup_dir = Path(tempfile.mkdtemp(prefix=f"cp-backup-{package_id}-"))
overwritten_backups = {}  # {rel_path: backup_path}
for rel_path in workspace_files:
    target = plane_root / rel_path
    if target.exists():
        backup_path = backup_dir / rel_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup_path)
        overwritten_backups[rel_path] = backup_path
if overwritten_backups:
    print(f"[install] Backed up {len(overwritten_backups)} existing files for rollback", file=sys.stderr)
```

Initialize `backup_dir = None` alongside `workspace_dir = None` (before the try block).

---

### Change 4: Post-Install Validation

After `atomic_copy_files`, before any commit operations:

```python
def validate_installed_files(
    manifest: dict,
    installed_files: List[Path],
    plane_root: Path,
) -> Tuple[bool, List[str]]:
    """
    Post-install validation: re-hash every installed file against manifest.
    Returns (passed, errors)
    """
    errors = []
    asset_hashes = {a["path"]: a["sha256"] for a in manifest.get("assets", [])}

    for file_path in installed_files:
        rel_path = str(file_path.relative_to(plane_root))
        expected = asset_hashes.get(rel_path)
        if expected is None:
            errors.append(f"Installed file {rel_path} not in manifest")
            continue
        actual = compute_sha256(file_path)
        expected_bare = expected.removeprefix("sha256:")
        actual_bare = actual.removeprefix("sha256:")
        if actual_bare != expected_bare:
            errors.append(f"Hash mismatch: {rel_path} expected={expected} actual=sha256:{actual_bare}")

    return (len(errors) == 0, errors)
```

Call after atomic_copy_files:
```python
print(f"[install] Validating installed files...", file=sys.stderr)
valid, val_errors = validate_installed_files(manifest, installed_files, plane_root)
if not valid:
    # ROLLBACK
    print(f"[install] VALIDATION FAILED - rolling back...", file=sys.stderr)
    rollback_install(installed_files, overwritten_backups, plane_root)
    error_msg = "POST-INSTALL VALIDATION FAILED:\n" + "\n".join(val_errors[:10])
    raise InstallError(error_msg)
print(f"[install] Validation PASSED - all {len(installed_files)} files verified", file=sys.stderr)
```

---

### Change 5: Rollback Function

```python
def rollback_install(
    installed_files: List[Path],
    overwritten_backups: Dict[str, Path],
    plane_root: Path,
) -> None:
    """
    Rollback a failed install: remove new files, restore overwritten files.
    After rollback, the system is exactly as it was before the install attempt.
    """
    for file_path in installed_files:
        rel_path = str(file_path.relative_to(plane_root))
        if rel_path in overwritten_backups:
            # Restore from backup
            shutil.copy2(overwritten_backups[rel_path], file_path)
        else:
            # New file - remove it
            if file_path.exists():
                file_path.unlink()
            # Clean up empty parent dirs (stop at plane_root)
            parent = file_path.parent
            try:
                while parent != plane_root and parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
            except OSError:
                pass  # Directory not empty or permission issue — stop cleaning
```

---

### Change 6: Reorder Commit Phase (ledger first, then ownership, then receipt)

**The new commit order** replaces the current receipt-then-ledger pattern:

```python
# === COMMIT PHASE (ledger is system truth — written first) ===

# 1. Write INSTALLED to ledger (with full asset detail)
asset_details = []
for asset in manifest.get("assets", []):
    asset_details.append({
        "path": asset["path"],
        "sha256": asset["sha256"],
        "classification": asset.get("classification", "unknown"),
    })

write_ledger_entry(
    event_type="INSTALLED",
    package_id=package_id,
    manifest_hash=manifest_hash,
    work_order_id=work_order_id,
    assets_count=len(installed_files),
    package_type=package_type,
    assets=asset_details,  # Full detail — ledger is system truth
)
print(f"[install] Wrote INSTALLED to ledger (system truth)", file=sys.stderr)

# 2. Append to file_ownership.csv (append-only with history)
print(f"[install] Updating file_ownership.csv...", file=sys.stderr)
append_file_ownership(manifest, package_id, plane_root, transfer_paths)

# 3. Write receipt (convenience snapshot — not system truth)
receipt_path = write_receipt(
    package_id=package_id,
    manifest=manifest,
    archive_path=archive_path,
    installed_files=installed_files,
    plane_root=plane_root,
    work_order_id=work_order_id,
)
print(f"[install] Receipt: {receipt_path}", file=sys.stderr)
```

**Important**: The ledger write now includes `assets` — full detail. The write_ledger_entry function may need to accept this new field. Check whether it passes through arbitrary kwargs (it likely does via `**extra`). If not, add the field.

---

### Change 7: file_ownership.csv — Append-Only with History

**Never overwrite or remove entries.** Use `replaced_date` and `superseded_by` columns for complete history.

```python
def append_file_ownership(
    manifest: dict,
    package_id: str,
    plane_root: Path,
    transfer_paths: Optional[Dict[str, str]] = None,
) -> None:
    """
    Append this package's files to file_ownership.csv.
    Creates the file with headers if it doesn't exist.

    APPEND-ONLY: Never removes old entries.
    For ownership transfers (file moves from pkg A to pkg B):
    - Append new entries for pkg B
    - Append supersession record for pkg A (replaced_date + superseded_by)

    The latest entry for a file_path is the current owner.
    Full history is preserved for audit.

    Columns: file_path, package_id, sha256, classification, installed_date, replaced_date, superseded_by
    """
    ownership_csv = plane_root / "HOT" / "registries" / "file_ownership.csv"
    file_exists = ownership_csv.exists()
    now = datetime.now(timezone.utc).isoformat()

    with open(ownership_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "file_path", "package_id", "sha256", "classification",
                "installed_date", "replaced_date", "superseded_by",
            ])

        # Write new ownership entries
        for asset in manifest.get("assets", []):
            writer.writerow([
                asset["path"],
                package_id,
                asset["sha256"],
                asset.get("classification", "unknown"),
                now,   # installed_date
                "",    # replaced_date (empty — this is the current owner)
                "",    # superseded_by (empty — not superseded yet)
            ])

        # Write supersession records for transferred files
        if transfer_paths:
            for file_path, old_package_id in transfer_paths.items():
                writer.writerow([
                    file_path,
                    old_package_id,
                    "",    # sha256 (old hash — could look up, but not needed for history)
                    "",    # classification
                    "",    # installed_date (original install date is in an earlier row)
                    now,   # replaced_date
                    package_id,  # superseded_by
                ])
```

**Note**: `transfer_paths` already exists — it comes from `check_ownership_conflicts()`. It's a dict of `{file_path: old_package_id}`.

---

### Change 8: InstallerClaims Auth Wiring (in main())

Replace the current auth block (lines 678-696):

```python
# Validate archive exists + load manifest for plane_id (needed for auth)
archive = args.archive.resolve()
if not archive.exists():
    print(f"Archive not found: {archive}", file=sys.stderr)
    return 1

manifest_preview = load_manifest_from_archive(archive)
if manifest_preview is None:
    print(f"Could not read manifest from archive: {archive}", file=sys.stderr)
    return 1

plane = manifest_preview.get("plane_id", "hot")

# AuthZ (state-gated: --dev bypasses, HMAC activates when secret exists)
if args.dev:
    print("[install] DEV MODE - auth, signature, and attestation checks bypassed", file=sys.stderr)
    allow_unsigned = True
    allow_unattested = True
    identity = None
    claims = None
else:
    try:
        token = args.token or os.getenv("CONTROL_PLANE_TOKEN")
        identity = get_provider().authenticate(token)
        env = os.getenv("CONTROL_PLANE_ENV", "dev")
        claims = InstallerClaims.from_identity(identity, env=env)
        require_authorization(
            action="install",
            pkg_id=args.package_id,
            tier="G0",
            env=env,
            claims=claims,
            plane=plane,
        )
    except PermissionError as e:
        print(f"Authorization failed: {e}", file=sys.stderr)
        return 1
```

**Remove** the duplicate archive validation that currently exists after the auth block (lines 692-696 in current version). The archive is now validated before auth.

---

### Change 9: Cleanup backup_dir

Add to the `finally` block:

```python
finally:
    if workspace_dir and workspace_dir.exists():
        shutil.rmtree(workspace_dir, ignore_errors=True)
    if backup_dir and backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)
```

---

## Phase 2: Merge G1-COMPLETE into VOCABULARY-001's gate_check.py

You are modifying: `_staging/PKG-VOCABULARY-001/HOT/scripts/gate_check.py`

The GOVERNANCE-UPGRADE-001 version of gate_check.py adds one function: `check_g1_complete()` (64 lines) + one entry in the gate map. This function ALREADY state-gates itself via ImportError.

Copy the `check_g1_complete()` function from `_staging/PKG-GOVERNANCE-UPGRADE-001/HOT/scripts/gate_check.py` (it starts around line 839) and paste it into VOCABULARY-001's version. Also add the gate map entry:

```python
"G1-COMPLETE": check_g1_complete,      # Framework completeness (Layer 2)
```

The function already handles the pre-enforcement case:
```python
try:
    from kernel.preflight import FrameworkCompletenessValidator
except ImportError:
    return GateResult(
        gate="G1-COMPLETE",
        passed=True,
        message="FrameworkCompletenessValidator not available (pre-enforcement)",
        ...
    )
```

No other changes to gate_check.py needed.

---

## Phase 3: Restructure GOVERNANCE-UPGRADE-001

GOVERNANCE-UPGRADE-001 no longer replaces any files. Update its manifest to ship only the test:

`_staging/PKG-GOVERNANCE-UPGRADE-001/manifest.json`:
```json
{
  "package_id": "PKG-GOVERNANCE-UPGRADE-001",
  "spec_id": "SPEC-GATE-001",
  "framework_id": "FMWK-000",
  "version": "1.0.0",
  "schema_version": "1.2",
  "plane_id": "hot",
  "title": "Governance Enforcement Test",
  "description": "Completeness test that verifies G1-COMPLETE gate works after frameworks are wired",
  "assets": [
    {
      "path": "HOT/tests/test_framework_completeness.py",
      "sha256": "<RECOMPUTE>",
      "classification": "test"
    }
  ],
  "dependencies": [
    "PKG-KERNEL-001",
    "PKG-VOCABULARY-001"
  ],
  "metadata": {
    "created_at": "2026-02-09T23:00:00+00:00",
    "author": "bootstrap",
    "description": "Layer 2 governance test: verifies G1-COMPLETE gate works after framework wiring"
  }
}
```

**Remove** the package_install.py and gate_check.py files from the GOVERNANCE-UPGRADE-001 staging directory (they're no longer assets of this package).

**Keep** `_staging/PKG-GOVERNANCE-UPGRADE-001/HOT/tests/test_framework_completeness.py` — recompute its SHA256 for the manifest.

---

## Phase 4: Rebuild Cascade

This is complex because THREE packages changed. Order matters.

### Step 1: KERNEL-001 rebuild

1. Recompute SHA256 of modified `_staging/PKG-KERNEL-001/HOT/scripts/package_install.py`
2. Update `_staging/PKG-KERNEL-001/manifest.json` with new hash for `HOT/scripts/package_install.py`
3. Rebuild `_staging/PKG-KERNEL-001.tar.gz`:
   ```bash
   cd _staging/PKG-KERNEL-001 && tar czf ../PKG-KERNEL-001.tar.gz $(ls)
   ```
4. Compute new KERNEL-001 archive digest:
   ```bash
   shasum -a 256 _staging/PKG-KERNEL-001.tar.gz
   ```
5. Update `_staging/PKG-GENESIS-000/HOT/config/seed_registry.json` with new KERNEL-001 digest
6. Update `Control_Plane_v2/HOT/config/seed_registry.json` (repo copy) with same digest
7. Recompute SHA256 of seed_registry.json
8. Update `_staging/PKG-GENESIS-000/manifest.json` with new seed_registry.json hash
9. Rebuild `_staging/PKG-GENESIS-000.tar.gz`:
   ```bash
   cd _staging/PKG-GENESIS-000 && tar czf ../PKG-GENESIS-000.tar.gz $(ls)
   ```

### Step 2: VOCABULARY-001 rebuild

1. Recompute SHA256 of modified `_staging/PKG-VOCABULARY-001/HOT/scripts/gate_check.py`
2. Update `_staging/PKG-VOCABULARY-001/manifest.json` with new hash for `HOT/scripts/gate_check.py`
3. Rebuild `_staging/PKG-VOCABULARY-001.tar.gz`:
   ```bash
   cd _staging/PKG-VOCABULARY-001 && tar czf ../PKG-VOCABULARY-001.tar.gz $(ls)
   ```

### Step 3: GOVERNANCE-UPGRADE-001 rebuild

1. Remove `HOT/scripts/package_install.py` and `HOT/scripts/gate_check.py` from `_staging/PKG-GOVERNANCE-UPGRADE-001/`
2. Recompute SHA256 of `_staging/PKG-GOVERNANCE-UPGRADE-001/HOT/tests/test_framework_completeness.py`
3. Update `_staging/PKG-GOVERNANCE-UPGRADE-001/manifest.json` (already written above — just fill in the SHA256)
4. Rebuild `_staging/PKG-GOVERNANCE-UPGRADE-001.tar.gz`:
   ```bash
   cd _staging/PKG-GOVERNANCE-UPGRADE-001 && tar czf ../PKG-GOVERNANCE-UPGRADE-001.tar.gz $(ls)
   ```

### Step 4: CP_BOOTSTRAP.tar.gz rebuild

1. Create a temp directory with all 8 archives:
   ```bash
   BDIR=$(mktemp -d)
   cp _staging/PKG-GENESIS-000.tar.gz "$BDIR/"
   cp _staging/PKG-KERNEL-001.tar.gz "$BDIR/"
   cp _staging/PKG-VOCABULARY-001.tar.gz "$BDIR/"
   cp _staging/PKG-REG-001.tar.gz "$BDIR/"
   cp _staging/PKG-GOVERNANCE-UPGRADE-001.tar.gz "$BDIR/"
   cp _staging/PKG-FRAMEWORK-WIRING-001.tar.gz "$BDIR/"
   cp _staging/PKG-SPEC-CONFORMANCE-001.tar.gz "$BDIR/"
   cp _staging/PKG-LAYOUT-001.tar.gz "$BDIR/"
   cd "$BDIR" && tar czf CP_BOOTSTRAP.tar.gz $(ls)
   cp CP_BOOTSTRAP.tar.gz /path/to/_staging/CP_BOOTSTRAP.tar.gz
   ```

**Important tar rule**: Do NOT use `tar czf ... -C dir .` — the `./` prefix breaks `load_manifest_from_archive()`. Use `cd dir && tar czf ... $(ls)` or `tar czf ... -C dir $(ls dir)`.

---

## Verification

### Test 1: Clean Install (all 8 packages)

```bash
TMPDIR=$(mktemp -d)
export CONTROL_PLANE_ROOT="$TMPDIR"

# Layer 0
tar xzf _staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
tar xzf "$TMPDIR/PKG-GENESIS-000.tar.gz" -C "$TMPDIR"
python3 "$TMPDIR/HOT/scripts/genesis_bootstrap.py" \
    --seed "$TMPDIR/HOT/config/seed_registry.json" \
    --archive "$TMPDIR/PKG-KERNEL-001.tar.gz"

# Layer 1
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-VOCABULARY-001.tar.gz" \
    --id PKG-VOCABULARY-001 --root "$TMPDIR" --dev
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-REG-001.tar.gz" \
    --id PKG-REG-001 --root "$TMPDIR" --dev

# Layer 2
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-GOVERNANCE-UPGRADE-001.tar.gz" \
    --id PKG-GOVERNANCE-UPGRADE-001 --root "$TMPDIR" --dev
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-FRAMEWORK-WIRING-001.tar.gz" \
    --id PKG-FRAMEWORK-WIRING-001 --root "$TMPDIR" --dev
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-SPEC-CONFORMANCE-001.tar.gz" \
    --id PKG-SPEC-CONFORMANCE-001 --root "$TMPDIR" --dev
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-LAYOUT-001.tar.gz" \
    --id PKG-LAYOUT-001 --root "$TMPDIR" --dev
```

**Expected output** for each Layer 1/2 install:
```
[install] Running G0B (system integrity)...
[install] G0B PASSED
[install] Running G0A (package declaration)...
[install] G0A PASSED
[install] Running G1 (chain)...
[install] G1 PASSED
[install] Running G1-COMPLETE (framework completeness)...
[install] G1-COMPLETE skipped (FrameworkCompletenessValidator not yet available)
                      -- OR --
[install] G1-COMPLETE PASSED (...)    [after FRAMEWORK-WIRING-001 is installed]
[install] Running G5 (signature)...
[install] G5 WAIVED (unsigned allowed)
[install] Validating installed files...
[install] Validation PASSED - all N files verified
[install] Wrote INSTALLED to ledger (system truth)
[install] Updating file_ownership.csv...
[install] Receipt: ...
```

### Test 2: file_ownership.csv Completeness + History

```bash
python3 -c "
import csv
with open('$TMPDIR/HOT/registries/file_ownership.csv') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

# Check columns exist
assert 'replaced_date' in rows[0], 'Missing replaced_date column'
assert 'superseded_by' in rows[0], 'Missing superseded_by column'

# Count active (non-superseded) entries
active = [r for r in rows if not r.get('superseded_by')]
print(f'Total entries: {len(rows)}')
print(f'Active entries: {len(active)}')
print(f'Superseded entries: {len(rows) - len(active)}')

# Every governed file should be owned
# Note: genesis_bootstrap.py writes KERNEL-001's entries separately
# package_install.py writes entries for all Layer 1+2 packages
"
```

### Test 3: Deliberate Corruption Detection (G0B)

```bash
# After clean install, corrupt a file
echo "corrupted" > "$TMPDIR/HOT/kernel/auth.py"

# Attempt another install — G0B should catch it
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-LAYOUT-001.tar.gz" \
    --id PKG-LAYOUT-001 --root "$TMPDIR" --dev 2>&1

# Expected: "G0B FAILED - system integrity compromised: Integrity mismatch: HOT/kernel/auth.py ..."
```

### Test 4: Auth Wiring (non-dev mode)

```bash
# Without --dev, should require auth
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-LAYOUT-001.tar.gz" \
    --id PKG-LAYOUT-001 --root "$TMPDIR" 2>&1

# Expected: "Authorization failed" (no token/HMAC secret configured)
```

### Test 5: Ledger Contains Full Detail

```bash
python3 -c "
import json
with open('$TMPDIR/HOT/ledger/governance.jsonl') as f:
    for line in f:
        entry = json.loads(line)
        if entry.get('event_type') == 'INSTALLED':
            pkg = entry.get('package_id', '?')
            assets = entry.get('assets', [])
            print(f'{pkg}: {len(assets)} assets in ledger entry')
            if assets:
                print(f'  First: {assets[0][\"path\"]}')
"
```

### Test 6: GOVERNANCE-UPGRADE-001 No Longer Replaces Files

```bash
# Check that GOVERNANCE-UPGRADE-001 only ships the test
python3 -c "
import json, tarfile
with tarfile.open('$TMPDIR/PKG-GOVERNANCE-UPGRADE-001.tar.gz', 'r:gz') as tf:
    members = [m.name for m in tf.getmembers() if not m.isdir()]
    print(f'Files in archive: {members}')
    assert 'HOT/scripts/package_install.py' not in members, 'Should NOT contain package_install.py!'
    assert 'HOT/scripts/gate_check.py' not in members, 'Should NOT contain gate_check.py!'
    print('PASS: No replacement files in GOVERNANCE-UPGRADE-001')
"
```

### Test 7: All Tests Pass

```bash
cd "$TMPDIR" && python3 -m pytest HOT/tests/ -v
# Expected: All pass, 0 failures
```

---

## What NOT To Do

- Do not modify genesis_bootstrap.py — that was fixed in the previous task
- Do not edit files in the live repo (Control_Plane_v2/HOT/) — only staging
- Do not change the gate ordering (G0B, G0A, G1, G1-COMPLETE, G5) — that's the correct order
- Do not remove the --dev flag — it's still needed for bootstrap
- Do not commit to git without asking
- Do not overwrite entries in file_ownership.csv — append only, use replaced_date/superseded_by
- Do not write receipt before ledger — ledger is system truth and must be written first
- Do not skip the rebuild cascade — stale hashes will break everything

---

## Summary of All Changes

| Phase | File | What | Rebuild? |
|-------|------|------|----------|
| 1 | `_staging/PKG-KERNEL-001/HOT/scripts/package_install.py` | G0B, G1-COMPLETE, backup/rollback, validate, ownership CSV, ledger-first, auth | KERNEL-001 -> seed_registry -> GENESIS-000 |
| 2 | `_staging/PKG-VOCABULARY-001/HOT/scripts/gate_check.py` | Merge G1-COMPLETE function (state-gated) | VOCABULARY-001 |
| 3 | `_staging/PKG-GOVERNANCE-UPGRADE-001/manifest.json` | Remove package_install.py + gate_check.py assets | GOVERNANCE-UPGRADE-001 |
| 3 | `_staging/PKG-GOVERNANCE-UPGRADE-001/HOT/scripts/` | Delete package_install.py + gate_check.py files | (part of above) |
| 4 | All affected .tar.gz + CP_BOOTSTRAP.tar.gz | Rebuild archives | Full cascade |

---

## TRUST TEST (Do This First, Report Results)

Complete all 5 steps. Show your work for each one. Do not summarize — show the actual answers and reasoning. If you get any wrong, stop and re-read the handoff.

### Step 1: State-Gating Understanding

The old design had GOVERNANCE-UPGRADE-001 **replacing** package_install.py and gate_check.py. Explain in your own words:

1. Why is file replacement wrong in this system? (Hint: think about what the ledger records)
2. How does G1-COMPLETE activate without replacing gate_check.py? Show the specific mechanism.
3. Name two other capabilities that are state-gated and what triggers their activation.

### Step 2: Commit Order

You just finished copying files and post-install validation passed. List the three commit operations in the correct order. For each one, explain WHY it's in that position (not just what it does).

**Wrong answer**: "receipt, then ledger" — if you wrote this, re-read Change 6.

### Step 3: file_ownership.csv Scenario

Package A owns `HOT/scripts/foo.py`. Package B is being installed and also declares `HOT/scripts/foo.py` as an asset (ownership transfer).

1. How many rows get appended to file_ownership.csv? What are they?
2. After this install, how do you determine the current owner of `HOT/scripts/foo.py`?
3. What happens to Package A's original row? (Hint: the answer is "nothing" — explain why)

### Step 4: Cascade Prediction

You've just modified `_staging/PKG-KERNEL-001/HOT/scripts/package_install.py`. List every file that must be updated and every archive that must be rebuilt, in order. Miss a step and the next clean install will fail.

**Show the full chain**: file hash → manifest → archive → parent manifest → parent archive → ...

### Step 5: Boundary Check

Answer without looking anything up:

1. You need to add the G0B function to package_install.py. Which exact file path do you edit?
2. After editing, where do you verify the change works — what directory, and how do you create it?
3. GOVERNANCE-UPGRADE-001 currently has `HOT/scripts/package_install.py` in its staging directory. What do you do with that file?

---

## After the Trust Test

Report your answers. If everything checks out, proceed to Phase 1. Work through Phases 1-4 in order — do not skip ahead. After each phase, verify before moving to the next.
