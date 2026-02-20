# Execution Plan: H-31 Context Authority MVP

**Created**: 2026-02-19
**Source**: H-31_Context_Authority_Build_Plan.md
**Governs**: All handoffs in the H-31 + H-29.1 sequence
**Archive when**: All 10 handoffs show PASS in status column

---

## Baseline (verified 2026-02-19)

| Metric | Value |
|--------|-------|
| Last completed handoff | H-31A-1 (RESULTS_HANDOFF_31A1.md) |
| Packages in CP_BOOTSTRAP | 23 |
| CP_BOOTSTRAP SHA | sha256:723e53eaea2d8af241f4dd9d92cc3b0c5428e71ee9bf517231981e62e4cb6de6 |
| Tests | 743 (742 pass, 1 pre-existing failure) |
| Pre-existing failure | test_exactly_five_frameworks (expects 5, finds 6 — FMWK-004) |
| Gates | 8/8 PASS |

---

## Execution Sequence (dependency-ordered)

### Level 0 — DONE

| # | Handoff | Package | Status | Tests Added | RESULTS File |
|---|---------|---------|--------|-------------|--------------|
| 1 | H-31A-1 | PKG-ADMIN-001 | **PASS** | 10 | RESULTS_HANDOFF_31A1.md |

### Level 1 — READY NOW (parallel-safe: different packages)

| # | Handoff | Package | Status | Tests Added | RESULTS File |
|---|---------|---------|--------|-------------|--------------|
| 2 | H-31A-2 | PKG-SESSION-HOST-V2-001 | **PASS** | 10 | RESULTS_HANDOFF_31A2.md |
| 3 | H-31B | PKG-HO1-EXECUTOR-001 | **PASS** | 12 | RESULTS_HANDOFF_31B.md |

**Why parallel**: H-31A-2 (consolidation caller) and H-31B (extend classify) touch different packages, have no shared code, and neither reads the other's output.

### Level 2 — After H-31B (parallel-safe: different packages)

| # | Handoff | Package | Status | Tests Added | RESULTS File |
|---|---------|---------|--------|-------------|--------------|
| 4 | H-29.1A | PKG-HO3-MEMORY-001 | **PASS** | 18 | RESULTS_HANDOFF_29_1A.md |
| 5 | H-31C | PKG-HO2-SUPERVISOR-001 | **PASS** | 16 | RESULTS_HANDOFF_31C.md |

**Why parallel**: H-29.1A (structured artifacts in HO3) and H-31C (intent resolver in HO2) touch different packages.
**Why after H-31B**: H-31C reads intent_signal from classify (has bridge mode, but real data needs H-31B). H-29.1A uses the same closed label vocabulary defined by H-31B.

### Level 3 — After H-29.1A (serial)

| # | Handoff | Package | Status | Tests Added | RESULTS File |
|---|---------|---------|--------|-------------|--------------|
| 6 | H-29.1B | PKG-HO1-EXECUTOR-001 | **PASS** | 10 | RESULTS_HANDOFF_29_1B.md |

**Why serial**: Consolidation prompt must produce structured artifacts defined by H-29.1A's schema.

### Level 4 — After H-29.1B + H-31C (serial)

| # | Handoff | Package | Status | Tests Added | RESULTS File |
|---|---------|---------|--------|-------------|--------------|
| 7 | H-29.1C | PKG-HO2-SUPERVISOR-001 | **PASS** | 18 | RESULTS_HANDOFF_29_1C.md |

**Why serial**: select_biases needs structured artifacts (H-29.1A/B) and label vocabulary (H-31B). Signal extraction needs classify labels. Modifies PKG-HO2-SUPERVISOR-001 after H-31C already changed it — must incorporate those changes.

### Level 5 — After H-29.1C (serial)

| # | Handoff | Package | Status | Tests Added | RESULTS File |
|---|---------|---------|--------|-------------|--------------|
| 8 | H-31D | PKG-HO2-SUPERVISOR-001 | SPEC ONLY | — | — |

**Why serial**: Liveness reducer reads INTENT_DECLARED/SUPERSEDED/CLOSED events (H-31C). Overlay writer creates projection snapshots consumed by H-31E-1. Builds on H-29.1C changes to PKG-HO2-SUPERVISOR-001.

### Level 6 — After H-31D (parallel-safe: different packages)

| # | Handoff | Package | Status | Tests Added | RESULTS File |
|---|---------|---------|--------|-------------|--------------|
| 9 | H-31E-1 | PKG-HO2-SUPERVISOR-001 | SPEC ONLY | — | — |
| 10 | H-31E-2 | PKG-ADMIN-001 | SPEC ONLY | — | — |

**Why parallel**: Different packages. H-31E-2 adds config values with .get() defaults — safe even if H-31E-1 hasn't added the HO2Config fields yet.

---

## Dependency Graph (visual)

```
H-31A-1 ✅ (PKG-ADMIN-001)
  │
  ├──────────────────────────────┐
  ▼                              ▼
H-31A-2 ✅ (SESSION-HOST-V2)  H-31B ✅ (HO1-EXECUTOR)
  │                              │
  │                    ┌─────────┴─────────┐
  │                    ▼                   ▼
  │                 H-29.1A ✅ (HO3-MEM) H-31C ✅ (HO2-SUP)
  │                    │                   │
  │                    ▼                   │
  │                 H-29.1B ✅ (HO1-EXE)   │
  │                    │                   │
  │                    └─────────┬─────────┘
  │                              ▼
  │                           H-29.1C ✅ (HO2-SUP)
  │                              │
  │                              ▼
  │                           H-31D (HO2-SUP)
  │                              │
  │                    ┌─────────┴─────────┐
  │                    ▼                   ▼
  │                 H-31E-1 (HO2-SUP)  H-31E-2 (ADMIN)
  │
  └─── (no downstream — consolidation caller is standalone)
```

---

## Package Modification Map

Shows which packages are touched by which handoffs (serialization within a package is mandatory):

| Package | Handoffs (in order) | Total touches |
|---------|--------------------|---------------|
| PKG-ADMIN-001 | H-31A-1 ✅, H-31E-2 | 2 |
| PKG-SESSION-HOST-V2-001 | H-31A-2 ✅ | 1 |
| PKG-HO1-EXECUTOR-001 | H-31B, H-29.1B | 2 |
| PKG-HO3-MEMORY-001 | H-29.1A | 1 |
| PKG-HO2-SUPERVISOR-001 | H-31C, H-29.1C, H-31D, H-31E-1 | 4 (bottleneck) |

**PKG-HO2-SUPERVISOR-001 is the critical path.** Four serial handoffs must land in order. No parallelism possible within this package.

---

## Spec Inventory

All 10 handoff specs exist on disk:

| Handoff | Spec File | Verified |
|---------|-----------|----------|
| H-31A-1 | BUILDER_HANDOFF_31A1_wire_ho3_into_admin.md | 2026-02-19 |
| H-31A-2 | BUILDER_HANDOFF_31A2_consolidation_caller.md | 2026-02-19 |
| H-31B | BUILDER_HANDOFF_31B_extend_classify.md | 2026-02-19 |
| H-31C | BUILDER_HANDOFF_31C_intent_lifecycle.md | 2026-02-19 |
| H-29.1A | BUILDER_HANDOFF_29_1A_structured_artifacts.md | 2026-02-19 |
| H-29.1B | BUILDER_HANDOFF_29_1B_consolidation_prompt.md | 2026-02-19 |
| H-29.1C | BUILDER_HANDOFF_29_1C_signal_extraction_consumption.md | 2026-02-19 |
| H-31D | BUILDER_HANDOFF_31D_liveness_reducer.md | 2026-02-19 |
| H-31E-1 | BUILDER_HANDOFF_31E1_context_projector.md | 2026-02-19 |
| H-31E-2 | BUILDER_HANDOFF_31E2_projection_config.md | 2026-02-19 |

---

## Risks

1. **PKG-HO2-SUPERVISOR-001 bottleneck**: 4 serial handoffs on the critical path. Any delay cascades.
2. **Baseline drift**: Each handoff changes test counts and CP_BOOTSTRAP hash. Specs cite "22 pkgs / 693 tests" but actual baseline is 23 pkgs / 743 tests. Builders must use the LATEST results file as input baseline, not the spec's original number.
3. **Pre-existing failure**: `test_exactly_five_frameworks` (expects 5 frameworks, finds 6). Not blocking but should be tracked.
4. ~~**10Q reviews lost**~~: Re-run complete. Both H-31A-2 and H-31B 10Q reviews passed 13/13.

---

## Progress Log

| Date | Event | By |
|------|-------|----|
| 2026-02-18 | H-31A-1 implemented and verified (PASS, 743 tests, 8/8 gates) | Builder agent |
| 2026-02-19 | Context failure — autonomous pipeline interrupted. All specs intact, no implementations lost. | System |
| 2026-02-19 | Full audit completed. Execution plan created. | Claude Code |
| 2026-02-19 | H-31A-2 10Q reviewed — 13/13 PASS. Approved. | Claude Code |
| 2026-02-19 | H-31B 10Q reviewed — 13/13 PASS. Approved. | Claude Code |
| 2026-02-19 | H-31A-2 implemented and verified (PASS, 764 tests, 8/8 gates) | Builder agent |
| 2026-02-19 | H-31B implemented and verified (PASS, 764 tests, 12 new, 8/8 gates) | Builder agent |
| 2026-02-19 | H-29.1A 10Q reviewed — 13/13 PASS. Approved. | Claude Code |
| 2026-02-19 | H-29.1A implemented and verified (PASS, 781 tests, 18 new, 8/8 gates) | Builder agent |
| 2026-02-19 | H-31C agent misfired — implemented H-31B (already done) instead of H-31C. No damage. | Builder agent |
| 2026-02-19 | H-29.1B 10Q reviewed — 13/13 PASS. Approved. | Claude Code |
| 2026-02-19 | H-31C 10Q reviewed — 13/13 PASS. Approved. Re-dispatched with tighter prompt. | Claude Code |
| 2026-02-19 | H-31C implemented and verified (PASS, 807 tests, 16 new, 8/8 gates) | Builder agent |
| 2026-02-19 | H-29.1B implemented and verified (PASS, 791 tests, 10 new, 8/8 gates) | Builder agent |
| 2026-02-19 | H-29.1C 10Q reviewed — 13/13 PASS. Approved. | Claude Code |
| 2026-02-19 | H-29.1C implemented and verified (PASS, 807 installed tests, 18 new, 8/8 gates) | Builder agent |
| | | |

---

## Completion Criteria

All of the following must be true before archiving this document:

- [ ] All 10 status cells show **PASS**
- [ ] All 10 RESULTS files exist with clean-room verification
- [ ] Final CP_BOOTSTRAP has all changes integrated
- [ ] Final gate check: 8/8 PASS
- [ ] No new test failures introduced (pre-existing failure excluded)
- [ ] Shadow mode validated for context projector (H-31E-1)
- [ ] This document archived to `_staging/architecture/` with date suffix
