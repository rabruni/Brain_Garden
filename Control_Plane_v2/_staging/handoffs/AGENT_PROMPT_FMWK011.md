# Agent Prompt: FMWK-011

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: FMWK-011** — Create Prompt Contracts governance framework

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_FMWK011_prompt_contracts.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/FMWK-011_Prompt_Contracts/`. Create this directory. No files outside except the results file.
2. v2 (`_staging/architecture/KERNEL_PHASE_2_v2.md`) is the ONLY design authority. Every claim must trace to a v2 section.
3. Do NOT modify any schema files in `_staging/PKG-PHASE2-SCHEMAS-001/`. Reference them, don't redefine them.
4. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_FMWK011.md`.

**Before writing ANY content, answer these 10 questions to confirm your understanding:**

1. What does FMWK-011 govern? What is a prompt contract?
2. What does FMWK-011 NOT govern? Name at least 3 things that belong to other frameworks or packages.
3. Which v2 sections are your primary sources? List section numbers AND titles.
4. What are the key invariants this framework enforces? Which v2 invariants (#1-7) does it cover?
5. What are the required fields in the existing `prompt_contract.schema.json`? (Do NOT guess — read the file.)
6. What is the dual validation protocol? What's the sequence and why?
7. What sections must the framework document contain (list all by number and title)?
8. What fields must `manifest.yaml` contain? Follow the format from FMWK-008's manifest.
9. How will you verify completeness — that every field in the existing schema is explained in your framework document?
10. How does FMWK-011 interact with FMWK-008 (Work Order Protocol), FMWK-009 (Tier Boundary), and FMWK-010 (Cognitive Stack)?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

---

## Expected Answers (for reviewer, not shown to agent)

**Q1**: FMWK-011 governs prompt contracts — versioned, schema-validated specifications for every LLM exchange. A prompt contract defines: what goes in (input_schema), what comes out (output_schema), execution boundaries (max_tokens, temperature), required context (what attention must assemble), and which agent class/tier it applies to. It's the IPC protocol between HO2 and HO1.

**Q2**: Does NOT govern: (a) WO schema/lifecycle (FMWK-008), (b) tier boundary enforcement (FMWK-009), (c) cognitive stack instantiation (FMWK-010), (d) specific contract instances like `classify.json` (ship with consuming packages, e.g., HANDOFF-14), (e) the runtime contract loader (HO1 Executor, HANDOFF-14).

**Q3**: v2 §4 "Agent Classes" (agent_class enum), v2 §10 "Architectural Invariants" (invariant #4 contractual, #6 structural validation), v2 §12 "Design Principles From CS Kernel Theory" (IPC = schema-enforced message passing), v2 §13 "Prior Art Patterns" (dual validation), v2 §1 "Grounding Model" (Step 3: HO1 loads contract).

**Q4**: Invariant #4 (communication is contractual) — primary. Invariant #6 (validation is structural) — dual validation. Invariant #1 (no direct LLM calls) — contracts route through LLM Gateway. Key framework invariants: every LLM call requires a contract, contracts are versioned, input/output validated against schemas.

**Q5**: Required: `contract_id` (pattern `^PRC-[A-Z]+-[0-9]+$`), `version` (semver pattern), `prompt_pack_id` (pattern `^PRM-[A-Z]+-[0-9]+$`), `boundary` (object with required `max_tokens` + `temperature`). Optional: `agent_class`, `tier`, `required_context`, `input_schema`, `output_schema`, `metadata`.

**Q6**: Dual validation = syntactic check first (cheap, deterministic — JSON Schema validation of LLM output against `output_schema`), then semantic check second (expensive, LLM-based — does the content actually answer the question?). Both must pass. Syntactic is free/instant; semantic is only invoked if syntactic passes. From v2 §13: "cheap/deterministic check first, expensive/LLM check second."

**Q7**: Purpose, Scope, 1. Contract Identity, 2. Contract Schema, 3. Boundary Constraints, 4. Input Schema, 5. Output Schema, 6. Required Context, 7. Dual Validation Protocol, 8. Contract Loading and Resolution, 9. Versioning and Lifecycle, 10. Implementation Mapping, Conformance, Status.

**Q8**: `framework_id` (FMWK-011), `title`, `version`, `status`, `ring`, `plane_id`, `created_at`, `assets`, `expected_specs`, `invariants` (array of `{level, statement}`), `path_authorizations`, `required_gates`.

**Q9**: Create a checklist of every property in `prompt_contract.schema.json`. After writing the framework document, check each property off against the section that explains it. Any uncovered property is a gap.

**Q10**: FMWK-008 defines WO field `constraints.prompt_contract_id` that links a WO to its contract. FMWK-011 defines what that contract contains. FMWK-009 defines tier boundaries — contracts have a `tier` field that must align with FMWK-009 rules. FMWK-010 defines cognitive stack isolation — contracts are part of the isolated state per stack. FMWK-011 is independent (no build dependency on others) but uses the metadata key standard from FMWK-008A.
