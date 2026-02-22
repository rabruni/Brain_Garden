# Builder Handoff: FMWK-010 — Cognitive Stack

## 1. Mission

Create the FMWK-010 Cognitive Stack governance framework. This framework formalizes Invariant #7 from KERNEL_PHASE_2_v2.md: "Separate cognitive stacks per agent class. Each agent class (ADMIN, each RESIDENT) instantiates its own HO2 + HO1 cognitive processes. Shared code, isolated state."

Without this framework, builders might create a single shared HO2 instance or conflate ADMIN and RESIDENT state. FMWK-010 defines what's shared (infrastructure), what's isolated (per-stack state), and how stacks are instantiated.

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/FMWK-010_Cognitive_Stack/`.** Create this directory. No files outside it except the results file.
2. **v2 is design authority.** Every claim in the framework MUST trace to a specific section of `_staging/architecture/KERNEL_PHASE_2_v2.md`.
3. **Depends on FMWK-009 tier boundary rules.** Cognitive stack isolation depends on what tiers can see. Reference FMWK-009, don't duplicate its rules.
4. **Reference existing schemas as-is.** `attention_template.schema.json` and `layout.json` define per-agent template structure and directory layout. Reference them — do NOT modify.
5. **manifest.yaml required.** Create following the format in `_staging/FMWK-008_Work_Order_Protocol/manifest.yaml`.
6. **Results file required.** When finished, write `_staging/RESULTS_FMWK010.md` with section-by-section verification results.
7. **Use terminology from v2.** "Cognitive process" is THE term for tier agents. Not faculty, operator, or module.

---

## 3. Architecture / Design

### What FMWK-010 Governs

FMWK-010 is the governance standard for cognitive stack instantiation — how the Kitchener loop is deployed per agent class. It defines:
- Shared infrastructure boundary (what all stacks share)
- Isolated state boundary (what's unique per stack)
- Stack instantiation model (factory pattern — write once, instantiate per agent class)
- Session state structure for HO2m
- Directory isolation rules (where each stack's files live)
- Attention template binding (how templates attach to stacks)
- Cross-stack visibility rules (who can see whose state)

### What FMWK-010 Does NOT Govern

- What HO2/HO1 cognitive processes do (HANDOFF-14/15)
- Tier boundary enforcement (FMWK-009 — FMWK-010 defers to it)
- WO schema or lifecycle (FMWK-008)
- Prompt contract schema (FMWK-011)
- How stacks communicate across agent classes (not needed — stacks are isolated by design)

### Non-Negotiable Rules From v2

From v2 §11 (Cognitive Stacks — Shared Code, Isolated State):

**What's shared** (infrastructure):
- HO3 governance layer (principles, north stars — same for all)
- KERNEL.syntactic (LLM Gateway, gates, integrity, auth)
- KERNEL.semantic (meta agent reads all stacks)
- Meta Learning Ledger (cross-cutting)

**What's isolated** (per stack):
- HO2m session state
- HO1m execution traces
- Attention templates
- Framework configuration
- Work order context

**Build implication** from v2 §11: "HO2 cognitive process is written ONCE as generic code. Each agent class instantiates its own copy with different config. Like a class vs instance."

From v2 §10 Invariant #7: "Separate cognitive stacks per agent class. Each agent class (ADMIN, each RESIDENT) instantiates its own HO2 + HO1 cognitive processes. Shared code, isolated state. Different frameworks, different session state, different attention behavior. They share HO3 governance, KERNEL.syntactic, KERNEL.semantic, and the Meta Learning Ledger."

### Adversarial Analysis: Isolation Granularity

**Hurdles**: Shared kernel code (LLM Gateway, ledger_client, schema_validator) must be accessible from all stacks without breaking tier boundaries. If HO1 is isolated per stack but all HO1 instances call the same LLM Gateway, the "isolation" is state isolation, not code isolation. This distinction must be crystal clear.

**Not Enough**: Without explicit shared/isolated boundaries, the first RESIDENT stack will accidentally share HO2m state with ADMIN. Session state bleeds across agent classes. Attention templates designed for ADMIN get applied to RESIDENT — wrong context, wrong behavior.

**Too Much**: Over-specifying the factory model constrains how HANDOFF-15 implements HO2 Supervisor. The framework should define WHAT is shared vs isolated, not HOW the factory creates instances. Implementation details belong to the package.

**Synthesis**: Define the shared/isolated boundary as a governance rule (lists of what goes where). Define the instantiation model as "factory pattern" without prescribing the factory's API. Leave runtime implementation to HANDOFF-15.

---

## 4. Implementation Steps

1. **Read v2 Sections 3, 11, 14** — three things per tier, shared/isolated state, concrete flows
2. **Read v2 Section 10** — invariant #7 (separate stacks)
3. **Read `attention_template.schema.json`** — understand per-agent template structure
4. **Read `layout.json`** — understand tier directory structure
5. **Read FMWK-009 handoff spec** — understand tier boundary dependency
6. **Create directory** `_staging/FMWK-010_Cognitive_Stack/`
7. **Write `cognitive_stack.md`** with these sections:
   - Purpose, Scope
   - 1. Shared Infrastructure (enumerate all shared components per v2 §11)
   - 2. Isolated State (enumerate all per-stack state per v2 §11)
   - 3. Stack Instantiation Model (factory pattern: generic code + per-agent config)
   - 4. Session State Structure (HO2m: what fields, session ID, history, arbitration outcomes)
   - 5. Directory Isolation (where each stack's files live in the filesystem)
   - 6. Attention Template Binding (how templates attach to stacks via `applies_to` selector)
   - 7. Cross-Stack Visibility (ADMIN cannot see RESIDENT state; meta agent reads all)
   - 8. Stack Lifecycle (creation at session start, teardown at session end)
   - 9. Implementation Mapping (which packages implement these rules)
   - 10. Relationship to Tier Boundaries (how FMWK-010 and FMWK-009 interact)
   - Conformance, Status
8. **Write `manifest.yaml`** — framework manifest with invariants
9. **Write `_staging/RESULTS_FMWK010.md`** — verification results

---

## 5. Package Plan

FMWK-010 is a governance framework, not a code package. It stays standalone in `_staging/FMWK-010_Cognitive_Stack/` until PKG-HO2-SUPERVISOR-001 (HANDOFF-15) implements the factory pattern it describes.

No tar archive. No install step. No pytest.

---

## 6. Test Plan — Document Verification Checklist

| # | Check | Method | Pass Criteria |
|---|-------|--------|---------------|
| 1 | Shared infrastructure list matches v2 §11 | Compare Section 1 to v2 | HO3 governance, KERNEL.syntactic, KERNEL.semantic, Meta Learning Ledger |
| 2 | Isolated state list matches v2 §11 | Compare Section 2 to v2 | HO2m, HO1m, attention templates, framework config, WO context |
| 3 | Factory pattern described | Read Section 3 | Generic code + per-agent config concept documented |
| 4 | Session state structure defined | Read Section 4 | HO2m fields enumerated |
| 5 | Directory isolation rules specified | Read Section 5 | Per-stack filesystem paths defined |
| 6 | Attention template binding uses `applies_to` | Read Section 6 | References `attention_template.schema.json` applies_to selector |
| 7 | Cross-stack visibility correct | Read Section 7 | ADMIN ≠ RESIDENT state; meta agent reads all |
| 8 | All v2 references accurate | Cross-check v2 sections | Section titles match v2 headings |
| 9 | No schema/code modifications | Check staged packages | No files changed |
| 10 | manifest.yaml valid YAML | Parse | No syntax errors |
| 11 | Invariant #7 fully covered | Read framework | Separate stacks per agent class enforced |
| 12 | Defers to FMWK-009 on tier boundaries | Read Section 10 | Explicit deference statement |
| 13 | Concrete flows referenced | Read framework | At least one v2 §14 flow cited as example |

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| v2 Section 11: Cognitive Stacks | `_staging/architecture/KERNEL_PHASE_2_v2.md` §11 | Primary source — shared vs isolated |
| v2 Section 3: Three Things Per Tier | `_staging/architecture/KERNEL_PHASE_2_v2.md` §3 | Memory/Process/Layout distinction |
| v2 Section 14: Concrete Flows | `_staging/architecture/KERNEL_PHASE_2_v2.md` §14 | ADMIN and DoPeJar stack examples |
| v2 Section 10: Invariants | `_staging/architecture/KERNEL_PHASE_2_v2.md` §10 | Invariant #7 |
| v2 Section 4: Agent Classes | `_staging/architecture/KERNEL_PHASE_2_v2.md` §4 | Agent class definitions |
| Attention template schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/attention_template.schema.json` | `applies_to` selector for per-agent binding |
| Layout config | `_staging/PKG-LAYOUT-002/HOT/config/layout.json` | Tier directory structure |
| FMWK-008 manifest | `_staging/FMWK-008_Work_Order_Protocol/manifest.yaml` | Manifest format exemplar |
| FMWK-009 handoff spec | `_staging/handoffs/BUILDER_HANDOFF_FMWK009_tier_boundary.md` | Tier boundary dependency |
| FMWK-000 (Governance) | Installed framework | Format exemplar for document structure |

---

## 8. End-to-End Verification

1. **Markdown structure check**: Confirm Purpose, Scope, 10 numbered sections, Conformance, Status all present.
2. **YAML lint**: Parse `manifest.yaml` — no syntax errors.
3. **v2 cross-reference**: For each `v2 Section N` reference, verify section number and title match actual v2.
4. **Schema/code integrity**: Confirm no files in staged packages were modified.
5. **Shared/isolated consistency**: Verify the shared list in Section 1 and isolated list in Section 2 are mutually exclusive and collectively exhaustive (nothing missing, nothing duplicated).

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `cognitive_stack.md` | `_staging/FMWK-010_Cognitive_Stack/` | CREATE — the framework standard |
| `manifest.yaml` | `_staging/FMWK-010_Cognitive_Stack/` | CREATE — framework manifest |
| `RESULTS_FMWK010.md` | `_staging/` | CREATE — verification results |

---

## 10. Design Principles

1. **Shared code, isolated state.** The Kitchener loop code is written once. Each agent class gets its own instance with its own state. Like a class vs instance.
2. **Isolation is state isolation, not code isolation.** All stacks call the same LLM Gateway, the same ledger_client. What's isolated is the session state, traces, templates, and context.
3. **The framework defines WHAT, not HOW.** FMWK-010 lists what's shared and what's isolated. The factory implementation is HANDOFF-15's job.
4. **Attention templates are the per-stack config.** Each agent class gets different templates via the `applies_to` selector. This is how the same HO2 code produces different behavior for ADMIN vs RESIDENT.
5. **FMWK-010 defers to FMWK-009 on tier boundary definitions.** If FMWK-010 discovers a gap in FMWK-009's tier rules, flag it — don't fill it.
6. **Cross-stack visibility follows v2 rules.** ADMIN cannot see RESIDENT state. RESIDENT cannot see ADMIN state. Only KERNEL.semantic (meta agent) reads across all stacks.
