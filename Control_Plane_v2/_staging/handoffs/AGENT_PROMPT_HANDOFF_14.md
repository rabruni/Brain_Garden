# Agent Prompt: HANDOFF-14

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**YOUR IDENTITY — print this FIRST before doing anything else:**
> **Agent: HANDOFF-14** — PKG-HO1-EXECUTOR-001: HO1 Executor — canonical LLM execution point (FIRST non-HOT package, plane_id: "ho1")

This identifies you in the user's terminal. Always print your identity line as your very first output.

**Read this file FIRST — it is your complete specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_14_ho1_executor.md`

**Also read these files for context:**
- `Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` — results file format, baseline snapshot format
- `Control_Plane_v2/_staging/FMWK-009_Tier_Boundary/tier_boundary.md` — HO1 import restrictions (Section 3)
- `Control_Plane_v2/_staging/FMWK-011_Prompt_Contracts/prompt_contracts.md` — contract loading rules (Section 8)
- `Control_Plane_v2/_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/prompt_router.py` — PromptRequest/PromptResponse dataclasses (lines 36-82)
- `Control_Plane_v2/_staging/PKG-SESSION-HOST-001/HOT/kernel/tool_dispatch.py` — ToolDispatcher to copy (110 LOC)
- `Control_Plane_v2/_staging/PKG-SESSION-HOST-001/HOT/kernel/session_host.py` — tool_use extraction pattern (lines 178-284)
- `Control_Plane_v2/_staging/PKG-TOKEN-BUDGETER-001/HOT/kernel/token_budgeter.py` — BudgetScope, TokenUsage, DebitResult dataclasses (lines 27-99)
- `Control_Plane_v2/_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` — LedgerClient.write() API (line 384), LedgerEntry dataclass (lines 104-128)
- `Control_Plane_v2/_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/prompt_contract.schema.json` — schema for contract validation
- `Control_Plane_v2/_staging/FMWK-008_Work_Order_Protocol/work_order_protocol.md` — WO schema (Section 4), WO types (Section 2)

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: use Python tarfile module with explicit arcname (NEVER shell tar with `./` prefix).
4. The Gateway instance is received via DI (constructor parameter). NEVER import PromptRouter/LLMGateway as a class. Import only PromptRequest/PromptResponse dataclasses.
5. LedgerClient method is write() — NEVER append().
6. This is plane_id "ho1" — files install to HO1/, NOT HOT/. The manifest must declare "plane_id": "ho1".
7. ToolDispatcher is COPIED from PKG-SESSION-HOST-001, not imported from it. The archived package cannot be imported.
8. Contract loader is MVP: file-based scan, schema validation, no caching.
9. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_HANDOFF_14.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What does HO1 own vs NOT own? List what HO1Executor is responsible for and what belongs to HO2.

2. Per FMWK-009 Section 3, what can HO1 code import and what is forbidden? Give specific examples of allowed and forbidden imports.

3. What 3 prompt contracts ship with this package? Give each contract_id, and name the schema file that validates them.

4. Describe the tool loop flow: What happens when the gateway returns a response with tool_use blocks? Walk through each step until a text response is returned.

5. How does HO1 get the Gateway instance — import or DI? Why is this critical for FMWK-009 compliance?

6. How does HO1 map WorkOrder fields to PromptRequest fields? List at least 5 field mappings from WO/contract to PromptRequest.

7. This is the first package with plane_id "ho1". What directory do files install to? What import path setup is needed?

8. Where does ToolDispatcher come from, and why is it copied rather than imported from its original package?

9. How many tests minimum? What are the key mocks (list at least 4)?

10. Who calls HO1Executor.execute(), and what do they expect back? What fields on the returned WorkOrder must be populated?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

---

## Expected Answers (for reviewer — do NOT show to agent)

1. **HO1 owns**: WO execution, prompt contract loading, tool loop (multi-round tool_use until text or budget), HO1m canonical trace writing, budget debit per call, input/output validation. **HO1 does NOT own**: WO creation (HO2), WO verification against acceptance criteria (HO2), attention/context assembly (HO2), routing decisions (HO2), session lifecycle (HO2).

2. **HO1 MAY import**: Python standard library; `HOT/kernel/` syscall interfaces (LedgerClient, LedgerEntry as value objects); PromptRequest/PromptResponse dataclasses from PKG-PROMPT-ROUTER-001 (value objects, not service classes); BudgetScope/TokenUsage/DebitResult from PKG-TOKEN-BUDGETER-001 (value objects); own HO1 modules (contract_loader, tool_dispatch). **HO1 MUST NOT import**: `HO2.*` (any HO2 module); `HOT/ledger/` (direct ledger file access); `HOT/registries/` (governance registries); `HOT/config/` policy files; PromptRouter/LLMGateway class (gets instance via DI instead); any module exposing HO2m or HO3m state.

3. **Three contracts**: `classify.json` (PRC-CLASSIFY-001), `synthesize.json` (PRC-SYNTHESIZE-001), `execute.json` (PRC-EXECUTE-001). All validated against `prompt_contract.schema.json` from PKG-PHASE2-SCHEMAS-001.

4. **Tool loop flow**: Gateway returns response with tool_use blocks in JSON content. HO1 extracts tool_use objects (each has tool_id + arguments). For each tool_use, HO1 calls `ToolDispatcher.execute(tool_id, arguments)` and gets a ToolResult. HO1 logs a TOOL_CALL entry to HO1m. HO1 appends the tool results to the conversation context. HO1 sends the updated conversation back to the gateway via `gateway.route()`. HO1 logs another LLM_CALL and debits budget. If the new response is text (no tool_use), the loop breaks. If still tool_use, repeat. If budget exhausted or turn_limit reached, fail the WO.

5. **DI (dependency injection)**. The Gateway instance is passed to HO1Executor's constructor, not imported as a class. This is critical for FMWK-009 because HO1 code in `HO1/` MUST NOT import HOT modules that expose tier state. By receiving the instance via DI, HO1 uses the Gateway's `.route()` method without knowing the class name, module path, or implementation. This also makes testing trivial — mock the gateway, inject it.

6. **Field mappings**: (a) `contract_id` from `wo["constraints"]["prompt_contract_id"]`; (b) `max_tokens` from `contract["boundary"]["max_tokens"]`; (c) `temperature` from `contract["boundary"]["temperature"]`; (d) `template_variables` from `wo["input_context"]`; (e) `work_order_id` from `wo["wo_id"]`; (f) `session_id` from `wo["session_id"]`; (g) `provider_id` from `contract["boundary"].get("provider_id")` (optional); (h) `structured_output` from `contract["boundary"].get("structured_output")` (optional); (i) `input_schema`/`output_schema` from contract.

7. **Files install to `HO1/`** directory — `HO1/kernel/`, `HO1/contracts/`, `HO1/tests/`. This is the FIRST non-HOT package. Import path setup: tests and runtime code need `sys.path` entries for `HO1/kernel/` (own code) and `HOT/kernel/` (for LedgerClient, PromptRequest dataclasses, etc.), following the `_ensure_import_paths()` pattern from `main.py`.

8. **ToolDispatcher** is copied from `PKG-SESSION-HOST-001/HOT/kernel/tool_dispatch.py` (110 LOC) into `HO1/kernel/tool_dispatch.py`. It is copied rather than imported because PKG-SESSION-HOST-001 is **archived** — archived packages cannot be imported, and importing from `HOT/kernel/` for a class that no longer lives there would be incorrect. The copy is self-contained (only depends on stdlib + dataclasses).

9. **35 tests minimum.** Key mocks: (a) Gateway instance (Mock with `.route()` returning mock PromptResponse); (b) TokenBudgeter (Mock with `.check()` and `.debit()` returning mock BudgetCheckResult/DebitResult); (c) LedgerClient (Mock with `.write()` capturing written entries); (d) ToolDispatcher (Mock with `.execute()` returning mock ToolResult). No real LLM calls.

10. **HO2 Supervisor** (HANDOFF-15) calls `HO1Executor.execute(work_order)`. Expects back a WorkOrder dict with: `output_result` populated (the LLM response or tool result); `state` set to `"completed"` or `"failed"`; `cost` populated with `input_tokens`, `output_tokens`, `total_tokens`, `llm_calls`, `tool_calls`, `elapsed_ms`; `completed_at` set to ISO8601 timestamp; `error` populated if state is `"failed"`.
