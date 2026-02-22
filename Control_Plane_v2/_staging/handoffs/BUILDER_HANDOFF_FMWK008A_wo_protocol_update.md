# Builder Handoff: FMWK-008A — Work Order Protocol Update

## 1. Mission

Update the existing FMWK-008 Work Order Protocol draft (`_staging/FMWK-008_Work_Order_Protocol/work_order_protocol.md`) to align with the Modified Kitchener dispatch model defined in KERNEL_PHASE_2_v2.md. This is the governance foundation — every work order, every ledger entry, every trace in the system follows what FMWK-008 defines.

Three additions are required: (a) Kitchener step alignment for every WO type and lifecycle state, (b) the hash-anchored trace model linking governance summaries to detailed trace files, and (c) the metadata key standard defining how relational/graph fields appear in all ledger entries.

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/FMWK-008_Work_Order_Protocol/`.** No files outside this directory. No writes to the conflated repo tree.
2. **This is a draft update, not a file replacement.** FMWK-008 is `status: draft`. Modify the existing `work_order_protocol.md` in-place. Do not create a new file with a different name.
3. **v2 is design authority.** Every claim in the updated framework MUST trace to a specific section of `_staging/architecture/KERNEL_PHASE_2_v2.md`. If v2 doesn't say it, the framework doesn't claim it.
4. **Reference existing schemas as-is.** The `ledger_entry_metadata.schema.json` defines relational keys under `relational.parent_event_id`, `relational.root_event_id`, `relational.related_artifacts`. Do NOT redefine these. If the framework needs schema changes, document as a "Schema Extension Proposal" section — do NOT modify schema files directly.
5. **manifest.yaml must be updated.** After updating the framework document, update `manifest.yaml` to reflect new invariants and assets.
6. **Results file required.** When finished, write `_staging/RESULTS_FMWK008A.md` with section-by-section verification results.

---

## 3. Architecture / Design

### What FMWK-008 Governs

FMWK-008 is the governance standard for work orders — the atomic unit of cognitive dispatch. It defines:
- WO schema (identity, types, lifecycle, input/output)
- WO lifecycle state machine (planned → dispatched → executing → completed/failed)
- Ledger recording rules (what events, which ledger, what metadata)
- Validation rules (planning time, execution time, quality gate)
- Budget model (session → WO → per-call hierarchy)
- Orchestration patterns (pipeline, future: parallel, voting, hierarchical)

### What FMWK-008 Does NOT Govern

- Prompt contract schema or lifecycle (FMWK-011)
- Tier boundary enforcement or import restrictions (FMWK-009)
- Cognitive stack instantiation or isolation rules (FMWK-010)
- Runtime WO code (PKG-WORK-ORDER-001, HANDOFF-13)

### What's Being Added (3 additions)

**Addition 1: Kitchener Step Alignment**

Every WO type maps to a Kitchener step. The lifecycle table gains a "Kitchener Step" column. This makes explicit which cognitive tier controls each state transition.

Non-negotiable rules from v2 Section 1:
- The canonical dispatch loop is 5-step: Ideation(L3) → Scoping(L2) → Execution(L1) → Verification(L2) → Synthesis(L3)
- Current build implements Steps 2→3→4 (HO3 bookends deferred)
- Step 2 (Scoping): HO2 creates WOs with acceptance criteria
- Step 3 (Execution): HO1 executes WOs via LLM Gateway
- Step 4 (Verification): HO2 checks output against Step 2 criteria

**Addition 2: Hash-Anchored Trace Model**

Two-tier recording: governance ledger (HO2m) gets summaries + `trace_hash`, detail lives in trace files (HO1m). This prevents governance ledger bloat while maintaining verifiability.

From v2 Section 18 open design question: "governance ledger gets summaries + trace_hash, detail in trace files."

**Addition 3: Metadata Key Standard**

Define how relational/graph metadata fields appear in all ledger entries. Uses the existing `ledger_entry_metadata.schema.json` structure:
- `relational.parent_event_id` — direct parent entry
- `relational.root_event_id` — root of causal chain
- `relational.related_artifacts` — array of `{type, id}` references

From v2 Section 6: "Meta ledger is graph-indexed. Enables relationship-based retrieval (Graph RAG)."

### Adversarial Analysis: Hash-Anchored Trace

**Hurdles**: Two-ledger write coordination. If HO2 writes a summary with `trace_hash` but HO1's trace file is corrupted or missing, the hash becomes unverifiable. Mitigation: trace_hash is computed AFTER HO1 completes, so HO2 reads the written trace before computing the hash.

**Not Enough**: Without the trace hash, governance summaries become unverifiable claims. "HO1 completed WO-001 successfully" with no way to prove what actually happened. The hash is the integrity link.

**Too Much**: Could over-specify the hash algorithm, trace file format, and coordination protocol. Risk: locking in decisions before PKG-WORK-ORDER-001 (HANDOFF-13) tests them. Mitigation: specify the principle (governance summary + trace_hash) and the metadata key (`context_fingerprint.context_hash`), leave implementation details to the consuming package.

**Synthesis**: Specify the two-tier model and the hash linkage. Leave coordination protocol details to HANDOFF-13.

---

## 4. Implementation Steps

1. **Read v2 Sections 1, 6, 17** — understand the Kitchener loop, memory architecture, and WO schema reference
2. **Read the existing FMWK-008 draft** — understand current 10-section structure (298 lines)
3. **Read `ledger_entry_metadata.schema.json`** — understand existing relational key structure
4. **Add Kitchener step column to Section 2 (Work Order Types)** — map each WO type to its Kitchener step
5. **Add Kitchener step column to Section 3 (Lifecycle)** — map each state transition to the tier that controls it
6. **Add Section 5a: Hash-Anchored Trace Model** — insert after Section 5 (Ledger Recording), before Section 6 (Validation Rules). Define: governance summary in HO2m, trace detail in HO1m, `trace_hash` linking them.
7. **Add Section 5b: Metadata Key Standard** — define the relational key convention for all ledger entries. Reference `ledger_entry_metadata.schema.json` field paths.
8. **Update Section 5 (Ledger Recording)** — add `trace_hash` to the HO2 ledger event fields. Add `relational.*` keys to both HO1 and HO2 event types.
9. **Update manifest.yaml** — add new invariants for trace hash and metadata keys. Bump version to 1.1.0.
10. **Write `_staging/RESULTS_FMWK008A.md`** — verify each section against v2, check manifest validity, confirm no schema modifications.

---

## 5. Package Plan

FMWK-008 is a governance framework, not a code package. It stays standalone in `_staging/FMWK-008_Work_Order_Protocol/` until PKG-WORK-ORDER-001 (HANDOFF-13) absorbs it as its governing framework.

No tar archive. No install step. No pytest.

---

## 6. Test Plan — Document Verification Checklist

| # | Check | Method | Pass Criteria |
|---|-------|--------|---------------|
| 1 | Every WO type has a Kitchener step column | Read Section 2 table | All 4 types map to a step |
| 2 | Every lifecycle state has a controlling tier | Read Section 3 table | All 5 states assigned HO1 or HO2 |
| 3 | Section 5a defines hash-anchored trace | Read Section 5a | Two-tier model described, trace_hash field defined |
| 4 | Section 5b defines metadata key standard | Read Section 5b | `relational.*` keys documented with field paths |
| 5 | Section 5 updated with trace_hash | Read Section 5 event tables | HO2 events include trace_hash field |
| 6 | Section 5 updated with relational keys | Read Section 5 event tables | Both HO1 and HO2 events reference relational metadata |
| 7 | All v2 references accurate | Cross-check each `v2 Section N` ref | Section titles match v2 headings |
| 8 | No schema modifications | Check `_staging/PKG-PHASE2-SCHEMAS-001/` | No files changed |
| 9 | manifest.yaml valid YAML | Parse with YAML parser | No syntax errors |
| 10 | manifest.yaml invariants cover new additions | Read manifest invariants | Trace hash + metadata key invariants present |
| 11 | Invariant coverage: #1 (no direct LLM calls) | Implied by WO types requiring Gateway | WO type rules reference LLM Gateway |
| 12 | Invariant coverage: #2 (every agent under WO) | Core framework purpose | Explicit in Section 1/Purpose |
| 13 | Invariant coverage: #5 (budgets enforced) | Section 7 budget model | Budget exhaustion rules unchanged |

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| v2 Section 1: Kitchener loop | `_staging/architecture/KERNEL_PHASE_2_v2.md` §1 | Canonical dispatch loop, step definitions |
| v2 Section 6: Memory Architecture | `_staging/architecture/KERNEL_PHASE_2_v2.md` §6 | Four ledgers, memory principles, graph indexing |
| v2 Section 10: Invariants | `_staging/architecture/KERNEL_PHASE_2_v2.md` §10 | 7 architectural invariants |
| v2 Section 17: WO Schema | `_staging/architecture/KERNEL_PHASE_2_v2.md` §17 | Target WO schema fields |
| v2 Section 18: Open questions | `_staging/architecture/KERNEL_PHASE_2_v2.md` §18 | Hash-anchored trace as open question |
| Existing FMWK-008 draft | `_staging/FMWK-008_Work_Order_Protocol/work_order_protocol.md` | Current 10-section structure to update |
| Existing manifest | `_staging/FMWK-008_Work_Order_Protocol/manifest.yaml` | Manifest to update |
| Ledger metadata schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/ledger_entry_metadata.schema.json` | Relational key structure (reference, don't modify) |
| FMWK-000 (Governance) | Installed framework | Format exemplar for framework document structure |
| FMWK-001 (Provenance) | Installed framework | Format exemplar for manifest structure |

---

## 8. End-to-End Verification

1. **Markdown structure check**: Confirm all original 10 sections remain, plus new 5a and 5b inserted in correct position.
2. **YAML lint**: Parse `manifest.yaml` — no syntax errors.
3. **v2 cross-reference**: For each `v2 Section N` reference in the document, verify the section number and title match the actual v2 document.
4. **Schema integrity**: Confirm no files in `_staging/PKG-PHASE2-SCHEMAS-001/` were modified.
5. **Internal consistency**: Confirm the Kitchener step assignments in Section 2 match the lifecycle tier assignments in Section 3.

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `work_order_protocol.md` | `_staging/FMWK-008_Work_Order_Protocol/` | MODIFY — add Kitchener alignment, Section 5a, Section 5b |
| `manifest.yaml` | `_staging/FMWK-008_Work_Order_Protocol/` | MODIFY — add invariants, bump version |
| `RESULTS_FMWK008A.md` | `_staging/` | CREATE — verification results |

---

## 10. Design Principles

1. **Governance before code.** FMWK-008 defines rules that PKG-WORK-ORDER-001 implements. The framework is locked before the package is built.
2. **Reference, don't redefine.** Existing schemas are consumed as-is. If extension is needed, document the proposal — don't modify schemas.
3. **Trace everything.** The hash-anchored model ensures governance summaries are verifiable against detailed traces. No unverifiable claims.
4. **Graph over append-only.** Relational metadata keys (`parent_event_id`, `root_event_id`, `related_artifacts`) create a graph structure over the append-only ledger without breaking immutability.
5. **Kitchener alignment is structural.** Every WO type and lifecycle state explicitly maps to a Kitchener step and controlling tier. No ambiguity about which cognitive level owns which transition.
6. **Downstream frameworks defer to this one.** FMWK-009, 010, 011 all reference the metadata key standard defined here. Terminology defined in FMWK-008A is authoritative for the batch.
