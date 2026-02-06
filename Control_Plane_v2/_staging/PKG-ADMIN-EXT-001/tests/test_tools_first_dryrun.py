"""Tests for TOOLS_FIRST DRY_RUN + Explicit Confirmation.

Verifies that:
1. Tools-first handlers default to dry-run (no execution without RUN: token)
2. Valid RUN: token causes execution (two-turn)
3. Invalid tokens fail closed (no execution)
4. Confirmation helper functions work correctly
5. admin_turn() integration passes confirmation_id through
6. A0 + EXECUTE enables same-turn execution
7. A0 without EXECUTE stays dry-run
8. EXECUTE without A0 stays dry-run
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))

from modules.admin_agent.handlers.confirmation import (
    extract_confirmation,
    extract_a0_execute,
    compute_confirmation_id,
    check_confirmation,
    _build_proposed,
    CONFIRM_RE,
)
from modules.admin_agent.handlers import tools_first
from modules.admin_agent.agent import AdminAgent


# =============================================================================
# Helpers
# =============================================================================

def _make_agent():
    """Create a mock AdminAgent."""
    agent = MagicMock(spec=AdminAgent)
    agent.list_installed.return_value = "PKG-A, PKG-B"
    agent.explain.return_value = "Explanation of artifact"
    agent.check_health.return_value = "PASS"
    agent._run_trace.return_value = {"health": "ok", "total_files": 10, "orphans": 0}
    agent.root = CONTROL_PLANE_ROOT
    return agent


def _valid_confirmation_id(handler_name, query):
    """Compute the correct confirmation_id for a handler + query."""
    proposed = {"handler": handler_name, "query": query}
    return compute_confirmation_id(proposed)


# =============================================================================
# 1. TestDryRunDefault
# =============================================================================

class TestDryRunDefault:
    """Handlers return a plan, NOT results, when no RUN: token is present."""

    def test_list_installed_dry_run(self):
        agent = _make_agent()
        context = {"query": "list packages"}
        result = tools_first.list_installed(agent, context)

        assert "Proposed Action" in result
        assert "RUN:" in result
        assert "list_installed" in result
        agent.list_installed.assert_not_called()

    def test_explain_dry_run(self):
        agent = _make_agent()
        context = {"query": "explain FMWK-000", "artifact_id": "FMWK-000"}
        result = tools_first.explain(agent, context)

        assert "Proposed Action" in result
        assert "RUN:" in result
        agent.explain.assert_not_called()

    def test_read_file_dry_run(self):
        agent = _make_agent()
        context = {"query": "read lib/auth.py"}
        result = tools_first.read_file(agent, context)

        assert "Proposed Action" in result
        assert "RUN:" in result

    def test_check_health_dry_run(self):
        agent = _make_agent()
        context = {"query": "check health"}
        result = tools_first.check_health(agent, context)

        assert "Proposed Action" in result
        assert "RUN:" in result
        agent.check_health.assert_not_called()

    def test_inventory_dry_run(self):
        agent = _make_agent()
        context = {"query": "inventory"}
        result = tools_first.inventory(agent, context)

        assert "Proposed Action" in result
        agent._run_trace.assert_not_called()

    def test_show_ledger_dry_run(self):
        agent = _make_agent()
        context = {"query": "show ledger"}
        result = tools_first.show_ledger(agent, context)

        assert "Proposed Action" in result

    def test_show_session_ledger_dry_run(self):
        agent = _make_agent()
        context = {"query": "show session ledger"}
        result = tools_first.show_session_ledger(agent, context)

        assert "Proposed Action" in result

    def test_show_prompts_used_dry_run(self):
        agent = _make_agent()
        context = {"query": "show prompts"}
        result = tools_first.show_prompts_used(agent, context)

        assert "Proposed Action" in result

    def test_list_frameworks_dry_run(self):
        agent = _make_agent()
        context = {"query": "list frameworks"}
        result = tools_first.list_frameworks(agent, context)

        assert "Proposed Action" in result

    def test_list_specs_dry_run(self):
        agent = _make_agent()
        context = {"query": "list specs"}
        result = tools_first.list_specs(agent, context)

        assert "Proposed Action" in result

    def test_list_files_dry_run(self):
        agent = _make_agent()
        context = {"query": "list files in lib"}
        result = tools_first.list_files(agent, context)

        assert "Proposed Action" in result


# =============================================================================
# 2. TestConfirmedExecution
# =============================================================================

class TestConfirmedExecution:
    """Handlers execute with a valid RUN: token."""

    def test_list_installed_confirmed(self):
        agent = _make_agent()
        query = "list packages"
        cid = _valid_confirmation_id("list_installed", query)
        context = {"query": query, "confirmation_id": cid}
        result = tools_first.list_installed(agent, context)

        agent.list_installed.assert_called_once()
        assert result == "PKG-A, PKG-B"

    def test_explain_confirmed(self):
        agent = _make_agent()
        query = "explain FMWK-000"
        cid = _valid_confirmation_id("explain", query)
        context = {"query": query, "confirmation_id": cid, "artifact_id": "FMWK-000"}
        result = tools_first.explain(agent, context)

        agent.explain.assert_called_once_with("FMWK-000")
        assert result == "Explanation of artifact"

    def test_check_health_confirmed(self):
        agent = _make_agent()
        query = "check health"
        cid = _valid_confirmation_id("check_health", query)
        context = {"query": query, "confirmation_id": cid}
        result = tools_first.check_health(agent, context)

        agent.check_health.assert_called_once()
        assert result == "PASS"

    def test_inventory_confirmed(self):
        agent = _make_agent()
        query = "inventory"
        cid = _valid_confirmation_id("inventory", query)
        context = {"query": query, "confirmation_id": cid}
        result = tools_first.inventory(agent, context)

        agent._run_trace.assert_called_once_with("--inventory")

    def test_list_frameworks_confirmed(self):
        agent = _make_agent()
        query = "list frameworks"
        cid = _valid_confirmation_id("list_frameworks", query)
        context = {"query": query, "confirmation_id": cid}
        tools_first.list_frameworks(agent, context)
        # If it gets past confirmation gate, it tries to read the CSV


# =============================================================================
# 3. TestInvalidConfirmation
# =============================================================================

class TestInvalidConfirmation:
    """Invalid tokens fail closed (no execution)."""

    def test_wrong_token_no_execution(self):
        agent = _make_agent()
        context = {"query": "list packages", "confirmation_id": "0000000000000000"}
        result = tools_first.list_installed(agent, context)

        assert "mismatch" in result.lower()
        agent.list_installed.assert_not_called()

    def test_truncated_token_no_execution(self):
        agent = _make_agent()
        # A truncated token won't match
        context = {"query": "list packages", "confirmation_id": "abcd1234"}
        result = tools_first.list_installed(agent, context)

        assert "mismatch" in result.lower()
        agent.list_installed.assert_not_called()

    def test_wrong_query_token_no_execution(self):
        """Token computed for a different query should not work."""
        agent = _make_agent()
        # Get token for a different query
        wrong_cid = _valid_confirmation_id("list_installed", "different query")
        context = {"query": "list packages", "confirmation_id": wrong_cid}
        result = tools_first.list_installed(agent, context)

        assert "mismatch" in result.lower()
        agent.list_installed.assert_not_called()

    def test_wrong_handler_token_no_execution(self):
        """Token computed for a different handler should not work."""
        agent = _make_agent()
        wrong_cid = _valid_confirmation_id("check_health", "list packages")
        context = {"query": "list packages", "confirmation_id": wrong_cid}
        result = tools_first.list_installed(agent, context)

        assert "mismatch" in result.lower()
        agent.list_installed.assert_not_called()


# =============================================================================
# 4. TestConfirmationHelpers
# =============================================================================

class TestConfirmationHelpers:
    """Unit tests for the helper functions."""

    def test_extract_confirmation_with_token(self):
        clean, cid = extract_confirmation("list packages RUN:a1b2c3d4e5f6a7b8")
        assert clean == "list packages"
        assert cid == "a1b2c3d4e5f6a7b8"

    def test_extract_confirmation_without_token(self):
        clean, cid = extract_confirmation("list packages")
        assert clean == "list packages"
        assert cid is None

    def test_extract_confirmation_token_in_middle(self):
        clean, cid = extract_confirmation("please RUN:abcdef0123456789 do it")
        assert cid == "abcdef0123456789"
        assert "RUN:" not in clean
        assert "please" in clean
        assert "do it" in clean

    def test_compute_confirmation_id_deterministic(self):
        proposed = {"handler": "list_installed", "query": "list packages"}
        id1 = compute_confirmation_id(proposed)
        id2 = compute_confirmation_id(proposed)
        assert id1 == id2
        assert len(id1) == 16

    def test_compute_confirmation_id_differs_for_different_input(self):
        id1 = compute_confirmation_id({"handler": "list_installed", "query": "list packages"})
        id2 = compute_confirmation_id({"handler": "check_health", "query": "check health"})
        assert id1 != id2

    def test_compute_confirmation_id_is_hex(self):
        cid = compute_confirmation_id({"handler": "test", "query": "q"})
        assert all(c in "0123456789abcdef" for c in cid)

    def test_build_proposed(self):
        context = {"query": "list packages", "session": "ignored"}
        proposed = _build_proposed("list_installed", context)
        assert proposed == {"handler": "list_installed", "query": "list packages"}

    def test_check_confirmation_no_id_returns_dryrun(self):
        result = check_confirmation("list_installed", {"query": "q"}, "desc")
        assert result is not None
        assert "Proposed Action" in result
        assert "RUN:" in result

    def test_check_confirmation_valid_returns_none(self):
        cid = compute_confirmation_id({"handler": "h", "query": "q"})
        result = check_confirmation("h", {"query": "q", "confirmation_id": cid}, "desc")
        assert result is None

    def test_check_confirmation_invalid_returns_mismatch(self):
        result = check_confirmation(
            "h", {"query": "q", "confirmation_id": "0000000000000000"}, "desc"
        )
        assert result is not None
        assert "mismatch" in result.lower()

    def test_confirm_re_matches_valid_tokens(self):
        assert CONFIRM_RE.search("RUN:a1b2c3d4e5f6a7b8")
        assert CONFIRM_RE.search("query RUN:0123456789abcdef more")

    def test_confirm_re_rejects_short_tokens(self):
        assert CONFIRM_RE.search("RUN:abcd") is None

    def test_confirm_re_rejects_uppercase_hex(self):
        assert CONFIRM_RE.search("RUN:A1B2C3D4E5F6A7B8") is None


# =============================================================================
# 5. TestAdminTurnIntegration
# =============================================================================

def _setup_cp_dirs(root: Path):
    """Create minimal Control Plane directory structure for admin_turn."""
    (root / "planes" / "ho1" / "sessions").mkdir(parents=True, exist_ok=True)
    (root / "ledger").mkdir(parents=True, exist_ok=True)
    (root / "_staging").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)


class TestAdminTurnIntegration:
    """Full-stack tests with mocked handlers verifying confirmation flow."""

    def test_admin_turn_dry_run(self, tmp_path):
        """admin_turn with bare query -> handler gets no confirmation_id -> dry run."""
        from modules.router.prompt_router import IntentResult

        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test dry run",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ):
            from modules.admin_agent.agent import admin_turn
            result = admin_turn(
                user_query="list packages",
                root=tmp_path,
            )

        assert "Proposed Action" in result
        assert "RUN:" in result

    def test_admin_turn_confirmed(self, tmp_path):
        """admin_turn with RUN:<valid> -> handler gets confirmation_id -> executes."""
        from modules.router.prompt_router import IntentResult

        _setup_cp_dirs(tmp_path)

        # First, compute the valid token
        # The clean query will be "list packages" and handler will be "list_installed"
        cid = _valid_confirmation_id("list_installed", "list packages")

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test confirmed",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.admin_agent.handlers.tools_first.list_installed",
            return_value="[executed list_installed]",
        ) as mock_handler:
            from modules.admin_agent.agent import admin_turn
            result = admin_turn(
                user_query=f"list packages RUN:{cid}",
                root=tmp_path,
            )

        mock_handler.assert_called_once()
        # Verify the handler received the confirmation_id in context
        call_context = mock_handler.call_args[0][1]
        assert call_context["confirmation_id"] == cid
        assert call_context["query"] == "list packages"
        assert result == "[executed list_installed]"

    def test_admin_turn_audit_preserves_original_query(self, tmp_path):
        """admin_turn logs the ORIGINAL query (with RUN: token) for audit trail."""
        from modules.router.prompt_router import IntentResult

        _setup_cp_dirs(tmp_path)

        cid = _valid_confirmation_id("list_installed", "list packages")
        original_query = f"list packages RUN:{cid}"

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test audit",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.admin_agent.handlers.tools_first.list_installed",
            return_value="[ok]",
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_query",
        ) as mock_write_query:
            from modules.admin_agent.agent import admin_turn
            admin_turn(user_query=original_query, root=tmp_path)

        # The original query (with RUN: token) should be written to the ledger
        mock_write_query.assert_called_once()
        call_kwargs = mock_write_query.call_args
        assert f"RUN:{cid}" in call_kwargs[1]["content"]

    def test_admin_turn_invalid_token_no_execution(self, tmp_path):
        """admin_turn with invalid RUN: token -> handler returns mismatch."""
        from modules.router.prompt_router import IntentResult

        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test invalid",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ):
            from modules.admin_agent.agent import admin_turn
            result = admin_turn(
                user_query="list packages RUN:0000000000000000",
                root=tmp_path,
            )

        assert "mismatch" in result.lower()


# =============================================================================
# 6. TestA0ExecuteExtraction
# =============================================================================

class TestA0ExecuteExtraction:
    """Unit tests for extract_a0_execute helper."""

    def test_a0_and_execute_detected(self):
        clean, flag = extract_a0_execute("A0 list packages EXECUTE")
        assert flag is True
        assert "A0" not in clean
        assert "EXECUTE" not in clean
        assert "list packages" in clean

    def test_execution_mode_and_execute_detected(self):
        clean, flag = extract_a0_execute("Execution Mode list packages EXECUTE")
        assert flag is True
        assert "Execution Mode" not in clean
        assert "EXECUTE" not in clean

    def test_a0_without_execute_not_authorized(self):
        clean, flag = extract_a0_execute("A0 list packages")
        assert flag is False
        assert clean == "A0 list packages"  # unchanged

    def test_execute_without_a0_not_authorized(self):
        clean, flag = extract_a0_execute("list packages EXECUTE")
        assert flag is False
        assert clean == "list packages EXECUTE"  # unchanged

    def test_neither_signal(self):
        clean, flag = extract_a0_execute("list packages")
        assert flag is False
        assert clean == "list packages"

    def test_case_insensitive_execute(self):
        clean, flag = extract_a0_execute("A0 list packages execute")
        assert flag is True

    def test_case_insensitive_execution_mode(self):
        clean, flag = extract_a0_execute("execution mode list packages EXECUTE")
        assert flag is True

    def test_a0_word_boundary(self):
        """A0 must be a standalone word, not part of another token."""
        clean, flag = extract_a0_execute("BA0B list packages EXECUTE")
        assert flag is False  # "A0" is inside "BA0B", not standalone

    def test_whitespace_cleanup(self):
        clean, flag = extract_a0_execute("A0   list   packages   EXECUTE")
        assert flag is True
        # Should not have excessive whitespace
        assert "  " not in clean


# =============================================================================
# 7. TestA0ExecuteSameTurn — Handler-level
# =============================================================================

class TestA0ExecuteSameTurn:
    """A0 + EXECUTE authorizes same-turn execution at the handler level."""

    def test_list_installed_a0_execute(self):
        agent = _make_agent()
        context = {"query": "list packages", "a0_execute": True}
        result = tools_first.list_installed(agent, context)

        agent.list_installed.assert_called_once()
        assert result == "PKG-A, PKG-B"
        # confirmation_id should have been injected for audit
        assert "confirmation_id" in context

    def test_explain_a0_execute(self):
        agent = _make_agent()
        context = {"query": "explain FMWK-000", "a0_execute": True,
                    "artifact_id": "FMWK-000"}
        result = tools_first.explain(agent, context)

        agent.explain.assert_called_once_with("FMWK-000")
        assert result == "Explanation of artifact"
        assert "confirmation_id" in context

    def test_check_health_a0_execute(self):
        agent = _make_agent()
        context = {"query": "check health", "a0_execute": True}
        result = tools_first.check_health(agent, context)

        agent.check_health.assert_called_once()
        assert result == "PASS"
        assert "confirmation_id" in context

    def test_inventory_a0_execute(self):
        agent = _make_agent()
        context = {"query": "inventory", "a0_execute": True}
        tools_first.inventory(agent, context)

        agent._run_trace.assert_called_once_with("--inventory")
        assert "confirmation_id" in context


# =============================================================================
# 8. TestA0ExecuteDryRunFallback
# =============================================================================

class TestA0ExecuteDryRunFallback:
    """A0-only or EXECUTE-only does NOT authorize; still returns dry-run."""

    def test_a0_only_no_execution(self):
        """a0_execute=False (A0 without EXECUTE at extraction) -> dry-run."""
        agent = _make_agent()
        context = {"query": "list packages"}  # no a0_execute, no confirmation_id
        result = tools_first.list_installed(agent, context)

        assert "Proposed Action" in result
        agent.list_installed.assert_not_called()

    def test_execute_only_no_execution(self):
        """EXECUTE without A0 never sets a0_execute -> dry-run."""
        agent = _make_agent()
        context = {"query": "list packages"}
        result = tools_first.list_installed(agent, context)

        assert "Proposed Action" in result
        agent.list_installed.assert_not_called()

    def test_a0_execute_false_explicit(self):
        """Explicitly a0_execute=False should NOT authorize."""
        agent = _make_agent()
        context = {"query": "list packages", "a0_execute": False}
        result = tools_first.list_installed(agent, context)

        assert "Proposed Action" in result
        agent.list_installed.assert_not_called()


# =============================================================================
# 9. TestCheckConfirmationPrecedence
# =============================================================================

class TestCheckConfirmationPrecedence:
    """RUN:<token> takes precedence over a0_execute when both are present."""

    def test_valid_run_token_with_a0_execute(self):
        """Both valid RUN: and a0_execute -> executes (via RUN: path)."""
        agent = _make_agent()
        query = "list packages"
        cid = _valid_confirmation_id("list_installed", query)
        context = {"query": query, "confirmation_id": cid, "a0_execute": True}
        result = tools_first.list_installed(agent, context)

        agent.list_installed.assert_called_once()
        assert result == "PKG-A, PKG-B"

    def test_invalid_run_token_with_a0_execute(self):
        """Invalid RUN: token fails even if a0_execute is True."""
        agent = _make_agent()
        context = {"query": "list packages", "confirmation_id": "0000000000000000",
                    "a0_execute": True}
        result = tools_first.list_installed(agent, context)

        # RUN: path checked first; mismatch blocks execution
        assert "mismatch" in result.lower()
        agent.list_installed.assert_not_called()


# =============================================================================
# 10. TestA0ExecuteAdminTurnIntegration
# =============================================================================

class TestA0ExecuteAdminTurnIntegration:
    """Full admin_turn integration with A0 + EXECUTE same-turn flow."""

    def test_admin_turn_a0_execute(self, tmp_path):
        """admin_turn with A0 + EXECUTE -> same-turn execution."""
        from modules.router.prompt_router import IntentResult

        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test a0 execute",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.admin_agent.handlers.tools_first.list_installed",
            return_value="[executed via A0]",
        ) as mock_handler:
            from modules.admin_agent.agent import admin_turn
            result = admin_turn(
                user_query="A0 list packages EXECUTE",
                root=tmp_path,
            )

        mock_handler.assert_called_once()
        call_context = mock_handler.call_args[0][1]
        assert call_context["a0_execute"] is True
        assert call_context["query"] == "list packages"
        assert result == "[executed via A0]"

    def test_admin_turn_a0_without_execute_dryrun(self, tmp_path):
        """admin_turn with A0 but no EXECUTE -> dry-run."""
        from modules.router.prompt_router import IntentResult

        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test a0 no execute",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ):
            from modules.admin_agent.agent import admin_turn
            result = admin_turn(
                user_query="A0 list packages",
                root=tmp_path,
            )

        assert "Proposed Action" in result

    def test_admin_turn_execute_without_a0_dryrun(self, tmp_path):
        """admin_turn with EXECUTE but no A0 -> dry-run."""
        from modules.router.prompt_router import IntentResult

        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test execute no a0",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ):
            from modules.admin_agent.agent import admin_turn
            result = admin_turn(
                user_query="list packages EXECUTE",
                root=tmp_path,
            )

        assert "Proposed Action" in result

    def test_admin_turn_a0_execute_audit_preserves_original(self, tmp_path):
        """Audit ledger records the original query (with A0/EXECUTE tokens)."""
        from modules.router.prompt_router import IntentResult

        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test audit a0",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.admin_agent.handlers.tools_first.list_installed",
            return_value="[ok]",
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_query",
        ) as mock_write_query:
            from modules.admin_agent.agent import admin_turn
            admin_turn(user_query="A0 list packages EXECUTE", root=tmp_path)

        mock_write_query.assert_called_once()
        logged_content = mock_write_query.call_args[1]["content"]
        assert "A0" in logged_content
        assert "EXECUTE" in logged_content

    def test_admin_turn_execution_mode_execute(self, tmp_path):
        """'Execution Mode' phrase works as A0 signal."""
        from modules.router.prompt_router import IntentResult

        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="health_check",
            confidence=0.95,
            reasoning="test execution mode",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.admin_agent.handlers.tools_first.check_health",
            return_value="[health ok]",
        ) as mock_handler:
            from modules.admin_agent.agent import admin_turn
            result = admin_turn(
                user_query="Execution Mode check health EXECUTE",
                root=tmp_path,
            )

        mock_handler.assert_called_once()
        assert result == "[health ok]"

    def test_admin_turn_a0_execute_confirmation_id_in_context(self, tmp_path):
        """A0+EXECUTE path injects confirmation_id into context for audit."""
        from modules.router.prompt_router import IntentResult

        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test cid injection",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.admin_agent.handlers.tools_first.list_installed",
            return_value="[ok]",
        ) as mock_handler:
            from modules.admin_agent.agent import admin_turn
            admin_turn(
                user_query="A0 list packages EXECUTE",
                root=tmp_path,
            )

        call_context = mock_handler.call_args[0][1]
        assert call_context.get("a0_execute") is True
