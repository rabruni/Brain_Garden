# Agent Prompt: FMWK-008A

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: FMWK-008A** — Update Work Order Protocol with Kitchener alignment, hash-anchored trace, metadata key standard

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_FMWK008A_wo_protocol_update.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/FMWK-008_Work_Order_Protocol/`. No files outside this directory except the results file.
2. This is a draft update — modify the existing `work_order_protocol.md` in-place. Do NOT create a replacement file.
3. v2 (`_staging/architecture/KERNEL_PHASE_2_v2.md`) is the ONLY design authority. Every claim must trace to a v2 section.
4. Do NOT modify any schema files in `_staging/PKG-PHASE2-SCHEMAS-001/`. Reference them, don't redefine them.
5. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_FMWK008A.md`.

**Before writing ANY content, answer these 10 questions to confirm your understanding:**

1. What does FMWK-008 govern? What are the boundaries of its scope?
2. What does FMWK-008 NOT govern? Name at least 3 things that belong to other frameworks.
3. Which v2 sections are your primary sources? List section numbers AND titles.
4. What are the 3 additions you are making to the existing draft? For each, state what v2 section or open question justifies it.
5. What are the exact field paths for relational metadata keys in the existing `ledger_entry_metadata.schema.json`? (Do NOT guess — read the file.)
6. Where does Section 5a (Hash-Anchored Trace) get inserted relative to existing sections? What comes before it and after it?
7. What sections does the existing draft have (list all 10 by number and title)?
8. What fields must the updated `manifest.yaml` contain? List the required fields.
9. How will you verify that your v2 section references are accurate? What specific check do you perform?
10. How does this framework interact with FMWK-009 (Tier Boundary), FMWK-010 (Cognitive Stack), and FMWK-011 (Prompt Contracts)?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

---

## Expected Answers (for reviewer, not shown to agent)

**Q1**: FMWK-008 governs work orders — the atomic unit of cognitive dispatch. Scope: WO schema, WO lifecycle state machine, ledger recording rules, validation rules, budget model, orchestration patterns. Applies to all WOs within a cognitive stack (ADMIN or RESIDENT).

**Q2**: Does NOT govern: (a) prompt contract schema/lifecycle (FMWK-011), (b) tier boundary enforcement/import restrictions (FMWK-009), (c) cognitive stack instantiation/isolation (FMWK-010), (d) runtime WO code (PKG-WORK-ORDER-001).

**Q3**: v2 §1 "Grounding Model: The Kitchener Orchestration Stack" (Kitchener loop), v2 §6 "Memory Architecture" (four ledgers, graph indexing), v2 §10 "Architectural Invariants" (7 invariants), v2 §17 "Work Order Schema" (target WO fields), v2 §18 "Critical Path — What's Next" (hash-anchored trace open question).

**Q4**: (a) Kitchener step alignment — justified by v2 §1 canonical dispatch loop. (b) Hash-anchored trace model — justified by v2 §18 open question "governance ledger gets summaries + trace_hash." (c) Metadata key standard — justified by v2 §6 "Meta ledger is graph-indexed."

**Q5**: `relational.parent_event_id` (string, pattern `^LED-[a-f0-9]{8}$`), `relational.root_event_id` (same pattern), `relational.related_artifacts` (array of `{type: enum, id: string}`). All nested under the `relational` object — no underscore prefix.

**Q6**: Section 5a goes after Section 5 (Ledger Recording) and before Section 6 (Validation Rules). Section 5b goes after 5a, also before Section 6.

**Q7**: 1. Work Order Identity, 2. Work Order Types, 3. Work Order Lifecycle, 4. Work Order Schema, 5. Ledger Recording, 6. Validation Rules, 7. Budget Model, 8. Orchestration Patterns, 9. Error Handling, 10. Implementation Mapping. Plus Purpose, Scope, Relationship to Existing Schema, Conformance, Status.

**Q8**: `framework_id`, `title`, `version`, `status`, `ring`, `plane_id`, `created_at`, `assets`, `expected_specs`, `invariants` (array of `{level, statement}`), `path_authorizations`, `required_gates`.

**Q9**: For each "v2 Section N" reference, open the actual v2 document, navigate to that section number, and verify the heading title matches what the framework claims. Titles are more stable than numbers.

**Q10**: FMWK-008A defines the metadata key standard that FMWK-009 (tier-tagged ledger entries), FMWK-010 (session state metadata), and FMWK-011 (contract-linked ledger entries) all reference. FMWK-009 depends on FMWK-008A being complete. FMWK-011 is independent but uses the same metadata convention. FMWK-010 depends on FMWK-009, which depends on FMWK-008A.
