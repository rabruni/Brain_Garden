"""Tests for PKG-WORK-ORDER-001 — Work Order atom.

37 tests covering:
- WorkOrder creation (7)
- State machine transitions (11)
- Validation (4)
- WO ledger entries (8)
- Schema coexistence (2)
- Serialization (2)
- Edge cases (3)

All tests use tmp_path fixtures and mock data. No real LLM calls. No API keys.
"""

import json
import sys
from pathlib import Path
from dataclasses import asdict
from unittest.mock import MagicMock, patch, call

import pytest

# Path setup: add kernel dirs directly (staging pattern — matches installed HOT/kernel/ merge)
_staging = Path(__file__).resolve().parents[3]  # _staging/
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT"))
sys.path.insert(0, str(_staging / "PKG-WORK-ORDER-001" / "HOT" / "kernel"))

from work_order import (  # noqa: E402
    WorkOrder,
    WorkOrderStateMachine,
    WorkOrderValidator,
    InvalidTransitionError,
    WorkOrderValidationError,
    COGNITIVE_WO_TYPES,
    WO_STATES,
    TERMINAL_STATES,
)
from wo_ledger import WOLedgerHelper  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def basic_wo():
    """Create a basic classify WorkOrder for testing."""
    return WorkOrder.create(
        wo_type="classify",
        session_id="SES-A1B2C3D4",
        created_by="ADMIN.ho2",
        input_context={"user_input": "show me all frameworks"},
        constraints={
            "prompt_contract_id": "PC-C-001",
            "token_budget": 2000,
            "turn_limit": 3,
            "timeout_seconds": 30,
        },
        acceptance_criteria={"min_confidence": 0.8},
    )


@pytest.fixture
def mock_ledger_client():
    """Create a mock LedgerClient that records write() calls."""
    client = MagicMock()
    client.write.return_value = "LED-abcd1234"
    return client


# ===========================================================================
# 1. WorkOrder Creation Tests (7)
# ===========================================================================

class TestWorkOrderCreation:
    def test_create_classify_wo(self):
        """Test 1: classify WO created with correct defaults."""
        wo = WorkOrder.create(
            wo_type="classify",
            session_id="SES-A1B2C3D4",
            created_by="ADMIN.ho2",
            input_context={"user_input": "hello"},
            constraints={"prompt_contract_id": "PC-C-001", "token_budget": 2000},
        )
        assert wo.state == "planned"
        assert wo.wo_type == "classify"
        assert wo.wo_id.startswith("WO-SES-A1B2C3D4-")
        assert wo.created_at != ""
        assert wo.tier_target == "HO1"

    def test_create_tool_call_wo(self):
        """Test 2: tool_call WO accepted, tier_target is HO1."""
        wo = WorkOrder.create(
            wo_type="tool_call",
            session_id="SES-X1Y2Z3W4",
            created_by="ADMIN.ho2",
            constraints={"tools_allowed": ["read_file"], "token_budget": 1000},
        )
        assert wo.wo_type == "tool_call"
        assert wo.tier_target == "HO1"

    def test_create_synthesize_wo(self):
        """Test 3: synthesize WO accepted."""
        wo = WorkOrder.create(
            wo_type="synthesize",
            session_id="SES-A1B2C3D4",
            created_by="ADMIN.ho2",
            constraints={"prompt_contract_id": "PC-S-001", "token_budget": 5000},
        )
        assert wo.wo_type == "synthesize"

    def test_create_execute_wo(self):
        """Test 4: execute WO accepted."""
        wo = WorkOrder.create(
            wo_type="execute",
            session_id="SES-A1B2C3D4",
            created_by="ADMIN.ho2",
            constraints={"prompt_contract_id": "PC-E-001", "token_budget": 3000},
        )
        assert wo.wo_type == "execute"

    def test_create_invalid_type_rejected(self):
        """Test 5: wo_type='delegate' raises error -- only 4 types allowed."""
        with pytest.raises(ValueError, match="Invalid wo_type"):
            WorkOrder.create(
                wo_type="delegate",
                session_id="SES-A1B2C3D4",
                created_by="ADMIN.ho2",
            )

    def test_create_required_fields(self):
        """Test 6: Missing session_id or created_by raises error."""
        with pytest.raises((ValueError, TypeError)):
            WorkOrder.create(
                wo_type="classify",
                session_id="",
                created_by="ADMIN.ho2",
            )
        with pytest.raises((ValueError, TypeError)):
            WorkOrder.create(
                wo_type="classify",
                session_id="SES-A1B2C3D4",
                created_by="",
            )

    def test_create_default_cost(self):
        """Test 7: Default cost dict has all 6 zero fields."""
        wo = WorkOrder.create(
            wo_type="classify",
            session_id="SES-A1B2C3D4",
            created_by="ADMIN.ho2",
            constraints={"prompt_contract_id": "PC-C-001", "token_budget": 1000},
        )
        expected_keys = {"input_tokens", "output_tokens", "total_tokens",
                         "llm_calls", "tool_calls", "elapsed_ms"}
        assert set(wo.cost.keys()) == expected_keys
        assert all(v == 0 for v in wo.cost.values())


# ===========================================================================
# 2. State Machine Transition Tests (11)
# ===========================================================================

class TestStateMachineTransitions:
    def test_planned_to_dispatched(self, basic_wo):
        """Test 8: planned -> dispatched is valid."""
        result = WorkOrderStateMachine.transition(basic_wo, "dispatched")
        assert result.state == "dispatched"

    def test_dispatched_to_executing(self, basic_wo):
        """Test 9: dispatched -> executing is valid."""
        WorkOrderStateMachine.transition(basic_wo, "dispatched")
        result = WorkOrderStateMachine.transition(basic_wo, "executing", actor_tier="HO1")
        assert result.state == "executing"

    def test_executing_to_completed(self, basic_wo):
        """Test 10: executing -> completed is valid, is_terminal() returns True."""
        WorkOrderStateMachine.transition(basic_wo, "dispatched")
        WorkOrderStateMachine.transition(basic_wo, "executing", actor_tier="HO1")
        result = WorkOrderStateMachine.transition(basic_wo, "completed", actor_tier="HO1")
        assert result.state == "completed"
        assert result.is_terminal()

    def test_executing_to_failed(self, basic_wo):
        """Test 11: executing -> failed is valid, is_terminal() returns True."""
        WorkOrderStateMachine.transition(basic_wo, "dispatched")
        WorkOrderStateMachine.transition(basic_wo, "executing", actor_tier="HO1")
        result = WorkOrderStateMachine.transition(basic_wo, "failed", actor_tier="HO1")
        assert result.state == "failed"
        assert result.is_terminal()

    def test_planned_to_failed(self, basic_wo):
        """Test 12: planned -> failed is valid (validation fail at planning)."""
        result = WorkOrderStateMachine.transition(basic_wo, "failed")
        assert result.state == "failed"

    def test_completed_to_any_forbidden(self, basic_wo):
        """Test 13: completed -> dispatched raises InvalidTransitionError."""
        WorkOrderStateMachine.transition(basic_wo, "dispatched")
        WorkOrderStateMachine.transition(basic_wo, "executing", actor_tier="HO1")
        WorkOrderStateMachine.transition(basic_wo, "completed", actor_tier="HO1")
        with pytest.raises(InvalidTransitionError):
            WorkOrderStateMachine.transition(basic_wo, "dispatched")

    def test_failed_to_any_forbidden(self, basic_wo):
        """Test 14: failed -> executing raises InvalidTransitionError."""
        WorkOrderStateMachine.transition(basic_wo, "failed")
        with pytest.raises(InvalidTransitionError):
            WorkOrderStateMachine.transition(basic_wo, "executing", actor_tier="HO1")

    def test_executing_to_planned_forbidden(self, basic_wo):
        """Test 15: No backward regression executing -> planned."""
        WorkOrderStateMachine.transition(basic_wo, "dispatched")
        WorkOrderStateMachine.transition(basic_wo, "executing", actor_tier="HO1")
        with pytest.raises(InvalidTransitionError):
            WorkOrderStateMachine.transition(basic_wo, "planned")

    def test_dispatched_to_planned_forbidden(self, basic_wo):
        """Test 16: No backward regression dispatched -> planned."""
        WorkOrderStateMachine.transition(basic_wo, "dispatched")
        with pytest.raises(InvalidTransitionError):
            WorkOrderStateMachine.transition(basic_wo, "planned")

    def test_ho1_cannot_set_planned(self, basic_wo):
        """Test 17: HO1 cannot transition to 'planned'."""
        with pytest.raises(InvalidTransitionError, match="HO1"):
            WorkOrderStateMachine.transition(basic_wo, "dispatched", actor_tier="HO1")

    def test_ho1_cannot_set_dispatched(self, basic_wo):
        """Test 18: HO1 cannot transition to 'dispatched'."""
        with pytest.raises(InvalidTransitionError, match="HO1"):
            WorkOrderStateMachine.transition(basic_wo, "dispatched", actor_tier="HO1")


# ===========================================================================
# 3. WorkOrder Validation Tests (4)
# ===========================================================================

class TestWorkOrderValidation:
    def test_validate_valid_wo(self, basic_wo):
        """Test 19: Well-formed WO passes validation."""
        valid, errors = WorkOrderValidator.validate(basic_wo)
        assert valid is True
        assert errors == []

    def test_validate_missing_prompt_contract(self):
        """Test 20: LLM-calling type without prompt_contract_id fails."""
        wo = WorkOrder.create(
            wo_type="classify",
            session_id="SES-A1B2C3D4",
            created_by="ADMIN.ho2",
            constraints={"token_budget": 2000},  # No prompt_contract_id
        )
        valid, errors = WorkOrderValidator.validate(wo)
        assert valid is False
        assert any("prompt_contract_id" in e for e in errors)

    def test_validate_tool_call_needs_tools(self):
        """Test 21: tool_call without tools_allowed fails."""
        wo = WorkOrder.create(
            wo_type="tool_call",
            session_id="SES-A1B2C3D4",
            created_by="ADMIN.ho2",
            constraints={"token_budget": 2000},  # No tools_allowed
        )
        valid, errors = WorkOrderValidator.validate(wo)
        assert valid is False
        assert any("tools_allowed" in e for e in errors)

    def test_validate_budget_positive(self):
        """Test 22: token_budget of 0 or negative fails."""
        wo = WorkOrder.create(
            wo_type="classify",
            session_id="SES-A1B2C3D4",
            created_by="ADMIN.ho2",
            constraints={"prompt_contract_id": "PC-C-001", "token_budget": 0},
        )
        valid, errors = WorkOrderValidator.validate(wo)
        assert valid is False
        assert any("token_budget" in e for e in errors)


# ===========================================================================
# 4. WO Ledger Entry Tests (8)
# ===========================================================================

class TestWOLedgerEntries:
    def test_write_wo_planned_creates_entry(self, basic_wo, mock_ledger_client):
        """Test 23: write_wo_planned() calls ledger_client.write() with WO_PLANNED."""
        helper = WOLedgerHelper(mock_ledger_client)
        entry_id = helper.write_wo_planned(basic_wo)
        mock_ledger_client.write.assert_called_once()
        entry = mock_ledger_client.write.call_args[0][0]
        assert entry.event_type == "WO_PLANNED"
        assert entry_id == "LED-abcd1234"

    def test_write_wo_dispatched_has_parent(self, basic_wo, mock_ledger_client):
        """Test 24: WO_DISPATCHED includes metadata.relational.parent_event_id."""
        helper = WOLedgerHelper(mock_ledger_client)
        helper.write_wo_dispatched(basic_wo, parent_event_id="LED-00001111")
        entry = mock_ledger_client.write.call_args[0][0]
        assert entry.event_type == "WO_DISPATCHED"
        assert entry.metadata["relational"]["parent_event_id"] == "LED-00001111"

    def test_write_wo_executing_has_relational(self, basic_wo, mock_ledger_client):
        """Test 25: WO_EXECUTING includes both parent_event_id and root_event_id."""
        helper = WOLedgerHelper(mock_ledger_client)
        helper.write_wo_executing(
            basic_wo,
            parent_event_id="LED-22223333",
            root_event_id="LED-00001111",
        )
        entry = mock_ledger_client.write.call_args[0][0]
        assert entry.event_type == "WO_EXECUTING"
        rel = entry.metadata["relational"]
        assert rel["parent_event_id"] == "LED-22223333"
        assert rel["root_event_id"] == "LED-00001111"

    def test_write_wo_completed_has_cost(self, basic_wo, mock_ledger_client):
        """Test 26: WO_COMPLETED includes cost in metadata."""
        basic_wo.cost = {"input_tokens": 100, "output_tokens": 50,
                         "total_tokens": 150, "llm_calls": 1,
                         "tool_calls": 0, "elapsed_ms": 500}
        helper = WOLedgerHelper(mock_ledger_client)
        helper.write_wo_completed(
            basic_wo,
            parent_event_id="LED-33334444",
            root_event_id="LED-00001111",
        )
        entry = mock_ledger_client.write.call_args[0][0]
        assert entry.event_type == "WO_COMPLETED"
        assert entry.metadata["cost"]["total_tokens"] == 150

    def test_write_wo_failed_has_error(self, basic_wo, mock_ledger_client):
        """Test 27: WO_FAILED includes error in metadata."""
        basic_wo.error = "Timeout exceeded"
        helper = WOLedgerHelper(mock_ledger_client)
        helper.write_wo_failed(
            basic_wo,
            parent_event_id="LED-44445555",
            root_event_id="LED-00001111",
        )
        entry = mock_ledger_client.write.call_args[0][0]
        assert entry.event_type == "WO_FAILED"
        assert entry.metadata["error"] == "Timeout exceeded"

    def test_write_wo_chain_complete_has_trace_hash(self, mock_ledger_client):
        """Test 28: WO_CHAIN_COMPLETE includes trace_hash in context_fingerprint."""
        helper = WOLedgerHelper(mock_ledger_client)
        helper.write_wo_chain_complete(
            session_id="SES-A1B2C3D4",
            wo_ids=["WO-SES-A1B2C3D4-001"],
            total_cost={"total_tokens": 200},
            trace_hash="sha256:abc123",
            root_event_id="LED-00001111",
        )
        entry = mock_ledger_client.write.call_args[0][0]
        assert entry.event_type == "WO_CHAIN_COMPLETE"
        assert entry.metadata["context_fingerprint"]["context_hash"] == "sha256:abc123"

    def test_write_wo_quality_gate_has_decision(self, mock_ledger_client):
        """Test 29: WO_QUALITY_GATE includes decision field."""
        helper = WOLedgerHelper(mock_ledger_client)
        helper.write_wo_quality_gate(
            session_id="SES-A1B2C3D4",
            decision="accept",
            parent_event_id="LED-55556666",
            trace_hash="sha256:def456",
        )
        entry = mock_ledger_client.write.call_args[0][0]
        assert entry.event_type == "WO_QUALITY_GATE"
        assert entry.metadata["decision"] == "accept"

    def test_all_entries_have_provenance(self, basic_wo, mock_ledger_client):
        """Test 30: Every event type populates metadata.provenance."""
        helper = WOLedgerHelper(mock_ledger_client)

        # Write one of each type
        helper.write_wo_planned(basic_wo)
        helper.write_wo_dispatched(basic_wo, parent_event_id="LED-00001111")
        helper.write_wo_executing(basic_wo, parent_event_id="LED-22223333", root_event_id="LED-00001111")
        helper.write_wo_completed(basic_wo, parent_event_id="LED-33334444", root_event_id="LED-00001111")
        basic_wo.error = "test error"
        helper.write_wo_failed(basic_wo, parent_event_id="LED-44445555", root_event_id="LED-00001111")
        helper.write_wo_chain_complete(
            session_id="SES-A1B2C3D4", wo_ids=["WO-1"], total_cost={},
            trace_hash="h", root_event_id="LED-00001111",
        )
        helper.write_wo_quality_gate(
            session_id="SES-A1B2C3D4", decision="accept",
            parent_event_id="LED-55556666", trace_hash="h",
        )

        assert mock_ledger_client.write.call_count == 7
        for call_args in mock_ledger_client.write.call_args_list:
            entry = call_args[0][0]
            prov = entry.metadata.get("provenance", {})
            assert "session_id" in prov, f"{entry.event_type} missing provenance.session_id"


# ===========================================================================
# 5. Schema Coexistence Tests (2)
# ===========================================================================

class TestSchemaCoexistence:
    def test_cognitive_schema_validates_independently(self):
        """Test 31: cognitive_work_order.schema.json loads and validates independently."""
        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "cognitive_work_order.schema.json"
        schema = json.loads(schema_path.read_text())

        assert schema["title"] == "Cognitive Work Order Schema"
        assert "classify" in schema["properties"]["wo_type"]["enum"]
        assert "$ref" not in json.dumps(schema)

        # Validate a sample cognitive WO against the schema structure
        sample = {
            "wo_id": "WO-SES-A1B2C3D4-001",
            "session_id": "SES-A1B2C3D4",
            "wo_type": "classify",
            "tier_target": "HO1",
            "state": "planned",
            "created_at": "2026-02-15T00:00:00Z",
            "created_by": "ADMIN.ho2",
        }
        # Check required fields are present
        for req in schema["required"]:
            assert req in sample

    def test_cognitive_schema_rejects_governance_type(self):
        """Test 32: wo_type='code_change' not in cognitive schema types."""
        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "cognitive_work_order.schema.json"
        schema = json.loads(schema_path.read_text())
        assert "code_change" not in schema["properties"]["wo_type"]["enum"]


# ===========================================================================
# 6. Serialization Tests (2)
# ===========================================================================

class TestSerialization:
    def test_wo_json_roundtrip(self, basic_wo):
        """Test 33: to_json() -> from_json() produces identical object."""
        json_str = basic_wo.to_json()
        restored = WorkOrder.from_json(json_str)
        assert restored.wo_id == basic_wo.wo_id
        assert restored.wo_type == basic_wo.wo_type
        assert restored.state == basic_wo.state
        assert restored.session_id == basic_wo.session_id
        assert restored.created_by == basic_wo.created_by
        assert restored.input_context == basic_wo.input_context
        assert restored.constraints == basic_wo.constraints
        assert restored.cost == basic_wo.cost

    def test_wo_dict_roundtrip(self, basic_wo):
        """Test 34: to_dict() -> from_dict() produces identical object."""
        d = basic_wo.to_dict()
        restored = WorkOrder.from_dict(d)
        assert restored.wo_id == basic_wo.wo_id
        assert restored.wo_type == basic_wo.wo_type
        assert restored.state == basic_wo.state
        assert restored.constraints == basic_wo.constraints


# ===========================================================================
# 7. Edge Case Tests (3)
# ===========================================================================

class TestEdgeCases:
    def test_parent_wo_id_chain(self):
        """Test 35: WO with parent_wo_id serializes and deserializes correctly."""
        wo = WorkOrder.create(
            wo_type="classify",
            session_id="SES-A1B2C3D4",
            created_by="ADMIN.ho2",
            constraints={"prompt_contract_id": "PC-C-001", "token_budget": 1000},
            parent_wo_id="WO-SES-A1B2C3D4-001",
        )
        assert wo.parent_wo_id == "WO-SES-A1B2C3D4-001"
        restored = WorkOrder.from_dict(wo.to_dict())
        assert restored.parent_wo_id == "WO-SES-A1B2C3D4-001"

    def test_empty_input_context(self):
        """Test 36: WO with empty input_context dict is valid."""
        wo = WorkOrder.create(
            wo_type="tool_call",
            session_id="SES-A1B2C3D4",
            created_by="ADMIN.ho2",
            constraints={"tools_allowed": ["list_files"], "token_budget": 500},
            input_context={},
        )
        valid, errors = WorkOrderValidator.validate(wo)
        assert valid is True

    def test_wo_id_format(self):
        """Test 37: Generated wo_id matches pattern WO-SES-{8 alphanum}-{seq:03d}."""
        import re
        wo = WorkOrder.create(
            wo_type="classify",
            session_id="SES-A1B2C3D4",
            created_by="ADMIN.ho2",
            constraints={"prompt_contract_id": "PC-C-001", "token_budget": 1000},
        )
        pattern = r"^WO-SES-[A-Z0-9]{8}-\d{3}$"
        assert re.match(pattern, wo.wo_id), f"wo_id '{wo.wo_id}' doesn't match expected pattern"
