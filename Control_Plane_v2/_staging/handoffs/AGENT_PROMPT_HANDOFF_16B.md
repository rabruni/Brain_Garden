# Agent Prompt: HANDOFF-16B

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**YOUR IDENTITY -- print this FIRST before doing anything else:**
> **Agent: HANDOFF-16B** -- PKG-LLM-GATEWAY-001: mechanical rename PromptRouter -> LLMGateway (zero functionality change)

This identifies you in the user's terminal. Always print your identity line as your very first output.

**Read this file FIRST -- it is your complete specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_16B_llm_gateway.md`

**Also read the builder standard for results file format:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_STANDARD.md`

**Also read the source file you are renaming:**
`Control_Plane_v2/_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/prompt_router.py`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design -> Test -> Then implement. Write tests FIRST.
3. ZERO functionality change. If you add new methods, change signatures, or modify behavior -- you are doing it wrong.
4. Tar archive format: use Python tarfile module with explicit arcname (NEVER shell tar with `./` prefix).
5. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_HANDOFF_16B.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What is the ONE new package you are creating? What layer does it install at? Does it modify any existing packages?

2. What class name is being renamed, and what is the new name? What file name is being renamed, and what is the new file name?

3. How does backward compatibility work? Describe the two mechanisms (alias in llm_gateway.py and the shim prompt_router.py).

4. Does `from prompt_router import PromptRouter` continue to work after this rename? How?

5. List ALL public names that must be importable from `llm_gateway.py`. (Hint: there are 8+ classes/enums/dataclasses plus the alias.)

6. What is the content of the thin re-export shim `prompt_router.py`? Write it out exactly.

7. Are there ANY API changes -- new methods, changed parameters, removed functionality? What is the correct answer?

8. How do PKG-LLM-GATEWAY-001 and PKG-PROMPT-ROUTER-001 coexist? Is the old package modified?

9. How many tests are in the test plan? Do any require real LLM calls or API keys?

10. Where does `provider.py` (MockProvider, LLMProvider protocol) live? Is it copied into this package or imported from PKG-PROMPT-ROUTER-001?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

---

## Expected Answers (for reviewer -- do NOT show to agent)

1. **New:** PKG-LLM-GATEWAY-001 (Layer 3). **Modified:** NONE. PKG-PROMPT-ROUTER-001 is NOT modified. This is a new package that coexists alongside it.

2. **Class:** `PromptRouter` -> `LLMGateway`. **File:** `prompt_router.py` -> `llm_gateway.py`. The old `prompt_router.py` becomes a thin re-export shim (new file in this package, not a modification to the old package).

3. **Two mechanisms:** (1) `llm_gateway.py` includes `PromptRouter = LLMGateway` alias at the bottom, so code importing from the new module gets both names. (2) A thin `prompt_router.py` shim does `from llm_gateway import *` and `PromptRouter = LLMGateway`, so code doing `from prompt_router import PromptRouter` continues to work when this package's kernel dir is on sys.path.

4. **Yes.** The shim `prompt_router.py` in PKG-LLM-GATEWAY-001 does `from llm_gateway import *` followed by `PromptRouter = LLMGateway`. When this package's `HOT/kernel/` is on sys.path (and shadows or supplements the old package), the import resolves through the shim to the `LLMGateway` class.

5. **Public names from `llm_gateway.py`:** `LLMGateway` (primary class), `PromptRouter` (alias), `PromptRequest`, `PromptResponse`, `RouteOutcome`, `CircuitState`, `CircuitBreaker`, `CircuitBreakerConfig`, `RouterConfig`. That's 9 names.

6. **Exact content:**
   ```python
   """Backward-compatibility shim. Use llm_gateway.py for new code."""
   from llm_gateway import *  # noqa: F401,F403
   PromptRouter = LLMGateway  # noqa: F405
   ```

7. **Zero.** No new methods, no changed parameters, no removed functionality, no new features. This is a mechanical rename only. If the answer is anything other than "zero," the implementation is wrong.

8. **Coexistence:** Both packages exist in _staging. PKG-PROMPT-ROUTER-001 is NOT modified -- its files remain as-is. PKG-LLM-GATEWAY-001 ships its own `llm_gateway.py` (new) and its own `prompt_router.py` (shim). When both are installed, the shim in PKG-LLM-GATEWAY-001 provides backward-compat. Archival of PKG-PROMPT-ROUTER-001 is a separate future task.

9. **18 tests.** Zero real LLM calls, zero API keys required. All tests use `MockProvider` from `provider.py` and `tmp_path` fixtures for isolated ledger paths.

10. **`provider.py` lives in `PKG-PROMPT-ROUTER-001/HOT/kernel/provider.py`.** It is NOT copied into PKG-LLM-GATEWAY-001. Tests import it from there by adding `PKG-PROMPT-ROUTER-001/HOT/kernel` to `sys.path`. The `LLMProvider` protocol and `MockProvider` are not part of this rename.
