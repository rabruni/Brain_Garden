"""Tests for Session Host V2 — thin adapter with degradation."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add package kernel to path
_pkg = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_pkg / "HOT" / "kernel"))

# Add PKG-KERNEL-001 for LedgerClient
_staging = _pkg.parent
_kernel = _staging / "PKG-KERNEL-001" / "HOT" / "kernel"
if _kernel.exists():
    sys.path.insert(0, str(_kernel))
    sys.path.insert(0, str(_kernel.parent))

# Add PKG-LLM-GATEWAY-001 for PromptRequest
_pr = _staging / "PKG-LLM-GATEWAY-001" / "HOT" / "kernel"
if _pr.exists():
    sys.path.insert(0, str(_pr))

# Add PKG-LLM-GATEWAY-001 for fallback
_gw = _staging / "PKG-LLM-GATEWAY-001" / "HOT" / "kernel"
if _gw.exists():
    sys.path.insert(0, str(_gw))

from session_host_v2 import SessionHostV2, TurnResult, AgentConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


@pytest.fixture
def host(mock_ho2, mock_gateway, agent_config, mock_ledger):
    return SessionHostV2(mock_ho2, mock_gateway, agent_config, mock_ledger)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNormalPath:
    def test_process_turn_delegates_to_ho2(self, host, mock_ho2):
        host.start_session()
        host.process_turn("hello")
        mock_ho2.handle_turn.assert_called_once_with("hello")

    def test_process_turn_returns_turn_result(self, host):
        host.start_session()
        result = host.process_turn("hello")
        assert isinstance(result, TurnResult)
        assert result.outcome == "success"
        assert result.response == "Hello from HO2"

    def test_start_session_delegates(self, host, mock_ho2):
        session_id = host.start_session()
        mock_ho2.start_session.assert_called_once()
        assert session_id == "SES-abc12345"

    def test_end_session_delegates(self, host, mock_ho2):
        host.start_session()
        host.end_session()
        mock_ho2.end_session.assert_called_once()


class TestDegradation:
    def test_degradation_on_ho2_exception(self, host, mock_ho2, mock_gateway):
        host.start_session()
        mock_ho2.handle_turn = MagicMock(side_effect=RuntimeError("HO2 crashed"))
        host.process_turn("hello")
        mock_gateway.route.assert_called_once()

    def test_degradation_returns_turn_result(self, host, mock_ho2, mock_gateway):
        host.start_session()
        mock_ho2.handle_turn = MagicMock(side_effect=RuntimeError("HO2 crashed"))
        result = host.process_turn("hello")
        assert isinstance(result, TurnResult)
        assert result.outcome == "degraded"
        assert result.response == "Degraded response"

    def test_degradation_logs_event(self, host, mock_ho2, mock_ledger):
        host.start_session()
        mock_ho2.handle_turn = MagicMock(side_effect=RuntimeError("HO2 crashed"))
        host.process_turn("hello")
        mock_ledger.write.assert_called()
        call_args = mock_ledger.write.call_args
        entry = call_args[0][0]
        assert entry.event_type == "DEGRADATION"


class TestDoubleFailure:
    def test_gateway_also_fails(self, host, mock_ho2, mock_gateway):
        host.start_session()
        mock_ho2.handle_turn = MagicMock(side_effect=RuntimeError("HO2 crashed"))
        mock_gateway.route = MagicMock(side_effect=RuntimeError("Gateway crashed"))
        result = host.process_turn("hello")
        assert isinstance(result, TurnResult)
        assert result.outcome == "error"
        assert "unavailable" in result.response.lower() or "failed" in result.response.lower()


class TestEdgeCases:
    def test_agent_config_passed_through(self, host, agent_config):
        assert host._config == agent_config
        assert host._config.agent_id == "ADMIN"

    def test_turn_result_dataclass(self):
        tr = TurnResult(response="hi", outcome="success")
        assert tr.response == "hi"
        assert tr.outcome == "success"
        assert tr.tool_calls == []
        assert tr.exchange_entry_ids == []

    def test_auto_start_session_on_first_turn(self, host, mock_ho2):
        # Don't call start_session first
        result = host.process_turn("hello")
        mock_ho2.start_session.assert_called_once()
        assert result.outcome == "success"

    def test_end_session_clears_session_id(self, host):
        host.start_session()
        assert host._session_id != ""
        host.end_session()
        assert host._session_id == ""

    def test_degradation_log_failure_non_fatal(self, host, mock_ho2, mock_ledger):
        host.start_session()
        mock_ho2.handle_turn = MagicMock(side_effect=RuntimeError("HO2 crashed"))
        mock_ledger.write = MagicMock(side_effect=Exception("Ledger broken"))
        # Should not raise — degradation log failure is non-fatal
        result = host.process_turn("hello")
        assert result.outcome in ("degraded", "error")
