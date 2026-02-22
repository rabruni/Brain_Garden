# Builder Handoff: FMWK-011 — Prompt Contracts

## 1. Mission

Create the FMWK-011 Prompt Contracts governance framework. This framework formalizes Invariant #4 from KERNEL_PHASE_2_v2.md: "Communication is contractual. Versioned prompt contracts with JSON schemas. Every exchange recorded."

Prompt contracts are the IPC protocol between HO2 (caller) and HO1 (executor). Without this framework, HO1 receives unstructured strings and returns unstructured strings. Contracts make every LLM exchange versioned, schema-validated, and auditable.

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/FMWK-011_Prompt_Contracts/`.** Create this directory. No files outside it except the results file.
2. **v2 is design authority.** Every claim in the framework MUST trace to a specific section of `_staging/architecture/KERNEL_PHASE_2_v2.md`.
3. **Reference existing schemas as-is.** The `prompt_contract.schema.json` from PKG-PHASE2-SCHEMAS-001 defines the contract structure. Reference it — do NOT redefine it. If the framework needs schema changes, document as a "Schema Extension Proposal" section.
4. **manifest.yaml required.** Create a `manifest.yaml` following the format in `_staging/FMWK-008_Work_Order_Protocol/manifest.yaml`.
5. **Results file required.** When finished, write `_staging/RESULTS_FMWK011.md` with section-by-section verification results.
6. **Use terminology from v2.** If a term was defined by FMWK-008A (metadata key standard, Kitchener step mapping), defer to that definition.

---

## 3. Architecture / Design

### What FMWK-011 Governs

FMWK-011 is the governance standard for prompt contracts — the versioned, schema-validated specifications for every LLM exchange. It defines:
- Contract identity (ID format, versioning rules)
- Contract schema (required fields, boundary constraints)
- Input/output schema conventions (how to define what goes in and what comes out)
- Required context specification (what attention must assemble before the contract fires)
- Dual validation protocol (syntactic first, semantic second)
- Contract loading and resolution rules (how HO1 finds and loads the right contract)
- Contract lifecycle (versioning, deprecation, migration)

### What FMWK-011 Does NOT Govern

- Work order schema or lifecycle (FMWK-008)
- Tier boundary enforcement (FMWK-009)
- Cognitive stack instantiation (FMWK-010)
- Specific contract instances (those ship with their consuming packages — `classify.json` with HANDOFF-14, etc.)
- The runtime contract loader (HO1 Executor, HANDOFF-14)

### Non-Negotiable Rules From v2

From v2 §10 Invariant #4: "Communication is contractual. Versioned prompt contracts with JSON schemas. Every exchange recorded."

From v2 §12 (Design Principles From CS Kernel Theory): "All tier-to-tier communication uses versioned prompt contracts with JSON schemas. HO2→HO1 dispatch = work orders. HO1→LLM = prompt contracts. No raw strings."

From v2 §13 (Prior Art Patterns): "Dual validation (syntactic → semantic). Reusable pattern: cheap/deterministic check first, expensive/LLM check second, both must pass."

From v2 §1 (Kitchener Step 3): "HO1 loads a prompt contract, makes the LLM call through a deterministic gateway, and returns the result."

### Adversarial Analysis: Schema Rigidity vs Flexibility

**Hurdles**: Over-specifying `output_schema` blocks useful exploratory results. If a classify contract requires exactly `{speech_act: string, ambiguity: string}`, the LLM can't return useful auxiliary information. Under-specifying means no validation is possible.

**Not Enough**: Without output schemas, there's no structural validation at all. HO2's Step 4 (Verification) has nothing to check against. Every "did it work?" becomes an LLM judgment call, which is expensive and unreliable.

**Too Much**: Mandating full JSON Schema for every output field creates brittle contracts that break when LLM behavior changes. The contract becomes a straitjacket instead of a guardrail.

**Synthesis**: Require `output_schema` to define the STRUCTURE (required keys, types), but allow `additionalProperties: true` by default. Core fields are validated; auxiliary information passes through. Contracts that need strict output (e.g., classification) can set `additionalProperties: false`. This is a per-contract decision, not a framework default.

---

## 4. Implementation Steps

1. **Read v2 Sections 4, 12, 13** — agent classes, IPC/capabilities, dual validation
2. **Read v2 Section 1** — understand Kitchener Step 3 (where contracts execute)
3. **Read v2 Section 10** — invariants, especially #4 (contractual communication)
4. **Read `prompt_contract.schema.json`** — understand existing contract structure (contract_id, version, boundary, required_context, input_schema, output_schema)
5. **Read `PromptRequest` dataclass in `prompt_router.py`** — understand existing fields (`contract_id`, `prompt_pack_id`) that link to contracts
6. **Create directory** `_staging/FMWK-011_Prompt_Contracts/`
7. **Write `prompt_contracts.md`** with these sections:
   - Purpose, Scope
   - 1. Contract Identity (ID format, versioning)
   - 2. Contract Schema (reference `prompt_contract.schema.json`, explain each field's role)
   - 3. Boundary Constraints (max_tokens, temperature, provider, structured_output)
   - 4. Input Schema (template variables, assembled context requirements)
   - 5. Output Schema (structural validation, additionalProperties policy)
   - 6. Required Context (ledger_queries, framework_refs, file_refs — what attention must provide)
   - 7. Dual Validation Protocol (syntactic: schema check; semantic: LLM output check)
   - 8. Contract Loading and Resolution (how HO1 finds the contract by contract_id)
   - 9. Versioning and Lifecycle (semver rules, deprecation, migration)
   - 10. Implementation Mapping (which packages consume this framework)
   - Conformance, Status
8. **Write `manifest.yaml`** — framework manifest with invariants
9. **Write `_staging/RESULTS_FMWK011.md`** — verification results

---

## 5. Package Plan

FMWK-011 is a governance framework, not a code package. It stays standalone in `_staging/FMWK-011_Prompt_Contracts/` until PKG-HO1-EXECUTOR-001 (HANDOFF-14) absorbs it as a governing framework for contract loading.

No tar archive. No install step. No pytest.

---

## 6. Test Plan — Document Verification Checklist

| # | Check | Method | Pass Criteria |
|---|-------|--------|---------------|
| 1 | Contract ID format defined | Read Section 1 | Pattern matches `prompt_contract.schema.json` (`^PRC-[A-Z]+-[0-9]+$`) |
| 2 | All `prompt_contract.schema.json` fields explained | Read Section 2 | contract_id, version, prompt_pack_id, agent_class, tier, boundary, required_context, input_schema, output_schema all covered |
| 3 | Boundary constraints documented | Read Section 3 | max_tokens, temperature, provider_id, structured_output explained |
| 4 | Dual validation protocol defined | Read Section 7 | Syntactic (schema) → Semantic (LLM output) sequence with both-must-pass rule |
| 5 | additionalProperties policy stated | Read Section 5 | Default `true`, override to `false` per-contract |
| 6 | Contract loading mechanism described | Read Section 8 | HO1 resolves contract_id to file, loads, validates against schema |
| 7 | Versioning rules defined | Read Section 9 | Semver, deprecation rules, no breaking changes in minor versions |
| 8 | All v2 references accurate | Cross-check v2 sections | Section titles match v2 headings |
| 9 | No schema modifications | Check `_staging/PKG-PHASE2-SCHEMAS-001/` | No files changed |
| 10 | manifest.yaml valid YAML | Parse | No syntax errors |
| 11 | Invariant #4 fully covered | Read framework | Contractual communication enforced |
| 12 | Invariant #6 addressed | Read Section 7 | Structural validation pattern documented |
| 13 | Invariant #1 referenced | Read framework | Contracts route through LLM Gateway (no direct calls) |

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| v2 Section 4: Agent Classes | `_staging/architecture/KERNEL_PHASE_2_v2.md` §4 | agent_class enum values |
| v2 Section 10: Invariants | `_staging/architecture/KERNEL_PHASE_2_v2.md` §10 | Invariant #4 (contractual), #6 (structural validation) |
| v2 Section 12: CS Kernel Theory | `_staging/architecture/KERNEL_PHASE_2_v2.md` §12 | IPC = schema-enforced message passing |
| v2 Section 13: Prior Art Patterns | `_staging/architecture/KERNEL_PHASE_2_v2.md` §13 | Dual validation pattern |
| v2 Section 1: Kitchener loop | `_staging/architecture/KERNEL_PHASE_2_v2.md` §1 | Step 3: HO1 loads contract |
| Prompt contract schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/prompt_contract.schema.json` | Existing contract structure (reference, don't modify) |
| PromptRequest dataclass | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/prompt_router.py` | Fields that link to contracts (contract_id, prompt_pack_id) |
| FMWK-008 draft | `_staging/FMWK-008_Work_Order_Protocol/work_order_protocol.md` | Format exemplar + WO field `constraints.prompt_contract_id` |
| FMWK-008 manifest | `_staging/FMWK-008_Work_Order_Protocol/manifest.yaml` | Manifest format exemplar |
| FMWK-000 (Governance) | Installed framework | Format exemplar for document structure |

---

## 8. End-to-End Verification

1. **Markdown structure check**: Confirm Purpose, Scope, 10 numbered sections, Conformance, Status all present.
2. **YAML lint**: Parse `manifest.yaml` — no syntax errors.
3. **v2 cross-reference**: For each `v2 Section N` reference, verify section number and title match actual v2.
4. **Schema integrity**: Confirm no files in `_staging/PKG-PHASE2-SCHEMAS-001/` were modified.
5. **Field coverage**: Every field in `prompt_contract.schema.json` must be explained somewhere in the framework document.

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `prompt_contracts.md` | `_staging/FMWK-011_Prompt_Contracts/` | CREATE — the framework standard |
| `manifest.yaml` | `_staging/FMWK-011_Prompt_Contracts/` | CREATE — framework manifest |
| `RESULTS_FMWK011.md` | `_staging/` | CREATE — verification results |

---

## 10. Design Principles

1. **Contracts are the IPC protocol.** Every LLM exchange has a versioned contract. No raw strings cross tier boundaries.
2. **Schema validates structure, not content.** `output_schema` checks that required keys exist and have correct types. Content quality is HO2's job (Step 4 verification).
3. **Dual validation: cheap then expensive.** Syntactic schema check first (deterministic, free). Semantic LLM output check second (expensive, only if schema passes). Both must pass.
4. **Permissive by default, strict by choice.** `additionalProperties: true` is the default. Contracts that need strict output opt in to `false`.
5. **Contracts don't own context.** `required_context` declares what attention must provide, but the contract doesn't assemble context itself. That's HO2's attention function.
6. **FMWK-011 defers to FMWK-009 on tier boundary definitions.** If FMWK-011 discovers a gap in tier rules, flag it — don't fill it.
