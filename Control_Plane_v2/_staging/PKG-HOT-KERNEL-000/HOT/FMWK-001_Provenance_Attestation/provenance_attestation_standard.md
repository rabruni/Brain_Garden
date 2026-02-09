# FMWK-ATT-001: Provenance Attestation Standard

**Version:** 1.0.0
**Status:** Active
**Category:** Security
**Dependencies:** FMWK-100, FMWK-107, FMWK-200
**Author:** system
**Created:** 2026-01-31

---

## 1. Purpose

This framework defines the provenance attestation standard for Control Plane packages. Attestations provide cryptographic binding between an archive's content and its build/source provenance, enabling supply chain security verification.

---

## 2. Attestation Schema v1.0

### 2.1 JSON Structure

```json
{
  "schema_version": "1.0",
  "package_id": "PKG-FMWK-100",
  "package_digest_sha256": "8f2589b3fec3ab42ac918b54b90d1c4c08b28ddbbbc79b13b89bf1b1598fc6fc",
  "built_at": "2026-01-31T12:00:00+00:00",
  "builder": {
    "tool": "control_plane_package_pack",
    "tool_version": "2.0.0"
  },
  "source": {
    "repo": "https://github.com/org/control_plane",
    "revision": "abc123def456",
    "branch": "main"
  },
  "metadata": {}
}
```

### 2.2 Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | string | Yes | Must be "1.0" |
| `package_id` | string | Yes | Package identifier (e.g., PKG-FMWK-100) |
| `package_digest_sha256` | string | Yes | SHA256 hash of archive file |
| `built_at` | string | Yes | RFC3339 UTC timestamp |
| `builder.tool` | string | Yes | Build tool name |
| `builder.tool_version` | string | Yes | Build tool version |
| `source.repo` | string | No | Source repository URL |
| `source.revision` | string | No | Source commit SHA |
| `source.branch` | string | No | Source branch name |
| `metadata` | object | No | Additional metadata |

---

## 3. File Naming Convention

| File | Extension | Description |
|------|-----------|-------------|
| Archive | `.tar.gz` | Package archive |
| Attestation | `.tar.gz.attestation.json` | Provenance attestation |
| Attestation Signature | `.tar.gz.attestation.json.sig` | Signed attestation |

---

## 4. Generation Rules

### 4.1 Pack-Time Generation

Attestations are generated at pack time using `package_pack.py`:

```bash
# Generate attestation
python3 scripts/package_pack.py --src frameworks/FMWK-100.md --id PKG-FMWK-100 --attest

# With source provenance
python3 scripts/package_pack.py --src frameworks/FMWK-100.md --id PKG-FMWK-100 \
    --attest --source-repo https://github.com/org/repo --source-revision abc123

# Auto-generate via environment
export CONTROL_PLANE_ATTEST_PACKAGES=1
python3 scripts/package_pack.py --src frameworks/FMWK-100.md --id PKG-FMWK-100
```

### 4.2 Requirements

1. Archive MUST exist before attestation creation
2. `package_digest_sha256` MUST match archive content
3. `built_at` MUST be UTC timestamp at creation time
4. Attestation MUST be written to DERIVED path (packages_store)

---

## 5. Verification Rules

### 5.1 Install-Time Verification

Package install verifies attestations in this order:

1. **Presence Check**: Does `.attestation.json` exist?
2. **Schema Validation**: Is `schema_version` supported?
3. **Digest Binding**: Does `package_digest_sha256` match archive?
4. **Optional Signature**: If `.attestation.json.sig` exists, verify

### 5.2 Fail-Closed Behavior

```python
# Default: Fail if attestation missing
if not has_attestation(archive):
    raise SystemExit("ERROR: Package missing attestation.")

# Waiver: Allow unattested with explicit opt-in
export CONTROL_PLANE_ALLOW_UNATTESTED=1
```

### 5.3 Verification Failures

| Failure | Error | Action |
|---------|-------|--------|
| Missing attestation | `AttestationMissing` | Block unless waived |
| Digest mismatch | `AttestationDigestMismatch` | Block (tamper detected) |
| Invalid JSON | `AttestationVerificationFailed` | Block |
| Unknown schema | `AttestationVerificationFailed` | Block |

---

## 6. Registry Schema Extensions

### 6.1 New Columns in packages_registry.csv

| Column | Description |
|--------|-------------|
| `attestation_path` | Path to `.attestation.json` file |
| `attestation_digest` | SHA256 of attestation file |
| `attestation_signature_path` | Path to `.attestation.json.sig` |

### 6.2 Example Row

```csv
id,name,...,signature,attestation_path,attestation_digest,attestation_signature_path,...
PKG-FMWK-100,Agent Development Standard,...,packages_store/FMWK-100.tar.gz.sig,packages_store/FMWK-100.tar.gz.attestation.json,abc123...,packages_store/FMWK-100.tar.gz.attestation.json.sig,...
```

---

## 7. Ledger Events

### 7.1 Event Types

| Event | Description |
|-------|-------------|
| `ATTESTATION_CREATED` | Attestation generated successfully |
| `ATTESTATION_SIGNED` | Attestation signature created |
| `ATTESTATION_VERIFIED` | Attestation verified at install time |
| `ATTESTATION_FAILED` | Verification failed (tamper/schema error) |
| `ATTESTATION_MISSING` | No attestation found |
| `ATTESTATION_WAIVED` | Unattested package installed with waiver |

### 7.2 Ledger Entry Format

```json
{
  "event_type": "provenance_attestation_verified",
  "submission_id": "PKG-FMWK-100",
  "decision": "ATTESTATION_VERIFIED",
  "reason": "ATTESTATION_VERIFIED: FMWK-100.tar.gz",
  "metadata": {
    "archive": "/path/to/FMWK-100.tar.gz",
    "schema_version": "1.0",
    "package_id": "PKG-FMWK-100",
    "package_digest": "8f2589b3fec3ab...",
    "built_at": "2026-01-31T12:00:00+00:00",
    "builder_tool": "control_plane_package_pack"
  }
}
```

---

## 8. Waiver Rules

### 8.1 Development Only

Waivers are intended for development environments only:

```bash
# Allow unattested packages (dev only)
export CONTROL_PLANE_ALLOW_UNATTESTED=1
```

### 8.2 CI/Production Enforcement

On main/release branches, waivers MUST NOT be used:

```yaml
# CI enforces strict attestation
env:
  CONTROL_PLANE_ALLOW_UNATTESTED: "0"
  CONTROL_PLANE_ALLOW_UNSIGNED: "0"
```

### 8.3 Waiver Logging

All waivers are logged to the ledger with:
- Package ID
- Archive path
- Actor identity
- Waiver reason

---

## 9. Implementation Reference

### 9.1 Core Library

**File:** `lib/provenance.py`

```python
from lib.provenance import (
    create_attestation,
    sign_attestation,
    verify_attestation,
    has_attestation,
    log_attestation_waiver,
    Attestation,
    BuilderInfo,
    SourceInfo,
)
```

### 9.2 CLI Integration

**Pack with attestation:**
```bash
python3 scripts/package_pack.py --src FILE --id PKG-ID --attest --sign
```

**Install with verification:**
```bash
python3 scripts/package_install.py --archive PKG.tar.gz --id PKG-ID
```

---

## 10. Security Considerations

### 10.1 Supply Chain Protection

Attestations protect against:
1. **Tampering**: Digest binding detects modified archives
2. **Substitution**: Package ID binding prevents swaps
3. **Provenance Falsification**: Source info provides audit trail

### 10.2 Trust Model

- Attestations are self-signed by the build tool
- Optional cryptographic signatures add external trust
- Ledger provides immutable audit trail

### 10.3 Limitations

- Attestations do not verify source code quality
- Build environment is trusted
- Signing keys must be protected

---

## 11. Validation Checklist

| Check | Description |
|-------|-------------|
| Schema version is "1.0" | Reject unknown versions |
| Package digest matches | Archive content integrity |
| Built_at is valid RFC3339 | Temporal integrity |
| Builder info present | Tool identification |
| Ledger event logged | Audit trail |

---

## 12. Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-31 | Initial release |
