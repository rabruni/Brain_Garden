# Agent Prompt: FMWK-009

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: FMWK-009** — Create Tier Boundary governance framework

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_FMWK009_tier_boundary.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/FMWK-009_Tier_Boundary/`. Create this directory. No files outside except the results file.
2. v2 (`_staging/architecture/KERNEL_PHASE_2_v2.md`) is the ONLY design authority.
3. Do NOT modify any existing code files. Reference them, don't change them.
4. This framework depends on FMWK-008A's metadata key standard. Reference it.
5. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_FMWK009.md`.

**Before writing ANY content, answer these 10 questions to confirm your understanding:**

1. What does FMWK-009 govern? What is the core principle in one sentence?
2. What does FMWK-009 NOT govern? Name at least 3 things that belong to other frameworks or packages.
3. Which v2 sections are your primary sources? List section numbers AND titles.
4. What can each tier see? Reproduce the visibility table from v2 Section 5 for all 3 tiers.
5. What syscalls must be enumerated? List at least 6 syscalls that a lower tier can invoke on a higher tier.
6. What existing code defines role-based access? What file, what roles does it define? (Read the file, don't guess.)
7. What sections must the framework document contain (list all by number and title)?
8. What fields must `manifest.yaml` contain? Follow the format from FMWK-008's manifest.
9. How will you enforce import restrictions given Python has no module-level import blocking?
10. How does FMWK-009 interact with FMWK-008A (Work Order Protocol), FMWK-010 (Cognitive Stack), and FMWK-011 (Prompt Contracts)?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

---

## Expected Answers (for reviewer, not shown to agent)

**Q1**: FMWK-009 governs tier boundaries — the isolation rules between HO1, HO2, and HO3/HOT. Core principle: "Reading up is forbidden. Calling through is allowed."

**Q2**: Does NOT govern: (a) WO schema/lifecycle (FMWK-008), (b) cognitive stack instantiation/isolation (FMWK-010), (c) prompt contract schema (FMWK-011), (d) auth/authz implementation (PKG-KERNEL-001 `authz.py`), (e) budget calculation/tracking (PKG-TOKEN-BUDGETER-001).

**Q3**: v2 §5 "The Visibility / Syscall Model" (primary), v2 §12 "Design Principles From CS Kernel Theory" (capabilities), v2 §4 "Agent Classes" (capability matrix), v2 §10 "Architectural Invariants" (invariants #1, #5), v2 §8 "Infrastructure Components" (LLM Gateway, Token Budgeter as KERNEL.syntactic).

**Q4**: HO3 sees: All (HO3m + HO2m + HO1m + Meta ledger). HO2 sees: HO2m + HO1m; receives constraints from HO3 (pushed down); can call HO3 services. HO1 sees: Only its work order context; receives instructions from HO2 (dispatched); can call HOT infrastructure (LLM Gateway, provider, ledger client).

**Q5**: `LLM_GATEWAY_CALL` (HO1 → LLM Gateway in HOT), `LEDGER_WRITE` (any tier → ledger_client), `LEDGER_READ` (tier reads own + lower tiers), `SCHEMA_VALIDATE` (any → schema_validator), `BUDGET_CHECK` (HO2 → token_budgeter), `BUDGET_DEBIT` (HO1 → token_budgeter), `POLICY_LOOKUP` (HO2 → HO3m for constraints).

**Q6**: `_staging/PKG-KERNEL-001/HOT/kernel/authz.py`. Roles: `admin`, `maintainer`, `auditor`, `reader`. Each role has permissions for read/write/manage operations.

**Q7**: Purpose, Scope, 1. Visibility Matrix, 2. Syscall Definitions, 3. Import Restrictions, 4. Budget Enforcement Chain, 5. Tier-Tagged Ledger Entries, 6. Enforcement Mechanism, 7. Capability Ceilings, 8. Cross-Tier Communication Patterns, 9. Implementation Mapping, 10. Future Extensions, Conformance, Status.

**Q8**: `framework_id` (FMWK-009), `title`, `version`, `status`, `ring`, `plane_id`, `created_at`, `assets`, `expected_specs`, `invariants` (array of `{level, statement}`), `path_authorizations`, `required_gates`.

**Q9**: Three-layer enforcement: (1) Path convention — code lives in the correct tier directory. (2) Gate check — `gate_check.py` verifies import statements in staged packages don't cross tier boundaries upward. (3) Future runtime assertion — syscall wrappers validate caller tier. Start with (1) + (2).

**Q10**: FMWK-008A defines the metadata key standard — FMWK-009 uses `scope.tier` and `relational.*` keys when defining tier-tagged ledger entries. FMWK-010 depends on FMWK-009 — cognitive stack isolation requires tier boundary rules. FMWK-011 has a `tier` field in contracts that must align with FMWK-009 rules. FMWK-009 depends on FMWK-008A (metadata keys) but is independent of FMWK-010 and FMWK-011.
