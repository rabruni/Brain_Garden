# Package Compliance Quick Reference

## TL;DR - Minimum Requirements

A compliant package needs:

1. **manifest.json** with:
   - `package_id`: `PKG-[A-Z0-9-]+` (e.g., `PKG-MY-TOOL-001`)
   - `schema_version`: `"1.2"`
   - `version`: Semver (e.g., `"1.0.0"`)
   - `assets`: Array of files with paths and SHA256 hashes

2. **All files declared** in `assets` with correct hashes
3. **No undeclared files** in the package
4. **No path escapes** (no `../` or absolute paths)

## Manifest Template (v1.2)

```json
{
  "package_id": "PKG-MY-TOOL-001",
  "package_type": "library",
  "schema_version": "1.2",
  "version": "1.0.0",
  "spec_id": "",
  "plane_id": "ho3",
  "assets": [
    {
      "path": "lib/my_module.py",
      "sha256": "sha256:64_hex_characters_here",
      "classification": "code"
    },
    {
      "path": "tests/test_my_module.py",
      "sha256": "sha256:64_hex_characters_here",
      "classification": "test"
    }
  ],
  "dependencies": [],
  "metadata": {
    "author": "",
    "description": "My package description"
  }
}
```

## Asset Hash Format

Hashes MUST be in format: `sha256:<64 hex characters>`

Generate with:
```bash
echo -n "sha256:" && shasum -a 256 <file> | cut -d' ' -f1
```

Or in Python:
```python
import hashlib
content = open(filepath, 'rb').read()
hash_val = f"sha256:{hashlib.sha256(content).hexdigest()}"
```

## Asset Classifications

| Classification | Use For |
|---------------|---------|
| `code` | Python modules (`lib/*.py`, `scripts/*.py`) |
| `test` | Test files (`tests/*.py`) |
| `config` | Configuration (`config/*.json`, `*.yaml`) |
| `schema` | JSON schemas (`schemas/*.json`) |
| `policy` | Policy files (`policies/*.yaml`) |
| `framework` | Framework definitions (`frameworks/*.md`) |
| `doc` | Documentation (`docs/*.md`) |
| `data` | Data files |

## Package Types

| Type | Description |
|------|-------------|
| `library` | Code modules |
| `tool` | CLI tools/scripts |
| `agent` | Agent packages (FMWK-100) |
| `framework` | Framework definitions |
| `spec` | Spec packs |
| `gate` | Gate implementations |
| `baseline` | Baseline packages (claim existing files) |

## Directory Structure

```
PKG-MY-TOOL-001/
├── manifest.json       # Required
├── lib/               # Code modules
│   └── my_module.py
├── tests/             # Tests
│   └── test_my_module.py
└── README.md          # Optional
```

For agent packages, also include:
```
├── capabilities.yaml   # Agent capabilities
└── prompts/
    ├── system.md      # System prompt
    └── turn.md        # Per-turn prompt
```

## Validation Commands

```bash
# Check if package is compliant (BEFORE staging)
python3 scripts/pkgutil.py preflight PKG-MY-TOOL-001 --src _staging/PKG-MY-TOOL-001

# JSON output for programmatic use
python3 scripts/pkgutil.py preflight PKG-MY-TOOL-001 --src _staging/PKG-MY-TOOL-001 --json

# Preview registry changes (delta)
python3 scripts/pkgutil.py delta PKG-MY-TOOL-001 --src _staging/PKG-MY-TOOL-001
```

## Gate Checks (What Preflight Validates)

| Gate | Check | Common Failure |
|------|-------|----------------|
| **MANIFEST** | Valid JSON, required fields | Missing `package_id` or `assets` |
| **G0A** | All files declared, hashes match | `UNDECLARED: extra.py` or `HASH_MISMATCH` |
| **G1** | Framework/spec chain valid | `FRAMEWORK_NOT_FOUND: FMWK-XXX` |
| **OWN** | No ownership conflicts | `OWNERSHIP_CONFLICT: lib/foo.py owned by PKG-OTHER` |
| **G5** | Signature (or waiver) | Set `CONTROL_PLANE_ALLOW_UNSIGNED=1` for dev |

## Common Errors and Fixes

### UNDECLARED file
```
G0A FAIL: UNDECLARED: lib/helper.py
```
**Fix**: Add the file to `assets` array with correct hash.

### HASH_MISMATCH
```
G0A FAIL: HASH_MISMATCH: lib/module.py expected sha256:abc... got sha256:def...
```
**Fix**: Recompute hash after editing file.

### PATH_ESCAPE
```
G0A FAIL: PATH_ESCAPE: ../etc/passwd
```
**Fix**: Use relative paths only, no `../` or absolute paths.

### Invalid hash format
```
G0A FAIL: Invalid hash format: md5:abc123
```
**Fix**: Use `sha256:<64 hex>` format only.

## Workflow

1. **Create skeleton**:
   ```bash
   python3 scripts/pkgutil.py init PKG-MY-TOOL-001 --output _staging/PKG-MY-TOOL-001
   # Or for agents:
   python3 scripts/pkgutil.py init-agent PKG-MY-AGENT-001 --framework FMWK-100 --output _staging/PKG-MY-AGENT-001
   ```

2. **Implement** your code in the package directory

3. **Validate**:
   ```bash
   python3 scripts/pkgutil.py preflight PKG-MY-TOOL-001 --src _staging/PKG-MY-TOOL-001
   ```

4. **Stage** (creates installable archive):
   ```bash
   python3 scripts/pkgutil.py stage PKG-MY-TOOL-001 --src _staging/PKG-MY-TOOL-001
   ```

5. **Install**:
   ```bash
   python3 scripts/package_install.py --archive _staging/PKG-MY-TOOL-001.tar.gz --id PKG-MY-TOOL-001
   ```

## Environment Variables

| Variable | Effect |
|----------|--------|
| `CONTROL_PLANE_ALLOW_UNSIGNED=1` | Skip signature validation (dev only) |

## Reference Files

- Schema: `schemas/package_manifest.json`
- Example: `installed/PKG-BASELINE-HO3-000/manifest.json`
- Framework: `frameworks/FMWK-107_package_management_standard.md`
