# FMWK-000: Control Plane Governance Framework

## Metadata
- framework_id: FMWK-000
- status: active
- version: 2.0.0
- plane: hot

## Overview

This is the root governance framework for Control Plane v2. It defines the non-negotiable invariants, gate sequence, and work order protocol that governs all changes to the control plane.

## Invariants

### Non-Negotiable

- [MUST] Every filename MUST be mapped exactly once to a Spec. No orphans. No duplicates.
- [MUST] All components MUST be installed via package manager. ONLY `genesis_bootstrap.py` is exempt.
- [MUST] Same `(work_order_id, wo_payload_hash)` reapplies as no-op. Same ID + different hash MUST FAIL.
- [MUST] All execution MUST occur in isolated workspace. No partial state to authoritative plane.
- [MUST] Work Orders MUST be approved via Git PR review. Agents MUST NOT self-approve.
- [MUST NOT] Standards MUST NOT be enforcement - ISO/CMMI/IEEE MAY inform schemas.
- [MUST NOT] Gate failures MUST NOT be ignored - fail-closed execution required.

### Security Posture

- [MUST] Fail-closed on all gate failures
- [MUST] No execution outside isolated workspace
- [MUST] No partial state writes
- [MUST] Human approval gate required

## Path Authorizations

Specs governed by this framework MAY own files matching:

- `lib/*.py`
- `scripts/*.py`
- `schemas/*.json`
- `config/*.json`
- `frameworks/*.md`
- `tests/test_*.py`
- `work_orders/**/*.json`

## Required Gates

All changes under this framework MUST pass:

| Gate | Phase | Purpose |
|------|-------|---------|
| G0 | VALIDATE | OWNERSHIP - Every file in governed roots must be registered |
| G1 | VALIDATE | CHAIN - Every file->spec->framework chain must be valid |
| G2 | VALIDATE | WORK_ORDER - Approval + idempotency check |
| G3 | VALIDATE | CONSTRAINTS - No constraint violations |
| G4 | VALIDATE | ACCEPTANCE - Tests must pass |
| G5 | APPLY | SIGNATURE - Package signatures must be valid |
| G6 | APPLY | LEDGER - Atomic write + ledger chain |

## Change Control

Allowed Work Order types:
- `code_change`: Modify existing files within spec scope
- `spec_delta`: Add new files, interfaces, or dependencies to spec
- `registry_change`: Modify registry files
- `dependency_add`: Add external dependency

## Genesis Exception

`genesis_bootstrap.py` is the ONLY script that MAY:
- Exist without a governing spec
- Install packages without a Work Order
- Operate before registries exist

## Ledger Split

| Ledger | Content | Purpose |
|--------|---------|---------|
| `work_orders.jsonl` | PROPOSED, APPROVED, REJECTED | Approval tracking |
| `applied_work_orders.jsonl` | APPLIED, COMPLETED, FAILED | Idempotency + execution |

## References

- [FMWK-100](FMWK-100_agent_development_standard.md): Agent Development Standard
- [FMWK-200](FMWK-200_ledger_protocol.md): Ledger Protocol Standard
- [FMWK-107](FMWK-107_package_management_standard.md): Package Management Standard
