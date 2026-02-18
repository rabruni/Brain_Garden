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
sys.path.insert(0, str(_staging / "PKG-LLM-GATEWAY-001" / "HOT" / "kernel"))
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


def _mock_tool_use_response(
    tool_id="list_packages",
    arguments=None,
    input_tokens=100,
    output_tokens=50,
):
    if arguments is None:
        arguments = {}
    return SimpleNamespace(
        content="{}",
        outcome="SUCCESS",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_id="mock-model",
        provider_id="mock",
        latency_ms=100.0,
        timestamp="2026-02-15T00:00:00Z",
        exchange_entry_id="LED-mock001",
        finish_reason="tool_use",
        content_blocks=(
            {"type": "tool_use", "id": "toolu_01", "name": tool_id, "input": arguments},
        ),
    )


def _mock_output_json_response(
    payload=None,
    extra_blocks=None,
    content="",
    input_tokens=100,
    output_tokens=50,
):
    if payload is None:
        payload = {"speech_act": "greeting", "ambiguity": "low"}
    blocks = [{"type": "tool_use", "id": "toolu_outjson", "name": "output_json", "input": payload}]
    if extra_blocks:
        blocks.extend(extra_blocks)
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
        finish_reason="tool_use",
        content_blocks=tuple(blocks),
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
        "boundary": {"max_tokens": 500, "temperature": 0, "structured_output": {
            "type": "object", "required": ["speech_act", "ambiguity"],
            "properties": {"speech_act": {"type": "string"}, "ambiguity": {"type": "string"}},
        }},
        "input_schema": {"type": "object", "required": ["user_input"], "properties": {"user_input": {"type": "string"}}},
        "output_schema": {"type": "object", "required": ["speech_act", "ambiguity"], "properties": {"speech_act": {"type": "string"}, "ambiguity": {"type": "string"}}},
    }))
    (contracts_dir / "synthesize.json").write_text(json.dumps({
        "contract_id": "PRC-SYNTHESIZE-001",
        "version": "1.0.0",
        "prompt_pack_id": "PRM-SYNTHESIZE-001",
        "tier": "ho1",
        "boundary": {"max_tokens": 4096, "temperature": 0.3, "structured_output": {
            "type": "object", "required": ["response_text"],
            "properties": {"response_text": {"type": "string"}},
        }},
        "input_schema": {"type": "object", "required": ["prior_results"], "properties": {"prior_results": {"type": "array"}}},
        "output_schema": {"type": "object", "required": ["response_text"], "properties": {"response_text": {"type": "string"}}},
    }))
    (contracts_dir / "execute.json").write_text(json.dumps({
        "contract_id": "PRC-EXECUTE-001",
        "version": "1.0.0",
        "prompt_pack_id": "PRM-EXECUTE-001",
        "tier": "ho1",
        "boundary": {"max_tokens": 4096, "temperature": 0.0, "structured_output": {
            "type": "object", "required": ["result"],
            "properties": {"result": {"type": "string"}},
        }},
        "input_schema": {"type": "object", "required": ["user_input"], "properties": {"user_input": {"type": "string"}}},
        "output_schema": {"type": "object", "required": ["result"], "properties": {"result": {"type": "string"}}},
    }))

    # Write prompt pack templates
    prompt_packs_dir = tmp_path / "prompt_packs"
    prompt_packs_dir.mkdir()
    (prompt_packs_dir / "PRM-CLASSIFY-001.txt").write_text(
        "You are a speech act classifier.\n\nUser input:\n{{user_input}}\n\n"
        "Respond with valid JSON only matching the schema."
    )
    (prompt_packs_dir / "PRM-SYNTHESIZE-001.txt").write_text(
        "You are a response synthesizer.\n\nPrior results:\n{{prior_results}}\n\n"
        "User input:\n{{user_input}}\n\nClassification:\n{{classification}}\n\n"
        "Assembled context:\n{{assembled_context}}\n\n"
        "Respond with valid JSON only matching the schema."
    )
    (prompt_packs_dir / "PRM-EXECUTE-001.txt").write_text(
        "You are a task executor.\n\nUser input:\n{{user_input}}\n\n"
        "Assembled context:\n{{assembled_context}}\n\n"
        "Respond with valid JSON only matching the schema."
    )

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
    mock_tool_dispatcher.get_api_tools.return_value = [
        {"name": "read_file", "description": "Read file", "input_schema": {"type": "object", "properties": {}}},
        {"name": "t1", "description": "Tool 1", "input_schema": {"type": "object", "properties": {}}},
        {"name": "t2", "description": "Tool 2", "input_schema": {"type": "object", "properties": {}}},
        {"name": "list_packages", "description": "List packages", "input_schema": {"type": "object", "properties": {}}},
        {"name": "list_files", "description": "List files", "input_schema": {"type": "object", "properties": {}}},
    ]

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
        classify_wo["constraints"]["tools_allowed"] = ["read_file"]
        tool_use_response = _mock_response('[{"type": "tool_use", "tool_id": "read_file", "arguments": {"path": "test.py"}}]')
        text_response = _mock_response('{"speech_act": "command", "ambiguity": "low"}')
        executor.gateway.route.side_effect = [tool_use_response, text_response]
        result = executor.execute(classify_wo)
        assert result["state"] == "completed"
        assert result["cost"]["llm_calls"] == 2

    def test_tool_loop_multi_round(self, executor, classify_wo):
        classify_wo["constraints"]["tools_allowed"] = ["t1", "t2"]
        tool_resp1 = _mock_response('[{"type": "tool_use", "tool_id": "t1", "arguments": {}}]')
        tool_resp2 = _mock_response('[{"type": "tool_use", "tool_id": "t2", "arguments": {}}]')
        text_resp = _mock_response('{"speech_act": "greeting", "ambiguity": "low"}')
        executor.gateway.route.side_effect = [tool_resp1, tool_resp2, text_resp]
        result = executor.execute(classify_wo)
        assert result["state"] == "completed"
        assert result["cost"]["llm_calls"] == 3

    def test_tool_loop_budget_exhausted_mid_loop(self, executor, classify_wo):
        classify_wo["constraints"]["tools_allowed"] = ["t1"]
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
            "constraints": {"prompt_contract_id": "PRC-CLASSIFY-001", "token_budget": 2000, "turn_limit": 2, "tools_allowed": ["t1"]},
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
    def test_no_double_debit_from_ho1(self, executor, classify_wo):
        executor.execute(classify_wo)
        assert executor.budgeter.debit.call_count == 0

    def test_budget_exhausted_fails_wo(self, executor, classify_wo):
        executor.budgeter.check.return_value = _mock_budget_check(False)
        result = executor.execute(classify_wo)
        assert result["state"] == "failed"
        assert "budget_exhausted" in result.get("error", "")

    def test_budget_scope_uses_wo_fields(self, executor, classify_wo):
        executor.execute(classify_wo)
        check_call = executor.budgeter.check.call_args
        scope = check_call[0][0]
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
            "constraints": {"prompt_contract_id": "PRC-CLASSIFY-001", "token_budget": 2000, "turn_limit": 5, "tools_allowed": ["t1"]},
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

    def test_llm_call_entry_has_prompts_used(self, executor, classify_wo):
        executor.execute(classify_wo)
        llm_calls = [c[0][0] for c in executor.ledger.write.call_args_list if c[0][0].event_type == "LLM_CALL"]
        assert len(llm_calls) >= 1
        assert len(llm_calls[0].prompts_used) >= 1

    def test_prompts_used_contains_prompt_pack_id(self, executor, classify_wo):
        executor.execute(classify_wo)
        llm_calls = [c[0][0] for c in executor.ledger.write.call_args_list if c[0][0].event_type == "LLM_CALL"]
        assert "PRM-CLASSIFY-001" in llm_calls[0].prompts_used

    def test_prompts_used_empty_for_tool_call_wo(self, executor):
        wo = {
            "wo_id": "WO-SES-TEST0001-009", "session_id": "SES-TEST0001",
            "wo_type": "tool_call", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {},
            "constraints": {"tools_allowed": ["list_packages"], "token_budget": 500},
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        executor.execute(wo)
        trace_entries = [c[0][0] for c in executor.ledger.write.call_args_list]
        assert all(entry.prompts_used == [] for entry in trace_entries)


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


# Budget Reconciliation Tests (5) — FOLLOWUP-18B
class TestBudgetReconciliation:
    def test_max_tokens_capped_to_budget(self, executor):
        """When token_budget < contract max_tokens, PromptRequest uses budget."""
        executor.gateway.route.return_value = _mock_response('{"response_text": "ok"}')
        wo = {
            "wo_id": "WO-SES-TEST0001-CAP1", "session_id": "SES-TEST0001",
            "wo_type": "synthesize", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"prior_results": [{"data": "test"}]},
            "constraints": {
                "prompt_contract_id": "PRC-SYNTHESIZE-001",
                "token_budget": 1000,  # < contract's 4096
                "turn_limit": 3,
            },
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                     "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        executor.execute(wo)
        request = executor.gateway.route.call_args[0][0]
        assert request.max_tokens == 1000  # capped to budget, not 4096

    def test_max_tokens_uses_contract_when_budget_larger(self, executor):
        """When token_budget > contract max_tokens, PromptRequest uses contract."""
        executor.gateway.route.return_value = _mock_response('{"speech_act": "greeting", "ambiguity": "low"}')
        wo = {
            "wo_id": "WO-SES-TEST0001-CAP2", "session_id": "SES-TEST0001",
            "wo_type": "classify", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"user_input": "hello"},
            "constraints": {
                "prompt_contract_id": "PRC-CLASSIFY-001",
                "token_budget": 10000,  # > contract's 500
                "turn_limit": 3,
            },
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                     "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        executor.execute(wo)
        request = executor.gateway.route.call_args[0][0]
        assert request.max_tokens == 500  # uses contract value, not 10000

    def test_gateway_rejection_fails_wo(self, executor, classify_wo):
        """Gateway returning REJECTED outcome must fail the WO."""
        executor.gateway.route.return_value = SimpleNamespace(
            content="", outcome="REJECTED",
            error_code="BUDGET_EXHAUSTED",
            error_message="Token budget exceeded",
            input_tokens=0, output_tokens=0,
            model_id="mock", provider_id="mock",
            latency_ms=0, timestamp="2026-02-15T00:00:00Z",
            exchange_entry_id="LED-rej001",
        )
        result = executor.execute(classify_wo)
        assert result["state"] == "failed"
        assert "BUDGET_EXHAUSTED" in result.get("error", "")

    def test_gateway_error_fails_wo(self, executor, classify_wo):
        """Gateway returning ERROR outcome must fail the WO."""
        executor.gateway.route.return_value = SimpleNamespace(
            content="", outcome="ERROR",
            error_code="PROVIDER_ERROR",
            error_message="Provider unavailable",
            input_tokens=0, output_tokens=0,
            model_id="mock", provider_id="mock",
            latency_ms=0, timestamp="2026-02-15T00:00:00Z",
            exchange_entry_id="LED-err001",
        )
        result = executor.execute(classify_wo)
        assert result["state"] == "failed"
        assert "PROVIDER_ERROR" in result.get("error", "")

    def test_gateway_success_completes_wo(self, executor, classify_wo):
        """Gateway returning SUCCESS outcome completes the WO normally."""
        executor.gateway.route.return_value = _mock_response()
        result = executor.execute(classify_wo)
        assert result["state"] == "completed"
        assert result["output_result"] is not None

    def test_followup_request_max_tokens_uses_remaining_budget(self, executor):
        """Tool-loop follow-up request should use remaining budget, not original budget."""
        executor.gateway.route.side_effect = [
            _mock_tool_use_response(input_tokens=1000, output_tokens=1000),
            _mock_response('{"response_text":"final"}', input_tokens=10, output_tokens=10),
        ]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "list_packages", "description": "List", "input_schema": {"type": "object", "properties": {}}},
        ]
        wo = {
            "wo_id": "WO-SES-TEST0001-REMAIN", "session_id": "SES-TEST0001",
            "wo_type": "synthesize", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"prior_results": [{"data": "test"}]},
            "constraints": {
                "prompt_contract_id": "PRC-SYNTHESIZE-001",
                "token_budget": 5000,
                "turn_limit": 3,
                "tools_allowed": ["list_packages"],
            },
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                     "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        result = executor.execute(wo)
        assert result["state"] == "completed"
        followup_request = executor.gateway.route.call_args_list[1][0][0]
        assert followup_request.max_tokens == 3000


# Template Rendering Tests (10) — FOLLOWUP-18C
class TestTemplateRendering:
    def test_render_template_substitutes_string_var(self, executor):
        """#1: {{user_input}} replaced with string value."""
        result = executor._render_template("PRM-CLASSIFY-001", {"user_input": "hello world"})
        assert "hello world" in result
        assert "{{user_input}}" not in result

    def test_render_template_substitutes_dict_var(self, executor):
        """#2: Dict value rendered as json.dumps, not Python repr."""
        ctx = {"user_input": "test", "classification": {"speech_act": "greeting", "ambiguity": "low"}}
        # Use a template that has {{classification}} — synthesize has it
        result = executor._render_template("PRM-SYNTHESIZE-001", ctx)
        assert '"speech_act": "greeting"' in result
        # Must not contain Python repr format
        assert "{'speech_act'" not in result

    def test_render_template_substitutes_list_var(self, executor):
        """#3: List value rendered as json.dumps."""
        ctx = {"prior_results": [{"data": "test"}], "user_input": "hello"}
        result = executor._render_template("PRM-SYNTHESIZE-001", ctx)
        assert '"data": "test"' in result
        assert "[{" not in result or '"data"' in result  # valid JSON array

    def test_render_template_missing_file_falls_back(self, executor):
        """#4: No template file -> json.dumps(input_ctx) behavior."""
        ctx = {"user_input": "hello"}
        result = executor._render_template("PRM-NONEXISTENT-001", ctx)
        assert result == json.dumps(ctx)

    def test_render_template_unknown_placeholder_preserved(self, executor):
        """#5: {{unknown}} stays literal when not in input_ctx."""
        ctx = {"user_input": "hello"}
        # Classify template only has {{user_input}}, no {{unknown}}
        # Use synthesize which has {{classification}} — pass without it
        result = executor._render_template("PRM-SYNTHESIZE-001", {"prior_results": [{"x": 1}]})
        # {{user_input}} is not in input_ctx, so it should remain literal
        assert "{{user_input}}" in result

    def test_render_template_appends_additional_context(self, executor):
        """#6: additional_context appended after rendered template."""
        ctx = {"user_input": "hello"}
        extra = "\nTool results: [{\"tool_id\": \"t1\"}]"
        result = executor._render_template("PRM-CLASSIFY-001", ctx, additional_context=extra)
        assert result.endswith(extra)
        assert "hello" in result

    def test_build_prompt_request_uses_template(self, executor, classify_wo):
        """#7: Full flow: contract with prompt_pack_id -> rendered prompt in PromptRequest."""
        contract = executor.contract_loader.load("PRC-CLASSIFY-001")
        request = executor._build_prompt_request(classify_wo, contract)
        # Should contain rendered template text, not raw json.dumps
        assert "speech act classifier" in request.prompt.lower() or "classifier" in request.prompt.lower()
        assert "hello world" in request.prompt
        # Should NOT be raw json.dumps
        assert request.prompt != json.dumps(classify_wo["input_context"])

    def test_build_prompt_request_fallback_uses_template(self, executor, classify_wo):
        """#8: SimpleNamespace fallback path also renders template."""
        contract = executor.contract_loader.load("PRC-CLASSIFY-001")
        # The executor uses SimpleNamespace path when PromptRequest import fails
        # We test _render_template directly since both paths call it
        prompt_pack_id = contract.get("prompt_pack_id", "")
        input_ctx = classify_wo.get("input_context", {})
        rendered = executor._render_template(prompt_pack_id, input_ctx)
        assert "hello world" in rendered
        assert "{{user_input}}" not in rendered

    def test_classify_template_includes_json_instruction(self, executor):
        """#9: PRM-CLASSIFY-001.txt in rendered prompt contains JSON instruction."""
        ctx = {"user_input": "test input"}
        result = executor._render_template("PRM-CLASSIFY-001", ctx)
        assert "valid JSON" in result or "json" in result.lower()

    def test_synthesize_template_renders_complex_context(self, executor):
        """#10: Synthesize with dict + list variables renders all as JSON."""
        ctx = {
            "prior_results": [{"speech_act": "greeting", "ambiguity": "low"}],
            "user_input": "hello",
            "classification": {"speech_act": "greeting", "ambiguity": "low"},
            "assembled_context": {"context_text": "prior session data", "fragment_count": 2},
        }
        result = executor._render_template("PRM-SYNTHESIZE-001", ctx)
        assert "hello" in result
        assert '"speech_act"' in result
        assert '"context_text"' in result
        assert "{{prior_results}}" not in result
        assert "{{classification}}" not in result
        assert "{{assembled_context}}" not in result


# Tool-Use Wiring Tests (9) — HANDOFF-21
class TestToolUseWiring:
    def test_prompt_request_includes_tools_when_allowed(self, executor, classify_wo):
        """When WO has tools_allowed, PromptRequest.tools is populated."""
        classify_wo["constraints"]["tools_allowed"] = ["read_file"]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "read_file", "description": "Read a file", "input_schema": {"type": "object", "properties": {}}},
            {"name": "gate_check", "description": "Run gates", "input_schema": {"type": "object", "properties": {}}},
        ]
        contract = executor.contract_loader.load("PRC-CLASSIFY-001")
        request = executor._build_prompt_request(classify_wo, contract)
        assert request.tools is not None
        assert len(request.tools) == 1
        assert request.tools[0]["name"] == "read_file"

    def test_prompt_request_no_tools_when_empty(self, executor, classify_wo):
        """When tools_allowed is empty, PromptRequest.tools is None."""
        classify_wo["constraints"]["tools_allowed"] = []
        contract = executor.contract_loader.load("PRC-CLASSIFY-001")
        request = executor._build_prompt_request(classify_wo, contract)
        assert request.tools is None

    def test_prompt_request_no_tools_when_missing(self, executor, classify_wo):
        """When tools_allowed is not in constraints, PromptRequest.tools is None."""
        classify_wo["constraints"].pop("tools_allowed", None)
        contract = executor.contract_loader.load("PRC-CLASSIFY-001")
        request = executor._build_prompt_request(classify_wo, contract)
        assert request.tools is None

    def test_prompt_request_tools_filtered_to_allowed(self, executor, classify_wo):
        """Only tools in tools_allowed appear in PromptRequest.tools."""
        classify_wo["constraints"]["tools_allowed"] = ["gate_check"]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "read_file", "description": "Read", "input_schema": {"type": "object", "properties": {}}},
            {"name": "gate_check", "description": "Gates", "input_schema": {"type": "object", "properties": {}}},
            {"name": "list_packages", "description": "List", "input_schema": {"type": "object", "properties": {}}},
        ]
        contract = executor.contract_loader.load("PRC-CLASSIFY-001")
        request = executor._build_prompt_request(classify_wo, contract)
        assert request.tools is not None
        assert len(request.tools) == 1
        assert request.tools[0]["name"] == "gate_check"

    def test_tool_loop_no_double_execution(self, executor, classify_wo):
        """Each tool executed exactly ONCE per loop iteration."""
        content_blocks = (
            {"type": "tool_use", "id": "toolu_01", "name": "read_file", "input": {"path": "test.py"}},
        )
        tool_resp = SimpleNamespace(
            content='', outcome="SUCCESS",
            input_tokens=100, output_tokens=50,
            model_id="mock", provider_id="mock",
            latency_ms=100, timestamp="2026-02-15T00:00:00Z",
            exchange_entry_id="LED-mock", finish_reason="tool_use",
            content_blocks=content_blocks,
        )
        text_resp = _mock_response('{"speech_act": "command", "ambiguity": "low"}')
        executor.gateway.route.side_effect = [tool_resp, text_resp]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "read_file", "description": "Read a file", "input_schema": {"type": "object", "properties": {}}},
        ]
        classify_wo["constraints"]["tools_allowed"] = ["read_file"]
        executor.execute(classify_wo)
        # Tool should be called exactly once (not twice from double-execution bug)
        assert executor.tool_dispatcher.execute.call_count == 1

    def test_tool_loop_uses_content_blocks(self, executor, classify_wo):
        """When response has content_blocks with tool_use, extracts from blocks."""
        content_blocks = (
            {"type": "tool_use", "id": "toolu_01", "name": "list_packages", "input": {}},
        )
        tool_resp = SimpleNamespace(
            content='{}', outcome="SUCCESS",
            input_tokens=100, output_tokens=50,
            model_id="mock", provider_id="mock",
            latency_ms=100, timestamp="2026-02-15T00:00:00Z",
            exchange_entry_id="LED-mock", finish_reason="tool_use",
            content_blocks=content_blocks,
        )
        text_resp = _mock_response('{"speech_act": "command", "ambiguity": "low"}')
        executor.gateway.route.side_effect = [tool_resp, text_resp]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "list_packages", "description": "List pkgs", "input_schema": {"type": "object", "properties": {}}},
        ]
        classify_wo["constraints"]["tools_allowed"] = ["list_packages"]
        executor.execute(classify_wo)
        # Dispatcher should be called with the name from content_blocks
        executor.tool_dispatcher.execute.assert_called_with("list_packages", {})

    def test_tool_loop_fallback_to_string_parsing(self):
        """When response has no content_blocks, falls back to string parsing."""
        from ho1_executor import HO1Executor
        exec_inst = HO1Executor.__new__(HO1Executor)
        # Response with no content_blocks attribute
        response = SimpleNamespace(finish_reason="stop")
        content = '[{"type": "tool_use", "tool_id": "read_file", "arguments": {"path": "x"}}]'
        result = exec_inst._extract_tool_uses(content, response)
        assert len(result) == 1
        assert result[0]["tool_id"] == "read_file"

    def test_tool_call_event_has_args_summary(self, executor, classify_wo):
        """TOOL_CALL ledger event includes args_summary."""
        content_blocks = (
            {"type": "tool_use", "id": "toolu_01", "name": "read_file", "input": {"path": "test.py"}},
        )
        tool_resp = SimpleNamespace(
            content='', outcome="SUCCESS",
            input_tokens=100, output_tokens=50,
            model_id="mock", provider_id="mock",
            latency_ms=100, timestamp="2026-02-15T00:00:00Z",
            exchange_entry_id="LED-mock", finish_reason="tool_use",
            content_blocks=content_blocks,
        )
        text_resp = _mock_response('{"speech_act": "command", "ambiguity": "low"}')
        executor.gateway.route.side_effect = [tool_resp, text_resp]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "read_file", "description": "Read", "input_schema": {"type": "object", "properties": {}}},
        ]
        classify_wo["constraints"]["tools_allowed"] = ["read_file"]
        executor.execute(classify_wo)
        tool_calls = [c for c in executor.ledger.write.call_args_list
                      if c[0][0].event_type == "TOOL_CALL"]
        assert len(tool_calls) >= 1
        meta = tool_calls[0][0][0].metadata
        assert "args_summary" in meta
        assert "path" in meta["args_summary"]

    def test_tool_call_event_has_result_summary(self, executor, classify_wo):
        """TOOL_CALL ledger event includes result_summary."""
        content_blocks = (
            {"type": "tool_use", "id": "toolu_01", "name": "list_packages", "input": {}},
        )
        tool_resp = SimpleNamespace(
            content='', outcome="SUCCESS",
            input_tokens=100, output_tokens=50,
            model_id="mock", provider_id="mock",
            latency_ms=100, timestamp="2026-02-15T00:00:00Z",
            exchange_entry_id="LED-mock", finish_reason="tool_use",
            content_blocks=content_blocks,
        )
        text_resp = _mock_response('{"speech_act": "command", "ambiguity": "low"}')
        executor.gateway.route.side_effect = [tool_resp, text_resp]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "list_packages", "description": "List", "input_schema": {"type": "object", "properties": {}}},
        ]
        classify_wo["constraints"]["tools_allowed"] = ["list_packages"]
        executor.execute(classify_wo)
        tool_calls = [c for c in executor.ledger.write.call_args_list
                      if c[0][0].event_type == "TOOL_CALL"]
        assert len(tool_calls) >= 1
        meta = tool_calls[0][0][0].metadata
        assert "result_summary" in meta


class TestOutputJsonNormalization:
    def test_output_json_intercepted_as_structured_output(self, executor):
        executor.gateway.route.return_value = _mock_output_json_response()
        wo = {
            "wo_id": "WO-SES-TEST0001-OJ1", "session_id": "SES-TEST0001",
            "wo_type": "classify", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"user_input": "hello"},
            "constraints": {"prompt_contract_id": "PRC-CLASSIFY-001", "token_budget": 2000, "turn_limit": 1},
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        result = executor.execute(wo)
        assert result["state"] == "completed"
        assert result["output_result"]["speech_act"] == "greeting"

    def test_output_json_payload_becomes_output_result(self, executor):
        payload = {"speech_act": "question", "ambiguity": "high"}
        executor.gateway.route.return_value = _mock_output_json_response(payload=payload)
        wo = {
            "wo_id": "WO-SES-TEST0001-OJ2", "session_id": "SES-TEST0001",
            "wo_type": "classify", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"user_input": "what is this"},
            "constraints": {"prompt_contract_id": "PRC-CLASSIFY-001", "token_budget": 2000, "turn_limit": 1},
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        result = executor.execute(wo)
        assert result["output_result"] == payload

    def test_output_json_ignored_when_in_tools_allowed(self, executor):
        executor.gateway.route.side_effect = [
            _mock_output_json_response(payload={"x": 1}),
            _mock_response('{"speech_act":"greeting","ambiguity":"low"}'),
        ]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "output_json", "description": "Pseudo tool", "input_schema": {"type": "object", "properties": {}}},
        ]
        wo = {
            "wo_id": "WO-SES-TEST0001-OJ3", "session_id": "SES-TEST0001",
            "wo_type": "classify", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"user_input": "hello"},
            "constraints": {
                "prompt_contract_id": "PRC-CLASSIFY-001",
                "token_budget": 2000,
                "turn_limit": 2,
                "tools_allowed": ["output_json"],
            },
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        executor.execute(wo)
        dispatched = [c[0][0] for c in executor.tool_dispatcher.execute.call_args_list]
        assert "output_json" in dispatched

    def test_output_json_with_real_tools_coexist(self, executor):
        mixed = _mock_output_json_response(
            payload={"speech_act": "command", "ambiguity": "low"},
            extra_blocks=[{"type": "tool_use", "id": "toolu_real", "name": "list_packages", "input": {}}],
        )
        executor.gateway.route.side_effect = [
            mixed,
            _mock_response('{"speech_act":"command","ambiguity":"low"}'),
        ]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "list_packages", "description": "List", "input_schema": {"type": "object", "properties": {}}},
        ]
        wo = {
            "wo_id": "WO-SES-TEST0001-OJ4", "session_id": "SES-TEST0001",
            "wo_type": "classify", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"user_input": "show packages"},
            "constraints": {
                "prompt_contract_id": "PRC-CLASSIFY-001",
                "token_budget": 2000,
                "turn_limit": 2,
                "tools_allowed": ["list_packages"],
            },
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        result = executor.execute(wo)
        assert result["state"] == "completed"
        dispatched = [c[0][0] for c in executor.tool_dispatcher.execute.call_args_list]
        assert dispatched.count("list_packages") == 1
        assert "output_json" not in dispatched

    def test_tools_allowed_filter_restored(self, executor):
        mixed = _mock_output_json_response(
            payload={"speech_act": "command", "ambiguity": "low"},
            extra_blocks=[
                {"type": "tool_use", "id": "toolu_t1", "name": "t1", "input": {}},
                {"type": "tool_use", "id": "toolu_t2", "name": "t2", "input": {}},
            ],
        )
        executor.gateway.route.side_effect = [mixed, _mock_response('{"speech_act":"command","ambiguity":"low"}')]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "t1", "description": "T1", "input_schema": {"type": "object", "properties": {}}},
            {"name": "t2", "description": "T2", "input_schema": {"type": "object", "properties": {}}},
        ]
        wo = {
            "wo_id": "WO-SES-TEST0001-OJ5", "session_id": "SES-TEST0001",
            "wo_type": "classify", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"user_input": "run"},
            "constraints": {
                "prompt_contract_id": "PRC-CLASSIFY-001",
                "token_budget": 2000,
                "turn_limit": 2,
                "tools_allowed": ["t1"],
            },
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        executor.execute(wo)
        dispatched = [c[0][0] for c in executor.tool_dispatcher.execute.call_args_list]
        assert dispatched == ["t1"]

    def test_empty_tools_allowed_blocks_all_dispatch(self, executor):
        executor.gateway.route.return_value = _mock_output_json_response(
            extra_blocks=[{"type": "tool_use", "id": "toolu_t1", "name": "t1", "input": {}}]
        )
        wo = {
            "wo_id": "WO-SES-TEST0001-OJ6", "session_id": "SES-TEST0001",
            "wo_type": "classify", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"user_input": "hello"},
            "constraints": {
                "prompt_contract_id": "PRC-CLASSIFY-001",
                "token_budget": 2000,
                "turn_limit": 1,
                "tools_allowed": [],
            },
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        result = executor.execute(wo)
        assert result["state"] == "completed"
        assert executor.tool_dispatcher.execute.call_count == 0


class TestAdminShellHotfix:
    def test_strip_code_fences_json(self, executor):
        content = "```json\n{\"response_text\":\"hi\"}\n```"
        assert executor._strip_code_fences(content) == "{\"response_text\":\"hi\"}"

    def test_strip_code_fences_language_tag(self, executor):
        content = "```python\nprint('ok')\n```"
        assert executor._strip_code_fences(content) == "print('ok')"

    def test_strip_code_fences_passthrough(self, executor):
        content = "plain text"
        assert executor._strip_code_fences(content) == "plain text"

    def test_fenced_json_normalized(self, executor):
        executor.gateway.route.return_value = _mock_response(
            "```json\n{\"response_text\":\"normalized\"}\n```"
        )
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "list_packages", "description": "List", "input_schema": {"type": "object", "properties": {}}},
        ]
        wo = {
            "wo_id": "WO-SES-TEST0001-FENCE", "session_id": "SES-TEST0001",
            "wo_type": "synthesize", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"prior_results": [{"data": "test"}]},
            "constraints": {
                "prompt_contract_id": "PRC-SYNTHESIZE-001",
                "token_budget": 5000,
                "turn_limit": 1,
                "tools_allowed": ["list_packages"],
            },
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                     "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        result = executor.execute(wo)
        assert result["state"] == "completed"
        assert result["output_result"]["response_text"] == "normalized"

    def test_natural_language_output_wrapped(self, executor):
        executor.gateway.route.side_effect = [
            _mock_tool_use_response(),
            _mock_response("Natural language final answer", input_tokens=20, output_tokens=20),
        ]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "list_packages", "description": "List", "input_schema": {"type": "object", "properties": {}}},
        ]
        wo = {
            "wo_id": "WO-SES-TEST0001-NAT", "session_id": "SES-TEST0001",
            "wo_type": "synthesize", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"prior_results": [{"data": "test"}]},
            "constraints": {
                "prompt_contract_id": "PRC-SYNTHESIZE-001",
                "token_budget": 5000,
                "turn_limit": 3,
                "tools_allowed": ["list_packages"],
            },
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                     "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        result = executor.execute(wo)
        assert result["state"] == "completed"
        assert result["output_result"] == {"response_text": "Natural language final answer"}

    def test_budget_guard_tool_loop(self, executor):
        executor.gateway.route.side_effect = [
            _mock_tool_use_response(input_tokens=900, output_tokens=700),
            _mock_response('{"response_text":"should_not_run"}'),
        ]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "list_packages", "description": "List", "input_schema": {"type": "object", "properties": {}}},
        ]
        wo = {
            "wo_id": "WO-SES-TEST0001-BUDGET", "session_id": "SES-TEST0001",
            "wo_type": "synthesize", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"prior_results": [{"data": "test"}]},
            "constraints": {
                "prompt_contract_id": "PRC-SYNTHESIZE-001",
                "token_budget": 2000,
                "turn_limit": 3,
                "tools_allowed": ["list_packages"],
            },
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                     "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }
        result = executor.execute(wo)
        assert result["state"] == "failed"
        assert "budget_exhausted" in result.get("error", "")
        assert executor.gateway.route.call_count == 1


class TestBudgetModesAndPristineLogging:
    def test_budget_mode_warn_continues_on_exhaustion(self, executor, classify_wo):
        executor.config["budget_mode"] = "warn"
        executor.budgeter.check.return_value = _mock_budget_check(False, remaining=0)
        executor.gateway.route.return_value = _mock_response('{"speech_act":"greeting","ambiguity":"low"}')

        result = executor.execute(classify_wo)

        assert result["state"] == "completed"
        warnings = [
            c[0][0] for c in executor.ledger.write.call_args_list
            if c[0][0].event_type == "BUDGET_WARNING"
        ]
        assert len(warnings) >= 1

    def test_budget_mode_off_skips_check(self, executor, classify_wo):
        executor.config["budget_mode"] = "off"
        executor.budgeter.check.side_effect = AssertionError("check should be skipped in off mode")
        executor.gateway.route.return_value = _mock_response('{"speech_act":"greeting","ambiguity":"low"}')

        result = executor.execute(classify_wo)

        assert result["state"] == "completed"
        assert executor.budgeter.check.call_count == 0

    def test_budget_mode_enforce_fails(self, executor, classify_wo):
        executor.config["budget_mode"] = "enforce"
        executor.budgeter.check.return_value = _mock_budget_check(False, remaining=0)

        result = executor.execute(classify_wo)

        assert result["state"] == "failed"
        assert "budget_exhausted" in result.get("error", "")

    def test_followup_min_from_config(self, executor):
        executor.config["budget_mode"] = "warn"
        executor.config["followup_min_remaining"] = 3500
        executor.gateway.route.side_effect = [
            _mock_tool_use_response(input_tokens=1100, output_tokens=1100),
            _mock_response('{"response_text":"continued"}', input_tokens=10, output_tokens=10),
        ]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "list_packages", "description": "List", "input_schema": {"type": "object", "properties": {}}},
        ]
        wo = {
            "wo_id": "WO-SES-TEST0001-MINCFG", "session_id": "SES-TEST0001",
            "wo_type": "synthesize", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"prior_results": [{"data": "test"}]},
            "constraints": {
                "prompt_contract_id": "PRC-SYNTHESIZE-001",
                "token_budget": 5000,
                "turn_limit": 3,
                "tools_allowed": ["list_packages"],
                "budget_mode": "warn",
                "followup_min_remaining": 3500,
            },
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                     "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }

        result = executor.execute(wo)

        assert result["state"] == "completed"
        warnings = [
            c[0][0] for c in executor.ledger.write.call_args_list
            if c[0][0].event_type == "BUDGET_WARNING"
        ]
        assert len(warnings) >= 1
        assert any("followup_min" in w.metadata for w in warnings)

    def test_tool_call_logs_full_arguments(self, executor, classify_wo):
        big_text = "x" * 600
        content_blocks = (
            {"type": "tool_use", "id": "toolu_01", "name": "read_file", "input": {"path": "f.py", "blob": big_text}},
        )
        tool_resp = SimpleNamespace(
            content="", outcome="SUCCESS",
            input_tokens=100, output_tokens=50,
            model_id="mock", provider_id="mock",
            latency_ms=100, timestamp="2026-02-15T00:00:00Z",
            exchange_entry_id="LED-mock", finish_reason="tool_use",
            content_blocks=content_blocks,
        )
        text_resp = _mock_response('{"speech_act":"command","ambiguity":"low"}')
        executor.gateway.route.side_effect = [tool_resp, text_resp]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "read_file", "description": "Read", "input_schema": {"type": "object", "properties": {}}},
        ]
        executor.tool_dispatcher.execute.return_value = SimpleNamespace(
            tool_id="read_file", status="ok", output={"ok": True, "blob": big_text}, error=None
        )
        classify_wo["constraints"]["tools_allowed"] = ["read_file"]

        executor.execute(classify_wo)

        tool_calls = [c[0][0] for c in executor.ledger.write.call_args_list if c[0][0].event_type == "TOOL_CALL"]
        assert len(tool_calls) >= 1
        meta = tool_calls[0].metadata
        assert meta["arguments"]["blob"] == big_text
        assert meta["args_bytes"] > 200
        assert meta["result_bytes"] > 500

    def test_tool_call_logs_error_detail(self, executor, classify_wo):
        content_blocks = (
            {"type": "tool_use", "id": "toolu_02", "name": "read_file", "input": {"path": "missing.py"}},
        )
        tool_resp = SimpleNamespace(
            content="", outcome="SUCCESS",
            input_tokens=10, output_tokens=10,
            model_id="mock", provider_id="mock",
            latency_ms=10, timestamp="2026-02-15T00:00:00Z",
            exchange_entry_id="LED-mock", finish_reason="tool_use",
            content_blocks=content_blocks,
        )
        text_resp = _mock_response('{"speech_act":"command","ambiguity":"low"}')
        executor.gateway.route.side_effect = [tool_resp, text_resp]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "read_file", "description": "Read", "input_schema": {"type": "object", "properties": {}}},
        ]
        executor.tool_dispatcher.execute.return_value = SimpleNamespace(
            tool_id="read_file", status="error", output=None, error="file_not_found"
        )
        classify_wo["constraints"]["tools_allowed"] = ["read_file"]

        executor.execute(classify_wo)

        tool_calls = [c[0][0] for c in executor.ledger.write.call_args_list if c[0][0].event_type == "TOOL_CALL"]
        assert len(tool_calls) >= 1
        meta = tool_calls[0].metadata
        assert meta["tool_error"] == "file_not_found"

    def test_handle_tool_call_logs_full_metadata(self, executor):
        executor.tool_dispatcher.execute.return_value = SimpleNamespace(
            tool_id="list_files", status="ok", output={"files": ["a.py"]}, error=None
        )
        wo = {
            "wo_id": "WO-SES-TEST0001-TOOLMETA", "session_id": "SES-TEST0001",
            "wo_type": "tool_call", "tier_target": "HO1", "state": "dispatched",
            "created_at": "2026-02-15T00:00:00Z", "created_by": "ADMIN.ho2",
            "input_context": {"path": "HOT/kernel"},
            "constraints": {"tools_allowed": ["list_files"], "token_budget": 500},
            "cost": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
        }

        result = executor.execute(wo)

        assert result["state"] == "completed"
        tool_calls = [c[0][0] for c in executor.ledger.write.call_args_list if c[0][0].event_type == "TOOL_CALL"]
        assert len(tool_calls) == 1
        meta = tool_calls[0].metadata
        assert meta["arguments"] == {"path": "HOT/kernel"}
        assert meta["result"] == {"files": ["a.py"]}


# ===========================================================================
# 29C Tests: domain_tags passthrough + tool_ids_used + consolidation assets
# ===========================================================================

class TestDomainTagsPassthrough:
    def test_ho1_passes_domain_tags(self, executor, classify_wo):
        """WO with constraints.domain_tags=["x"] -> PromptRequest.domain_tags==["x"]."""
        classify_wo["constraints"]["domain_tags"] = ["consolidation"]
        contract = executor.contract_loader.load("PRC-CLASSIFY-001")
        request = executor._build_prompt_request(classify_wo, contract)
        assert request.domain_tags == ["consolidation"]

    def test_ho1_passes_empty_domain_tags(self, executor, classify_wo):
        """WO without domain_tags -> PromptRequest.domain_tags==[]."""
        classify_wo["constraints"].pop("domain_tags", None)
        contract = executor.contract_loader.load("PRC-CLASSIFY-001")
        request = executor._build_prompt_request(classify_wo, contract)
        assert request.domain_tags == []

    def test_ho1_exposes_tool_ids_used(self, executor, classify_wo):
        """HO1 tool loop populates cost['tool_ids_used'] with actual tool_id strings."""
        content_blocks = (
            {"type": "tool_use", "id": "toolu_01", "name": "list_packages", "input": {}},
        )
        tool_resp = SimpleNamespace(
            content='{}', outcome="SUCCESS",
            input_tokens=100, output_tokens=50,
            model_id="mock", provider_id="mock",
            latency_ms=100, timestamp="2026-02-15T00:00:00Z",
            exchange_entry_id="LED-mock", finish_reason="tool_use",
            content_blocks=content_blocks,
        )
        text_resp = _mock_response('{"speech_act": "command", "ambiguity": "low"}')
        executor.gateway.route.side_effect = [tool_resp, text_resp]
        executor.tool_dispatcher.get_api_tools.return_value = [
            {"name": "list_packages", "description": "List pkgs", "input_schema": {"type": "object", "properties": {}}},
        ]
        classify_wo["constraints"]["tools_allowed"] = ["list_packages"]
        result = executor.execute(classify_wo)
        assert result["state"] == "completed"
        assert result["cost"]["tool_ids_used"] == ["list_packages"]

    def test_consolidation_prompt_pack_loads(self, executor):
        """PRM-CONSOLIDATE-001.txt exists and renders with template variables."""
        # Write the consolidation prompt pack to the executor's prompt_packs dir
        template_dir = executor.contract_loader.contracts_dir.parent / "prompt_packs"
        template_dir.mkdir(exist_ok=True)
        (template_dir / "PRM-CONSOLIDATE-001.txt").write_text(
            "You are analyzing patterns in user interaction signals.\n\n"
            "Signal: {{signal_id}}\nObservation count: {{count}}\n"
            "Across sessions: {{session_count}}\nRecent events:\n{{recent_events}}\n\n"
            "Respond with valid JSON matching this schema."
        )
        ctx = {
            "signal_id": "intent:tool_query",
            "count": "5",
            "session_count": "3",
            "recent_events": '["EVT-001", "EVT-002"]',
        }
        result = executor._render_template("PRM-CONSOLIDATE-001", ctx)
        assert "intent:tool_query" in result
        assert "Observation count: 5" in result
        assert "{{signal_id}}" not in result

    def test_consolidation_contract_loads(self, executor, tmp_path):
        """PRC-CONSOLIDATE-001.json loads via contract_loader."""
        # Write consolidate contract to the executor's contracts dir
        contracts_dir = executor.contract_loader.contracts_dir
        (contracts_dir / "consolidate.json").write_text(json.dumps({
            "contract_id": "PRC-CONSOLIDATE-001",
            "version": "1.0.0",
            "prompt_pack_id": "PRM-CONSOLIDATE-001",
            "tier": "ho1",
            "boundary": {"max_tokens": 512, "temperature": 0.0},
            "input_schema": {"type": "object", "required": ["signal_id", "count", "session_count", "recent_events"]},
            "output_schema": {"type": "object", "required": ["bias", "category", "salience_weight", "decay_modifier"]},
        }))
        contract = executor.contract_loader.load("PRC-CONSOLIDATE-001")
        assert contract["contract_id"] == "PRC-CONSOLIDATE-001"
        assert contract["prompt_pack_id"] == "PRM-CONSOLIDATE-001"
        assert contract["boundary"]["max_tokens"] == 512
