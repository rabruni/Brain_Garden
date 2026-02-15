# Builder Handoff: FMWK-009 — Tier Boundary

## 1. Mission

Create the FMWK-009 Tier Boundary governance framework. This framework formalizes the visibility/syscall model from KERNEL_PHASE_2_v2.md Section 5: "Lower tiers CANNOT read higher tier state. Lower tiers CAN call higher tier services (syscalls)."

Without this framework, tier isolation is aspirational — any code can import any module. FMWK-009 makes "reading up = forbidden, calling through = allowed" a governed, enforceable rule.

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/FMWK-009_Tier_Boundary/`.** Create this directory. No files outside it except the results file.
2. **v2 is design authority.** Every claim in the framework MUST trace to a specific section of `_staging/architecture/KERNEL_PHASE_2_v2.md`.
3. **Reference existing code as-is.** `authz.py` from PKG-KERNEL-001 defines role-based access. FMWK-009 adds tier as a second dimension. Do NOT modify existing code — describe the extension rules.
4. **Depends on FMWK-008A metadata key standard.** Tier-tagged ledger entries use the metadata convention from FMWK-008A. Reference it, don't reinvent it.
5. **manifest.yaml required.** Create following the format in `_staging/FMWK-008_Work_Order_Protocol/manifest.yaml`.
6. **Results file required.** When finished, write `_staging/RESULTS_FMWK009.md` with section-by-section verification results.
7. **Use terminology from v2.** "Cognitive process" is THE term for tier agents. HOT and HO3 are synonyms. Use HOT in filesystem paths, HO3 in architectural discussion.

---

## 3. Architecture / Design

### What FMWK-009 Governs

FMWK-009 is the governance standard for tier boundaries — the rules that enforce isolation between HO1, HO2, and HO3/HOT. It defines:
- Visibility matrix (what each tier can see)
- Syscall definitions (enumerated services a lower tier can invoke)
- Import restrictions (what code each tier directory may reference)
- Budget enforcement chain (HO3 → HO2 → HO1 token budget hierarchy)
- Tier-tagged ledger entries (how `scope.tier` is set on every ledger write)

### What FMWK-009 Does NOT Govern

- Work order schema or lifecycle (FMWK-008)
- Cognitive stack instantiation or isolation (FMWK-010)
- Prompt contract schema (FMWK-011)
- Auth/authz implementation (existing PKG-KERNEL-001 `authz.py`)
- Budget calculation or tracking (existing PKG-TOKEN-BUDGETER-001)

### Non-Negotiable Rules From v2

From v2 §5 (The Visibility / Syscall Model):
- "Lower tiers CANNOT read higher tier state. Lower tiers CAN call higher tier services (syscalls)."
- HO3 sees: All (HO3m + HO2m + HO1m + Meta ledger)
- HO2 sees: HO2m + HO1m. Receives constraints from HO3 (pushed down).
- HO1 sees: Only its work order context. Receives instructions from HO2 (dispatched).
- "Reading up is forbidden. Calling through is allowed."

From v2 §10 Invariant #1: "No direct LLM calls. Every LLM call flows through the LLM Gateway (KERNEL.syntactic)."

From v2 §10 Invariant #5: "Budgets are enforced, not advisory. Token limits per work order."

### Adversarial Analysis: Enforcement Granularity

**Hurdles**: Python has no module-level import restrictions. A file in `HO1/` can `import` anything from `HOT/` or `HO2/` — the language doesn't prevent it. Enforcement must be gate checks + convention, not runtime import blocking.

**Not Enough**: Without enforcement, tier boundaries are documentation-only. A builder agent writing HO1 code could accidentally import HO2's session state, breaking isolation. The first violation becomes precedent for the second.

**Too Much**: Building a custom import hook or AST-based import scanner is over-engineering for the current codebase. The enforcement mechanism should match the system's maturity.

**Synthesis**: Three-layer enforcement: (1) Path convention — code lives where it belongs (`HO1/`, `HO2/`, `HOT/`). (2) Gate check — `gate_check.py` verifies import statements in staged packages don't cross tier boundaries upward. (3) Runtime assertion — syscall wrappers validate caller tier before executing. Start with (1) + (2), add (3) when runtime exists.

---

## 4. Implementation Steps

1. **Read v2 Sections 5, 12** — visibility/syscall model, capabilities
2. **Read v2 Section 10** — invariants #1 (no direct LLM calls), #5 (budgets enforced)
3. **Read `authz.py`** — understand existing role-based access patterns
4. **Read `ledger_entry_metadata.schema.json`** — understand `scope.tier` field
5. **Read FMWK-008A handoff spec** — understand metadata key standard dependency
6. **Create directory** `_staging/FMWK-009_Tier_Boundary/`
7. **Write `tier_boundary.md`** with these sections:
   - Purpose, Scope
   - 1. Visibility Matrix (reproduce v2 §5 table with enforcement rules)
   - 2. Syscall Definitions (enumerate each: `LLM_GATEWAY_CALL`, `LEDGER_WRITE`, `LEDGER_READ`, `SCHEMA_VALIDATE`, `BUDGET_CHECK`, `BUDGET_DEBIT`, `POLICY_LOOKUP`)
   - 3. Import Restrictions (per-tier: what `HO1/` code may import, what `HO2/` may import, what `HOT/` may import)
   - 4. Budget Enforcement Chain (HO3 sets session ceiling → HO2 allocates per-WO → HO1 debits per-call)
   - 5. Tier-Tagged Ledger Entries (how `scope.tier` field is set, references FMWK-008A metadata standard)
   - 6. Enforcement Mechanism (path convention + gate check + future runtime assertion)
   - 7. Capability Ceilings (per agent class, from v2 §4 capability matrix)
   - 8. Cross-Tier Communication Patterns (syscall-only, pushed-down constraints, no reading up)
   - 9. Implementation Mapping (which packages enforce these rules)
   - 10. Future Extensions (import hook, runtime caller validation)
   - Conformance, Status
8. **Write `manifest.yaml`** — framework manifest with invariants
9. **Write `_staging/RESULTS_FMWK009.md`** — verification results

---

## 5. Package Plan

FMWK-009 is a governance framework, not a code package. It stays standalone in `_staging/FMWK-009_Tier_Boundary/` until PKG-HO1-EXECUTOR-001 (HANDOFF-14) and PKG-HO2-SUPERVISOR-001 (HANDOFF-15) enforce its rules at runtime.

No tar archive. No install step. No pytest.

---

## 6. Test Plan — Document Verification Checklist

| # | Check | Method | Pass Criteria |
|---|-------|--------|---------------|
| 1 | Visibility matrix matches v2 §5 | Compare Section 1 to v2 table | All 3 tiers match: what they see, receive, and can call |
| 2 | Every syscall enumerated | Read Section 2 | At least: LLM_GATEWAY_CALL, LEDGER_WRITE, LEDGER_READ, SCHEMA_VALIDATE, BUDGET_CHECK, BUDGET_DEBIT |
| 3 | Import restrictions per tier | Read Section 3 | HO1, HO2, HOT each have explicit allowed/forbidden import patterns |
| 4 | Budget chain documented | Read Section 4 | HO3→HO2→HO1 hierarchy, exhaustion behavior at each level |
| 5 | `scope.tier` convention defined | Read Section 5 | Matches `ledger_entry_metadata.schema.json` scope.tier enum: `hot`, `ho2`, `ho1` |
| 6 | Enforcement mechanism specified | Read Section 6 | At least path convention + gate check described |
| 7 | Capability ceilings from v2 §4 | Read Section 7 | ADMIN capabilities (CAP_READ_ALL, CAP_AUDIT_WRITE) + RESIDENT restrictions |
| 8 | All v2 references accurate | Cross-check v2 sections | Section titles match v2 headings |
| 9 | References FMWK-008A metadata standard | Read Section 5 | Explicit reference to FMWK-008A for relational metadata keys |
| 10 | No code modifications | Check `_staging/PKG-KERNEL-001/` | No files changed |
| 11 | manifest.yaml valid YAML | Parse | No syntax errors |
| 12 | Invariant #1 fully covered | Read framework | No direct LLM calls enforced |
| 13 | Invariant #5 addressed | Read Section 4 | Budget enforcement chain documented |

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| v2 Section 5: Visibility / Syscall | `_staging/architecture/KERNEL_PHASE_2_v2.md` §5 | Primary source — visibility table and principle |
| v2 Section 12: CS Kernel Theory | `_staging/architecture/KERNEL_PHASE_2_v2.md` §12 | Capabilities model |
| v2 Section 4: Agent Classes | `_staging/architecture/KERNEL_PHASE_2_v2.md` §4 | ADMIN capability matrix |
| v2 Section 10: Invariants | `_staging/architecture/KERNEL_PHASE_2_v2.md` §10 | Invariants #1, #5 |
| v2 Section 8: Infrastructure | `_staging/architecture/KERNEL_PHASE_2_v2.md` §8 | LLM Gateway, Token Budgeter as KERNEL.syntactic |
| authz.py | `_staging/PKG-KERNEL-001/HOT/kernel/authz.py` | Existing role-based access (reference, don't modify) |
| Ledger metadata schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/ledger_entry_metadata.schema.json` | `scope.tier` field (reference, don't modify) |
| layout.json | `_staging/PKG-LAYOUT-002/HOT/config/layout.json` | Tier directory structure |
| FMWK-008 manifest | `_staging/FMWK-008_Work_Order_Protocol/manifest.yaml` | Manifest format exemplar |
| FMWK-008A handoff spec | `_staging/handoffs/BUILDER_HANDOFF_FMWK008A_wo_protocol_update.md` | Metadata key standard dependency |

---

## 8. End-to-End Verification

1. **Markdown structure check**: Confirm Purpose, Scope, 10 numbered sections, Conformance, Status all present.
2. **YAML lint**: Parse `manifest.yaml` — no syntax errors.
3. **v2 cross-reference**: For each `v2 Section N` reference, verify section number and title match actual v2.
4. **Code integrity**: Confirm no files in `_staging/PKG-KERNEL-001/` or `_staging/PKG-PHASE2-SCHEMAS-001/` were modified.
5. **Visibility matrix consistency**: Verify the framework's visibility table exactly matches v2 §5.

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `tier_boundary.md` | `_staging/FMWK-009_Tier_Boundary/` | CREATE — the framework standard |
| `manifest.yaml` | `_staging/FMWK-009_Tier_Boundary/` | CREATE — framework manifest |
| `RESULTS_FMWK009.md` | `_staging/` | CREATE — verification results |

---

## 10. Design Principles

1. **Reading up = forbidden. Calling through = allowed.** This is THE principle. Every rule in the framework derives from it.
2. **Syscalls are the only crossing mechanism.** Lower tiers invoke higher-tier services through enumerated, logged syscalls. No backdoor imports.
3. **Path IS boundary.** Code in `HO1/` belongs to HO1. Code in `HO2/` belongs to HO2. Directory structure enforces tier membership.
4. **Gate checks enforce what language can't.** Python doesn't prevent cross-tier imports. Gate checks at package install time do.
5. **Tier adds a second dimension to access control.** `authz.py` has roles (admin, maintainer, auditor, reader). FMWK-009 adds tier (HO1, HO2, HOT). Both must be satisfied.
6. **FMWK-009 defers to FMWK-008A on metadata conventions.** Tier-tagged ledger entries use the `scope.tier` field and `relational.*` keys defined by FMWK-008A. If FMWK-010 discovers a gap in FMWK-009's tier rules, it flags it — doesn't fill it.
