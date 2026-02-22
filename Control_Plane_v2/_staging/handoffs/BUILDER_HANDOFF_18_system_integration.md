# BUILDER HANDOFF 18: System Integration — Kitchener Loop Wiring

## 1. Mission

Wire the 6 new code packages (H-13 through H-17) into a working system. This handoff connects the Modified Kitchener cognitive dispatch loop to the ADMIN entrypoint, fixes manifest gaps found during audit, aligns registries with the authoritative source, rebuilds 5 archives + CP_BOOTSTRAP, and verifies the integrated system end-to-end.

**This is an integration handoff, not a code package handoff.** No new packages are created. Existing packages and infrastructure files are modified to connect the components built in H-13 through H-17.

### Audit Findings (Why This Is More Than a Simple Wiring Job)

The following gaps were discovered during pre-dispatch audit:

1. **Missing `supersedes` markers** — PKG-SESSION-HOST-V2-001 doesn't declare it supersedes PKG-SESSION-HOST-001. PKG-HO2-SUPERVISOR-001 doesn't declare it supersedes PKG-ATTENTION-001.
2. **Wrong dependency references** — PKG-HO1-EXECUTOR-001 and PKG-SESSION-HOST-V2-001 depend on PKG-PROMPT-ROUTER-001 instead of PKG-LLM-GATEWAY-001.
3. **PKG-ADMIN-001 manifest** missing 6 V2 dependency declarations (WO, Gateway, HO1, HO2, SH-V2, Shell).
4. **PKG-HO2-SUPERVISOR-001 manifest** missing `package_type` field.
5. **PKG-HO1-EXECUTOR-001 manifest** missing `framework_id` and `title` fields.
6. **Registry gap bigger than expected** — PKG-KERNEL-001 registries have 1 framework and 3 specs; authoritative source (PKG-FRAMEWORK-WIRING-001) has 4 frameworks and 11 specs; need to align + add 4 new Kitchener frameworks.
7. **admin_config.json** references FMWK-005 (nonexistent) instead of FMWK-000.
8. **5 archives need rebuilding** (not 3) — because HO2 and SH-V2 manifests also changed.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree.
2. **No new packages.** This handoff modifies existing package source files only.
3. **V1 packages remain installed.** PKG-SESSION-HOST-001, PKG-PROMPT-ROUTER-001, PKG-ATTENTION-001 stay in the bootstrap. They are superseded at runtime but not removed.
4. **Use kernel tools for hashing and packing.** `hashing.py:compute_sha256()` for all SHA256 hashes. `packages.py:pack()` for all archives. NEVER use raw `hashlib` or shell `tar`. See "Required Kernel Tools" in BUILDER_HANDOFF_STANDARD.md.
5. **Clean-room verification.** Extract rebuilt CP_BOOTSTRAP.tar.gz → install all packages → all gates pass → E2E smoke test.
6. **Results file.** Write `_staging/handoffs/RESULTS_HANDOFF_18.md` with FULL template including Clean-Room Verification, Baseline Snapshot, and E2E test results.
7. **Hash format.** All SHA256 hashes in manifests: `sha256:<64hex>` (71 chars). No bare hex.
8. **Backfill missing RESULTS files.** H-13, H-14, H-15, H-16B are missing RESULTS files. Write them now.
9. **SPEC-CORE-001 is NOT removable.** 3 packages (LAYOUT-001, PROMPT-ROUTER-001, TOKEN-BUDGETER-001) reference it. It must be in the registry.

## 3. Architecture / Design

### Current State (BROKEN)
```
main.py → build_session_host() → SessionHost (V1) → PromptRouter (V1) → AnthropicProvider
                                  ↓
                                  AttentionService (V1)
                                  ToolDispatcher (V1, in HOT/kernel/)
```

### Target State (WORKING)
```
main.py → run_cli() → Shell → SessionHostV2 → HO2Supervisor → HO1Executor → LLMGateway → AnthropicProvider
                                  ↓ (degradation)
                                  LLMGateway.route() direct
```

### Supersession Map

| New Package | Supersedes | Why |
|-------------|-----------|-----|
| PKG-LLM-GATEWAY-001 | PKG-PROMPT-ROUTER-001 | Already declared. Routing → HO2, send/log → Gateway. |
| PKG-SESSION-HOST-V2-001 | PKG-SESSION-HOST-001 | **MISSING.** V2 thin adapter replaces V1 flat loop. |
| PKG-HO2-SUPERVISOR-001 | PKG-ATTENTION-001 | **MISSING.** HO2 absorbs attention functionality. |

### Dependency Corrections

| Package | Wrong Dep | Correct Dep | Why |
|---------|----------|-------------|-----|
| PKG-HO1-EXECUTOR-001 | PKG-PROMPT-ROUTER-001 | PKG-LLM-GATEWAY-001 | HO1 calls Gateway, not Prompt Router |
| PKG-SESSION-HOST-V2-001 | PKG-PROMPT-ROUTER-001 | PKG-LLM-GATEWAY-001 | SH-V2 degrades through Gateway |

### PromptRouter Lifecycle Resolution

PKG-PROMPT-ROUTER-001 remains in bootstrap (V1 code still needed by V1 test files). PKG-LLM-GATEWAY-001 installs after it and overwrites `prompt_router.py` with the backward-compat shim (`PromptRouter = LLMGateway`). This is an intentional ownership transfer via dependency declaration.

## 4. Implementation Steps

### Phase 1: Manifest Fixes (Steps 1-5) — JSON edits only

**Step 1: PKG-HO1-EXECUTOR-001/manifest.json**
- Add `"framework_id": "FMWK-000"` (was missing)
- Add `"title": "HO1 Executor"` (was missing)
- Change dependency `"PKG-PROMPT-ROUTER-001"` → `"PKG-LLM-GATEWAY-001"`

**Step 2: PKG-HO2-SUPERVISOR-001/manifest.json**
- Add `"package_type": "kernel"` (was missing)
- Add `"supersedes": "PKG-ATTENTION-001"`

**Step 3: PKG-SESSION-HOST-V2-001/manifest.json**
- Add `"supersedes": "PKG-SESSION-HOST-001"`
- Change dependency `"PKG-PROMPT-ROUTER-001"` → `"PKG-LLM-GATEWAY-001"`

**Step 4: PKG-ADMIN-001/manifest.json**
- Add 6 dependencies: `PKG-WORK-ORDER-001`, `PKG-LLM-GATEWAY-001`, `PKG-HO1-EXECUTOR-001`, `PKG-HO2-SUPERVISOR-001`, `PKG-SESSION-HOST-V2-001`, `PKG-SHELL-001`
- Keep all existing V1 deps (backward compat / degradation fallback)

**Step 5: PKG-ADMIN-001/HOT/config/admin_config.json**
- Change `"framework_id": "FMWK-005"` → `"framework_id": "FMWK-000"`

### Phase 2: Registry Alignment (Steps 6-7)

**Step 6: frameworks_registry.csv** (`PKG-KERNEL-001/HOT/registries/`)

Current state: 1 row (FMWK-000). Target: 8 rows.

Add 7 rows — 3 backfill from authoritative source (`PKG-FRAMEWORK-WIRING-001/HOT/registries/frameworks_registry.csv`) + 4 new Kitchener:

```csv
FMWK-001,Provenance Attestation Standard,active,1.1.0,hot,2026-01-31T00:00:00Z
FMWK-002,Ledger Protocol Standard,active,1.1.0,hot,2026-01-30T00:00:00Z
FMWK-007,Package Management Standard,active,1.2.0,hot,2026-01-30T00:00:00Z
FMWK-008,Work Order Protocol,active,1.1.0,hot,2026-02-14T00:00:00Z
FMWK-009,Tier Boundary,active,1.0.0,hot,2026-02-14T00:00:00Z
FMWK-010,Cognitive Stack,active,1.0.0,hot,2026-02-14T00:00:00Z
FMWK-011,Prompt Contracts,active,1.0.0,hot,2026-02-14T00:00:00Z
```

**Step 7: specs_registry.csv** (`PKG-KERNEL-001/HOT/registries/`)

Current state: 3 rows (SPEC-GENESIS-001, SPEC-GATE-001, SPEC-REG-001). Target: 11 rows.

Add 8 rows from authoritative source:

```csv
SPEC-CORE-001,Core Infrastructure,FMWK-000,active,1.0.0,hot,2026-02-09T00:00:00Z
SPEC-INT-001,Integrity & Merkle,FMWK-000,active,1.0.0,hot,2026-02-09T00:00:00Z
SPEC-LEDGER-001,Ledger System,FMWK-002,active,1.0.0,hot,2026-02-09T00:00:00Z
SPEC-PKG-001,Package Management,FMWK-007,active,1.0.0,hot,2026-02-09T00:00:00Z
SPEC-PLANE-001,Multi-Plane,FMWK-000,active,1.0.0,hot,2026-02-09T00:00:00Z
SPEC-POLICY-001,Policy Management,FMWK-000,active,1.0.0,hot,2026-02-09T00:00:00Z
SPEC-SEC-001,Security & Auth,FMWK-001,active,1.0.0,hot,2026-02-09T00:00:00Z
SPEC-VER-001,Version Control,FMWK-000,active,1.0.0,hot,2026-02-09T00:00:00Z
```

**Verification**: After adding, SPEC-LEDGER-001 → FMWK-002, SPEC-PKG-001 → FMWK-007, SPEC-SEC-001 → FMWK-001. All parent frameworks must exist in frameworks_registry.csv (they will after Step 6). This is what G1 checks.

### Phase 3: Code Change (Step 8) — One file only

The only code file that changes is `PKG-ADMIN-001/HOT/admin/main.py`.

**Step 8a: Add sys.path entries** in `_ensure_import_paths()`:

Add staging paths for 6 new packages:
```python
staging / "PKG-WORK-ORDER-001" / "HOT" / "kernel",
staging / "PKG-LLM-GATEWAY-001" / "HOT" / "kernel",
staging / "PKG-HO1-EXECUTOR-001" / "HO1" / "kernel",
staging / "PKG-HO2-SUPERVISOR-001" / "HO2" / "kernel",
staging / "PKG-SESSION-HOST-V2-001" / "HOT" / "kernel",
staging / "PKG-SHELL-001" / "HOT" / "kernel",
```

Add installed-root paths for HO1/kernel and HO2/kernel:
```python
if root is not None:
    add = [
        Path(root) / "HOT" / "kernel",
        Path(root) / "HO1" / "kernel",
        Path(root) / "HO2" / "kernel",
        Path(root) / "HOT" / "scripts",
    ] + add
```

**Step 8b: Add `build_session_host_v2()` function** using DI constructor signatures.

Read these constructors from source (do NOT guess signatures):
- `HO1Executor(gateway, ledger, budgeter, tool_dispatcher, contract_loader, config)` — `ho1_executor.py:45-59`
- `HO2Supervisor(plane_root, agent_class, ho1_executor, ledger_client, token_budgeter, config)` — `ho2_supervisor.py:88-96`
- `SessionHostV2(ho2_supervisor, gateway, agent_config, ledger_client)` — `session_host_v2.py:45-46`
- `Shell(session_host_v2, agent_config, input_fn, output_fn)` — `shell.py:24-30`

Build order:
1. `cfg_dict = load_admin_config(config_path)` → raw dict
2. `ledger_gov = LedgerClient(root / "HOT/ledger/governance.jsonl")` — governance ledger (dir exists from bootstrap)
3. Create HO2/HO1 ledger dirs: `(root / "HO2/ledger").mkdir(parents=True, exist_ok=True)` and `(root / "HO1/ledger").mkdir(parents=True, exist_ok=True)` — these dirs do NOT exist after bootstrap, you MUST create them.
4. `ledger_ho2m = LedgerClient(root / "HO2/ledger/ho2m.jsonl")` — HO2 memory
5. `ledger_ho1m = LedgerClient(root / "HO1/ledger/ho1m.jsonl")` — HO1 memory
6. `budgeter = TokenBudgeter(ledger_client=ledger_gov, config=BudgetConfig())` — class is `BudgetConfig` (NOT `BudgeterConfig`) from `token_budgeter.py:132`. Constructor: `TokenBudgeter(ledger_client, config: BudgetConfig, rate_limit_config=None)`.
7. `contract_loader = ContractLoader(contracts_dir=root / "HO1/contracts")` — from `contract_loader.py`
8. `tool_dispatcher = ToolDispatcher(plane_root=root, tool_configs=cfg_dict["tools"], permissions=cfg_dict["permissions"])`
9. `_register_admin_tools(tool_dispatcher, root)` — re-use existing function
10. `gateway = LLMGateway(ledger_client=ledger_gov, budgeter=budgeter, config=RouterConfig(...), dev_mode=dev_mode)`
11. `gateway.register_provider("anthropic", AnthropicProvider())`
12. `ho1_config = {"agent_id": "admin-001.ho1", "agent_class": "ADMIN", ...}`
13. `ho1 = HO1Executor(gateway=gateway, ledger=ledger_ho1m, budgeter=budgeter, tool_dispatcher=tool_dispatcher, contract_loader=contract_loader, config=ho1_config)`
14. `ho2_config = HO2Config(attention_templates=["ATT-ADMIN-001"], ho2m_path=root/"HO2/ledger/ho2m.jsonl", ho1m_path=root/"HO1/ledger/ho1m.jsonl")`
15. `ho2 = HO2Supervisor(plane_root=root, agent_class="ADMIN", ho1_executor=ho1, ledger_client=ledger_ho2m, token_budgeter=budgeter, config=ho2_config)`
16. Build V2 AgentConfig — **NAME COLLISION**: both V1 (`session_host.py:39`) and V2 (`session_host_v2.py:30`) define `AgentConfig`. Fields are identical (agent_id, agent_class, framework_id, tier, system_prompt, attention, tools, budget, permissions). V1 has `from_file()` classmethod, V2 doesn't. **Resolution**: import V2's version with alias: `from session_host_v2 import AgentConfig as V2AgentConfig`. Construct manually from cfg_dict: `V2AgentConfig(agent_id=cfg_dict["agent_id"], agent_class=cfg_dict["agent_class"], ...)`.
17. `sh_v2 = SessionHostV2(ho2_supervisor=ho2, gateway=gateway, agent_config=v2_agent_config, ledger_client=ledger_gov)`
18. Return `Shell(session_host_v2=sh_v2, agent_config=v2_agent_config, input_fn=input_fn, output_fn=output_fn)`

**Step 8c: Rewire `run_cli()`** to try V2 first, catch ImportError/Exception → degrade to V1 with warning:
```python
try:
    shell = build_session_host_v2(root=root, config_path=config_path, dev_mode=dev_mode,
                                   input_fn=input_fn, output_fn=output_fn)
    shell.run()
    return 0
except Exception as exc:
    import sys
    print(f"WARNING: V2 Kitchener loop failed ({exc}), falling back to V1", file=sys.stderr)
    # ... existing V1 code ...
```

**Step 8d: Keep `build_session_host()` (V1)** as fallback. Do not remove it.

### Phase 4: Build & Verify (Steps 9-13)

**Step 9: Recompute hashes + rebuild 5 archives using kernel tools**

For each modified package, use the built-in kernel tools:

```python
import sys
from pathlib import Path

staging = Path("Control_Plane_v2/_staging")
sys.path.insert(0, str(staging / "PKG-KERNEL-001/HOT/kernel"))

from hashing import compute_sha256
from packages import pack

# For each package:
# 1. Recompute sha256 for all changed files
# 2. Update manifest.json with fresh hashes
# 3. Pack deterministically
pack(src=pkg_dir, dest=staging / f"{pkg_id}.tar.gz")
```

**5 archives rebuilt:**
- `PKG-KERNEL-001.tar.gz` (registries changed)
- `PKG-ADMIN-001.tar.gz` (main.py + admin_config.json + manifest.json)
- `PKG-HO1-EXECUTOR-001.tar.gz` (manifest.json changed)
- `PKG-HO2-SUPERVISOR-001.tar.gz` (manifest.json changed)
- `PKG-SESSION-HOST-V2-001.tar.gz` (manifest.json changed)

**Step 10: Rebuild CP_BOOTSTRAP.tar.gz** (23 packages)

Assemble all 23 package .tar.gz files + install.sh + resolve_install_order.py + README.md + INSTALL.md into bootstrap archive.

**Current bootstrap (18 packages):**
- Layer 0: PKG-GENESIS-000, PKG-KERNEL-001 (updated)
- Layer 1: PKG-VOCABULARY-001, PKG-REG-001
- Layer 2: PKG-GOVERNANCE-UPGRADE-001, PKG-FRAMEWORK-WIRING-001, PKG-SPEC-CONFORMANCE-001, PKG-LAYOUT-001
- Layer 3: PKG-PHASE2-SCHEMAS-001, PKG-TOKEN-BUDGETER-001, PKG-PROMPT-ROUTER-001, PKG-ANTHROPIC-PROVIDER-001, PKG-LAYOUT-002, PKG-BOOT-MATERIALIZE-001
- Layer 3 (V1 app): PKG-ATTENTION-001, PKG-SESSION-HOST-001, PKG-ADMIN-001 (updated)
- Layer 3 (H-13): PKG-WORK-ORDER-001 (already in bootstrap)

**5 new archives to add:**
- Layer 3: PKG-LLM-GATEWAY-001, PKG-HO1-EXECUTOR-001, PKG-HO2-SUPERVISOR-001, PKG-SESSION-HOST-V2-001
- Layer 4: PKG-SHELL-001

**Excluded:** PKG-FLOW-RUNNER-001 exists on disk (24 total .tar.gz files) but is superseded/dead — do NOT include it.

**Total: 18 + 5 = 23 packages.**

**Step 11: Clean-room install (full governance pipeline)**

```bash
TMPDIR=$(mktemp -d)
tar xzf _staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
INSTALLDIR="$TMPDIR/INSTALL_ROOT"
mkdir -p "$INSTALLDIR"
bash "$TMPDIR/install.sh" --root "$INSTALLDIR" --dev
```

Expected: 23 packages installed, 8/8 gates PASS.

The pipeline enforces:
- G0A: every file in manifest + hashes match
- G1: spec_id → framework_id chain valid (proves registry alignment)
- G1-COMPLETE: all framework wiring satisfied
- Ownership: no conflicts (dependency-declared transfers OK)
- Ledger: INSTALL_STARTED → INSTALLED events
- Receipts: per-package receipt.json with hash proof

**Step 12: Backfill RESULTS + E2E smoke test**

Write to `_staging/handoffs/`:
- `RESULTS_HANDOFF_13.md` (PKG-WORK-ORDER-001: 37 tests, 4 assets)
- `RESULTS_HANDOFF_14.md` (PKG-HO1-EXECUTOR-001: 35 tests, 7 assets)
- `RESULTS_HANDOFF_15.md` (PKG-HO2-SUPERVISOR-001: 47 tests, 6 assets)
- `RESULTS_HANDOFF_16B.md` (PKG-LLM-GATEWAY-001: 18 tests, 3 assets)

Move existing RESULTS files from package dirs to `_staging/handoffs/` if they exist.

E2E smoke test:
```bash
# Requires ANTHROPIC_API_KEY in environment
python3 "$INSTALLDIR/HOT/admin/main.py" --root "$INSTALLDIR" --dev
# At admin> prompt, type: hello
# Expected: response flows through Shell → SH-V2 → HO2 → HO1 → LLMGateway → Anthropic
# Verify ledger contains: WO_PLANNED, WO_DISPATCHED, LLM_CALL, WO_COMPLETED, WO_CHAIN_COMPLETE, WO_QUALITY_GATE
```

**Step 13: Write RESULTS_HANDOFF_18.md** (gold-standard format per RESULTS_HANDOFF_9)

Must include all sections: Files Modified, Archives Built, Clean-Room Verification, E2E Smoke Test, Baseline Snapshot, Full Regression.

## 5. Package Plan

No new packages. Modified packages:

| Package | What Changes | Rebuild Archive |
|---------|-------------|-----------------|
| PKG-KERNEL-001 | frameworks_registry.csv (+7 rows), specs_registry.csv (+8 rows) | YES |
| PKG-ADMIN-001 | main.py (V2 wiring), admin_config.json (FMWK-000), manifest.json (+6 deps) | YES |
| PKG-HO1-EXECUTOR-001 | manifest.json (framework_id, title, dep fix) | YES |
| PKG-HO2-SUPERVISOR-001 | manifest.json (package_type, supersedes) | YES |
| PKG-SESSION-HOST-V2-001 | manifest.json (supersedes, dep fix) | YES |

## 6. Test Plan

### Integration Tests (run manually, not pytest)

| Test | What It Validates | Expected |
|------|-------------------|----------|
| Clean-room install | All 23 packages install through gates | 8/8 gates PASS |
| Import smoke test | Key modules importable from installed layout | `from shell import Shell`, `from ho2_supervisor import HO2Supervisor`, etc. all succeed |
| V1 fallback | If V2 construction fails, main.py degrades to V1 SessionHost | V1 REPL works |
| E2E cognitive turn | "hello" at admin> → response via Kitchener loop | Response displayed, ledger has WO events |
| E2E degradation | Force HO2 failure → SH-V2 degrades to direct LLM call | Response displayed, DEGRADATION event in ledger |
| Registry lineage | Every package traces to registered spec and framework | G1 passes for all 23 |

### Existing Tests (regression)

All 163 tests across 6 new packages must still pass. All bootstrap tests must still pass.

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Current main.py | `_staging/PKG-ADMIN-001/HOT/admin/main.py` | Entrypoint to rewire |
| V1 build_session_host | `main.py:139-180` | Pattern for V2 builder |
| Shell constructor | `_staging/PKG-SHELL-001/HOT/kernel/shell.py:24-30` | DI signature |
| SessionHostV2 constructor | `_staging/PKG-SESSION-HOST-V2-001/HOT/kernel/session_host_v2.py:42-46` | DI signature |
| HO2Supervisor constructor | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py:88-96` | DI signature |
| HO1Executor constructor | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py:45-59` | DI signature |
| ContractLoader constructor | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/contract_loader.py:30` | DI signature |
| LLMGateway constructor | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py:156-163` | Gateway construction |
| HO2Config dataclass | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py:51-64` | Config fields |
| V2 AgentConfig dataclass | `_staging/PKG-SESSION-HOST-V2-001/HOT/kernel/session_host_v2.py:30-39` | Config fields |
| TokenBudgeter | `_staging/PKG-TOKEN-BUDGETER-001/HOT/kernel/token_budgeter.py` | Budgeter construction |
| ToolDispatcher | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/tool_dispatch.py:32-39` | Dispatcher construction |
| Authoritative framework registry | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/registries/frameworks_registry.csv` | Source of truth for backfill |
| Authoritative spec registry | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/registries/specs_registry.csv` | Source of truth for backfill |
| RESULTS_HANDOFF_9 | `_staging/handoffs/RESULTS_HANDOFF_9.md` | Gold-standard RESULTS format |
| BUILDER_HANDOFF_STANDARD | `_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` | RESULTS template, Required Kernel Tools, Reviewer Checklist |
| Kernel hashing tool | `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py:compute_sha256()` | Canonical hash format |
| Kernel packing tool | `_staging/PKG-KERNEL-001/HOT/kernel/packages.py:pack()` | Deterministic archives |

## 8. End-to-End Verification

```bash
# 1. Clean-room install
TMPDIR=$(mktemp -d)
tar xzf _staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
INSTALLDIR="$TMPDIR/INSTALL_ROOT"
mkdir -p "$INSTALLDIR"
bash "$TMPDIR/install.sh" --root "$INSTALLDIR" --dev

# Expected:
#   Packages: 23 total (23 receipts)
#   Gates: 8 passed, 0 failed

# 2. Import smoke test
python3 -c "
import sys
sys.path.insert(0, '$INSTALLDIR/HOT/kernel')
sys.path.insert(0, '$INSTALLDIR/HO1/kernel')
sys.path.insert(0, '$INSTALLDIR/HO2/kernel')
from shell import Shell
from session_host_v2 import SessionHostV2
from ho2_supervisor import HO2Supervisor
from ho1_executor import HO1Executor
from llm_gateway import LLMGateway
from work_order import WorkOrder
from contract_loader import ContractLoader
print('ALL IMPORTS OK')
"

# 3. Unit test regression
python3 -m pytest _staging/PKG-WORK-ORDER-001 _staging/PKG-HO1-EXECUTOR-001 \
    _staging/PKG-LLM-GATEWAY-001 _staging/PKG-HO2-SUPERVISOR-001 \
    _staging/PKG-SESSION-HOST-V2-001 _staging/PKG-SHELL-001 -v
# Expected: 163 passed

# 4. E2E smoke test (requires ANTHROPIC_API_KEY)
ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" python3 "$INSTALLDIR/HOT/admin/main.py" --root "$INSTALLDIR" --dev
# Type: hello
# Expected: assistant: [response from Kitchener loop]
# Verify ledger: WO_PLANNED, WO_DISPATCHED, LLM_CALL, WO_COMPLETED, WO_CHAIN_COMPLETE, WO_QUALITY_GATE
# Type: /exit
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `manifest.json` | `_staging/PKG-HO1-EXECUTOR-001/` | MODIFY (add framework_id, title, fix dep) |
| `manifest.json` | `_staging/PKG-HO2-SUPERVISOR-001/` | MODIFY (add package_type, supersedes) |
| `manifest.json` | `_staging/PKG-SESSION-HOST-V2-001/` | MODIFY (add supersedes, fix dep) |
| `manifest.json` | `_staging/PKG-ADMIN-001/` | MODIFY (add 6 V2 deps) |
| `admin_config.json` | `_staging/PKG-ADMIN-001/HOT/config/` | MODIFY (FMWK-005 → FMWK-000) |
| `frameworks_registry.csv` | `_staging/PKG-KERNEL-001/HOT/registries/` | MODIFY (1 → 8 rows) |
| `specs_registry.csv` | `_staging/PKG-KERNEL-001/HOT/registries/` | MODIFY (3 → 11 rows) |
| `main.py` | `_staging/PKG-ADMIN-001/HOT/admin/` | MODIFY (rewire to V2 Kitchener loop) |
| `PKG-KERNEL-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-ADMIN-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-HO1-EXECUTOR-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-HO2-SUPERVISOR-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-SESSION-HOST-V2-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD (23 packages) |
| `RESULTS_HANDOFF_13.md` | `_staging/handoffs/` | CREATE (backfill) |
| `RESULTS_HANDOFF_14.md` | `_staging/handoffs/` | CREATE (backfill) |
| `RESULTS_HANDOFF_15.md` | `_staging/handoffs/` | CREATE (backfill) |
| `RESULTS_HANDOFF_16B.md` | `_staging/handoffs/` | CREATE (backfill) |
| `RESULTS_HANDOFF_16.md` | `_staging/handoffs/` | MOVE (from package dir) |
| `RESULTS_HANDOFF_17.md` | `_staging/handoffs/` | MOVE (from package dir) |
| `RESULTS_HANDOFF_18.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **V1 remains as fallback.** If V2 construction fails at boot time, degrade to V1 SessionHost with a stderr warning. Do not break existing functionality.
2. **DI everywhere.** `build_session_host_v2()` constructs the entire dependency graph and passes it down. No module-level singletons.
3. **Three ledger instances.** HO2m (HO2 supervisor ledger), HO1m (HO1 execution ledger), and governance (existing). Each is a separate LedgerClient pointed at a separate .jsonl file.
4. **Registry updates are governance.** Adding frameworks to the registry is not optional infrastructure — it's the governance chain that makes G1 meaningful. Align with authoritative source in PKG-FRAMEWORK-WIRING-001.
5. **Use kernel tools.** `compute_sha256()` for hashes, `pack()` for archives. Never bypass these.
6. **E2E is the acceptance test.** Unit tests prove components work. E2E proves the system works. Both are required.
7. **Follow RESULTS_HANDOFF_9 as the gold standard.** That results file had everything: files modified, CP_BOOTSTRAP rebuilt, clean-room verification, gate results, baseline snapshot.

---

## 11. Known Pitfalls (Read Before Building)

These are verified pitfalls discovered during 10Q review. The spec above already accounts for them, but they're collected here so nothing is missed.

### Pitfall 1: `BudgetConfig`, not `BudgeterConfig`
The class is `BudgetConfig` at `token_budgeter.py:132`. Constructor: `TokenBudgeter(ledger_client, config: BudgetConfig, rate_limit_config=None)`. Do NOT invent a `BudgeterConfig` class.

### Pitfall 2: AgentConfig Name Collision
Both V1 (`session_host.py:39`) and V2 (`session_host_v2.py:30`) export `AgentConfig`. Same 9 fields (agent_id, agent_class, framework_id, tier, system_prompt, attention, tools, budget, permissions). V1 has `from_file()` classmethod; V2 doesn't. **Resolution**: import V2 with alias (`from session_host_v2 import AgentConfig as V2AgentConfig`) and construct manually from the config dict. V1's `AgentConfig.from_file()` is still used in the V1 fallback path — don't break it.

### Pitfall 3: HO2/ledger/ and HO1/ledger/ Directories Don't Exist
Bootstrap only creates `HOT/ledger/`. The `HO2/ledger/` and `HO1/ledger/` directories must be created explicitly in `build_session_host_v2()` before constructing LedgerClient instances:
```python
(root / "HO2" / "ledger").mkdir(parents=True, exist_ok=True)
(root / "HO1" / "ledger").mkdir(parents=True, exist_ok=True)
```

### Pitfall 4: Bootstrap Has 18 Packages, Not 17
Current `CP_BOOTSTRAP.tar.gz` contains **18** packages (PKG-WORK-ORDER-001 was added by H-13). You add **5** new archives (HO1, HO2, LLM-GW, SH-V2, SHELL) to reach 23. There are 24 `.tar.gz` files on disk — **exclude PKG-FLOW-RUNNER-001** (dead/superseded).

### Pitfall 5: `packages.py:pack()` Signature
`pack(src: Path, dest: Path, base: Optional[Path] = None) -> str`. The `src` arg is the package directory, `dest` is the output `.tar.gz` path. Returns raw hex digest (NOT `sha256:` prefixed). The manifest hashes still come from `compute_sha256()`.

---

## 12. Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-18** — Wire the 6 Kitchener code packages (H-13 through H-17) into a working system by fixing manifests, aligning registries, rewiring main.py, and running clean-room verification.

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_18_system_integration.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. No new packages — modify existing files only.
3. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
4. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir → run install.sh → ALL gates must pass. This is NOT optional.
5. Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail, and whether you introduced new failures.
6. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_18.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md. MUST include: Clean-Room Verification section, Baseline Snapshot section, Full Regression section. Missing sections = incomplete handoff.
7. Registry updates: Align PKG-KERNEL-001 registries with the authoritative source in PKG-FRAMEWORK-WIRING-001, plus add the 4 Kitchener frameworks.
8. CP_BOOTSTRAP rebuild: Rebuild with all 23 packages (18 current + 5 new). Report SHA256.
9. Backfill RESULTS files for H-13, H-14, H-15, H-16B.
10. Built-in tools: Use `hashing.py:compute_sha256()` for all SHA256 hashes and `packages.py:pack()` for all archives. NEVER use raw hashlib or shell tar. See "Required Kernel Tools" in BUILDER_HANDOFF_STANDARD.md.

**Read Section 11 (Known Pitfalls) BEFORE answering. It contains 5 verified traps.**

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. How many manifest.json files need editing, and which packages? What specific field(s) change in each?
2. What are the two wrong dependency references, and what should they each be corrected to? Why are the V1 packages these replace still kept in the bootstrap?
3. How many rows does frameworks_registry.csv currently have, and how many after? Name all 7 new framework IDs. Which 3 are backfill and which 4 are new Kitchener?
4. How many rows does specs_registry.csv currently have, and how many after? Name the 3 specs that reference non-FMWK-000 frameworks and confirm those frameworks will exist after Step 6.
5. What is the exact class name for the token budgeter config, and what module is it in? What is the TokenBudgeter constructor signature?
6. Two modules define `AgentConfig`. Name both files and their line numbers. What is your import strategy to avoid the collision? Which version gets used where?
7. What directories must be created before constructing LedgerClient instances for HO2m and HO1m? Why don't they exist already?
8. How many packages are currently in CP_BOOTSTRAP.tar.gz? How many new archives do you add? What is the one .tar.gz on disk that you must NOT include, and why?
9. In build_session_host_v2(), what must be constructed before HO1Executor, and what must HO1Executor exist before? List the full 6-component dependency chain.
10. How many RESULTS files total (write + move)? List each with its action (CREATE backfill, MOVE, or CREATE new).

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

---

## 13. Expected 10Q Answers (Reviewer Reference)

**Q1:** 4 manifest.json files:
- PKG-HO1-EXECUTOR-001: add `framework_id: FMWK-000`, `title: HO1 Executor`, change dep `PKG-PROMPT-ROUTER-001` → `PKG-LLM-GATEWAY-001`
- PKG-HO2-SUPERVISOR-001: add `package_type: kernel`, `supersedes: PKG-ATTENTION-001`
- PKG-SESSION-HOST-V2-001: add `supersedes: PKG-SESSION-HOST-001`, change dep `PKG-PROMPT-ROUTER-001` → `PKG-LLM-GATEWAY-001`
- PKG-ADMIN-001: add 6 deps (WO, Gateway, HO1, HO2, SH-V2, Shell), keep all existing V1 deps

Plus `admin_config.json` (not a manifest but also JSON edit): FMWK-005 → FMWK-000.

**Q2:** PKG-HO1-EXECUTOR-001 depends on PKG-PROMPT-ROUTER-001 → should be PKG-LLM-GATEWAY-001. PKG-SESSION-HOST-V2-001 depends on PKG-PROMPT-ROUTER-001 → should be PKG-LLM-GATEWAY-001. V1 packages stay because: (a) backward compat for degradation fallback, (b) PKG-LLM-GATEWAY-001 declares `supersedes: PKG-PROMPT-ROUTER-001` and handles the ownership transfer via its dependency chain.

**Q3:** Currently 1 data row (FMWK-000). After edit: 8 data rows. Backfill (from PKG-FRAMEWORK-WIRING-001): FMWK-001, FMWK-002, FMWK-007. New Kitchener: FMWK-008, FMWK-009, FMWK-010, FMWK-011.

**Q4:** Currently 3 data rows (SPEC-GENESIS-001, SPEC-GATE-001, SPEC-REG-001). After edit: 11. Non-FMWK-000: SPEC-LEDGER-001 → FMWK-002 (exists after Step 6 ✓), SPEC-PKG-001 → FMWK-007 (exists ✓), SPEC-SEC-001 → FMWK-001 (exists ✓).

**Q5:** `BudgetConfig` (NOT BudgeterConfig) from `token_budgeter.py:132`. Constructor: `TokenBudgeter(ledger_client: Any, config: BudgetConfig, rate_limit_config: Optional[RateLimitConfig] = None)`.

**Q6:** V1: `session_host.py:39` — has `from_file()` classmethod, used by V1 `build_session_host()`. V2: `session_host_v2.py:30` — no `from_file()`, same 9 fields. Import strategy: `from session_host_v2 import AgentConfig as V2AgentConfig`. V2AgentConfig used in `build_session_host_v2()` for SessionHostV2 + Shell. V1 AgentConfig untouched in fallback path.

**Q7:** `HO2/ledger/` and `HO1/ledger/` — created via `Path.mkdir(parents=True, exist_ok=True)`. They don't exist because bootstrap only creates `HOT/` tier directories. HO2 and HO1 layout dirs may exist but the `ledger/` subdirs do not.

**Q8:** Currently **18** packages in CP_BOOTSTRAP. Add **5** new: PKG-HO1-EXECUTOR-001, PKG-HO2-SUPERVISOR-001, PKG-LLM-GATEWAY-001, PKG-SESSION-HOST-V2-001, PKG-SHELL-001. **Exclude** PKG-FLOW-RUNNER-001 (dead/superseded, absorbed by HO2+HO1). Total = 23.

**Q9:** Before HO1: LedgerClient (×3), BudgetConfig → TokenBudgeter, ContractLoader, ToolDispatcher, LLMGateway + AnthropicProvider. HO1 must exist before: HO2Supervisor → SessionHostV2 → Shell. Full chain: (1) Ledgers → (2) TokenBudgeter → (3) ContractLoader + ToolDispatcher → (4) LLMGateway → (5) HO1Executor → (6) HO2 → SH-V2 → Shell.

**Q10:** 7 RESULTS files:
- CREATE (backfill): RESULTS_HANDOFF_13.md, RESULTS_HANDOFF_14.md, RESULTS_HANDOFF_15.md, RESULTS_HANDOFF_16B.md
- MOVE: RESULTS_HANDOFF_16.md (from PKG-SESSION-HOST-V2-001/), RESULTS_HANDOFF_17.md (from PKG-SHELL-001/)
- CREATE: RESULTS_HANDOFF_18.md
