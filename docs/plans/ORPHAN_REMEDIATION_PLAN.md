# Orphan Remediation Plan

**Date**: 2026-02-04
**Status**: PENDING (waiting for current sprints to complete)
**Orphan Count**: 63 files

---

## Executive Summary

The Control Plane has 63 orphan files - files in governed roots without package ownership. These need to be packaged and installed to restore governance compliance.

---

## Current State

```
=== Control Plane Governance Status ===
Sealed: True
Owned Files: 273
Orphan Files: 63
Installed Packages: 5
Health: ORPHANS_DETECTED
```

---

## Remediation Groups

### 1. PKG-SHELL-001 (28 files)

**Description**: Universal Shell for Control Plane

**Spec**: SPEC-SHELL-001
**Framework**: FMWK-SHELL-001

**Files**:
```
frameworks/FMWK-SHELL-001_shell_standard.md
modules/shell/README.md
modules/shell/__init__.py
modules/shell/__main__.py
modules/shell/capabilities.json
modules/shell/chat_ui.py
modules/shell/commands/__init__.py
modules/shell/commands/core.py
modules/shell/commands/governance.py
modules/shell/commands/memory.py
modules/shell/commands/notes.py
modules/shell/commands/signals.py
modules/shell/interfaces.py
modules/shell/operations.py
modules/shell/shell.py
scripts/shell.py
specs/SPEC-SHELL-001/00_overview.md
specs/SPEC-SHELL-001/01_problem.md
specs/SPEC-SHELL-001/02_solution.md
specs/SPEC-SHELL-001/03_requirements.md
specs/SPEC-SHELL-001/04_design.md
specs/SPEC-SHELL-001/05_testing.md
specs/SPEC-SHELL-001/06_rollout.md
specs/SPEC-SHELL-001/07_registry.md
specs/SPEC-SHELL-001/08_commit.md
tests/test_shell.py
tests/test_shell_commands.py
tests/test_shell_pipe.py
```

**Commands**:
```bash
# 1. Register framework (if not already)
python3 scripts/pkgutil.py register-framework FMWK-SHELL-001 \
  --src frameworks/FMWK-SHELL-001_shell_standard.md

# 2. Register spec (if not already)
python3 scripts/pkgutil.py register-spec SPEC-SHELL-001 \
  --src specs/SPEC-SHELL-001

# 3. Create staging package
python3 scripts/remediate_orphans.py --execute
# OR manually:
mkdir -p _staging/PKG-SHELL-001
# Copy files maintaining directory structure

# 4. Preflight
python3 scripts/pkgutil.py preflight PKG-SHELL-001 --src _staging/PKG-SHELL-001

# 5. Stage
python3 scripts/pkgutil.py stage PKG-SHELL-001 --src _staging/PKG-SHELL-001

# 6. Install
CONTROL_PLANE_ALLOW_UNSIGNED=1 python3 scripts/package_install.py \
  --archive _staging/PKG-SHELL-001.tar.gz --id PKG-SHELL-001
```

---

### 2. PKG-CHAT-001 (27 files)

**Description**: Chat Interface for Control Plane

**Spec**: SPEC-CHAT-001
**Framework**: FMWK-CHAT-001

**Files**:
```
frameworks/FMWK-CHAT-001_chat_interface_governance.md
modules/chat_interface/__init__.py
modules/chat_interface/__main__.py
modules/chat_interface/classifier.py
modules/chat_interface/handlers/__init__.py
modules/chat_interface/handlers/browse.py
modules/chat_interface/handlers/help.py
modules/chat_interface/handlers/ledger.py
modules/chat_interface/handlers/packages.py
modules/chat_interface/handlers/search.py
modules/chat_interface/registry.py
modules/chat_interface/session.py
schemas/chat_request.json
schemas/chat_response.json
scripts/chat.py
specs/SPEC-CHAT-001/00_overview.md
specs/SPEC-CHAT-001/01_problem.md
specs/SPEC-CHAT-001/02_solution.md
specs/SPEC-CHAT-001/03_requirements.md
specs/SPEC-CHAT-001/04_design.md
specs/SPEC-CHAT-001/05_testing.md
specs/SPEC-CHAT-001/06_rollout.md
specs/SPEC-CHAT-001/07_registry.md
specs/SPEC-CHAT-001/08_commit.md
specs/SPEC-CHAT-001/manifest.yaml
tests/test_chat_interface.py
tests/test_chat_session.py
```

**Commands**:
```bash
# 1. Register framework
python3 scripts/pkgutil.py register-framework FMWK-CHAT-001 \
  --src frameworks/FMWK-CHAT-001_chat_interface_governance.md

# 2. Register spec
python3 scripts/pkgutil.py register-spec SPEC-CHAT-001 \
  --src specs/SPEC-CHAT-001

# 3-6. Same as PKG-SHELL-001 workflow
```

---

### 3. PKG-BASELINE-UPDATE (7 files)

**Description**: Files to add to baseline package

**Action**: Regenerate baseline manifest (not a new package)

**Files**:
```
docs/ADMIN_AGENT_SCRIPT_REF.md
docs/AGENT_OPERATIONS_GUIDE.md
docs/CROSSCUTTING.md
modules/admin_agent/tools.py
scripts/agent_check.py
scripts/remediate_orphans.py
tests/test_prompt_tracking.py
```

**Commands**:
```bash
# Regenerate baseline manifest to include these files
python3 scripts/generate_baseline_manifest.py --plane ho3 \
  --output packages_store/PKG-BASELINE-HO3-000/

# Reinstall baseline
CONTROL_PLANE_ALLOW_UNSIGNED=1 python3 scripts/package_install.py \
  --archive packages_store/PKG-BASELINE-HO3-000.tar.gz \
  --id PKG-BASELINE-HO3-000
```

---

### 4. UNKNOWN (1 file)

**Files**:
```
docs/TODO_ADMIN_SEPARATION.md
```

**Action**: Manual classification needed
- Option A: Add to PKG-BASELINE-UPDATE (if it's a core doc)
- Option B: Delete if obsolete
- Option C: Create new package if it's a distinct feature

---

## Execution Order

1. **Register frameworks first** (FMWK-SHELL-001, FMWK-CHAT-001)
2. **Register specs** (SPEC-SHELL-001, SPEC-CHAT-001)
3. **Package and install PKG-SHELL-001**
4. **Package and install PKG-CHAT-001**
5. **Regenerate and reinstall baseline** (for the 7 core files)
6. **Handle UNKNOWN file** manually
7. **Verify zero orphans**: `python3 scripts/agent_check.py --orphans`
8. **Apply strict AGENTS.md rules**: `cp docs/plans/AGENTS_STRICT_RULES.md AGENTS.md`

---

## Verification Commands

```bash
# Check current orphan count
python3 scripts/agent_check.py --status

# List all orphans
python3 scripts/agent_check.py --orphans

# Run all gates
python3 scripts/gate_check.py --all

# Verify governance health
python3 scripts/agent_check.py --status
# Should show: Health: HEALTHY
```

---

## Tools Available

| Tool | Purpose |
|------|---------|
| `scripts/agent_check.py --status` | Governance health check |
| `scripts/agent_check.py --orphans` | List orphan files |
| `scripts/agent_check.py --path <path>` | Check if path is governed |
| `scripts/remediate_orphans.py --plan` | Show remediation plan |
| `scripts/remediate_orphans.py --execute` | Create staging packages |
| `scripts/pkgutil.py preflight` | Validate package before install |
| `scripts/pkgutil.py stage` | Create installable tar.gz |
| `scripts/package_install.py` | Install package to governed roots |

---

## Post-Remediation Checklist

- [ ] All frameworks registered
- [ ] All specs registered
- [ ] PKG-SHELL-001 installed
- [ ] PKG-CHAT-001 installed
- [ ] Baseline regenerated with new core files
- [ ] UNKNOWN file handled
- [ ] `agent_check.py --orphans` shows 0 orphans
- [ ] `gate_check.py --all` passes
- [ ] Strict AGENTS.md rules applied
- [ ] Team notified of new governance workflow

---

## Notes

- Current sprints are in progress - do NOT apply strict rules yet
- Safe zones for agents: `docs/`, `_external_quarantine/`, `_staging/`, `tmp/`
- Strict rules saved at: `docs/plans/AGENTS_STRICT_RULES.md`
