# CP-ARCH-001: Control Plane Architecture Overview

**Document ID**: CP-ARCH-001
**Version**: 1.0.0
**Status**: NORMATIVE
**Plane**: HO3

---

## 1. Purpose

This document defines the architectural principles, tier model, and core abstractions of the Control Plane. It is the entry point for humans and agents seeking to understand how governance, execution, and memory work together.

---

## 2. Core Principles

| Principle | Statement |
|-----------|-----------|
| **Ledger is Memory** | Agents have no persistent context windows. All memory is externalized to append-only ledgers. |
| **Immutable Installs** | Installed packages are never edited. Changes require new package versions. |
| **Factory Model** | The Control Plane builds applications. It does not self-modify during execution. |
| **Explicit Authority** | No action occurs without a declared Work Order and approval chain. |
| **Fail-Closed** | Any integrity, authorization, or dependency failure halts execution. |

---

## 3. Three-Tier Architecture

```
+------------------------------------------------------------------+
|                         HO3 (HOT)                                |
|                    Governance Tier                               |
|------------------------------------------------------------------|
|  Owns: Frameworks, Gates, Package Manager, Integrity Rules       |
|  Writes: L-INTENT, L-PACKAGE                                     |
|  Active Ledgers: 1 (governance.jsonl)                            |
|  Authority: Defines what CAN exist                               |
+------------------------------------------------------------------+
                              |
                              | governs
                              v
+------------------------------------------------------------------+
|                         HO2 (META)                               |
|                    Work Order Tier                               |
|------------------------------------------------------------------|
|  Owns: Work Orders, Session State, Coordination Agents           |
|  Writes: L-WORKORDER                                             |
|  Active Ledgers: Few (one per active session/project)            |
|  Authority: Defines what WILL happen                             |
+------------------------------------------------------------------+
                              |
                              | dispatches
                              v
+------------------------------------------------------------------+
|                         HO1 (FIRST)                              |
|                      Worker Tier                                 |
|------------------------------------------------------------------|
|  Owns: Execution Agents, Runtime Artifacts, Evidence             |
|  Writes: L-EXEC, L-EVIDENCE                                      |
|  Active Ledgers: Many (one per task/worker)                      |
|  Authority: Performs work within granted scope                   |
+------------------------------------------------------------------+
```

### 3.1 Tier Roles

| Tier | Name | Primary Role | May Reference |
|------|------|--------------|---------------|
| HO3 | Governance (HOT) | Define law, install packages, enforce integrity | Self only |
| HO2 | Work Order (META) | Coordinate work, manage sessions, approve tasks | HO3 |
| HO1 | Worker (FIRST) | Execute tasks, produce artifacts, record evidence | HO3, HO2 |

### 3.2 Tier Boundaries

| Constraint | Enforcement |
|------------|-------------|
| Lower tiers MUST NOT modify higher tiers | Gate: G0-TIER |
| Lower tiers MAY read higher tier interfaces | Explicit dependency declaration |
| Cross-tier writes require Work Order | Gate: G2-WORKORDER |

---

## 4. Ledger as Memory

Agents operate without persistent context windows. All state is externalized.

```
+------------------+         +------------------+
|     AGENT        |         |     LEDGER       |
|  (stateless)     | ------> |  (append-only)   |
|                  | <------ |                  |
|  - Reads ledger  |         |  - L-INTENT      |
|  - Performs act  |         |  - L-WORKORDER   |
|  - Writes entry  |         |  - L-EXEC        |
+------------------+         |  - L-EVIDENCE    |
                             +------------------+
```

### 4.1 Implications

| Implication | Consequence |
|-------------|-------------|
| No hidden state | All decisions are auditable via ledger |
| Resumable execution | Any agent can resume from ledger state |
| Deterministic replay | Same ledger inputs -> same outputs |
| Turn isolation | Each turn declares its inputs explicitly |

---

## 5. Semantic Exchange Model

Agents communicate via **prompt-shaped messages** with structured headers.

### 5.1 Required Prompt Header

```yaml
# Every agent prompt MUST include:
ledger_ids:
  - L-EXEC-20260202-001
artifact_ids:
  - ART-REQ-001
  - ART-DESIGN-002
versions:
  framework: FMWK-SDLC-100@1.0.0
  spec: SPEC-TRACE-001@1.2.0
work_order_id: WO-20260202-001
turn_number: 3
declared_inputs:
  - file: requirements.md
    hash: sha256:abc123...
  - ledger_entry: L-EXEC-20260202-001#42
```

### 5.2 Turn Isolation Contract

| Rule | Description |
|------|-------------|
| Declared inputs only | Agent may only reference artifacts listed in prompt header |
| No side-channel reads | Reading undeclared files is a gate violation |
| Output to ledger | All outputs recorded before next turn |

---

## 6. Factory Model

The Control Plane is a **factory** that builds applications. It does not self-modify.

```
+--------------------------------------------------------------+
|                     CONTROL PLANE (FACTORY)                  |
|                                                              |
|   +-----------+    +-----------+    +-----------+            |
|   | Frameworks|    |  Packages |    |   Gates   |            |
|   |   (LAW)   |--->|  (TOOLS)  |--->| (ENFORCE) |            |
|   +-----------+    +-----------+    +-----------+            |
|                          |                                   |
|                          v                                   |
|                    +-----------+                             |
|                    |   BUILDS  |                             |
|                    +-----------+                             |
|                          |                                   |
+--------------------------|-----------------------------------+
                           |
                           v
                  +-----------------+
                  |  APPLICATIONS   |
                  |    (BUILT)      |
                  |                 |
                  |  - Signed       |
                  |  - Immutable    |
                  |  - Cannot edit  |
                  |    factory      |
                  +-----------------+
```

### 6.1 Factory Invariants

| Invariant | Statement |
|-----------|-----------|
| F1 | Factory assets are installed via package manager only |
| F2 | Factory assets are never modified during execution |
| F3 | Applications are produced into RUNTIME space |
| F4 | Applications must be packaged to become authoritative |

---

## 7. Builder vs Built

A strict capability firewall separates the Control Plane (BUILDER) from its outputs (BUILT).

| Role | Description | Capabilities |
|------|-------------|--------------|
| **BUILDER** | Control Plane itself | Install packages, define frameworks, run gates |
| **BUILT** | Applications produced by Control Plane | Execute within sandbox, read interfaces, produce artifacts |

### 7.1 Firewall Rules

| BUILT is FORBIDDEN from: |
|--------------------------|
| Installing or uninstalling packages |
| Modifying framework LAW docs |
| Writing to HO3 ledgers |
| Signing packages |
| Approving Work Orders |
| Modifying gates |

See: **CP-FIREWALL-001** for complete specification.

---

## 8. Component Relationships

```
+------------------------------------------------------------------+
|                                                                  |
|   FRAMEWORK LAW          FRAMEWORK PACKAGE         SPEC PACK     |
|   (invariants)     --->  (agents, libs,     --->  (owned         |
|                          gates, prompts)          assets)        |
|         |                       |                     |          |
|         |                       |                     |          |
|         v                       v                     v          |
|   +-----------+          +-----------+         +-----------+     |
|   |  DEFINES  |          | INSTALLS  |         |   OWNS    |     |
|   |  allowed  |          |  to tiers |         |  specific |     |
|   |  behavior |          |  via PM   |         |   files   |     |
|   +-----------+          +-----------+         +-----------+     |
|         |                       |                     |          |
|         +-----------------------+-----------------------+        |
|                                 |                                |
|                                 v                                |
|                          +-----------+                           |
|                          |   GATES   |                           |
|                          |  enforce  |                           |
|                          | integrity |                           |
|                          +-----------+                           |
|                                 |                                |
|                                 v                                |
|                          +-----------+                           |
|                          |  LEDGER   |                           |
|                          |  records  |                           |
|                          |   all     |                           |
|                          +-----------+                           |
|                                                                  |
+------------------------------------------------------------------+
```

---

## 9. Two Spaces

| Space | Mutability | Authority | Gate Visibility |
|-------|------------|-----------|-----------------|
| **INSTALLED** | Immutable | Authoritative | Gates enforce |
| **RUNTIME** | Mutable | Non-authoritative | Gates ignore |

### 9.1 Promotion Path

```
RUNTIME (draft) --> PACKAGE --> WORK ORDER --> APPROVAL --> INSTALL --> INSTALLED (authoritative)
```

---

## 10. Glossary

| Term | Definition |
|------|------------|
| **Framework** | LAW doc + Package defining governance rules and tools |
| **Package** | Installable unit containing assets with manifest + signature |
| **Spec Pack** | Package defining ownership of specific files |
| **Gate** | Validation checkpoint that fails closed on violation |
| **Ledger** | Append-only log serving as externalized memory |
| **Work Order** | Authorized unit of work with declared scope |
| **Tier** | Hierarchical level (HO3 > HO2 > HO1) with distinct authority |

---

## References

- CP-PKG-001: Framework & Package Model Specification
- CP-LEDGER-001: Tiered Ledger Model
- CP-FIREWALL-001: Builder vs Built Firewall
