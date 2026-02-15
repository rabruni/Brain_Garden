# Agent Prompt: HANDOFF-15

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**YOUR IDENTITY -- print this FIRST before doing anything else:**
> **Agent: HANDOFF-15** -- PKG-HO2-SUPERVISOR-001: HO2 Supervisor (Kitchener Steps 2+4, attention, quality gate, session lifecycle)

This identifies you in the user's terminal. Always print your identity line as your very first output.

**Read this file FIRST -- it is your complete specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_15_ho2_supervisor.md`

**Also read these critical references:**
- `Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` -- results file format, baseline snapshot format
- `Control_Plane_v2/_staging/FMWK-009_Tier_Boundary/tier_boundary.md` -- visibility rules (HO2 sees HO2m + HO1m, NOT HO3m directly)
- `Control_Plane_v2/_staging/FMWK-010_Cognitive_Stack/cognitive_stack.md` -- factory pattern, shared/isolated boundary
- `Control_Plane_v2/_staging/FMWK-008_Work_Order_Protocol/work_order_protocol.md` -- WO schema, lifecycle, ledger events, trace_hash
- `Control_Plane_v2/_staging/PKG-ATTENTION-001/HOT/kernel/attention_service.py` -- absorption target (pipeline logic, BudgetTracker)
- `Control_Plane_v2/_staging/PKG-ATTENTION-001/HOT/kernel/attention_stages.py` -- absorption target (ContextProvider, ContextFragment)
- `Control_Plane_v2/_staging/PKG-SESSION-HOST-001/HOT/kernel/session_host.py` -- absorption target (session patterns, TurnResult)

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design -> Test -> Then implement. Write tests FIRST.
3. Tar archive format: use Python tarfile module with explicit arcname (NEVER shell tar with `./` prefix).
4. End-to-end verification: package tests pass, attention template validates against schema, no LLM Gateway imports in HO2 code.
5. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_HANDOFF_15.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.
6. HO2 NEVER calls LLM Gateway directly. ALL cognitive work is dispatched as WorkOrders to HO1. If you find yourself importing prompt_router or llm_gateway in HO2 code, STOP -- you are violating Invariant #1.
7. LedgerClient method is `write()`, not `append()`. Pattern: `ledger_client.write(LedgerEntry(event_type="...", ...))`.
8. PKG-ATTENTION-001 and PKG-SESSION-HOST-001 are ARCHIVED. Absorb (copy and adapt) their code into HO2 modules. Do NOT import from them.
9. manifest.json must have `"plane_id": "ho2"` -- this is the first HO2 package.
10. HO1Executor is mocked in tests. Use MockHO1Executor that returns preset WorkOrder results. No real LLM calls.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What are the 4 source files and 1 config file you are creating in this package? Which directory does each live in? What is the plane_id in the manifest?

2. HO2 owns Kitchener Steps 2 and 4. What does Step 2 (Scoping) do, and what does Step 4 (Verification) do? Where does Step 3 (Execution) happen?

3. Trace the handle_turn("hello") flow. Name every WorkOrder created, its wo_type, and what HO1 returns for each.

4. What are the two attention operations, and which tier ledgers does each read? Which FMWK-009 visibility rule governs HO2's read access?

5. This package absorbs code from 2 archived packages. Name the packages, and for each, list ONE thing absorbed, ONE thing adapted, and ONE thing dropped.

6. How does the factory pattern from FMWK-010 apply? If you instantiate HO2Supervisor for ADMIN and for RESIDENT, what differs between the two instances?

7. What does the quality gate check for MVP? What happens when it rejects? What is the max_retries behavior?

8. What 4 event types does HO2 write to HO2m during a turn? What is trace_hash and how is it computed?

9. How many tests minimum? What are the key mocks? Does any test make a real LLM call?

10. Who calls HO2Supervisor.handle_turn() at runtime (which future package), and what does it return?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

---

## Expected Answers (for reviewer -- do NOT show to agent)

1. **4 source files**: `HO2/kernel/ho2_supervisor.py` (main class), `HO2/kernel/attention.py` (AttentionRetriever + ContextProvider), `HO2/kernel/quality_gate.py` (QualityGate), `HO2/kernel/session_manager.py` (SessionManager). **1 config file**: `HO2/attention_templates/ATT-ADMIN-001.json`. Plus `HO2/tests/test_ho2_supervisor.py` and `manifest.json`. **plane_id**: `"ho2"` -- this is the first HO2 package.

2. **Step 2 (Scoping)**: HO2 classifies user intent (dispatches classify WO to HO1), runs attention retrieval (horizontal scan + priority probe), assembles context, creates the synthesize WO with acceptance criteria. **Step 4 (Verification)**: HO2 checks the synthesize WO's output against acceptance criteria via QualityGate. Accept -> return to user. Reject -> retry or escalate. **Step 3 (Execution)**: Happens in HO1. HO1Executor receives WOs, loads prompt contracts, calls LLM Gateway, returns results.

3. **handle_turn("hello") flow**: WO#1 (wo_type=`classify`, input="hello") -> HO1 returns `{speech_act: "greeting", ambiguity: "high"}`. Attention runs: horizontal_scan (recent HO2m) + priority_probe (HO3m, empty). WO#2 (wo_type=`synthesize`, input=classification+context, prior_results=[WO#1 output]) -> HO1 returns `{response_text: "Hello! How can I help you today?"}`. QualityGate.verify() -> accept. Return TurnResult with response.

4. **Two operations**: `horizontal_scan` reads HO2m (recent orchestration context for this session) and HO1m (recent execution traces). `priority_probe` reads HO3m for north stars/salience anchors (initially empty -- HO3m not yet populated). **FMWK-009 visibility**: HO2 can read HO2m + HO1m (Section 1 visibility matrix). HO2 accesses HO3m via POLICY_LOOKUP syscall or pushed-down parameters, NOT direct read.

5. **PKG-ATTENTION-001**: Absorbed -- pipeline execution model (`_run_pipeline()` pattern). Adapted -- `AssembledContext` simplified to `AttentionContext` (drops `pipeline_trace`). Dropped -- `AttentionService.assemble()` standalone interface (attention now internal to HO2). **PKG-SESSION-HOST-001**: Absorbed -- session ID format `SES-{8 hex}` and start/end lifecycle. Adapted -- `TurnResult` gains `wo_chain_summary` and `cost_summary` fields. Dropped -- `process_turn()` flat loop (replaced by Kitchener dispatch).

6. **Factory pattern**: HO2Supervisor code is written ONCE (generic). Each agent class instantiates its own copy with different `HO2Config`: different `attention_templates` (ATT-ADMIN-001 vs ATT-DPJ-001), different `ho2m_path` (scoped per agent class, e.g. `HO2/ledger/ADMIN/workorder.jsonl`), different `budget_ceiling`, different `framework_config`. Shared code, isolated state (FMWK-010 Invariant #7).

7. **MVP quality gate checks**: output_result is not None, not empty, contains `response_text` key, response length > 0. **On reject**: create a new synthesize WO with tighter constraints (retry). **max_retries**: configurable (default 2). After retries exhausted, log escalation event to HO2m instead of retrying again.

8. **4 event types**: `WO_PLANNED` (WO created), `WO_DISPATCHED` (WO sent to HO1), `WO_CHAIN_COMPLETE` (all WOs done for this turn), `WO_QUALITY_GATE` (accept/reject decision). **trace_hash**: SHA256 of concatenated HO1m entries for this WO chain. Computed AFTER HO1 completes all WOs. HO2 reads HO1m entries (filter by session_id + wo_ids), concatenates as sorted JSON, computes SHA256. Stored on `WO_CHAIN_COMPLETE` and `WO_QUALITY_GATE` events in the `metadata.context_fingerprint.context_hash` field.

9. **47 tests minimum.** Key mocks: `MockHO1Executor` (returns preset WorkOrder results per wo_type), `MockLedgerClient` (captures write() calls for assertion), `MockTokenBudgeter` (tracks allocations/checks), `ContextProvider` (returns mock ledger entries and registry rows). **No real LLM calls in any test.**

10. **SessionHostV2** (HANDOFF-16, PKG-SESSION-HOST-V2-001) calls `handle_turn(user_message)`. Returns `TurnResult` with: `response` (user-facing text), `wo_chain_summary` (list of WO summaries), `cost_summary` (token totals), `session_id`, `quality_gate_passed` (bool). The Shell (HANDOFF-17, PKG-SHELL-001) ultimately displays the response to the user.
