# Package Compliance Guide

## Overview: The Governance Chain

Every package MUST be part of a governance chain:

```
Framework (FMWK-XXX)
    ↓ registered in frameworks_registry.csv
Spec (SPEC-XXX)
    ↓ registered in specs_registry.csv, references framework
Package (PKG-XXX)
    ↓ references spec_id in manifest.json
Files
    ↓ declared in manifest.json assets
```

**If any link in this chain is missing, the package will FAIL G1 validation.**

---

## Quick Start: Creating a Compliant Package

### Step 1: Ensure Framework Exists

Check if your framework is registered:
```bash
grep "FMWK-100" registries/frameworks_registry.csv
```

If not, register it:
```bash
python3 scripts/pkgutil.py register-framework FMWK-100 --src frameworks/FMWK-100_*.md
```

### Step 2: Ensure Spec Exists

Check if your spec is registered:
```bash
grep "SPEC-MY-001" registries/specs_registry.csv
```

If not, create and register it:
```bash
# Create spec directory
mkdir -p specs/SPEC-MY-001

# Create manifest.yaml
cat > specs/SPEC-MY-001/manifest.yaml << 'EOF'
spec_id: SPEC-MY-001
title: "My Spec Title"
framework_id: FMWK-100
status: active
version: 1.0.0
plane_id: ho3

assets:
  - lib/my_module.py
  - tests/test_my_module.py

invariants:
  - "All methods MUST be documented"

acceptance:
  tests:
    - "pytest tests/test_my_module.py"
EOF

# Register the spec
python3 scripts/pkgutil.py register-spec SPEC-MY-001 --src specs/SPEC-MY-001
```

### Step 3: Create Package

```bash
# For standard packages
python3 scripts/pkgutil.py init PKG-MY-001 --spec SPEC-MY-001 --output _staging/PKG-MY-001

# For agent packages
python3 scripts/pkgutil.py init-agent PKG-MY-AGENT-001 --framework FMWK-100 --output _staging/PKG-MY-AGENT-001
```

### Step 4: Edit manifest.json

The manifest.json MUST have these fields:

```json
{
  "package_id": "PKG-MY-001",
  "schema_version": "1.2",
  "version": "1.0.0",
  "spec_id": "SPEC-MY-001",        // ← REQUIRED: Must reference registered spec
  "plane_id": "ho3",
  "package_type": "library",
  "assets": [
    {
      "path": "lib/my_module.py",
      "sha256": "sha256:abcd1234...",  // ← 64 hex chars after sha256:
      "classification": "library"
    }
  ],
  "dependencies": [],
  "metadata": {
    "description": "My package"
  }
}
```

### Step 5: Validate

```bash
python3 scripts/pkgutil.py preflight PKG-MY-001 --src _staging/PKG-MY-001
```

### Step 6: Stage and Install

```bash
# Stage (creates .tar.gz)
python3 scripts/pkgutil.py stage PKG-MY-001 --src _staging/PKG-MY-001

# Install
CONTROL_PLANE_ALLOW_UNSIGNED=1 python3 scripts/package_install.py \
  --archive _staging/PKG-MY-001.tar.gz --id PKG-MY-001
```

---

## Required Fields in manifest.json

| Field | Required | Format | Example |
|-------|----------|--------|---------|
| `package_id` | YES | `PKG-[A-Z0-9-]+` | `"PKG-MY-TOOL-001"` |
| `schema_version` | YES | `"1.2"` | `"1.2"` |
| `version` | YES | Semver | `"1.0.0"` |
| `spec_id` | **YES** | `SPEC-[A-Z0-9-]+` | `"SPEC-MY-001"` |
| `plane_id` | YES | `ho1\|ho2\|ho3` | `"ho3"` |
| `assets` | YES | Array | See below |
| `package_type` | Recommended | String | `"library"` |
| `dependencies` | Optional | Array of PKG-IDs | `["PKG-CORE-001"]` |
| `metadata` | Optional | Object | `{"description": "..."}` |

---

## Asset Declaration

Each file in your package MUST be declared in `assets`:

```json
{
  "path": "lib/module.py",
  "sha256": "sha256:abc123def456...",  // EXACTLY 64 hex chars
  "classification": "library"          // See classifications below
}
```

### Computing SHA256 Hash

```bash
# Bash
python3 -c "from lib.preflight import compute_sha256; print(compute_sha256('path/to/file'))"

# Or manually
echo -n "sha256:" && shasum -a 256 path/to/file | cut -d' ' -f1
```

### Asset Classifications

| Classification | Use For | Path Pattern |
|---------------|---------|--------------|
| `library` | Python modules | `lib/*.py` |
| `script` | CLI scripts | `scripts/*.py` |
| `test` | Test files | `tests/*.py` |
| `config` | Configuration | `config/*.json`, `*.yaml` |
| `schema` | JSON schemas | `schemas/*.json` |
| `documentation` | Docs | `docs/*.md`, `README.md` |
| `prompt` | Agent prompts | `prompts/*.md` |
| `other` | Everything else | - |

---

## Gate Validations

When you run `preflight`, these gates are checked:

### MANIFEST Gate
- Valid JSON syntax
- `package_id` present and matches filename
- `assets` array present

**Common failures:**
```
MANIFEST FAIL: Missing required field 'package_id'
MANIFEST FAIL: package_id mismatch: manifest has PKG-A, expected PKG-B
```

### G0A Gate (Package Declaration)
- Every file in package is declared in `assets`
- Every declared file exists
- All hashes match
- No path escapes (`../` or absolute paths)

**Common failures:**
```
G0A FAIL: UNDECLARED: lib/extra_file.py
G0A FAIL: HASH_MISMATCH: lib/module.py expected sha256:abc... got sha256:def...
G0A FAIL: PATH_ESCAPE: ../etc/passwd contains '..'
G0A FAIL: Invalid hash format for lib/foo.py: must be sha256:<64 hex chars>
```

### G1 Gate (Chain Validation) - CRITICAL
- `spec_id` field is present and non-empty
- Spec exists in `registries/specs_registry.csv`
- Spec's `framework_id` exists in `registries/frameworks_registry.csv`
- All dependencies are valid PKG-IDs

**Common failures:**
```
G1 FAIL: SPEC_MISSING: Package must have 'spec_id' field
G1 FAIL: SPEC_NOT_FOUND: SPEC-MY-001 not in specs_registry.csv
G1 FAIL: FRAMEWORK_NOT_FOUND: FMWK-XXX referenced by SPEC-MY-001 not found
G1 FAIL: INVALID_DEP: 'bad-dep-format' - must match PKG-[A-Z0-9-]+
```

### OWN Gate (Ownership)
- No file is already owned by another package

**Common failures:**
```
OWN FAIL: OWNERSHIP_CONFLICT: lib/shared.py already owned by PKG-OTHER-001
```

### G5 Gate (Signature)
- Package is signed OR `CONTROL_PLANE_ALLOW_UNSIGNED=1` is set

**Common failures:**
```
G5 FAIL: SIGNATURE_MISSING: Package is not signed
```
**Fix:** Set environment variable for development:
```bash
export CONTROL_PLANE_ALLOW_UNSIGNED=1
```

---

## Complete Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. REGISTER FRAMEWORK (if new)                                  │
│    pkgutil register-framework FMWK-XXX --src frameworks/        │
│    Result: Entry in frameworks_registry.csv                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. REGISTER SPEC (if new)                                       │
│    mkdir -p specs/SPEC-XXX && create manifest.yaml              │
│    pkgutil register-spec SPEC-XXX --src specs/SPEC-XXX          │
│    Result: Entry in specs_registry.csv                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. CREATE PACKAGE SKELETON                                      │
│    pkgutil init PKG-XXX --spec SPEC-XXX --output _staging/      │
│    Result: _staging/PKG-XXX/ with manifest.json template        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. IMPLEMENT                                                    │
│    - Add your code files to the package directory               │
│    - Edit manifest.json to set spec_id                          │
│    - Hashes will be auto-computed by preflight/stage            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. PREFLIGHT VALIDATION                                         │
│    pkgutil preflight PKG-XXX --src _staging/PKG-XXX             │
│    Result: PASS/FAIL with detailed gate results                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. STAGE                                                        │
│    pkgutil stage PKG-XXX --src _staging/PKG-XXX                 │
│    Result: _staging/PKG-XXX.tar.gz + .sha256 + .delta.csv       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. INSTALL                                                      │
│    package_install.py --archive _staging/PKG-XXX.tar.gz         │
│    Result: Files installed, file_ownership.csv updated          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting Checklist

### Package won't pass G1?

1. **Check spec_id is set:**
   ```bash
   jq '.spec_id' _staging/PKG-XXX/manifest.json
   ```

2. **Check spec is registered:**
   ```bash
   grep "SPEC-XXX" registries/specs_registry.csv
   ```

3. **Check framework is registered:**
   ```bash
   grep "FMWK-XXX" registries/frameworks_registry.csv
   ```

### Package has UNDECLARED files?

Run preflight - it will auto-update asset hashes:
```bash
pkgutil preflight PKG-XXX --src _staging/PKG-XXX
```

### Package has HASH_MISMATCH?

Files changed after staging. Re-run:
```bash
pkgutil stage PKG-XXX --src _staging/PKG-XXX
```

### Testing without full governance chain?

Use `--no-strict` flag (testing only, not for production):
```bash
pkgutil preflight PKG-XXX --src _staging/PKG-XXX --no-strict
```

---

## Example: Minimal Compliant Package

### 1. Framework exists (FMWK-100)
```bash
$ grep FMWK-100 registries/frameworks_registry.csv
FMWK-100,Agent Development Standard,active,1.0.0,ho3,2026-02-01T00:00:00Z
```

### 2. Create and register spec
```bash
mkdir -p specs/SPEC-EXAMPLE-001
cat > specs/SPEC-EXAMPLE-001/manifest.yaml << 'EOF'
spec_id: SPEC-EXAMPLE-001
title: "Example Spec"
framework_id: FMWK-100
status: active
version: 1.0.0
plane_id: ho3
assets:
  - lib/example.py
EOF

python3 scripts/pkgutil.py register-spec SPEC-EXAMPLE-001 --src specs/SPEC-EXAMPLE-001
```

### 3. Create package
```bash
python3 scripts/pkgutil.py init PKG-EXAMPLE-001 --spec SPEC-EXAMPLE-001 --output _staging/PKG-EXAMPLE-001

# Add code
echo '# Example module' > _staging/PKG-EXAMPLE-001/lib/example.py

# Edit manifest.json to set spec_id
# (pkgutil init should do this, but verify)
```

### 4. Validate and install
```bash
python3 scripts/pkgutil.py preflight PKG-EXAMPLE-001 --src _staging/PKG-EXAMPLE-001
python3 scripts/pkgutil.py stage PKG-EXAMPLE-001 --src _staging/PKG-EXAMPLE-001
CONTROL_PLANE_ALLOW_UNSIGNED=1 python3 scripts/package_install.py \
  --archive _staging/PKG-EXAMPLE-001.tar.gz --id PKG-EXAMPLE-001
```

---

## Reference

- **Package Schema:** `schemas/package_manifest.json`
- **Example Package:** `installed/PKG-BASELINE-HO3-000/manifest.json`
- **Framework Standard:** `frameworks/FMWK-107_package_management_standard.md`
- **Specs Registry:** `registries/specs_registry.csv`
- **Frameworks Registry:** `registries/frameworks_registry.csv`
