# RESULTS_FMWK009: Tier Boundary Framework Verification

**Framework**: FMWK-009 Tier Boundary
**Date**: 2026-02-14
**Verifier**: Builder agent (FMWK-009)

---

## Section-by-Section Verification

### Check 1: Visibility matrix matches v2 Section 5

**Method**: Compare `tier_boundary.md` Section 1 to v2 Section 5: The Visibility / Syscall Model.

**Result**: PASS

The visibility table in Section 1 reproduces the v2 Section 5 table exactly:

| Tier | Sees | Receives From Above | Calls (syscalls) |
|------|------|---------------------|------------------|
| HO3 | All: HO3m + HO2m + HO1m + Meta ledger | -- | -- |
| HO2 | HO2m + HO1m | Constraints from HO3 (pushed down) | HO3 services (e.g., policy lookup) |
| HO1 | Only its work order context | Instructions from HO2 (dispatched) | HOT infrastructure: LLM Gateway, provider, ledger client |

Additionally, a Ledger Visibility sub-table maps each ledger file to per-tier access levels, extending v2's principle into actionable rules.

---

### Check 2: Every syscall enumerated

**Method**: Read Section 2 for the syscall table.

**Result**: PASS

Seven syscalls enumerated:

1. `LLM_GATEWAY_CALL` -- HO1 to HOT
2. `LEDGER_WRITE` -- HO1/HO2 to HOT
3. `LEDGER_READ` -- HO1/HO2 to HOT
4. `SCHEMA_VALIDATE` -- HO1/HO2 to HOT
5. `BUDGET_CHECK` -- HO1/HO2 to HOT
6. `BUDGET_DEBIT` -- HO1 to HOT
7. `POLICY_LOOKUP` -- HO2 to HOT/HO3

Meets the minimum requirement of at least 6. Each syscall includes caller, target, service location, and description. Rule 5 ("no undeclared syscalls") ensures the table remains authoritative.

---

### Check 3: Import restrictions per tier

**Method**: Read Section 3 for per-tier import tables.

**Result**: PASS

Three separate tables define allowed and forbidden imports for:
- HO1 (`HO1/`): May import stdlib, `HOT/kernel/` syscall interfaces, own packages. May NOT import `HO2.*`, `HOT/ledger/`, `HOT/registries/`, `HOT/config/`.
- HO2 (`HO2/`): May import stdlib, `HOT/kernel/` syscalls, `HO1/` ledger via LEDGER_READ, own packages, own HO2m ledger. May NOT import `HOT/ledger/governance.jsonl`, `HOT/config/` directly.
- HOT (`HOT/`): No restrictions on downward reads. KERNEL.syntactic code must not make cognitive judgments.

---

### Check 4: Budget chain documented

**Method**: Read Section 4 for HO3 to HO2 to HO1 hierarchy.

**Result**: PASS

Budget hierarchy documented as:
- HO3 sets session ceiling (configured per agent class)
- HO2 allocates per-WO from session budget
- HO1 debits per-call via BUDGET_DEBIT syscall

Enforcement rules table maps each rule to its enforcing tier and v2 source. Budget exhaustion cascade documented with degradation behavior referencing v2 Section 1.

---

### Check 5: `scope.tier` convention defined

**Method**: Read Section 5 and verify it matches `ledger_entry_metadata.schema.json` enum values.

**Result**: PASS

- References `scope.tier` field from `ledger_entry_metadata.schema.json` (PKG-PHASE2-SCHEMAS-001)
- Enum values match: `"hot"`, `"ho2"`, `"ho1"`
- Tier assignment rules map originating tier to `scope.tier` value with concrete event type examples
- Setting convention covers cognitive process entries, syscall-originated entries, and KERNEL.syntactic entries
- References FMWK-008 Section 5b metadata key standard for relational fields

---

### Check 6: Enforcement mechanism specified

**Method**: Read Section 6 for at least path convention + gate check.

**Result**: PASS

Three-layer enforcement documented:
1. **Path convention (Active)**: Directory = tier. Layout reference to `layout.json`.
2. **Gate check (Active)**: Static analysis of import statements at package install time. Table of what it catches and what it allows.
3. **Runtime assertion (Future)**: Caller tier validation in syscall wrappers. Deferred to HANDOFF-14/15.

---

### Check 7: Capability ceilings from v2 Section 4

**Method**: Read Section 7 for ADMIN and RESIDENT capabilities.

**Result**: PASS

Four agent class capability tables:
- **ADMIN**: CAP_READ_ALL, CAP_AUDIT_WRITE, L-OBSERVE, L-ANNOTATE. Restrictions listed (cannot modify kernel code, cannot interact with RESIDENTs directly, etc.).
- **RESIDENT**: Own namespace only, no cross-stack access.
- **KERNEL.syntactic**: Infrastructure services, no cognitive judgment.
- **KERNEL.semantic**: Cross-cutting read, meta ledger write.

Capability + Tier = Access Decision formula documented: both `role_check` (authz.py) and `tier_check` (FMWK-009) must pass.

---

### Check 8: All v2 references accurate

**Method**: Cross-check each `v2 Section N` reference against actual KERNEL_PHASE_2_v2.md headings.

| Reference Used | Actual v2 Heading | Match? |
|----------------|-------------------|--------|
| v2 Section 1: Grounding Model: The Kitchener Orchestration Stack | "1. Grounding Model: The Kitchener Orchestration Stack" | YES |
| v2 Section 3: Three Things Per Tier | "3. Three Things Per Tier" | YES |
| v2 Section 4: Agent Classes | "4. Agent Classes" | YES |
| v2 Section 5: The Visibility / Syscall Model | "5. The Visibility / Syscall Model" | YES |
| v2 Section 6: Memory Architecture | "6. Memory Architecture" | YES |
| v2 Section 8: Infrastructure Components | "8. Infrastructure Components" | YES |
| v2 Section 9: Learning Model -- Three Timescales | "9. Learning Model -- Three Timescales" | YES |
| v2 Section 10: Architectural Invariants | "10. Architectural Invariants" | YES |
| v2 Section 11: Cognitive Stacks | "11. Cognitive Stacks -- Shared Code, Isolated State" | YES |
| v2 Section 12: Design Principles From CS Kernel Theory | "12. Design Principles From CS Kernel Theory" | YES |
| v2 Section 18: Critical Path -- What's Next | "18. Critical Path -- What's Next" | YES |

**Result**: PASS -- all 11 v2 section references verified.

---

### Check 9: References FMWK-008A metadata standard

**Method**: Read Section 5 for explicit reference to FMWK-008 Section 5b.

**Result**: PASS

Section 5 states: "FMWK-008 Section 5b defines the metadata key standard for relational fields (`metadata.relational.*`) and provenance fields (`metadata.provenance.*`). FMWK-009 adds the requirement that `metadata.scope.tier` is populated on every entry."

Tier-scoped graph traversal patterns documented using both `scope.tier` and `relational.*` fields together.

---

### Check 10: No code modifications

**Method**: Verify no files in `_staging/PKG-KERNEL-001/` or `_staging/PKG-PHASE2-SCHEMAS-001/` were modified.

**Result**: PASS

No files modified. Framework references existing code as-is:
- `PKG-KERNEL-001/HOT/kernel/authz.py` -- referenced in Sections 7 and Conformance
- `PKG-PHASE2-SCHEMAS-001/HOT/schemas/ledger_entry_metadata.schema.json` -- referenced in Section 5
- `PKG-LAYOUT-002/HOT/config/layout.json` -- referenced in Section 6

---

### Check 11: manifest.yaml valid YAML

**Method**: Parse manifest.yaml for syntax errors.

**Result**: PASS

Manifest contains all required fields:
- `framework_id`: FMWK-009
- `title`: Tier Boundary -- Visibility, Syscalls, and Isolation
- `version`: "1.0.0"
- `status`: draft
- `ring`: kernel
- `plane_id`: hot
- `created_at`: ISO 8601
- `assets`: [tier_boundary.md]
- `expected_specs`: [SPEC-TIER-001]
- `invariants`: 11 invariants (all MUST or MUST NOT)
- `path_authorizations`: 7 paths
- `required_gates`: [G0, G1, G2, G6]

Format follows FMWK-008 manifest exemplar.

---

### Check 12: Invariant #1 fully covered

**Method**: Verify that v2 Invariant #1 ("No direct LLM calls") is enforced in the framework.

**Result**: PASS

- Section 2 (Syscall Definitions): `LLM_GATEWAY_CALL` syscall explicitly states "All LLM calls MUST flow through this syscall (v2 Section 10: Architectural Invariants, Invariant #1)."
- Section 8 (Cross-Tier Communication Patterns): Forbidden Patterns table includes "Direct LLM call bypassing Gateway" with source "v2 Section 10: Invariant #1."
- manifest.yaml invariant: "Every LLM call MUST flow through the LLM_GATEWAY_CALL syscall (v2 Invariant #1)"

---

### Check 13: Invariant #5 addressed

**Method**: Read Section 4 for budget enforcement chain.

**Result**: PASS

- Section 4 (Budget Enforcement Chain): Full hierarchy documented (HO3 session ceiling, HO2 per-WO allocation, HO1 per-call debit).
- Enforcement rules table maps each budget rule to its v2 source (Invariant #5).
- Budget exhaustion cascade documents degradation behavior.
- manifest.yaml invariant: "Token budgets MUST be enforced at every tier level -- session ceiling (HO3), per-WO allocation (HO2), per-call debit (HO1) (v2 Invariant #5)"

---

## End-to-End Verification

### 1. Markdown structure check

PASS -- Document contains:
- Purpose, Scope (preamble)
- 10 numbered sections (1-10)
- Conformance
- Status

### 2. YAML lint

PASS -- manifest.yaml parsed without errors. All fields present.

### 3. v2 cross-reference

PASS -- All 11 v2 section references verified against actual headings (see Check 8).

### 4. Code integrity

PASS -- No files in PKG-KERNEL-001, PKG-PHASE2-SCHEMAS-001, or PKG-LAYOUT-002 were modified.

### 5. Visibility matrix consistency

PASS -- Framework Section 1 visibility table exactly matches v2 Section 5 table.

---

## Summary

| Check | Result |
|-------|--------|
| 1. Visibility matrix | PASS |
| 2. Syscalls enumerated | PASS |
| 3. Import restrictions | PASS |
| 4. Budget chain | PASS |
| 5. scope.tier convention | PASS |
| 6. Enforcement mechanism | PASS |
| 7. Capability ceilings | PASS |
| 8. v2 references accurate | PASS |
| 9. FMWK-008A reference | PASS |
| 10. No code modifications | PASS |
| 11. manifest.yaml valid | PASS |
| 12. Invariant #1 covered | PASS |
| 13. Invariant #5 addressed | PASS |

**Overall: 13/13 PASS**

---

## Files Created

| File | Location |
|------|----------|
| `tier_boundary.md` | `_staging/FMWK-009_Tier_Boundary/tier_boundary.md` |
| `manifest.yaml` | `_staging/FMWK-009_Tier_Boundary/manifest.yaml` |
| `RESULTS_FMWK009.md` | `_staging/RESULTS_FMWK009.md` |
