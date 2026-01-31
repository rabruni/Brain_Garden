# FMWK-PKG-001: Package Standard v1.0

**Status**: Active
**Version**: 1.0.0
**Author**: system
**Created**: 2026-01-31
**ALTITUDE**: L4-ARCHITECTURE

---

## 1. Overview

This framework defines the tiered package system for the Control Plane. Packages are
organized into strict hierarchical tiers with explicit dependency rules. The system
enables pristine rebuilds from a minimal Genesis kernel.

---

## 2. Tier Hierarchy

| Tier | ID Prefix | Purpose | May Depend On | Install Order |
|------|-----------|---------|---------------|---------------|
| G0 (Genesis) | `PKG-G0-NNN` | Minimal kernel + bootstrapper | NOTHING | 1 |
| T0 | `PKG-T0-NNN` | Trust baseline (libs) | G0 only | 2 |
| T1 | `PKG-T1-NNN` | Runtime tools (scripts) | T0, G0 | 3 |
| T2 | `PKG-T2-NNN` | Modules | T1, T0, G0 | 4 |
| T3 | `PKG-T3-NNN` | Agents/Entities | T2, T1, T0, G0 | 5 |

### 2.1 Tier Dependency Matrix

```
From/To │ G0  │ T0  │ T1  │ T2  │ T3
────────┼─────┼─────┼─────┼─────┼─────
   G0   │  -  │  X  │  X  │  X  │  X
   T0   │ OK  │  -  │  X  │  X  │  X
   T1   │ OK  │ OK  │  -  │  X  │  X
   T2   │ OK  │ OK  │ OK  │  -  │  X
   T3   │ OK  │ OK  │ OK  │ OK  │  -
```

- **OK**: Allowed dependency direction
- **X**: Forbidden dependency direction (violates I1-TIER)
- **-**: Same tier (allowed within tier)

---

## 3. Package Manifest Schema (v1.0)

Each package has a `manifest.json` at `packages/<PKG-ID>/manifest.json`:

```json
{
  "schema_version": "1.0",
  "id": "PKG-T0-001",
  "name": "Integrity Library",
  "version": "1.0.0",
  "tier": "T0",
  "description": "Three-check integrity validation",
  "artifact_paths": ["lib/integrity.py"],
  "deps": ["PKG-G0-002"],
  "conflicts": [],
  "platform": "any",
  "arch": "any",
  "license": "MIT",
  "author": "system",
  "created_at": "2026-01-31T00:00:00Z"
}
```

### 3.1 Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Must be "1.0" |
| `id` | string | Package ID (PKG-XX-NNN) |
| `name` | string | Human-readable name |
| `version` | string | Semver version |
| `tier` | string | One of: G0, T0, T1, T2, T3 |
| `artifact_paths` | array | Paths to installed artifacts |
| `deps` | array | Package ID dependencies |

### 3.2 Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | string | "" | Package description |
| `conflicts` | array | [] | Conflicting package IDs |
| `platform` | string | "any" | Target platform (any, linux, darwin) |
| `arch` | string | "any" | Target architecture (any, x86_64, arm64) |
| `license` | string | "MIT" | Package license |
| `author` | string | "" | Package author |
| `created_at` | string | "" | ISO 8601 timestamp |
| `signature` | string | "" | HMAC-SHA256 signature |
| `attestation` | object | null | Attestation details |

---

## 4. Non-Negotiable Invariants

These invariants MUST be enforced. No waivers on main/release branches.

| ID | Invariant | Description |
|----|-----------|-------------|
| I1-TIER | Lower tiers CANNOT depend on higher tiers | G0→T0→T1→T2→T3 only |
| I2-SIGNED | All packages signed on main/release | HMAC-SHA256 signature required |
| I3-ATTESTED | All packages attested on main/release | Build attestation required |
| I4-DETERMINISTIC | Same inputs = identical archive hash | Reproducible builds |
| I5-GENESIS-ZERO | Genesis packages have ZERO lib/ dependencies | stdlib only |
| I6-LEDGER-CHAIN | Every install logged; chain must verify | Immutable ledger |
| I7-PRISTINE | Only INSTALL mode writes to PRISTINE paths | Protected directories |
| I8-RECEIPTS | Every install writes a receipt to `installed/` | State tracking |

---

## 5. Genesis (G0) Specification

### 5.1 Genesis Packages

| ID | Name | Content | Deps | Constraint |
|----|------|---------|------|------------|
| PKG-G0-001 | Paths | `lib/paths.py` | NONE | stdlib only |
| PKG-G0-002 | Merkle | `lib/merkle.py` | NONE | stdlib only |
| PKG-G0-003 | Packages | `lib/packages.py` | NONE | stdlib only |

### 5.2 Genesis Bootstrapper

`scripts/genesis_bootstrap.py` is a self-contained bootstrapper that:

1. Has ZERO imports from lib/ (Python stdlib only)
2. Reads a seed registry (JSON file)
3. Verifies SHA-256 digest
4. Verifies signature (HMAC-SHA256, key from env)
5. Extracts tarball to CONTROL_PLANE
6. Writes install receipt to `installed/<pkg-id>/`

### 5.3 Seed Registry Format

```json
{
  "schema_version": "1.0",
  "created_at": "2026-01-31T00:00:00Z",
  "packages": [
    {
      "id": "PKG-G0-001",
      "name": "Paths",
      "version": "1.0.0",
      "tier": "G0",
      "source": "packages_store/PKG-G0-001_paths.tar.gz",
      "digest": "abc123...",
      "signature": "def456..."
    }
  ],
  "install_order": ["PKG-G0-001", "PKG-G0-002", "PKG-G0-003"]
}
```

---

## 6. Tier0 (T0) Trust Baseline

### 6.1 T0 Packages

| ID | Name | Content | Deps |
|----|------|---------|------|
| PKG-T0-001 | Integrity | `lib/integrity.py` | G0-002 |
| PKG-T0-002 | Ledger | `lib/ledger_client.py` | G0-002 |
| PKG-T0-003 | Pristine | `lib/pristine.py` | G0-001, T0-002 |
| PKG-T0-004 | Auth | `lib/auth.py` | NONE (stdlib) |
| PKG-T0-005 | Authz | `lib/authz.py` | T0-004 |
| PKG-T0-006 | Signing | `lib/signing.py` | G0-003, T0-002 |
| PKG-T0-007 | Provenance | `lib/provenance.py` | G0-003, T0-002, T0-006 |
| PKG-T0-008 | Package Audit | `lib/package_audit.py` | T0-002 |

### 6.2 T0 Self-Verification

After T0 install, the system is self-verifying:

```python
from lib.integrity import IntegrityChecker
from lib.ledger_client import LedgerClient

checker = IntegrityChecker()
result = checker.validate()
assert result.passed, 'Integrity failed'

client = LedgerClient()
valid, _ = client.verify_chain()
assert valid, 'Ledger chain broken'
```

---

## 7. Tier1 (T1) Runtime Tools

### 7.1 T1 Packages

| ID | Name | Content | Deps |
|----|------|---------|------|
| PKG-T1-001 | Pack | `scripts/package_pack.py` | G0-003, T0-006, T0-007 |
| PKG-T1-002 | Install | `scripts/package_install.py` | G0-003, T0-003..T0-008 |
| PKG-T1-003 | Validate | `scripts/validate_packages.py` | G0-001 |
| PKG-T1-004 | Integrity Check | `scripts/integrity_check.py` | T0-001, G0-002 |
| PKG-T1-005 | Checkpoint | `scripts/cp_version_checkpoint.py` | T0-001..T0-005 |
| PKG-T1-006 | Rollback | `scripts/cp_version_rollback.py` | T0-001..T0-005, G0-003 |
| PKG-T1-007 | Sync | `scripts/package_sync.py` | G0-001 |
| PKG-T1-008 | Factory | `scripts/package_factory.py` | T1-001..T1-004 |

---

## 8. Install Receipt Contract

### 8.1 Receipt Location

Every successful install writes a receipt to:
```
installed/<PKG-ID>/receipt.json
```

### 8.2 Receipt Format

```json
{
  "id": "PKG-T0-001",
  "version": "1.0.0",
  "archive": "/path/to/PKG-T0-001_integrity.tar.gz",
  "archive_digest": "sha256:abc123...",
  "installed_at": "2026-01-31T12:00:00+00:00",
  "installer": "genesis_bootstrap|package_install",
  "files": [
    {"path": "lib/integrity.py", "sha256": "def456..."},
    {"path": "lib/__init__.py", "sha256": "ghi789..."}
  ]
}
```

### 8.3 Receipt Invariants

1. Every successful install MUST create a receipt
2. Receipt includes file-level SHA-256 hashes
3. `installed/` is in DERIVED paths (always writable)
4. Rebuild comparison requires identical receipt sets

---

## 9. Factory Workflow

### 9.1 Canonical Flow

```
CREATE → VALIDATE → PACK → SIGN → ATTEST → REGISTER → INSTALL → VERIFY
```

### 9.2 Gate Sequence

| Gate | Check | Failure = |
|------|-------|-----------|
| G1 | manifest.json valid | HALT |
| G2 | tier deps valid | HALT |
| G3 | pack deterministic | HALT |
| G4 | signature valid | HALT (main/release) |
| G5 | attestation valid | HALT (main/release) |
| G6 | digest matches registry | HALT |
| G7 | install succeeds | HALT |
| G8 | integrity check passes | HALT |
| G9 | ledger chain intact | HALT |

---

## 10. Pristine Rebuild

### 10.1 Definition

A pristine rebuild proves the Control Plane can be wiped to Genesis-only
state and rebuilt to the same trusted configuration.

### 10.2 Drill Steps

1. Export current state (checkpoint, packages, ledger, installed receipts)
2. Wipe PRISTINE paths (frameworks/, lib/, modules/, schemas/, scripts/)
3. Install G0 packages using genesis_bootstrap.py
4. Install T0..T3 packages in order
5. Verify integrity, ledger chain, installed state
6. Compare installed receipts before/after

### 10.3 Success Criteria

- Zero waivers on main/release
- `integrity_check.py --verify --orphans --chain --strict` passes
- `LedgerClient().verify_chain()` returns True
- Installed state matches pre-drill state

---

## 11. Package ID Conventions

### 11.1 ID Format

```
PKG-<TIER>-<NNN>
```

Examples:
- `PKG-G0-001` - Genesis paths library
- `PKG-T0-005` - Tier0 authz library
- `PKG-T1-002` - Tier1 install script
- `PKG-T2-006` - Tier2 shaper module
- `PKG-T3-001` - Tier3 hello agent

### 11.2 Reserved Ranges

| Range | Purpose |
|-------|---------|
| G0-001 to G0-010 | Core Genesis kernel |
| T0-001 to T0-100 | Trust baseline libs |
| T1-001 to T1-100 | Runtime tool scripts |
| T2-001 to T2-100 | Control Plane modules |
| T3-001 to T3-999 | Agents and entities |

---

## 12. Validation

### 12.1 Tier Dependency Validation

```bash
python3 scripts/validate_tier_deps.py
python3 scripts/validate_tier_deps.py --strict  # Fail on any violation
```

### 12.2 Manifest Validation

```bash
python3 scripts/validate_package_manifest.py --manifest packages/PKG-T0-001/manifest.json
```

### 12.3 Full Factory Validation

```bash
python3 scripts/package_factory.py --id PKG-T0-001 --validate-only
```

---

## 13. References

- SPEC-026: Package Registry
- SPEC-027: Package Manifest Layer
- FMWK-200: Ledger Protocol
- FMWK-107: Package Management Standard
