# Control Plane v2 — Bootstrap Install Guide

## What This Is

This archive contains 13 packages that install the Control Plane v2 governance foundation across 4 layers:

| Layer | Purpose | Packages |
|-------|---------|----------|
| 0 (axioms) | Core kernel + genesis bootstrap | PKG-GENESIS-000, PKG-KERNEL-001 |
| 1 (vocabulary) | Vocabulary definitions + registries | PKG-VOCABULARY-001, PKG-REG-001 |
| 2 (governance) | Governance enforcement, framework wiring, spec conformance, layout | PKG-GOVERNANCE-UPGRADE-001, PKG-FRAMEWORK-WIRING-001, PKG-SPEC-CONFORMANCE-001, PKG-LAYOUT-001 |
| 3 (application) | Phase 2 schemas, token budgeting, prompt routing, LLM provider, layout upgrade | PKG-PHASE2-SCHEMAS-001, PKG-TOKEN-BUDGETER-001, PKG-PROMPT-ROUTER-001, PKG-ANTHROPIC-PROVIDER-001, PKG-LAYOUT-002 |

All 13 packages are installed automatically by `install.sh`. No separate Layer 3 step needed.

## Prerequisites

- **Python 3.10+** (stdlib only — no pip packages required)
- **bash** (for install.sh)
- **tar** (GNU or BSD)

## Quick Start

```bash
# Extract the bootstrap archive
tar xzf CP_BOOTSTRAP.tar.gz -C /tmp/bootstrap
cd /tmp/bootstrap

# Run the installer (--dev bypasses auth for testing)
./install.sh --root /path/to/control_plane --dev
```

Expected: 13 packages installed, 8/8 gates PASS. Takes ~10 seconds.

### install.sh Options

| Flag | Required | Description |
|------|----------|-------------|
| `--root <dir>` | Yes | Target install directory (created if absent) |
| `--dev` | No | Bypass auth/signature checks (for testing) |
| `--force` | No | Overwrite existing files (for re-install/recovery) |

## Manual Install (Step-by-Step)

If you cannot run bash scripts, follow these steps exactly. All commands use absolute paths — replace `$ROOT` with your chosen install directory and `$BOOTSTRAP` with the directory where you extracted the bootstrap archive.

### Set environment

```bash
export ROOT="/path/to/control_plane"
export BOOTSTRAP="/path/to/extracted/bootstrap"
export CONTROL_PLANE_ROOT="$ROOT"
mkdir -p "$ROOT"
```

### Layer 0: Genesis + Kernel

```bash
# Step 1: Extract the genesis seed (puts genesis_bootstrap.py + configs on disk)
tar xzf "$BOOTSTRAP/packages/PKG-GENESIS-000.tar.gz" -C "$ROOT"

# Step 2: Install PKG-KERNEL-001 via genesis bootstrapper
python3 "$ROOT/HOT/scripts/genesis_bootstrap.py" \
    --seed "$ROOT/HOT/config/seed_registry.json" \
    --archive "$BOOTSTRAP/packages/PKG-KERNEL-001.tar.gz" \
    --id PKG-KERNEL-001 \
    --force
```

After this step, `$ROOT/HOT/scripts/package_install.py` exists and is used for all remaining packages.

### Layer 1: Vocabulary + Registries

```bash
# Step 3: PKG-VOCABULARY-001
python3 "$ROOT/HOT/scripts/package_install.py" \
    --archive "$BOOTSTRAP/packages/PKG-VOCABULARY-001.tar.gz" \
    --id PKG-VOCABULARY-001 --root "$ROOT" --dev

# Step 4: PKG-REG-001
python3 "$ROOT/HOT/scripts/package_install.py" \
    --archive "$BOOTSTRAP/packages/PKG-REG-001.tar.gz" \
    --id PKG-REG-001 --root "$ROOT" --dev
```

### Layer 2: Governance Enforcement

```bash
# Step 5: PKG-GOVERNANCE-UPGRADE-001
python3 "$ROOT/HOT/scripts/package_install.py" \
    --archive "$BOOTSTRAP/packages/PKG-GOVERNANCE-UPGRADE-001.tar.gz" \
    --id PKG-GOVERNANCE-UPGRADE-001 --root "$ROOT" --dev

# Step 6: PKG-FRAMEWORK-WIRING-001
python3 "$ROOT/HOT/scripts/package_install.py" \
    --archive "$BOOTSTRAP/packages/PKG-FRAMEWORK-WIRING-001.tar.gz" \
    --id PKG-FRAMEWORK-WIRING-001 --root "$ROOT" --dev

# Step 7: PKG-SPEC-CONFORMANCE-001
python3 "$ROOT/HOT/scripts/package_install.py" \
    --archive "$BOOTSTRAP/packages/PKG-SPEC-CONFORMANCE-001.tar.gz" \
    --id PKG-SPEC-CONFORMANCE-001 --root "$ROOT" --dev

# Step 8: PKG-LAYOUT-001
python3 "$ROOT/HOT/scripts/package_install.py" \
    --archive "$BOOTSTRAP/packages/PKG-LAYOUT-001.tar.gz" \
    --id PKG-LAYOUT-001 --root "$ROOT" --dev
```

### Layer 3: Application Packages

```bash
# Step 9: PKG-PHASE2-SCHEMAS-001
python3 "$ROOT/HOT/scripts/package_install.py" \
    --archive "$BOOTSTRAP/packages/PKG-PHASE2-SCHEMAS-001.tar.gz" \
    --id PKG-PHASE2-SCHEMAS-001 --root "$ROOT" --dev

# Step 10: PKG-TOKEN-BUDGETER-001
python3 "$ROOT/HOT/scripts/package_install.py" \
    --archive "$BOOTSTRAP/packages/PKG-TOKEN-BUDGETER-001.tar.gz" \
    --id PKG-TOKEN-BUDGETER-001 --root "$ROOT" --dev

# Step 11: PKG-PROMPT-ROUTER-001
python3 "$ROOT/HOT/scripts/package_install.py" \
    --archive "$BOOTSTRAP/packages/PKG-PROMPT-ROUTER-001.tar.gz" \
    --id PKG-PROMPT-ROUTER-001 --root "$ROOT" --dev

# Step 12: PKG-ANTHROPIC-PROVIDER-001
python3 "$ROOT/HOT/scripts/package_install.py" \
    --archive "$BOOTSTRAP/packages/PKG-ANTHROPIC-PROVIDER-001.tar.gz" \
    --id PKG-ANTHROPIC-PROVIDER-001 --root "$ROOT" --dev

# Step 13: PKG-LAYOUT-002
python3 "$ROOT/HOT/scripts/package_install.py" \
    --archive "$BOOTSTRAP/packages/PKG-LAYOUT-002.tar.gz" \
    --id PKG-LAYOUT-002 --root "$ROOT" --dev
```

All 13 packages installed. Bootstrap complete.

## Verification

### Gate Checks

```bash
CONTROL_PLANE_ROOT="$ROOT" python3 "$ROOT/HOT/scripts/gate_check.py" --root "$ROOT" --all
```

Expected results after full install:

| Gate | Expected | What it checks |
|------|----------|----------------|
| G0B | PASS | File ownership — all files owned, 0 orphans |
| G1 | PASS | Dependency chains validated |
| G1-COMPLETE | PASS | Framework completeness |
| G2 | PASS | Work order system |
| G3 | PASS | Constraints |
| G4 | PASS | Acceptance infrastructure |
| G5 | PASS | Signatures |
| G6 | PASS | Ledger entries present |

Overall: 8/8 gates PASS.

### Receipts

Every installed package writes a receipt:

```bash
ls "$ROOT/HOT/installed"/PKG-*/receipt.json
```

After full install, you should see 13 receipts:

```
PKG-GENESIS-000
PKG-KERNEL-001
PKG-VOCABULARY-001
PKG-REG-001
PKG-GOVERNANCE-UPGRADE-001
PKG-FRAMEWORK-WIRING-001
PKG-SPEC-CONFORMANCE-001
PKG-LAYOUT-001
PKG-PHASE2-SCHEMAS-001
PKG-TOKEN-BUDGETER-001
PKG-PROMPT-ROUTER-001
PKG-ANTHROPIC-PROVIDER-001
PKG-LAYOUT-002
```

### Tests

```bash
CONTROL_PLANE_ROOT="$ROOT" \
PYTHONPATH="$ROOT/HOT/kernel:$ROOT/HOT" \
python3 -m pytest "$ROOT/HOT/tests/" -v
```

## Troubleshooting

### "Target exists" error from genesis_bootstrap.py

The genesis bootstrapper won't overwrite files unless `--force` is passed. If re-installing:

```bash
./install.sh --root /path/to/control_plane --dev --force
```

Or manually: add `--force` to the genesis_bootstrap.py command.

### "Package not in seed registry" from genesis_bootstrap.py

You passed the wrong file to `--seed`. It must be `seed_registry.json`, NOT a `.tar.gz` archive:

```bash
# Wrong:
python3 genesis_bootstrap.py --seed PKG-GENESIS-000.tar.gz ...

# Correct:
python3 genesis_bootstrap.py --seed "$ROOT/HOT/config/seed_registry.json" ...
```

### CONTROL_PLANE_ROOT not set

Both genesis_bootstrap.py and package_install.py use this env var. Always set it:

```bash
export CONTROL_PLANE_ROOT="/path/to/control_plane"
```

Or pass `--root` to package_install.py.

### Auth errors from package_install.py

If you see auth/signature errors, add `--dev` to bypass (for testing only):

```bash
python3 package_install.py --archive ... --id ... --root "$ROOT" --dev
```

### Tar archive has ./ prefix (load_manifest_from_archive fails)

If you rebuild any package archive, NEVER use `tar czf ... -C dir .` — the `./` prefix breaks manifest loading. Use Python's `tarfile` module with explicit `arcname`, or:

```bash
tar czf ARCHIVE.tar.gz -C dir $(ls dir)
```

## Architecture

The 4-layer bootstrap follows a strict dependency chain:

```
Layer 0 (axioms)      → Kernel primitives: paths, hashing, pristine boundaries,
                         ledger client, auth, schema validation, package installer
Layer 1 (vocabulary)  → Governance vocabulary: spec/framework registry validation,
                         chain integrity checks
Layer 2 (governance)  → Governance enforcement: framework wiring, spec conformance
                         tests, file ownership validation, layout definition
Layer 3 (application) → Phase 2 schemas, token budget management, prompt routing,
                         Anthropic LLM provider, layout upgrade (HO2/HO1 dirs)
```

Each layer can only reference concepts from layers below it. Layer 0 can't reference frameworks or specs (those come in Layer 1). Layer 1 can't reference governance enforcement (that comes in Layer 2). Layer 3 builds on all lower layers.

PKG-GENESIS-000 is special: it contains the bootstrapper itself (`genesis_bootstrap.py`) and must be extracted raw before any package install can happen. This resolves the chicken-and-egg problem — the first package that installs the package system can't be installed by the package system.
