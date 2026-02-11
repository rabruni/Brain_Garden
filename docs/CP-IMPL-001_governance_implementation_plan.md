# CP-IMPL-001: Control Plane Governance Implementation Plan

**Document ID**: CP-IMPL-001
**Version**: 1.0.0
**Status**: NORMATIVE (Implementation Roadmap)
**Date**: 2026-02-02
**Plane**: HO3

---

## Executive Summary

This document defines the phased implementation plan to achieve full FMWK-000 governance compliance for Control Plane v2. The plan transforms the current state (populated HO3 with empty ownership registries) into a fully governed system where:

1. Every governed file has exactly one package owner
2. All packages are installed via package manager with ledger-first recording
3. Gates are fail-closed and enforced at install and integrity check time
4. Builder/Built firewall prevents runtime artifacts from modifying the control plane
5. Work Orders govern all changes with Git PR approval model
6. Genesis bootstrap is the only exception, sealed after first use

---

## Binding Constraints (NON-NEGOTIABLE)

These constraints apply to ALL phases and MUST NOT drift:

### Hash Format Standard
- ALL hashes use format: `sha256:<64-character-hex>`
- Applies to: manifests, baseline, registries, gates, ledger entries
- Example: `sha256:a1b2c3d4e5f6...` (64 hex chars after colon)

### Install Destinations
- **Governed assets**: Pristine roots (`frameworks/`, `specs/`, `lib/`, `scripts/`, `registries/`, `modules/`, `schemas/`, `policies/`, `tests/`, `docs/`, `gates/`)
- **Package receipts**: `installed/<pkg_id>/receipt.json`, `installed/<pkg_id>/manifest.json`
- **Package archives**: `packages_store/<pkg_id>.tar.gz`

### Two-Class Registry Model

| Class | Examples | Source of Truth | Mutation Method |
|-------|----------|-----------------|-----------------|
| **Derived State** | `registries/file_ownership.csv`, `registries/packages_state.csv`, `registries/compiled/*.json` | Ledger + installed manifests | `rebuild_derived_registries.py` only |
| **Curated Governance** | `registries/control_plane_registry.csv`, `registries/specs_registry.csv`, `registries/frameworks_registry.csv` | The file itself (law) | Work Order only |

### Manifest Schema
- EXTEND existing `schemas/package_manifest.json` (no fork)
- New fields: `install_targets[]`, `asset_classification{}`
- Backward compatibility: If `install_targets` absent, emit deprecation warning, use legacy flat install
- Fail-closed on ambiguous mappings

### Two-Phase Ledger Install
| Event | Trigger | Meaning |
|-------|---------|---------|
| `INSTALL_STARTED` | Before workspace creation | Intent recorded |
| `INSTALLED` | After atomic commit succeeds | Success |
| `INSTALL_FAILED` | On any failure | Failure recorded with error |

### Ownership Semantics
- **No last-write-wins**: Asset takeover requires explicit upgrade/migration policy
- **Conflict = FAIL**: Two packages claiming same file without upgrade policy is fatal
- **Rebuild detects conflicts**: `rebuild_derived_registries.py` must detect and report conflicts

### G0 Split
- **G0A (Package Declaration)**: At package install pre-commit — "every file being installed is declared in manifest + hashes match archive"
- **G0B (Plane Ownership)**: At integrity/seal check — "every governed file is owned by exactly one package + hash matches"

### Seal Trigger
- Seal ONLY after: baseline installed + derived registries rebuilt + G0B passes
- Baseline refresh post-seal requires Work Order type `baseline_refresh`

### Phase 1 HO3-Only Scope (Added 2026-02-02)
- **All Phase 1 operations are HO3 governance context only**
- HO3 owns: packages, gates, installs, L-PACKAGE ledger writes
- Do NOT implicitly touch HO2/HO1 state
- Aligns to CP-ARCH-001: tier roles/authority, immutable installs, ledger is memory

### Explicit Baseline Refresh Authority (Added 2026-02-02)
- Pre-seal: baseline install is the single bootstrap exception
- Post-seal: ANY baseline refresh requires Work Order with `type: baseline_refresh`
- Enforced via policy + gate validation, NOT just a script flag
- `install_baseline.py` MUST validate WO type if sealed

### Ledger is Memory (Added 2026-02-02)
- Baseline install and package installs MUST write canonical L-PACKAGE events
- Event sequence: `INSTALL_STARTED` → `INSTALLED` | `INSTALL_FAILED`
- Events written to HO3 ledger (`ledger/packages.jsonl`)
- Receipts are proof; ledger is the truth spine
- Receipt without ledger entry is invalid state

### Turn Isolation / Declared Inputs (Added 2026-02-02)
- Baseline manifest MUST record declared scan inputs as metadata:
  - `scan_roots`: Array of scanned directories
  - `exclusion_patterns`: Array of excluded patterns
  - `hash_algorithm`: Algorithm used (e.g., "sha256")
  - `hash_format_version`: Format version (e.g., "1.0")
- Metadata is explicitly EXCLUDED from manifest_hash computation
- `install_baseline.py` MUST verify it uses only declared inputs from manifest

---

## Phase 0: Gap Analysis

### Component Assessment

| Component | Files | What Works Now | Gaps vs Constraints | Fix Type | Acceptance Criteria |
|-----------|-------|----------------|---------------------|----------|---------------------|
| **Package Install** | `scripts/package_install.py`, `lib/packages.py` | Hash verification, signature check, receipt writing, plane-aware | No namespaced targets, writes registry directly (not projection), gates not enforced, no two-phase ledger | REFACTOR | Install to pristine roots, INSTALL_STARTED→INSTALLED, G0A enforced |
| **Package Pack** | `scripts/package_pack.py` | Deterministic tar.gz, SHA256, signing | No manifest v1.1 `install_targets[]`, updates registry directly | REFACTOR | Manifest includes `install_targets[]`, registry untouched |
| **Package Uninstall** | `scripts/package_uninstall.py` | Re-packs to store, removes from installed/ | No dependent check (violates fail-closed), no ledger UNINSTALL event | REFACTOR | Fail if dependents exist, write UNINSTALLED to ledger |
| **Gate Check** | `scripts/gate_check.py` | G0-G6 structure, governed_roots.json, chain stub | Gates informational only, not integrated into install, G2-G6 stubs | REFACTOR | G0A/G0B split, `--enforce` mode, integrated into install |
| **Ledger Client** | `lib/ledger_client.py`, `lib/ledger_factory.py` | Hash chaining, append-only, rotation, Merkle, TierContext | Missing INSTALL_STARTED/FAILED event types | TWEAK | Add event types |
| **Workspace** | `lib/workspace.py` | IsolatedWorkspace ctx mgr, quarantine, audit log | Not used by package_install.py or apply_work_order.py | TWEAK | Integrate into install and WO flows |
| **Atomic** | `lib/atomic.py` | AtomicTransaction ctx mgr, staging+rename, rollback, git | ALIGNED | NONE | — |
| **Work Order Apply** | `scripts/apply_work_order.py` | WO discovery, gate sequence, idempotency check | Gates not fail-closed, workspace not used, no atomic integration | REFACTOR | Fail-closed gates, workspace execution, atomic commit |
| **Genesis Bootstrap** | `scripts/genesis_bootstrap.py` | Self-contained, seed_registry.json, HMAC verify | No L-PACKAGE GENESIS entry, no chain init, no seal | TWEAK | Write GENESIS, seal after first package |
| **Pristine** | `lib/pristine.py` | PathClass enum, WriteMode, InstallModeContext | No BUILT marker tracking, no firewall enforcement | REFACTOR | BUILT markers in receipts, G-FIREWALL integration |
| **Gate Operations** | `lib/gate_operations.py` | CRUD with ledger, authz checks | Uses registry directly, no namespaced paths | REFACTOR | Operations via gates, namespaced paths |
| **Registry** | `lib/registry.py`, `registries/*.csv` | CSV read/write, schema validation | Registry is source of truth (should be projection for state), direct mutations | REFACTOR | Derived registries rebuilt only, curated via WO |
| **Ownership Registries** | `registries/file_ownership.csv` | Does not exist | G0 cannot pass, no ownership tracking | CREATE | Derived from ledger+manifests, conflict detection |

### Current State Summary
- **HO3 file count**: ~92 governed files
- **Ownership registry**: Empty (0 files tracked)
- **G0 status**: Cannot pass (no ownership data)
- **Seal status**: Unsealed (pre-bootstrap)

---

## Phase 1: Baseline Sealing + Aligned Package Model

### Goal
Establish ownership of all existing HO3 files via baseline package, enable G0 to pass, make plane usable for subsequent package installs.

### Deliverables

| Action | File | Purpose |
|--------|------|---------|
| CREATE | `scripts/generate_baseline_manifest.py` | Deterministic baseline manifest generator |
| CREATE | `scripts/install_baseline.py` | Baseline package installer |
| CREATE | `scripts/rebuild_derived_registries.py` | Rebuild derived state from ledger+manifests |
| CREATE | `registries/file_ownership.csv` | Derived file ownership registry |
| CREATE | `packages_store/PKG-BASELINE-HO3-000.tar.gz` | Baseline package artifact |
| CREATE | `installed/PKG-BASELINE-HO3-000/` | Baseline receipt directory |
| CREATE | `config/seal.json` | Seal status marker |
| CREATE | `tests/test_phase1_baseline.py` | Phase 1 acceptance tests |
| MODIFY | `schemas/package_manifest.json` | Add `install_targets[]`, `asset_classification{}` |
| MODIFY | `scripts/package_install.py` | Namespaced install, two-phase ledger, workspace, G0A |
| MODIFY | `scripts/gate_check.py` | G0A/G0B split, `--enforce` mode |
| MODIFY | `lib/ledger_client.py` | Add INSTALL_STARTED, INSTALL_FAILED event types |

### Detailed Specifications

#### 1.1 Baseline Manifest Generator

**File**: `scripts/generate_baseline_manifest.py`

**Behavior**:
- Scans all pristine roots for governed files
- Produces deterministic manifest (sorted paths, no timestamps in hashed content)
- Computes `sha256:<64hex>` for each file
- Classifies each asset by path pattern
- Outputs manifest.json to specified directory

**Asset Classification Rules**:
```python
CLASSIFICATION_PATTERNS = {
    r"^frameworks/.*\.md$": "law_doc",
    r"^specs/.*/manifest\.yaml$": "spec_manifest",
    r"^specs/.*": "spec_asset",
    r"^lib/.*\.py$": "library",
    r"^scripts/.*\.py$": "script",
    r"^scripts/.*\.sh$": "script",
    r"^registries/.*\.csv$": "registry",
    r"^registries/compiled/.*\.json$": "compiled_registry",
    r"^schemas/.*\.json$": "schema",
    r"^policies/.*\.yaml$": "policy",
    r"^tests/.*\.py$": "test",
    r"^docs/.*\.md$": "documentation",
    r"^modules/.*": "module",
    r"^gates/.*\.py$": "gate",
}
```

**Manifest Schema** (extends package_manifest.json):
```json
{
  "package_id": "PKG-BASELINE-HO3-000",
  "version": "1.0.0",
  "plane_id": "ho3",
  "package_type": "baseline",
  "install_targets": [
    {
      "namespace": "lib",
      "target_id": "core",
      "files": ["paths.py", "output.py", "cursor.py"]
    }
  ],
  "assets": [
    {
      "path": "lib/paths.py",
      "sha256": "sha256:a1b2c3...",
      "classification": "library"
    }
  ],
  "dependencies": [],
  "metadata": {
    "generated_at": "2026-02-02T00:00:00Z",
    "generator_version": "1.0.0"
  }
}
```

**Note**: `metadata.generated_at` is explicitly EXCLUDED from manifest_hash computation.

**Manifest Hash Computation**:
```python
def compute_manifest_hash(manifest: dict) -> str:
    """Compute deterministic hash excluding metadata block."""
    hashable = {k: v for k, v in manifest.items() if k != "metadata"}
    canonical = json.dumps(hashable, sort_keys=True, separators=(',', ':'))
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
```

#### 1.2 Baseline Package Creation

**File**: `packages_store/PKG-BASELINE-HO3-000.tar.gz`

**Contents**:
```
PKG-BASELINE-HO3-000/
├── manifest.json          # Package manifest
├── checksums.sha256       # All file hashes (redundant verification)
└── signature.json         # Optional for now; required post-Phase 3
```

**Note**: Baseline package does NOT contain the actual files (they already exist in pristine roots). It contains only the manifest claiming ownership.

#### 1.3 Baseline Installation

**File**: `scripts/install_baseline.py`

**Pre-conditions**:
- Plane is unsealed, OR
- Work Order of type `baseline_refresh` is approved

**Algorithm**:
```
1. Check seal status
   IF sealed AND no WO → FAIL "Plane sealed, baseline_refresh WO required"
   IF sealed AND WO.type != baseline_refresh → FAIL "Wrong WO type"

2. Extract baseline package from packages_store/
3. Load manifest.json

4. Write INSTALL_STARTED to L-PACKAGE
   {
     "event_type": "INSTALL_STARTED",
     "package_id": "PKG-BASELINE-HO3-000",
     "package_type": "baseline",
     "plane_id": "ho3",
     "timestamp": "<ISO8601>"
   }

5. Verify every claimed file exists with matching hash
   FOR each asset in manifest.assets:
     IF file does not exist → INSTALL_FAILED, FAIL
     IF hash mismatch → INSTALL_FAILED, FAIL

6. Check for ownership conflicts (should be none for initial baseline)
   current_ownership = load_file_ownership()
   FOR each asset in manifest.assets:
     IF asset.path in current_ownership:
       IF current_ownership[asset.path].owner != manifest.package_id:
         → INSTALL_FAILED, FAIL "Conflict: {path} owned by {owner}"

7. Write receipt
   installed/PKG-BASELINE-HO3-000/receipt.json
   installed/PKG-BASELINE-HO3-000/manifest.json

8. Write INSTALLED to L-PACKAGE
   {
     "event_type": "INSTALLED",
     "package_id": "PKG-BASELINE-HO3-000",
     "manifest_hash": "sha256:...",
     "assets_count": 92,
     "timestamp": "<ISO8601>"
   }

9. Rebuild derived registries
   run rebuild_derived_registries.py

10. Run G0B check
    IF G0B fails → WARNING (log but don't fail install)

11. IF all passed AND unsealed:
    Write seal marker
    config/seal.json = {"sealed": true, "sealed_at": "<ISO8601>", "sealed_by": "PKG-BASELINE-HO3-000"}
```

#### 1.4 Derived Registry Rebuilder

**File**: `scripts/rebuild_derived_registries.py`

**Derived Registries** (rebuilt):
- `registries/file_ownership.csv`
- `registries/packages_state.csv`
- `registries/compiled/packages.json`
- `registries/compiled/file_ownership.json`

**Curated Registries** (NEVER touched):
- `registries/control_plane_registry.csv`
- `registries/specs_registry.csv`
- `registries/frameworks_registry.csv`

**Algorithm**:
```
1. Read L-PACKAGE ledger chronologically
2. Build ownership map with conflict detection:

   ownership = {}
   conflicts = []

   FOR entry in ledger:
     IF entry.event_type == "INSTALLED":
       manifest = load_manifest(entry.package_id)
       FOR asset in manifest.assets:
         IF asset.path in ownership:
           existing = ownership[asset.path]
           IF existing.package_id != entry.package_id:
             # Check for upgrade policy
             IF not is_upgrade_allowed(existing.package_id, entry.package_id):
               conflicts.append({
                 "path": asset.path,
                 "current_owner": existing.package_id,
                 "conflicting_owner": entry.package_id
               })
             ELSE:
               # Upgrade allowed, replace
               ownership[asset.path] = {...}
         ELSE:
           ownership[asset.path] = {
             "file_path": asset.path,
             "owner_package_id": entry.package_id,
             "sha256": asset.sha256,
             "classification": asset.classification,
             "installed_at": entry.timestamp
           }

     ELIF entry.event_type == "UNINSTALLED":
       manifest = load_manifest(entry.package_id)
       FOR asset in manifest.assets:
         IF ownership.get(asset.path, {}).get("owner_package_id") == entry.package_id:
           del ownership[asset.path]

3. IF conflicts:
   FAIL with conflict report

4. Write derived registries atomically
```

**file_ownership.csv Schema**:
```csv
file_path,owner_package_id,sha256,classification,installed_at
lib/paths.py,PKG-BASELINE-HO3-000,sha256:a1b2c3...,library,2026-02-02T00:00:00Z
```

#### 1.5 G0 Gate Split

**G0A: Package Declaration Check**

**When**: Package install pre-commit (in workspace)
**Purpose**: Verify package is internally consistent

**Checks**:
1. Every file in archive is declared in `manifest.assets[]`
2. Every declared asset hash matches archive file hash
3. `install_targets[]` paths are valid namespaces
4. No path escapes (no `..`, no absolute paths)

**Implementation**:
```python
def gate_g0a_package_declaration(archive_path: Path, manifest: dict) -> tuple[bool, str]:
    errors = []

    # Check 1: All archive files declared
    archive_files = list_archive_contents(archive_path)
    declared_paths = {a["path"] for a in manifest.get("assets", [])}

    for af in archive_files:
        if af not in declared_paths and af != "manifest.json" and af != "signature.json":
            errors.append(f"UNDECLARED: {af} in archive but not in manifest")

    # Check 2: Declared hashes match
    for asset in manifest.get("assets", []):
        archive_hash = compute_hash_in_archive(archive_path, asset["path"])
        if archive_hash != asset["sha256"]:
            errors.append(f"HASH_MISMATCH: {asset['path']} manifest={asset['sha256'][:16]}... archive={archive_hash[:16]}...")

    # Check 3: Valid namespaces
    valid_namespaces = {"frameworks", "specs", "lib", "scripts", "gates", "schemas", "policies", "modules", "tests", "docs", "registries"}
    for target in manifest.get("install_targets", []):
        if target["namespace"] not in valid_namespaces:
            errors.append(f"INVALID_NAMESPACE: {target['namespace']}")

    # Check 4: No path escapes
    for asset in manifest.get("assets", []):
        if ".." in asset["path"] or asset["path"].startswith("/"):
            errors.append(f"PATH_ESCAPE: {asset['path']}")

    if errors:
        return False, f"G0A FAILED: {len(errors)} issues\n" + "\n".join(errors)
    return True, f"G0A PASSED: {len(manifest.get('assets', []))} assets verified"
```

**G0B: Plane Ownership Check**

**When**: Integrity check, seal check, pre-install validation
**Purpose**: Verify plane is fully governed

**Checks**:
1. Every file in governed roots is owned by exactly one package
2. Every owned file exists with matching hash
3. No orphan files in governed roots

**Implementation**:
```python
def gate_g0b_plane_ownership(plane: str) -> tuple[bool, str]:
    errors = []
    governed_roots = load_governed_roots(plane)
    ownership = load_file_ownership_registry()

    # Check 1: Every governed file is owned
    for root in governed_roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for path in root_path.rglob("*"):
            if path.is_file() and not is_excluded(path):
                rel_path = str(path.relative_to("."))
                if rel_path not in ownership:
                    errors.append(f"ORPHAN: {rel_path} has no owner")

    # Check 2: Every owned file exists with correct hash
    for file_path, entry in ownership.items():
        path = Path(file_path)
        if not path.exists():
            errors.append(f"MISSING: {file_path} owned by {entry['owner_package_id']} does not exist")
        else:
            actual_hash = f"sha256:{compute_sha256(path)}"
            if actual_hash != entry["sha256"]:
                errors.append(f"HASH_MISMATCH: {file_path} expected {entry['sha256'][:24]}... got {actual_hash[:24]}...")

    if errors:
        return False, f"G0B FAILED: {len(errors)} issues\n" + "\n".join(errors[:20])
    return True, f"G0B PASSED: {len(ownership)} files owned, 0 orphans"
```

#### 1.6 Updated Package Install

**File**: `scripts/package_install.py`

**Key Changes**:
1. Extract assets to pristine roots (not installed/)
2. Write receipt to installed/<pkg_id>/
3. Two-phase ledger (INSTALL_STARTED → INSTALLED/FAILED)
4. Use workspace for file staging
5. Use atomic transaction for commit
6. Run G0A before commit
7. Check ownership conflicts

**Algorithm**:
```
1. Validate inputs
   - Archive exists
   - Work Order provided and approved (or pre-seal exception)

2. Extract manifest from archive
3. Run G0A(archive, manifest)
   IF FAIL → return error (no ledger entry yet)

4. Write INSTALL_STARTED to L-PACKAGE

5. Create IsolatedWorkspace
   TRY:
     # Check ownership conflicts
     current_ownership = load_file_ownership()
     FOR asset in manifest.assets:
       IF asset.path in current_ownership:
         IF current_ownership[asset.path].owner != manifest.package_id:
           IF not is_upgrade_allowed(...):
             RAISE OwnershipConflict

     # Stage files to workspace
     FOR target in manifest.install_targets:
       dest_dir = workspace / target.namespace / target.target_id
       FOR file in target.files:
         stage_file(archive/file, dest_dir/file)

     # Verify staged files match manifest
     FOR asset in manifest.assets:
       staged = workspace / asset.path
       IF compute_hash(staged) != asset.sha256:
         RAISE HashMismatch

     # Run G5 (signature) if required
     IF is_sealed():
       run_gate_g5(manifest)

     # Atomic commit
     WITH AtomicTransaction:
       workspace.commit_to_pristine_roots()
       write_receipt(manifest)
       write_manifest_copy(manifest)

   EXCEPT Exception as e:
     Write INSTALL_FAILED to L-PACKAGE
     RAISE

6. Write INSTALLED to L-PACKAGE

7. Rebuild derived registries
```

### Gates Activated

| Gate | Where Enforced | Mode |
|------|----------------|------|
| G0A | `package_install.py` pre-ledger | FAIL-CLOSED |
| G0B | `integrity_check.py --verify` | FAIL-CLOSED |
| G0B | `install_baseline.py` post-install | WARNING (log only) |
| G5 | `package_install.py` post-seal | FAIL-CLOSED |

### Acceptance Tests

**File**: `tests/test_phase1_baseline.py`

```python
import pytest
from pathlib import Path
import json
import csv

class TestBaselineManifestGeneration:
    """Tests for generate_baseline_manifest.py"""

    def test_manifest_deterministic(self, tmp_path):
        """Two runs on identical tree produce identical manifest_hash."""
        # Run generator twice
        manifest1 = generate_baseline_manifest("ho3", output=tmp_path / "m1")
        manifest2 = generate_baseline_manifest("ho3", output=tmp_path / "m2")

        hash1 = compute_manifest_hash(manifest1)
        hash2 = compute_manifest_hash(manifest2)
        assert hash1 == hash2

    def test_manifest_covers_all_governed_files(self):
        """Every file in governed roots appears in manifest."""
        manifest = generate_baseline_manifest("ho3")
        governed = set(list_governed_files("ho3"))
        manifest_paths = {a["path"] for a in manifest["assets"]}

        missing = governed - manifest_paths
        assert missing == set(), f"Missing from manifest: {missing}"

    def test_hash_format_standardized(self):
        """All hashes use sha256:<64hex> format."""
        manifest = generate_baseline_manifest("ho3")
        for asset in manifest["assets"]:
            assert asset["sha256"].startswith("sha256:")
            assert len(asset["sha256"]) == 7 + 64  # "sha256:" + 64 hex

    def test_metadata_excluded_from_hash(self):
        """metadata.generated_at does not affect manifest_hash."""
        manifest1 = generate_baseline_manifest("ho3")
        manifest1["metadata"]["generated_at"] = "2026-01-01T00:00:00Z"

        manifest2 = generate_baseline_manifest("ho3")
        manifest2["metadata"]["generated_at"] = "2099-12-31T23:59:59Z"

        assert compute_manifest_hash(manifest1) == compute_manifest_hash(manifest2)


class TestBaselinePackageCreation:
    """Tests for baseline package artifact."""

    def test_baseline_package_exists(self):
        """Baseline package tar exists in packages_store."""
        assert Path("packages_store/PKG-BASELINE-HO3-000.tar.gz").exists()

    def test_baseline_package_contains_manifest(self):
        """Baseline tar contains manifest.json."""
        contents = list_tar_contents("packages_store/PKG-BASELINE-HO3-000.tar.gz")
        assert "PKG-BASELINE-HO3-000/manifest.json" in contents


class TestBaselineInstallation:
    """Tests for install_baseline.py"""

    def test_install_pre_seal_succeeds(self, fresh_plane):
        """Baseline installs when plane is unsealed."""
        result = install_baseline("ho3")
        assert result.success
        assert Path("installed/PKG-BASELINE-HO3-000/receipt.json").exists()

    def test_install_blocked_post_seal_without_wo(self, sealed_plane):
        """Baseline install requires WO after seal."""
        with pytest.raises(SealedPlaneError, match="baseline_refresh WO required"):
            install_baseline("ho3")

    def test_install_writes_two_phase_ledger(self, fresh_plane):
        """Install writes INSTALL_STARTED then INSTALLED."""
        install_baseline("ho3")
        entries = list(read_ledger("ledger/packages.jsonl"))

        # Find our entries
        our_entries = [e for e in entries if e.get("package_id") == "PKG-BASELINE-HO3-000"]
        assert len(our_entries) >= 2
        assert our_entries[-2]["event_type"] == "INSTALL_STARTED"
        assert our_entries[-1]["event_type"] == "INSTALLED"

    def test_install_creates_seal(self, fresh_plane):
        """Baseline install seals the plane."""
        install_baseline("ho3")
        assert Path("config/seal.json").exists()
        seal = json.loads(Path("config/seal.json").read_text())
        assert seal["sealed"] is True

    def test_install_fails_on_missing_file(self, fresh_plane, monkeypatch):
        """Install fails if claimed file missing."""
        # Remove a file temporarily
        Path("lib/paths.py").rename("lib/paths.py.bak")
        try:
            with pytest.raises(InstallError, match="does not exist"):
                install_baseline("ho3")

            # Verify INSTALL_FAILED written
            entries = list(read_ledger("ledger/packages.jsonl"))
            failed = [e for e in entries if e.get("event_type") == "INSTALL_FAILED"]
            assert len(failed) > 0
        finally:
            Path("lib/paths.py.bak").rename("lib/paths.py")

    def test_install_fails_on_hash_mismatch(self, fresh_plane):
        """Install fails if file hash doesn't match."""
        original = Path("lib/paths.py").read_text()
        Path("lib/paths.py").write_text(original + "\n# tampered")
        try:
            with pytest.raises(InstallError, match="hash mismatch"):
                install_baseline("ho3")
        finally:
            Path("lib/paths.py").write_text(original)


class TestG0AfterBaseline:
    """Tests for G0B after baseline installation."""

    def test_g0b_passes_after_baseline(self, baseline_installed):
        """G0B passes with zero orphans after baseline."""
        result, msg = gate_g0b_plane_ownership("ho3")
        assert result is True
        assert "0 orphans" in msg

    def test_g0b_fails_on_orphan(self, baseline_installed):
        """G0B fails if unowned file exists in governed root."""
        Path("lib/rogue.py").write_text("# orphan file")
        try:
            result, msg = gate_g0b_plane_ownership("ho3")
            assert result is False
            assert "ORPHAN: lib/rogue.py" in msg
        finally:
            Path("lib/rogue.py").unlink()

    def test_g0b_fails_on_hash_mismatch(self, baseline_installed):
        """G0B fails if owned file is modified."""
        original = Path("lib/paths.py").read_text()
        Path("lib/paths.py").write_text("# completely different content")
        try:
            result, msg = gate_g0b_plane_ownership("ho3")
            assert result is False
            assert "HASH_MISMATCH: lib/paths.py" in msg
        finally:
            Path("lib/paths.py").write_text(original)


class TestDerivedRegistryRebuild:
    """Tests for rebuild_derived_registries.py"""

    def test_rebuild_creates_file_ownership(self, baseline_installed):
        """Rebuild creates file_ownership.csv."""
        Path("registries/file_ownership.csv").unlink(missing_ok=True)
        rebuild_derived_registries("ho3")
        assert Path("registries/file_ownership.csv").exists()

    def test_rebuild_is_idempotent(self, baseline_installed):
        """Multiple rebuilds produce identical output."""
        rebuild_derived_registries("ho3")
        content1 = Path("registries/file_ownership.csv").read_text()

        rebuild_derived_registries("ho3")
        content2 = Path("registries/file_ownership.csv").read_text()

        assert content1 == content2

    def test_rebuild_detects_conflicts(self, baseline_installed):
        """Rebuild fails if two packages claim same file without upgrade policy."""
        # Manually create conflicting ledger entry
        append_to_ledger("ledger/packages.jsonl", {
            "event_type": "INSTALLED",
            "package_id": "PKG-CONFLICT-001",
            # ... manifest claims lib/paths.py
        })

        with pytest.raises(OwnershipConflict):
            rebuild_derived_registries("ho3")

    def test_rebuild_never_touches_curated(self, baseline_installed):
        """Curated registries are never modified by rebuild."""
        original = Path("registries/control_plane_registry.csv").read_text()
        rebuild_derived_registries("ho3")
        after = Path("registries/control_plane_registry.csv").read_text()
        assert original == after

    def test_rebuild_verify_mode(self, baseline_installed):
        """--verify mode compares without writing."""
        result = rebuild_derived_registries("ho3", verify_only=True)
        assert result.matches is True


class TestPackageInstallNamespaced:
    """Tests for updated package_install.py"""

    def test_assets_go_to_pristine_roots(self, baseline_installed, test_package_tar):
        """Package assets install to pristine roots."""
        install_package(test_package_tar, work_order_id="WO-TEST-001")
        assert Path("frameworks/FMWK-TEST-001/FMWK-TEST-001.md").exists()

    def test_receipt_goes_to_installed(self, baseline_installed, test_package_tar):
        """Receipt goes to installed/<pkg>/."""
        install_package(test_package_tar, work_order_id="WO-TEST-001")
        assert Path("installed/PKG-TEST-001/receipt.json").exists()
        assert Path("installed/PKG-TEST-001/manifest.json").exists()

    def test_g0a_blocks_undeclared_file(self, baseline_installed, package_with_extra_file):
        """G0A fails if archive contains undeclared file."""
        with pytest.raises(GateError, match="G0A FAILED.*UNDECLARED"):
            install_package(package_with_extra_file, work_order_id="WO-TEST-002")

    def test_ownership_conflict_fails(self, baseline_installed, conflicting_package):
        """Install fails if file already owned without upgrade policy."""
        with pytest.raises(OwnershipConflict):
            install_package(conflicting_package, work_order_id="WO-TEST-003")
```

### CLI Verification Sequence

```bash
# === Phase 1 CLI Verification ===

# 1. Generate baseline manifest
python3 scripts/generate_baseline_manifest.py --plane ho3 --output packages_store/PKG-BASELINE-HO3-000/
echo "Asset count:"
cat packages_store/PKG-BASELINE-HO3-000/manifest.json | jq '.assets | length'

# 2. Verify hash format
cat packages_store/PKG-BASELINE-HO3-000/manifest.json | jq '.assets[0].sha256'
# → "sha256:a1b2c3d4..."

# 3. Verify determinism
python3 scripts/generate_baseline_manifest.py --plane ho3 --output /tmp/baseline1/
python3 scripts/generate_baseline_manifest.py --plane ho3 --output /tmp/baseline2/
python3 -c "
import json
m1 = json.load(open('/tmp/baseline1/manifest.json'))
m2 = json.load(open('/tmp/baseline2/manifest.json'))
from scripts.generate_baseline_manifest import compute_manifest_hash
print(f'Hash 1: {compute_manifest_hash(m1)}')
print(f'Hash 2: {compute_manifest_hash(m2)}')
print(f'Match: {compute_manifest_hash(m1) == compute_manifest_hash(m2)}')
"

# 4. Create baseline package tar
cd packages_store && tar -czf PKG-BASELINE-HO3-000.tar.gz PKG-BASELINE-HO3-000/ && cd ..

# 5. Install baseline
python3 scripts/install_baseline.py --plane ho3
echo "Receipt exists:"
ls installed/PKG-BASELINE-HO3-000/

# 6. Verify ledger entries
echo "Ledger entries:"
tail -3 ledger/packages.jsonl | jq -r '.event_type'

# 7. Verify seal
cat config/seal.json | jq '.'

# 8. Verify derived registry created
head -3 registries/file_ownership.csv

# 9. Run G0B
python3 scripts/gate_check.py --gate G0B --plane ho3 --enforce
echo "Exit code: $?"

# 10. Test orphan detection
echo "# rogue" > lib/rogue.py
python3 scripts/gate_check.py --gate G0B --plane ho3 --enforce || echo "G0B correctly failed"
rm lib/rogue.py

# 11. Test hash mismatch detection
cp lib/paths.py lib/paths.py.bak
echo "# tampered" >> lib/paths.py
python3 scripts/gate_check.py --gate G0B --plane ho3 --enforce || echo "G0B correctly failed"
mv lib/paths.py.bak lib/paths.py

# 12. Verify rebuild is idempotent
python3 scripts/rebuild_derived_registries.py --plane ho3 --verify
echo "Exit code: $?"

# 13. Run all Phase 1 tests
pytest tests/test_phase1_baseline.py -v
```

### Done Criteria

| Criterion | Verification Command | Expected |
|-----------|---------------------|----------|
| Baseline manifest generator exists | `ls scripts/generate_baseline_manifest.py` | File exists |
| Manifest is deterministic | Two runs produce same hash | Hash match |
| Hash format is `sha256:<64hex>` | `jq '.assets[0].sha256'` | Starts with "sha256:" |
| Baseline package exists | `ls packages_store/PKG-BASELINE-HO3-000.tar.gz` | File exists |
| Baseline installed | `ls installed/PKG-BASELINE-HO3-000/receipt.json` | File exists |
| Ledger has INSTALL_STARTED + INSTALLED | `grep PKG-BASELINE packages.jsonl \| wc -l` | ≥ 2 |
| Seal created | `cat config/seal.json \| jq '.sealed'` | `true` |
| file_ownership.csv exists | `ls registries/file_ownership.csv` | File exists |
| G0B passes | `gate_check.py --gate G0B --enforce; echo $?` | 0 |
| Orphan detected | Add rogue file, run G0B | FAIL |
| Hash mismatch detected | Modify file, run G0B | FAIL |
| Rebuild is idempotent | `--verify` mode | Match |
| Curated registries untouched | Compare before/after | Identical |
| All pytest pass | `pytest tests/test_phase1_baseline.py` | 0 |

### Risks and Edge Cases

| Risk | Mitigation |
|------|------------|
| Baseline includes files that shouldn't be governed | `governed_roots.json` allowlist + explicit exclusion patterns |
| Determinism broken by floating metadata | `metadata` block excluded from hash computation |
| Existing orphan files block baseline | Must clean up orphans BEFORE baseline install OR add to baseline manifest |
| Hash algorithm changes | `sha256:` prefix allows future algorithm upgrades |
| Rebuild conflicts on edge cases | Explicit conflict detection, not last-write-wins |
| Bootstrap deadlock (G0B fails, can't install baseline to fix) | G0A/G0B split: baseline only needs G0A (self-consistency) |

---

## Phase 2: Gate Enforcement + Workspace Integration

### Goal
Make gates fail-closed and integrate workspace isolation into package install and work order execution flows.

### Deliverables

| Action | File | Purpose |
|--------|------|---------|
| CREATE | `lib/gate_sequence.py` | Orchestrate G0→G1→G2→G3→G4→G5→G6 with fail-fast |
| CREATE | `tests/test_phase2_gates.py` | Phase 2 acceptance tests |
| MODIFY | `scripts/gate_check.py` | Add `--enforce` mode (exit 1 on fail) |
| MODIFY | `scripts/package_install.py` | Full workspace integration |
| MODIFY | `scripts/apply_work_order.py` | Use workspace + atomic + gates |
| MODIFY | `lib/workspace.py` | Add `commit_to_pristine_roots()` method |

### Detailed Specifications

#### 2.1 Gate Sequence Orchestrator

**File**: `lib/gate_sequence.py`

```python
GATE_ORDER = ["G0A", "G0B", "G1", "G2", "G3", "G4", "G5", "G6"]

GATE_APPLICABILITY = {
    "package_install": ["G0A", "G1", "G5"],
    "work_order_apply": ["G0B", "G1", "G2", "G3", "G4", "G5", "G6"],
    "integrity_check": ["G0B", "G1"],
}

def run_gate_sequence(context: str, **kwargs) -> tuple[bool, list[str]]:
    """Run applicable gates in order, fail-fast on first failure."""
    applicable = GATE_APPLICABILITY.get(context, [])
    results = []

    for gate_name in GATE_ORDER:
        if gate_name not in applicable:
            continue

        gate_fn = get_gate_function(gate_name)
        passed, message = gate_fn(**kwargs)
        results.append({"gate": gate_name, "passed": passed, "message": message})

        if not passed:
            return False, results  # Fail-fast

    return True, results
```

#### 2.2 Updated Package Install with Workspace

```python
def install_package(archive_path: Path, work_order_id: str) -> InstallResult:
    manifest = extract_manifest(archive_path)
    pkg_id = manifest["package_id"]

    # Pre-flight: G0A (no ledger entry yet)
    passed, msg = gate_g0a_package_declaration(archive_path, manifest)
    if not passed:
        raise GateError(f"G0A: {msg}")

    # Record intent
    append_to_ledger("packages.jsonl", {
        "event_type": "INSTALL_STARTED",
        "package_id": pkg_id,
        "work_order_id": work_order_id,
    })

    try:
        with IsolatedWorkspace(base_dir=get_plane_path()) as ws:
            # Stage all files
            for target in manifest["install_targets"]:
                dest_dir = ws.path / target["namespace"]
                for file in target["files"]:
                    ws.stage_from_archive(archive_path, file, dest_dir / file)

            # Verify hashes in workspace
            for asset in manifest["assets"]:
                staged = ws.path / asset["path"]
                actual = f"sha256:{compute_sha256(staged)}"
                if actual != asset["sha256"]:
                    raise HashMismatchError(asset["path"], asset["sha256"], actual)

            # Run G1 (chain validation)
            passed, msg = gate_g1_chain(manifest)
            if not passed:
                raise GateError(f"G1: {msg}")

            # Run G5 (signature) if sealed
            if is_sealed():
                passed, msg = gate_g5_signature(archive_path, manifest)
                if not passed:
                    raise GateError(f"G5: {msg}")

            # Atomic commit
            with AtomicTransaction(get_plane_path()) as tx:
                # Copy from workspace to pristine roots
                for target in manifest["install_targets"]:
                    src_dir = ws.path / target["namespace"]
                    dest_dir = Path(target["namespace"])
                    for file in target["files"]:
                        tx.stage_file(src_dir / file, dest_dir / file)

                # Write receipt
                receipt = create_receipt(pkg_id, manifest, work_order_id)
                tx.stage_json(f"installed/{pkg_id}/receipt.json", receipt)
                tx.stage_json(f"installed/{pkg_id}/manifest.json", manifest)

                tx.commit()

        # Success
        append_to_ledger("packages.jsonl", {
            "event_type": "INSTALLED",
            "package_id": pkg_id,
            "manifest_hash": compute_manifest_hash(manifest),
        })

        # Rebuild derived registries
        rebuild_derived_registries()

        return InstallResult(success=True, package_id=pkg_id)

    except Exception as e:
        append_to_ledger("packages.jsonl", {
            "event_type": "INSTALL_FAILED",
            "package_id": pkg_id,
            "error": str(e),
        })
        raise
```

### Gates Activated

| Gate | Where Enforced | Mode |
|------|----------------|------|
| G0A | `package_install.py` pre-ledger | FAIL-CLOSED |
| G0B | `apply_work_order.py` pre-execute | FAIL-CLOSED |
| G1 | `package_install.py` in workspace | FAIL-CLOSED |
| G1 | `apply_work_order.py` in workspace | FAIL-CLOSED |
| G5 | `package_install.py` post-seal | FAIL-CLOSED |

### Acceptance Tests

```python
class TestGateEnforcement:
    def test_enforce_mode_exits_nonzero(self):
        """--enforce mode returns exit code 1 on failure."""
        result = subprocess.run(
            ["python3", "scripts/gate_check.py", "--gate", "G0B", "--enforce"],
            capture_output=True
        )
        # With orphan file present
        assert result.returncode == 1

    def test_gate_sequence_fail_fast(self):
        """Gate sequence stops on first failure."""
        results = run_gate_sequence("package_install", archive=bad_archive, manifest=manifest)
        assert results[0]["gate"] == "G0A"
        assert results[0]["passed"] is False
        assert len(results) == 1  # Stopped after first

class TestWorkspaceIntegration:
    def test_failed_install_leaves_no_files(self, baseline_installed, bad_signature_package):
        """Failed install leaves pristine roots unchanged."""
        before = list_dir_hashes("frameworks/")

        with pytest.raises(GateError):
            install_package(bad_signature_package, "WO-TEST")

        after = list_dir_hashes("frameworks/")
        assert before == after

    def test_workspace_quarantined_on_failure(self, baseline_installed, bad_package):
        """Failed install quarantines workspace."""
        with pytest.raises(GateError):
            install_package(bad_package, "WO-TEST")

        quarantine_dirs = list(Path("quarantine/").glob("*"))
        assert len(quarantine_dirs) > 0
```

### Done Criteria

| Criterion | Verification |
|-----------|--------------|
| `--enforce` mode exits non-zero on fail | Manual test with orphan file |
| Gate sequence is fail-fast | Unit test for gate_sequence.py |
| Failed install leaves no partial state | Test with bad signature package |
| Workspace quarantined on failure | Check quarantine/ directory |
| All Phase 2 tests pass | `pytest tests/test_phase2_gates.py` |

### Risks and Edge Cases

| Risk | Mitigation |
|------|------------|
| Workspace disk full | Check available space before creating workspace |
| Atomic commit fails mid-way | AtomicTransaction rollback handles this |
| Quarantine fills up disk | Retention policy: 30 days max |

---

## Phase 3: Builder vs Built Firewall

### Goal
Prevent BUILT artifacts (runtime-produced) from modifying BUILDER (Control Plane) components.

### Deliverables

| Action | File | Purpose |
|--------|------|---------|
| CREATE | `lib/firewall.py` | G-FIREWALL implementation |
| CREATE | `schemas/built_marker.json` | BUILT artifact origin schema |
| CREATE | `tests/test_phase3_firewall.py` | Phase 3 acceptance tests |
| MODIFY | `lib/pristine.py` | Add BUILT marker tracking |
| MODIFY | `scripts/gate_check.py` | Add G-FIREWALL to gate sequence |
| MODIFY | `scripts/package_install.py` | Add origin field to receipts |

### Detailed Specifications

#### 3.1 BUILT Marker Schema

**File**: `schemas/built_marker.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["origin", "produced_by", "work_order_id", "timestamp"],
  "properties": {
    "origin": { "const": "BUILT" },
    "produced_by": { "type": "string", "description": "Package ID that produced this artifact" },
    "work_order_id": { "type": "string", "pattern": "^WO-\\d{8}-\\d{3}$" },
    "timestamp": { "type": "string", "format": "date-time" },
    "signature": { "type": "string", "description": "Base64-encoded signature" },
    "signed_by": { "type": "string", "description": "Key ID used for signing" }
  }
}
```

#### 3.2 Receipt Origin Field

All package receipts include an `origin` field:

```json
{
  "package_id": "PKG-TEST-001",
  "origin": "BUILDER",
  "installed_at": "2026-02-02T12:00:00Z",
  "manifest_hash": "sha256:...",
  "work_order_id": "WO-20260202-001"
}
```

For BUILT artifacts:
```json
{
  "artifact_id": "APP-OUTPUT-001",
  "origin": "BUILT",
  "produced_by": "PKG-APP-001",
  "work_order_id": "WO-20260202-002",
  "timestamp": "2026-02-02T13:00:00Z"
}
```

#### 3.3 G-FIREWALL Implementation

**File**: `lib/firewall.py`

```python
FORBIDDEN_ACTIONS_FOR_BUILT = [
    "INSTALL_PACKAGE",
    "UNINSTALL_PACKAGE",
    "MODIFY_FRAMEWORK",
    "MODIFY_GATE",
    "SIGN_PACKAGE",
    "APPROVE_WORK_ORDER",
    "WRITE_L_INTENT",
    "WRITE_L_PACKAGE",
    "APPROVE_L_WORKORDER",
    "MODIFY_HO3",
    "MODIFY_HO2_RESTRICTED",
    "ACCESS_SIGNING_KEYS",
]

def gate_g_firewall(actor_origin: str, operation: str, target: dict) -> tuple[bool, str]:
    """
    G-FIREWALL: Prevent BUILT actors from modifying BUILDER.

    Returns (passed, message).
    """
    if actor_origin != "BUILT":
        return True, "G-FIREWALL: BUILDER actor, full access"

    # BUILT actor - check forbidden actions
    if operation in FORBIDDEN_ACTIONS_FOR_BUILT:
        return False, f"G-FIREWALL DENIED: BUILT cannot {operation}"

    # Check target tier
    if target.get("tier") == "HO3":
        return False, "G-FIREWALL DENIED: BUILT cannot modify HO3"

    if target.get("tier") == "HO2" and operation not in ["PROPOSE_WORK_ORDER", "READ"]:
        return False, "G-FIREWALL DENIED: BUILT cannot modify HO2 (except propose WO)"

    # Check ledger access
    if target.get("ledger") in ["L-INTENT", "L-PACKAGE"]:
        return False, f"G-FIREWALL DENIED: BUILT cannot write to {target['ledger']}"

    return True, "G-FIREWALL: Action permitted for BUILT"
```

### Gates Activated

| Gate | Where Enforced | Mode |
|------|----------------|------|
| G-FIREWALL | All write operations | FAIL-CLOSED |
| G-FIREWALL | Package install (check actor origin) | FAIL-CLOSED |
| G-FIREWALL | Work order approval | FAIL-CLOSED |

### Acceptance Tests

```python
class TestBuiltMarker:
    def test_builder_receipts_have_origin(self, baseline_installed, test_package):
        """BUILDER package receipts include origin: BUILDER."""
        install_package(test_package, "WO-TEST-001")
        receipt = json.loads(Path("installed/PKG-TEST-001/receipt.json").read_text())
        assert receipt["origin"] == "BUILDER"

class TestFirewall:
    def test_built_cannot_install_package(self, baseline_installed, test_package):
        """BUILT actor cannot install packages."""
        with pytest.raises(FirewallDenied, match="BUILT cannot INSTALL_PACKAGE"):
            install_package(test_package, "WO-TEST", actor_origin="BUILT")

    def test_built_cannot_approve_wo(self, baseline_installed):
        """BUILT actor cannot approve work orders."""
        with pytest.raises(FirewallDenied, match="BUILT cannot APPROVE_WORK_ORDER"):
            approve_work_order("WO-20260202-001", actor_origin="BUILT")

    def test_built_cannot_write_ho3(self, baseline_installed):
        """BUILT actor cannot modify HO3 files."""
        with pytest.raises(FirewallDenied, match="BUILT cannot modify HO3"):
            write_file("frameworks/FMWK-000.md", "# hacked", actor_origin="BUILT")

    def test_builder_can_do_everything(self, baseline_installed, test_package):
        """BUILDER actor has full access."""
        install_package(test_package, "WO-TEST", actor_origin="BUILDER")
        assert Path("installed/PKG-TEST-001/receipt.json").exists()
```

### Done Criteria

| Criterion | Verification |
|-----------|--------------|
| All receipts have origin field | `jq '.origin' installed/*/receipt.json` |
| G-FIREWALL blocks BUILT install | Test with actor_origin=BUILT |
| G-FIREWALL blocks BUILT approval | Test WO approval |
| G-FIREWALL blocks BUILT HO3 write | Test file write |
| BUILDER has full access | Test all operations |

### Risks and Edge Cases

| Risk | Mitigation |
|------|------------|
| Actor origin spoofed | Origin determined by runtime context, not user input |
| Human override needed | Explicit two-person approval + time-limited override |
| Agent self-promotion | Blocked by G-FIREWALL; requires explicit promotion path |

---

## Phase 4: Work Order Protocol Complete

### Goal
Full WO lifecycle with Git PR approval model, idempotency, and scope validation.

### Deliverables

| Action | File | Purpose |
|--------|------|---------|
| CREATE | `.github/workflows/wo-approval.yml` | CI writes ledger on PR merge |
| CREATE | `scripts/compute_wo_hash.py` | Canonical JSON hash computation |
| CREATE | `scripts/validate_work_order.py` | Schema + scope validation |
| CREATE | `ledger/work_orders.jsonl` | PROPOSED/APPROVED tracking |
| CREATE | `ledger/applied_work_orders.jsonl` | APPLIED/COMPLETED tracking |
| CREATE | `tests/test_phase4_work_orders.py` | Phase 4 acceptance tests |
| MODIFY | `scripts/apply_work_order.py` | Full implementation with gates |
| MODIFY | `schemas/work_order.schema.json` | Add scope, constraints, outputs |

### Detailed Specifications

#### 4.1 Work Order Hash Computation

**File**: `scripts/compute_wo_hash.py`

```python
def compute_wo_hash(wo_path: Path) -> str:
    """
    Compute deterministic hash of Work Order payload.

    Canonicalization:
    - Keys sorted alphabetically (recursive)
    - No trailing whitespace
    - UTF-8 encoding, no BOM
    - Compact separators (no spaces)
    """
    with open(wo_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Exclude metadata that shouldn't affect hash
    hashable = {k: v for k, v in data.items() if k not in ["_metadata"]}

    canonical = json.dumps(hashable, sort_keys=True, separators=(',', ':'))
    digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    return f"sha256:{digest}"
```

#### 4.2 Work Order Lifecycle

```
1. PROPOSE
   - Author creates work_orders/<plane>/WO-YYYYMMDD-NNN.json
   - Opens PR to target branch
   - CI validates schema, computes wo_payload_hash (preview)
   - Ledger entry: {"event_type": "PROPOSED", "work_order_id": "...", "wo_payload_hash": "..."}

2. APPROVE (Git PR Merge)
   - Required reviewer(s) approve PR
   - On merge, CI:
     a) Recomputes wo_payload_hash
     b) Appends to work_orders.jsonl: status=APPROVED
   - Ledger entry: {"event_type": "APPROVED", "work_order_id": "...", "approved_by": "...", "merge_commit": "..."}

3. EXECUTE (Isolated Workspace)
   - apply_work_order.py runs in workspace
   - Idempotency check:
     * If (work_order_id, wo_payload_hash) in applied → NO-OP
     * If work_order_id exists with different hash → FAIL (tampering)
   - Gates G0B, G1, G2, G3, G4 validate
   - Ledger entry on start: {"event_type": "EXECUTION_STARTED", ...}

4. APPLY (Atomic Commit)
   - G5 (signature), G6 (ledger) run
   - Atomic write: registry updates + ledger entry
   - Ledger entry: {"event_type": "APPLIED", ...}

5. COMPLETE
   - Final verification
   - Ledger entry: {"event_type": "COMPLETED", ...}
```

#### 4.3 Idempotency Check

```python
def check_idempotency(work_order_id: str, wo_payload_hash: str) -> str:
    """
    Check if Work Order has already been applied.

    Returns:
    - "NEW": First time, proceed
    - "IDEMPOTENT": Already applied with same hash, NO-OP
    - "CONFLICT": Same ID but different hash, FAIL
    """
    applied = load_applied_work_orders()

    for entry in applied:
        if entry["work_order_id"] == work_order_id:
            if entry["wo_payload_hash"] == wo_payload_hash:
                return "IDEMPOTENT"
            else:
                return "CONFLICT"

    return "NEW"
```

### Gates Activated

| Gate | Where Enforced | Mode |
|------|----------------|------|
| G2 | `apply_work_order.py` pre-execute | FAIL-CLOSED |
| G3 | `apply_work_order.py` in workspace | FAIL-CLOSED |
| G4 | `apply_work_order.py` in workspace | FAIL-CLOSED |
| G6 | `apply_work_order.py` post-apply | FAIL-CLOSED |

### Acceptance Tests

```python
class TestWorkOrderHash:
    def test_hash_is_deterministic(self, wo_file):
        """Same WO produces same hash."""
        hash1 = compute_wo_hash(wo_file)
        hash2 = compute_wo_hash(wo_file)
        assert hash1 == hash2

    def test_hash_format(self, wo_file):
        """Hash uses sha256:<64hex> format."""
        h = compute_wo_hash(wo_file)
        assert h.startswith("sha256:")
        assert len(h) == 7 + 64

class TestIdempotency:
    def test_first_apply_succeeds(self, baseline_installed, approved_wo):
        """First apply of WO succeeds."""
        result = apply_work_order(approved_wo)
        assert result.status == "APPLIED"

    def test_second_apply_is_noop(self, baseline_installed, applied_wo):
        """Second apply of same WO is NO-OP."""
        result = apply_work_order(applied_wo)
        assert result.status == "IDEMPOTENT"

    def test_tampered_wo_fails(self, baseline_installed, applied_wo):
        """Apply of WO with different hash fails."""
        # Modify WO file after approval
        modify_wo_file(applied_wo)
        with pytest.raises(TamperDetected):
            apply_work_order(applied_wo)

class TestScopeValidation:
    def test_out_of_scope_change_fails(self, baseline_installed, approved_wo):
        """WO cannot modify files outside scope.allowed_files."""
        # WO scope only allows lib/foo.py
        # Try to modify lib/bar.py
        with pytest.raises(ScopeViolation):
            apply_work_order(approved_wo, changes={"lib/bar.py": "# bad"})
```

### Done Criteria

| Criterion | Verification |
|-----------|--------------|
| WO hash is deterministic | Two computations match |
| Idempotent apply is NO-OP | Second apply returns IDEMPOTENT |
| Tampered WO fails | Modified WO returns CONFLICT |
| Scope validation works | Out-of-scope change fails |
| G2-G6 enforced | All gates run in sequence |

### Risks and Edge Cases

| Risk | Mitigation |
|------|------------|
| CI fails during ledger write | Retry with idempotency check |
| PR merged without CI | Branch protection required |
| Concurrent WO execution | Mutex/lock on plane |

---

## Phase 5: Genesis Seal + Self-Hosting

### Goal
Genesis bootstrap installs core package, seals plane, then only package_install.py can modify.

### Deliverables

| Action | File | Purpose |
|--------|------|---------|
| CREATE | `packages_store/PKG-G0-CORE.tar.gz` | Pre-built core package |
| CREATE | `tests/test_phase5_genesis.py` | Phase 5 acceptance tests |
| MODIFY | `scripts/genesis_bootstrap.py` | Write GENESIS entry, seal |
| MODIFY | `config/seal.json` | Already created in Phase 1 |

### Detailed Specifications

#### 5.1 Genesis Bootstrap Update

```python
def genesis_bootstrap(package_id: str) -> None:
    """
    Bootstrap the control plane with first package.

    Only allowed when:
    - Plane is unsealed (config/seal.json doesn't exist or sealed=false)
    - Package is PKG-G0-CORE or PKG-BASELINE-*
    """
    # Check seal
    if is_sealed():
        raise SealedError("Plane is sealed. Use package_install.py")

    # Validate package ID
    if not package_id.startswith("PKG-G0-") and not package_id.startswith("PKG-BASELINE-"):
        raise GenesisError(f"Genesis only allows G0 or BASELINE packages, got {package_id}")

    # Write GENESIS entry to L-PACKAGE
    append_to_ledger("packages.jsonl", {
        "event_type": "GENESIS",
        "package_id": package_id,
        "timestamp": now_iso(),
        "message": "Control plane genesis bootstrap"
    })

    # Install package (simplified, no gates for genesis)
    install_package_genesis(package_id)

    # Note: Seal happens after baseline install in Phase 1
    # Genesis does NOT seal; baseline install does
```

#### 5.2 Seal Verification

```python
def is_sealed() -> bool:
    """Check if plane is sealed."""
    seal_file = Path("config/seal.json")
    if not seal_file.exists():
        return False

    seal = json.loads(seal_file.read_text())
    return seal.get("sealed", False)

def verify_seal_integrity() -> tuple[bool, str]:
    """Verify seal is intact and baseline is installed."""
    if not is_sealed():
        return False, "Plane is not sealed"

    # Check baseline package installed
    baseline_receipt = Path("installed/PKG-BASELINE-HO3-000/receipt.json")
    if not baseline_receipt.exists():
        return False, "Baseline package not installed"

    # Check G0B passes
    passed, msg = gate_g0b_plane_ownership("ho3")
    if not passed:
        return False, f"G0B failed: {msg}"

    return True, "Seal integrity verified"
```

### Gates Activated

| Gate | Where Enforced | Mode |
|------|----------------|------|
| Genesis exception | `genesis_bootstrap.py` only | Bypasses gates |
| All gates | `package_install.py` post-seal | FAIL-CLOSED |

### Acceptance Tests

```python
class TestGenesisBootstrap:
    def test_genesis_writes_ledger(self, fresh_plane):
        """Genesis writes GENESIS entry to L-PACKAGE."""
        genesis_bootstrap("PKG-G0-CORE")
        entries = list(read_ledger("ledger/packages.jsonl"))
        genesis_entries = [e for e in entries if e["event_type"] == "GENESIS"]
        assert len(genesis_entries) == 1

    def test_genesis_blocked_after_seal(self, sealed_plane):
        """Genesis fails after plane is sealed."""
        with pytest.raises(SealedError):
            genesis_bootstrap("PKG-G0-CORE")

    def test_genesis_only_allows_g0_packages(self, fresh_plane):
        """Genesis rejects non-G0 packages."""
        with pytest.raises(GenesisError, match="only allows G0"):
            genesis_bootstrap("PKG-APP-001")

class TestSelfHosting:
    def test_post_seal_requires_package_install(self, sealed_plane, test_package):
        """After seal, must use package_install.py."""
        # genesis_bootstrap fails
        with pytest.raises(SealedError):
            genesis_bootstrap("PKG-TEST-001")

        # package_install works
        install_package(test_package, "WO-TEST-001")
        assert Path("installed/PKG-TEST-001/receipt.json").exists()
```

### Done Criteria

| Criterion | Verification |
|-----------|--------------|
| GENESIS entry in ledger | `grep GENESIS packages.jsonl` |
| Genesis blocked after seal | Test with sealed plane |
| Only G0/BASELINE allowed | Test with regular package |
| Post-seal uses package_install | Test normal install flow |

### Risks and Edge Cases

| Risk | Mitigation |
|------|------------|
| Seal file deleted | G0B would fail (ownership mismatch), plane unusable until resealed |
| Genesis run twice | Idempotency: check if GENESIS already exists |
| Core package corrupted | Verify signature before install |

---

## SDLC Test Package

### Purpose
A complete SDLC framework package to install as test subject, validating all phases of the implementation. This package proves:

1. Namespaced installation works (frameworks/, specs/, gates/)
2. Gates are enforced on install
3. Ledger records installation correctly
4. Package can define custom gates that get enforced
5. Dependencies are checked

### Package Contents

#### FMWK-SDLC-100: SDLC Governance Framework LAW

**Install target**: `frameworks/FMWK-SDLC-100/FMWK-SDLC-100.md`

```markdown
# FMWK-SDLC-100: SDLC Governance Framework

## Metadata
- framework_id: FMWK-SDLC-100
- status: active
- version: 1.0.0
- plane: ho3

## Invariants

- [MUST] Every SDLC-governed spec defines required feedback types
- [MUST] Phase gates require complete feedback bundle before transition
- [MUST] All feedback is immutable after recording to L-EVIDENCE
- [MUST] Feedback is signed by its author
- [MUST NOT] Self-authored feedback (author != artifact author)
- [MUST NOT] Skip phases without explicit waiver Work Order

## Path Authorizations

Specs governed by this framework MAY own files matching:
- `evidence/{spec_id}/**`
- `artifacts/{spec_id}/**`

## Required Gates
- G0A (package declaration)
- G0B (plane ownership)
- G1 (chain)
- G-FEEDBACK-COMPLETE (custom)
- G-FEEDBACK-TRACE (custom)

## Security Posture
- Fail-closed on missing feedback
- Fail-closed on broken trace link
- Fail-closed on invalid signature
```

#### FMWK-SDLC-QUAL-001: Quality Feedback Governance LAW

**Install target**: `frameworks/FMWK-SDLC-QUAL-001/FMWK-SDLC-QUAL-001.md`

(Normative rules from CP-SDLC-QUAL-001 reformatted as LAW)

#### SPEC-SDLC-FEEDBACK-001: Feedback Evidence Spec Pack

**Install target**: `specs/SPEC-SDLC-FEEDBACK-001/`

```yaml
# specs/SPEC-SDLC-FEEDBACK-001/manifest.yaml
spec_id: SPEC-SDLC-FEEDBACK-001
title: "SDLC Feedback Evidence"
framework_id: FMWK-SDLC-100
status: active
version: 1.0.0
plane_id: ho3

assets:
  - schemas/feedback.schema.json
  - schemas/rubric.schema.json

interfaces:
  - name: submit_feedback
    description: Submit feedback artifact for an SDLC phase
  - name: validate_feedback
    description: Validate feedback against schema and trace links

invariants:
  - "Feedback MUST reference valid target artifacts"
  - "Feedback MUST be signed by author"

acceptance:
  checks:
    - "test -f specs/SPEC-SDLC-FEEDBACK-001/schemas/feedback.schema.json"
    - "python3 -m json.tool specs/SPEC-SDLC-FEEDBACK-001/schemas/feedback.schema.json"
```

#### Custom Gates

**Install target**: `gates/G-FEEDBACK-COMPLETE/`

```python
# gates/G-FEEDBACK-COMPLETE/gate.py

def check(context: dict) -> tuple[bool, str]:
    """
    G-FEEDBACK-COMPLETE: Verify feedback bundle exists and conforms to schema.

    Triggered at: Phase gate transition
    """
    phase = context.get("phase")
    spec_id = context.get("spec_id")
    evidence_path = Path(f"evidence/{spec_id}/{phase}")

    if not evidence_path.exists():
        return False, f"Missing evidence directory: {evidence_path}"

    feedback_files = list(evidence_path.glob("*.json"))
    if not feedback_files:
        return False, f"No feedback artifacts in {evidence_path}"

    for fb in feedback_files:
        data = json.loads(fb.read_text())

        # Validate required fields
        required = ["feedback_id", "author_id", "author_role", "feedback_type", "target_artifacts"]
        missing = [f for f in required if f not in data]
        if missing:
            return False, f"Invalid feedback {fb.name}: missing {missing}"

        # Validate hash format
        if "content_hash" in data:
            if not data["content_hash"].startswith("sha256:"):
                return False, f"Invalid hash format in {fb.name}"

    return True, f"G-FEEDBACK-COMPLETE: {len(feedback_files)} feedback artifacts validated"
```

**Install target**: `gates/G-FEEDBACK-TRACE/`

```python
# gates/G-FEEDBACK-TRACE/gate.py

def check(context: dict) -> tuple[bool, str]:
    """
    G-FEEDBACK-TRACE: Verify feedback traces to requirements, design, tests.

    Triggered at: Phase gate transition
    """
    spec_id = context.get("spec_id")
    evidence_path = Path(f"evidence/{spec_id}")

    if not evidence_path.exists():
        return True, "G-FEEDBACK-TRACE: No evidence yet (OK for early phases)"

    for fb_file in evidence_path.rglob("*.json"):
        data = json.loads(fb_file.read_text())
        targets = data.get("target_artifacts", [])

        for target in targets:
            artifact_id = target.get("artifact_id")
            version = target.get("version")

            if not artifact_exists(artifact_id, version):
                return False, f"Broken trace in {fb_file.name}: {artifact_id}@{version} not found"

    return True, "G-FEEDBACK-TRACE: All traces valid"
```

#### Package Manifest

**File**: `PKG-SDLC-100/manifest.json`

```json
{
  "package_id": "PKG-SDLC-100",
  "version": "1.0.0",
  "plane_id": "ho3",
  "package_type": "framework",
  "spec_id": "SPEC-SDLC-001",
  "framework_id": "FMWK-SDLC-100",

  "install_targets": [
    {
      "namespace": "frameworks",
      "target_id": "FMWK-SDLC-100",
      "files": ["FMWK-SDLC-100.md"]
    },
    {
      "namespace": "frameworks",
      "target_id": "FMWK-SDLC-QUAL-001",
      "files": ["FMWK-SDLC-QUAL-001.md"]
    },
    {
      "namespace": "specs",
      "target_id": "SPEC-SDLC-FEEDBACK-001",
      "files": ["manifest.yaml", "schemas/feedback.schema.json", "schemas/rubric.schema.json"]
    },
    {
      "namespace": "gates",
      "target_id": "G-FEEDBACK-COMPLETE",
      "files": ["gate.py", "__init__.py"]
    },
    {
      "namespace": "gates",
      "target_id": "G-FEEDBACK-TRACE",
      "files": ["gate.py", "__init__.py"]
    }
  ],

  "assets": [
    {"path": "frameworks/FMWK-SDLC-100/FMWK-SDLC-100.md", "sha256": "sha256:...", "classification": "law_doc"},
    {"path": "frameworks/FMWK-SDLC-QUAL-001/FMWK-SDLC-QUAL-001.md", "sha256": "sha256:...", "classification": "law_doc"},
    {"path": "specs/SPEC-SDLC-FEEDBACK-001/manifest.yaml", "sha256": "sha256:...", "classification": "spec_manifest"},
    {"path": "specs/SPEC-SDLC-FEEDBACK-001/schemas/feedback.schema.json", "sha256": "sha256:...", "classification": "schema"},
    {"path": "specs/SPEC-SDLC-FEEDBACK-001/schemas/rubric.schema.json", "sha256": "sha256:...", "classification": "schema"},
    {"path": "gates/G-FEEDBACK-COMPLETE/gate.py", "sha256": "sha256:...", "classification": "gate"},
    {"path": "gates/G-FEEDBACK-COMPLETE/__init__.py", "sha256": "sha256:...", "classification": "gate"},
    {"path": "gates/G-FEEDBACK-TRACE/gate.py", "sha256": "sha256:...", "classification": "gate"},
    {"path": "gates/G-FEEDBACK-TRACE/__init__.py", "sha256": "sha256:...", "classification": "gate"}
  ],

  "dependencies": [
    {"package_id": "PKG-BASELINE-HO3-000", "version": ">=1.0.0"}
  ],

  "acceptance": {
    "tests": ["pytest tests/test_sdlc_gates.py"],
    "checks": [
      "python3 scripts/gate_check.py --gate G-FEEDBACK-COMPLETE --spec SPEC-SDLC-FEEDBACK-001 --dry-run",
      "python3 scripts/gate_check.py --gate G-FEEDBACK-TRACE --spec SPEC-SDLC-FEEDBACK-001 --dry-run"
    ]
  },

  "metadata": {
    "created_at": "2026-02-02T00:00:00Z",
    "description": "SDLC governance framework with feedback evidence and trace gates"
  }
}
```

### Install Expectations

```bash
# Pre-requisites
# - Phase 1-5 complete
# - Baseline installed and sealed
# - G0B passes

# Install SDLC package
python3 scripts/package_install.py \
  --archive packages_store/PKG-SDLC-100.tar.gz \
  --id PKG-SDLC-100 \
  --wo WO-20260202-SDLC

# Expected outcomes:
# 1. G0A passes (all files declared, hashes match)
# 2. G1 passes (FMWK-SDLC-100 references exist)
# 3. G5 passes (signature valid)
# 4. Files installed to pristine roots:
ls frameworks/FMWK-SDLC-100/
# → FMWK-SDLC-100.md

ls frameworks/FMWK-SDLC-QUAL-001/
# → FMWK-SDLC-QUAL-001.md

ls specs/SPEC-SDLC-FEEDBACK-001/
# → manifest.yaml, schemas/

ls gates/G-FEEDBACK-COMPLETE/
# → gate.py, __init__.py

ls gates/G-FEEDBACK-TRACE/
# → gate.py, __init__.py

# 5. Receipt created:
cat installed/PKG-SDLC-100/receipt.json
# → {"package_id": "PKG-SDLC-100", "origin": "BUILDER", ...}

# 6. Ledger updated:
grep PKG-SDLC-100 ledger/packages.jsonl
# → INSTALL_STARTED, INSTALLED

# 7. Derived registries updated:
grep FMWK-SDLC-100 registries/file_ownership.csv
# → frameworks/FMWK-SDLC-100/FMWK-SDLC-100.md,PKG-SDLC-100,...

# 8. Custom gates available:
python3 scripts/gate_check.py --list-gates
# → ... G-FEEDBACK-COMPLETE, G-FEEDBACK-TRACE ...
```

### What SDLC Package Proves

| Capability | Proof |
|------------|-------|
| Namespaced install | Files go to `frameworks/`, `specs/`, `gates/` |
| G0A enforcement | Package with undeclared file fails |
| G1 chain validation | Package with missing framework_id fails |
| G5 signature | Unsigned package fails post-seal |
| Two-phase ledger | INSTALL_STARTED before INSTALLED |
| Receipt creation | `installed/PKG-SDLC-100/receipt.json` exists |
| Derived registry update | `file_ownership.csv` includes SDLC assets |
| Dependency resolution | Would fail if baseline not installed |
| Custom gate installation | Gates appear in `gates/` directory |
| Acceptance checks | Package's acceptance.checks ran successfully |

### Failure Cases (Deterministic)

```bash
# FAIL: Missing dependency
rm -rf installed/PKG-BASELINE-HO3-000/
python3 scripts/package_install.py --archive PKG-SDLC-100.tar.gz --wo WO-TEST
# → ERROR: G1 FAILED: dependency PKG-BASELINE-HO3-000 not installed

# FAIL: Invalid signature
python3 scripts/package_install.py --archive PKG-SDLC-100-BADSIG.tar.gz --wo WO-TEST
# → ERROR: G5 FAILED: signature verification failed

# FAIL: Undeclared file in archive
# (PKG-SDLC-100-ORPHAN.tar.gz contains extra file not in manifest)
python3 scripts/package_install.py --archive PKG-SDLC-100-ORPHAN.tar.gz --wo WO-TEST
# → ERROR: G0A FAILED: UNDECLARED file "rogue.py" in archive

# FAIL: Hash mismatch
# (PKG-SDLC-100-BADHASH.tar.gz has modified file)
python3 scripts/package_install.py --archive PKG-SDLC-100-BADHASH.tar.gz --wo WO-TEST
# → ERROR: G0A FAILED: HASH_MISMATCH for FMWK-SDLC-100.md
```

---

## Implementation Order

| Week | Phase | Key Milestone |
|------|-------|---------------|
| 1 | Phase 1 | Baseline sealed, G0A/G0B split, derived registries |
| 2 | Phase 2 | Gate enforcement, workspace integration |
| 3 | Phase 3 | Builder/Built firewall |
| 4 | Phase 4 | Work Order protocol complete |
| 5 | Phase 5 | Genesis seal, self-hosting |
| 5 | SDLC | Install PKG-SDLC-100 as validation |

---

## Appendix A: File Change Summary

### Phase 1
- CREATE: `scripts/generate_baseline_manifest.py`
- CREATE: `scripts/install_baseline.py`
- CREATE: `scripts/rebuild_derived_registries.py`
- CREATE: `registries/file_ownership.csv`
- CREATE: `packages_store/PKG-BASELINE-HO3-000.tar.gz`
- CREATE: `installed/PKG-BASELINE-HO3-000/`
- CREATE: `config/seal.json`
- CREATE: `tests/test_phase1_baseline.py`
- MODIFY: `schemas/package_manifest.json`
- MODIFY: `scripts/package_install.py`
- MODIFY: `scripts/gate_check.py`
- MODIFY: `lib/ledger_client.py`

### Phase 2
- CREATE: `lib/gate_sequence.py`
- CREATE: `tests/test_phase2_gates.py`
- MODIFY: `scripts/gate_check.py`
- MODIFY: `scripts/package_install.py`
- MODIFY: `scripts/apply_work_order.py`
- MODIFY: `lib/workspace.py`

### Phase 3
- CREATE: `lib/firewall.py`
- CREATE: `schemas/built_marker.json`
- CREATE: `tests/test_phase3_firewall.py`
- MODIFY: `lib/pristine.py`
- MODIFY: `scripts/gate_check.py`
- MODIFY: `scripts/package_install.py`

### Phase 4
- CREATE: `.github/workflows/wo-approval.yml`
- CREATE: `scripts/compute_wo_hash.py`
- CREATE: `scripts/validate_work_order.py`
- CREATE: `ledger/work_orders.jsonl`
- CREATE: `ledger/applied_work_orders.jsonl`
- CREATE: `tests/test_phase4_work_orders.py`
- MODIFY: `scripts/apply_work_order.py`
- MODIFY: `schemas/work_order.schema.json`

### Phase 5
- CREATE: `packages_store/PKG-G0-CORE.tar.gz`
- CREATE: `tests/test_phase5_genesis.py`
- MODIFY: `scripts/genesis_bootstrap.py`

### SDLC Package
- CREATE: `packages_store/PKG-SDLC-100/` (all contents)
- CREATE: `packages_store/PKG-SDLC-100.tar.gz`

---

## Appendix B: Verification Command Summary

```bash
# Phase 1 verification
python3 scripts/generate_baseline_manifest.py --plane ho3 --output packages_store/PKG-BASELINE-HO3-000/
python3 scripts/install_baseline.py --plane ho3
python3 scripts/gate_check.py --gate G0B --plane ho3 --enforce
python3 scripts/rebuild_derived_registries.py --verify
pytest tests/test_phase1_baseline.py -v

# Phase 2 verification
python3 scripts/gate_check.py --all --enforce
pytest tests/test_phase2_gates.py -v

# Phase 3 verification
pytest tests/test_phase3_firewall.py -v

# Phase 4 verification
python3 scripts/compute_wo_hash.py --wo work_orders/ho3/WO-TEST.json
python3 scripts/apply_work_order.py --wo WO-TEST --dry-run
pytest tests/test_phase4_work_orders.py -v

# Phase 5 verification
python3 scripts/genesis_bootstrap.py --package PKG-G0-CORE  # Should fail if sealed
pytest tests/test_phase5_genesis.py -v

# SDLC validation
python3 scripts/package_install.py --archive packages_store/PKG-SDLC-100.tar.gz --wo WO-SDLC
python3 scripts/gate_check.py --gate G-FEEDBACK-COMPLETE --dry-run
python3 scripts/gate_check.py --gate G-FEEDBACK-TRACE --dry-run
```

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-02-02 | Claude | Initial implementation plan |

---

*End of CP-IMPL-001*
