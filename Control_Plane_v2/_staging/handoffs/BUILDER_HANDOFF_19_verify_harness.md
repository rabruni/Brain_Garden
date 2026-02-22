# BUILDER_HANDOFF_19: Verification Harness (PKG-VERIFY-001)

## 1. Mission

Build a single verification script (`verify.py`) that replaces the ad-hoc verification steps every builder agent and human reviewer currently does manually. After install, one command runs all governance gates, all unit tests, an import smoke check, and optionally an E2E smoke test. The script reports a combined pass/fail with structured output. Ships as PKG-VERIFY-001 and becomes part of CP_BOOTSTRAP.tar.gz.

**Package:** PKG-VERIFY-001

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** Ships as `_staging/PKG-VERIFY-001/` with manifest.json, SHA256 hashes, proper dependencies.
4. **End-to-end verification.** After building, run the full install chain including your new package. All gates must pass. Then run YOUR script from the installed root to verify it works.
5. **No hardcoding.** Test discovery paths, gate list, timeouts — all config-driven or auto-discovered.
6. **No file replacement.** Must not overwrite any file from another package.
7. **Tar archive format:** Use `packages.py:pack()` — NEVER shell tar.
8. **Results file.** Write `_staging/handoffs/RESULTS_HANDOFF_19.md`.
9. **Full regression test.** Run ALL staged package tests and report results.
10. **Baseline snapshot.** Results file must include baseline snapshot.
11. **Use kernel tools.** `hashing.py:compute_sha256()` for hashes, `packages.py:pack()` for archives.
12. **Hash format.** `sha256:<64hex>` (71 chars). Bare hex fails G0A.
13. **Read-only.** The verification script must NEVER write to the install root, modify files, create files in governed directories, or have any side effects. It reads and reports. Period. The only writes are to stdout/stderr and optionally a report file in a user-specified output path OUTSIDE the root.
14. **Subprocess isolation.** Gate checks and pytest run as subprocesses, not in-process. This prevents import pollution and matches how humans run these tools.
15. **Exit codes matter.** Exit 0 = all checks pass. Exit 1 = at least one failure. Builder agents and CI can use the exit code directly.
16. **Current bootstrap has 20 packages** (after CLEANUP-2 runs). Your package brings it to 21.

---

## 3. Architecture / Design

### What it replaces

Every handoff spec currently tells agents to do this manually:

```bash
# Step 1: Clean-room install
TMPDIR=$(mktemp -d)
tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
bash "$TMPDIR/install.sh" --root "$TMPDIR/INSTALL_ROOT" --dev

# Step 2: Gates
python3 "$TMPDIR/INSTALL_ROOT/HOT/scripts/gate_check.py" --root "$TMPDIR/INSTALL_ROOT" --all

# Step 3: Unit tests (agents guess which packages to test)
python3 -m pytest PKG-WORK-ORDER-001 PKG-HO1-EXECUTOR-001 ... -v

# Step 4: E2E smoke
echo "hello" | python3 "$TMPDIR/INSTALL_ROOT/HOT/admin/main.py" --root "$TMPDIR/INSTALL_ROOT" --dev
```

After this handoff, one command replaces all of that:

```bash
python3 "$ROOT/HOT/scripts/verify.py" --root "$ROOT"
```

Or with E2E:

```bash
python3 "$ROOT/HOT/scripts/verify.py" --root "$ROOT" --e2e
```

### Verification Levels

The script runs checks in sequence. Each level includes all previous levels. If a level fails, subsequent levels still run (do not short-circuit — report everything).

```
LEVEL 1: GATES (governance integrity)
├─ Calls: gate_check.py --root $ROOT --all
├─ Parses: per-gate PASS/FAIL
├─ Reports: 8 gate results
└─ Fails if: any gate fails

LEVEL 2: UNIT TESTS (component correctness)
├─ Discovers: all test_*.py files under $ROOT/{HOT,HO1,HO2}/**/tests/
├─ Calls: python3 -m pytest <discovered_files> -v --tb=short
├─ Parses: total/passed/failed/skipped from pytest exit code + output
├─ Reports: per-file results + summary
└─ Fails if: any test fails

LEVEL 3: IMPORT SMOKE (wiring correctness)
├─ Imports these modules from $ROOT paths:
│   shell, session_host_v2, ho2_supervisor, ho1_executor,
│   llm_gateway, work_order, contract_loader, token_budgeter,
│   ledger_client, anthropic_provider
├─ Reports: per-module OK/FAIL
└─ Fails if: any import fails

LEVEL 4: E2E SMOKE (end-to-end data flow) — opt-in via --e2e
├─ Requires: ANTHROPIC_API_KEY in environment
├─ Calls: echo "hello" | python3 $ROOT/HOT/admin/main.py --root $ROOT --dev
├─ Timeout: 30 seconds (configurable via --e2e-timeout)
├─ Checks: output contains a non-empty assistant response
│   NOT "Quality gate failed", NOT "error", NOT empty
├─ Reports: response preview (first 100 chars) + pass/fail
└─ Fails if: timeout, error output, empty response, or quality gate failure
└─ Skips if: --e2e not specified, or ANTHROPIC_API_KEY not set (with clear message)
```

### Interface

```
verify.py --root <dir> [OPTIONS]

Required:
  --root <dir>          Installed control plane root

Options:
  --e2e                 Run Level 4 E2E smoke test (requires ANTHROPIC_API_KEY)
  --e2e-timeout <sec>   E2E timeout in seconds (default: 30)
  --gates-only          Run only Level 1 (fast governance check)
  --json                Output structured JSON report to stdout
  --report <path>       Write report to file (outside root — never writes inside root)
  --verbose             Show full pytest output and gate details

Exit codes:
  0   All checks passed
  1   One or more checks failed
  2   Script error (bad arguments, missing root, etc.)
```

### Default behavior (no flags)

`verify.py --root $ROOT` runs Levels 1-3 (gates + tests + import smoke). Level 4 (E2E) requires explicit `--e2e`.

### Output format (default, human-readable)

```
═══ VERIFY: Control Plane v2 ══════════════════════════════

── Level 1: Gates ──────────────────────────────────────────
G0B:         PASS  (120 files, 0 orphans)
G1:          PASS  (20 chains)
G1-COMPLETE: PASS  (20 frameworks)
G2:          PASS
G3:          PASS
G4:          PASS
G5:          PASS
G6:          PASS  (3 ledgers, 110 entries)
Gates: 8/8 PASS

── Level 2: Unit Tests ─────────────────────────────────────
HOT/tests/test_work_order.py          37 passed
HO1/tests/test_ho1_executor.py        35 passed
HO2/tests/test_ho2_supervisor.py      47 passed
HOT/tests/test_llm_gateway.py         18 passed
HOT/tests/test_session_host_v2.py     14 passed
HOT/tests/test_shell.py               12 passed
HOT/tests/test_admin.py                8 passed
HOT/tests/test_anthropic_provider.py  24 passed
HOT/tests/test_token_budgeter.py      10 passed
...
Tests: 205 passed, 0 failed, 0 skipped

── Level 3: Import Smoke ───────────────────────────────────
shell                OK
session_host_v2      OK
ho2_supervisor       OK
ho1_executor         OK
llm_gateway          OK
work_order           OK
contract_loader      OK
token_budgeter       OK
ledger_client        OK
anthropic_provider   OK
Imports: 10/10 OK

── Level 4: E2E Smoke ──────────────────────────────────────
[SKIPPED — --e2e not specified]

════════════════════════════════════════════════════════════
RESULT: PASS (3/3 levels passed, 1 skipped)
════════════════════════════════════════════════════════════
```

### JSON output (--json)

```json
{
  "result": "PASS",
  "levels": {
    "gates": {"status": "PASS", "passed": 8, "failed": 0, "details": [...]},
    "tests": {"status": "PASS", "total": 205, "passed": 205, "failed": 0, "skipped": 0},
    "imports": {"status": "PASS", "total": 10, "ok": 10, "failed": 0},
    "e2e": {"status": "SKIPPED", "reason": "--e2e not specified"}
  },
  "root": "/path/to/root",
  "timestamp": "2026-02-15T...",
  "package_count": 21
}
```

### Adversarial Analysis: Scope

**Hurdles**: Test discovery from an installed root is different from staging. In staging, tests are in `PKG-*/HOT/tests/`. When installed, they're in `$ROOT/HOT/tests/`, `$ROOT/HO1/tests/`, `$ROOT/HO2/tests/`. The script must discover from the INSTALLED layout, not the staging layout. Also: pytest needs `sys.path` set up correctly to import the modules under test — the same import path problem that plagues every handoff.

**Not Enough**: Without this script, every handoff spec repeats the same 4-step manual verification. Agents skip steps. Reviewers can't tell if verification actually ran. A missing verification script means missing verification.

**Too Much**: We could try to build a CI pipeline, a web dashboard, or a test runner framework. Overkill. One Python script, subprocess calls, parsed output. Keep it dead simple.

**Synthesis**: One script, four levels, subprocess isolation, auto-discovery. No framework, no dependencies beyond stdlib + pytest.

---

## 4. Implementation Steps

### Step 1: Create package directory structure

```
_staging/PKG-VERIFY-001/
├── HOT/
│   ├── scripts/
│   │   └── verify.py
│   └── tests/
│       └── test_verify.py
└── manifest.json
```

### Step 2: Write tests (DTT — tests first)

`test_verify.py` tests the verification script's output parsing and reporting logic. Since verify.py is primarily a subprocess orchestrator, tests focus on:

- Parsing gate_check.py output into structured results
- Parsing pytest output into pass/fail counts
- Import smoke check logic
- JSON output format
- Exit code behavior
- Handling of missing root directory
- Handling of --e2e without API key
- E2E output parsing (detecting "Quality gate failed" vs real response)
- Report generation

Tests should NOT call gate_check.py or pytest for real — mock subprocess calls.

### Step 3: Implement verify.py

The script is a subprocess orchestrator. It:

1. Parses arguments
2. Validates `--root` exists and has `HOT/scripts/gate_check.py`
3. Runs Level 1: `subprocess.run([python3, gate_check_path, "--root", root, "--all"])`
4. Parses gate output (regex: `^(G[0-9A-Z-]+): (PASS|FAIL)`)
5. Runs Level 2: `subprocess.run([python3, "-m", "pytest", *test_files, "-v", "--tb=short"])`
   - Test discovery: glob `{HOT,HO1,HO2}/**/tests/test_*.py` under root
   - Sets PYTHONPATH to include `$ROOT/HOT/kernel`, `$ROOT/HOT`, `$ROOT/HO1/kernel`, `$ROOT/HO2/kernel`
6. Parses pytest output (regex: `(\d+) passed`)
7. Runs Level 3: For each module, `subprocess.run([python3, "-c", f"import {module}"])` with PYTHONPATH set
8. If `--e2e`:
   - Checks `ANTHROPIC_API_KEY` in environ
   - Runs `subprocess.run(["echo", "hello"], stdout=PIPE)` piped to `subprocess.run([python3, main_py, "--root", root, "--dev"], stdin=PIPE, timeout=timeout)`
   - Checks output for success markers
9. Prints report (human or JSON)
10. Exits with appropriate code

### Step 4: Build manifest.json

```json
{
  "package_id": "PKG-VERIFY-001",
  "package_type": "kernel",
  "title": "Verification Harness",
  "version": "1.0.0",
  "schema_version": "1.2",
  "spec_id": "SPEC-GATE-001",
  "framework_id": "FMWK-000",
  "plane_id": "hot",
  "layer": 3,
  "assets": [
    {"path": "HOT/scripts/verify.py", "sha256": "sha256:<computed>", "classification": "script"},
    {"path": "HOT/tests/test_verify.py", "sha256": "sha256:<computed>", "classification": "test"}
  ],
  "dependencies": ["PKG-KERNEL-001", "PKG-VOCABULARY-001"],
  "metadata": {
    "created_at": "2026-02-15T00:00:00+00:00",
    "author": "builder",
    "description": "Verification harness — single command for gates, tests, import smoke, and E2E."
  }
}
```

Dependencies:
- PKG-KERNEL-001 — paths, hashing (used by gate_check)
- PKG-VOCABULARY-001 — gate_check.py lives here

### Step 5: Pack and add to bootstrap

1. Compute SHA256 hashes for both files
2. Pack `PKG-VERIFY-001.tar.gz` using `packages.py:pack()`
3. Rebuild `CP_BOOTSTRAP.tar.gz` with the new package (21 packages total — 20 from CLEANUP-2 + this one)

### Step 6: Clean-room install

```bash
TMPDIR=$(mktemp -d)
tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
mkdir -p "$TMPDIR/INSTALL_ROOT"
bash "$TMPDIR/install.sh" --root "$TMPDIR/INSTALL_ROOT" --dev
```

Expected: 21 packages, 8/8 gates.

### Step 7: Run verify.py from installed root

```bash
python3 "$TMPDIR/INSTALL_ROOT/HOT/scripts/verify.py" --root "$TMPDIR/INSTALL_ROOT"
```

This is the script verifying itself. Levels 1-3 must pass. Level 4 skipped (no --e2e).

### Step 8: Run own tests + full regression

```bash
# Own tests
python3 -m pytest PKG-VERIFY-001/HOT/tests/test_verify.py -v

# Full regression
python3 -m pytest PKG-WORK-ORDER-001 PKG-HO1-EXECUTOR-001 \
    PKG-HO2-SUPERVISOR-001 PKG-LLM-GATEWAY-001 \
    PKG-SESSION-HOST-V2-001 PKG-SHELL-001 PKG-ADMIN-001 \
    PKG-ANTHROPIC-PROVIDER-001 PKG-TOKEN-BUDGETER-001 \
    PKG-VERIFY-001 -v
```

---

## 5. Package Plan

### PKG-VERIFY-001 (new)

- **Package ID:** PKG-VERIFY-001
- **Layer:** 3
- **spec_id:** SPEC-GATE-001
- **framework_id:** FMWK-000
- **plane_id:** hot
- **Assets:**
  - `HOT/scripts/verify.py` — classification: script
  - `HOT/tests/test_verify.py` — classification: test
- **Dependencies:** `PKG-KERNEL-001`, `PKG-VOCABULARY-001`

---

## 6. Test Plan

### test_verify.py — minimum 15 tests

| # | Test Name | Validates | Expected |
|---|-----------|-----------|----------|
| 1 | `test_parse_gate_output_all_pass` | Parses gate_check output with 8 PASS lines | Returns 8 GateResult objects, all passed=True |
| 2 | `test_parse_gate_output_with_failure` | Parses output with G1: FAIL | Returns GateResult with passed=False for G1 |
| 3 | `test_parse_pytest_output_all_pass` | Parses "163 passed" from pytest output | Returns total=163, passed=163, failed=0 |
| 4 | `test_parse_pytest_output_with_failures` | Parses "160 passed, 3 failed" | Returns total=163, passed=160, failed=3 |
| 5 | `test_parse_pytest_output_with_skips` | Parses "160 passed, 2 skipped" | Returns total=162, passed=160, skipped=2 |
| 6 | `test_discover_test_files` | Discovers test_*.py under mock root | Returns paths from HOT/tests, HO1/tests, HO2/tests |
| 7 | `test_discover_no_tests` | Empty root with no test files | Returns empty list |
| 8 | `test_import_smoke_module_list` | Verifies the canonical module list | Contains all 10 expected modules |
| 9 | `test_e2e_output_success` | Parses output with real LLM response | Detects success |
| 10 | `test_e2e_output_quality_gate_fail` | Parses "Quality gate failed" in output | Detects failure |
| 11 | `test_e2e_output_empty` | No assistant response in output | Detects failure |
| 12 | `test_e2e_skipped_no_flag` | --e2e not specified | Reports SKIPPED |
| 13 | `test_e2e_skipped_no_api_key` | --e2e but no ANTHROPIC_API_KEY | Reports SKIPPED with reason |
| 14 | `test_json_output_format` | --json flag produces valid JSON | JSON has result, levels, root, timestamp keys |
| 15 | `test_exit_code_all_pass` | All levels pass | Exit code 0 |
| 16 | `test_exit_code_gate_failure` | Gate fails | Exit code 1 |
| 17 | `test_exit_code_test_failure` | pytest has failures | Exit code 1 |
| 18 | `test_missing_root` | --root points to nonexistent dir | Exit code 2, clear error |
| 19 | `test_invalid_root_no_gate_check` | --root exists but no gate_check.py | Exit code 2, clear error |
| 20 | `test_gates_only_flag` | --gates-only skips tests and imports | Only Level 1 runs |

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| gate_check.py | `_staging/PKG-VOCABULARY-001/HOT/scripts/gate_check.py` | Output format to parse |
| install.sh | `_staging/install.sh` | How gates are called post-install (line 178) |
| ADMIN main.py | `_staging/PKG-ADMIN-001/HOT/admin/main.py` | E2E entrypoint, `_ensure_import_paths()` pattern |
| BUILDER_HANDOFF_STANDARD.md | `_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` | Results file format |
| RESULTS_HANDOFF_18.md | `_staging/handoffs/RESULTS_HANDOFF_18.md` | Example of manual verification output to replicate |

---

## 8. End-to-End Verification

```bash
cd Control_Plane_v2/_staging

# 1. Build and pack
python3 -c "
import sys; sys.path.insert(0, 'PKG-KERNEL-001/HOT/kernel'); sys.path.insert(0, 'PKG-KERNEL-001/HOT')
from hashing import compute_sha256; from packages import pack
# compute hashes, write manifest, pack
"

# 2. Rebuild CP_BOOTSTRAP.tar.gz (21 packages)
# ... (include PKG-VERIFY-001.tar.gz)

# 3. Clean-room install
TMPDIR=$(mktemp -d)
tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
mkdir -p "$TMPDIR/INSTALL_ROOT"
bash "$TMPDIR/install.sh" --root "$TMPDIR/INSTALL_ROOT" --dev
# Expected: 21 packages, 8/8 gates

# 4. Run verify.py from installed root (THE proof)
python3 "$TMPDIR/INSTALL_ROOT/HOT/scripts/verify.py" --root "$TMPDIR/INSTALL_ROOT"
# Expected: Levels 1-3 PASS, Level 4 SKIPPED

# 5. Run verify.py with --json
python3 "$TMPDIR/INSTALL_ROOT/HOT/scripts/verify.py" --root "$TMPDIR/INSTALL_ROOT" --json
# Expected: valid JSON, result: "PASS"

# 6. Run own package tests
python3 -m pytest PKG-VERIFY-001/HOT/tests/test_verify.py -v
# Expected: 20 tests, all pass

# 7. Full regression
python3 -m pytest PKG-WORK-ORDER-001 PKG-HO1-EXECUTOR-001 \
    PKG-HO2-SUPERVISOR-001 PKG-LLM-GATEWAY-001 \
    PKG-SESSION-HOST-V2-001 PKG-SHELL-001 PKG-ADMIN-001 \
    PKG-ANTHROPIC-PROVIDER-001 PKG-TOKEN-BUDGETER-001 \
    PKG-VERIFY-001 -v
# Expected: all pass, zero new failures
```

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `verify.py` | `_staging/PKG-VERIFY-001/HOT/scripts/` | CREATE |
| `test_verify.py` | `_staging/PKG-VERIFY-001/HOT/tests/` | CREATE |
| `manifest.json` | `_staging/PKG-VERIFY-001/` | CREATE |
| `PKG-VERIFY-001.tar.gz` | `_staging/` | CREATE |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD (21 packages) |

---

## 10. Design Principles

1. **One command, full picture.** A human runs `verify.py --root $ROOT` and knows exactly what's passing and what's broken. No guessing, no multi-step manual process.
2. **Read-only. No side effects.** The script never writes to the install root. It reads files, runs subprocesses, and reports. If you run it twice, nothing changes.
3. **Subprocess isolation.** Gates and tests run as subprocesses with their own Python process. This prevents import pollution and matches how humans run these tools manually.
4. **Fail-open reporting.** If Level 1 fails, Levels 2-3 still run. Report everything. Don't short-circuit — the human needs the full picture to diagnose.
5. **Structured output.** `--json` gives machines a parseable report. Default gives humans a readable one. Same data, two formats.
6. **E2E is opt-in.** Level 4 requires `--e2e` and an API key. It hits a real LLM. Don't surprise people with API calls and costs.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-19** — Build verification harness (PKG-VERIFY-001)

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_19_verify_harness.md`

**Also read before answering:**
- `Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` — results file format, reviewer checklist
- `Control_Plane_v2/_staging/PKG-VOCABULARY-001/HOT/scripts/gate_check.py` (first 60 lines) — gate output format
- `Control_Plane_v2/_staging/install.sh` (lines 175-205) — how gates are called post-install

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: use `packages.py:pack()` — NEVER shell tar.
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz → install.sh → ALL gates must pass. Then run YOUR verify.py from the installed root. This is NOT optional.
6. Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_19.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md.
8. CP_BOOTSTRAP rebuild: Rebuild CP_BOOTSTRAP.tar.gz with 21 packages. Report member count and SHA256.
9. Built-in tools: Use `hashing.py:compute_sha256()` for hashes and `packages.py:pack()` for archives. Import path: `sys.path.insert(0, 'PKG-KERNEL-001/HOT/kernel'); sys.path.insert(0, 'PKG-KERNEL-001/HOT')`.
10. The script must be READ-ONLY. It must NEVER write to the install root. NEVER create files inside $ROOT. The only output is stdout/stderr and optionally a report file at a user-specified path OUTSIDE the root.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What are the 4 verification levels, what does each check, and which are run by default?
2. How does verify.py discover test files from an installed root? What glob pattern and which directories?
3. How does verify.py call gate_check.py — in-process import or subprocess? Why?
4. What exit codes does verify.py use, and what does each mean?
5. When --e2e is specified but ANTHROPIC_API_KEY is not set, what happens?
6. How do you set up PYTHONPATH for the pytest subprocess so it can import modules from the installed root?
7. What regex pattern do you use to parse gate_check.py output into per-gate results?
8. How many tests does your test file need, and what subprocess behavior do you mock?
9. How many packages will be in CP_BOOTSTRAP.tar.gz after your work, and what are your package's dependencies?
10. After clean-room install, what exact command proves your script works from the installed root?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers (for reviewer)

1. Level 1: Gates (gate_check.py --all, 8 gates). Level 2: Unit tests (pytest discovery). Level 3: Import smoke (10 key modules). Level 4: E2E smoke (echo hello through full stack, needs API key). Default runs 1-3. Level 4 requires --e2e.
2. Globs `{HOT,HO1,HO2}/**/tests/test_*.py` under `$ROOT`. These are the installed paths — packages unpack into these tier directories.
3. Subprocess (`subprocess.run([python3, gate_check_path, "--root", root, "--all"])`). Subprocess isolation prevents import pollution and matches manual usage.
4. Exit 0 = all checks passed. Exit 1 = at least one failure. Exit 2 = script error (bad args, missing root).
5. Level 4 reports SKIPPED with reason "ANTHROPIC_API_KEY not set". Not a failure — just skipped. Overall result still based on Levels 1-3.
6. Set `PYTHONPATH` in the subprocess env to include `$ROOT/HOT/kernel:$ROOT/HOT:$ROOT/HO1/kernel:$ROOT/HO2/kernel:$ROOT/HOT/scripts`.
7. `r'^(G[0-9A-Z_-]+):\s*(PASS|FAIL)'` — matches lines like "G0B: PASS" or "G1-COMPLETE: FAIL".
8. Minimum 15 tests (spec says 15, test plan has 20). Mock `subprocess.run` for gate_check, pytest, and import checks. Never call real subprocesses in unit tests.
9. 21 packages (20 from CLEANUP-2 + PKG-VERIFY-001). Dependencies: PKG-KERNEL-001, PKG-VOCABULARY-001.
10. `python3 "$TMPDIR/INSTALL_ROOT/HOT/scripts/verify.py" --root "$TMPDIR/INSTALL_ROOT"` — should print Levels 1-3 PASS, Level 4 SKIPPED, exit code 0.
