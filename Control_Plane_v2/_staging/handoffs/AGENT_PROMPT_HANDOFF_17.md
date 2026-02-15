# Agent Prompt: HANDOFF-17

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**YOUR IDENTITY — print this FIRST before doing anything else:**
> **Agent: HANDOFF-17** — PKG-SHELL-001: human-facing command shell with REPL loop and admin command parsing

This identifies you in the user's terminal. Always print your identity line as your very first output.

**Read this file FIRST — it is your complete specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_17_shell.md`

**Also read the builder standard for results file format:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_STANDARD.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design -> Test -> Then implement. Write tests FIRST.
3. Tar archive format: use Python tarfile module with explicit arcname (NEVER shell tar with `./` prefix).
4. End-to-end verification: package tests pass, full regression passes, Shell class under 200 lines.
5. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_HANDOFF_17.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.
6. Shell does NOT load config. It receives all dependencies via constructor injection.
7. Shell does NOT modify main.py. The main.py rewiring is a separate followup task.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What is the ONE package you are creating? What layer does it install at? What are its dependencies?

2. What does Shell do vs. what does it delegate? Name the three things Shell owns and the four things it does NOT own.

3. How does Shell distinguish a cognitive turn from an admin command? What is the parsing rule?

4. Describe the REPL loop structure — what are the steps from Shell.run() starting to the loop ending?

5. Shell receives its dependencies via constructor injection. List the four __init__ parameters and explain why Shell does NOT load config from disk.

6. How do you test a REPL without interactive terminal input? What two callable parameters make this possible?

7. How many tests are in the test plan? Do any of them require a real ANTHROPIC_API_KEY or real LLM calls?

8. Does this package modify main.py or any other existing package? What is the relationship between Shell and the current run_cli() function in main.py?

9. What happens when the user types `/foo` (an unknown command)? What happens on empty input? What happens on EOFError?

10. Trace "hello" from the user typing it to seeing a response. Name every component the message passes through.

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

---

## Expected Answers (for reviewer — do NOT show to agent)

1. **PKG-SHELL-001**, Layer 4, plane_id "hot". Dependencies: PKG-SESSION-HOST-V2-001, PKG-KERNEL-001.

2. **Shell owns**: REPL loop, command parsing (`/` prefix), output formatting. **Shell does NOT own**: config loading (main.py), cognitive dispatch (HO2 via SessionHostV2), LLM calls (HO1 via LLM Gateway), session state (HO2 Supervisor).

3. Lines starting with `/` are admin commands (e.g., `/help`, `/exit`, `/show frameworks`). All other non-empty lines are cognitive turns sent to `session_host_v2.process_turn()`. Single parsing rule, unambiguous.

4. (a) Call `session_host_v2.start_session(agent_config)` to get session_id. (b) Print session started message. (c) Set `_running = True`. (d) Loop: read input via `input_fn("admin> ")`. (e) Strip whitespace; skip if empty. (f) If starts with `/`: dispatch to command handler. (g) Else: call `session_host_v2.process_turn(text)`, format and print result. (h) On `/exit`: set `_running = False`, break. (i) On EOFError or KeyboardInterrupt: break. (j) `finally` block: call `session_host_v2.end_session()`, print "Session ended."

5. The four `__init__` parameters: `session_host_v2` (the V2 session host instance), `agent_config` (AgentConfig for the ADMIN agent), `input_fn` (defaults to `input`, injectable for testing), `output_fn` (defaults to `print`, injectable for testing). Shell does NOT load config because separation of concerns is the entire point of this package — main.py handles config loading and dependency construction, Shell handles presentation.

6. **Dependency injection for I/O.** `input_fn` and `output_fn` are constructor parameters. Tests inject mock callables: `input_fn` returns preset strings from a list (simulating user typing), `output_fn` appends to a captured list (recording what Shell would print). No real terminal interaction, no stdin/stdout mocking.

7. **13 tests.** Zero real API calls, zero ANTHROPIC_API_KEY required. All tests use mock SessionHostV2 and injected I/O functions.

8. **No.** This package creates new files only (shell.py, test_shell.py, manifest.json). It does NOT modify main.py or any other existing package. Shell replaces the REPL loop pattern currently in `run_cli()`, but the actual rewiring of main.py to instantiate Shell is a separate followup task noted in the spec.

9. `/foo` (unknown): Shell prints "Unknown command: /foo. Type /help for available commands." Empty input: stripped to empty string, skipped (continue), no error. EOFError: caught in try/except, breaks the loop, `finally` block calls `end_session()` and prints "Session ended."

10. User types "hello" -> Shell.run() reads via input_fn -> strip -> not empty, not `/` prefix -> cognitive turn -> Shell calls `session_host_v2.process_turn("hello")` -> SessionHostV2 delegates to HO2 Supervisor -> HO2 creates WO#1 classify -> dispatches to HO1 Executor -> HO1 loads prompt contract, calls LLM Gateway -> LLM response -> HO1 returns completed WO -> HO2 creates WO#2 synthesize -> HO1 synthesizes -> HO2 verifies -> SessionHostV2 returns TurnResult -> Shell calls `_format_result(result)` -> Shell prints "assistant: {result.response}" via output_fn -> user sees response.
