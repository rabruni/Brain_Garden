# Agent Prompt: FMWK-010

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: FMWK-010** — Create Cognitive Stack governance framework

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_FMWK010_cognitive_stack.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/FMWK-010_Cognitive_Stack/`. Create this directory. No files outside except the results file.
2. v2 (`_staging/architecture/KERNEL_PHASE_2_v2.md`) is the ONLY design authority.
3. Do NOT modify any existing schema or code files. Reference them, don't change them.
4. This framework depends on FMWK-009 (Tier Boundary). Reference it, don't duplicate its rules.
5. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_FMWK010.md`.

**Before writing ANY content, answer these 10 questions to confirm your understanding:**

1. What does FMWK-010 govern? What is Invariant #7 in one sentence?
2. What does FMWK-010 NOT govern? Name at least 3 things that belong to other frameworks or packages.
3. Which v2 sections are your primary sources? List section numbers AND titles.
4. What is shared across all cognitive stacks? List ALL shared components from v2 Section 11.
5. What is isolated per stack? List ALL isolated state from v2 Section 11.
6. What is the `applies_to` selector in `attention_template.schema.json`? (Read the file, don't guess.)
7. What sections must the framework document contain (list all by number and title)?
8. What fields must `manifest.yaml` contain? Follow the format from FMWK-008's manifest.
9. How will you verify that the shared and isolated lists are complete — that nothing from v2 §11 is missing?
10. How does FMWK-010 interact with FMWK-008A (Work Order Protocol), FMWK-009 (Tier Boundary), and FMWK-011 (Prompt Contracts)?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

---

## Expected Answers (for reviewer, not shown to agent)

**Q1**: FMWK-010 governs cognitive stack instantiation — how the Kitchener loop is deployed per agent class. Invariant #7: "Separate cognitive stacks per agent class. Each agent class instantiates its own HO2 + HO1 cognitive processes. Shared code, isolated state."

**Q2**: Does NOT govern: (a) what HO2/HO1 cognitive processes do (HANDOFF-14/15), (b) tier boundary enforcement (FMWK-009), (c) WO schema/lifecycle (FMWK-008), (d) prompt contract schema (FMWK-011), (e) cross-stack communication (not needed — stacks are isolated by design).

**Q3**: v2 §11 "Cognitive Stacks — Shared Code, Isolated State" (primary), v2 §3 "Three Things Per Tier" (memory/process/layout distinction), v2 §14 "Concrete Flows" (ADMIN and DoPeJar examples), v2 §10 "Architectural Invariants" (invariant #7), v2 §4 "Agent Classes" (agent class definitions).

**Q4**: Shared: (a) HO3 governance layer (principles, north stars), (b) KERNEL.syntactic (LLM Gateway, gates, integrity, auth), (c) KERNEL.semantic (meta agent reads all stacks), (d) Meta Learning Ledger (cross-cutting).

**Q5**: Isolated: (a) HO2m session state, (b) HO1m execution traces, (c) Attention templates, (d) Framework configuration, (e) Work order context.

**Q6**: `applies_to` is an object with three optional arrays: `agent_class` (enum: KERNEL.syntactic, KERNEL.semantic, ADMIN, RESIDENT), `framework_id` (pattern: `^FMWK-[A-Z0-9-]+$`), `tier` (enum: hot, ho2, ho1). It selects which agents/frameworks/tiers use a given attention template.

**Q7**: Purpose, Scope, 1. Shared Infrastructure, 2. Isolated State, 3. Stack Instantiation Model, 4. Session State Structure, 5. Directory Isolation, 6. Attention Template Binding, 7. Cross-Stack Visibility, 8. Stack Lifecycle, 9. Implementation Mapping, 10. Relationship to Tier Boundaries, Conformance, Status.

**Q8**: `framework_id` (FMWK-010), `title`, `version`, `status`, `ring`, `plane_id`, `created_at`, `assets`, `expected_specs`, `invariants` (array of `{level, statement}`), `path_authorizations`, `required_gates`.

**Q9**: Read v2 §11 line by line. Create a two-column checklist: "shared" and "isolated". For each item v2 mentions, check it off against the framework's Section 1 or Section 2. Any unchecked item is a gap.

**Q10**: FMWK-008A defines WO context (one of the isolated items). FMWK-009 defines tier boundaries that constrain what each stack's tiers can access — FMWK-010 defers to FMWK-009 for those rules. FMWK-011 defines prompt contracts — contracts are loaded per-stack (part of isolated state). FMWK-010 depends on FMWK-009 (tier boundaries constrain stack access). FMWK-010 does NOT depend on FMWK-008A or FMWK-011 directly.
