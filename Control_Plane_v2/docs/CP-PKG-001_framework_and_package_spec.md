# CP-PKG-001: Framework & Package Model Specification

**Document ID**: CP-PKG-001
**Version**: 1.0.0
**Status**: NORMATIVE
**Plane**: HO3

---

## 1. Scope

This document specifies the normative rules for:
- Framework LAW documents
- Framework and Spec packages
- Package manifests
- Install behavior
- Registry derivation
- Dependency and uninstall semantics
- Bootstrap policy

---

## 2. Framework LAW Document

### 2.1 Definition

A Framework LAW document declares governance rules. It is **implementation-free**.

### 2.2 Required Sections

| Section | Content |
|---------|---------|
| Metadata | framework_id, version, status, plane |
| Invariants | MUST / MUST NOT / SHOULD rules |
| Path Authorizations | Allowed file patterns for governed specs |
| Required Gates | Gates that apply to all governed specs |
| Change Control | Allowed Work Order types |
| Security Posture | Fail-closed rules, isolation requirements |

### 2.3 Prohibited Content

| FORBIDDEN in LAW doc |
|----------------------|
| Specific file paths (use patterns only) |
| API signatures or function definitions |
| Implementation code |
| Test commands |
| Example payloads |
| Version-specific dependency versions |

### 2.4 LAW Document Template

```markdown
# FMWK-{NNN}: {Title}

## Metadata
- framework_id: FMWK-{NNN}
- version: {semver}
- status: active | draft | deprecated
- plane: ho3 | ho2 | ho1

## Invariants
- [MUST] {rule}
- [MUST NOT] {rule}
- [SHOULD] {recommendation}

## Path Authorizations
- `libs/{package_id}/**`
- `agents/{package_id}/**`
- `specs/{spec_id}/**`

## Required Gates
- G0-PACKAGE
- G0-SPEC
- G-INTEGRITY
- {framework-specific gates}

## Change Control
- code_change
- spec_delta
- dependency_add

## Security Posture
- Fail-closed on all gate failures
- No execution outside declared scope
```

---

## 3. Package Types

| Type | Contains | Identity Field |
|------|----------|----------------|
| `framework` | LAW doc, agents, libs, gates, prompts, seed specs | `framework_id` |
| `spec` | Spec manifest, owned assets | `spec_id` |
| `library` | Shared libraries | `package_id` only |
| `agent` | Agent definitions, prompts | `package_id` only |
| `prompt` | Prompt templates | `package_id` only |
| `gate` | Gate implementations | `package_id` only |

---

## 4. Package Manifest Schema (v1.1)

### 4.1 Required Fields

```yaml
schema_version: "1.1"                    # REQUIRED
package_id: PKG-{TYPE}-{NNN}             # REQUIRED, pattern: ^PKG-[A-Z0-9-]+$
version: 1.0.0                           # REQUIRED, semver
type: framework                          # REQUIRED, enum

assets:                                  # REQUIRED, non-empty array
  - source: path/in/package
    hash: sha256:{64 hex chars}
    plane: ho3                           # ho3 | ho2 | ho1
    type: law_doc                        # asset type enum
    spec_owner: null                     # optional SPEC-* reference

integrity:                               # REQUIRED
  alg: ed25519                           # ed25519 | rsa4096
  manifest_hash: sha256:{64 hex chars}
  signature: base64:{signature}
  signed_by: {key_identity}
```

### 4.2 Conditional Fields

| Field | Required When |
|-------|---------------|
| `framework_id` | `type: framework` |
| `spec_id` | `type: spec` |
| `requires_framework` | `type: spec` |

### 4.3 Optional Fields

```yaml
dependencies:
  - package_id: PKG-CORE-001
    version: ">=1.0.0"

upgrade_policy:
  allow_asset_removal: false
  migration: null

metadata:
  title: "Human-readable title"
  maintainer: team@example.com
  license: proprietary
  repository: https://...
```

### 4.4 Asset Type Enum

| Value | Description |
|-------|-------------|
| `law_doc` | Framework LAW document |
| `spec` | Spec pack manifest |
| `library` | Python/code library |
| `agent` | Agent definition |
| `prompt` | Prompt template |
| `gate` | Gate implementation |
| `config` | Configuration file |
| `test` | Test file |
| `other` | Uncategorized asset |

---

## 5. Namespaced Install Targets

Packages declare `source` paths. The installer computes `install_target` using namespacing rules.

### 5.1 Mapping Rules

| Asset Type | Namespace | Install Target |
|------------|-----------|----------------|
| `law_doc` | `{framework_id}` | `frameworks/{framework_id}/{filename}` |
| `spec` | `{spec_id}` | `specs/{spec_id}/{relative_path}` |
| `library` | `{package_id}` | `libs/{package_id}/{relative_path}` |
| `agent` | `{package_id}` | `agents/{package_id}/{relative_path}` |
| `prompt` | `{package_id}` | `prompts/{package_id}/{relative_path}` |
| `gate` | `{package_id}` | `gates/{package_id}/{relative_path}` |
| `config` | `{package_id}` | `config/{package_id}/{relative_path}` |
| `test` | `{package_id}` | `tests/{package_id}/{relative_path}` |
| `other` | `{package_id}` | `packages/{package_id}/{relative_path}` |

### 5.2 Full Target Path

```
{plane_root}/{install_target}

where plane_root:
  ho3 = {CONTROL_PLANE_ROOT}
  ho2 = {CONTROL_PLANE_ROOT}/planes/ho2
  ho1 = {CONTROL_PLANE_ROOT}/planes/ho1
```

---

## 6. Ownership Model

### 6.1 Two-Layer Ownership

| Layer | Scope | Uniqueness |
|-------|-------|------------|
| Package Owner | Every installed file | Globally unique |
| Spec Owner | Files within a spec | Globally unique |

### 6.2 Ownership Rules

| Rule | Statement |
|------|-----------|
| O1 | Every installed file has exactly ONE package owner |
| O2 | A file MAY have exactly ONE spec owner (optional) |
| O3 | Spec owner, if present, must be declared in package manifest |
| O4 | No file may be owned by multiple packages |
| O5 | No file may be owned by multiple specs |

---

## 7. Registry-as-Projection

### 7.1 Source of Truth

```
AUTHORITATIVE:
  - ledger/packages.jsonl (install history)
  - manifests/{package_id}/{version}/package.manifest.yaml

DERIVED (projections):
  - registries/packages_registry.csv
  - registries/frameworks_registry.csv
  - registries/specs_registry.csv
```

### 7.2 Derivation Rules

| Registry | Derived From |
|----------|--------------|
| `packages_registry.csv` | Replay ledger, extract assets from each installed manifest |
| `frameworks_registry.csv` | Parse installed LAW doc headers |
| `specs_registry.csv` | Parse installed spec manifest.yaml files |

### 7.3 Registry Contribution Policy

| Policy | Statement |
|--------|-----------|
| Packages MUST NOT contribute registry rows | No `type: registry` assets |
| Registries are rebuilt on demand | Rebuild from ledger + manifests |
| Registries are query indexes only | Not source of truth |

---

## 8. Integrity Model

### 8.1 Three-Layer Integrity

| Layer | What | How |
|-------|------|-----|
| Hash | File content integrity | `sha256(file_content)` |
| Signature | Package authenticity | `sign(manifest_hash, private_key)` |
| Ledger | Install provenance | Append-only entry on install |

### 8.2 Manifest Hash Computation

```
manifest_hash = sha256(
  sorted([asset.hash for asset in assets])
)
```

### 8.3 Signature Requirements

| Requirement | Statement |
|-------------|-----------|
| Algorithm | ed25519 (preferred) or rsa4096 |
| Key storage | External HSM or secrets manager |
| Key identity | Recorded in `signed_by` field |
| Verification | Against trusted keyring (not in Control Plane) |

---

## 9. Dependency Resolution

### 9.1 Fail-Closed Policy

| Scenario | Outcome |
|----------|---------|
| Dependency not installed | FAIL |
| Dependency version outside range | FAIL |
| Circular dependency | FAIL |
| Dependency conflict between packages | FAIL |

### 9.2 Version Constraints

```yaml
dependencies:
  - package_id: PKG-CORE-001
    version: ">=1.0.0,<2.0.0"   # semver range
```

### 9.3 Resolution Order

1. Parse all dependencies recursively
2. Check each dependency is installed
3. Check each installed version satisfies constraint
4. Fail if any check fails

---

## 10. Upgrade Semantics

### 10.1 Preconditions

| Precondition | Check |
|--------------|-------|
| Work Order approved | `work_order_id` valid in ledger |
| Package installed | Current version exists |
| Version is newer | `new_version > current_version` |
| Dependencies satisfied | All new deps resolvable |
| Dependents compatible | All dependents accept new version |

### 10.2 Asset Removal Policy

| `allow_asset_removal` | Assets Removed? | Outcome |
|-----------------------|-----------------|---------|
| `false` (default) | Yes | FAIL |
| `false` | No | OK |
| `true` | Yes | OK (logged) |
| `true` | No | OK |

### 10.3 Upgrade Ledger Entry

```json
{
  "event_type": "UPGRADED",
  "package_id": "PKG-XXX-001",
  "version": "2.0.0",
  "previous_version": "1.0.0",
  "removed_assets": [
    {"path": "...", "hash": "sha256:...", "type": "...", "plane": "..."}
  ],
  "work_order_id": "WO-...",
  "..."
}
```

---

## 11. Uninstall Semantics

### 11.1 Preconditions

| Precondition | Check |
|--------------|-------|
| Work Order approved | `work_order_id` valid |
| Package installed | Current version exists |
| No dependents | No installed package depends on this |

### 11.2 Dependent Check

```
IF EXISTS package P WHERE P.dependencies CONTAINS this_package:
  FAIL "Cannot uninstall: dependent packages exist: {list}"
```

### 11.3 No Cascade (v1)

| Policy | Statement |
|--------|-----------|
| Cascade uninstall | NOT SUPPORTED in v1 |
| Future cascade | Requires explicit enumeration in Work Order |

### 11.4 Uninstall Ledger Entry

```json
{
  "event_type": "UNINSTALLED",
  "package_id": "PKG-XXX-001",
  "version": "1.0.0",
  "removed_assets": [
    {"path": "...", "hash": "sha256:...", "type": "...", "plane": "..."}
  ],
  "work_order_id": "WO-...",
  "..."
}
```

---

## 12. Bootstrap Policy

### 12.1 Genesis Package

| Property | Value |
|----------|-------|
| Package ID | `PKG-PM-CORE-001` |
| Type | `library` |
| Contents | Package manager, gates, ledger client |
| Installed by | `genesis_bootstrap.py` |

### 12.2 Bootstrap Sequence

1. `genesis_bootstrap.py` validates `PKG-PM-CORE-001`
2. Verifies signature against external keyring
3. Creates initial ledger with GENESIS entry
4. Installs `PKG-PM-CORE-001` assets
5. Writes INSTALLED ledger entry
6. Creates `.genesis_complete` marker
7. System is SEALED

### 12.3 Post-Bootstrap State

| Property | State |
|----------|-------|
| `genesis_bootstrap.py` | Blocked by marker |
| Package manager | Installed and operational |
| Future installs | Via package manager only |
| Exceptions | NONE |

---

## 13. External Keyring

### 13.1 Location

| Allowed | NOT Allowed |
|---------|-------------|
| External HSM | Inside Control Plane |
| Secrets manager | Installed as package |
| `~/.control_plane/trusted_keys.json` | `{CP_ROOT}/config/keys.json` |

### 13.2 Keyring Schema

```json
{
  "keys": [
    {
      "key_id": "maintainer@org-2026",
      "algorithm": "ed25519",
      "public_key": "base64:...",
      "valid_from": "2026-01-01T00:00:00Z",
      "valid_until": "2027-12-31T23:59:59Z",
      "status": "active"
    }
  ]
}
```

### 13.3 Key Rotation Policy

| Trigger | Action |
|---------|--------|
| Key compromise | MUST rotate immediately, revoke old |
| MAJOR version | SHOULD rotate |
| MINOR/PATCH | MAY keep same key |

---

## 14. Gates

### 14.1 G0-PACKAGE

| Check | Failure |
|-------|---------|
| File has package owner | "Orphaned file" |
| Owner is installed | "Owner not installed" |
| Hash matches manifest | "Tampering detected" |

### 14.2 G0-SPEC

| Check | Failure |
|-------|---------|
| Spec owner exists | "Unknown spec owner" |
| Spec references valid framework | "Broken chain" |

### 14.3 G-INTEGRITY

| Check | Failure |
|-------|---------|
| Manifest hash matches computed | "Hash mismatch" |
| Signature verifies | "Invalid signature" |
| Ledger entry exists | "Missing provenance" |
| Ledger chain unbroken | "Chain corruption" |

---

## References

- CP-ARCH-001: Control Plane Architecture Overview
- CP-LEDGER-001: Tiered Ledger Model
- CP-FIREWALL-001: Builder vs Built Firewall
