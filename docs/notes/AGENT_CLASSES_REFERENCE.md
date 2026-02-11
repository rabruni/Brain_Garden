# Agent Classes Quick Reference
**Version**: 1.0
**Locked**: 2026-02-04

---

## The Model

```
KERNEL = Cognition (the brain)
ADMIN  = Interface (human-facing)
RESIDENT = Senses (perception + action)
```

---

## KERNEL

### KERNEL.syntactic
- **Nature**: Pure code, deterministic
- **LLM**: None
- **Drift**: Impossible
- **Examples**: trace.py, merkle.py, gates, hash chains
- **Interactive**: No

### KERNEL.semantic
- **Nature**: Controlled LLM, one-shot prompts
- **LLM**: Yes - strict JSON, registered prompts, logged
- **Drift**: Controlled via structure
- **Examples**: Router, Attention, Wisdom, Meta/HOT
- **Interactive**: No
- **Pattern**:
  ```python
  response = llm.complete(
      prompt=GOVERNED_PROMPT,    # Registered
      input=strict_json,         # Validated
      temperature=0              # Deterministic
  )
  ledger.write({"in": hash(input), "out": hash(response)})
  ```

---

## ADMIN (Managers)

- **Nature**: Crosscutting observers
- **Examples**: Admin, Monitor, Security, Trust
- **Interactive**: Yes (human-facing)
- **Runtime**: Control Plane runtime
- **Namespace**: `planes/admin/` (or `/opt/control_plane_admin/`)
- **Capabilities**:
  - CAP_READ_ALL: Yes
  - CAP_AUDIT_WRITE: Yes (own namespace)
  - CAP_WRITE_*: No
  - CAP_INVOKE_AGENT: No
- **Work Orders**: Standing authorization (not per-query)
- **Turn Isolation**: Post-declaration via L-OBSERVE
- **Memory**: HO1 (exec), HO2 (session), HO3 (learning)

---

## RESIDENT (Senses)

- **Nature**: Task executors
- **Examples**: Worker agents, Application agents
- **Interactive**: Task-dependent
- **Runtime**: Resident runtime (separate)
- **Namespace**: `planes/ho1/`, `planes/ho2/`
- **Capabilities**: Scoped per work order
- **Work Orders**: Required for any action
- **Turn Isolation**: Pre-declaration
- **Memory**: HO1 only (stateless)

---

## Capability Matrix

| Class | READ_ALL | AUDIT_WRITE | INVOKE_AGENT |
|-------|----------|-------------|--------------|
| KERNEL.syntactic | N/A | N/A | N/A |
| KERNEL.semantic | Limited | Kernel | Internal |
| ADMIN | Yes | Own namespace | No |
| RESIDENT | Scoped | Scoped | v1.2 |

---

## Memory Model (Anti-Drift)

| Level | Type | Drift? | Purpose |
|-------|------|--------|---------|
| HO1 | Fast/None | No drift | Stateless execution |
| HO2 | Slow | Controlled | Session memory |
| HO3 | Learning | Controlled | Wisdom accumulation |

**Key**: Agents don't REMEMBER, they READ (from ledgers).

---

## Firewall Summary

```
BUILDER:  Full write
BUILT:    Scoped write (HO1 + RUNTIME)
ADMIN:    Own namespace only (more restricted than BUILT)
```

ADMIN is a watchtower outside the walls, not a hole in the firewall.

---

## See Also

- AGENT_ARCHITECTURE_SESSION_20260204.md (full session notes)
- CP-FIREWALL-001 v1.1.0 (Section 11: ADMIN)
- TODO_ADMIN_SEPARATION.md (OS-level separation)
