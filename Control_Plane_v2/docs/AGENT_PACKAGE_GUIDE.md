# Agent Package Management Guide

This document provides everything an agent needs to help humans create, validate, and install packages in the Control Plane governance system.

---

## Quick Reference

### Essential Commands

```bash
# Query compliance requirements (use --json for programmatic access)
python3 scripts/pkgutil.py compliance summary --json
python3 scripts/pkgutil.py compliance gates --json
python3 scripts/pkgutil.py compliance troubleshoot --error G1 --json

# Create packages
python3 scripts/pkgutil.py init PKG-XXX --spec SPEC-XXX --output _staging/PKG-XXX
python3 scripts/pkgutil.py init-agent PKG-XXX --framework FMWK-100 --output _staging/PKG-XXX

# Validate and install
python3 scripts/pkgutil.py preflight PKG-XXX --src _staging/PKG-XXX
python3 scripts/pkgutil.py stage PKG-XXX --src _staging/PKG-XXX
CONTROL_PLANE_ALLOW_UNSIGNED=1 python3 scripts/package_install.py --archive _staging/PKG-XXX.tar.gz --id PKG-XXX
```

### Programmatic API

```python
from lib.agent_helpers import CPInspector

inspector = CPInspector()

# Get complete compliance requirements
summary, evidence = inspector.get_compliance_summary()

# List what's available
frameworks, _ = inspector.list_available_frameworks()
specs, _ = inspector.list_available_specs(framework_id="FMWK-100")

# Get help for errors
guide, _ = inspector.get_troubleshooting_guide(error_type="G1")
```

---

## The Governance Chain (CRITICAL)

Every package MUST be part of this chain:

```
Framework (FMWK-XXX)     ← Defines governance rules
    ↓ registered in frameworks_registry.csv
Spec (SPEC-XXX)          ← Defines what files the package owns
    ↓ registered in specs_registry.csv
Package (PKG-XXX)        ← Contains the actual files
    ↓ manifest.json references spec_id
Files                    ← Declared in manifest.json assets
```

**If any link is missing, G1 gate validation FAILS.**

---

## Complete Workflow

### Step 1: Check What Already Exists

Before creating anything, check what frameworks and specs are available:

```bash
# List all frameworks
python3 scripts/pkgutil.py compliance frameworks

# List all specs
python3 scripts/pkgutil.py compliance specs

# List specs for a specific framework
python3 scripts/pkgutil.py compliance specs --framework FMWK-100 --json
```

Or programmatically:

```python
from lib.agent_helpers import CPInspector
inspector = CPInspector()

frameworks, _ = inspector.list_available_frameworks()
for fw in frameworks:
    print(f"{fw['framework_id']}: {fw['title']}")

specs, _ = inspector.list_available_specs()
for spec in specs:
    print(f"{spec['spec_id']}: {spec['title']} (framework: {spec['framework_id']})")
```

### Step 2: Register Framework (if needed)

If the framework doesn't exist:

```bash
# Check if framework exists
grep "FMWK-100" registries/frameworks_registry.csv

# Register new framework
python3 scripts/pkgutil.py register-framework FMWK-NEW --src frameworks/FMWK-NEW_name.md
```

Framework files live in `frameworks/` and follow the pattern `FMWK-XXX_description.md`.

### Step 3: Create and Register Spec (if needed)

If the spec doesn't exist:

```bash
# Create spec directory structure
mkdir -p specs/SPEC-MY-001

# Create manifest.yaml (REQUIRED fields shown)
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
  - "All public methods MUST be documented"

acceptance:
  tests:
    - "pytest tests/test_my_module.py"
EOF

# Register the spec
python3 scripts/pkgutil.py register-spec SPEC-MY-001 --src specs/SPEC-MY-001
```

### Step 4: Create Package Skeleton

```bash
# For library/standard packages
python3 scripts/pkgutil.py init PKG-MY-001 --spec SPEC-MY-001 --output _staging/PKG-MY-001

# For agent packages (includes prompts/, capabilities.yaml)
python3 scripts/pkgutil.py init-agent PKG-MY-AGENT-001 --framework FMWK-100 --output _staging/PKG-MY-AGENT-001
```

This creates:
```
_staging/PKG-MY-001/
├── manifest.json      ← Package metadata
├── lib/
│   └── (your code)
└── tests/
    └── (your tests)
```

### Step 5: Implement the Package

Add your code files to the package directory. The manifest.json will be auto-updated during preflight.

**Important**: Ensure `spec_id` is set in manifest.json:

```json
{
  "package_id": "PKG-MY-001",
  "schema_version": "1.2",
  "version": "1.0.0",
  "spec_id": "SPEC-MY-001",
  "plane_id": "ho3",
  "package_type": "library",
  "assets": []
}
```

### Step 6: Validate with Preflight

```bash
python3 scripts/pkgutil.py preflight PKG-MY-001 --src _staging/PKG-MY-001
```

This runs all validation gates:
- **MANIFEST**: Valid JSON, required fields present
- **G0A**: All files declared, hashes match, no path escapes
- **G1**: spec_id → spec exists → framework exists
- **OWN**: No file ownership conflicts
- **G5**: Signature check (waived with CONTROL_PLANE_ALLOW_UNSIGNED=1)

**Preflight auto-updates asset hashes**, so run it after any file changes.

### Step 7: Stage the Package

```bash
python3 scripts/pkgutil.py stage PKG-MY-001 --src _staging/PKG-MY-001
```

Creates:
- `_staging/PKG-MY-001.tar.gz` - Installable archive
- `_staging/PKG-MY-001.tar.gz.sha256` - Checksum
- `_staging/PKG-MY-001.delta.csv` - Registry changes preview

### Step 8: Install

```bash
CONTROL_PLANE_ALLOW_UNSIGNED=1 python3 scripts/package_install.py \
  --archive _staging/PKG-MY-001.tar.gz \
  --id PKG-MY-001
```

---

## Gate Validations Explained

### MANIFEST Gate
- Valid JSON syntax
- `package_id` present and matches expected
- `assets` array present

### G0A Gate (Package Declaration)
- Every file in package directory is declared in `assets`
- Every declared file exists
- All SHA256 hashes match
- No path escapes (`../` or absolute paths)

### G1 Gate (Chain Validation) - CRITICAL
- `spec_id` field is present and non-empty
- Spec exists in `registries/specs_registry.csv`
- Spec's `framework_id` exists in `registries/frameworks_registry.csv`
- All dependencies are valid PKG-IDs

### OWN Gate (Ownership)
- No file is already owned by another installed package

### G5 Gate (Signature)
- Package is signed OR `CONTROL_PLANE_ALLOW_UNSIGNED=1` is set

---

## Troubleshooting Common Errors

### G1 FAIL: SPEC_MISSING

**Cause**: Package manifest missing `spec_id` field.

**Fix**:
```bash
# Check current spec_id
jq '.spec_id' _staging/PKG-XXX/manifest.json

# Add spec_id to manifest.json
```

### G1 FAIL: SPEC_NOT_FOUND

**Cause**: `spec_id` references a spec that isn't registered.

**Fix**:
```bash
# Check if spec exists
grep "SPEC-XXX" registries/specs_registry.csv

# If not, register it
python3 scripts/pkgutil.py register-spec SPEC-XXX --src specs/SPEC-XXX
```

### G1 FAIL: FRAMEWORK_NOT_FOUND

**Cause**: Spec references a framework that isn't registered.

**Fix**:
```bash
# Check if framework exists
grep "FMWK-XXX" registries/frameworks_registry.csv

# If not, register it
python3 scripts/pkgutil.py register-framework FMWK-XXX --src frameworks/
```

### G0A FAIL: UNDECLARED

**Cause**: File exists in package but not in `assets` array.

**Fix**:
```bash
# Preflight auto-updates hashes
python3 scripts/pkgutil.py preflight PKG-XXX --src _staging/PKG-XXX
```

### G0A FAIL: HASH_MISMATCH

**Cause**: File content changed after hash was computed.

**Fix**:
```bash
# Re-run preflight to update hashes
python3 scripts/pkgutil.py preflight PKG-XXX --src _staging/PKG-XXX

# Then re-stage
python3 scripts/pkgutil.py stage PKG-XXX --src _staging/PKG-XXX
```

### OWN FAIL: OWNERSHIP_CONFLICT

**Cause**: A file is already owned by another installed package.

**Fix**: Either:
1. Remove the conflicting file from your package
2. Uninstall the conflicting package first

### G5 FAIL: SIGNATURE_MISSING

**Cause**: Package not signed (required in production).

**Fix for development**:
```bash
export CONTROL_PLANE_ALLOW_UNSIGNED=1
```

---

## Manifest.json Reference

### Required Fields

| Field | Format | Example |
|-------|--------|---------|
| `package_id` | `PKG-[A-Z0-9-]+` | `"PKG-MY-TOOL-001"` |
| `schema_version` | `"1.2"` | `"1.2"` |
| `version` | Semver | `"1.0.0"` |
| `spec_id` | `SPEC-[A-Z0-9-]+` | `"SPEC-MY-001"` |
| `plane_id` | `ho1\|ho2\|ho3` | `"ho3"` |
| `assets` | Array | See below |

### Optional Fields

| Field | Format | Example |
|-------|--------|---------|
| `package_type` | String | `"library"`, `"agent"` |
| `dependencies` | Array of PKG-IDs | `["PKG-CORE-001"]` |
| `metadata` | Object | `{"description": "..."}` |
| `capabilities` | Array (agents) | `["inspect", "explain"]` |

### Asset Object

```json
{
  "path": "lib/module.py",
  "sha256": "sha256:abc123...",
  "classification": "library"
}
```

### Asset Classifications

| Classification | Use For | Path Pattern |
|---------------|---------|--------------|
| `library` | Python modules | `lib/*.py` |
| `script` | CLI scripts | `scripts/*.py` |
| `test` | Test files | `tests/*.py` |
| `config` | Configuration | `config/*.json`, `*.yaml` |
| `schema` | JSON schemas | `schemas/*.json` |
| `documentation` | Docs | `docs/*.md` |
| `prompt` | Agent prompts | `prompts/*.md` |
| `other` | Everything else | - |

---

## Example: Complete Package Creation

### Scenario: Create a utility library package

```bash
# 1. Check framework exists (FMWK-100 is Agent Development Standard)
grep "FMWK-100" registries/frameworks_registry.csv
# Output: FMWK-100,Agent Development Standard,active,...

# 2. Create and register spec
mkdir -p specs/SPEC-UTILS-001
cat > specs/SPEC-UTILS-001/manifest.yaml << 'EOF'
spec_id: SPEC-UTILS-001
title: "Utility Functions"
framework_id: FMWK-100
status: active
version: 1.0.0
plane_id: ho3
assets:
  - lib/utils.py
  - tests/test_utils.py
invariants:
  - "All functions MUST have docstrings"
acceptance:
  tests:
    - "pytest tests/test_utils.py"
EOF

python3 scripts/pkgutil.py register-spec SPEC-UTILS-001 --src specs/SPEC-UTILS-001

# 3. Create package skeleton
python3 scripts/pkgutil.py init PKG-UTILS-001 --spec SPEC-UTILS-001 --output _staging/PKG-UTILS-001

# 4. Add code
cat > _staging/PKG-UTILS-001/lib/utils.py << 'EOF'
"""Utility functions for Control Plane."""

def format_id(prefix: str, number: int) -> str:
    """Format an ID with prefix and zero-padded number."""
    return f"{prefix}-{number:03d}"
EOF

cat > _staging/PKG-UTILS-001/tests/test_utils.py << 'EOF'
"""Tests for utils module."""
from lib.utils import format_id

def test_format_id():
    assert format_id("PKG", 1) == "PKG-001"
    assert format_id("SPEC", 42) == "SPEC-042"
EOF

# 5. Validate
python3 scripts/pkgutil.py preflight PKG-UTILS-001 --src _staging/PKG-UTILS-001

# 6. Stage
python3 scripts/pkgutil.py stage PKG-UTILS-001 --src _staging/PKG-UTILS-001

# 7. Install
CONTROL_PLANE_ALLOW_UNSIGNED=1 python3 scripts/package_install.py \
  --archive _staging/PKG-UTILS-001.tar.gz --id PKG-UTILS-001

# 8. Verify
python3 scripts/gate_check.py --all
```

---

## Querying Compliance Information

### CLI Queries

```bash
# Get full summary
python3 scripts/pkgutil.py compliance summary

# Get gate details
python3 scripts/pkgutil.py compliance gates

# Get manifest requirements
python3 scripts/pkgutil.py compliance manifest

# Get workflow steps
python3 scripts/pkgutil.py compliance workflow

# List frameworks
python3 scripts/pkgutil.py compliance frameworks

# List specs (optionally filter by framework)
python3 scripts/pkgutil.py compliance specs
python3 scripts/pkgutil.py compliance specs --framework FMWK-100

# Get troubleshooting help
python3 scripts/pkgutil.py compliance troubleshoot
python3 scripts/pkgutil.py compliance troubleshoot --error G1

# Get example manifest
python3 scripts/pkgutil.py compliance example
python3 scripts/pkgutil.py compliance example --type agent
```

### JSON Output for Programmatic Use

Add `--json` to any compliance command:

```bash
python3 scripts/pkgutil.py compliance summary --json
python3 scripts/pkgutil.py compliance specs --framework FMWK-100 --json
```

### Python API

```python
from lib.agent_helpers import CPInspector

inspector = CPInspector()

# Complete summary
summary, evidence = inspector.get_compliance_summary()
print(f"Available frameworks: {len(summary['available_frameworks'])}")
print(f"Available specs: {len(summary['available_specs'])}")

# Governance chain
chain, _ = inspector.get_governance_chain()
for level in chain['chain']:
    print(f"Level {level['level']}: {level['name']}")

# Gate requirements
gates, _ = inspector.get_gate_requirements()
for gate_id, gate in gates['gates'].items():
    print(f"{gate_id}: {gate['description']}")

# Troubleshooting
guide, _ = inspector.get_troubleshooting_guide(error_type="G1")
for key, item in guide['troubleshooting'].items():
    print(f"{item['symptom']}: {item['fix']}")

# Get spec manifest
manifest, _ = inspector.get_spec_manifest("SPEC-CORE-001")
if manifest:
    print(f"Assets: {manifest.get('assets', [])}")
```

---

## Files and Registries Reference

### Key Directories

| Path | Purpose |
|------|---------|
| `frameworks/` | Framework definition files (FMWK-XXX_*.md) |
| `specs/` | Spec directories with manifest.yaml |
| `_staging/` | Working area for package development |
| `installed/` | Installed package manifests |
| `packages_store/` | Package archives |
| `registries/` | CSV registries |

### Key Registries

| Registry | Purpose |
|----------|---------|
| `registries/frameworks_registry.csv` | Registered frameworks |
| `registries/specs_registry.csv` | Registered specs |
| `registries/file_ownership.csv` | Which package owns each file |
| `registries/packages_state.csv` | Installed package status |

### Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/pkgutil.py` | Package authoring CLI |
| `scripts/package_install.py` | Install packages |
| `scripts/gate_check.py` | Verify all gates pass |
| `scripts/rebuild_derived_registries.py` | Rebuild file_ownership.csv |

---

## Best Practices for Agents

1. **Always query before creating**: Check if framework/spec exists before trying to register
2. **Use --json for parsing**: Machine-readable output is more reliable
3. **Run preflight after changes**: It auto-updates hashes
4. **Check gates after install**: Run `gate_check.py --all` to verify
5. **Use evidence pointers**: CPInspector methods return evidence for auditability
6. **Handle errors gracefully**: Use troubleshooting guide for common issues

---

## Testing Mode

For development/testing without full governance chain:

```bash
# Skip spec_id requirement (testing only)
python3 scripts/pkgutil.py preflight PKG-XXX --src _staging/PKG-XXX --no-strict

# Stage without strict validation
python3 scripts/pkgutil.py stage PKG-XXX --src _staging/PKG-XXX --no-strict
```

**Note**: `--no-strict` is for testing only. Production packages MUST have valid governance chains.
