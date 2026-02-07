# PHASE-02_PLAYBOOK.md

**Version**: 1.0.0
**Date**: 2026-02-03
**Audience**: Human operators and AI agents

---

## Overview

This playbook describes how to operate the Phase 2 G2 WORK_ORDER gate system. It covers:

1. Approving Work Orders (human only)
2. Running gates
3. Checking provenance
4. Rebuilding registries
5. Troubleshooting failures

---

## 1. How a Human Approves a Work Order

### Prerequisites

1. **Ed25519 keypair**: Generate if not exists
   ```bash
   python3 scripts/wo_keygen.py
   ```
   This creates `~/.control_plane_v2/private_key.pem`

2. **Register public key**: Add to `config/trusted_keys.json`
   ```json
   {
     "keys": [{
       "key_id": "your-key-id",
       "algorithm": "Ed25519",
       "public_key_b64": "<output from wo_keygen.py>",
       "roles": ["wo_approver"]
     }]
   }
   ```

### Approval Process

**Step 1**: Create Work Order file
```bash
# Create WO file at work_orders/ho3/WO-YYYYMMDD-NNN.json
cat > work_orders/ho3/WO-20260203-001.json << 'EOF'
{
  "work_order_id": "WO-20260203-001",
  "type": "code_change",
  "plane_id": "ho3",
  "spec_id": "SPEC-CORE-001",
  "framework_id": "FMWK-000",
  "scope": {
    "allowed_files": ["lib/paths.py"],
    "forbidden_files": []
  },
  "acceptance": {
    "tests": ["pytest tests/test_paths.py"],
    "checks": []
  }
}
EOF
```

**Step 2**: Review the Work Order
- Verify `spec_id` owns the files in `allowed_files`
- Verify `framework_id` governs the spec
- Verify acceptance tests are appropriate

**Step 3**: Sign and approve
```bash
python3 scripts/wo_approve.py \
  --wo work_orders/ho3/WO-20260203-001.json \
  --key-file ~/.control_plane_v2/private_key.pem \
  --reason "Approved: fixes path resolution bug per issue #42"
```

**Output**: WO_APPROVED event written to `ledger/governance.jsonl`

**Step 4**: Verify approval
```bash
python3 scripts/wo_verify.py --wo-id WO-20260203-001
```

### What Agents CANNOT Do

- Agents MUST NOT have access to Ed25519 private keys
- Agents MUST NOT call `wo_approve.py`
- Agents MAY propose Work Orders (create the JSON file)
- Agents MAY execute approved Work Orders via `apply_work_order.py`

---

## 2. How Gates Run

### Single Gate Execution

```bash
# Run G2 gate only
python3 scripts/gate_check.py --gate G2 \
  --wo WO-20260203-001 \
  --wo-file work_orders/ho3/WO-20260203-001.json \
  --skip-signature  # Only for testing; remove in production
```

### Full Gate Sequence

```bash
# Run all gates (G0A, G0B, G1, G2)
python3 scripts/gate_check.py --all --enforce
```

### Work Order Execution

```bash
# Execute approved Work Order (runs G2 internally)
python3 scripts/apply_work_order.py --wo WO-20260203-001
```

**Execution flow**:
```
1. Load WO file
2. Run G2 (approval, signature, idempotency, scope)
   └─ If G2 fails → EXIT with error
3. Write WO_RECEIVED to HO2
4. Create isolated workspace
5. Run G0B, G1, G3, G4 in workspace
   └─ If any fails → discard workspace, EXIT
6. Atomic apply (write files, update registries)
7. Write WO_COMPLETED to HO2
8. Write WO_ATTESTATION to HOT
9. EXIT success
```

### Gate Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All gates passed (or NO_OP for idempotent retry) |
| 1 | Gate failure (check stdout for details) |
| 2 | Invalid arguments or configuration error |

---

## 3. How Provenance Is Checked

### Manual Chain Verification

**Step 1**: Find HOT approval
```bash
grep "WO-20260203-001" ledger/governance.jsonl | grep WO_APPROVED
```
Extract: `entry_hash` (this is the HOT approval hash)

**Step 2**: Verify HO2 references HOT
```bash
grep "WO-20260203-001" planes/ho2/ledger/workorder.jsonl | grep WO_RECEIVED
```
Verify: `hot_approval_hash` matches HOT `entry_hash`

**Step 3**: Find session linkage
```bash
grep "WO-20260203-001" planes/ho1/sessions/*/ledger/session.jsonl | grep SESSION_START
```
Verify: `wo_instance_hash` matches HO2 instance ledger hash

**Step 4**: Verify attestation
```bash
grep "WO-20260203-001" ledger/governance.jsonl | grep WO_ATTESTATION
```
Verify: `ho2_completion_hash` matches HO2 WO_COMPLETED `entry_hash`

### Programmatic Verification

```python
from lib.ledger_client import LedgerClient
from pathlib import Path

# Load ledgers
hot = LedgerClient(ledger_path=Path('ledger/governance.jsonl'))
ho2 = LedgerClient(ledger_path=Path('planes/ho2/ledger/workorder.jsonl'))

# Find approval
approvals = [e for e in hot.read_all() if e.event_type == 'WO_APPROVED' and e.submission_id == 'WO-20260203-001']
approval = approvals[-1]  # Latest

# Find received
received = [e for e in ho2.read_all() if e.event_type == 'WO_RECEIVED' and e.submission_id == 'WO-20260203-001']
recv = received[-1]

# Verify chain
assert recv.metadata['hot_approval_hash'] == approval.entry_hash, "Chain broken!"
print("Provenance verified")
```

---

## 4. How Registries Are Rebuilt

### When to Rebuild

Rebuild derived registries when:
- Package installed/uninstalled
- Baseline package updated
- Registry corruption suspected

### Rebuild Command

```bash
python3 scripts/rebuild_derived_registries.py --plane ho3
```

**What it rebuilds**:
- `registries/file_ownership.csv` — from package manifests
- `registries/packages_state.csv` — from ledger entries
- `registries/compiled/file_ownership.json` — JSON version
- `registries/compiled/packages.json` — JSON version

### Verify Rebuild

```bash
# Check file counts
wc -l registries/file_ownership.csv
# Expected: 135 (134 files + header)

# Verify no orphans
python3 scripts/gate_check.py --gate G0B --enforce
# Expected: G0B PASSED: 134 files owned, 0 orphans
```

### What NOT to Do

- **NEVER** edit `registries/compiled/*.json` directly
- **NEVER** edit `registries/file_ownership.csv` directly (except via rebuild)
- Curated registries (`control_plane_registry.csv`, `specs_registry.csv`) require Work Order

---

## 5. Common Failure Patterns and Fixes

### F1: "No WO_APPROVED found"

**Symptom**:
```
G2: FAIL
  No WO_APPROVED found for WO-20260203-001
```

**Cause**: Work Order not approved yet

**Fix**: Run `wo_approve.py` as human operator

---

### F2: "Hash mismatch" / "TAMPERING"

**Symptom**:
```
G2: FAIL
  TAMPERING DETECTED: hash mismatch
  Expected: sha256:abc123...
  Got: sha256:def456...
```

**Cause**: WO file modified after approval

**Fix**:
1. Restore original WO file from git
2. Or: Create new WO with new ID and re-approve

---

### F3: "Replay variant detected"

**Symptom**:
```
G2: FAIL
  Replay variant: WO-20260203-001 already completed with different hash
```

**Cause**: Trying to reuse WO ID for different content

**Fix**: Create new WO with new ID (e.g., `WO-20260203-002`)

---

### F4: "Signature verification failed"

**Symptom**:
```
G2: FAIL
  Signature verification failed for key admin-001
```

**Cause**:
- Wrong key used to sign
- Public key in `trusted_keys.json` doesn't match private key
- Corrupted signature

**Fix**:
1. Verify key ID matches
2. Re-sign with correct private key
3. Check `trusted_keys.json` has correct public key

---

### F5: "ORPHAN: scripts/new_script.py"

**Symptom**:
```
G0B: FAIL
  10 orphans detected
  ERROR: ORPHAN: scripts/new_script.py
```

**Cause**: File exists but not registered in `file_ownership.csv`

**Fix**:
1. Add file to package manifest
2. Rebuild derived registries
3. Or: Remove orphan file if unintended

---

### F6: "Spec not found"

**Symptom**:
```
G2: FAIL
  Spec SPEC-UNKNOWN-001 not found in specs_registry.csv
```

**Cause**: WO references non-existent spec

**Fix**: Correct `spec_id` in WO file to valid spec

---

### F7: Idempotent NO_OP (not a failure)

**Symptom**:
```
G2: PASS (NO_OP)
  Work Order already applied (idempotent)
```

**Cause**: WO already executed successfully

**Action**: No action needed. This is expected behavior for retries.

---

## Quick Reference

### Files

| File | Purpose |
|------|---------|
| `scripts/wo_approve.py` | Human approval CLI |
| `scripts/wo_verify.py` | Verify approval signature |
| `scripts/wo_keygen.py` | Generate Ed25519 keypair |
| `scripts/g2_gate.py` | G2 gate implementation |
| `scripts/gate_check.py` | Run gates |
| `scripts/apply_work_order.py` | Execute approved WO |
| `scripts/rebuild_derived.py` | Rebuild derived registries |
| `config/trusted_keys.json` | Trusted public keys |
| `config/registry_policy.json` | Curated vs derived classification |
| `ledger/governance.jsonl` | HOT ledger (approvals, attestations) |
| `planes/ho2/ledger/workorder.jsonl` | HO2 ledger (received, completed) |

### Commands Cheatsheet

```bash
# Generate keypair
python3 scripts/wo_keygen.py

# Approve WO (human only)
python3 scripts/wo_approve.py --wo <path> --key-file <key> --reason "<reason>"

# Verify approval
python3 scripts/wo_verify.py --wo-id <WO-ID>

# Run G2 gate
python3 scripts/gate_check.py --gate G2 --wo <WO-ID> --wo-file <path>

# Run all gates
python3 scripts/gate_check.py --all --enforce

# Execute WO
python3 scripts/apply_work_order.py --wo <WO-ID>

# Rebuild registries
python3 scripts/rebuild_derived_registries.py --plane ho3

# Check for orphans
python3 scripts/gate_check.py --gate G0B --enforce
```

---

## Agent Guidelines

### What Agents CAN Do

1. Create Work Order JSON files (propose changes)
2. Run `gate_check.py` to validate
3. Run `apply_work_order.py` for approved WOs
4. Run `rebuild_derived_registries.py`
5. Query ledgers for provenance
6. Run tests

### What Agents CANNOT Do

1. Sign Work Orders (`wo_approve.py`)
2. Access Ed25519 private keys
3. Directly edit curated registries
4. Directly edit derived registries
5. Bypass gates

### Agent Workflow

```
1. Receive task requiring code change
2. Identify affected files
3. Look up owning Spec via file_ownership.csv
4. Create WO JSON with correct spec_id, scope
5. Notify human: "WO ready for approval"
6. WAIT for human approval
7. Run: apply_work_order.py --wo <WO-ID>
8. Verify: gate_check.py --all
9. Report completion
```
