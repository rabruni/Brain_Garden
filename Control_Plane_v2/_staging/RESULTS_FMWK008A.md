# RESULTS: FMWK-008A — Work Order Protocol Update

**Agent**: FMWK-008A
**Date**: 2026-02-14
**Handoff**: `_staging/handoffs/BUILDER_HANDOFF_FMWK008A_wo_protocol_update.md`

---

## Files Modified

| File | Action | Location |
|------|--------|----------|
| `work_order_protocol.md` | MODIFIED | `_staging/FMWK-008_Work_Order_Protocol/` |
| `manifest.yaml` | MODIFIED | `_staging/FMWK-008_Work_Order_Protocol/` |
| `RESULTS_FMWK008A.md` | CREATED | `_staging/` |

## Files NOT Modified (integrity check)

| File | Status |
|------|--------|
| `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/ledger_entry_metadata.schema.json` | UNTOUCHED — verified via `git diff --name-only` |

---

## Section-by-Section Verification

### Check 1: Every WO type has a Kitchener step column

**PASS**

Section 2 table now has 5 columns: Type, Tier Target, **Kitchener Step**, Description, LLM Call?. All 4 WO types (`classify`, `tool_call`, `synthesize`, `execute`) map to Step 3: Execution (L1). A supplementary Kitchener Step Mapping table shows all 5 steps and their WO relationship.

### Check 2: Every lifecycle state has a controlling tier

**PASS**

Section 3 state table now has 5 columns: State, Set By, **Kitchener Step**, **Controlling Tier**, Meaning. All 5 states assigned:
- `planned` — HO2, Step 2: Scoping (L2)
- `dispatched` — HO2, Step 2: Scoping (L2)
- `executing` — HO1, Step 3: Execution (L1)
- `completed` — HO1, Step 3: Execution (L1)
- `failed` — HO1 or HO2, Step 3/4

State transition rules table also gained a Kitchener Step column.

### Check 3: Section 5a defines hash-anchored trace

**PASS**

Section 5a ("Hash-Anchored Trace Model") inserted after Section 5, before Section 5b. Contains:
- Problem statement referencing v2 Section 18 open question
- Two-tier recording model table (HO2 = summaries, HO1 = detail)
- `trace_hash` computation sequence (4 steps)
- Ordering guarantee (computed AFTER HO1 completes)
- Field location: `metadata.context_fingerprint.context_hash`
- Verification procedure (4 steps)
- Implementation boundary (protocol here, code in PKG-WORK-ORDER-001)

### Check 4: Section 5b defines metadata key standard

**PASS**

Section 5b ("Metadata Key Standard") inserted after Section 5a, before Section 6. Contains:
- Required relational fields: `relational.parent_event_id`, `relational.root_event_id`, `relational.related_artifacts` with exact types and when-required rules
- Provenance fields: `provenance.agent_id`, `provenance.agent_class`, `provenance.work_order_id`, `provenance.session_id`, `provenance.framework_id`
- Context fingerprint fields: `context_fingerprint.context_hash`, `prompt_pack_id`, `tokens_used.input`, `tokens_used.output`, `model_id`
- Graph traversal patterns table (5 patterns)
- Downstream frameworks note (FMWK-009, 010, 011)

### Check 5: Section 5 updated with trace_hash

**PASS**

HO2 ledger event table now includes `trace_hash` as a bold key field on `WO_CHAIN_COMPLETE` and `WO_QUALITY_GATE` events. HO2 section description updated to reference Section 5a.

### Check 6: Section 5 updated with relational keys

**PASS**

Both HO2 and HO1 ledger event tables now include a **Relational Metadata** column. Each event type specifies which `relational.*` keys it carries:
- HO2: `WO_PLANNED` carries `root_event_id` + `related_artifacts`; `WO_DISPATCHED` carries `parent_event_id`; `WO_CHAIN_COMPLETE` carries `root_event_id` + `related_artifacts`; `WO_QUALITY_GATE` carries `parent_event_id`
- HO1: `WO_EXECUTING` carries `parent_event_id` (cross-tier to HO2) + `root_event_id`; `LLM_CALL` carries `parent_event_id` + `related_artifacts`; `TOOL_CALL` carries `parent_event_id`; `WO_COMPLETED`/`WO_FAILED` carry `parent_event_id` + `root_event_id`

Ledger Invariants section gained 3 new invariants for trace_hash and relational keys.

### Check 7: All v2 references accurate

**PASS**

Cross-checked every `v2 Section N` reference against actual v2 headings:

| Reference in FMWK-008 | Actual v2 Heading | Match? |
|------------------------|-------------------|--------|
| v2 Section 1: Grounding Model: The Kitchener Orchestration Stack | `## 1. Grounding Model: The Kitchener Orchestration Stack` | YES |
| v2 Section 6: Memory Architecture | `## 6. Memory Architecture` | YES |
| v2 Section 9: Learning Model — Three Timescales | `## 9. Learning Model — Three Timescales` | YES |
| v2 Section 18: Critical Path — What's Next | `## 18. Critical Path — What's Next` | YES |

### Check 8: No schema modifications

**PASS**

`git diff --name-only -- Control_Plane_v2/_staging/PKG-PHASE2-SCHEMAS-001/` returned empty. No files in the schema package were touched.

### Check 9: manifest.yaml valid YAML

**PASS**

Parsed with `python3 -c "import yaml; yaml.safe_load(...)"`. No syntax errors. Version reads as `1.1.0`. 10 invariants parsed.

### Check 10: manifest.yaml invariants cover new additions

**PASS**

4 new invariants added (total: 10):

| # | New Invariant | Covers |
|---|---------------|--------|
| 7 | Every HO2 terminal event MUST include a trace_hash | Section 5a (hash-anchored trace) |
| 8 | Every ledger entry MUST populate relational.parent_event_id when a causal parent exists | Section 5b (metadata key standard) |
| 9 | Every ledger entry at chain boundaries MUST populate relational.root_event_id | Section 5b (metadata key standard) |
| 10 | Metadata key standard MUST NOT redefine fields already in schema | Constraint 4 from handoff |

### Check 11: Invariant coverage — #1 (no direct LLM calls)

**PASS**

WO type rules in Section 2 specify that `classify`, `synthesize`, and `execute` require prompt contracts, implying LLM Gateway usage. Section 5b context fingerprint fields document model_id per LLM call. Consistent with v2 Section 10 Invariant #1: "Every LLM call flows through the LLM Gateway."

### Check 12: Invariant coverage — #2 (every agent under WO)

**PASS**

Framework Purpose statement: "the work order as the atomic unit of cognitive dispatch." Section 1: "HO2 is the ONLY tier that creates work orders." Section 3: all agent work enters the lifecycle state machine. Consistent with v2 Section 10 Invariant #2: "Every agent operates under a work order."

### Check 13: Invariant coverage — #5 (budgets enforced)

**PASS**

Section 7 (Budget Model) unchanged — defines session > WO > LLM call hierarchy. Budget exhaustion rules: WO fails with `budget_exhausted`, session returns degraded response. Manifest invariant #5: "Every WO MUST have a bounded token budget." Consistent with v2 Section 10 Invariant #5: "Budgets are enforced, not advisory."

---

## End-to-End Verification

### 1. Markdown structure check

**PASS** — All original 10 sections remain. New Section 5a and 5b inserted between Section 5 and Section 6. Section ordering: 1, 2, 3, 4, 5, 5a, 5b, 6, 7, 8, 9, 10, Conformance, Status.

### 2. YAML lint

**PASS** — `manifest.yaml` parses without errors. All fields present.

### 3. v2 cross-reference

**PASS** — 4 unique v2 Section references. All section numbers and titles verified against `KERNEL_PHASE_2_v2.md`. See Check 7 table above.

### 4. Schema integrity

**PASS** — No files in `_staging/PKG-PHASE2-SCHEMAS-001/` were modified. Verified via git diff.

### 5. Internal consistency

**PASS** — Kitchener step assignments in Section 2 (all WO types = Step 3: Execution) are consistent with Section 3 lifecycle tier assignments (HO2 owns planned/dispatched at Step 2, HO1 owns executing/completed at Step 3). The quality gate (Step 4: Verification) is not a WO type — it is an HO2 act recorded as `WO_QUALITY_GATE`, consistent across both sections.

---

## Summary

| Category | Result |
|----------|--------|
| Checks passed | 13/13 |
| End-to-end checks passed | 5/5 |
| Files modified | 2 (work_order_protocol.md, manifest.yaml) |
| Files created | 1 (RESULTS_FMWK008A.md) |
| Schema files touched | 0 |
| v2 references verified | 4/4 |
| Manifest invariants | 10 (6 original + 4 new) |

**FMWK-008A: COMPLETE**
