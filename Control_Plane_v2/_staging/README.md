# Control Plane v2 Bootstrap

## Prerequisites

- Python 3.10+
- `pip install anthropic>=0.40.0`

## Install

```bash
chmod +x install.sh
./install.sh --root /path/to/install --dev
```

This auto-discovers and installs all 16 packages in dependency order. Takes ~10 seconds.

Do NOT install packages manually. The install order matters and install.sh handles it.

## Start ADMIN

```bash
export ANTHROPIC_API_KEY="your-api-key"
python3 /path/to/install/HOT/admin/main.py --root /path/to/install --dev
```

You get an `admin>` prompt. ADMIN is the governance interface — it can run gate checks, read files, query the ledger, and list packages.

Type `exit` or `quit` to end the session.

## Verify

```bash
python3 /path/to/install/HOT/scripts/gate_check.py --root /path/to/install --all
```

Expected: 8/8 gates PASS.

## Flags

| Flag | Description |
|------|-------------|
| `--root <dir>` | Install directory (required, created if absent) |
| `--dev` | Bypass auth checks (use for testing) |
| `--force` | Overwrite existing files (re-install/recovery) |

## What's inside this archive

```
README.md                 <-- You are here
INSTALL.md                <-- Detailed manual guide + troubleshooting
install.sh                <-- Run this to install
resolve_install_order.py  <-- Auto-discovers package install order
packages/                 <-- Package archives (do not extract manually)
  PKG-GENESIS-000.tar.gz            Layer 0: bootstrap seed
  PKG-KERNEL-001.tar.gz             Layer 0: kernel primitives
  PKG-VOCABULARY-001.tar.gz         Layer 1: governance vocabulary
  PKG-REG-001.tar.gz                Layer 1: registries
  PKG-GOVERNANCE-UPGRADE-001.tar.gz Layer 2: governance enforcement
  PKG-FRAMEWORK-WIRING-001.tar.gz   Layer 2: frameworks + schemas
  PKG-SPEC-CONFORMANCE-001.tar.gz   Layer 2: spec conformance
  PKG-LAYOUT-001.tar.gz             Layer 2: tier layout
  PKG-LAYOUT-002.tar.gz             Layer 3: layout upgrade
  PKG-PHASE2-SCHEMAS-001.tar.gz     Layer 3: phase 2 schemas
  PKG-TOKEN-BUDGETER-001.tar.gz     Layer 3: token budgeting
  PKG-ATTENTION-001.tar.gz          Layer 3: attention service
  PKG-PROMPT-ROUTER-001.tar.gz      Layer 3: prompt routing
  PKG-ANTHROPIC-PROVIDER-001.tar.gz Layer 3: Anthropic LLM provider
  PKG-SESSION-HOST-001.tar.gz       Layer 3: session host (agent runtime)
  PKG-ADMIN-001.tar.gz              Layer 3: ADMIN agent (governance UI)
```

## Do not

- Do NOT extract or install packages from `packages/` manually. Use `install.sh`.
- Do NOT skip `--dev` unless you have HMAC auth configured.
- Do NOT edit installed files. Use the package system to ship changes.

## Detailed guide

See `INSTALL.md` for manual step-by-step install, troubleshooting, and architecture overview.
