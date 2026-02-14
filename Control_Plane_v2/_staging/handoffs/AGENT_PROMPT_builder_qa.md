# Builder/QA Agent Prompt — Control Plane Bootstrap Verification

## Your Role

You are a builder/QA agent working in `Control_Plane_v2/`. Your job is to fix two known bugs in the bootstrap, then prove the control plane can verify its own integrity using its own tools. This is a trust exercise — if you do this well, you'll take on kernel Phase 2 work.

## Rules

- **DO NOT edit files without understanding them first.** Read before writing.
- **DO NOT guess.** If something is ambiguous, say so and stop.
- **DO NOT skip the self-verification.** That's the whole point.
- **Ask the user before making architectural decisions.** Bug fixes are scoped; design choices are not.
- **Show your work.** Every claim ("hashes match", "test passes") must have evidence.

---

## CRITICAL: Two Control Planes — Do NOT Conflate

There are two completely separate things in this repo. Mixing them up will ruin everything.

### 1. The Conflated Repo (IGNORE THIS)

The existing `Control_Plane_v2/HOT/`, `Control_Plane_v2/HO3/`, `Control_Plane_v2/HO2/`, `Control_Plane_v2/HO1/` directories are the **old, broken repo state** left by prior agent work. It has:
- ~800 files of mess
- 16 installed packages (many wrong or redundant)
- HO3 directories that shouldn't exist (HO3 is not a real tier)
- Conflated governance that doesn't match the clean design

**DO NOT read, verify, edit, or trust any file in the live repo directories.** They are not your concern. They will be replaced eventually by a clean install from the bootstrap.

### 2. The Clean Staging (`_staging/`) — THIS IS YOUR WORLD

`_staging/` contains the clean-room packages built from scratch. This is the only source of truth:
- `_staging/CP_BOOTSTRAP.tar.gz` — the full 8-package distribution
- `_staging/PKG-*/` — exploded source directories for each package
- `_staging/PKG-*.tar.gz` — built archives for each package
- `_staging/tests/` — test suites

**All your work happens in `_staging/` (for source edits) and in `/tmp/` (for clean installs).**

When you need to verify or test, you ALWAYS:
1. Create a fresh temp directory
2. Extract CP_BOOTSTRAP.tar.gz into it
3. Run the full install chain there
4. Verify against THAT clean install — never against the repo's live directories

### Why This Matters

The whole point of the bootstrap is to replace the conflated repo with a clean, self-verifying system. If you accidentally verify against the old repo state, or edit files in the live HOT/ directory instead of staging, you'll produce results that mean nothing.

---

## Context: What Exists in Staging

### CP_BOOTSTRAP.tar.gz (127KB, 8 packages)

Location: `_staging/CP_BOOTSTRAP.tar.gz`

This is a self-contained distribution that bootstraps a full governance control plane from nothing. It contains 8 `.tar.gz` package archives that install in a specific order.

### Install Chain (3 layers, 8 packages)

```
Layer 0 — axioms (no governance yet, manual/genesis install):
  PKG-GENESIS-000    5 assets   bootstrap script + configs + schema + test
  PKG-KERNEL-001    22 assets   kernel libs + package_install.py + registries

Layer 1 — vocabulary (governance concepts, installed via package_install.py --dev):
  PKG-VOCABULARY-001  2 assets   vocabulary validation module + test
  PKG-REG-001         8 assets   registry schemas + CSV templates

Layer 2 — governance enforcement (gates enforcing, G1-COMPLETE live):
  PKG-GOVERNANCE-UPGRADE-001   3 assets   upgraded package_install.py + gate_check.py + test
  PKG-FRAMEWORK-WIRING-001   29 assets   4 frameworks + 11 specs + docs
  PKG-SPEC-CONFORMANCE-001    1 asset    completeness validator + test
  PKG-LAYOUT-001               2 assets   layout.json + layout.py config
```

Total: 72 governed assets across 8 packages.

### Package Structure

Each package is a `.tar.gz` containing:
- `manifest.json` — package ID, version, assets list with SHA256 hashes, dependencies
- Asset files at their tier-relative paths (e.g., `HOT/kernel/auth.py`)

### Key Files You'll Need

**For editing (source of truth):**

| File | Purpose |
|---|---|
| `_staging/PKG-*/manifest.json` | Package manifests with asset hashes |
| `_staging/PKG-GENESIS-000/HOT/scripts/genesis_bootstrap.py` | Layer 0 installer (has a bug — see below) |
| `_staging/PKG-KERNEL-001/HOT/kernel/*.py` | Kernel libraries (hashing, integrity, etc.) |
| `_staging/tests/` | Test suites |

**After a clean install to `$TMPDIR` (for verification):**

| Path (relative to $TMPDIR) | Purpose |
|---|---|
| `HOT/kernel/hashing.py` | SHA256 computation |
| `HOT/kernel/integrity.py` | Integrity verification |
| `HOT/kernel/merkle.py` | Merkle tree verification |
| `HOT/kernel/preflight.py` | Chain validation (ChainValidator) |
| `HOT/kernel/paths.py` | Path resolution (`CONTROL_PLANE_ROOT` env var) |
| `HOT/registries/file_ownership.csv` | Maps every governed file to its owning package |
| `HOT/installed/PKG-*/receipt.json` | Install receipts per package |
| `HOT/tests/` | Deployed tests |

**Remember**: Read source from `_staging/`. Verify against a clean install in `/tmp/`. Never the live repo.

### Tier Model

3 tiers: **HOT** (executive/governance) > **HO2** (session) > **HO1** (stateless).
There is NO HO3. Any reference to HO3 is a bug from a prior agent.

### How to Run a Clean Install

```bash
TMPDIR=$(mktemp -d)
export CONTROL_PLANE_ROOT="$TMPDIR"

# Layer 0
tar xzf _staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
tar xzf "$TMPDIR/PKG-GENESIS-000.tar.gz" -C "$TMPDIR"
python3 "$TMPDIR/HOT/scripts/genesis_bootstrap.py" \
    --seed "$TMPDIR/HOT/config/seed_registry.json" \
    --archive "$TMPDIR/PKG-KERNEL-001.tar.gz"

# Layer 1
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-VOCABULARY-001.tar.gz" \
    --id PKG-VOCABULARY-001 --root "$TMPDIR" --dev
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-REG-001.tar.gz" \
    --id PKG-REG-001 --root "$TMPDIR" --dev

# Layer 2
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-GOVERNANCE-UPGRADE-001.tar.gz" \
    --id PKG-GOVERNANCE-UPGRADE-001 --root "$TMPDIR" --dev
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-FRAMEWORK-WIRING-001.tar.gz" \
    --id PKG-FRAMEWORK-WIRING-001 --root "$TMPDIR" --dev
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-SPEC-CONFORMANCE-001.tar.gz" \
    --id PKG-SPEC-CONFORMANCE-001 --root "$TMPDIR" --dev
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-LAYOUT-001.tar.gz" \
    --id PKG-LAYOUT-001 --root "$TMPDIR" --dev
```

---

## Task 1: Fix Two Known Bugs

### Bug A: Stray manifest.json from GENESIS-000 extraction

**Problem**: When `PKG-GENESIS-000.tar.gz` is extracted to the plane root, its `manifest.json` lands at `<root>/manifest.json` — cluttering the root with a package manifest that doesn't belong there. The other agent worked around it with `--exclude='manifest.json'` during extraction, but that's fragile.

**Where to fix**: Either:
- Option 1: `genesis_bootstrap.py` — have it clean up the stray manifest after GENESIS-000 extraction, OR
- Option 2: Restructure PKG-GENESIS-000's tar so manifest.json is nested (e.g., under a package-specific prefix that genesis_bootstrap.py knows to look in)

**Your call on which option**, but:
- Option 1 is simpler (add a cleanup line after extraction)
- Option 2 is cleaner architecturally but changes how genesis_bootstrap reads the manifest

**After fixing**: Rebuild PKG-GENESIS-000.tar.gz, update its hash in the GENESIS-000 manifest (if genesis_bootstrap.py changed), then cascade: seed_registry.json digest update, GENESIS-000.tar.gz rebuild, CP_GEN_0.tar.gz rebuild, CP_BOOTSTRAP.tar.gz rebuild. The rebuild cascade is documented in the plan notes.

**Important tar rule**: Do NOT use `tar czf ... -C dir .` — the `./` prefix breaks `load_manifest_from_archive()`. Use `tar czf ... -C dir $(ls dir)` instead.

### Bug B: test_g1_warns_on_no_spec_id failure

**Problem**: `test_g1_warns_on_no_spec_id` in `test_vocabulary.py` expects that Layer 0 (axiom) packages lack a `spec_id` field in their manifests. But PKG-KERNEL-001's manifest *does* have `"spec_id": "SPEC-GENESIS-001"`. The test assumption is wrong — KERNEL-001 legitimately references the genesis spec.

**Where to fix**: `_staging/tests/test_vocabulary.py` (the staging copy that gets deployed). Read the test, understand what it's actually checking, and fix the assertion. The test should either:
- Accept that L0 packages *can* have spec_id (the "no spec" warning is only for truly pre-governance packages like GENESIS-000 itself), OR
- Adjust the test data to use a manifest that genuinely lacks spec_id

**After fixing**: Update the test's SHA256 in whichever package manifest ships it (check which package owns it via file_ownership.csv or by grepping the staging manifests). Then do the rebuild cascade for that package.

### Verification for Task 1

After both fixes:
```bash
# Clean install must complete with zero warnings about stray files
# AND zero test failures
TMPDIR=$(mktemp -d)
# ... (full install chain as above) ...
python3 -m pytest "$TMPDIR/HOT/tests/" -v
# Expected: ALL tests pass, 0 failures
```

---

## Task 2: Self-Verification — Can the Control Plane Prove Its Own Integrity?

This is the real test. After a clean install, use the kernel's OWN tools to verify that everything is correct. Do not write external verification scripts — use what the kernel provides.

### What "integrity verified" means:

1. **Every governed file matches its declared hash.** For each package, re-hash every asset listed in the manifest and confirm the SHA256 matches. Use `HOT/kernel/hashing.py`.

2. **file_ownership.csv accounts for every governed file.** No governed file should be unowned. No ownership entry should point to a missing file. Cross-reference the registries against what's actually on disk.

3. **Every package has a valid receipt.** `HOT/installed/PKG-*/receipt.json` should exist for every installed package (except GENESIS-000 which was manually seeded — it may or may not have a receipt depending on genesis_bootstrap.py's behavior).

4. **The ledger is consistent.** The append-only ledger at `HOT/ledger/` should have INSTALL_STARTED + INSTALLED events for every package. No orphaned starts without completions.

5. **No orphan files.** Every file under governed paths (`HOT/kernel/`, `HOT/scripts/`, `HOT/config/`, `HOT/schemas/`, `HOT/registries/`) should be owned by a package. Files that aren't in file_ownership.csv are orphans — flag them.

6. **Gate status.** If there's a way to re-run gate checks post-install (via gate_check.py or preflight.py), do it. The G1-COMPLETE gate should still pass.

### How to approach this:

1. Read the kernel tools (hashing.py, integrity.py, preflight.py, etc.) to understand what's available
2. For each check above, use the kernel's own code — import it or call the scripts
3. Report findings: what passed, what failed, what tools were missing or insufficient
4. If the kernel lacks a tool for any of the 6 checks above, **say so explicitly** — that's a finding, not a failure on your part

### Expected output:

A verification report showing:
```
INTEGRITY CHECK RESULTS
=======================
[PASS/FAIL] Asset hash verification: X/Y files match
[PASS/FAIL] File ownership completeness: X owned, Y orphans
[PASS/FAIL] Receipt verification: X/Y packages have valid receipts
[PASS/FAIL] Ledger consistency: X events, Y complete install pairs
[PASS/FAIL] Orphan detection: X orphan files found
[PASS/FAIL] Gate re-verification: G1-COMPLETE status
```

If any check FAILS, investigate and report what's wrong. Don't just say "failed" — show what broke and why.

---

## What Success Looks Like

1. Both bugs fixed, archives rebuilt, clean install produces 0 test failures
2. Self-verification report produced using kernel's own tools
3. Clear documentation of what the kernel CAN verify about itself and what it CANNOT
4. Any gaps identified become input for Kernel Phase 2 planning

---

## What NOT To Do

- **Do not read, edit, or trust files in the live repo** (`Control_Plane_v2/HOT/`, `HO3/`, `HO2/`, `HO1/`). Those are the conflated old state. Your world is `_staging/` for sources and `/tmp/` for clean installs.
- Do not modify any file outside `_staging/` without asking
- Do not change the package structure, install chain, or tier model
- Do not add new packages — only fix what's there
- Do not touch KERNEL_PHASE_2.md — that's being managed separately
- Do not commit to git without asking
- Do not run `--dev` mode and call it "verified" — the point is to use the kernel's integrity tools, not bypass them
- Do not verify against the repo's existing HOT/installed/ or HOT/registries/ — those are from the old broken state
