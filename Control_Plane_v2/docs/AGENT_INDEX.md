# Agent Documentation Index

**Start Here**: This is the master index for agents working with the Control Plane.

---

## Quick Start

| Task | Document |
|------|----------|
| **Create a package** | [AGENT_PACKAGE_GUIDE.md](AGENT_PACKAGE_GUIDE.md) |
| **Understand compliance** | [PACKAGE_COMPLIANCE.md](PACKAGE_COMPLIANCE.md) |
| **Query compliance programmatically** | `python3 scripts/pkgutil.py compliance --help` |
| **Operate the Control Plane (agents)** | [AGENT_OPERATIONS_GUIDE.md](AGENT_OPERATIONS_GUIDE.md) |
| **Script reference for Admin Agent** | [ADMIN_AGENT_SCRIPT_REF.md](ADMIN_AGENT_SCRIPT_REF.md) |
| **Understand architecture** | [CP-ARCH-001_control_plane_overview.md](CP-ARCH-001_control_plane_overview.md) |

---

## Package Management (Primary Use Case)

### Essential Commands

```bash
# Query what you need to know
python3 scripts/pkgutil.py compliance summary --json
python3 scripts/pkgutil.py compliance gates --json
python3 scripts/pkgutil.py compliance troubleshoot --error G1 --json

# Create packages
python3 scripts/pkgutil.py init PKG-XXX --spec SPEC-XXX --output _staging/PKG-XXX
python3 scripts/pkgutil.py preflight PKG-XXX --src _staging/PKG-XXX
python3 scripts/pkgutil.py stage PKG-XXX --src _staging/PKG-XXX

# Install
CONTROL_PLANE_ALLOW_UNSIGNED=1 python3 scripts/package_install.py --archive _staging/PKG-XXX.tar.gz --id PKG-XXX

# Verify
python3 scripts/gate_check.py --all
```

### Programmatic API

```python
from lib.agent_helpers import CPInspector

inspector = CPInspector()

# Get everything you need
summary, evidence = inspector.get_compliance_summary()
frameworks, _ = inspector.list_available_frameworks()
specs, _ = inspector.list_available_specs()
guide, _ = inspector.get_troubleshooting_guide(error_type="G1")
```

### Key Documents

| Document | Purpose |
|----------|---------|
| [AGENT_PACKAGE_GUIDE.md](AGENT_PACKAGE_GUIDE.md) | **Complete guide** - workflows, examples, troubleshooting |
| [PACKAGE_COMPLIANCE.md](PACKAGE_COMPLIANCE.md) | Technical reference - gates, fields, validations |

---

## System Understanding

### Architecture

| Document | Purpose |
|----------|---------|
| [CP-ARCH-001_control_plane_overview.md](CP-ARCH-001_control_plane_overview.md) | Three-tier architecture (HO3/HO2/HO1) |
| [CP-LEDGER-001_tiered_ledger_model.md](CP-LEDGER-001_tiered_ledger_model.md) | Ledger system and memory model |
| [CP-PKG-001_framework_and_package_spec.md](CP-PKG-001_framework_and_package_spec.md) | Package and framework specifications |
| [CP-FIREWALL-001_builder_vs_built.md](CP-FIREWALL-001_builder_vs_built.md) | Builder vs built separation |
| [AGENT_OPERATIONS_GUIDE.md](AGENT_OPERATIONS_GUIDE.md) | Operational playbook for LLM agents |

### Frameworks (Governance Rules)

Frameworks define governance rules. Located in `frameworks/`:

| Framework | Purpose |
|-----------|---------|
| FMWK-000 | Core governance framework |
| FMWK-100 | Agent development standard |
| FMWK-107 | Package management standard |
| FMWK-200 | Ledger protocol |
| FMWK-ATT-001 | Provenance attestation |

List available: `python3 scripts/pkgutil.py compliance frameworks`

### Specs (Asset Definitions)

Specs define what files a package can own. Located in `specs/`:

List available: `python3 scripts/pkgutil.py compliance specs --json`

---

## Key Scripts

| Script | Purpose | Example |
|--------|---------|---------|
| `scripts/pkgutil.py` | Package authoring | `pkgutil init`, `preflight`, `stage` |
| `scripts/package_install.py` | Install packages | `--archive <tar.gz> --id PKG-XXX` |
| `scripts/gate_check.py` | Verify gates | `--all` or `--gate G1` |
| `scripts/trace.py` | Explainability | `--inventory`, `--file <path>` |
| `scripts/integrity_check.py` | Verify hashes | `--json` |

---

## Key Libraries

| Library | Purpose |
|---------|---------|
| `lib/agent_helpers.py` | Read-only inspection API for agents |
| `lib/preflight.py` | Package validation logic |
| `lib/plane.py` | Multi-plane operations |
| `lib/ledger_client.py` | Ledger read/write |

---

## Registries

| Registry | Purpose |
|----------|---------|
| `registries/frameworks_registry.csv` | Registered frameworks |
| `registries/specs_registry.csv` | Registered specs |
| `registries/file_ownership.csv` | Which package owns each file |
| `registries/packages_state.csv` | Installed packages |

---

## Common Agent Tasks

### 1. Help Human Create a Package

Read: [AGENT_PACKAGE_GUIDE.md](AGENT_PACKAGE_GUIDE.md)

Quick workflow:
1. Check existing frameworks/specs: `pkgutil compliance frameworks` and `specs`
2. Create spec if needed: `pkgutil register-spec`
3. Create package: `pkgutil init PKG-XXX --spec SPEC-XXX`
4. Add code, run `pkgutil preflight`
5. Stage and install

### 2. Debug Package Validation Errors

```bash
# Get troubleshooting for specific error
python3 scripts/pkgutil.py compliance troubleshoot --error G1 --json
```

Or programmatically:
```python
from lib.agent_helpers import CPInspector
inspector = CPInspector()
guide, _ = inspector.get_troubleshooting_guide(error_type="G1")
```

### 3. Understand What's Installed

```bash
# List installed packages
python3 scripts/trace.py --inventory

# Explain a file's provenance
python3 scripts/trace.py --file lib/merkle.py
```

Or programmatically:
```python
from lib.agent_helpers import CPInspector
inspector = CPInspector()
packages, _ = inspector.list_installed()
```

### 4. Verify System Health

```bash
# Run all gates
python3 scripts/gate_check.py --all

# Check specific gate
python3 scripts/gate_check.py --gate G1
```

---

## Evidence and Auditability

All CPInspector methods return `(result, EvidencePointer)` tuples:

```python
packages, evidence = inspector.list_installed()
print(f"Evidence source: {evidence.source}")
print(f"Evidence path: {evidence.path}")
print(f"Evidence hash: {evidence.hash}")
```

This enables:
- **Auditability**: Prove what data was seen
- **Replayability**: Verify results later
- **No-drift**: Outputs reference specific state

---

## Authentication (if needed)

For operations requiring auth:

```bash
# Initialize auth (one-time)
python3 scripts/cp_init_auth.py

# Source credentials
source ~/.control_plane_v2/secrets.env

# Operations use CONTROL_PLANE_TOKEN automatically
```

For package install during development:
```bash
export CONTROL_PLANE_ALLOW_UNSIGNED=1
```

---

## File Locations

| Path | Purpose |
|------|---------|
| `docs/` | Documentation |
| `frameworks/` | Framework definitions (FMWK-*.md) |
| `specs/` | Spec definitions (SPEC-*/manifest.yaml) |
| `_staging/` | Package development area |
| `installed/` | Installed package manifests |
| `packages_store/` | Package archives |
| `registries/` | CSV registries |
| `ledger/` | Append-only ledgers |
| `lib/` | Python libraries |
| `scripts/` | CLI tools |
| `tests/` | Test files |

---

## Getting Help

```bash
# Package utilities help
python3 scripts/pkgutil.py --help
python3 scripts/pkgutil.py compliance --help

# Gate check help
python3 scripts/gate_check.py --help

# Trace/explainability help
python3 scripts/trace.py --help
```
