# Agent Prompt: HANDOFF-16

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**YOUR IDENTITY — print this FIRST before doing anything else:**
> **Agent: HANDOFF-16** — PKG-SESSION-HOST-V2-001: thin adapter delegating session turns to HO2 Supervisor with degradation fallback

This identifies you in the user's terminal. Always print your identity line as your very first output.

**Read this file FIRST — it is your complete specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_16_session_host_v2.md`

**Also read the builder standard for results file format:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_STANDARD.md`

**Also read the V1 Session Host for dataclass reference:**
`Control_Plane_v2/_staging/PKG-SESSION-HOST-001/HOT/kernel/session_host.py`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: use Python tarfile module with explicit arcname (NEVER shell tar with `./` prefix).
4. V2 is THIN — under 100 lines of logic. If you are writing attention, routing, WO creation, or tool dispatch, STOP. That belongs in HO2 Supervisor.
5. Redefine `TurnResult` and `AgentConfig` dataclasses locally in `session_host_v2.py`. Do NOT import from archived PKG-SESSION-HOST-001.
6. LedgerClient method is `write()` — NEVER `append()`.
7. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_HANDOFF_16.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What is V2's relationship to V1 (PKG-SESSION-HOST-001)? Does V2 import from V1? What happens to V1?

2. What are the EXACTLY three things V2 does? If you list more than three, you have scope-crept.

3. What triggers the degradation fallback, and what does the fallback do step by step?

4. Where do the `TurnResult` and `AgentConfig` dataclasses come from? Why not import from V1?

5. What is the `process_turn()` signature, and what are the three possible `outcome` values in the returned `TurnResult`?

6. What happens when BOTH HO2 Supervisor AND LLM Gateway fail during a turn?

7. What are the package's plane_id, layer, and dependencies?

8. How many tests are in the test plan? Do any require a real ANTHROPIC_API_KEY or make real LLM calls?

9. What LedgerClient method is used for degradation logging? (Hint: it is NOT `append()`.)

10. Who calls SessionHostV2, and who does SessionHostV2 call? Name the upstream caller and the two downstream components.

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

---

## Expected Answers (for reviewer — do NOT show to agent)

1. V2 **replaces** V1 functionally. V1 is archived — `PKG-SESSION-HOST-001` remains on disk for provenance but is not installed or imported. V2 is a NEW package (`PKG-SESSION-HOST-V2-001`). V2 does NOT import from V1. `TurnResult` and `AgentConfig` are redefined locally in `session_host_v2.py` for interface compatibility.

2. Exactly three things: (a) `start_session()` / `end_session()` → delegates to HO2 Supervisor, (b) `process_turn()` → delegates to HO2 Supervisor's `handle_turn()`, (c) catches exceptions from HO2 → degrades to direct LLM call through Gateway. If the answer includes attention, routing, WO creation, tool dispatch, or history management — wrong.

3. **Trigger:** any unhandled exception from `ho2_supervisor.handle_turn()`. **Fallback steps:** (1) log a warning, (2) write a DEGRADATION event to ledger via `ledger.write()`, (3) construct a minimal `PromptRequest` with the user message and basic metadata, (4) call `gateway.route(request)`, (5) return the Gateway response as a `TurnResult` with `outcome="degraded"`.

4. Redefined locally in `session_host_v2.py`. Copied from V1's definitions for interface compatibility. NOT imported from archived `PKG-SESSION-HOST-001` because V1 is archived and should not be a runtime dependency. V2 is a new package with its own definitions.

5. `process_turn(user_message: str) -> TurnResult`. Three outcomes: `"success"` (HO2 handled normally), `"degraded"` (HO2 failed, Gateway fallback succeeded), `"error"` (both HO2 and Gateway failed).

6. `TurnResult` returned with `outcome="error"` and a static error message like "Service temporarily unavailable." The double failure is caught by a nested try/except in the `_degrade()` method. No exception propagates to the caller.

7. `plane_id: "hot"`, `layer: 3`. Dependencies: `PKG-HO2-SUPERVISOR-001`, `PKG-HO1-EXECUTOR-001` (transitive via HO2), `PKG-PROMPT-ROUTER-001` (Gateway for degradation fallback), `PKG-KERNEL-001` (LedgerClient for degradation logging).

8. **13 tests.** Zero real LLM calls, zero `ANTHROPIC_API_KEY` required. All tests use `MagicMock` for HO2 Supervisor and Gateway.

9. `write()`. The method is `LedgerClient.write()`, never `append()`.

10. **Upstream caller:** Shell (PKG-SHELL-001, HANDOFF-17) calls `SessionHostV2.process_turn()`. **Downstream:** (a) `HO2Supervisor.handle_turn()` on the normal path, (b) `LLMGateway.route()` (or `PromptRouter.route()`) on the degradation path only.
