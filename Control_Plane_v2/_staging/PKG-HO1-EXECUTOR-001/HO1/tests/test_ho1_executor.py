"""Tests for PKG-HO1-EXECUTOR-001 — HO1 Executor.

35 tests covering: execute flow (8), contract loading (5), tool loop (5),
budget enforcement (3), state transitions (3), HO1m trace (4),
I/O validation (4), error handling (3).

All tests use mocks. No real LLM calls. No API keys.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch, call

import pytest

_staging = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT"))
sys.path.insert(0, str(_staging / "PKG-PROMPT-ROUTER-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-TOKEN-BUDGETER-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-HO1-EXECUTOR-001" / "HO1" / "kernel"))


@pytest.fixture(autouse=True)
def _bypass_pristine():
    with patch("kernel.pristine.assert_append_only", return_value=None):
        yield


def _mock_response(content='{"speech_act": "greeting", "ambiguity": "low"}', input_tokens=100, output_tokens=50):
    return SimpleNamespace(
        content=content,
        outcome="SUCCESS",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_id="mock-model",
        provider_id="mock",
        latency_ms=100.0,
        timestamp="2026-02-15T00:00:00Z",
        exchange_entry_id="LED-mock001",
    )


def _mock_budget_check(allowed=True, remaining=10000):
    return SimpleNamespace(allowed=allowed, remaining=remaining, reason=None)


def _mock_debit_result():
    return SimpleNamespace(success=True, remaining=9850, total_consumed=150, cost_incurred=0.001, ledger_entry_id="LED-b01")


@pytest.fixture
def classify_wo():
    return {
        "wo_id": "WO-SES-TEST0001-001",
        "session_id": "SES-TEST0001",
        "wo_type": "classify",
        "tier_target": "HO1",
        "state": "dispatched",
        "created_at": "2026-02-15T00:00:00Z",
        "created_by": "ADMIN.ho2",
        "input_context": {"user_input": "hello world"},
        "constraints": {
            "prompt_contract_id": "PRC-CLASSIFY-001",
            "token_budget": 2000,
            "turn_limit": 3,
            "timeout_seconds": 30,
        },
        "acceptance_criteria": {},
        "output_result": None,
        "error": None,
        "completed_at": None,
        "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
    }


@pytest.fixture
def executor(tmp_path):
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()

    # Write classify contract
    (contracts_dir / "classify.json").write_text(json.dumps({
        "contract_id": "PRC-CLASSIFY-001",
        "version": "1.0.0",
        "prompt_pack_id": "PRM-CLASSIFY-001",
        "tier": "ho1",
        "boundary": {"max_tokens": 500, "temperature": 0},
        "input_schema": {"type": "object", "required": ["user_input"], "properties": {"user_input": {"type": "string"}}},
        "output_schema": {"type": "object", "required": ["speech_act", "ambiguity"], "properties": {"speech_act": {"type": "string"}, "ambiguity": {"type": "string"}}},
    }))
    (contracts_dir / "synthesize.json").write_text(json.dumps({
        "contract_id": "PRC-SYNTHESIZE-001",
        "version": "1.0.0",
        "prompt_pack_id": "PRM-SYNTHESIZE-001",
        "tier": "ho1",
        "boundary": {"max_tokens": 4096, "temperature": 0.3},
        "input_schema": {"type": "object", "required": ["prior_results"], "properties": {"prior_results": {"type": "array"}}},
        "output_schema": {"type": "object", "required": ["response_text"], "properties": {"response_text": {"type": "string"}}},
    }))
    (contracts_dir / "execute.json").write_text(json.dumps({
        "contract_id": "PRC-EXECUTE-001",
        "version": "1.0.0",
        "prompt_pack_id": "PRM-EXECUTE-001",
        "tier": "ho1",
        "boundary": {"max_tokens": 4096, "temperature": 0.0},
        "input_schema": {"type": "object", "required": ["user_input"], "properties": {"user_input": {"type": "string"}}},
        "output_schema": {"type": "object", "required": ["result"], "properties": {"result": {"type": "string"}}},
    }))

    from contract_loader import ContractLoader
    from ho1_executor import HO1Executor

    mock_gateway = Mock()
    mock_gateway.route.return_value = _mock_response()

    mock_budgeter = Mock()
    mock_budgeter.check.return_value = _mock_budget_check()
    mock_budgeter.debit.return_value = _mock_debit_result()

    mock_ledger = Mock()
    mock_ledger.write.return_value = "LED-trace01"

    mock_tool_dispatcher = Mock()
    mock_tool_dispatcher.execute.return_value = SimpleNamespace(tool_id="test", status="ok", output="result")

    loader = ContractLoader(contracts_dir=contracts_dir, schema_path=None)

    config = {
        "agent_id": "HO1.test",
        "agent_class": "ADMIN",
        "framework_id": "FMWK-000",
        "package_id": "PKG-HO1-EXECUTOR-001",
        "tier": "ho1",
    }

    return HO1Executor(
        gateway=mock_gateway,
        ledger=mock_ledger,
        budgeter=mock_budgeter,
        tool_dispatcher=mock_tool_dispatcher,
        contract_loader=loader,
        config=config,
    )


# Execute Flow Tests (8)
class TestExecuteFlow:
    def test_execute_classify_happy_path(self, executor, classify_wo):
        result = executor.execute(classify_wo)
        assert result["state"] == "completed"
        assert result["output_result"] is not None

    def test_execute_synthesize_happy_path(self, executor):
        executor.gateway.route.return_value = _mock_response('{"response_text": "Here is your answer"}')
        wo = {
            "wo_id": "WO-SES-TEST0001-002", "session_id": "SES-TEST0001",
            "wo_type": "synthesize", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"prior_results": [{"data": "test"}]},
            "constraints": {"prompt_contract_id": "PRC-SYNTHESIZE-001", "token_budget": 5000, "turn_limit": 3},
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        result = executor.execute(wo)
        assert result["state"] == "completed"

    def test_execute_general_happy_path(self, executor):
        executor.gateway.route.return_value = _mock_response('{"result": "done"}')
        wo = {
            "wo_id": "WO-SES-TEST0001-003", "session_id": "SES-TEST0001",
            "wo_type": "execute", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"user_input": "run task"},
            "constraints": {"prompt_contract_id": "PRC-EXECUTE-001", "token_budget": 3000, "turn_limit": 3},
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        result = executor.execute(wo)
        assert result["state"] == "completed"

    def test_execute_tool_call_wo_type(self, executor):
        wo = {
            "wo_id": "WO-SES-TEST0001-004", "session_id": "SES-TEST0001",
            "wo_type": "tool_call", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {},
            "constraints": {"tools_allowed": ["list_files"], "token_budget": 500},
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        result = executor.execute(wo)
        assert result["state"] == "completed"
        assert result["cost"]["tool_calls"] >= 1

    def test_execute_returns_completed_state(self, executor, classify_wo):
        result = executor.execute(classify_wo)
        assert result["state"] == "completed"

    def test_execute_populates_output_result(self, executor, classify_wo):
        result = executor.execute(classify_wo)
        assert result["output_result"] is not None
        assert isinstance(result["output_result"], dict)

    def test_execute_populates_cost_fields(self, executor, classify_wo):
        result = executor.execute(classify_wo)
        assert result["cost"]["input_tokens"] > 0
        assert result["cost"]["llm_calls"] >= 1

    def test_execute_populates_completed_at(self, executor, classify_wo):
        result = executor.execute(classify_wo)
        assert result["completed_at"] is not None
        assert "T" in result["completed_at"]


# Contract Loading Tests (5)
class TestContractLoading:
    def test_contract_loader_load_by_id(self, executor):
        contract = executor.contract_loader.load("PRC-CLASSIFY-001")
        assert contract["contract_id"] == "PRC-CLASSIFY-001"

    def test_contract_loader_validates_schema(self, executor):
        contract = executor.contract_loader.load("PRC-CLASSIFY-001")
        assert "boundary" in contract
        assert "input_schema" in contract

    def test_contract_loader_missing_contract(self, executor):
        from contract_loader import ContractNotFoundError
        with pytest.raises(ContractNotFoundError):
            executor.contract_loader.load("PRC-NONEXISTENT-001")

    def test_contract_loader_invalid_schema(self, tmp_path):
        contracts_dir = tmp_path / "bad_contracts"
        contracts_dir.mkdir()
        (contracts_dir / "bad.json").write_text(json.dumps({"contract_id": "PRC-BAD-001"}))

        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({
            "type": "object",
            "required": ["contract_id", "boundary", "input_schema"],
        }))

        from contract_loader import ContractLoader, ContractValidationError
        loader = ContractLoader(contracts_dir=contracts_dir, schema_path=schema_path)
        with pytest.raises(ContractValidationError):
            loader.load("PRC-BAD-001")

    def test_contract_loader_extracts_boundary(self, executor):
        contract = executor.contract_loader.load("PRC-CLASSIFY-001")
        assert "max_tokens" in contract["boundary"]
        assert "temperature" in contract["boundary"]


# Tool Loop Tests (5)
class TestToolLoop:
    def test_tool_loop_single_tool_call(self, executor, classify_wo):
        tool_use_response = _mock_response('[{"type": "tool_use", "tool_id": "read_file", "arguments": {"path": "test.py"}}]')
        text_response = _mock_response('{"speech_act": "command", "ambiguity": "low"}')
        executor.gateway.route.side_effect = [tool_use_response, text_response]
        result = executor.execute(classify_wo)
        assert result["state"] == "completed"
        assert result["cost"]["llm_calls"] == 2

    def test_tool_loop_multi_round(self, executor, classify_wo):
        tool_resp1 = _mock_response('[{"type": "tool_use", "tool_id": "t1", "arguments": {}}]')
        tool_resp2 = _mock_response('[{"type": "tool_use", "tool_id": "t2", "arguments": {}}]')
        text_resp = _mock_response('{"speech_act": "greeting", "ambiguity": "low"}')
        executor.gateway.route.side_effect = [tool_resp1, tool_resp2, text_resp]
        result = executor.execute(classify_wo)
        assert result["state"] == "completed"
        assert result["cost"]["llm_calls"] == 3

    def test_tool_loop_budget_exhausted_mid_loop(self, executor, classify_wo):
        tool_resp = _mock_response('[{"type": "tool_use", "tool_id": "t1", "arguments": {}}]')
        executor.gateway.route.return_value = tool_resp
        executor.budgeter.check.side_effect = [
            _mock_budget_check(True), _mock_budget_check(False)
        ]
        result = executor.execute(classify_wo)
        assert result["state"] == "failed"
        assert "budget_exhausted" in result.get("error", "")

    def test_tool_loop_turn_limit_exceeded(self, executor):
        tool_resp = _mock_response('[{"type": "tool_use", "tool_id": "t1", "arguments": {}}]')
        executor.gateway.route.return_value = tool_resp
        wo = {
            "wo_id": "WO-SES-TEST0001-005", "session_id": "SES-TEST0001",
            "wo_type": "classify", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"user_input": "test"},
            "constraints": {"prompt_contract_id": "PRC-CLASSIFY-001", "token_budget": 2000, "turn_limit": 2},
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        result = executor.execute(wo)
        assert result["state"] == "failed"
        assert "turn_limit_exceeded" in result.get("error", "")

    def test_tool_use_extraction_parses_json(self):
        from ho1_executor import HO1Executor
        exec_inst = HO1Executor.__new__(HO1Executor)
        content = '[{"type": "tool_use", "tool_id": "read_file", "arguments": {"path": "x"}}]'
        result = exec_inst._extract_tool_uses(content)
        assert len(result) == 1
        assert result[0]["tool_id"] == "read_file"


# Budget Enforcement Tests (3)
class TestBudgetEnforcement:
    def test_budget_debit_after_each_call(self, executor, classify_wo):
        executor.execute(classify_wo)
        assert executor.budgeter.debit.call_count >= 1

    def test_budget_exhausted_fails_wo(self, executor, classify_wo):
        executor.budgeter.check.return_value = _mock_budget_check(False)
        result = executor.execute(classify_wo)
        assert result["state"] == "failed"
        assert "budget_exhausted" in result.get("error", "")

    def test_budget_scope_uses_wo_fields(self, executor, classify_wo):
        executor.execute(classify_wo)
        debit_call = executor.budgeter.debit.call_args
        scope = debit_call[0][0]
        assert scope.session_id == "SES-TEST0001"


# State Transition Tests (3)
class TestStateTransitions:
    def test_state_dispatched_to_executing(self, executor, classify_wo):
        # The WO starts as dispatched, should transition to executing then completed
        result = executor.execute(classify_wo)
        assert result["state"] in ("completed", "failed")

    def test_state_executing_to_completed(self, executor, classify_wo):
        result = executor.execute(classify_wo)
        assert result["state"] == "completed"

    def test_state_executing_to_failed(self, executor, classify_wo):
        executor.gateway.route.side_effect = Exception("Gateway error")
        result = executor.execute(classify_wo)
        assert result["state"] == "failed"


# HO1m Trace Writing Tests (4)
class TestTraceWriting:
    def test_trace_llm_call_entry(self, executor, classify_wo):
        executor.execute(classify_wo)
        calls = [c for c in executor.ledger.write.call_args_list
                 if c[0][0].event_type == "LLM_CALL"]
        assert len(calls) >= 1

    def test_trace_tool_call_entry(self, executor):
        tool_resp = _mock_response('[{"type": "tool_use", "tool_id": "t1", "arguments": {}}]')
        text_resp = _mock_response('{"speech_act": "greeting", "ambiguity": "low"}')
        executor.gateway.route.side_effect = [tool_resp, text_resp]
        wo = {
            "wo_id": "WO-SES-TEST0001-006", "session_id": "SES-TEST0001",
            "wo_type": "classify", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"user_input": "test"},
            "constraints": {"prompt_contract_id": "PRC-CLASSIFY-001", "token_budget": 2000, "turn_limit": 5},
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        executor.execute(wo)
        calls = [c for c in executor.ledger.write.call_args_list
                 if c[0][0].event_type == "TOOL_CALL"]
        assert len(calls) >= 1

    def test_trace_wo_completed_entry(self, executor, classify_wo):
        executor.execute(classify_wo)
        calls = [c for c in executor.ledger.write.call_args_list
                 if c[0][0].event_type == "WO_COMPLETED"]
        assert len(calls) == 1

    def test_trace_wo_failed_entry(self, executor, classify_wo):
        executor.gateway.route.side_effect = Exception("test error")
        executor.execute(classify_wo)
        calls = [c for c in executor.ledger.write.call_args_list
                 if c[0][0].event_type == "WO_FAILED"]
        assert len(calls) == 1


# Input/Output Validation Tests (4)
class TestIOValidation:
    def test_input_validation_passes(self, executor, classify_wo):
        result = executor.execute(classify_wo)
        assert result["state"] == "completed"

    def test_input_validation_fails(self, executor):
        wo = {
            "wo_id": "WO-SES-TEST0001-007", "session_id": "SES-TEST0001",
            "wo_type": "classify", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {},  # Missing required user_input
            "constraints": {"prompt_contract_id": "PRC-CLASSIFY-001", "token_budget": 2000, "turn_limit": 3},
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        result = executor.execute(wo)
        assert result["state"] == "failed"
        assert "input_schema_invalid" in result.get("error", "")

    def test_output_validation_passes(self, executor, classify_wo):
        result = executor.execute(classify_wo)
        assert result["state"] == "completed"

    def test_output_validation_fails(self, executor, classify_wo):
        executor.gateway.route.return_value = _mock_response('{"wrong": "fields"}')
        result = executor.execute(classify_wo)
        assert result["state"] == "failed"
        assert "output_schema_invalid" in result.get("error", "")


# Error Handling Tests (3)
class TestErrorHandling:
    def test_gateway_error_fails_wo(self, executor, classify_wo):
        executor.gateway.route.side_effect = Exception("Connection refused")
        result = executor.execute(classify_wo)
        assert result["state"] == "failed"
        assert "gateway_error" in result.get("error", "")

    def test_contract_missing_fails_wo(self, executor):
        wo = {
            "wo_id": "WO-SES-TEST0001-008", "session_id": "SES-TEST0001",
            "wo_type": "classify", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"user_input": "test"},
            "constraints": {"prompt_contract_id": "PRC-NONEXISTENT-001", "token_budget": 2000, "turn_limit": 3},
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        result = executor.execute(wo)
        assert result["state"] == "failed"
        assert "contract_not_found" in result.get("error", "")

    def test_budget_gone_before_start(self, executor, classify_wo):
        executor.budgeter.check.return_value = _mock_budget_check(False)
        result = executor.execute(classify_wo)
        assert result["state"] == "failed"
        assert "budget_exhausted" in result.get("error", "")
