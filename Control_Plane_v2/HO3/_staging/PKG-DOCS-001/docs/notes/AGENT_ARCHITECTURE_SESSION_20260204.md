# Agent Architecture Design Session
**Date**: 2026-02-04
**Status**: LOCKED
**Outcome**: Complete agent classification model for Control Plane

---

## Executive Summary

This session established the complete agent architecture for the Control Plane, defining three primary agent classes and their relationships. The key insight is that the Control Plane represents **Cognition** while Residents represent **Senses**.

---

## Agent Classification Model

```
┌─────────────────────────────────────────────────────────────────┐
│                         KERNEL                                   │
│                      (Cognition)                                 │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              KERNEL.syntactic                           │   │
│   │                                                         │   │
│   │   trace.py    merkle.py    gates    hash chains         │   │
│   │                                                         │   │
│   │   - Pure code, deterministic                            │   │
│   │   - No LLM, no drift possible                           │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              KERNEL.semantic                            │   │
│   │                                                         │   │
│   │   Router      Attention      Wisdom      Meta/HOT       │   │
│   │                                                         │   │
│   │   - Controlled one-shot prompts                         │   │
│   │   - Strict JSON formats                                 │   │
│   │   - Logged to ledgers, reads ledgers                    │   │
│   │   - NOT human-interactive                               │   │
│   │   - Drift controlled via structure                      │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
              coordinates     │     coordinates
         ┌────────────────────┴────────────────────┐
         │                                         │
         ▼                                         ▼
┌─────────────────────┐                 ┌─────────────────────┐
│       ADMIN         │                 │     RESIDENT        │
│    (Managers)       │                 │     (Senses)        │
├─────────────────────┤                 ├─────────────────────┤
│  Admin Agent        │                 │  Worker Agents      │
│  Monitor Agent      │                 │  Application Agents │
│  Security Agent     │                 │  Task Executors     │
│  Trust Agent        │                 │                     │
│                     │                 │                     │
│  - Human-facing     │                 │  - Task-facing      │
│  - Crosscutting     │                 │  - Work order bound │
│  - Observers        │                 │  - Scoped access    │
└─────────────────────┘                 └─────────────────────┘
```

---

## Class Definitions

### KERNEL.syntactic

| Property | Value |
|----------|-------|
| Nature | Pure code, deterministic |
| LLM Usage | None |
| Drift Risk | None |
| Examples | trace.py, merkle.py, gates, hash chains |
| Human-Interactive | No |
| Runtime | Control Plane core |

### KERNEL.semantic

| Property | Value |
|----------|-------|
| Nature | Controlled LLM, one-shot prompts |
| LLM Usage | Yes - strictly controlled |
| Drift Risk | Controlled via structure |
| Examples | Router, Attention, Wisdom, Meta/HOT agents |
| Human-Interactive | No |
| Runtime | Control Plane core |
| Prompt Format | Registered, hashed, strict JSON |
| State | Stateless (memory in ledgers) |

### ADMIN (Managers)

| Property | Value |
|----------|-------|
| Nature | Crosscutting observers |
| LLM Usage | Yes - for user interaction |
| Examples | Admin Agent, Monitor Agent, Security Agent, Trust Agent |
| Human-Interactive | Yes |
| Runtime | Control Plane runtime (separate from Residents) |
| Namespace | `planes/admin/` (or OS-separated `/opt/control_plane_admin/`) |
| Capabilities | CAP_READ_ALL, CAP_AUDIT_WRITE |
| Memory Model | HO1 (execution), HO2 (session), HO3 (learning) |

### RESIDENT (Senses)

| Property | Value |
|----------|-------|
| Nature | Task executors, perception + action |
| LLM Usage | Yes - within work order scope |
| Examples | Worker agents, Application agents |
| Human-Interactive | Task-dependent |
| Runtime | Resident runtime (separate from Control Plane) |
| Namespace | `planes/ho1/`, `planes/ho2/` |
| Capabilities | Scoped per work order |
| Memory Model | HO1 only (stateless execution) |
| Work Orders | Required for any action |

---

## The Three Concerns (Resolved)

### Concern 1: Work Orders for ADMIN

**Problem**: ADMIN queries don't have work orders.

**Resolution**: ADMIN operates under **standing authorization**. This exception applies ONLY to system agents (ADMIN class), not Residents. The classification is immutable (set at package install, verified by gate).

```json
{
  "work_order_id": "WO-ADMIN-OBSERVE-001",
  "type": "standing_authorization",
  "agent_class": "system",
  "scope": {
    "allowed_actions": ["read_all_tiers", "write_own_namespace"],
    "forbidden_actions": ["modify_builder", "modify_built", "invoke_agents"]
  },
  "expires": null
}
```

**Boundary Protection**:
- Classification at install time (manifest + gate)
- Capabilities package-bound, not runtime-requestable
- ADMIN cannot invoke Residents
- Residents cannot invoke ADMIN
- Exception cannot leak to Resident class

### Concern 2: Turn Isolation for ADMIN

**Problem**: ADMIN reads files dynamically, cannot pre-declare.

**Resolution**: ADMIN uses **post-declaration** instead of pre-declaration.

| Resident Agents | ADMIN Agents |
|-----------------|--------------|
| Pre-declare inputs in prompt header | Post-declare via L-OBSERVE logging |
| Constrained reads (violation if undeclared) | Logged reads (violation if unlogged) |
| Scoped capability | CAP_READ_ALL capability |

Both achieve auditability. The mechanism differs based on agent class.

### Concern 3: ADMIN is Neither BUILDER nor BUILT

**Problem**: CP-FIREWALL-001 defined only two categories.

**Resolution**: ADMIN is a valid third category because the firewall protects against **modification**, not observation.

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

ADMIN is **more write-restricted than BUILT**. It's a watchtower outside the walls, not a hole in the firewall.

---

## Memory Model (Anti-Drift Design)

### The HO Levels

| Level | Memory Type | Cognitive Altitude | Purpose |
|-------|-------------|-------------------|---------|
| HO1 | Fast / None | First Order | Execute, no memory = no drift |
| HO2 | Slow | Second Order | Meta-aware, session memory |
| HO3 | Learning | Higher Order | Wisdom accumulation |

### Anti-Drift Principle

```
HO1 Agent executes:
├── Has NO memory of what it did
├── If it retries → same inputs = same behavior
├── Cannot drift because it cannot remember
└── Ledger is FOR OTHERS to read, not for the agent

HO2 Agent coordinates:
├── Knows the OUTCOME it's seeking
├── Meta-aware: "Is this working?"
├── Memory is scoped to work order/session
└── Reads L-EXEC from HO1

HO3 learns:
├── Sees patterns across work orders
├── Can evolve frameworks
├── Long-term strategic memory
└── This is where wisdom accumulates
```

### Key Insight: Agents Don't REMEMBER, They READ

```
Traditional:  Agent.memory["user_name"] = "Ray"  ← mutable, can drift
HO Model:     ledger.read("L-EXEC", turn=1)      ← immutable, verified
```

---

## ADMIN Namespace and HO Stack

ADMIN gets the same HO architecture in its own isolated namespace:

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

Plus breadcrumbs at each observed tier:
```
planes/ho3/ledger/observe.jsonl  ← "Admin session X read governance.jsonl"
planes/ho2/ledger/observe.jsonl  ← "Admin session X read workorder.jsonl"
planes/ho1/ledger/observe.jsonl  ← "Admin session X read session Y"
```

---

## OS-Level Separation (Defense in Depth)

### Proposed Structure

```
/opt/control_plane/              # Owner: cp_service:cp_group (750)
├── ledger/                      # HO3 governance
├── installed/                   # Packages
└── planes/
    ├── ho1/                     # Residents
    └── ho2/                     # Work orders

/opt/control_plane_admin/        # Owner: cp_admin:cp_admin (700)
├── ho1/                         # Admin execution ledger
├── ho2/                         # Admin session ledger
├── ho3/                         # Admin learning ledger
├── scripts/                     # Admin scripts (chat.py, etc.)
├── lib/                         # Admin libraries
└── modules/
    └── admin_agent/             # Admin agent module

/opt/control_plane_observe/      # Owner: cp_observe:cp_observe (750)
├── ho1_observe.jsonl            # L-OBSERVE from HO1
├── ho2_observe.jsonl            # L-OBSERVE from HO2
└── ho3_observe.jsonl            # L-OBSERVE from HO3
```

### Security Domains

| Domain | User | Contains |
|--------|------|----------|
| cp_service | Control Plane service | KERNEL + Residents |
| cp_admin | Admin agents | ADMIN namespace + code |
| cp_observe | Observation logs | L-OBSERVE (append-only) |

---

## KERNEL.semantic Control Pattern

All semantic kernel agents use controlled one-shot prompts:

```python
# Pattern for KERNEL.semantic agents
response = llm.complete(
    prompt=GOVERNED_PROMPT,           # Registered, hashed
    input=strict_json_input,          # Schema-validated
    output_format="strict_json",      # No freeform
    max_tokens=limited,               # Bounded
    temperature=0,                    # Deterministic
)

# Immediately logged
ledger.write({
    "prompt_id": "PRM-ROUTER-001",
    "input_hash": hash(input),
    "output_hash": hash(response),
    "timestamp": now()
})

# No memory between calls = no drift
```

### Constraints for KERNEL.semantic

| Constraint | Purpose |
|------------|---------|
| One-shot only | No multi-turn = no drift accumulation |
| Strict JSON | No freeform = parseable, verifiable |
| Registered prompts | Governance over prompt content |
| Logged I/O | Full audit trail |
| No human interaction | Internal only = no prompt injection |
| Stateless | Memory in ledgers, not in agent |
| Temperature 0 | Deterministic responses |

---

## Capability Matrix

| Agent Class | CAP_READ_ALL | CAP_AUDIT_WRITE | CAP_ROUTE | CAP_ATTENTION | CAP_INVOKE_AGENT |
|-------------|--------------|-----------------|-----------|---------------|------------------|
| KERNEL.syntactic | N/A (code) | N/A (code) | N/A | N/A | N/A |
| KERNEL.semantic | Limited | Kernel ledger | Yes (Router) | Yes (Attention) | Internal only |
| ADMIN | Yes | Yes (admin/) | No | No | No |
| RESIDENT | Scoped | Scoped (ho1/) | No | No | v1.2 (designed for) |

---

## Runtime Separation

```
┌─────────────────────────────────────────────────────────────┐
│                 CONTROL PLANE RUNTIME                       │
│                 (KERNEL + ADMIN space)                      │
│                                                             │
│   KERNEL: trace.py, gates, router, attention, wisdom        │
│   ADMIN: Admin, Monitor, Security, Trust agents             │
│   - Infrastructure level                                    │
│   - Observe everything                                      │
│   - Write to own namespace only                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                            │
                       observes/coordinates
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                  RESIDENT RUNTIME                           │
│                  (BUILT / Senses space)                     │
│                                                             │
│   Application agents, workers                               │
│   - Sandboxed                                               │
│   - Scoped access                                           │
│   - Work order governed                                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Multi-Tenant Residents (Future)

Current ledger entries lack explicit tenant visibility:

```json
{
  "session_id": "SES-20260204-raymondbruni-xxx",
  // Missing: tenant_id, resident_id, agent_id
}
```

**Need to add:**

```json
{
  "session_id": "SES-...",
  "tenant_id": "TENANT-acme-corp",
  "resident_id": "RES-worker-001",
  "agent_class": "resident"
}
```

---

## Resident-to-Resident Invocation (v1.2)

Designed for but not implemented. Requires:
- Clear invocation boundaries
- Ledger entries showing caller/callee
- Work order scope validation
- Anti-recursion rules

---

## Comparison to OS Models

| Concept | Unix | Windows | Control Plane |
|---------|------|---------|---------------|
| Superuser | root (UID 0) | Domain Admin | BUILDER |
| Service account | nobody/daemon | SYSTEM | KERNEL |
| Auditor | auditd | Event Log | ADMIN |
| User process | regular user | Standard User | RESIDENT |
| Elevation | sudo | UAC | Work Order |
| Capability split | CAP_* | Privileges | Per-class caps |

### Improvements Over Traditional Models

| Traditional Problem | Control Plane Solution |
|--------------------|----------------------|
| Root can write AND read | ADMIN can READ only, enforced by capability |
| Admin can sudo to root | No escalation path - crosscutting is isolated |
| Audit is optional | L-OBSERVE is mandatory for crosscutting |
| Lateral movement (agent→agent) | CAP_INVOKE_AGENT = false |
| Single point of failure | Crosscutting is orthogonal, can't modify tiers |

---

## Updated CP-FIREWALL-001

Version 1.1.0 adds Section 11: Observer Role (ADMIN)

Key additions:
- ADMIN definition in Section 2
- ADMIN box in Section 3 diagram
- ADMIN_CHECKS in G-FIREWALL gate (Section 6.2)
- Full ADMIN specification (Section 11)

---

## Open Items

### TODO: Admin OS Separation
See: `docs/TODO_ADMIN_SEPARATION.md`

### Future Governance Questions

| Question | Implication |
|----------|-------------|
| How are KERNEL.semantic agents validated? | Need gate for prompt registration |
| Can KERNEL agents modify each other? | Anti-recursion for KERNEL? |
| What if Router is compromised? | All routing affected |
| What if Wisdom/Meta drifts? | Strategic decisions affected |
| How is Cognition protected from Senses? | Residents can't invoke KERNEL directly |

---

## Summary

### Three Agent Classes

1. **KERNEL** - Cognition (the brain)
   - KERNEL.syntactic: Pure code, deterministic
   - KERNEL.semantic: Controlled LLM, one-shot, strict JSON

2. **ADMIN** - Interface (human-facing observers)
   - Crosscutting read access
   - Write only to own namespace
   - Managers: Admin, Monitor, Security, Trust

3. **RESIDENT** - Senses (perception + action)
   - Task executors
   - Work order bound
   - Scoped access

### Key Principles

1. **Ledger is Memory** - Agents don't remember, they read
2. **No Drift** - HO1 stateless, HO2 session-scoped, HO3 learning
3. **One-Shot Control** - KERNEL.semantic uses controlled prompts
4. **Crosscutting Isolation** - ADMIN observes but cannot modify
5. **OS Defense in Depth** - Separate users/directories for isolation

---

## References

- CP-FIREWALL-001 v1.1.0: Builder vs Built Firewall (with ADMIN)
- CP-ARCH-001: Control Plane Architecture Overview
- CP-LEDGER-001: Tiered Ledger Model
- TODO_ADMIN_SEPARATION.md: OS-level separation tasks
