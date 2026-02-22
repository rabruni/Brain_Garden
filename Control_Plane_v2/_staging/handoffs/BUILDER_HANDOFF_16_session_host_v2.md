# BUILDER_HANDOFF_16: Session Host V2 — Thin Adapter + Degradation

## 1. Mission

Create `PKG-SESSION-HOST-V2-001` — a thin adapter (~100 lines of logic) that replaces the flat Session Host v1 loop with pure delegation to HO2 Supervisor. V2 does exactly three things: start session, process turn (delegate to HO2), and catch exceptions (degrade to direct LLM call through Gateway). Everything else — attention, routing, WO orchestration, session state — lives in HO2 Supervisor.

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** New code ships as packages in `_staging/PKG-SESSION-HOST-V2-001/` with manifest.json, SHA256 hashes, proper dependencies. Follow existing package patterns.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → install all layers → install YOUR new package. All gates must pass.
5. **No hardcoding.** Every threshold, timeout, retry count, rate limit — all config-driven. No magic constants.
6. **No file replacement.** Packages must NEVER overwrite another package's files. Use state-gating instead.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`).
8. **Results file.** When finished, write `_staging/RESULTS_HANDOFF_16.md` (see `BUILDER_HANDOFF_STANDARD.md`).
9. **Full regression test.** Run ALL staged package tests (not just yours) and report results.
10. **Baseline snapshot.** Your results file must include a baseline snapshot.

**Task-specific constraints:**

11. **V2 is THIN.** Under 100 lines of logic. If you find yourself writing attention retrieval, routing logic, WO creation, or tool dispatch — STOP. That belongs in HO2 Supervisor (PKG-HO2-SUPERVISOR-001). V2 delegates everything.
12. **Redefine dataclasses locally.** `TurnResult` and `AgentConfig` are redefined in `session_host_v2.py`. Do NOT import them from the archived PKG-SESSION-HOST-001. Copy the definitions for interface compatibility.
13. **LedgerClient method is `write()`.** Never `append()`. Check the existing `LedgerClient` API.
14. **Degradation is a try/except.** The entire process_turn delegation is wrapped in try/except. On any exception from HO2, construct a minimal `PromptRequest` and call `gateway.route()` directly. Log the degradation event to the ledger.

---

## 3. Architecture / Design

### What V2 Does vs. Delegates

| V2 Owns | V2 Delegates to HO2 |
|---------|---------------------|
| Thin turn wrapping | Session lifecycle (session ID, start/end events) |
| Degradation fallback (try/except → Gateway) | Attention retrieval |
| TurnResult/AgentConfig dataclass redefinition | WO creation and orchestration |
| | Routing decisions |
| | Tool dispatch |
| | Quality gating |
| | History tracking |

### Call Flow — Normal Path

```
Shell → SessionHostV2.process_turn(user_message)
         │
         └─ try:
              ho2_supervisor.handle_turn(user_message) → result
              return TurnResult(response=result.response, outcome="success", ...)
```

### Call Flow — Degradation Path

```
Shell → SessionHostV2.process_turn(user_message)
         │
         └─ try:
              ho2_supervisor.handle_turn(user_message) → RAISES EXCEPTION
            except Exception as exc:
              log degradation event to ledger  📝
              request = PromptRequest(prompt=user_message, ...)
              response = gateway.route(request)
              return TurnResult(response=response.content, outcome="degraded", ...)
```

### Call Flow — Double Failure

```
Shell → SessionHostV2.process_turn(user_message)
         │
         └─ try: ho2 → RAISES
            except:
              try: gateway.route() → ALSO RAISES
              except:
                return TurnResult(response="Service unavailable...", outcome="error")
```

### Adversarial Analysis: Scope

**Hurdles**: Degradation requires constructing a `PromptRequest`, which means V2 must know enough about the prompt format to build a minimal one. Also requires importing `LedgerClient` for degradation logging — the "thin adapter" has real dependencies.

**Too Much**: If V2 grows session management, attention, tool dispatch, or routing — it recreates V1. The Session Host v1 was 300+ lines because it owned too much. V2 must resist scope creep.

**Synthesis**: V2 is under 100 lines of logic. Degradation is a simple try/except that constructs a minimal `PromptRequest` with just the user message and basic metadata. No attention, no tool loop, no WO chain — just a raw LLM call as a last resort.

---

## 4. Implementation Steps

### Step 1: Write tests (DTT)

Create `_staging/PKG-SESSION-HOST-V2-001/HOT/tests/test_session_host_v2.py` with all tests from the Test Plan (Section 6). Tests mock `HO2Supervisor` and `LLMGateway` (or `PromptRouter`). No real LLM calls.

### Step 2: Implement session_host_v2.py

Create `_staging/PKG-SESSION-HOST-V2-001/HOT/kernel/session_host_v2.py`:

```python
"""Session Host V2: thin adapter delegating to HO2 Supervisor.

Replaces v1 flat loop. V2 does exactly three things:
1. start_session() → delegates to HO2
2. process_turn() → delegates to HO2
3. Catches exceptions → degrades to direct LLM call through Gateway

Under 100 lines of logic. Everything else lives in HO2 Supervisor.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)
```

#### Dataclasses (redefined locally):

```python
@dataclass
class TurnResult:
    response: str
    outcome: str  # "success", "degraded", "error"
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    exchange_entry_ids: list[str] = field(default_factory=list)


@dataclass
class AgentConfig:
    agent_id: str
    agent_class: str
    framework_id: str
    tier: str
    system_prompt: str
    attention: dict[str, Any]
    tools: list[dict[str, Any]]
    budget: dict[str, Any]
    permissions: dict[str, Any]
```

#### Class:

```python
class SessionHostV2:
    """Thin adapter: delegates to HO2, degrades to Gateway on failure."""

    def __init__(self, ho2_supervisor, gateway, agent_config: AgentConfig,
                 ledger_client=None):
        self._ho2 = ho2_supervisor
        self._gateway = gateway
        self._config = agent_config
        self._ledger = ledger_client
        self._session_id = ""

    def start_session(self, agent_config: AgentConfig | None = None) -> str:
        config = agent_config or self._config
        self._session_id = self._ho2.start_session()
        return self._session_id

    def process_turn(self, user_message: str) -> TurnResult:
        if not self._session_id:
            self.start_session()

        try:
            result = self._ho2.handle_turn(user_message)
            return TurnResult(
                response=getattr(result, "response", str(result)),
                outcome="success",
                tool_calls=getattr(result, "tool_calls", []),
                exchange_entry_ids=getattr(result, "exchange_entry_ids", []),
            )
        except Exception as ho2_exc:
            return self._degrade(user_message, ho2_exc)

    def _degrade(self, user_message: str, ho2_exc: Exception) -> TurnResult:
        logger.warning("HO2 failed (%s), degrading to direct LLM call", ho2_exc)
        self._log_degradation(ho2_exc)

        try:
            from prompt_router import PromptRequest
            request = PromptRequest(
                prompt=user_message,
                prompt_pack_id="PRM-DEGRADED-001",
                contract_id="PRC-DEGRADED-001",
                agent_id=self._config.agent_id,
                agent_class=self._config.agent_class,
                framework_id=self._config.framework_id,
                package_id="PKG-SESSION-HOST-V2-001",
                work_order_id=f"WO-DEGRADED-{uuid.uuid4().hex[:8]}",
                session_id=self._session_id,
                tier=self._config.tier,
                max_tokens=4096,
                temperature=0.0,
            )
            response = self._gateway.route(request)
            return TurnResult(
                response=getattr(response, "content", str(response)),
                outcome="degraded",
            )
        except Exception as gw_exc:
            logger.error("Gateway also failed (%s), returning error", gw_exc)
            return TurnResult(
                response="Service temporarily unavailable. Both HO2 supervisor "
                         "and LLM gateway failed. Please try again.",
                outcome="error",
            )

    def _log_degradation(self, exc: Exception) -> None:
        if self._ledger is None:
            return
        try:
            from ledger_client import LedgerEntry
            self._ledger.write(
                LedgerEntry(
                    event_type="DEGRADATION",
                    submission_id="PKG-SESSION-HOST-V2-001",
                    decision="DEGRADED",
                    reason=f"HO2 failed: {exc}",
                    metadata={
                        "session_id": self._session_id,
                        "agent_id": self._config.agent_id,
                        "error_type": type(exc).__name__,
                    },
                )
            )
        except Exception:
            logger.warning("Failed to log degradation event to ledger")

    def end_session(self) -> None:
        if self._session_id:
            try:
                self._ho2.end_session()
            except Exception as exc:
                logger.warning("HO2 end_session failed (%s)", exc)
            self._session_id = ""
```

### Step 3: Create manifest.json

Create `_staging/PKG-SESSION-HOST-V2-001/manifest.json` (see Section 5).

### Step 4: Build package archive

```python
import tarfile
from pathlib import Path

def build_pkg(pkg_dir, output_path):
    with tarfile.open(output_path, "w:gz") as tf:
        for f in sorted(Path(pkg_dir).rglob("*")):
            if f.is_file() and "__pycache__" not in str(f):
                tf.add(str(f), arcname=str(f.relative_to(pkg_dir)))
```

### Step 5: Clean-room verification

See Section 8 for exact commands.

### Step 6: Write results file

Write `_staging/RESULTS_HANDOFF_16.md` following the standard format.

---

## 5. Package Plan

### New Package

| Field | Value |
|-------|-------|
| Package ID | `PKG-SESSION-HOST-V2-001` |
| Layer | 3 |
| spec_id | `SPEC-GATE-001` |
| framework_id | `FMWK-000` |
| plane_id | `hot` |
| Dependencies | `PKG-HO2-SUPERVISOR-001`, `PKG-HO1-EXECUTOR-001`, `PKG-PROMPT-ROUTER-001`, `PKG-KERNEL-001` |
| Assets | `HOT/kernel/session_host_v2.py` (kernel), `HOT/tests/test_session_host_v2.py` (test) |

### manifest.json

```json
{
  "package_id": "PKG-SESSION-HOST-V2-001",
  "version": "1.0.0",
  "schema_version": "1.2",
  "title": "Session Host V2 — Thin Adapter",
  "description": "Thin adapter delegating session turns to HO2 Supervisor with degradation fallback to direct LLM Gateway call",
  "spec_id": "SPEC-GATE-001",
  "framework_id": "FMWK-000",
  "plane_id": "hot",
  "layer": 3,
  "dependencies": [
    "PKG-HO2-SUPERVISOR-001",
    "PKG-HO1-EXECUTOR-001",
    "PKG-PROMPT-ROUTER-001",
    "PKG-KERNEL-001"
  ],
  "assets": [
    {
      "path": "HOT/kernel/session_host_v2.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "kernel"
    },
    {
      "path": "HOT/tests/test_session_host_v2.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "test"
    }
  ]
}
```

---

## 6. Test Plan

**File:** `_staging/PKG-SESSION-HOST-V2-001/HOT/tests/test_session_host_v2.py`

All tests mock `HO2Supervisor` and `LLMGateway`/`PromptRouter`. No real LLM calls. Use `unittest.mock.MagicMock` or `Mock`.

### Setup

```python
@pytest.fixture
def mock_ho2():
    ho2 = MagicMock()
    ho2.start_session.return_value = "SES-abc12345"
    ho2.handle_turn.return_value = MagicMock(
        response="Hello from HO2",
        tool_calls=[],
        exchange_entry_ids=["EX-001"],
    )
    return ho2

@pytest.fixture
def mock_gateway():
    gw = MagicMock()
    gw.route.return_value = MagicMock(content="Degraded response")
    return gw

@pytest.fixture
def agent_config():
    return AgentConfig(
        agent_id="ADMIN",
        agent_class="ADMIN",
        framework_id="FMWK-107",
        tier="HOT",
        system_prompt="You are an admin.",
        attention={},
        tools=[],
        budget={},
        permissions={},
    )

@pytest.fixture
def mock_ledger():
    return MagicMock()
```

### Tests

| # | Test | Validates |
|---|------|-----------|
| 1 | `test_process_turn_delegates_to_ho2` | `ho2.handle_turn` called with `user_message` |
| 2 | `test_process_turn_returns_turn_result` | Return type is `TurnResult` with `outcome="success"` |
| 3 | `test_start_session_delegates` | `ho2.start_session` called, returns session_id string |
| 4 | `test_end_session_delegates` | `ho2.end_session` called |
| 5 | `test_degradation_on_ho2_exception` | HO2 raises `RuntimeError` → `gateway.route` called |
| 6 | `test_degradation_returns_turn_result` | Degraded response is a `TurnResult` with `outcome="degraded"` |
| 7 | `test_degradation_logs_event` | Degradation event written to ledger via `ledger.write()` |
| 8 | `test_gateway_also_fails` | Both HO2 and Gateway raise → `TurnResult` with `outcome="error"` |
| 9 | `test_agent_config_passed_through` | Config is accessible on the host instance |
| 10 | `test_turn_result_dataclass` | `TurnResult` has fields: `response`, `outcome`, `tool_calls`, `exchange_entry_ids` |
| 11 | `test_auto_start_session_on_first_turn` | If `process_turn` called before `start_session`, session is auto-started |
| 12 | `test_end_session_clears_session_id` | After `end_session`, `_session_id` is empty |
| 13 | `test_degradation_log_failure_non_fatal` | If ledger write fails during degradation logging, it does not propagate |

**13 tests total.** Covers: normal delegation (3 methods), degradation path, double failure, ledger logging, dataclass integrity, edge cases.

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Session Host V1 | `_staging/PKG-SESSION-HOST-001/HOT/kernel/session_host.py` | Pattern reference. V2 replaces this. Copy `TurnResult` and `AgentConfig` dataclass shapes. |
| PromptRouter / LLM Gateway | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/prompt_router.py` | `PromptRequest` dataclass for degradation fallback. `route()` method signature. |
| LedgerClient | `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` | `LedgerEntry` dataclass for degradation logging. Method is `write()`, never `append()`. |
| HO2 Supervisor (future) | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py` | `handle_turn()`, `start_session()`, `end_session()` signatures. Mock in tests until this package exists. |
| Builder standard | `_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` | Results file format, baseline snapshot format. |

---

## 8. End-to-End Verification

```bash
# 1. Run package tests
cd Control_Plane_v2/_staging
CONTROL_PLANE_ROOT="/tmp/test" python3 -m pytest PKG-SESSION-HOST-V2-001/HOT/tests/test_session_host_v2.py -v
# Expected: 13 tests pass

# 2. Verify package archive contents
tar tzf _staging/PKG-SESSION-HOST-V2-001.tar.gz
# Expected:
#   manifest.json
#   HOT/kernel/session_host_v2.py
#   HOT/tests/test_session_host_v2.py

# 3. Verify manifest hashes
python3 -c "
import json, hashlib
from pathlib import Path
m = json.loads(Path('_staging/PKG-SESSION-HOST-V2-001/manifest.json').read_text())
for asset in m['assets']:
    actual = hashlib.sha256(Path('_staging/PKG-SESSION-HOST-V2-001', asset['path']).read_bytes()).hexdigest()
    declared = asset['sha256']
    status = 'MATCH' if actual == declared else 'MISMATCH'
    print(f\"{asset['path']}: {status}\")
"
# Expected: all MATCH

# 4. Gate check (after install)
python3 "$INSTALLDIR/HOT/scripts/gate_check.py" --root "$INSTALLDIR" --all
# Expected: all gates PASS

# 5. Full regression
cd Control_Plane_v2/_staging
python3 -m pytest . -v --ignore=PKG-FLOW-RUNNER-001
# Expected: all pass, no new failures
```

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `session_host_v2.py` | `_staging/PKG-SESSION-HOST-V2-001/HOT/kernel/` | CREATE |
| `test_session_host_v2.py` | `_staging/PKG-SESSION-HOST-V2-001/HOT/tests/` | CREATE |
| `manifest.json` | `_staging/PKG-SESSION-HOST-V2-001/` | CREATE |
| `RESULTS_HANDOFF_16.md` | `_staging/` | CREATE |

**Not modified:** No existing packages are modified by this handoff.

---

## 10. Design Principles

1. **V2 is THIN.** Under 100 lines of logic. If it does attention, routing, WO creation, or tool dispatch — it has failed its purpose. V2 wraps and delegates. Period.
2. **Degradation is the safety net.** The try/except around `ho2.handle_turn()` ensures the system always responds, even if the entire Kitchener loop is broken. Direct LLM via Gateway is the fallback — worse quality, but always available.
3. **Dataclasses are local.** `TurnResult` and `AgentConfig` are redefined in V2, not imported from archived V1. This prevents dependency on a dead package while maintaining interface compatibility.
4. **Degradation is logged.** Every degradation event writes to the governance ledger via `LedgerClient.write()`. This creates an audit trail of system failures. If ledger write itself fails, V2 logs a warning but does not crash.
5. **V2 is the API boundary.** Shell (HANDOFF-17) calls `SessionHostV2.process_turn()`. Shell never knows about HO2 internals. If the Kitchener loop changes internally, Shell is unaffected.
6. **End session is best-effort.** If `ho2.end_session()` fails, V2 logs a warning and clears its session ID. The session is considered ended regardless.
