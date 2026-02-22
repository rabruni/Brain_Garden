# Builder Follow-Up #3B: Bootstrap Install Script + Guide

## Mission

Add `install.sh` and `INSTALL.md` to `CP_BOOTSTRAP.tar.gz` so that an external agent (Codex, Gemini, or any LLM) receiving ONLY the bootstrap archive can install the full control plane from scratch — zero context required.

**CRITICAL CONSTRAINTS — read before doing anything:**

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree.
2. **DTT: Design → Test → Then implement.** Write the script, then verify it works in a clean-room install.
3. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`).
4. **End-to-end verification.** After rebuilding CP_BOOTSTRAP.tar.gz, extract it to a clean temp dir and run install.sh. All 8 packages must install. All gates must pass.
5. **Do NOT modify any package archives or manifests.** You are only adding two new files (`install.sh`, `INSTALL.md`) to the top level of `CP_BOOTSTRAP.tar.gz` alongside the existing 8 `.tar.gz` archives.

---

## The Problem

CP_BOOTSTRAP.tar.gz currently contains 8 raw `.tar.gz` package archives — nothing else:

```
PKG-GENESIS-000.tar.gz
PKG-KERNEL-001.tar.gz
PKG-VOCABULARY-001.tar.gz
PKG-REG-001.tar.gz
PKG-GOVERNANCE-UPGRADE-001.tar.gz
PKG-FRAMEWORK-WIRING-001.tar.gz
PKG-SPEC-CONFORMANCE-001.tar.gz
PKG-LAYOUT-001.tar.gz
```

An external agent receiving this has no way to know:
- The install order (Layer 0 → 1 → 2)
- That PKG-GENESIS-000 must be extracted manually first (chicken-and-egg: genesis_bootstrap.py is inside it)
- That genesis_bootstrap.py takes `--seed` (seed_registry.json, NOT the genesis archive) and `--archive` (for PKG-KERNEL-001.tar.gz)
- That `CONTROL_PLANE_ROOT` env var controls the root directory
- That `package_install.py` (from PKG-KERNEL-001) handles Layers 1-2
- That `--dev` bypasses auth for testing
- That Layer 3 packages are separate archives installed after bootstrap

---

## What to Build

### File 1: `install.sh`

A self-contained bash script that runs the full Layer 0-2 install chain. Place at the top level of CP_BOOTSTRAP.tar.gz.

**Requirements:**

1. Accept `--root <dir>` argument (required — where to install)
2. Accept `--dev` flag (optional — bypasses auth, default: off)
3. Accept `--layer3 <pkg1.tar.gz> [pkg2.tar.gz ...]` (optional — additional packages to install after bootstrap)
4. Work on macOS and Linux (bash, no bashisms that break on dash/sh)
5. Use `set -euo pipefail` — fail on any error
6. Print clear progress messages at each step
7. Verify prerequisites: `python3` must be available
8. Exit with 0 on success, non-zero on failure with clear error message
9. Run gate checks at the end and report results

**Flow:**

```
Step 1: Create root directory if it doesn't exist
Step 2: Set CONTROL_PLANE_ROOT=$ROOT
Step 3: Determine where the package archives are
        (same directory as install.sh — the extracted bootstrap)
Step 4: Extract PKG-GENESIS-000.tar.gz into $ROOT
        (this puts genesis_bootstrap.py, seed_registry.json, bootstrap_sequence.json
         into $ROOT/HOT/scripts/, $ROOT/HOT/config/)
Step 5: Run genesis_bootstrap.py to install PKG-KERNEL-001
        python3 "$ROOT/HOT/scripts/genesis_bootstrap.py" \
            --seed "$ROOT/HOT/config/seed_registry.json" \
            --archive "$BOOTSTRAP_DIR/PKG-KERNEL-001.tar.gz"
        (now package_install.py exists at $ROOT/HOT/scripts/package_install.py)
Step 6: Install Layer 1 packages (order matters)
        python3 "$ROOT/HOT/scripts/package_install.py" \
            --archive "$BOOTSTRAP_DIR/PKG-VOCABULARY-001.tar.gz" \
            --id PKG-VOCABULARY-001 --root "$ROOT" [--dev]
        python3 "$ROOT/HOT/scripts/package_install.py" \
            --archive "$BOOTSTRAP_DIR/PKG-REG-001.tar.gz" \
            --id PKG-REG-001 --root "$ROOT" [--dev]
Step 7: Install Layer 2 packages (order matters)
        PKG-GOVERNANCE-UPGRADE-001
        PKG-FRAMEWORK-WIRING-001
        PKG-SPEC-CONFORMANCE-001
        PKG-LAYOUT-001
Step 8: Install Layer 3 packages if --layer3 was provided
        For each archive in order provided
Step 9: Run gate checks
        python3 "$ROOT/HOT/scripts/gate_check.py" --root "$ROOT" --all
Step 10: Print summary
```

**Package install order** (from bootstrap_sequence.json):
```
Layer 0 (genesis):     PKG-KERNEL-001        (via genesis_bootstrap.py)
Layer 1 (vocabulary):  PKG-VOCABULARY-001     (via package_install.py)
Layer 1 (registries):  PKG-REG-001
Layer 2 (governance):  PKG-GOVERNANCE-UPGRADE-001
Layer 2 (wiring):      PKG-FRAMEWORK-WIRING-001
Layer 2 (conformance): PKG-SPEC-CONFORMANCE-001
Layer 2 (layout):      PKG-LAYOUT-001
```

**CLI args for the two installers:**

genesis_bootstrap.py:
```
--seed <path>       Path to seed_registry.json (required)
--archive <path>    Path to PKG-KERNEL-001.tar.gz (required)
--force             Overwrite existing files
--verify-only       Validate without installing
```
Uses `CONTROL_PLANE_ROOT` env var for root directory.

package_install.py:
```
--archive <path>    Package archive path (required)
--id <pkg_id>       Package ID (required)
--root <path>       Plane root path
--dev               Bypass auth/signatures
--force             Overwrite existing files
--dry-run           Validate only
```

### File 2: `INSTALL.md`

Human-readable install guide. Place at the top level of CP_BOOTSTRAP.tar.gz alongside install.sh.

**Content should cover:**

1. **What this is** — Control Plane v2 bootstrap: 8 packages across 3 layers
2. **Prerequisites** — Python 3.10+, no pip packages required (stdlib only)
3. **Quick start** — the one-liner using install.sh
4. **Manual install** — step-by-step commands for each layer (for agents that can't run bash)
5. **Layer 3 packages** — how to install additional packages on top of bootstrap
6. **Verification** — how to run gate checks and what passes look like
7. **Troubleshooting** — common errors (wrong CONTROL_PLANE_ROOT, missing --dev, tar prefix issue)
8. **Architecture note** — brief explanation of the 3-layer bootstrap (axioms → vocabulary → governance)

**Tone:** Written for an LLM agent with no prior context. Every command must be copy-pasteable. No assumed knowledge.

---

## Implementation Steps

### Step 1: Create install.sh

Write the script at `Control_Plane_v2/_staging/install.sh`.

### Step 2: Create INSTALL.md

Write the guide at `Control_Plane_v2/_staging/INSTALL.md`.

### Step 3: Rebuild CP_BOOTSTRAP.tar.gz

The bootstrap archive currently contains 8 `.tar.gz` files. Add `install.sh` and `INSTALL.md` to the same level.

**How CP_BOOTSTRAP.tar.gz is built:**

The archive is created from the individual package archives. The new build process:

1. Create a temporary staging directory
2. Copy all 8 `.tar.gz` package archives into it
3. Copy `install.sh` and `INSTALL.md` into it
4. Make install.sh executable (`chmod +x`)
5. Build: `tar czf CP_BOOTSTRAP.tar.gz -C <staging_dir> $(ls <staging_dir>)`

Expected contents after rebuild:
```
INSTALL.md
install.sh
PKG-FRAMEWORK-WIRING-001.tar.gz
PKG-GENESIS-000.tar.gz
PKG-GOVERNANCE-UPGRADE-001.tar.gz
PKG-KERNEL-001.tar.gz
PKG-LAYOUT-001.tar.gz
PKG-REG-001.tar.gz
PKG-SPEC-CONFORMANCE-001.tar.gz
PKG-VOCABULARY-001.tar.gz
```

### Step 4: Clean-room verification

```bash
# Fresh temp dir — simulates an external agent
TESTDIR=$(mktemp -d)
cd "$TESTDIR"

# Extract bootstrap (this is what the external agent gets)
tar xzf /path/to/_staging/CP_BOOTSTRAP.tar.gz

# Run the installer
chmod +x install.sh
./install.sh --root "$TESTDIR/control_plane" --dev

# Verify
# - All 8 packages installed
# - Gate checks pass (G0B, G1, G1-COMPLETE)
# - file_ownership.csv has expected rows
# - All receipts in HOT/installed/

# Also test Layer 3:
./install.sh --root "$TESTDIR/cp_with_layer3" --dev \
    --layer3 /path/to/_staging/PKG-PHASE2-SCHEMAS-001.tar.gz \
             /path/to/_staging/PKG-TOKEN-BUDGETER-001.tar.gz \
             /path/to/_staging/PKG-PROMPT-ROUTER-001.tar.gz

# Verify Layer 3 installed on top of bootstrap
ls "$TESTDIR/cp_with_layer3/HOT/schemas/"
# Should include prompt_contract.schema.json, budget_config.schema.json, router_config.schema.json
```

### Step 5: Test the INSTALL.md commands manually

Extract the bootstrap, follow the manual install steps in INSTALL.md exactly as written, confirm they work.

---

## Design Principles

1. **Self-contained.** The bootstrap archive + install.sh is everything needed. No external dependencies, no network access, no pip install.
2. **Idempotent.** Running install.sh twice with `--force` should work (useful for recovery).
3. **Fail-fast with clear errors.** If python3 isn't found, say so. If an archive is missing, say which one. If a gate fails, show the output.
4. **LLM-friendly.** INSTALL.md commands are copy-pasteable. No ambiguity. An agent reading it should be able to install without interpretation.
5. **Layer 3 is optional.** The bootstrap installs Layers 0-2. Layer 3 packages are explicitly passed via `--layer3`. This keeps the bootstrap stable — new Layer 3 packages don't require rebuilding CP_BOOTSTRAP.tar.gz.

---

## Files Created / Modified

| File | Location | Action |
|------|----------|--------|
| `install.sh` | `_staging/` (then into CP_BOOTSTRAP.tar.gz) | CREATE |
| `INSTALL.md` | `_staging/` (then into CP_BOOTSTRAP.tar.gz) | CREATE |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD (add 2 files, keep all 8 archives) |

**Not modified:** Any package archive, any manifest, any Python code.
