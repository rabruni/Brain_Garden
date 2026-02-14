# Agent Prompt: CLEANUP-1

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: CLEANUP-1** — Remove PKG-FLOW-RUNNER-001 (superseded by HO2+HO1 cognitive dispatch)

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_CLEANUP_1_flow_runner.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. Delete only what is listed in the spec. Do NOT delete process docs that mention Flow Runner historically.
3. Do NOT modify CP_BOOTSTRAP.tar.gz — PKG-FLOW-RUNNER-001 was never in it.
4. When finished, write your results to `Control_Plane_v2/_staging/handoffs/RESULTS_CLEANUP_1.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.

**Before doing ANY work, answer these 10 questions to confirm your understanding:**

1. What are the 5 files you will delete, and what directory are they all under?
2. Why is it safe to delete this package without rebuilding CP_BOOTSTRAP.tar.gz?
3. What is the FMWK-005 collision, and how does deleting PKG-FLOW-RUNNER-001 resolve it?
4. Which FMWK-005 manifest STAYS after deletion, and who owns it?
5. How many process docs mention "flow runner" and why are you NOT changing them?
6. What two changes do you make to BUILDER_HANDOFF_STANDARD.md?
7. What does your `grep` check for dangling imports look for, and what result do you expect?
8. What is the full pytest command for regression testing?
9. If you find an unexpected import of flow_runner in a product file, what do you do?
10. After deletion, what is the expected output of `grep -rl "framework_id.*FMWK-005" _staging/PKG-*/ | grep manifest`?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

## Expected Answers (for reviewer)

1. `manifest.json`, `HOT/kernel/flow_runner.py`, `HOT/schemas/flow_runner_config.schema.json`, `HOT/FMWK-005_Agent_Orchestration/manifest.yaml`, `HOT/tests/test_flow_runner.py` — all under `_staging/PKG-FLOW-RUNNER-001/`
2. PKG-FLOW-RUNNER-001 was never included in CP_BOOTSTRAP.tar.gz. It was staged but never shipped. No archive references it.
3. Both PKG-FLOW-RUNNER-001 (`FMWK-005_Agent_Orchestration`) and PKG-ADMIN-001 (`FMWK-005_Admin`) claim framework ID FMWK-005. Deleting the Flow Runner package removes the competing manifest, leaving ADMIN as the sole owner.
4. `PKG-ADMIN-001/HOT/FMWK-005_Admin/manifest.yaml` stays. PKG-ADMIN-001 owns it.
5. 18 process docs in handoffs/ and architecture/. They're historical narrative references, not functional dependencies. Changing them would sanitize history.
6. (a) Update agent registry: HANDOFF-5 status from "COMPLETE (unvalidated)" to "SUPERSEDED (absorbed by HO2+HO1, CLEANUP-1)". (b) Update cross-cutting concerns: replace "flow runner" with "HO2 supervisor" in 3 rows.
7. `grep -r "import.*flow_runner\|from.*flow_runner" _staging/PKG-*/` — expected result: no matches.
8. `CONTROL_PLANE_ROOT="$TMPDIR" python3 -m pytest Control_Plane_v2/_staging/ -v`
9. STOP and report. Do NOT attempt to fix — it may require a design decision.
10. Only `PKG-ADMIN-001/HOT/FMWK-005_Admin/manifest.yaml`
