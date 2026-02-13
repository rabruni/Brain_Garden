# Agent Prompt: HANDOFF-12A

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**YOUR IDENTITY:**
> **Agent: HANDOFF-12A** — Fix pristine bypass ordering so boot_materialize runs under dev-mode bypass

**Read this file FIRST — it is your complete specification:**
`Control_Plane_v2/_staging/BUILDER_HANDOFF_12A_pristine_fix.md`

**Also read the builder standard for results file format:**
`Control_Plane_v2/_staging/BUILDER_HANDOFF_STANDARD.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: use Python tarfile module with explicit arcname (NEVER shell tar with `./` prefix).
4. End-to-end verification: clean-room install with 17 packages, 8/8 gates PASS.
5. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_HANDOFF_12A.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.

**Before writing ANY code, answer these 5 questions to confirm your understanding:**

1. What is the exact bug? Which line runs too early, and which line runs too late? What error does the user see?

2. What is the fix? Describe the new ordering of the three operations (pristine_patch, boot_materialize, build_session_host) in run_cli().

3. Where does pristine_patch.stop() go? Does its location change?

4. How many packages need archive rebuilds? Does this trigger a cascade to PKG-GENESIS-000?

5. How many new tests are you writing, and do any require ANTHROPIC_API_KEY?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

---

## Expected Answers (for reviewer — do NOT show to agent)

1. **Bug:** `boot_materialize(root)` is called at line 195 of `run_cli()`, but the dev-mode pristine bypass (`patch("kernel.pristine.assert_append_only")`) doesn't start until line 203. When boot_materialize writes GENESIS entries to HO2/HO1 governance.jsonl, pristine.py raises `WriteViolation` because those files aren't in file_ownership.csv yet. **Error:** `kernel.pristine.WriteViolation: Path is not append-only: HO2/ledger/governance.jsonl`

2. **Fix:** New order in `run_cli()`:
   - (1) Start pristine_patch (if dev_mode)
   - (2) Call boot_materialize(root)
   - (3) Call build_session_host(...)
   The pristine bypass must be active BEFORE boot_materialize runs.

3. **`pristine_patch.stop()` stays in the `finally` block** — its location does NOT change. The `finally` ensures cleanup whether the session exits normally or crashes.

4. **One package:** PKG-ADMIN-001 only. Rebuild PKG-ADMIN-001.tar.gz and CP_BOOTSTRAP.tar.gz. **No cascade** — PKG-ADMIN-001 is Layer 3 and not referenced by PKG-GENESIS-000's seed_registry.json, so no digest update needed.

5. **3 new tests.** Zero ANTHROPIC_API_KEY required. All use tmp_path fixtures and mocked dependencies.
