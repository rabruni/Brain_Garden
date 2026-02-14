Read the file `Control_Plane_v2/_staging/AGENT_PROMPT_builder_qa.md` — it is your complete briefing. Every rule, every file path, every constraint is in that document. Read it fully before doing anything.

But FIRST — before you touch any code — you must complete the trust test below. This is mandatory. If you skip it or get it wrong, you will not proceed to the real work.

---

## TRUST TEST (Do This First, Report Results)

Complete all 4 steps. Show your work for each one. Do not summarize — show the actual commands and output.

### Step 1: Clean Install

Create a fresh temp directory. Extract `_staging/CP_BOOTSTRAP.tar.gz` into it. Run the full 8-package install chain (Layer 0 via genesis_bootstrap.py, Layers 1-2 via package_install.py --dev). Set `CONTROL_PLANE_ROOT` to the temp directory.

**Show**: The install output for all 8 packages. Every package must succeed.

### Step 2: Single File Hash Verification

Pick `HOT/kernel/install_auth.py` from the clean install. Using the kernel's own `hashing.py` (from the same clean install, NOT from the repo), compute its SHA256. Then read `PKG-KERNEL-001`'s manifest.json (from `_staging/`) and find the declared hash for that file.

**Show**: The computed hash, the manifest hash, and whether they match.

**Why this file**: It was modified today. If the hashes match, the rebuild cascade worked. If they don't, something is broken.

### Step 3: Boundary Check

Answer these two questions (no tools needed, just demonstrate understanding from the briefing):

1. You need to fix a bug in `genesis_bootstrap.py`. Which file do you edit — the one at `Control_Plane_v2/HOT/scripts/genesis_bootstrap.py` or the one at `Control_Plane_v2/_staging/PKG-GENESIS-000/HOT/scripts/genesis_bootstrap.py`? Why?

2. You need to verify that `file_ownership.csv` accounts for all governed files. Where do you look — `Control_Plane_v2/HOT/registries/file_ownership.csv` or `$TMPDIR/HOT/registries/file_ownership.csv` from your clean install? Why?

### Step 4: Cascade Understanding

You're about to fix genesis_bootstrap.py (Bug A from the briefing). After editing the source file, list every step in the rebuild cascade — every hash recomputation, every manifest update, every archive rebuild — in order. Don't do it yet, just list the steps.

**Why**: If you miss a step, the archives will have stale hashes and the next clean install will fail. This is the most common mistake.

---

## After the Trust Test

Once you've reported your trust test results, pause and wait for my review. If everything checks out, proceed to the real work:

1. **Bug A**: Fix the stray manifest.json leak from GENESIS-000 extraction
2. **Bug B**: Fix the test_g1_warns_on_no_spec_id test failure
3. **Self-Verification**: Prove the control plane can verify its own integrity using its own tools

All details are in `_staging/AGENT_PROMPT_builder_qa.md`.
