# Agent Prompt: HANDOFF-12A

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-12A** — Fix pristine bypass ordering so boot_materialize runs under dev-mode bypass

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/BUILDER_HANDOFF_12A_pristine_fix.md`

**Also read the builder standard for results file format:**
`Control_Plane_v2/_staging/BUILDER_HANDOFF_STANDARD.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: use Python tarfile module with explicit arcname (NEVER shell tar with `./` prefix).
4. End-to-end verification: clean-room install with 17 packages, 8/8 gates PASS.
5. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_HANDOFF_12A.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What is the exact bug? Which line runs too early, and which line runs too late? What error does the user see?

2. What is the fix? Describe the new ordering of the three operations (pristine_patch, boot_materialize, build_session_host) in run_cli().

3. Where does pristine_patch.stop() go? Does its location change?

4. How many packages need archive rebuilds? Does this trigger a cascade to PKG-GENESIS-000?

5. How many new tests are you writing, and do any require ANTHROPIC_API_KEY?

6. What does `pristine.assert_append_only()` check? Why do HO2/HO1 governance.jsonl files fail this check when created by boot_materialize?

7. In the `finally` block, if `pristine_patch` is None (non-dev mode), what happens? Show the guard logic.

8. What is the exact import already in main.py that provides the `patch` function? Do you need to add any new imports?

9. After your fix, list the complete execution order of `run_cli()` in dev mode from entry to session start (6 steps).

10. For the clean-room verification, what exact command proves the fix works? What was the crash before, and what is the expected output after?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

---

## Expected Answers (for reviewer — do NOT show to agent)

1. **Bug:** `boot_materialize(root)` is called at line 195 of `run_cli()`, but the dev-mode pristine bypass (`patch("kernel.pristine.assert_append_only")`) doesn't start until line 203-204. When boot_materialize writes GENESIS entries to HO2/HO1 governance.jsonl, pristine.py raises `WriteViolation` because those files aren't in file_ownership.csv yet. **Error:** `kernel.pristine.WriteViolation: Path is not append-only: HO2/ledger/governance.jsonl`

2. **Fix:** New order in `run_cli()`:
   - (1) Start pristine_patch (if dev_mode)
   - (2) Call boot_materialize(root)
   - (3) Call build_session_host(...)
   The pristine bypass must be active BEFORE boot_materialize runs.

3. **`pristine_patch.stop()` stays in the `finally` block** — its location does NOT change. The `finally` ensures cleanup whether the session exits normally or crashes.

4. **One package:** PKG-ADMIN-001 only. Rebuild PKG-ADMIN-001.tar.gz and CP_BOOTSTRAP.tar.gz. **No cascade** — PKG-ADMIN-001 is Layer 3 and not referenced by PKG-GENESIS-000's seed_registry.json, so no digest update needed.

5. **3 new tests.** Zero ANTHROPIC_API_KEY required. All use tmp_path fixtures and mocked dependencies.

6. **`assert_append_only(path)`** checks that a file is classified as a LEDGER path (append-only allowed) in the pristine system. HO2/HO1 governance.jsonl files fail because they are brand new — boot_materialize just created them, they aren't registered in file_ownership.csv yet, so pristine classifies them as DERIVED/NORMAL and rejects the write.

7. **Guard:** `if pristine_patch is not None: pristine_patch.stop()` — the existing `finally` block already checks for None before calling stop(). In non-dev mode, `pristine_patch` remains None and stop() is never called. No change needed.

8. **`from unittest.mock import patch`** — already imported at line 17 of main.py. No new imports needed.

9. **Dev mode execution order:**
   1. `_ensure_import_paths(root=root)`
   2. `from boot_materialize import boot_materialize`
   3. Create and start `pristine_patch` (dev_mode=True)
   4. `boot_materialize(root)` — runs under pristine bypass
   5. `build_session_host(root, config_path, dev_mode)` — builds all dependencies
   6. `host.start_session()` — session begins

10. **Command:** `python3 cp_root/HOT/admin/main.py --root cp_root --dev <<< "exit"`
    **Before fix:** Crash with `kernel.pristine.WriteViolation: Path is not append-only: HO2/ledger/governance.jsonl`
    **After fix:** Session starts and exits cleanly, HO2/HO1 directories + tier.json + governance.jsonl exist.
