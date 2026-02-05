# Admin Agent

Read-only agent for explaining the Control Plane governance system. The first governed agent that operates inside the Control Plane's governance model.

## Purpose

This is a Tier 3 (T3) agent that provides:
- Human-friendly explanations of any artifact (framework, spec, package, file)
- Package listing with installation details
- System health checks
- Inventory overview

The Admin Agent wraps `trace.py` for low-level operations and adds formatting for human consumption.

## Usage

### Using the Class

```python
from modules.admin_agent import AdminAgent

agent = AdminAgent()

# Explain an artifact
print(agent.explain("FMWK-000"))
print(agent.explain("SPEC-CORE-001"))
print(agent.explain("PKG-KERNEL-001"))
print(agent.explain("lib/merkle.py"))

# List installed packages
print(agent.list_installed())

# Check system health
print(agent.check_health())
```

### Using the Turn Function

```python
from modules.admin_agent import admin_turn

# Explain queries
print(admin_turn("What is FMWK-000?"))
print(admin_turn("Explain SPEC-CORE-001"))

# List queries
print(admin_turn("What packages are installed?"))

# Health queries
print(admin_turn("Is the system healthy?"))
```

## Query Classification

The Admin Agent classifies queries into types:

| Query Pattern | Type | Handler |
|---------------|------|---------|
| "explain X", "what is X" | explain | explain(artifact_id) |
| "list packages", "installed" | list | list_installed() |
| "health", "status", "verify" | status | check_health() |
| "inventory" | inventory | trace --inventory |
| Other | general | explain(best guess) |

## Capabilities

The Admin Agent operates in **read-only mode**:

**Can Read:**
- Ledgers (governance, exec, evidence)
- Registries (frameworks, specs, packages, files)
- Installed package manifests
- Configuration files
- Documentation files

**Can Execute:**
- `scripts/trace.py` (explain, installed, inventory, verify)
- `scripts/integrity_check.py`

**Can Write:**
- Session ledgers only (L-EXEC, L-EVIDENCE)

**Forbidden:**
- All `lib/` files
- Package management scripts
- Work order approval

## Dependencies

- `modules/agent_runtime/` (T1 runtime)
- `modules/stdlib_evidence/` (T0 evidence)
- `scripts/trace.py` (kernel explainer)

## Specification

See `specs/SPEC-ADMIN-001/` for the full specification including:
- Problem statement (01_problem.md)
- Design rationale (02_solution.md)
- Requirements FR-ADMIN-001 through FR-ADMIN-010 (03_requirements.md)
- Test plan (05_testing.md)
