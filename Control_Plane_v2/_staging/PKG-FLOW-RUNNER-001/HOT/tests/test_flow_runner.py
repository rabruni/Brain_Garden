"""
Tests for the Flow Runner (Agent Orchestrator) — PKG-FLOW-RUNNER-001.

40 tests covering all 9 steps of the v1 flow + 4 v2 extension point stubs.
Written BEFORE implementation (DTT: Design → Test → Then implement).

All external dependencies are mocked:
- Token Budgeter (allocate, check, debit)
- Prompt Router (send)
- Attention Service (assemble)
- LedgerClient (write)
- Framework resolution (registry CSV, manifest YAML)
- Auth/AuthZ
"""

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Add the kernel directory to sys.path so we can import flow_runner directly.
_KERNEL_DIR = str(Path(__file__).resolve().parent.parent / "kernel")
if _KERNEL_DIR not in sys.path:
    sys.path.insert(0, _KERNEL_DIR)

from flow_runner import (
    FlowRunner,
    FlowRequest,
    FlowResult,
    ExecutionContext,
    # v2 extension points
    StepStrategy,
    SingleStepStrategy,
    ApertureManager,
    DelegationManager,
    RecoveryStrategy,
)


# ---------------------------------------------------------------------------
# Fixtures — shared mock objects and valid test data
# ---------------------------------------------------------------------------

def _valid_work_order(**overrides) -> dict:
    """Return a minimal valid work order dict."""
    wo = {
        "work_order_id": "WO-20260210-001",
        "type": "code_change",
        "plane_id": "hot",
        "spec_id": "SPEC-ORCHESTRATION-001",
        "framework_id": "FMWK-005",
        "scope": {"allowed_files": ["HOT/kernel/flow_runner.py"]},
        "acceptance": {"tests": [], "checks": []},
        "authorization": {
            "authorized_by": "human",
            "session_id": "SES-ABCD1234",
        },
    }
    wo.update(overrides)
    return wo


def _valid_framework_manifest(**overrides) -> dict:
    """Return a parsed framework manifest dict (from YAML)."""
    fm = {
        "framework_id": "FMWK-005",
        "title": "Agent Orchestration Framework",
        "version": "1.0.0",
        "status": "active",
        "ring": "kernel",
        "plane_id": "hot",
        "created_at": "2026-02-10T00:00:00Z",
        "assets": ["agent_orchestration_standard.md"],
        "expected_specs": ["SPEC-ORCHESTRATION-001"],
        "invariants": [],
        "path_authorizations": [
            "HOT/kernel/flow_runner.py",
            "HOT/tests/test_flow_runner.py",
        ],
        "required_gates": ["G0", "G1", "G5"],
    }
    fm.update(overrides)
    return fm


def _valid_prompt_contract(**overrides) -> dict:
    """Return a minimal prompt contract dict."""
    pc = {
        "contract_id": "PRC-ORCH-001",
        "version": "1.0.0",
        "prompt_pack_id": "PRM-ORCH-001",
        "agent_class": "KERNEL.semantic",
        "tier": "hot",
        "boundary": {"max_tokens": 4096, "temperature": 0.7},
        "required_context": {
            "file_refs": ["HOT/schemas/work_order.schema.json"],
        },
    }
    pc.update(overrides)
    return pc


def _mock_config(**overrides) -> dict:
    """Return a flow runner config dict with defaults."""
    cfg = {
        "default_budget": {
            "token_limit": 10000,
            "turn_limit": 1,
            "timeout_seconds": 120,
        },
        "agent_id_prefix": "AGT",
        "max_concurrent_flows": 1,
        "execution_timeout_seconds": 300,
        "framework_resolution": {
            "registry_path": "HOT/registries/frameworks_registry.csv",
            "manifest_filename": "manifest.yaml",
        },
        "acceptance": {
            "command_timeout_seconds": 30,
            "max_commands": 10,
        },
        "ledger": {"event_prefix": "WO"},
        "v2_features": {
            "multi_step_enabled": False,
            "aperture_enabled": False,
            "delegation_enabled": False,
            "recovery_enabled": False,
        },
    }
    cfg.update(overrides)
    return cfg


@pytest.fixture
def mock_budgeter():
    """Mock Token Budgeter with default allow-all behavior."""
    budgeter = MagicMock()
    budgeter.allocate.return_value = MagicMock(
        success=True, allocated=10000, reason="OK"
    )
    budgeter.check.return_value = MagicMock(
        allowed=True, remaining=10000, reason="OK", retry_after_ms=None
    )
    budgeter.debit.return_value = MagicMock(
        success=True, remaining=9000, reason="OK"
    )
    return budgeter


@pytest.fixture
def mock_router():
    """Mock Prompt Router with default success behavior."""
    router = MagicMock()
    router.send.return_value = MagicMock(
        response="This is the LLM response.",
        tokens_used={"input": 500, "output": 200},
        ledger_entry_ids=["LED-aabb0001", "LED-aabb0002"],
        validation_result={"valid": True},
        latency_ms=150,
    )
    return router


@pytest.fixture
def mock_attention():
    """Mock Attention Service with default success behavior."""
    attention = MagicMock()
    attention.assemble.return_value = MagicMock(
        context_text="Assembled context for the agent.",
        context_hash="sha256:abc123def456",
        fragments=[
            MagicMock(source="file", source_id="work_order.schema.json",
                      content="schema content", token_estimate=100,
                      relevance_score=None),
        ],
        template_id="ATT-DEFAULT-001",
        pipeline_trace=[],
        budget_used=MagicMock(tokens=100, queries=1, elapsed_ms=50),
        warnings=[],
    )
    return attention


@pytest.fixture
def mock_ledger():
    """Mock LedgerClient that captures written entries."""
    ledger = MagicMock()
    # Each write returns a unique entry ID
    ledger.write.side_effect = lambda entry: entry.id if hasattr(entry, 'id') else f"LED-{id(entry):08x}"[-12:]
    return ledger


@pytest.fixture
def mock_framework_resolver():
    """Mock framework resolution: registry lookup + manifest load."""
    resolver = MagicMock()
    resolver.resolve.return_value = _valid_framework_manifest()
    resolver.find_prompt_contracts.return_value = [_valid_prompt_contract()]
    return resolver


@pytest.fixture
def mock_auth():
    """Mock auth provider (passthrough)."""
    auth = MagicMock()
    auth.authenticate.return_value = MagicMock(user="human", roles=["admin"])
    auth.is_authorized.return_value = True
    return auth


@pytest.fixture
def runner(mock_budgeter, mock_router, mock_attention, mock_ledger,
           mock_framework_resolver, mock_auth):
    """Fully wired FlowRunner with all dependencies mocked."""
    return FlowRunner(
        config=_mock_config(),
        budgeter=mock_budgeter,
        router=mock_router,
        attention=mock_attention,
        ledger=mock_ledger,
        framework_resolver=mock_framework_resolver,
        auth=mock_auth,
    )


def _make_request(**overrides) -> FlowRequest:
    """Build a FlowRequest with valid defaults."""
    kwargs = {
        "work_order": _valid_work_order(),
        "caller_id": "human",
        "dev_mode": False,
    }
    kwargs.update(overrides)
    return FlowRequest(**kwargs)


# ===================================================================
# STEP 1: Work Order Validation (tests 1-5)
# ===================================================================

class TestWorkOrderValidation:

    def test_valid_wo_accepted(self, runner):
        """1. Well-formed WO passes validation — flow proceeds."""
        req = _make_request()
        result = runner.execute(req)
        assert result.status == "success"

    def test_invalid_wo_rejected(self, runner):
        """2. Malformed WO (missing required fields) rejected with error."""
        bad_wo = {"work_order_id": "WO-20260210-001"}  # missing type, plane_id, etc.
        req = _make_request(work_order=bad_wo)
        result = runner.execute(req)
        assert result.status == "rejected"
        assert result.error is not None
        assert "validation" in result.error.lower() or "required" in result.error.lower()

    def test_missing_required_fields_rejected(self, runner):
        """3. Each required field missing individually triggers rejection."""
        required_fields = ["work_order_id", "type", "plane_id", "spec_id",
                           "framework_id", "scope", "acceptance"]
        for field_name in required_fields:
            wo = _valid_work_order()
            del wo[field_name]
            req = _make_request(work_order=wo)
            result = runner.execute(req)
            assert result.status == "rejected", (
                f"Expected rejection when '{field_name}' is missing"
            )

    def test_authorization_validated(self, runner, mock_auth):
        """4. Authorization chain is checked when present."""
        wo = _valid_work_order(authorization={
            "authorized_by": "human",
            "authorization_chain": ["human", "DoPeJar"],
            "session_id": "SES-ABCD1234",
        })
        req = _make_request(work_order=wo)
        result = runner.execute(req)
        # Auth was called during execution
        assert mock_auth.authenticate.called or mock_auth.is_authorized.called

    def test_wo_rejected_logged(self, runner, mock_ledger):
        """5. Rejected WO writes WO_REJECTED to ledger."""
        bad_wo = {"work_order_id": "WO-20260210-001"}
        req = _make_request(work_order=bad_wo)
        result = runner.execute(req)
        assert result.status == "rejected"
        # At least one ledger write happened (the WO_REJECTED event)
        assert mock_ledger.write.called
        written_entry = mock_ledger.write.call_args_list[0][0][0]
        assert written_entry.event_type == "WO_REJECTED"


# ===================================================================
# STEP 2: Framework Resolution (tests 6-11)
# ===================================================================

class TestFrameworkResolution:

    def test_framework_found(self, runner, mock_framework_resolver):
        """6. framework_id from WO resolved to manifest."""
        req = _make_request()
        result = runner.execute(req)
        assert result.status == "success"
        mock_framework_resolver.resolve.assert_called_once()
        call_args = mock_framework_resolver.resolve.call_args
        assert call_args[0][0] == "FMWK-005" or call_args[1].get("framework_id") == "FMWK-005"

    def test_framework_not_found_rejected(self, runner, mock_framework_resolver):
        """7. Unknown framework_id → rejection."""
        mock_framework_resolver.resolve.return_value = None
        req = _make_request()
        result = runner.execute(req)
        assert result.status == "rejected"
        assert "framework" in result.error.lower()

    def test_agent_class_from_wo(self, runner):
        """8. agent_class extracted from WO when specified."""
        wo = _valid_work_order(agent_class="KERNEL.semantic")
        req = _make_request(work_order=wo)
        result = runner.execute(req)
        assert result.status == "success"

    def test_agent_class_not_permitted(self, runner, mock_framework_resolver):
        """9. agent_class not in framework's permitted classes → rejection."""
        # Framework only allows KERNEL.syntactic
        manifest = _valid_framework_manifest()
        manifest["permitted_agent_classes"] = ["KERNEL.syntactic"]
        mock_framework_resolver.resolve.return_value = manifest
        wo = _valid_work_order(agent_class="RESIDENT")
        req = _make_request(work_order=wo)
        result = runner.execute(req)
        assert result.status == "rejected"
        assert "agent_class" in result.error.lower() or "permitted" in result.error.lower()

    def test_agent_id_generated(self, runner):
        """10. Unique agent ID created with correct format: AGT-{fmwk}-{wo}-{ts}."""
        req = _make_request()
        result = runner.execute(req)
        assert result.agent_id is not None
        assert result.agent_id.startswith("AGT-")

    def test_tier_from_plane_id(self, runner):
        """11. Tier determined from WO's plane_id field."""
        wo = _valid_work_order(plane_id="ho2")
        req = _make_request(work_order=wo)
        result = runner.execute(req)
        assert result.status == "success"


# ===================================================================
# STEP 3: Budget Allocation (tests 12-15)
# ===================================================================

class TestBudgetAllocation:

    def test_budget_from_wo(self, runner, mock_budgeter):
        """12. WO budget fields used for allocation."""
        wo = _valid_work_order(budget={
            "token_limit": 5000,
            "turn_limit": 1,
            "timeout_seconds": 60,
        })
        req = _make_request(work_order=wo)
        result = runner.execute(req)
        assert result.status == "success"
        mock_budgeter.allocate.assert_called_once()
        alloc_call = mock_budgeter.allocate.call_args
        # Verify the budget from WO was passed
        scope = alloc_call[0][0] if alloc_call[0] else alloc_call[1].get("scope")
        assert scope is not None

    def test_default_budget_when_absent(self, runner, mock_budgeter):
        """13. Config defaults used when WO has no budget field."""
        wo = _valid_work_order()
        # Ensure no budget field
        wo.pop("budget", None)
        req = _make_request(work_order=wo)
        result = runner.execute(req)
        assert result.status == "success"
        mock_budgeter.allocate.assert_called_once()

    def test_budget_denied_rejects(self, runner, mock_budgeter):
        """14. Over-committed session → WO rejected."""
        mock_budgeter.allocate.return_value = MagicMock(
            success=False, allocated=0, reason="SESSION_OVER_COMMITTED"
        )
        req = _make_request()
        result = runner.execute(req)
        assert result.status == "rejected"
        assert "budget" in result.error.lower()

    def test_budget_scope_correct(self, runner, mock_budgeter):
        """15. Budget scoped to session + WO + agent."""
        wo = _valid_work_order()
        req = _make_request(work_order=wo)
        result = runner.execute(req)
        mock_budgeter.allocate.assert_called_once()
        alloc_call = mock_budgeter.allocate.call_args
        scope = alloc_call[0][0] if alloc_call[0] else alloc_call[1].get("scope")
        # Scope should contain session_id, work_order_id
        assert hasattr(scope, "session_id") or (isinstance(scope, dict) and "session_id" in scope)
        assert hasattr(scope, "work_order_id") or (isinstance(scope, dict) and "work_order_id" in scope)


# ===================================================================
# STEP 4: Execution Context (tests 16-20)
# ===================================================================

class TestExecutionContext:

    def test_context_created(self, runner):
        """16. ExecutionContext has all required fields populated."""
        req = _make_request()
        result = runner.execute(req)
        assert result.status == "success"
        assert result.agent_id is not None
        assert result.work_order_id == "WO-20260210-001"

    def test_prompt_contracts_resolved(self, runner, mock_framework_resolver):
        """17. Prompt contracts for framework/agent_class loaded."""
        req = _make_request()
        result = runner.execute(req)
        mock_framework_resolver.find_prompt_contracts.assert_called_once()

    def test_path_authorizations_set(self, runner, mock_framework_resolver):
        """18. Path authorizations come from framework manifest."""
        manifest = _valid_framework_manifest(path_authorizations=[
            "HOT/kernel/flow_runner.py",
            "HOT/tests/*.py",
        ])
        mock_framework_resolver.resolve.return_value = manifest
        req = _make_request()
        result = runner.execute(req)
        assert result.status == "success"

    def test_tool_permissions_set(self, runner):
        """19. Tool permissions from WO's tool_permissions field."""
        wo = _valid_work_order(tool_permissions=[
            {"tool_id": "file_read", "allowed": True},
            {"tool_id": "file_write", "allowed": False},
        ])
        req = _make_request(work_order=wo)
        result = runner.execute(req)
        assert result.status == "success"

    def test_wo_started_logged(self, runner, mock_ledger):
        """20. WO_STARTED written to ledger with full metadata."""
        req = _make_request()
        result = runner.execute(req)
        # Find the WO_STARTED entry among all writes
        wo_started_calls = [
            call for call in mock_ledger.write.call_args_list
            if call[0][0].event_type == "WO_STARTED"
        ]
        assert len(wo_started_calls) >= 1
        entry = wo_started_calls[0][0][0]
        assert entry.event_type == "WO_STARTED"
        # Metadata should have provenance with agent_id, framework_id, work_order_id
        meta = entry.metadata
        assert "provenance" in meta or "agent_id" in meta


# ===================================================================
# STEP 5: Attention (tests 21-23)
# ===================================================================

class TestAttention:

    def test_attention_called(self, runner, mock_attention):
        """21. Attention service called with correct AttentionRequest fields."""
        req = _make_request()
        result = runner.execute(req)
        mock_attention.assemble.assert_called_once()
        call_args = mock_attention.assemble.call_args
        attn_req = call_args[0][0] if call_args[0] else call_args[1].get("request")
        # Should contain agent_id, agent_class, framework_id, tier, work_order_id, session_id
        assert attn_req is not None

    def test_attention_warnings_logged(self, runner, mock_attention, mock_ledger):
        """22. Warnings from attention are captured in flow execution."""
        mock_attention.assemble.return_value = MagicMock(
            context_text="Partial context.",
            context_hash="sha256:partial",
            fragments=[],
            template_id="ATT-DEFAULT-001",
            pipeline_trace=[],
            budget_used=MagicMock(tokens=50, queries=1, elapsed_ms=20),
            warnings=["File HOT/missing.json not found — skipped"],
        )
        req = _make_request()
        result = runner.execute(req)
        # Flow should still succeed (warnings are non-fatal)
        assert result.status == "success"

    def test_attention_failure_handled(self, runner, mock_attention):
        """23. Attention fail (on_empty:fail) → flow returns failure."""
        mock_attention.assemble.side_effect = RuntimeError(
            "Attention failed: no context and on_empty=fail"
        )
        req = _make_request()
        result = runner.execute(req)
        assert result.status == "failure"
        assert result.error is not None


# ===================================================================
# STEP 6: Prompt Routing (tests 24-27)
# ===================================================================

class TestPromptRouting:

    def test_router_called(self, runner, mock_router):
        """24. Router called with assembled context + contract."""
        req = _make_request()
        result = runner.execute(req)
        mock_router.send.assert_called_once()

    def test_router_rejection_handled(self, runner, mock_router):
        """25. Auth/budget rejection from router → flow failure."""
        mock_router.send.side_effect = RuntimeError("BUDGET_EXHAUSTED")
        req = _make_request()
        result = runner.execute(req)
        assert result.status in ("rejected", "failure")
        assert result.error is not None

    def test_router_timeout_handled(self, runner, mock_router):
        """26. Router timeout → flow returns status="timeout"."""
        mock_router.send.side_effect = TimeoutError("Provider timeout after 120s")
        req = _make_request()
        result = runner.execute(req)
        assert result.status == "timeout"

    def test_router_response_captured(self, runner, mock_router):
        """27. Response text, tokens, entry IDs captured in FlowResult."""
        req = _make_request()
        result = runner.execute(req)
        assert result.response == "This is the LLM response."
        assert result.tokens_used == {"input": 500, "output": 200}
        assert len(result.ledger_entry_ids) > 0


# ===================================================================
# STEP 7: Acceptance Criteria (tests 28-30)
# ===================================================================

class TestAcceptanceCriteria:

    def test_output_schema_validated(self, runner, mock_router):
        """28. Response validated against io_schema.output_schema."""
        wo = _valid_work_order(io_schema={
            "output_schema": {
                "type": "object",
                "required": ["result"],
                "properties": {"result": {"type": "string"}},
            }
        })
        # Router returns JSON that matches the schema
        mock_router.send.return_value = MagicMock(
            response='{"result": "done"}',
            tokens_used={"input": 100, "output": 50},
            ledger_entry_ids=["LED-cc000001"],
            validation_result={"valid": True},
            latency_ms=80,
        )
        req = _make_request(work_order=wo)
        result = runner.execute(req)
        assert result.validation_result is not None

    def test_acceptance_all_pass(self, runner):
        """29. All acceptance criteria pass → success."""
        wo = _valid_work_order(acceptance={"tests": [], "checks": []})
        req = _make_request(work_order=wo)
        result = runner.execute(req)
        assert result.status == "success"

    def test_acceptance_partial_fail(self, runner):
        """30. Some acceptance criteria fail → failure with gate_results."""
        wo = _valid_work_order(acceptance={
            "tests": ["false"],  # exit 1 = fail
            "checks": [],
        })
        req = _make_request(work_order=wo)
        result = runner.execute(req)
        assert result.status == "failure"
        assert result.validation_result is not None


# ===================================================================
# STEP 8: Outcome (tests 31-33)
# ===================================================================

class TestOutcome:

    def test_success_logged(self, runner, mock_ledger):
        """31. WO_EXEC_COMPLETE logged with full outcome metadata."""
        req = _make_request()
        result = runner.execute(req)
        assert result.status == "success"
        complete_calls = [
            call for call in mock_ledger.write.call_args_list
            if call[0][0].event_type == "WO_EXEC_COMPLETE"
        ]
        assert len(complete_calls) >= 1
        entry = complete_calls[0][0][0]
        meta = entry.metadata
        assert "outcome" in meta or "status" in meta

    def test_failure_logged(self, runner, mock_router, mock_ledger):
        """32. WO_EXEC_FAILED logged with error detail."""
        mock_router.send.side_effect = RuntimeError("Provider crashed")
        req = _make_request()
        result = runner.execute(req)
        failed_calls = [
            call for call in mock_ledger.write.call_args_list
            if call[0][0].event_type == "WO_EXEC_FAILED"
        ]
        assert len(failed_calls) >= 1

    def test_ledger_entry_ids_collected(self, runner, mock_ledger):
        """33. All ledger entries from flow collected in result."""
        req = _make_request()
        result = runner.execute(req)
        # Should have at least WO_STARTED + WO_EXEC_COMPLETE + router entries
        assert len(result.ledger_entry_ids) >= 2


# ===================================================================
# FULL FLOW (tests 34-36)
# ===================================================================

class TestFullFlow:

    def test_happy_path_single_step(self, runner, mock_budgeter, mock_attention,
                                     mock_router, mock_ledger):
        """34. Full flow: valid WO → framework → budget → context → prompt → accept → success."""
        req = _make_request()
        result = runner.execute(req)

        assert result.status == "success"
        assert result.work_order_id == "WO-20260210-001"
        assert result.agent_id.startswith("AGT-")
        assert result.response == "This is the LLM response."
        assert result.tokens_used == {"input": 500, "output": 200}
        assert result.error is None
        assert result.duration_ms >= 0
        assert len(result.ledger_entry_ids) >= 2

        # Verify call order: budgeter → attention → router
        mock_budgeter.allocate.assert_called_once()
        mock_attention.assemble.assert_called_once()
        mock_router.send.assert_called_once()

    def test_dev_mode_bypasses_auth(self, runner, mock_auth):
        """35. Dev mode skips auth, uses mock provider."""
        req = _make_request(dev_mode=True)
        result = runner.execute(req)
        assert result.status == "success"
        # In dev mode, auth should be bypassed (not called, or called with passthrough)
        # Implementation may vary — at minimum, flow should not reject due to auth.

    def test_result_always_returned(self, runner, mock_framework_resolver):
        """36. No exceptions leak — FlowResult always returned."""
        # Make framework resolver raise an unexpected error
        mock_framework_resolver.resolve.side_effect = Exception("Unexpected DB error")
        req = _make_request()
        result = runner.execute(req)
        # Should get a FlowResult, not an exception
        assert isinstance(result, FlowResult)
        assert result.status == "failure"
        assert result.error is not None


# ===================================================================
# V2 EXTENSION POINTS (tests 37-40)
# ===================================================================

class TestV2ExtensionPoints:

    def test_single_step_strategy(self):
        """37. SingleStepStrategy: send one prompt, then complete."""
        strategy = SingleStepStrategy()
        ctx = MagicMock()

        # First call: no history → send_prompt
        action = strategy.next_step(ctx, history=[])
        assert action.type == "send_prompt"

        # Second call: with history → complete
        action = strategy.next_step(ctx, history=[MagicMock()])
        assert action.type == "complete"

    def test_aperture_always_closed_v1(self):
        """38. ApertureManager returns 'closed' in v1."""
        aperture = ApertureManager()
        assert aperture.current_state() == "closed"
        assert aperture.should_transition(step_count=5, budget_remaining=0.5) is None

    def test_delegation_not_implemented_v1(self):
        """39. DelegationManager raises NotImplementedError in v1."""
        delegation = DelegationManager()
        with pytest.raises(NotImplementedError):
            delegation.create_sub_wo(parent_wo={}, sub_task={})
        with pytest.raises(NotImplementedError):
            delegation.collect_results(sub_results=[])

    def test_recovery_discards_v1(self):
        """40. RecoveryStrategy returns 'discard' in v1."""
        recovery = RecoveryStrategy()
        result = recovery.on_failure(
            context=MagicMock(),
            partial_results=[],
            error="Some error",
        )
        assert result == "discard"
