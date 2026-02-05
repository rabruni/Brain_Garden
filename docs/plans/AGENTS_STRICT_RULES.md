# Agent Governance Rules (Control Plane v2) - STRICT VERSION

**STATUS**: SAVED FOR LATER - Apply after current sprints complete

**TO APPLY**: Copy this content to `/playground/AGENTS.md`

---

**CRITICAL**: This document defines MANDATORY constraints for all AI agents working in this repository. Violations create orphan files that break governance.

---

## Core Principle: Build Outside, Install Inside

```
YOU BUILD HERE:          _staging/PKG-XXX/
                         _external_quarantine/

YOU QUERY HERE:          Control_Plane_v2/ (READ-ONLY for agents)

INSTALLATION ONLY VIA:   python3 scripts/package_install.py
```

**NEVER write directly to governed roots** (`lib/`, `modules/`, `scripts/`, `frameworks/`, `specs/`, `registries/`, `schemas/`, `tests/`, `docs/`, `gates/`).

---

## Governed Roots (READ-ONLY for Agents)

These directories are governed by packages. Direct writes create orphans.

| Path | Owner | Agent Access |
|------|-------|--------------|
| `lib/` | PKG-BASELINE-HO3-000 | READ-ONLY |
| `modules/` | Various packages | READ-ONLY |
| `scripts/` | PKG-BASELINE-HO3-000 | READ-ONLY |
| `frameworks/` | Framework packages | READ-ONLY |
| `specs/` | Spec packages | READ-ONLY |
| `registries/` | Derived (rebuild only) | READ-ONLY |
| `schemas/` | PKG-BASELINE-HO3-000 | READ-ONLY |
| `tests/` | Various packages | READ-ONLY |
| `docs/` | Various packages | READ-ONLY |
| `gates/` | Gate packages | READ-ONLY |
| `ledger/` | Append-only | APPEND via scripts only |
| `installed/` | Package manager | NEVER |
| `config/` | System | NEVER |

---

## Agent Workspace (WRITE-ALLOWED)

| Path | Purpose | Cleanup |
|------|---------|---------|
| `_staging/PKG-XXX/` | Build packages here | Delete after install |
| `_external_quarantine/` | Import external files | Process into packages |
| `tmp/` | Temporary work | Auto-cleaned |

---

## Mandatory Workflow: Creating or Modifying Code

### Step 1: Check What Exists

Before ANY work, query the Control Plane:

```bash
# What packages exist?
echo '{"operation": "pkg_list"}' | python3 -m modules.shell | jq

# What spec should I use?
echo '{"operation": "list_specs"}' | python3 -m modules.shell | jq

# Is this path governed?
echo '{"operation": "explain_path", "path": "lib/myfile.py"}' | python3 -m modules.shell | jq

# What are the manifest requirements?
echo '{"operation": "manifest_requirements"}' | python3 -m modules.shell | jq
```

### Step 2: Create Package in Staging

```bash
# Create package skeleton
python3 scripts/pkgutil.py init PKG-MY-FEATURE-001 \
  --spec SPEC-XXX \
  --output _staging/PKG-MY-FEATURE-001

# For agent packages
python3 scripts/pkgutil.py init-agent PKG-MY-AGENT-001 \
  --framework FMWK-100 \
  --output _staging/PKG-MY-AGENT-001
```

### Step 3: Build Your Code in Staging

Write ALL new files to `_staging/PKG-XXX/`:

```
_staging/PKG-MY-FEATURE-001/
├── manifest.json           # Package manifest
├── lib/
│   └── my_module.py        # Your code
├── tests/
│   └── test_my_module.py   # Your tests
└── README.md               # Documentation
```

### Step 4: Validate Before Installing

```bash
# Run preflight (validates G0A, G1, ownership)
python3 scripts/pkgutil.py preflight PKG-MY-FEATURE-001 \
  --src _staging/PKG-MY-FEATURE-001

# If preflight fails, FIX IT before proceeding
```

### Step 5: Stage and Install

```bash
# Stage (creates tar.gz)
python3 scripts/pkgutil.py stage PKG-MY-FEATURE-001 \
  --src _staging/PKG-MY-FEATURE-001

# Install (moves files to governed roots)
CONTROL_PLANE_ALLOW_UNSIGNED=1 python3 scripts/package_install.py \
  --archive _staging/PKG-MY-FEATURE-001.tar.gz \
  --id PKG-MY-FEATURE-001
```

### Step 6: Verify and Cleanup

```bash
# Verify gates pass
python3 scripts/gate_check.py --all

# Clean up staging
rm -rf _staging/PKG-MY-FEATURE-001/
rm _staging/PKG-MY-FEATURE-001.tar.gz
```

---

## Modifying Existing Packages

If you need to modify files owned by an existing package:

### Option A: Patch Package (Preferred)

1. Find owner: `echo '{"operation": "explain_path", "path": "lib/target.py"}' | python3 -m modules.shell`
2. Copy existing package to staging
3. Modify files in staging
4. Bump version in manifest.json
5. Preflight → Stage → Install

### Option B: New Package (if adding new files)

1. Create new spec if needed (frameworks + specs must exist)
2. Create package in staging referencing that spec
3. Preflight → Stage → Install

---

## Forbidden Actions (WILL CREATE ORPHANS)

| Action | Why Forbidden | Alternative |
|--------|---------------|-------------|
| `Write` to `lib/*.py` | Creates orphan | Build in `_staging/`, install |
| `Write` to `modules/*/` | Creates orphan | Build in `_staging/`, install |
| `Write` to `scripts/*.py` | Creates orphan | Build in `_staging/`, install |
| `Edit` governed file directly | Breaks hash | Modify in staging, reinstall |
| Create file without package | Orphan | Always package first |
| Delete governed file | Breaks ownership | Uninstall package |

---

## Pre-Flight Checklist (Before Writing ANY Code)

- [ ] Did I query `explain_path` to check if target is governed?
- [ ] Am I writing to `_staging/PKG-XXX/` (not governed roots)?
- [ ] Does my package have a valid `spec_id` referencing a registered spec?
- [ ] Does the spec reference a registered framework?
- [ ] Did I run `preflight` and it passed?

---

## Handling Orphan Files

If you've created orphans (files in governed roots without package ownership):

### Option 1: Package Them

```bash
# Create package for orphans
python3 scripts/pkgutil.py init PKG-ORPHAN-RESCUE-001 \
  --spec SPEC-CORE-001 \
  --output _staging/PKG-ORPHAN-RESCUE-001

# Move orphans into staging
mv lib/orphan_file.py _staging/PKG-ORPHAN-RESCUE-001/lib/

# Preflight, stage, install
```

### Option 2: Quarantine Them

```bash
# Move to quarantine for later processing
python3 scripts/quarantine_orphans.py --dry-run
python3 scripts/quarantine_orphans.py --execute
```

### Option 3: Add to Baseline (if core file)

If the file should be part of baseline:

```bash
# Regenerate baseline manifest
python3 scripts/generate_baseline_manifest.py --plane ho3 \
  --output packages_store/PKG-BASELINE-HO3-000/

# Reinstall baseline (requires work order post-seal)
```

---

## Quick Reference: Pipe Commands for Agents

```bash
# Get packaging workflow
echo '{"operation": "packaging_workflow"}' | python3 -m modules.shell | jq

# Get manifest requirements
echo '{"operation": "manifest_requirements"}' | python3 -m modules.shell | jq

# List frameworks
echo '{"operation": "list_frameworks"}' | python3 -m modules.shell | jq

# List specs
echo '{"operation": "list_specs"}' | python3 -m modules.shell | jq

# Explain if path is writable
echo '{"operation": "explain_path", "path": "lib/foo.py"}' | python3 -m modules.shell | jq

# Troubleshoot errors
echo '{"operation": "troubleshoot", "error_type": "G1"}' | python3 -m modules.shell | jq

# Get example manifest
echo '{"operation": "example_manifest", "package_type": "library"}' | python3 -m modules.shell | jq
```

---

## Environment Setup

```bash
# For unsigned development packages
export CONTROL_PLANE_ALLOW_UNSIGNED=1

# Working directory
cd Control_Plane_v2/
```

---

## Summary: The Golden Rule

**If you're about to write to a governed path, STOP.**

1. Create a package in `_staging/`
2. Run `preflight`
3. Fix any errors
4. Run `stage` then `package_install.py`
5. Verify with `gate_check.py --all`

This ensures every file has an owner, every change is tracked, and the governance chain remains intact.
