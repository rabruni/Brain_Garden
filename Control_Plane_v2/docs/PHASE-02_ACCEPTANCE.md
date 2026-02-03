# PHASE-02_ACCEPTANCE.md

**Version**: 1.0.0
**Date**: 2026-02-03
**Status**: ALL CRITERIA MET

---

## Acceptance Criteria

### Category 1: Authorization

| ID | Criterion | Test Method | Status |
|----|-----------|-------------|--------|
| A1 | An unapproved WO cannot modify any file in any tier | `test_g2_gate.py::test_ho2_rejects_unapproved_wo` | PASS |
| A2 | A WO signed by an untrusted key is rejected | Verify signature against `trusted_keys.json` | PASS |
| A3 | A WO with missing signature field is rejected | Schema validation + G2 gate | PASS |
| A4 | Only keys with role `wo_approver` can sign WOs | Key role check in `g2_gate.py` | PASS |

### Category 2: Idempotency

| ID | Criterion | Test Method | Status |
|----|-----------|-------------|--------|
| I1 | Same `(work_order_id, wo_payload_hash)` is a guaranteed NO-OP | `test_idempotency.py::test_same_hash_is_noop` | PASS |
| I2 | Multiple retries of same WO all return NO-OP | `test_idempotency.py::test_multiple_retries_all_noop` | PASS |
| I3 | Same ID + different hash MUST always FAIL | `test_idempotency.py::test_different_hash_rejected` | PASS |
| I4 | Idempotency check queries HO2 workorder.jsonl | `test_idempotency.py::test_idempotency_checks_ho2_ledger` | PASS |
| I5 | `wo_payload_hash` computed from canonical JSON | `test_idempotency.py::test_hash_computed_from_canonical_json` | PASS |
| I6 | Idempotency does NOT depend on execution outputs | `test_idempotency.py::test_idempotency_independent_of_execution_output` | PASS |

### Category 3: Tamper Detection

| ID | Criterion | Test Method | Status |
|----|-----------|-------------|--------|
| T1 | Modified WO payload after approval is rejected | `test_g2_gate.py::test_tampered_wo_rejected` | PASS |
| T2 | Hash mismatch produces "TAMPERING" or "mismatch" in error | Assertion on error message content | PASS |
| T3 | Replay variant (same ID, different hash, both approved) fails | `test_g2_gate.py::test_replay_variant_rejected` | PASS |

### Category 4: Cross-Tier Provenance

| ID | Criterion | Test Method | Status |
|----|-----------|-------------|--------|
| P1 | HO1 session requires valid WO instance reference | `test_cross_tier_provenance.py::test_session_requires_wo_instance_path` | PASS |
| P2 | SESSION_START contains `wo_instance_ledger_path` and `wo_instance_hash` | `test_cross_tier_provenance.py::test_session_ledger_contains_wo_reference` | PASS |
| P3 | WO_ATTESTATION references HO2 completion hash | `test_cross_tier_provenance.py::test_attestation_references_ho2_hash` | PASS |
| P4 | Failed WO has FAILED status, not success | `test_cross_tier_provenance.py::test_failed_wo_has_failed_status` | PASS |
| P5 | Full chain HOT→HO2→HO1 is verifiable | `test_cross_tier_provenance.py::test_full_chain_hot_to_ho1` | PASS |
| P6 | Every HO1 event is traceable to a HOT approval hash | Chain: SESSION_START → WO instance → WO_RECEIVED → hot_approval_hash | PASS |

### Category 5: Scope Enforcement

| ID | Criterion | Test Method | Status |
|----|-----------|-------------|--------|
| S1 | WO can only modify files in `scope.allowed_files` | G2 scope validation | PASS |
| S2 | `allowed_files` must be subset of spec assets | Spec manifest comparison | PASS |
| S3 | Files outside scope cannot be written | G0B ownership check | PASS |

### Category 6: Registry Hygiene

| ID | Criterion | Test Method | Status |
|----|-----------|-------------|--------|
| R1 | Curated registries classified in `registry_policy.json` | Config file exists with curated list | PASS |
| R2 | Derived registries classified in `registry_policy.json` | Config file exists with derived list | PASS |
| R3 | `rebuild_derived.py` regenerates from sources | Script execution test | PASS |
| R4 | All governed files have owner in `file_ownership.csv` | G0B gate with 0 orphans | PASS |

### Category 7: Gate Execution

| ID | Criterion | Test Method | Status |
|----|-----------|-------------|--------|
| G1 | G2 runs before G0B in gate sequence | `apply_work_order.py` gate ordering | PASS |
| G2 | Gate failure produces non-zero exit code | All failure tests check returncode | PASS |
| G3 | Gate failure leaves no state changes | Workspace discarded on failure | PASS |
| G4 | Approved WO passes G2 and proceeds | `test_g2_gate.py::test_approved_wo_passes_g2` | PASS |

---

## Summary

| Category | Criteria | Passing |
|----------|----------|---------|
| Authorization | 4 | 4 |
| Idempotency | 6 | 6 |
| Tamper Detection | 3 | 3 |
| Cross-Tier Provenance | 6 | 6 |
| Scope Enforcement | 3 | 3 |
| Registry Hygiene | 4 | 4 |
| Gate Execution | 4 | 4 |
| **TOTAL** | **30** | **30** |

---

## Test Execution Evidence

```
$ python3 -m pytest tests/test_g2_gate.py tests/test_cross_tier_provenance.py tests/test_idempotency.py -v

tests/test_g2_gate.py::TestG2UnapprovedWO::test_ho2_rejects_unapproved_wo PASSED
tests/test_g2_gate.py::TestG2TamperedWO::test_tampered_wo_rejected PASSED
tests/test_g2_gate.py::TestG2Idempotency::test_retried_wo_idempotent PASSED
tests/test_g2_gate.py::TestG2ReplayVariant::test_replay_variant_rejected PASSED
tests/test_g2_gate.py::TestG2ScopeValidation::test_scope_validation_passes PASSED
tests/test_g2_gate.py::TestG2ApprovalExists::test_approved_wo_passes_g2 PASSED
tests/test_cross_tier_provenance.py::TestHO1RequiresValidWORef::test_session_requires_wo_instance_path PASSED
tests/test_cross_tier_provenance.py::TestSessionLedgerProvesWOLinkage::test_session_ledger_contains_wo_reference PASSED
tests/test_cross_tier_provenance.py::TestHOTProvesCompletionViaRefs::test_attestation_references_ho2_hash PASSED
tests/test_cross_tier_provenance.py::TestFailedWONoSuccessSummary::test_failed_wo_has_failed_status PASSED
tests/test_cross_tier_provenance.py::TestFailedWONoSuccessSummary::test_successful_wo_has_success_status PASSED
tests/test_cross_tier_provenance.py::TestCrossTierChain::test_full_chain_hot_to_ho1 PASSED
tests/test_idempotency.py::TestIdempotentRetry::test_same_hash_is_noop PASSED
tests/test_idempotency.py::TestIdempotentRetry::test_multiple_retries_all_noop PASSED
tests/test_idempotency.py::TestDifferentHashFails::test_different_hash_rejected PASSED
tests/test_idempotency.py::TestIdempotencyCheckQuerySource::test_idempotency_checks_ho2_ledger PASSED
tests/test_idempotency.py::TestIdempotencyCheckQuerySource::test_new_wo_proceeds PASSED
tests/test_idempotency.py::TestIdempotencyHashComparison::test_hash_computed_from_canonical_json PASSED
tests/test_idempotency.py::TestIdempotencyHashComparison::test_idempotency_independent_of_execution_output PASSED

19 passed
```

Full test suite: **264 passed, 9 warnings**

---

## Acceptance Declaration

All 30 acceptance criteria are met. Phase 2 implementation is complete and verified.

Signed: Architect/Auditor
Date: 2026-02-03
