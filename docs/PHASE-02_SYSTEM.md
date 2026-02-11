# PHASE-02_SYSTEM.md

**Version**: 1.0.0
**Date**: 2026-02-03
**Status**: IMPLEMENTED

---

## A. System Purpose

### What Phase 2 Guarantees

Phase 2 implements the G2 WORK_ORDER gate, which guarantees:

1. **No unauthorized changes**: Every mutation to governed files requires a cryptographically signed Work Order approved by a human with a trusted Ed25519 key.

2. **Tamper detection**: Any modification to a Work Order after approval is detected via SHA-256 hash comparison and rejected.

3. **Idempotent execution**: Retrying an already-applied Work Order is safe—it produces no side effects (NO-OP).

4. **Replay protection**: Attempting to execute the same Work Order ID with different content fails hard (tampering/replay variant).

5. **Cross-tier provenance**: Every action in lower tiers (HO2, HO1) can be traced back to a specific approval event in HOT via cryptographic hash references.

6. **Scope enforcement**: Work Orders can only modify files explicitly listed in their scope, which must be a subset of the owning Spec's assets.

### What Phase 2 Prevents (Attack Model)

| Attack Vector | Prevention Mechanism |
|---------------|---------------------|
| Agent self-approval | Ed25519 signatures require private key; agents have no access |
| WO tampering post-approval | Hash comparison: `computed_hash != approved_hash` → FAIL |
| Replay of old WO with new content | Idempotency check: same ID + different hash → FAIL |
| Scope escalation | `allowed_files` validated against `spec.assets` |
| Orphan file injection | G0B requires every file in governed roots to be owned |
| Ledger forgery | Hash chain verification; each entry references previous hash |
| Unauthorized tier writes | Each tier has explicit write boundaries enforced by gates |

---

## B. Actors & Tiers

### HOT (Governance Tier / HO3)

**Identity**: The authoritative governance tier. Source of truth for approvals and attestations.

| Permission | Scope |
|------------|-------|
| **Can Write** | `ledger/governance.jsonl` (WO_APPROVED, WO_ATTESTATION) |
| **Can Write** | `config/trusted_keys.json` (key rotation, out of scope Phase 2) |
| **Can Read** | All tiers (full visibility) |
| **Must Never Touch** | HO2 instance ledgers, HO1 session ledgers (read-only reference) |

**Key Events Written**:
- `WO_APPROVED` — Human approval with Ed25519 signature
- `WO_ATTESTATION` — Summary of completed WO execution with HO2 hash reference

---

### HO2 (Work Order Tier)

**Identity**: The execution coordination tier. Receives approved WOs, spawns sessions, records completion.

| Permission | Scope |
|------------|-------|
| **Can Write** | `planes/ho2/ledger/workorder.jsonl` (WO_RECEIVED, WO_COMPLETED) |
| **Can Write** | `planes/ho2/work_orders/{wo_id}/ledger/execution.jsonl` (instance) |
| **Can Read** | HOT governance.jsonl (to verify approvals) |
| **Can Read** | HO1 session ledgers (to verify completion) |
| **Must Never Touch** | HOT governance.jsonl (read-only), curated registries |

**Key Events Written**:
- `WO_RECEIVED` — G2 passed, WO accepted into execution queue
- `WO_COMPLETED` — Execution finished, references instance ledger hash

---

### HO1 (Worker Tier)

**Identity**: The execution tier. Performs actual work within session boundaries.

| Permission | Scope |
|------------|-------|
| **Can Write** | `planes/ho1/sessions/{session_id}/ledger/session.jsonl` (instance) |
| **Can Write** | Files within WO scope (via atomic apply) |
| **Can Read** | HO2 instance ledger (to verify WO linkage) |
| **Must Never Touch** | HOT governance.jsonl, HO2 base ledger, curated registries |

**Key Events Written**:
- `SESSION_START` — Links to WO instance via `wo_instance_ledger_path` + hash
- `SESSION_END` — Result status and final hash

---

## C. G2 WORK_ORDER Gate — Formal Specification

### Preconditions

Before G2 can execute:

1. Work Order file MUST exist at `work_orders/{plane}/WO-YYYYMMDD-NNN.json`
2. Work Order MUST conform to `schemas/work_order.schema.json`
3. `config/trusted_keys.json` MUST exist with at least one key with role `wo_approver`
4. HOT `ledger/governance.jsonl` MUST be readable

### Canonical JSON → Hash Process

```
STEP 1: Load WO file as JSON object
STEP 2: Serialize with canonical rules:
        - Keys sorted alphabetically (recursive)
        - Separators: (',', ':') — no spaces
        - UTF-8 encoding
        - No BOM
STEP 3: Compute SHA-256 of canonical string
STEP 4: Format as "sha256:<64-hex-chars>"
```

**Implementation**:
```python
canonical = json.dumps(wo_data, sort_keys=True, separators=(',', ':'))
wo_payload_hash = 'sha256:' + hashlib.sha256(canonical.encode('utf-8')).hexdigest()
```

### Signature Verification

```
STEP 1: Extract signature_b64 and approver_key_id from WO_APPROVED event
STEP 2: Load public key from config/trusted_keys.json by key_id
STEP 3: Verify key has role "wo_approver"
STEP 4: Decode signature from base64
STEP 5: Verify Ed25519 signature over wo_payload_hash string
STEP 6: If verification fails → HARD FAIL
```

**Key Schema** (`config/trusted_keys.json`):
```json
{
  "keys": [{
    "key_id": "string",
    "algorithm": "Ed25519",
    "public_key_b64": "base64-encoded-32-bytes",
    "roles": ["wo_approver"]
  }]
}
```

### Scope Checking

Scope validation is **file-by-file, no globs**:

```
STEP 1: Load spec from specs_registry.csv via WO.spec_id
STEP 2: Load spec manifest from specs/{spec_id}/manifest.yaml
STEP 3: Extract spec.assets[] — list of exact file paths
STEP 4: For each file in WO.scope.allowed_files:
        - VERIFY file ∈ spec.assets
        - If not → HARD FAIL "file not in spec assets"
STEP 5: For each file in WO.scope.forbidden_files:
        - VERIFY file ∉ changeset (if known at gate time)
```

### Idempotency Rules

```
STEP 1: Query HO2 workorder.jsonl for WO_COMPLETED events
STEP 2: Filter by submission_id == wo_id
STEP 3: If found:
        a) Extract recorded wo_payload_hash
        b) Compare with computed hash:
           - MATCH → Return NO_OP (idempotent success)
           - MISMATCH → HARD FAIL (tampering/replay variant)
STEP 4: If not found → PROCEED with execution
```

### Failure Modes

| Condition | Failure Type | Action |
|-----------|--------------|--------|
| No WO_APPROVED event found | HARD FAIL | Reject, log, exit non-zero |
| Hash mismatch (tampering) | HARD FAIL | Reject, log "TAMPERING DETECTED" |
| Signature invalid | HARD FAIL | Reject, log "SIGNATURE VERIFICATION FAILED" |
| Key not trusted | HARD FAIL | Reject, log "KEY NOT IN TRUSTED KEYS" |
| Same ID + different hash | HARD FAIL | Reject, log "REPLAY VARIANT DETECTED" |
| File not in spec assets | HARD FAIL | Reject, log "SCOPE VIOLATION" |
| Spec not found | HARD FAIL | Reject, log "SPEC NOT FOUND" |
| Same ID + same hash (completed) | SOFT PASS | Return NO_OP, exit zero |

**Hard Fail**: Non-zero exit code, no state changes, audit log entry.
**Soft Pass**: Zero exit code, no state changes, log "idempotent no-op".

---

## D. Idempotency Contract

| Case | Inputs | Expected Result | Why |
|------|--------|-----------------|-----|
| New WO | `(WO-001, hash-A)` not in HO2 | PROCEED | First execution |
| Retry same | `(WO-001, hash-A)` in HO2 as COMPLETED | NO_OP | Idempotent retry is safe |
| Retry 3x | `(WO-001, hash-A)` in HO2 | NO_OP (all 3) | Unlimited safe retries |
| Tampered | `(WO-001, hash-B)` where `hash-A` completed | FAIL | Different content = tampering |
| Replay variant | `(WO-001, hash-C)` approved after `hash-A` completed | FAIL | Cannot reuse WO ID |
| Different WO | `(WO-002, hash-D)` not in HO2 | PROCEED | Independent WO |
| Partial execution | `(WO-001, hash-A)` started but not completed | PROCEED | Retry partial is allowed |

**Invariant**: Idempotency is defined over `(work_order_id, wo_payload_hash)`. It MUST NOT depend on:
- Execution outputs
- Registry state
- Timestamps
- Session IDs

---

## E. Cross-Tier Provenance Contract

### Chain Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ HOT: ledger/governance.jsonl                                        │
│                                                                     │
│  WO_APPROVED ─────────────────────────────────────────────┐        │
│  ├─ wo_id: "WO-20260202-001"                              │        │
│  ├─ wo_payload_hash: "sha256:abc123..."                   │        │
│  ├─ signature_b64: "<Ed25519 sig>"                        │        │
│  ├─ approver_key_id: "admin-001"                          │        │
│  └─ entry_hash: "sha256:HOT_APPROVAL_HASH"  ◄─────────────┼────┐   │
│                                                           │    │   │
│  WO_ATTESTATION ◄─────────────────────────────────────────┼────┼─┐ │
│  ├─ wo_id: "WO-20260202-001"                              │    │ │ │
│  ├─ result_status: "success"                              │    │ │ │
│  └─ ho2_completion_hash: "sha256:HO2_COMPLETION_HASH" ────┼────┼─┼─┤
└─────────────────────────────────────────────────────────────────┼─┼─┘
                                                              │   │ │
┌─────────────────────────────────────────────────────────────┼───┼─┼─┐
│ HO2: planes/ho2/ledger/workorder.jsonl                      │   │ │ │
│                                                             │   │ │ │
│  WO_RECEIVED                                                │   │ │ │
│  ├─ wo_id: "WO-20260202-001"                                │   │ │ │
│  ├─ wo_payload_hash: "sha256:abc123..."                     │   │ │ │
│  └─ hot_approval_hash: "sha256:HOT_APPROVAL_HASH" ──────────┘   │ │ │
│                                                                 │ │ │
│  WO_COMPLETED                                                   │ │ │
│  ├─ wo_id: "WO-20260202-001"                                    │ │ │
│  ├─ wo_payload_hash: "sha256:abc123..."                         │ │ │
│  ├─ instance_ledger_hash: "sha256:HO2_INSTANCE_HASH" ───────────┼─┘ │
│  └─ entry_hash: "sha256:HO2_COMPLETION_HASH" ───────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                                                 │
┌────────────────────────────────────────────────────────────────┼────┐
│ HO2 Instance: planes/ho2/work_orders/{wo_id}/ledger/execution.jsonl │
│                                                                │    │
│  SESSION_SPAWNED                                               │    │
│  ├─ session_id: "SESSION-20260202-001"                         │    │
│  └─ session_ledger_path: "planes/ho1/sessions/.../session.jsonl"    │
│                                                                │    │
│  entry_hash: "sha256:HO2_INSTANCE_HASH" ───────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                                                 │
┌────────────────────────────────────────────────────────────────┼────┐
│ HO1 Instance: planes/ho1/sessions/{session_id}/ledger/session.jsonl │
│                                                                     │
│  SESSION_START                                                      │
│  ├─ session_id: "SESSION-20260202-001"                              │
│  ├─ wo_id: "WO-20260202-001"                                        │
│  ├─ wo_instance_ledger_path: "planes/ho2/work_orders/.../exec.jsonl"│
│  └─ wo_instance_hash: "sha256:HO2_INSTANCE_HASH" ───────────────────┘
└─────────────────────────────────────────────────────────────────────┘
```

### Hash Linkage Table

| From | To | Hash Field | Verification |
|------|----|------------|--------------|
| HO2 WO_RECEIVED | HOT WO_APPROVED | `hot_approval_hash` | MANDATORY |
| HO2 WO_COMPLETED | HO2 Instance | `instance_ledger_hash` | MANDATORY |
| HOT WO_ATTESTATION | HO2 WO_COMPLETED | `ho2_completion_hash` | MANDATORY |
| HO1 SESSION_START | HO2 Instance | `wo_instance_hash` | MANDATORY |

### Verification Requirements

1. **WO_RECEIVED must verify**: Query HOT governance.jsonl, confirm `hot_approval_hash` matches actual entry hash of WO_APPROVED event.

2. **SESSION_START must verify**: The `wo_instance_hash` matches the current hash of the HO2 instance ledger at spawn time.

3. **WO_ATTESTATION must verify**: The `ho2_completion_hash` matches the entry hash of the WO_COMPLETED event in HO2.

4. **Chain replay**: Any auditor can replay the full chain by following hash references from HO1 → HO2 → HOT and verifying each link.

---

## PHASE-02_GOVERNANCE_CHECKLIST

### Invariant Validation

| # | Question | Answer | Evidence / Notes |
|---|----------|--------|------------------|
| 1 | Does any mutation occur before G2 passes? | **NO** | G2 runs FIRST in gate sequence (before G0B). File writes only occur in APPLY phase after all VALIDATE gates pass. |
| 2 | Are all file writes explicitly scoped 1:1 by filename? | **YES** | `scope.allowed_files` is an array of exact paths. No globs permitted in WO schema. |
| 3 | Can derived registries be edited directly? | **NO** | `config/registry_policy.json` classifies `registries/compiled/*.json` as derived. Rebuild-only via `rebuild_derived.py`. |
| 4 | Is provenance chain verification mandatory, not optional? | **YES** | `WO_RECEIVED` requires `hot_approval_hash`. `SESSION_START` requires `wo_instance_hash`. Tests enforce this. |
| 5 | Is there a single entrypoint for gate execution? | **YES** | `scripts/gate_check.py --gate G2` or `scripts/apply_work_order.py` which calls G2 internally. |
| 6 | Can a compromised key corrupt the system? | **PARTIALLY** | A compromised Ed25519 private key could approve malicious WOs. Mitigation: key rotation, multiple approvers (future), audit trail in ledger. |

### Issue #6 Detail

**Risk**: If an attacker obtains an Ed25519 private key with `wo_approver` role, they can sign arbitrary Work Orders.

**Mitigations in place**:
- Private keys stored outside governed roots (`~/.control_plane_v2/`)
- All approvals recorded in immutable ledger (forensic trail)
- Key rotation documented (change `trusted_keys.json`, old key's approvals remain valid but key cannot sign new WOs)

**Future mitigations** (out of scope Phase 2):
- Multi-signature approval (require 2+ keys)
- Key expiration (`expires_at` field exists in schema but not enforced)
- Hardware key support (YubiKey, etc.)

**Verdict**: Phase 2 provides single-key protection. Multi-key would require Phase 3+ enhancement.

---
