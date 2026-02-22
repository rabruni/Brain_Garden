# BUILDER_HANDOFF_14: HO1 Executor — Canonical LLM Execution Point

## 1. Mission

Create `PKG-HO1-EXECUTOR-001` — the HO1 cognitive process that serves as the single canonical execution point for ALL LLM calls in the system. Every LLM invocation flows through HO1. This enforces Invariant #1 (no direct LLM calls) and Invariant #3 (agents don't remember, they READ). HO1 receives dispatched work orders from HO2, loads the appropriate prompt contract, calls the LLM Gateway, runs a multi-round tool loop when needed, validates output, debits the token budget, writes the canonical trace to HO1m, and returns the completed work order.

This is the **FIRST package targeting plane_id "ho1"** — the first non-HOT package in the system. All files install to `HO1/`, not `HOT/`.

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** New code ships as packages in `_staging/PKG-HO1-EXECUTOR-001/` with manifest.json, SHA256 hashes, proper dependencies. Follow existing package patterns.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → install Layers 0-3 (17 packages) → install YOUR new package. All gates must pass.
5. **No hardcoding.** Every threshold, timeout, retry count, rate limit — all config-driven. This is the #1 lesson from 7 layers of prior art.
6. **No file replacement.** Packages must NEVER overwrite another package's files. Use state-gating instead.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`).
8. **Results file.** When finished, write `_staging/RESULTS_HANDOFF_14.md` (see `BUILDER_HANDOFF_STANDARD.md`).
9. **Full regression test.** Run ALL staged package tests (not just yours) and report results. New failures you introduced are blockers. Pre-existing failures from unvalidated packages are noted but not blockers.
10. **Baseline snapshot.** Your results file must include a baseline snapshot (package count, file_ownership rows, total tests, all gate results) so the next agent can diff against it.

**Task-specific constraints:**

11. **Gateway via DI, not import.** The LLM Gateway instance is received via dependency injection (constructor parameter), NOT imported as a class. HO1 code MUST NOT `from HOT.kernel.prompt_router import PromptRouter` or similar. This satisfies FMWK-009 import restrictions — HO1 uses the Gateway without knowing its implementation.
12. **LedgerClient method is `write()`.** Never `append()`. The method signature is `write(entry: LedgerEntry) -> str`.
13. **plane_id is "ho1".** This is the first non-HOT package. The manifest must declare `"plane_id": "ho1"`. Files install to `HO1/`, not `HOT/`.
14. **Import path setup required.** HO1 code needs `sys.path` manipulation following the `main.py` `_ensure_import_paths()` pattern. Tests must set up these paths in fixtures.
15. **ToolDispatcher is COPIED, not imported.** Copy `tool_dispatch.py` (110 LOC) from `PKG-SESSION-HOST-001/HOT/kernel/tool_dispatch.py` into `HO1/kernel/tool_dispatch.py`. PKG-SESSION-HOST-001 is archived — importing from archived packages is forbidden.
16. **No caching in contract loader.** MVP contract loading: find by contract_id in contracts directory, validate against schema, extract boundary + I/O schemas. No caching, no hot-reload, no version resolution beyond directory scanning.

---

## 3. Architecture / Design

### HO1 Executor Flow

HO1 receives a WorkOrder from HO2 and executes it through this flow:

```
HO2 Supervisor
  │
  ▼
HO1Executor.execute(work_order: WorkOrder) → WorkOrder
  │
  ├─ Step 1: Transition state: dispatched → executing
  │
  ├─ Step 2: Load prompt contract by constraints.prompt_contract_id
  │   └─ ContractLoader.load(contract_id) → dict
  │       └─ Validate against prompt_contract.schema.json
  │
  ├─ Step 3: Validate input_context against contract.input_schema
  │   └─ If fails: WO → failed (input_schema_invalid)
  │
  ├─ Step 4: Build PromptRequest from contract + WO fields
  │   ├─ contract_id → constraints.prompt_contract_id
  │   ├─ max_tokens → contract.boundary.max_tokens
  │   ├─ temperature → contract.boundary.temperature
  │   ├─ template_variables → input_context
  │   ├─ work_order_id → wo_id
  │   ├─ session_id → session_id
  │   ├─ provider_id → contract.boundary.provider_id (optional)
  │   └─ structured_output → contract.boundary.structured_output (optional)
  │
  ├─ Step 5: TOOL LOOP (max iterations = constraints.turn_limit)
  │   │
  │   ├─ 5a. Call gateway.route(request) → response
  │   ├─ 5b. Log LLM_CALL to HO1m
  │   ├─ 5c. Debit budget via TokenBudgeter
  │   ├─ 5d. If response has tool_use blocks:
  │   │   ├─ For each tool_use: call ToolDispatcher.execute()
  │   │   ├─ Log TOOL_CALL to HO1m
  │   │   ├─ Append tool results to conversation
  │   │   └─ Continue loop
  │   ├─ 5e. If response is text (no tool_use):
  │   │   └─ Break loop
  │   └─ 5f. If budget exhausted or turn_limit reached:
  │       └─ Fail WO with budget_exhausted/turn_limit_exceeded
  │
  ├─ Step 6: Validate output against contract.output_schema (syntactic)
  │
  ├─ Step 7: Set WO.output_result, WO.cost, WO.completed_at
  │
  ├─ Step 8: Transition state: executing → completed (or failed)
  │
  ├─ Step 9: Log WO_COMPLETED or WO_FAILED to HO1m
  │
  └─ Step 10: Return completed WorkOrder to HO2
```

### Dependency Injection Pattern

HO1 receives ALL external dependencies through its constructor. This is the cornerstone of FMWK-009 compliance:

```python
class HO1Executor:
    def __init__(
        self,
        gateway,              # LLM Gateway instance (duck-typed, has .route())
        ledger: LedgerClient, # For writing to HO1m
        budgeter,             # TokenBudgeter instance
        tool_dispatcher,      # ToolDispatcher instance
        contract_loader,      # ContractLoader instance
        config: dict,         # Config (agent_id, agent_class, tier, etc.)
    ):
```

HO1 never imports `PromptRouter`, `LLMGateway`, or any HOT module that exposes tier state. It only imports:
- Python stdlib
- `PromptRequest` and `PromptResponse` dataclasses (value objects, not service classes)
- `LedgerClient` and `LedgerEntry` (syscall interface)
- `BudgetScope`, `TokenUsage` (value objects from TokenBudgeter)
- Its own modules (`contract_loader`, `tool_dispatch`)

### Contract Loading

Simple file-based resolution. No registry, no caching:

```
1. Receive contract_id from WO.constraints.prompt_contract_id
2. Scan contracts directory for JSON files
3. Load each, check if contract_id matches
4. Validate matching contract against prompt_contract.schema.json
5. Return parsed contract dict
6. If not found: raise ContractNotFoundError
```

### Tool Loop

Adapted from `SessionHost.process_turn()` (lines 178-284 of session_host.py):

```
1. Extract tool_use blocks from response content (JSON parsing)
2. For each tool_use: call ToolDispatcher.execute(tool_id, arguments)
3. Log each TOOL_CALL to HO1m
4. Build follow-up prompt with tool results appended
5. Send follow-up through gateway
6. Repeat until text response or budget/turn limit
```

The key difference from SessionHost: HO1 operates within a WO's budget and turn_limit constraints, not a session's.

### HO1m Trace Writing

Every significant action is logged to `HO1/ledger/worker.jsonl`:

| Event Type | When | Key Metadata |
|------------|------|-------------|
| `WO_EXECUTING` | State transition to executing | wo_id, session_id, contract_id |
| `LLM_CALL` | After each gateway.route() call | wo_id, input_tokens, output_tokens, model_id, latency_ms |
| `TOOL_CALL` | After each tool execution | wo_id, tool_id, status, error (if any) |
| `WO_COMPLETED` | Successful completion | wo_id, output_result summary, total cost |
| `WO_FAILED` | Any failure | wo_id, error code, error message |

All entries include `scope.tier = "ho1"` per FMWK-009 Section 5.

### Adversarial Analysis: DI for Gateway

**Hurdles**: First HO1 package means no established pattern for DI in this codebase. Constructor injection requires all callers (HO2 Supervisor, tests) to assemble the dependency graph. Import paths require `sys.path` setup since HO1 is a new tier directory.

**Too Much**: Building a full DI container, service locator, or auto-wiring framework. The system has 4-5 dependencies — manual constructor injection is sufficient.

**Not Enough**: Without DI, HO1 would `from HOT.kernel.prompt_router import PromptRouter` directly, violating FMWK-009 import restrictions and making testing require real infrastructure.

**Synthesis**: Manual constructor injection. Gateway, budgeter, ledger, tool_dispatcher, and contract_loader are all passed to the constructor. Tests mock them trivially. HO2 Supervisor (HANDOFF-15) assembles the real instances and injects them when creating HO1Executor.

### Adversarial Analysis: Contract Loader Scope

**Hurdles**: No contract registry infrastructure exists yet. Contracts are JSON files in a directory.

**Too Much**: Building caching, hot-reload, version resolution, registry integration. No consumer needs these features yet.

**Not Enough**: Without a contract loader, HO1 cannot execute contract-bound WOs. Without schema validation, invalid contracts cause silent failures.

**Synthesis**: MVP file-based loader. Scan directory, match contract_id, validate against schema. No caching. When a registry exists (future), the loader interface stays the same — only the resolution changes.

---

## 4. Implementation Steps

### Step 1: Write tests (DTT)

Create `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py` with all tests from the Test Plan (Section 6). Tests use `tmp_path` fixtures to create isolated plane roots. No real LLM calls — all gateway calls are mocked.

**Import path fixture**: Tests must add the package's `HO1/kernel/` directory to `sys.path` before importing HO1 modules. Create a conftest.py or use a fixture that does:

```python
import sys
from pathlib import Path

# Add HO1 kernel to path
ho1_kernel = Path(__file__).resolve().parent.parent / "kernel"
sys.path.insert(0, str(ho1_kernel))

# Add HOT kernel for LedgerClient, PromptRequest, etc.
# (In tests, these come from _staging packages)
staging = Path(__file__).resolve().parent.parent.parent.parent
hot_kernel = staging / "PKG-KERNEL-001" / "HOT" / "kernel"
sys.path.insert(0, str(hot_kernel))
router_kernel = staging / "PKG-PROMPT-ROUTER-001" / "HOT" / "kernel"
sys.path.insert(0, str(router_kernel))
budgeter_kernel = staging / "PKG-TOKEN-BUDGETER-001" / "HOT" / "kernel"
sys.path.insert(0, str(budgeter_kernel))
```

### Step 2: Copy ToolDispatcher

Copy `_staging/PKG-SESSION-HOST-001/HOT/kernel/tool_dispatch.py` (110 LOC) to `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/tool_dispatch.py`. No modifications needed — it is a self-contained module with no external imports beyond stdlib and dataclasses.

### Step 3: Implement contract_loader.py

Create `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/contract_loader.py`:

```python
"""Prompt contract loader for HO1 Executor.

Loads prompt contract JSON files by contract_id.
Validates against prompt_contract.schema.json.
MVP — no caching, no hot-reload, no version resolution.
"""
```

Class: `ContractLoader`

```python
class ContractLoader:
    def __init__(self, contracts_dir: Path, schema_path: Path):
        """
        Args:
            contracts_dir: Directory containing contract JSON files.
            schema_path: Path to prompt_contract.schema.json for validation.
        """

    def load(self, contract_id: str) -> dict:
        """Load and validate a prompt contract by contract_id.

        Scans contracts_dir for JSON files, loads each,
        returns the first whose contract_id field matches.
        Validates against prompt_contract.schema.json.

        Args:
            contract_id: The contract ID to find (e.g., "PRC-CLASSIFY-001").

        Returns:
            Parsed contract dict.

        Raises:
            ContractNotFoundError: If no contract matches the ID.
            ContractValidationError: If the contract fails schema validation.
        """
```

Custom exceptions:
- `ContractNotFoundError(contract_id: str)` — contract_id not found in contracts directory
- `ContractValidationError(contract_id: str, errors: list[str])` — schema validation failed

### Step 4: Implement ho1_executor.py

Create `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py`:

```python
"""HO1 Executor — canonical execution point for all LLM calls.

Every LLM invocation flows through HO1. This enforces:
  - Invariant #1: No direct LLM calls
  - Invariant #3: Agents don't remember, they READ

HO1 receives WorkOrders from HO2, executes them, and returns results.
"""
```

Class: `HO1Executor`

Constructor parameters (all via DI):

| Parameter | Type | Source |
|-----------|------|--------|
| `gateway` | duck-typed (has `.route(PromptRequest) -> PromptResponse`) | Injected by HO2 or test |
| `ledger` | `LedgerClient` | Pre-configured with HO1m ledger path |
| `budgeter` | duck-typed (has `.check()`, `.debit()`) | TokenBudgeter instance |
| `tool_dispatcher` | `ToolDispatcher` | Pre-configured with registered tools |
| `contract_loader` | `ContractLoader` | Pre-configured with contracts dir and schema path |
| `config` | `dict` | Agent configuration: `agent_id`, `agent_class`, `framework_id`, `package_id`, `tier` |

Primary method:

```python
def execute(self, work_order: dict) -> dict:
    """Execute a work order and return the completed/failed WO.

    Args:
        work_order: WorkOrder as a dict (from PKG-WORK-ORDER-001 or plain dict).

    Returns:
        The work order dict with output_result, cost, completed_at, and state populated.
    """
```

**Why dict, not WorkOrder dataclass?** PKG-WORK-ORDER-001 (HANDOFF-13) may or may not be built when this package ships. Using dicts makes the interface resilient to the WO dataclass not existing yet. When the dataclass exists, the dict IS the serialized form. The executor reads known keys and is forward-compatible.

Internal methods:

| Method | Purpose |
|--------|---------|
| `_transition_state(wo, new_state)` | Set `wo["state"]` and log transition |
| `_load_contract(contract_id)` | Delegate to ContractLoader |
| `_validate_input(contract, input_context)` | Validate against contract's input_schema |
| `_build_prompt_request(wo, contract)` | Map WO + contract fields to PromptRequest |
| `_extract_tool_uses(content)` | Parse tool_use blocks from response content |
| `_run_tool_loop(wo, contract, request)` | The multi-round tool loop |
| `_validate_output(contract, content)` | Validate against contract's output_schema |
| `_log_event(event_type, wo, **metadata)` | Write to HO1m via LedgerClient |
| `_debit_budget(wo, response)` | Debit tokens via TokenBudgeter |

### Step 5: Create prompt contracts

Create three minimum viable contracts:

**`HO1/contracts/classify.json`** — Intent classification:
```json
{
  "contract_id": "PRC-CLASSIFY-001",
  "version": "1.0.0",
  "prompt_pack_id": "PRM-CLASSIFY-001",
  "tier": "ho1",
  "boundary": {
    "max_tokens": 500,
    "temperature": 0
  },
  "input_schema": {
    "type": "object",
    "required": ["user_input"],
    "properties": {
      "user_input": {
        "type": "string",
        "description": "Raw user utterance to classify"
      }
    }
  },
  "output_schema": {
    "type": "object",
    "required": ["speech_act", "ambiguity"],
    "properties": {
      "speech_act": {
        "type": "string",
        "enum": ["greeting", "question", "command", "reentry_greeting", "farewell"]
      },
      "ambiguity": {
        "type": "string",
        "enum": ["low", "medium", "high"]
      }
    },
    "additionalProperties": true
  }
}
```

**`HO1/contracts/synthesize.json`** — Response synthesis:
```json
{
  "contract_id": "PRC-SYNTHESIZE-001",
  "version": "1.0.0",
  "prompt_pack_id": "PRM-SYNTHESIZE-001",
  "tier": "ho1",
  "boundary": {
    "max_tokens": 4096,
    "temperature": 0.3
  },
  "input_schema": {
    "type": "object",
    "required": ["prior_results"],
    "properties": {
      "prior_results": {
        "type": "array",
        "items": { "type": "object" },
        "description": "Results from prior WOs to synthesize"
      },
      "user_input": {
        "type": "string",
        "description": "Original user input for context"
      }
    }
  },
  "output_schema": {
    "type": "object",
    "required": ["response_text"],
    "properties": {
      "response_text": {
        "type": "string",
        "description": "User-facing synthesized response"
      }
    },
    "additionalProperties": true
  }
}
```

**`HO1/contracts/execute.json`** — General execution:
```json
{
  "contract_id": "PRC-EXECUTE-001",
  "version": "1.0.0",
  "prompt_pack_id": "PRM-EXECUTE-001",
  "tier": "ho1",
  "boundary": {
    "max_tokens": 4096,
    "temperature": 0.0
  },
  "input_schema": {
    "type": "object",
    "required": ["user_input"],
    "properties": {
      "user_input": {
        "type": "string",
        "description": "User input or instruction to execute"
      },
      "assembled_context": {
        "type": "object",
        "description": "Context assembled by HO2 attention"
      }
    }
  },
  "output_schema": {
    "type": "object",
    "required": ["result"],
    "properties": {
      "result": {
        "type": "string",
        "description": "Execution result"
      }
    },
    "additionalProperties": true
  }
}
```

### Step 6: Create manifest.json

```json
{
  "package_id": "PKG-HO1-EXECUTOR-001",
  "version": "1.0.0",
  "schema_version": "1.2",
  "title": "HO1 Executor — Canonical LLM Execution Point",
  "description": "HO1 cognitive process: executes work orders via prompt contracts, tool loop, and budget enforcement",
  "spec_id": "SPEC-GATE-001",
  "framework_id": "FMWK-000",
  "plane_id": "ho1",
  "layer": 3,
  "dependencies": [
    "PKG-KERNEL-001",
    "PKG-PROMPT-ROUTER-001",
    "PKG-TOKEN-BUDGETER-001"
  ],
  "assets": [
    {
      "path": "HO1/kernel/ho1_executor.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "kernel"
    },
    {
      "path": "HO1/kernel/contract_loader.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "kernel"
    },
    {
      "path": "HO1/kernel/tool_dispatch.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "kernel"
    },
    {
      "path": "HO1/contracts/classify.json",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "config"
    },
    {
      "path": "HO1/contracts/synthesize.json",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "config"
    },
    {
      "path": "HO1/contracts/execute.json",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "config"
    },
    {
      "path": "HO1/tests/test_ho1_executor.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "test"
    },
    {
      "path": "manifest.json",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "manifest"
    }
  ]
}
```

### Step 7: Build package archive

```bash
# From _staging/
cd PKG-HO1-EXECUTOR-001
# Compute SHA256 for all assets and update manifest.json
# Build archive:
tar czf ../PKG-HO1-EXECUTOR-001.tar.gz -C . $(ls .)
```

Or use Python `tarfile` with explicit `arcname`:
```python
import tarfile
from pathlib import Path

def build_pkg(pkg_dir, output_path):
    with tarfile.open(output_path, "w:gz") as tf:
        for f in sorted(Path(pkg_dir).rglob("*")):
            if f.is_file() and "__pycache__" not in str(f):
                tf.add(str(f), arcname=str(f.relative_to(pkg_dir)))
```

### Step 8: Verification and results

Run package tests, full regression, write results file.

---

## 5. Package Plan

### New Package

| Field | Value |
|-------|-------|
| Package ID | `PKG-HO1-EXECUTOR-001` |
| Layer | 3 |
| spec_id | `SPEC-GATE-001` |
| framework_id | `FMWK-000` |
| plane_id | `ho1` |
| Dependencies | `PKG-KERNEL-001`, `PKG-PROMPT-ROUTER-001`, `PKG-TOKEN-BUDGETER-001` |

### Assets

| Path | Classification | Description |
|------|---------------|-------------|
| `HO1/kernel/ho1_executor.py` | kernel | HO1Executor class with execute() and tool loop |
| `HO1/kernel/contract_loader.py` | kernel | ContractLoader for loading prompt contracts |
| `HO1/kernel/tool_dispatch.py` | kernel | ToolDispatcher (copied from PKG-SESSION-HOST-001) |
| `HO1/contracts/classify.json` | config | PRC-CLASSIFY-001 prompt contract |
| `HO1/contracts/synthesize.json` | config | PRC-SYNTHESIZE-001 prompt contract |
| `HO1/contracts/execute.json` | config | PRC-EXECUTE-001 prompt contract |
| `HO1/tests/test_ho1_executor.py` | test | 25+ tests |
| `manifest.json` | manifest | Package manifest |

### No Modified Packages

This handoff creates ONE new package. No existing packages are modified.

---

## 6. Test Plan

**File:** `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py`

All tests use `tmp_path` fixtures for isolated plane roots. No real LLM calls. All gateway calls return mock PromptResponse objects. All budgeter calls return mock DebitResult objects.

### Key Mock Setup

```python
# Mock gateway: has .route() method
mock_gateway = Mock()
mock_gateway.route.return_value = PromptResponse(
    content='{"speech_act": "greeting", "ambiguity": "low"}',
    outcome=RouteOutcome.SUCCESS,
    input_tokens=100, output_tokens=50,
    model_id="mock-model", provider_id="mock",
    latency_ms=100.0, timestamp="2026-02-14T00:00:00Z",
    exchange_entry_id="LED-mock001",
)

# Mock budgeter: has .check() and .debit()
mock_budgeter = Mock()
mock_budgeter.check.return_value = BudgetCheckResult(allowed=True, remaining=10000)
mock_budgeter.debit.return_value = DebitResult(
    success=True, remaining=9850, total_consumed=150,
    cost_incurred=0.001, ledger_entry_id="LED-budget01",
)

# Mock ledger: has .write()
mock_ledger = Mock()
mock_ledger.write.return_value = "LED-trace01"
```

### Execute Flow Tests

| # | Test | Validates |
|---|------|-----------|
| 1 | `test_execute_classify_happy_path` | Full classify WO: load contract, call gateway, validate output, return completed WO with output_result |
| 2 | `test_execute_synthesize_happy_path` | Full synthesize WO: different contract, different input_schema, completed |
| 3 | `test_execute_general_happy_path` | Full execute WO: PRC-EXECUTE-001 contract |
| 4 | `test_execute_tool_call_wo_type` | WO with wo_type=tool_call: dispatches to ToolDispatcher, no LLM call |
| 5 | `test_execute_returns_completed_state` | Returned WO has state="completed" |
| 6 | `test_execute_populates_output_result` | Returned WO has output_result set from gateway response |
| 7 | `test_execute_populates_cost_fields` | Returned WO has cost.input_tokens, cost.output_tokens, cost.total_tokens, cost.llm_calls set |
| 8 | `test_execute_populates_completed_at` | Returned WO has completed_at set to ISO8601 timestamp |

### Contract Loading Tests

| # | Test | Validates |
|---|------|-----------|
| 9 | `test_contract_loader_load_by_id` | ContractLoader.load("PRC-CLASSIFY-001") returns classify contract |
| 10 | `test_contract_loader_validates_schema` | Loaded contract passes prompt_contract.schema.json validation |
| 11 | `test_contract_loader_missing_contract` | ContractLoader.load("PRC-NONEXISTENT-001") raises ContractNotFoundError |
| 12 | `test_contract_loader_invalid_schema` | Contract with missing required fields raises ContractValidationError |
| 13 | `test_contract_loader_extracts_boundary` | Loaded contract has boundary.max_tokens and boundary.temperature |

### Tool Loop Tests

| # | Test | Validates |
|---|------|-----------|
| 14 | `test_tool_loop_single_tool_call` | Gateway returns tool_use → ToolDispatcher called → follow-up sent → text response returned |
| 15 | `test_tool_loop_multi_round` | Gateway returns tool_use twice → two rounds of tool dispatch → text response on third call |
| 16 | `test_tool_loop_budget_exhausted_mid_loop` | Budgeter returns budget_exhausted after first LLM call → WO fails with budget_exhausted |
| 17 | `test_tool_loop_turn_limit_exceeded` | Turn limit = 2, gateway keeps returning tool_use → WO fails with turn_limit_exceeded |
| 18 | `test_tool_use_extraction_parses_json` | _extract_tool_uses correctly parses tool_use blocks from JSON response content |

### Budget Enforcement Tests

| # | Test | Validates |
|---|------|-----------|
| 19 | `test_budget_debit_after_each_call` | budgeter.debit() called once per gateway.route() call |
| 20 | `test_budget_exhausted_fails_wo` | When budgeter.check() returns allowed=False, WO fails with budget_exhausted |
| 21 | `test_budget_scope_uses_wo_fields` | BudgetScope constructed with correct session_id and work_order_id |

### State Transition Tests

| # | Test | Validates |
|---|------|-----------|
| 22 | `test_state_dispatched_to_executing` | WO state transitions from "dispatched" to "executing" at start |
| 23 | `test_state_executing_to_completed` | WO state transitions from "executing" to "completed" on success |
| 24 | `test_state_executing_to_failed` | WO state transitions from "executing" to "failed" on error |

### HO1m Trace Writing Tests

| # | Test | Validates |
|---|------|-----------|
| 25 | `test_trace_llm_call_entry` | LedgerClient.write() called with event_type="LLM_CALL" after gateway.route() |
| 26 | `test_trace_tool_call_entry` | LedgerClient.write() called with event_type="TOOL_CALL" after tool dispatch |
| 27 | `test_trace_wo_completed_entry` | LedgerClient.write() called with event_type="WO_COMPLETED" on success |
| 28 | `test_trace_wo_failed_entry` | LedgerClient.write() called with event_type="WO_FAILED" on failure |

### Input/Output Validation Tests

| # | Test | Validates |
|---|------|-----------|
| 29 | `test_input_validation_passes` | Valid input_context passes input_schema check |
| 30 | `test_input_validation_fails` | Missing required field in input_context → WO fails with input_schema_invalid |
| 31 | `test_output_validation_passes` | Valid response content passes output_schema check |
| 32 | `test_output_validation_fails` | Invalid response → WO set to failed with output_schema_invalid |

### Error Handling Tests

| # | Test | Validates |
|---|------|-----------|
| 33 | `test_gateway_error_fails_wo` | Gateway raises exception → WO fails with gateway_error |
| 34 | `test_contract_missing_fails_wo` | Non-existent contract_id → WO fails with contract_not_found |
| 35 | `test_budget_gone_before_start` | Budget check fails before first call → WO fails with budget_exhausted |

**35 tests total.** Covers: execute flow (8), contract loading (5), tool loop (5), budget enforcement (3), state transitions (3), HO1m trace (4), I/O validation (4), error handling (3).

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| PromptRequest/PromptResponse dataclasses | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/prompt_router.py` (lines 36-82) | Field definitions for building PromptRequest from WO + contract |
| ToolDispatcher class | `_staging/PKG-SESSION-HOST-001/HOT/kernel/tool_dispatch.py` (110 LOC) | Copy into HO1 (self-contained, no external deps) |
| TokenBudgeter API | `_staging/PKG-TOKEN-BUDGETER-001/HOT/kernel/token_budgeter.py` (lines 27-99) | BudgetScope, TokenUsage, DebitResult, BudgetCheckResult dataclasses |
| LedgerClient.write() | `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` (line 384) | write(LedgerEntry) -> str API |
| LedgerEntry dataclass | `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` (lines 104-128) | Fields for trace entries |
| SessionHost tool loop | `_staging/PKG-SESSION-HOST-001/HOT/kernel/session_host.py` (lines 178-284) | Pattern for tool_use extraction, tool dispatch, and follow-up prompting |
| prompt_contract.schema.json | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/prompt_contract.schema.json` | Schema for contract validation in ContractLoader |
| WO Schema (FMWK-008) | `_staging/FMWK-008_Work_Order_Protocol/work_order_protocol.md` (Section 4) | WO field names and structure |
| FMWK-009 import restrictions | `_staging/FMWK-009_Tier_Boundary/tier_boundary.md` (Section 3) | HO1 import rules |
| FMWK-011 contract loading | `_staging/FMWK-011_Prompt_Contracts/prompt_contracts.md` (Section 8) | Contract resolution flow |
| main.py import paths | `_staging/PKG-ADMIN-001/HOT/admin/main.py` | `_ensure_import_paths()` pattern for sys.path setup |

---

## 8. End-to-End Verification

```bash
# 1. Run package tests
cd Control_Plane_v2/_staging
CONTROL_PLANE_ROOT="/tmp/test" python3 -m pytest PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py -v
# Expected: 35 tests pass

# 2. Verify contract files are valid JSON
python3 -c "
import json
from pathlib import Path
contracts = Path('PKG-HO1-EXECUTOR-001/HO1/contracts')
for f in contracts.glob('*.json'):
    data = json.loads(f.read_text())
    assert 'contract_id' in data, f'{f.name}: missing contract_id'
    assert 'boundary' in data, f'{f.name}: missing boundary'
    print(f'{f.name}: {data[\"contract_id\"]} v{data[\"version\"]} OK')
"
# Expected: classify.json, synthesize.json, execute.json all OK

# 3. Verify contracts against schema
python3 -c "
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path('PKG-KERNEL-001/HOT/kernel')))
from schema_validator import SchemaValidator
schema_path = Path('PKG-PHASE2-SCHEMAS-001/HOT/schemas/prompt_contract.schema.json')
sv = SchemaValidator(schema_path.parent)
contracts = Path('PKG-HO1-EXECUTOR-001/HO1/contracts')
for f in contracts.glob('*.json'):
    data = json.loads(f.read_text())
    ok, errors = sv.validate(data, 'prompt_contract.schema.json')
    print(f'{f.name}: valid={ok} errors={errors}')
"
# Expected: All valid=True

# 4. Verify package archive contents
tar tzf PKG-HO1-EXECUTOR-001.tar.gz
# Expected:
#   manifest.json
#   HO1/kernel/ho1_executor.py
#   HO1/kernel/contract_loader.py
#   HO1/kernel/tool_dispatch.py
#   HO1/contracts/classify.json
#   HO1/contracts/synthesize.json
#   HO1/contracts/execute.json
#   HO1/tests/test_ho1_executor.py

# 5. Verify manifest plane_id
python3 -c "
import json
m = json.loads(open('PKG-HO1-EXECUTOR-001/manifest.json').read())
assert m['plane_id'] == 'ho1', f'Expected ho1, got {m[\"plane_id\"]}'
assert m['layer'] == 3
print(f'plane_id={m[\"plane_id\"]}, layer={m[\"layer\"]}')
"
# Expected: plane_id=ho1, layer=3

# 6. Verify ToolDispatcher was copied (not imported)
python3 -c "
from pathlib import Path
src = Path('PKG-SESSION-HOST-001/HOT/kernel/tool_dispatch.py')
dst = Path('PKG-HO1-EXECUTOR-001/HO1/kernel/tool_dispatch.py')
assert dst.exists(), 'ToolDispatcher not copied'
assert 'class ToolDispatcher' in dst.read_text()
print('ToolDispatcher copied OK')
"
# Expected: ToolDispatcher copied OK

# 7. Verify no forbidden imports in HO1 code
python3 -c "
from pathlib import Path
forbidden = ['from HO2', 'import HO2', 'from HOT.ledger', 'from HOT.registries', 'from HOT.config']
for f in Path('PKG-HO1-EXECUTOR-001/HO1/kernel').glob('*.py'):
    content = f.read_text()
    for pattern in forbidden:
        assert pattern not in content, f'{f.name} contains forbidden import: {pattern}'
print('No forbidden imports found')
"
# Expected: No forbidden imports found

# 8. Full regression
cd Control_Plane_v2/_staging
python3 -m pytest . -v --ignore=PKG-FLOW-RUNNER-001
# Expected: all pass, no new failures

# 9. Write results file
# _staging/RESULTS_HANDOFF_14.md
```

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/` | CREATE |
| `contract_loader.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/` | CREATE |
| `tool_dispatch.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/` | CREATE (copy from PKG-SESSION-HOST-001) |
| `classify.json` | `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/` | CREATE |
| `synthesize.json` | `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/` | CREATE |
| `execute.json` | `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/` | CREATE |
| `test_ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/` | CREATE |
| `manifest.json` | `_staging/PKG-HO1-EXECUTOR-001/` | CREATE |
| `PKG-HO1-EXECUTOR-001.tar.gz` | `_staging/` | CREATE |
| `RESULTS_HANDOFF_14.md` | `_staging/` | CREATE |

**Not modified:** No existing packages are modified. This handoff creates one new package only.

---

## 10. Design Principles

1. **DI is the tier boundary.** HO1 receives the Gateway instance through constructor injection, not import. This is not a stylistic choice — it is how FMWK-009 is enforced at the code level. HO1 never knows the Gateway's class name or module path. It only knows the interface: `.route(PromptRequest) -> PromptResponse`.

2. **HO1 is stateless per WO.** HO1 does not maintain state between work orders. Each `execute()` call is self-contained: load contract, call gateway, return result. Session state is HO2's responsibility.

3. **Every action is traced.** Every LLM call, every tool execution, every state transition, every failure is written to HO1m. The trace is the audit trail. Without it, no one can verify what HO1 did.

4. **Budget is law.** HO1 checks the budget before each LLM call and debits after. If the budget is exhausted, the WO fails immediately. HO1 does not make "one more call" or "finish the current loop."

5. **Contracts are the API.** HO1 does not receive freeform prompts. It receives a contract_id that specifies what the LLM call looks like: boundary constraints, input schema, output schema. The contract is the IPC between HO2 and HO1.

6. **Fail fast, fail loud.** Missing contract → fail. Invalid input → fail. Budget gone → fail. Gateway error → fail. Every failure sets WO state to `failed`, logs to HO1m, and returns to HO2 for handling. No silent swallowing.

7. **First HO1 package sets the pattern.** This is the first non-HOT package. The import path setup, the DI pattern, the HO1m trace format — these become the reference implementation for all future HO1 packages.
