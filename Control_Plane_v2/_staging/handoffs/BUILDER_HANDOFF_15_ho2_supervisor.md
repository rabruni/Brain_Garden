# BUILDER_HANDOFF_15: HO2 Supervisor (PKG-HO2-SUPERVISOR-001)

## 1. Mission

Build `PKG-HO2-SUPERVISOR-001` -- the brain of the Modified Kitchener cognitive dispatch loop. This is the **first HO2 package** (`plane_id: "ho2"`) and the **largest package** in the build sequence. HO2 owns Kitchener Steps 2 (Scoping) and 4 (Verification). It plans work order chains, dispatches them to HO1 for execution, verifies results through a quality gate, manages session lifecycle, and assembles context through attention retrieval. HO2 absorbs pipeline logic from PKG-ATTENTION-001 and session patterns from PKG-SESSION-HOST-001.

**Critical invariant**: HO2 does NOT call LLM Gateway directly. ALL cognitive decisions -- planning, classification, verification, synthesis -- are dispatched as internal work orders to HO1. HO1 is the single canonical LLM execution point (v2 Invariant #1).

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design -> Test -> Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** New code ships as packages in `_staging/PKG-HO2-SUPERVISOR-001/` with manifest.json, SHA256 hashes, proper dependencies. Follow existing package patterns.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` -> install all layers -> verify HO2 package installs. All gates must pass.
5. **No hardcoding.** Every threshold, timeout, retry count, budget ceiling, max WO chain length -- all config-driven. No magic constants.
6. **No file replacement.** Packages must NEVER overwrite another package's files. Use state-gating instead.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` -- never `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`).
8. **Results file.** When finished, write `_staging/RESULTS_HANDOFF_15.md` (see `BUILDER_HANDOFF_STANDARD.md`).
9. **Full regression test.** Run ALL staged package tests (not just yours) and report results.
10. **Baseline snapshot.** Your results file must include a baseline snapshot.

**Task-specific constraints:**

11. **HO2 NEVER calls LLM Gateway directly.** All cognitive work (classify, verify, synthesize) is dispatched as WorkOrders to HO1Executor. This enforces Invariant #1. If you find yourself importing `prompt_router` or `llm_gateway` in HO2 code, you are violating this constraint.
12. **HO1Executor is a build-time dependency only.** In tests, HO1 is mocked. The package depends on HANDOFF-14 being complete (for the interface contract), but tests never call real HO1 code. Use `MockHO1Executor` that returns preset `WorkOrder` results.
13. **Factory pattern per FMWK-010.** HO2Supervisor code is written ONCE as generic code. Each agent class (ADMIN, RESIDENT) instantiates its own copy with different config (attention templates, ho2m_path, budget_ceiling, framework_config). Like a class vs. instance.
14. **LedgerClient method is `write()`, not `append()`.** All ledger writes use `ledger_client.write(LedgerEntry(...))`. Check `session_host.py` for the pattern.
15. **Absorb, do not import, from archived packages.** PKG-ATTENTION-001 and PKG-SESSION-HOST-001 are ARCHIVED. Copy and adapt the relevant logic into HO2 code. Do not import from those packages.
16. **plane_id is "ho2".** This is the first package that installs to the HO2 tier. The manifest.json must have `"plane_id": "ho2"`.

---

## 3. Architecture / Design

### 3.1 Component Overview

```
PKG-HO2-SUPERVISOR-001
|
+-- HO2/kernel/
|   +-- ho2_supervisor.py    # HO2Supervisor: handle_turn(), start_session(), end_session()
|   +-- attention.py          # AttentionRetriever: horizontal_scan(), priority_probe()
|   +-- quality_gate.py       # QualityGate: verify() -- Step 4
|   +-- session_manager.py    # SessionManager: session lifecycle, ID gen, history
|
+-- HO2/attention_templates/
|   +-- ATT-ADMIN-001.json    # Minimum viable ADMIN attention template
|
+-- HO2/tests/
|   +-- test_ho2_supervisor.py  # 40+ tests
|
+-- manifest.json
```

### 3.2 handle_turn Flow (Kitchener Steps 2-3-4)

This is the core flow. Every user message passes through this pipeline:

```
User input "hello"
  --> HO2Supervisor.handle_turn("hello")
    --> Step 2 (Scoping):
      --> Create WO#1: classify (wo_type=classify, input=user_message)
      --> Dispatch WO#1 to HO1Executor.execute()
      --> HO1 returns completed WO#1:
          {speech_act: "greeting", ambiguity: "high"}
      --> AttentionRetriever.horizontal_scan(ho2m_ledger)
          --> reads recent HO2m entries (WO chains, session context)
          --> returns ContextFragment[]
      --> AttentionRetriever.priority_probe(ho3m_path)
          --> reads HO3m for north stars, salience anchors
          --> returns ContextFragment[] (initially empty)
      --> Merge context: include-all up to attention budget
      --> Create WO#2: synthesize (wo_type=synthesize,
            input=classification+context, prior_results=[WO#1.output_result])

    --> Step 3 (Execute):
      --> Dispatch WO#2 to HO1Executor.execute()
      --> HO1 returns completed WO#2:
          {response_text: "Hello! How can I help you today?"}

    --> Step 4 (Verify):
      --> QualityGate.verify(
            output=WO#2.output_result,
            acceptance_criteria=from Step 2 planning
          )
      --> If PASS: proceed to return
      --> If FAIL: create retry WO with tighter constraints,
                   or log escalation if retry budget exhausted

    --> Log orchestration to HO2m:
      --> WO_PLANNED events (one per WO)
      --> WO_DISPATCHED events
      --> WO_CHAIN_COMPLETE with trace_hash
      --> WO_QUALITY_GATE with pass/fail decision

    --> Compute trace_hash:
      --> SHA256 of concatenated HO1m entries for this WO chain
      --> Stored on WO_CHAIN_COMPLETE and WO_QUALITY_GATE events

  --> Return TurnResult(
        response="Hello! How can I help you today?",
        wo_chain_summary=[WO#1, WO#2],
        cost_summary={input_tokens: N, output_tokens: N, llm_calls: 2}
      )
```

### 3.3 Absorption Mapping

This package absorbs code from 2 archived packages. The following table documents WHAT is absorbed, WHAT is adapted, and WHAT is dropped.

#### From PKG-ATTENTION-001 (attention_service.py, ~539 LOC)

| Element | Disposition | Detail |
|---------|-------------|--------|
| Pipeline execution model | **ABSORBED** | `_run_pipeline()` pattern: run stages sequentially, collect fragments, merge results, track budget. Reused in `AttentionRetriever._run_stages()`. |
| `BudgetTracker` | **ABSORBED** | Token/query/timeout tracking during context assembly. Reused as-is. |
| Template resolution | **ABSORBED** | `resolve_template()` + `_match_specificity()` logic for `applies_to` matching. Reused for selecting attention templates at stack creation. |
| `AssembledContext` | **ADAPTED** | Simplified for WO-scoped context. New name: `AttentionContext`. Fields: `context_text`, `context_hash`, `fragments`, `template_id`, `budget_used`. Drops `pipeline_trace` (HO2 logs to ledger instead). |
| `AttentionRequest` | **ADAPTED** | No longer driven by prompt contract. Now driven by WO's required_context and session state. Replaced by method params on `horizontal_scan()` and `priority_probe()`. |
| `AttentionService.assemble()` | **DROPPED** | Standalone service interface removed. Attention is now internal to HO2 -- called by `handle_turn()`, not by external consumers. |
| `ContextCache` | **DROPPED** | Cache adds complexity without clear benefit in WO-scoped context model. Each WO gets fresh context. |

#### From PKG-ATTENTION-001 (attention_stages.py, ~398 LOC)

| Element | Disposition | Detail |
|---------|-------------|--------|
| `ContextProvider` class | **ABSORBED** | Injectable I/O layer. `read_ledger_entries()`, `read_registry()`, `read_file()`, `search_text()`. Reused as HO2's I/O adapter for ledger/registry/file reads. |
| `ContextFragment` dataclass | **ABSORBED** | Fragment structure (`source`, `source_id`, `content`, `token_estimate`, `relevance_score`). Reused as-is. |
| `PipelineState` dataclass | **ABSORBED** | Mutable state for pipeline stages. Reused. |
| `StageOutput` dataclass | **ABSORBED** | Stage result type. Reused. |
| 8 individual stage runners | **ADAPTED** | Consolidated into 2 operations: `horizontal_scan` (reads HO2m + HO1m recent entries) and `priority_probe` (reads HO3m for salience anchors via POLICY_LOOKUP or pushed-down parameters). The `run_ledger_query`, `run_registry_query`, `run_horizontal_search`, and `run_structuring` runners are composed inside these 2 operations. |
| `run_halting` | **DROPPED** | Halting logic replaced by attention budget enforcement. If budget exceeded, return partial context. |
| `run_custom` + custom handler registry | **DROPPED** | No custom handlers needed at this stage. |

#### From PKG-SESSION-HOST-001 (session_host.py, ~315 LOC)

| Element | Disposition | Detail |
|---------|-------------|--------|
| Session ID format (`SES-{8 hex}`) | **ABSORBED** | `f"SES-{uuid.uuid4().hex[:8]}"`. Reused in `SessionManager.start_session()`. |
| Session start/end lifecycle | **ABSORBED** | `SESSION_START` and `SESSION_END` ledger events. Reused pattern with HO2m-scoped writes. |
| History tracking (`TurnMessage` list) | **ABSORBED** | In-memory turn history for context. Reused in `SessionManager`. |
| `TurnResult` dataclass | **ABSORBED** | Return type from `handle_turn()`. Adapted: adds `wo_chain_summary` and `cost_summary` fields. |
| `AgentConfig` dataclass | **ABSORBED** | Config structure for agent-class-specific instantiation. Adapted for factory pattern. |
| `process_turn()` main loop | **DROPPED** | Replaced by Kitchener dispatch (`handle_turn()`). The flat attention->router->tools->response flow is replaced by classify->attention->synthesize->verify. |
| Direct LLM calls (`_route_prompt()`) | **DROPPED** | All LLM calls go through HO1 via WorkOrder dispatch. HO2 never calls router/gateway directly. |
| Direct attention calls (`_build_attention_request()`) | **DROPPED** | Attention is now internal to HO2 (called directly in `handle_turn()`), not via an external service. |
| `ToolDispatcher` reference | **DROPPED** | Tool dispatch is HO1's responsibility. HO2 creates `tool_call` WOs; HO1 executes them. |

### 3.4 Component Design

#### ho2_supervisor.py -- `HO2Supervisor`

The main orchestrator. Written once, instantiated per agent class via factory pattern (FMWK-010).

```python
class HO2Supervisor:
    def __init__(
        self,
        plane_root: Path,
        agent_class: str,                    # "ADMIN" or "RESIDENT:<name>"
        ho1_executor: HO1ExecutorProtocol,   # Injected -- mocked in tests
        ledger_client: LedgerClient,         # Writes to HO2m
        token_budgeter: TokenBudgeter,       # Budget check/allocate
        config: HO2Config,                   # Per-agent config
    ): ...

    def start_session(self) -> str:
        """Initialize session. Returns session_id."""

    def end_session(self) -> None:
        """Close session. Write SESSION_END to HO2m."""

    def handle_turn(self, user_message: str) -> TurnResult:
        """Main entry: classify -> attention -> synthesize -> verify -> return."""
```

`HO2Config` dataclass:
```python
@dataclass
class HO2Config:
    attention_templates: list[str]     # Template IDs or paths
    ho2m_path: Path                    # HO2m ledger path (scoped per agent class)
    ho1m_path: Path                    # HO1m ledger path (for trace_hash computation)
    budget_ceiling: int                # Session token ceiling
    max_wo_chain_length: int           # Max WOs per turn (default: 10)
    max_retries: int                   # Max quality gate retries (default: 2)
    classify_contract_id: str          # Prompt contract for classify WOs
    synthesize_contract_id: str        # Prompt contract for synthesize WOs
    verify_contract_id: str            # Prompt contract for verify WOs
    attention_budget_tokens: int       # Max tokens for attention assembly
    attention_budget_queries: int      # Max queries for attention assembly
    attention_timeout_ms: int          # Timeout for attention assembly
```

`TurnResult` dataclass (adapted from PKG-SESSION-HOST-001):
```python
@dataclass
class TurnResult:
    response: str                      # User-facing response text
    wo_chain_summary: list[dict]       # [{wo_id, wo_type, state, cost}]
    cost_summary: dict                 # {input_tokens, output_tokens, llm_calls, tool_calls}
    session_id: str
    quality_gate_passed: bool
```

`HO1ExecutorProtocol` -- the interface HO2 depends on:
```python
class HO1ExecutorProtocol(Protocol):
    def execute(self, work_order: WorkOrder) -> WorkOrder:
        """Execute a work order and return it with output_result populated."""
        ...
```

#### attention.py -- `AttentionRetriever`

Absorbed from PKG-ATTENTION-001. Two operations:

```python
class AttentionRetriever:
    def __init__(
        self,
        plane_root: Path,
        context_provider: ContextProvider,   # Absorbed from attention_stages.py
        config: HO2Config,
    ): ...

    def horizontal_scan(self, session_id: str) -> AttentionContext:
        """Read recent HO2m entries for this session.
        Returns assembled context fragments from recent WO chains,
        session history, and HO1m summaries.
        Per FMWK-009: HO2 can read HO2m + HO1m."""

    def priority_probe(self) -> AttentionContext:
        """Read HO3m for north stars and salience anchors.
        Initially returns empty context (HO3m not yet populated).
        Per FMWK-009: HO2 accesses HO3m via POLICY_LOOKUP syscall
        or pushed-down parameters, NOT direct read."""

    def assemble_wo_context(
        self,
        horizontal: AttentionContext,
        priority: AttentionContext,
        user_message: str,
        classification: dict,
    ) -> dict:
        """Merge horizontal + priority context into assembled_context
        dict for a synthesize WO's input_context. Budget-aware:
        truncates to attention_budget_tokens."""
```

`AttentionContext` dataclass:
```python
@dataclass
class AttentionContext:
    context_text: str
    context_hash: str
    fragments: list[ContextFragment]
    template_id: str
    budget_used: BudgetUsed
```

#### quality_gate.py -- `QualityGate`

Step 4 (Verification):

```python
class QualityGate:
    def __init__(self, config: HO2Config): ...

    def verify(
        self,
        output_result: dict,
        acceptance_criteria: dict,
        wo_id: str,
    ) -> QualityGateResult:
        """Check WO output against acceptance criteria.
        Binary: accept or reject.
        Returns QualityGateResult with decision and reason."""
```

`QualityGateResult`:
```python
@dataclass
class QualityGateResult:
    decision: str        # "accept" or "reject"
    reason: str          # Why accepted or rejected
    wo_id: str
```

For MVP, acceptance criteria check:
- `output_result` is not None and not empty
- `output_result` contains a `response_text` key (for synthesize WOs)
- Response length > 0
- No error markers in output

Rejection triggers: create a new WO with tighter constraints (retry). If retries exhausted, log escalation event.

#### session_manager.py -- `SessionManager`

Session lifecycle:

```python
class SessionManager:
    def __init__(
        self,
        ledger_client: LedgerClient,
        agent_class: str,
        agent_id: str,
    ): ...

    def start_session(self) -> str:
        """Generate session ID (SES-{8 hex}), write SESSION_START to HO2m.
        Returns session_id."""

    def end_session(self, session_id: str, turn_count: int, total_cost: dict) -> None:
        """Write SESSION_END to HO2m with summary."""

    def add_turn(self, user_message: str, response: str) -> None:
        """Track turn in in-memory history."""

    @property
    def history(self) -> list[TurnMessage]:
        """Return turn history for this session."""

    @property
    def session_id(self) -> str:
        """Current session ID."""

    @property
    def wo_sequence(self) -> int:
        """Next WO sequence number for this session."""

    def next_wo_id(self) -> str:
        """Generate next WO ID: WO-{session_id}-{seq:03d}."""
```

### 3.5 WO Chain Orchestration

HO2 composes WOs into sequential pipelines (v1 pattern from FMWK-008 Section 8):

**Minimal chain (greeting)**:
```
WO-001 (classify) --> WO-002 (synthesize) --> quality gate --> return
```

**Standard chain (question)**:
```
WO-001 (classify) --> WO-002 (synthesize) --> quality gate --> return
```

**Tool chain (admin command)**:
```
WO-001 (classify) --> WO-002 (tool_call) --> WO-003 (synthesize) --> quality gate --> return
```

Each WO in the chain:
1. Created by HO2 with `WorkOrder.create()` (imports from PKG-WORK-ORDER-001)
2. Budget allocated via `TokenBudgeter.allocate()`
3. Budget checked via `TokenBudgeter.check()` before dispatch
4. Dispatched to `HO1Executor.execute()`
5. Result checked; if failed, HO2 handles error (retry or degrade)
6. Logged to HO2m as `WO_PLANNED` then `WO_DISPATCHED`

### 3.6 Degradation Path

Per v2 Section 1 and FMWK-010 Section 8:

```
HO1Executor.execute() raises exception
  --> HO2 catches
  --> Log DEGRADATION event to HO2m (governance violation)
  --> Attempt direct LLM call through LLM Gateway (backwards-compat)
  --> If that also fails, return error TurnResult
  --> IMPORTANT: direct LLM call is logged as governance violation
                 (Invariant #1 broken, but system stays available)
```

The degradation path exists to prevent total failure. It is NOT a normal code path.

### 3.7 Trace Hash Computation

Per FMWK-008 Section 5a:

```python
def compute_trace_hash(ho1m_entries: list[dict]) -> str:
    """SHA256 of concatenated HO1m entries for a WO chain."""
    serialized = "".join(json.dumps(e, sort_keys=True) for e in ho1m_entries)
    return hashlib.sha256(serialized.encode()).hexdigest()
```

Steps:
1. HO1 completes all WOs in the chain, writes trace entries to HO1m
2. HO2 reads HO1m entries for this chain (filter by session_id + wo_ids)
3. HO2 computes SHA256 of the concatenated entries
4. HO2 writes trace_hash on `WO_CHAIN_COMPLETE` and `WO_QUALITY_GATE` events

### 3.8 Adversarial Analysis

**Hurdles**: Largest package. 4 source files + 1 template + 1 test file. HO2 dispatches ALL LLM work to HO1 -- if HO1Executor is broken, HO2 cannot think at all. Attention absorption is ~300 LOC that needs adaptation. Memory arbitration has no existing code. The factory pattern must handle both ADMIN and RESIDENT configs without conflation.

**Too Much**: Full memory arbitration with offer-choice/auto-resume/escalate strategies. Parallel WO dispatch. Voting patterns. Multi-session multi-agent support. Full HO3m content population. All premature -- add complexity without current consumers.

**Not Enough**: Without quality gating, every HO1 response is accepted uncritically -- no verification loop. Without attention, HO1 gets no context and generates hallucinated responses. Without session management, there is no session state, no history, no continuity. Without the factory pattern, ADMIN and RESIDENT state bleeds across agent classes.

**Synthesis**: Build the inner loop (classify -> attention -> synthesize -> verify) with binary quality gate. Attention simplified to horizontal scan (HO2m recent entries) + priority probe (HO3m, returns empty initially). Arbitration deferred to simplest strategy: include-all fragments up to attention budget. Factory pattern via config injection. Degradation path exists as governed exception with logging.

---

## 4. Implementation Steps

### Step 1: Write tests (DTT)

Create `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py` with all 40+ tests from the Test Plan (Section 6). Tests use `tmp_path` fixtures, mocked HO1Executor, mocked LedgerClient, and mocked TokenBudgeter. No real LLM calls.

### Step 2: Implement data classes and protocols

Create shared types used across all HO2 modules:
- `TurnResult` dataclass
- `HO2Config` dataclass
- `HO1ExecutorProtocol` (typing.Protocol)
- `QualityGateResult` dataclass
- `AttentionContext` dataclass

Place these in `ho2_supervisor.py` or a separate `ho2_types.py` if cleaner (your choice -- keep imports minimal).

### Step 3: Implement session_manager.py

Create `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/session_manager.py`:
- `SessionManager` class
- Session ID generation: `f"SES-{uuid.uuid4().hex[:8]}"`
- `start_session()`: generate ID, write `SESSION_START` to HO2m via `ledger_client.write(LedgerEntry(...))`
- `end_session()`: write `SESSION_END` to HO2m
- `add_turn()`: append to in-memory history
- `next_wo_id()`: `f"WO-{self._session_id}-{self._wo_seq:03d}"`, increment `_wo_seq`
- Reuse patterns from `session_host.py` lines 104-123 and 296-315

### Step 4: Implement attention.py

Create `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/attention.py`:
- Copy and adapt `ContextProvider` from `attention_stages.py`
- Copy and adapt `ContextFragment`, `StageOutput`, `PipelineState`, `BudgetTracker` from absorbed packages
- `AttentionRetriever` class with:
  - `horizontal_scan(session_id)`: reads HO2m recent entries, runs structuring (dedup, sort, truncate to budget)
  - `priority_probe()`: reads HO3m for north stars (returns empty initially). Uses POLICY_LOOKUP pattern or returns empty if HO3m has no content.
  - `assemble_wo_context()`: merges horizontal + priority fragments, truncates to budget, computes context_hash
- Template resolution: load templates from `attention_templates/` dir, match via `applies_to`
- Budget tracking during assembly: max_context_tokens, max_queries, timeout_ms from `HO2Config`

### Step 5: Implement quality_gate.py

Create `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/quality_gate.py`:
- `QualityGate` class with `verify()` method
- MVP checks: output not None, not empty, contains expected keys, no error markers
- Returns `QualityGateResult(decision="accept"|"reject", reason="...", wo_id="...")`
- Configurable criteria (could be extended later)

### Step 6: Implement ho2_supervisor.py

Create `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py`:
- `HO2Supervisor` class
- `__init__()`: store plane_root, agent_class, ho1_executor, ledger_client, token_budgeter, config. Create SessionManager, AttentionRetriever, QualityGate.
- `start_session()`: delegate to SessionManager
- `end_session()`: delegate to SessionManager
- `handle_turn(user_message)`: the core Kitchener loop:
  1. Ensure session started
  2. Create classify WO -> dispatch to HO1 -> get classification
  3. Run attention (horizontal_scan + priority_probe)
  4. Assemble context for synthesize WO
  5. Create synthesize WO -> dispatch to HO1 -> get response
  6. Quality gate: verify output
  7. If reject: retry (create new WO) up to max_retries, then escalate
  8. Log WO chain events to HO2m
  9. Compute trace_hash from HO1m entries
  10. Log WO_CHAIN_COMPLETE + WO_QUALITY_GATE
  11. Track turn in SessionManager
  12. Return TurnResult
- `_dispatch_wo(work_order)`: try HO1, catch exceptions, degrade if needed
- `_create_wo(wo_type, input_context, constraints)`: use WorkOrder.create() + budget allocation
- `_log_wo_event(event_type, wo, **kwargs)`: write to HO2m ledger
- `_compute_trace_hash(wo_ids)`: read HO1m entries, compute SHA256

### Step 7: Create ATT-ADMIN-001.json attention template

Create `_staging/PKG-HO2-SUPERVISOR-001/HO2/attention_templates/ATT-ADMIN-001.json`:
- Must validate against `attention_template.schema.json`
- `applies_to: {"agent_class": ["ADMIN"], "tier": ["ho2"]}`
- Pipeline: `tier_select` (all tiers) -> `registry_scan` (frameworks registry) -> `structuring`
- Budget: `max_context_tokens: 10000, max_queries: 20, timeout_ms: 5000`
- Fallback: `on_timeout: "return_partial", on_empty: "proceed_empty"`

### Step 8: Create manifest.json

```json
{
  "package_id": "PKG-HO2-SUPERVISOR-001",
  "version": "1.0.0",
  "schema_version": "1.2",
  "title": "HO2 Supervisor - Kitchener Cognitive Dispatch",
  "description": "Deliberative supervisor: plans WO chains, dispatches to HO1, verifies results, manages sessions, assembles attention context",
  "spec_id": "SPEC-GATE-001",
  "framework_id": "FMWK-000",
  "plane_id": "ho2",
  "layer": 3,
  "dependencies": [
    "PKG-WORK-ORDER-001",
    "PKG-KERNEL-001",
    "PKG-TOKEN-BUDGETER-001",
    "PKG-PHASE2-SCHEMAS-001"
  ],
  "assets": [
    {
      "path": "HO2/kernel/ho2_supervisor.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "module"
    },
    {
      "path": "HO2/kernel/attention.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "module"
    },
    {
      "path": "HO2/kernel/quality_gate.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "module"
    },
    {
      "path": "HO2/kernel/session_manager.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "module"
    },
    {
      "path": "HO2/attention_templates/ATT-ADMIN-001.json",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "config"
    },
    {
      "path": "HO2/tests/test_ho2_supervisor.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "test"
    }
  ]
}
```

**Note:** `PKG-HO1-EXECUTOR-001` is NOT listed as a manifest dependency. HO1 is a runtime dependency (HO2 calls it), but the manifest dependency chain does not include it because HO2 mocks HO1 in its tests and uses a protocol for type safety. The spec interface is the dependency, not the installed package.

### Step 9: Build package archive

```bash
cd _staging
# Remove any __pycache__ or .pyc from PKG-HO2-SUPERVISOR-001
find PKG-HO2-SUPERVISOR-001 -name '__pycache__' -exec rm -rf {} +
find PKG-HO2-SUPERVISOR-001 -name '*.pyc' -delete
# Build archive using Python tarfile with explicit arcname
python3 -c "
import tarfile
from pathlib import Path
pkg = Path('PKG-HO2-SUPERVISOR-001')
with tarfile.open('PKG-HO2-SUPERVISOR-001.tar.gz', 'w:gz') as tf:
    for f in sorted(pkg.rglob('*')):
        if f.is_file() and '__pycache__' not in str(f):
            tf.add(str(f), arcname=str(f.relative_to(pkg)))
"
```

### Step 10: End-to-end verification

See Section 8 for exact commands.

### Step 11: Write results file

Write `_staging/RESULTS_HANDOFF_15.md` following the standard format.

---

## 5. Package Plan

### New Package

| Field | Value |
|-------|-------|
| Package ID | `PKG-HO2-SUPERVISOR-001` |
| Layer | 3 |
| spec_id | `SPEC-GATE-001` |
| framework_id | `FMWK-000` |
| plane_id | `ho2` |
| Dependencies | `PKG-WORK-ORDER-001`, `PKG-KERNEL-001`, `PKG-TOKEN-BUDGETER-001`, `PKG-PHASE2-SCHEMAS-001` |

### Assets

| Path | Classification | Description |
|------|----------------|-------------|
| `HO2/kernel/ho2_supervisor.py` | module | HO2Supervisor main class |
| `HO2/kernel/attention.py` | module | AttentionRetriever + ContextProvider |
| `HO2/kernel/quality_gate.py` | module | QualityGate verification |
| `HO2/kernel/session_manager.py` | module | Session lifecycle management |
| `HO2/attention_templates/ATT-ADMIN-001.json` | config | ADMIN attention template |
| `HO2/tests/test_ho2_supervisor.py` | test | 40+ unit tests |

---

## 6. Test Plan

**File:** `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py`

All tests use `tmp_path` fixtures. HO1Executor is mocked to return preset WorkOrder results. No real LLM calls.

### Mock Setup

```python
class MockHO1Executor:
    """Returns preset results for each WO type."""
    def __init__(self, responses: dict[str, dict] | None = None): ...
    def execute(self, work_order: WorkOrder) -> WorkOrder: ...

class MockLedgerClient:
    """Captures all write() calls for assertion."""
    def __init__(self): ...
    def write(self, entry: LedgerEntry) -> None: ...

class MockTokenBudgeter:
    """Tracks allocations and checks."""
    def __init__(self, session_budget: int = 100000): ...
    def allocate(self, scope, allocation) -> str: ...
    def check(self, scope) -> dict: ...
    def debit(self, scope, usage) -> dict: ...
```

### handle_turn Tests

| # | Test | Validates |
|---|------|-----------|
| 1 | `test_handle_turn_hello_end_to_end` | Full classify->synthesize pipeline for "hello". Returns TurnResult with response text. |
| 2 | `test_handle_turn_creates_classify_wo` | First WO in chain has wo_type="classify" and user_message in input_context. |
| 3 | `test_handle_turn_creates_synthesize_wo` | Second WO has wo_type="synthesize" with classification in prior_results. |
| 4 | `test_handle_turn_returns_turn_result` | Return type is TurnResult with all required fields populated. |
| 5 | `test_handle_turn_multi_wo_chain` | Chain with 3+ WOs (classify -> tool_call -> synthesize). |
| 6 | `test_handle_turn_auto_starts_session` | If session not started, handle_turn starts it automatically. |
| 7 | `test_handle_turn_wo_chain_summary` | TurnResult.wo_chain_summary contains all WOs with correct types and states. |
| 8 | `test_handle_turn_cost_summary` | TurnResult.cost_summary aggregates token costs from all WOs. |

### Attention Tests

| # | Test | Validates |
|---|------|-----------|
| 9 | `test_horizontal_scan_returns_recent_entries` | Reads HO2m entries for current session. Returns non-empty fragments. |
| 10 | `test_horizontal_scan_empty_ho2m` | Returns empty AttentionContext when HO2m has no entries. |
| 11 | `test_priority_probe_returns_empty` | Returns empty when HO3m has no content (initial state). |
| 12 | `test_attention_budget_truncation` | Fragments truncated when total tokens exceed attention_budget_tokens. |
| 13 | `test_attention_context_hash_computed` | context_hash is SHA256 of context_text. |
| 14 | `test_template_resolution_admin` | ATT-ADMIN-001 template matched for agent_class="ADMIN". |
| 15 | `test_template_resolution_no_match` | Returns default template when no match found. |
| 16 | `test_assemble_wo_context_merges` | horizontal + priority fragments merged into assembled_context dict. |

### Quality Gate Tests

| # | Test | Validates |
|---|------|-----------|
| 17 | `test_quality_gate_accept_valid_output` | Valid output_result with response_text passes. Decision="accept". |
| 18 | `test_quality_gate_reject_none_output` | None output_result rejected. Decision="reject". |
| 19 | `test_quality_gate_reject_empty_output` | Empty dict output_result rejected. |
| 20 | `test_quality_gate_reject_no_response_text` | Output without response_text key rejected. |
| 21 | `test_quality_gate_retry_flow` | On reject, handle_turn creates retry WO. Tests that retry WO is dispatched. |
| 22 | `test_quality_gate_escalation_after_max_retries` | After max_retries, escalation event logged instead of another retry. |
| 23 | `test_quality_gate_event_logged` | WO_QUALITY_GATE event written to HO2m with decision and trace_hash. |

### Session Management Tests

| # | Test | Validates |
|---|------|-----------|
| 24 | `test_start_session_generates_id` | Returns string matching `SES-{8 hex}` pattern. |
| 25 | `test_start_session_idempotent` | Calling start_session twice returns same session_id. |
| 26 | `test_start_session_writes_ledger` | SESSION_START event written to HO2m. |
| 27 | `test_end_session_writes_ledger` | SESSION_END event written to HO2m with turn count and cost. |
| 28 | `test_session_history_tracking` | add_turn populates history list. |
| 29 | `test_next_wo_id_format` | Returns WO-SES-XXXXXXXX-001, WO-SES-XXXXXXXX-002, etc. |
| 30 | `test_next_wo_id_monotonic` | Sequence numbers increase monotonically. |

### Factory Pattern Tests

| # | Test | Validates |
|---|------|-----------|
| 31 | `test_factory_admin_config` | HO2Supervisor instantiated with ADMIN config: ATT-ADMIN-001 template, admin ho2m path. |
| 32 | `test_factory_resident_config` | HO2Supervisor instantiated with RESIDENT config: different template, different ho2m path. |
| 33 | `test_factory_isolated_ho2m` | Two stacks write to different HO2m paths. Entries do not cross. |

### WO Chain Orchestration Tests

| # | Test | Validates |
|---|------|-----------|
| 34 | `test_classify_synthesize_pipeline` | classify -> synthesize chain completes. Both WOs reach "completed". |
| 35 | `test_classify_tool_call_synthesize_pipeline` | classify -> tool_call -> synthesize chain. Three WOs in chain. |
| 36 | `test_wo_budget_allocated_per_wo` | Each WO gets budget allocated via TokenBudgeter.allocate(). |
| 37 | `test_wo_budget_checked_before_dispatch` | TokenBudgeter.check() called before each dispatch. |
| 38 | `test_wo_budget_insufficient_returns_degraded` | When session budget insufficient, returns degraded TurnResult. |

### Degradation Tests

| # | Test | Validates |
|---|------|-----------|
| 39 | `test_ho1_exception_triggers_degradation` | HO1 raises -> HO2 catches -> DEGRADATION event logged -> returns error TurnResult. |
| 40 | `test_degradation_event_logged_to_ho2m` | DEGRADATION event written with governance_violation=True. |

### Ledger Recording Tests

| # | Test | Validates |
|---|------|-----------|
| 41 | `test_wo_planned_event_logged` | WO_PLANNED event written to HO2m for each WO created. |
| 42 | `test_wo_dispatched_event_logged` | WO_DISPATCHED event written with wo_id and tier_target. |
| 43 | `test_wo_chain_complete_event_logged` | WO_CHAIN_COMPLETE written with wo_count and total_cost. |
| 44 | `test_wo_quality_gate_event_logged` | WO_QUALITY_GATE written with decision (pass/reject). |

### Trace Hash Tests

| # | Test | Validates |
|---|------|-----------|
| 45 | `test_trace_hash_computed_from_ho1m` | trace_hash is SHA256 of concatenated HO1m entries for the chain. |
| 46 | `test_trace_hash_on_chain_complete` | WO_CHAIN_COMPLETE event includes trace_hash field. |
| 47 | `test_trace_hash_on_quality_gate` | WO_QUALITY_GATE event includes trace_hash field. |

**47 tests total.** Covers: end-to-end handle_turn, attention retrieval, quality gating, session lifecycle, factory pattern, WO chain orchestration, degradation, ledger recording, trace hash computation.

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| AttentionService | `_staging/PKG-ATTENTION-001/HOT/kernel/attention_service.py` | Pipeline logic, BudgetTracker, template resolution -- ABSORBED |
| ContextProvider | `_staging/PKG-ATTENTION-001/HOT/kernel/attention_stages.py` | I/O adapter, ContextFragment, stage runners -- ABSORBED |
| SessionHost | `_staging/PKG-SESSION-HOST-001/HOT/kernel/session_host.py` | Session lifecycle, TurnResult, history tracking -- ABSORBED |
| ATT-ADMIN-001.json (v1) | `_staging/PKG-ADMIN-001/HOT/attention_templates/ATT-ADMIN-001.json` | Starting point for new ADMIN attention template |
| attention_template.schema.json | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/attention_template.schema.json` | Template validation schema |
| LedgerClient | `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` | `write(LedgerEntry(...))` pattern for HO2m writes |
| TokenBudgeter | `_staging/PKG-TOKEN-BUDGETER-001/HOT/kernel/token_budgeter.py` | Budget allocate/check/debit API |
| FMWK-008 | `_staging/FMWK-008_Work_Order_Protocol/work_order_protocol.md` | WO schema, lifecycle, ledger events, trace_hash |
| FMWK-009 | `_staging/FMWK-009_Tier_Boundary/tier_boundary.md` | HO2 visibility: HO2m+HO1m. Syscall model. |
| FMWK-010 | `_staging/FMWK-010_Cognitive_Stack/cognitive_stack.md` | Factory pattern, shared/isolated boundary |
| BUILD_ROADMAP | `_staging/BUILD_ROADMAP.md` | HANDOFF-15 section, dependency graph |

---

## 8. End-to-End Verification

```bash
# 1. Run package tests
cd Control_Plane_v2/_staging
CONTROL_PLANE_ROOT="/tmp/test_ho2" python3 -m pytest PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py -v
# Expected: 47 tests pass, 0 fail

# 2. Verify package archive contents
python3 -c "
import tarfile
with tarfile.open('PKG-HO2-SUPERVISOR-001.tar.gz', 'r:gz') as tf:
    for m in tf.getmembers():
        print(m.name)
"
# Expected:
#   manifest.json
#   HO2/kernel/ho2_supervisor.py
#   HO2/kernel/attention.py
#   HO2/kernel/quality_gate.py
#   HO2/kernel/session_manager.py
#   HO2/attention_templates/ATT-ADMIN-001.json
#   HO2/tests/test_ho2_supervisor.py

# 3. Verify manifest.json
python3 -c "
import json
m = json.loads(open('PKG-HO2-SUPERVISOR-001/manifest.json').read())
assert m['plane_id'] == 'ho2', f'Expected ho2, got {m[\"plane_id\"]}'
assert m['layer'] == 3
assert 'PKG-WORK-ORDER-001' in m['dependencies']
assert 'PKG-KERNEL-001' in m['dependencies']
print('manifest.json: OK')
"

# 4. Verify attention template validates against schema
python3 -c "
import json
from jsonschema import validate
schema = json.loads(open('PKG-PHASE2-SCHEMAS-001/HOT/schemas/attention_template.schema.json').read())
template = json.loads(open('PKG-HO2-SUPERVISOR-001/HO2/attention_templates/ATT-ADMIN-001.json').read())
validate(instance=template, schema=schema)
print('ATT-ADMIN-001.json validates against schema: OK')
"

# 5. Full regression test
CONTROL_PLANE_ROOT="/tmp/test" python3 -m pytest . -v \
    --ignore=PKG-FLOW-RUNNER-001
# Expected: all pass, no new failures

# 6. Verify no HO2 code imports prompt_router or llm_gateway
grep -r "import prompt_router\|import llm_gateway\|from prompt_router\|from llm_gateway" \
    PKG-HO2-SUPERVISOR-001/HO2/kernel/ && echo "FAIL: HO2 imports LLM Gateway!" || echo "OK: No LLM Gateway imports in HO2"

# 7. Verify no HO2 code imports from archived packages
grep -r "from attention_service\|from session_host\|import attention_service\|import session_host" \
    PKG-HO2-SUPERVISOR-001/HO2/kernel/ && echo "FAIL: HO2 imports archived package!" || echo "OK: No archived package imports"
```

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | CREATE |
| `attention.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | CREATE |
| `quality_gate.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | CREATE |
| `session_manager.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | CREATE |
| `ATT-ADMIN-001.json` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/attention_templates/` | CREATE |
| `test_ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/` | CREATE |
| `manifest.json` | `_staging/PKG-HO2-SUPERVISOR-001/` | CREATE |
| `PKG-HO2-SUPERVISOR-001.tar.gz` | `_staging/` | CREATE |
| `RESULTS_HANDOFF_15.md` | `_staging/` | CREATE |

**Not modified:** No existing package source files are modified. This package only creates new files in a new package directory.

---

## 10. Design Principles

1. **HO2 never calls LLM Gateway directly.** All cognitive work is dispatched as WorkOrders to HO1. This is Invariant #1. If HO2 needs to think (classify, verify, plan), it creates an internal WO and dispatches it. The degradation path (direct LLM call) exists only for total HO1 failure and is logged as a governance violation.

2. **Factory pattern: one codebase, many stacks.** HO2Supervisor is written once. Agent classes differ only in config: attention templates, ho2m paths, budget ceilings, framework configs. Code is shared; state is isolated. This is FMWK-010 Invariant #7.

3. **Attention is budget-aware and fail-open.** If attention assembly exceeds its budget, return partial context. If attention finds nothing (empty HO3m, empty HO2m), proceed with empty context. Never block the response because context is incomplete. Absence of context is safer than blocking.

4. **Quality gate is binary for MVP.** Accept or reject. No partial scoring, no confidence thresholds, no multi-criteria weighted evaluation. Rejection triggers retry (new WO with tighter constraints) up to max_retries, then escalation. Sophisticated quality evaluation is deferred.

5. **Every orchestration decision is logged.** WO_PLANNED, WO_DISPATCHED, WO_CHAIN_COMPLETE, WO_QUALITY_GATE -- all written to HO2m. The trace_hash links HO2m governance summaries to HO1m detailed traces. Full audit trail.

6. **Degradation is governed, not hidden.** When the Kitchener loop fails, the system degrades to direct LLM call. This is not silent -- it is logged as a DEGRADATION event with governance_violation=True. The system stays available but the violation is permanently recorded.

7. **Absorb, do not import.** PKG-ATTENTION-001 and PKG-SESSION-HOST-001 are ARCHIVED. Their code is absorbed (copied and adapted) into HO2, not imported. No runtime dependency on archived packages.
