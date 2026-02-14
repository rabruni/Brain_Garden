# Agent Prompt: HANDOFF-12

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**YOUR IDENTITY — print this FIRST before doing anything else:**
> **Agent: HANDOFF-12** — PKG-BOOT-MATERIALIZE-001: boot-time HO2/HO1 materialization + ledger_client.py path fix

This identifies you in the user's terminal. Always print your identity line as your very first output.

**Read this file FIRST — it is your complete specification:**
`Control_Plane_v2/_staging/BUILDER_HANDOFF_12_boot_materialize.md`

**Also read the builder standard for results file format:**
`Control_Plane_v2/_staging/BUILDER_HANDOFF_STANDARD.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: use Python tarfile module with explicit arcname (NEVER shell tar with `./` prefix).
4. End-to-end verification: clean-room install with 17 packages, 8/8 gates PASS.
5. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_HANDOFF_12.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What is the ONE new package you are creating, and what TWO existing packages are you modifying? What layer does the new package install at?

2. What are the three steps boot_materialize() performs, and in what order? Why does the order matter?

3. Where do tier names and subdirectory names come from? Can you hardcode "HO2" or "HO1" anywhere in boot_materialize.py?

4. The GENESIS chain goes HO1 → HO2 → HOT. When writing HO2's GENESIS entry, what specific value goes into `parent_hash`, and how do you obtain it?

5. What happens if boot_materialize() is called a second time when everything already exists? How many new GENESIS entries are created?

6. In ledger_client.py, what are the exact three functions that have the `planes/` path bug? For `read_recent_from_tier()`, what is the current HOT path (line 1015) and why is it also wrong?

7. After your path fix, what path does `get_session_ledger_path("ho2", "SES-001", root=Path("/cp"))` return? (Write the full path.)

8. In main.py, where exactly does the boot_materialize() call go — before or after `build_session_host()`? What happens if materialization fails?

9. How many tests are in the test plan? Do any of them require a real ANTHROPIC_API_KEY or make real LLM calls?

10. After this handoff, how many total packages are in CP_BOOTSTRAP.tar.gz? What is the install verification: how many packages installed, how many gates must pass?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

---

## Expected Answers (for reviewer — do NOT show to agent)

1. **New:** PKG-BOOT-MATERIALIZE-001 (Layer 3). **Modified:** PKG-KERNEL-001 (ledger_client.py path fix) and PKG-ADMIN-001 (main.py boot call + import path).

2. **Step A:** Materialize directories (calls existing `materialize_layout.materialize()`). **Step B:** Write tier.json manifests for any tier missing one (TierManifest with parent_ledger). **Step C:** Initialize GENESIS entries in order HOT → HO2 → HO1 with hash chain. **Order matters** because each child GENESIS needs the parent tier's last entry hash — if you write HO1 before HO2, there's no HO2 hash to reference.

3. From `HOT/config/layout.json`. The `tiers` map gives tier names → directory names, `tier_dirs` gives subdirectory names. **No hardcoding allowed** — constraint #5 and design principle #2 are explicit about this. If layout.json changes, boot_materialize adapts without code changes.

4. `parent_hash` = the `entry_hash` of the last entry in HOT's governance.jsonl. Obtained via `LedgerClient(ledger_path=hot_ledger_path).get_last_entry_hash_value()`. If HOT's ledger was empty, HOT's GENESIS was written in the step before (order matters), so there will be at least one entry.

5. **Zero** new GENESIS entries. boot_materialize checks `client.count() == 0` before writing GENESIS. If the ledger already has entries, it skips. Directories and tier.json are also checked before creation. Second boot = no-op.

6. The three functions: `get_session_ledger_path()` (line 954), `read_recent_from_tier()` (line 1019), `list_session_ledgers()` (line 1044). For `read_recent_from_tier()`, the HOT path at line 1015 is `root / "ledger" / "governance.jsonl"` — this is wrong because HOT's ledger is inside the HOT directory: `root / "HOT" / "ledger" / "governance.jsonl"`.

7. `/cp/HO2/sessions/SES-001/ledger/exec.jsonl` — note HO2 is uppercase, no `planes/` prefix.

8. **Before** `build_session_host()`. In `run_cli()`, the boot call comes first. If materialization fails (returns non-zero), ADMIN prints a warning but still boots — non-fatal. The session host works against existing HOT structure; HO2/HO1 features degrade gracefully.

9. **21 tests.** Zero real API calls, zero ANTHROPIC_API_KEY required. All tests use `tmp_path` fixtures for isolated plane roots.

10. **17 packages** in CP_BOOTSTRAP.tar.gz (16 existing + PKG-BOOT-MATERIALIZE-001). Verification: 17 packages installed, 8/8 gates PASS.
