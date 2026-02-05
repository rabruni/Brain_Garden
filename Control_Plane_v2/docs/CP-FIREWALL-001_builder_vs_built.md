# CP-FIREWALL-001: Builder vs Built Firewall

**Document ID**: CP-FIREWALL-001
**Version**: 1.1.0
**Status**: NORMATIVE
**Plane**: HO3
**Amended**: 2026-02-04 (Added ADMIN role)

---

## 1. Purpose

This document specifies the capability firewall separating the Control Plane (BUILDER) from applications it produces (BUILT). The firewall prevents BUILT artifacts from modifying the factory that created them.

---

## 2. Definitions

| Term | Definition |
|------|------------|
| **BUILDER** | The Control Plane: installed packages, gates, package manager |
| **BUILT** | Applications, agents, and artifacts produced by the Control Plane (Residents) |
| **ADMIN** | Infrastructure-level observer agents with crosscutting read access (Managers) |
| **Firewall** | Capability boundary enforced by gates |
| **Promotion** | Process of moving BUILT artifact to BUILDER (requires approval) |

---

## 3. Role Separation

```
+------------------------------------------------------------------+
|                         BUILDER                                  |
|                    (Control Plane)                               |
|                                                                  |
|   Capabilities:                                                  |
|   [x] Install/uninstall packages                                 |
|   [x] Define and modify frameworks                               |
|   [x] Run and modify gates                                       |
|   [x] Sign packages                                              |
|   [x] Approve Work Orders                                        |
|   [x] Write to HO3 ledgers                                       |
|                                                                  |
+------------------------------------------------------------------+
                              |
                              | produces
                              | (one-way)
                              v
+------------------------------------------------------------------+
|                          BUILT                                   |
|                 (Applications / Residents)                       |
|                                                                  |
|   Capabilities:                                                  |
|   [x] Execute within sandbox                                     |
|   [x] Read installed interfaces                                  |
|   [x] Write to RUNTIME space                                     |
|   [x] Write to HO1 ledgers (L-EXEC, L-EVIDENCE)                  |
|   [x] Propose Work Orders (not approve)                          |
|                                                                  |
|   FORBIDDEN:                                                     |
|   [ ] Modify BUILDER                                             |
|   [ ] Self-promote to BUILDER                                    |
|                                                                  |
+------------------------------------------------------------------+

                    OBSERVED BY (crosscutting)

+------------------------------------------------------------------+
|                          ADMIN                                   |
|              (Infrastructure / Managers)                         |
|                                                                  |
|   Capabilities:                                                  |
|   [x] Read all tiers (CAP_READ_ALL)                              |
|   [x] Write to ADMIN namespace only (CAP_AUDIT_WRITE)            |
|   [x] Log observations to L-OBSERVE                              |
|                                                                  |
|   FORBIDDEN:                                                     |
|   [ ] Modify BUILDER                                             |
|   [ ] Modify BUILT                                               |
|   [ ] Invoke other agents                                        |
|   [ ] Write to any tier ledger                                   |
|                                                                  |
|   Runtime: Control Plane runtime (not Resident runtime)          |
|   Namespace: planes/admin/                                       |
|                                                                  |
+------------------------------------------------------------------+
```

---

## 4. BUILT Signing

### 4.1 BUILT Marker

All BUILT artifacts are signed with a marker indicating their origin:

```json
{
  "artifact_id": "APP-OUTPUT-001",
  "origin": "BUILT",
  "produced_by": "PKG-FMWK-SDLC-100",
  "work_order_id": "WO-20260202-001",
  "timestamp": "2026-02-02T12:00:00Z",
  "signature": "base64:...",
  "signed_by": "builder_key"
}
```

### 4.2 Marker Requirements

| Field | Requirement |
|-------|-------------|
| `origin` | MUST be "BUILT" |
| `produced_by` | MUST reference installed package |
| `work_order_id` | MUST reference approved Work Order |
| `signature` | MUST be verifiable against builder key |

---

## 5. Forbidden Actions for BUILT

### 5.1 Complete Prohibition List

| Action | Gate | Failure Message |
|--------|------|-----------------|
| Install package | G-FIREWALL | "BUILT cannot install packages" |
| Uninstall package | G-FIREWALL | "BUILT cannot uninstall packages" |
| Modify framework LAW doc | G-FIREWALL | "BUILT cannot modify frameworks" |
| Modify gate implementation | G-FIREWALL | "BUILT cannot modify gates" |
| Sign packages | G-FIREWALL | "BUILT cannot sign packages" |
| Approve Work Orders | G-FIREWALL | "BUILT cannot approve work orders" |
| Write to L-INTENT | G-FIREWALL | "BUILT cannot write to L-INTENT" |
| Write to L-PACKAGE | G-FIREWALL | "BUILT cannot write to L-PACKAGE" |
| Write to L-WORKORDER (approve) | G-FIREWALL | "BUILT cannot approve work orders" |
| Modify HO3 files | G-FIREWALL | "BUILT cannot modify HO3" |
| Modify HO2 files (except allowed) | G-FIREWALL | "BUILT cannot modify HO2" |
| Access external keyring | G-FIREWALL | "BUILT cannot access signing keys" |

### 5.2 Allowed Actions for BUILT

| Action | Ledger | Constraint |
|--------|--------|------------|
| Execute tasks | L-EXEC | Within Work Order scope |
| Produce artifacts | RUNTIME | Non-authoritative |
| Record evidence | L-EVIDENCE | Within Work Order scope |
| Propose Work Orders | L-WORKORDER | Status=PROPOSED only |
| Read installed interfaces | - | Read-only |

---

## 6. Gate: G-FIREWALL

### 6.1 Trigger

G-FIREWALL runs before any write operation.

### 6.2 Check Sequence

```
G-FIREWALL(operation, actor, target):

  1. Identify actor origin
     IF actor.origin == "ADMIN":
       GOTO admin_checks
     IF actor.origin == "BUILT":
       GOTO built_checks
     ELSE:
       PASS (BUILDER has full access)

  ADMIN_CHECKS:
  1a. ADMIN may only READ or WRITE to admin namespace
      IF operation == READ:
        PASS (CAP_READ_ALL granted)
      IF operation == WRITE AND target.namespace == "admin":
        PASS (CAP_AUDIT_WRITE granted)
      IF operation == WRITE AND target.namespace != "admin":
        FAIL "ADMIN cannot write outside admin namespace"
      IF operation IN [INVOKE_AGENT]:
        FAIL "ADMIN cannot invoke other agents"
      FAIL "ADMIN cannot perform {operation}"

  BUILT_CHECKS:
  2. Check operation type
     IF operation IN [INSTALL, UNINSTALL, MODIFY_FRAMEWORK,
                      MODIFY_GATE, SIGN_PACKAGE, APPROVE_WO]:
       FAIL "BUILT cannot perform {operation}"

  3. Check target tier
     IF target.tier == HO3:
       FAIL "BUILT cannot modify HO3"
     IF target.tier == HO2 AND operation != PROPOSE_WO:
       FAIL "BUILT cannot modify HO2"

  4. Check ledger access
     IF target.ledger IN [L-INTENT, L-PACKAGE]:
       FAIL "BUILT cannot write to {ledger}"
     IF target.ledger == L-WORKORDER AND operation == APPROVE:
       FAIL "BUILT cannot approve work orders"

  5. PASS
```

---

## 7. Human Override

### 7.1 Override Conditions

The firewall MAY be overridden by explicit human approval:

| Override Type | Requirement |
|---------------|-------------|
| Emergency access | Two-person approval + audit log |
| Promotion to BUILDER | Work Order + review + signature |
| Temporary elevation | Time-limited, logged, revocable |

### 7.2 Override Procedure

1. Human creates Work Order with `type: firewall_override`
2. Second human approves Work Order
3. Override scope explicitly enumerated
4. Override logged to L-INTENT
5. Time limit enforced (max 24 hours)
6. Automatic revocation at expiry

### 7.3 Override Logging

```json
{
  "entry_id": "INTENT-20260202-120000-001",
  "event_type": "FIREWALL_OVERRIDE",
  "override_type": "promotion | emergency | elevation",
  "scope": ["specific", "actions", "allowed"],
  "approved_by": ["user1", "user2"],
  "expires_at": "2026-02-03T12:00:00Z",
  "work_order_id": "WO-20260202-001"
}
```

---

## 8. Promotion Path

### 8.1 BUILT to BUILDER Promotion

BUILT artifacts may become BUILDER artifacts only through:

```
BUILT artifact
    |
    v
Package (with manifest + signature)
    |
    v
Work Order (type: package_install)
    |
    v
Human approval
    |
    v
Gate validation (G0, G-INTEGRITY)
    |
    v
Package manager install
    |
    v
BUILDER artifact (installed)
```

### 8.2 Promotion Requirements

| Requirement | Check |
|-------------|-------|
| Artifact packaged | Manifest exists with valid schema |
| Artifact signed | Signature verifies against keyring |
| Work Order approved | Human approval recorded |
| Gates pass | G0-PACKAGE, G0-SPEC, G-INTEGRITY |
| Dependencies satisfied | All deps installed |

---

## 9. Anti-Recursion

### 9.1 Principle

BUILT MUST NOT be able to modify the rules that govern it.

### 9.2 Anti-Recursion Rules

| Rule | Statement |
|------|-----------|
| AR1 | BUILT cannot modify gate implementations |
| AR2 | BUILT cannot modify firewall rules |
| AR3 | BUILT cannot grant itself BUILDER capabilities |
| AR4 | BUILT cannot modify its own BUILT marker |
| AR5 | BUILT cannot forge BUILDER signatures |

### 9.3 Enforcement

Anti-recursion is enforced at multiple levels:

| Level | Mechanism |
|-------|-----------|
| Gate | G-FIREWALL rejects forbidden operations |
| Signature | BUILDER signatures cannot be forged |
| Keyring | Signing keys inaccessible to BUILT |
| Ledger | Append-only prevents history modification |

---

## 10. Future: Agent Self-Promotion

### 10.1 Current State (v1)

- BUILT agents MUST NOT self-promote
- All promotion requires human approval
- Work Order approval is human-only

### 10.2 Future State (v2+)

Design allows for authorized agent self-promotion with:

| Safeguard | Purpose |
|-----------|---------|
| Capability tokens | Time-limited, scope-limited |
| Multi-agent approval | N-of-M agents must agree |
| Audit trail | All actions logged |
| Revocation | Instant revoke capability |

### 10.3 Preserved Fields

Current schema includes fields for future use:

```json
{
  "installed_by": "human@org | agent_id",
  "approval_type": "human | agent_quorum | capability_token",
  "capability_token_id": null
}
```

---

## 11. Observer Role (ADMIN)

### 11.1 Purpose

ADMIN agents provide infrastructure-level observation, audit, and assistance capabilities. They exist outside the BUILDER/BUILT hierarchy and serve as crosscutting managers of the Control Plane.

### 11.2 Classification

| Property | Value |
|----------|-------|
| Agent Class | `system` |
| Runtime | Control Plane runtime (not Resident runtime) |
| Namespace | `planes/admin/` |
| Manifest Field | `"agent_class": "system"` |

### 11.3 ADMIN Capabilities

| Capability | Granted | Description |
|------------|---------|-------------|
| `CAP_READ_ALL` | Yes | Read any file in any tier |
| `CAP_AUDIT_WRITE` | Yes | Write to ADMIN namespace only |
| `CAP_WRITE_BUILDER` | No | Cannot modify BUILDER artifacts |
| `CAP_WRITE_BUILT` | No | Cannot modify BUILT artifacts |
| `CAP_INVOKE_AGENT` | No | Cannot invoke other agents |

### 11.4 ADMIN Namespace

ADMIN agents write only to their isolated namespace:

```
planes/admin/
├── ho1/                    # ADMIN execution memory (stateless)
│   └── ledger/
│       └── exec.jsonl
├── ho2/                    # ADMIN session memory (conversation)
│   └── ledger/
│       └── session-{id}.jsonl
└── ho3/                    # ADMIN learning memory (patterns)
    └── ledger/
        └── insights.jsonl
```

### 11.5 Observation Logging (L-OBSERVE)

When ADMIN reads from a tier, it logs to that tier's observe ledger:

```json
{
  "entry_id": "OBS-20260204-220000-001",
  "event_type": "ADMIN_READ",
  "agent_id": "admin",
  "session_id": "SES-20260204-xxx",
  "files_read": ["ledger/governance.jsonl"],
  "timestamp": "2026-02-04T22:00:00Z",
  "prev_hash": "sha256:...",
  "entry_hash": "sha256:..."
}
```

Each tier maintains its own `observe.jsonl`:
- `planes/ho3/ledger/observe.jsonl` (or `ledger/observe.jsonl`)
- `planes/ho2/ledger/observe.jsonl`
- `planes/ho1/ledger/observe.jsonl`

### 11.6 Standing Authorization

ADMIN agents operate under standing work order authorization:

```json
{
  "work_order_id": "WO-ADMIN-OBSERVE-001",
  "type": "standing_authorization",
  "agent_class": "system",
  "scope": {
    "allowed_actions": ["read_all_tiers", "write_own_namespace", "log_observations"],
    "forbidden_actions": ["modify_builder", "modify_built", "invoke_agents"]
  },
  "expires": null,
  "approved_by": ["governance_bootstrap"]
}
```

### 11.7 Turn Isolation for ADMIN

ADMIN agents use post-declaration rather than pre-declaration:

| Resident Agents | ADMIN Agents |
|-----------------|--------------|
| Pre-declare inputs in prompt header | Post-declare via L-OBSERVE logging |
| Constrained reads (violation if undeclared) | Logged reads (violation if unlogged) |
| Scoped capability | `CAP_READ_ALL` capability |

### 11.8 Firewall Preservation

ADMIN does not violate the BUILDER/BUILT firewall because:

| Check | Status |
|-------|--------|
| ADMIN cannot modify BUILDER | Enforced - no write capability |
| ADMIN cannot modify BUILT | Enforced - no write capability |
| ADMIN writes only to own namespace | Enforced - `planes/admin/` isolation |
| ADMIN cannot invoke agents | Enforced - `CAP_INVOKE_AGENT=false` |
| ADMIN is more write-restricted than BUILT | True - BUILT can write HO1, ADMIN cannot |

### 11.9 ADMIN Examples

| Agent | Purpose | Capabilities Used |
|-------|---------|-------------------|
| Admin Agent | Explain system, answer queries | `CAP_READ_ALL`, `CAP_AUDIT_WRITE` |
| Monitor Agent | Track health, performance | `CAP_READ_ALL`, `CAP_AUDIT_WRITE` |
| Security Agent | Audit access, detect anomalies | `CAP_READ_ALL`, `CAP_AUDIT_WRITE` |
| Trust Agent | Verify integrity, validate chains | `CAP_READ_ALL`, `CAP_AUDIT_WRITE` |

### 11.10 ADMIN vs BUILT Summary

```
Write Hierarchy:

BUILDER:  [████████████████████] Full write access
BUILT:    [████████░░░░░░░░░░░░] Scoped to HO1 + RUNTIME
ADMIN:    [██░░░░░░░░░░░░░░░░░░] Own namespace only

Read Hierarchy:

BUILDER:  [████████████████████] Full read access
BUILT:    [████████░░░░░░░░░░░░] Scoped reads
ADMIN:    [████████████████████] Full read access (crosscutting)
```

ADMIN is a **watchtower outside the walls**, not a hole in the firewall.

---

## References

- CP-ARCH-001: Control Plane Architecture Overview
- CP-PKG-001: Framework & Package Model Specification
- CP-LEDGER-001: Tiered Ledger Model
