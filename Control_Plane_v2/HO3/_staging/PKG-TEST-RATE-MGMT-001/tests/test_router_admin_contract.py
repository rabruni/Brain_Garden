"""Router/Admin Agent Contract Harness.

Proves the current router and admin agent 'work right' via contract tests.
No redesign, no new handlers, no refactors — tests + glue only.

Tests:
1. RouteResult contract invariants on 11 representative inputs
2. Confidence boundary behavior (0.8 threshold)
3. All valid intents produce known handlers
4. route_query() does not execute handlers or call classify_intent more than once
5. admin_turn() dispatches exactly the selected handler (no double-call)
6. No cross-mode fallback — handler must exist in returned mode (fail-closed)
7. handler_executed evidence records what handler actually ran
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))

from modules.router.decision import (
    route_query,
    RouteResult,
    RouteMode,
    INTENT_HANDLER_MAP,
)
from modules.router.prompt_router import IntentResult, VALID_INTENTS


# =============================================================================
# Contract constants
# =============================================================================

# Handler names that exist in modules.admin_agent.handlers.tools_first
TOOLS_FIRST_HANDLERS = {
    "list_installed", "explain", "check_health", "inventory",
    "show_ledger", "show_session_ledger", "show_prompts_used",
    "read_file", "list_frameworks", "list_specs", "list_files",
}

# Handler names that exist in modules.admin_agent.handlers.llm_assisted
LLM_ASSISTED_HANDLERS = {
    "validate_document", "summarize", "explain_llm", "general",
}

ALL_HANDLERS = TOOLS_FIRST_HANDLERS | LLM_ASSISTED_HANDLERS


# =============================================================================
# Test vectors: (intent, confidence, expected_handler, expected_mode)
# =============================================================================

ROUTE_VECTORS = [
    # High confidence -> TOOLS_FIRST
    ("list_packages",    0.95, "list_installed",      RouteMode.TOOLS_FIRST),
    ("list_frameworks",  0.90, "list_frameworks",     RouteMode.TOOLS_FIRST),
    ("list_specs",       0.85, "list_specs",          RouteMode.TOOLS_FIRST),
    ("explain_artifact", 0.92, "explain",             RouteMode.TOOLS_FIRST),
    ("health_check",     0.88, "check_health",        RouteMode.TOOLS_FIRST),
    ("show_ledger",      0.80, "show_ledger",         RouteMode.TOOLS_FIRST),
    # Low confidence -> LLM_ASSISTED
    ("show_session",     0.79, "show_session_ledger", RouteMode.LLM_ASSISTED),
    ("read_file",        0.50, "read_file",           RouteMode.LLM_ASSISTED),
    ("validate",         0.70, "validate_document",   RouteMode.LLM_ASSISTED),
    ("general",          0.30, "general",             RouteMode.LLM_ASSISTED),
    # Unknown intent -> defaults to "general"
    ("nonexistent_xyz",  0.60, "general",             RouteMode.LLM_ASSISTED),
]


# =============================================================================
# 1. RouteResult Contract
# =============================================================================

class TestRouteResultContract:
    """route_query() returns RouteResult satisfying contract invariants."""

    @pytest.fixture(autouse=True)
    def _mock_classify(self):
        """Mock classify_intent so we control the IntentResult."""
        self._mock_intent = None
        with patch("modules.router.prompt_router.classify_intent") as mock_ci:
            mock_ci.side_effect = lambda query: self._mock_intent
            self._mock_ci = mock_ci
            yield

    def _set_intent(self, intent, confidence, artifact_id=None, file_path=None):
        self._mock_intent = IntentResult(
            intent=intent,
            confidence=confidence,
            artifact_id=artifact_id,
            file_path=file_path,
            reasoning=f"test: {intent}",
        )

    @pytest.mark.parametrize(
        "intent,confidence,expected_handler,expected_mode",
        ROUTE_VECTORS,
        ids=[v[0] for v in ROUTE_VECTORS],
    )
    def test_route_contract(self, intent, confidence, expected_handler, expected_mode):
        """route_query() maps intent to correct handler+mode and satisfies invariants."""
        self._set_intent(intent, confidence)
        result = route_query("test query")

        # Correct mapping
        assert isinstance(result, RouteResult)
        assert result.handler == expected_handler
        assert result.mode == expected_mode

        # C1: mode is TOOLS_FIRST or LLM_ASSISTED (never DENIED from route_query)
        assert result.mode in {RouteMode.TOOLS_FIRST, RouteMode.LLM_ASSISTED}

        # C2: handler exists in at least one handler module
        assert result.handler in ALL_HANDLERS, (
            f"Handler '{result.handler}' not in any handler module"
        )

        # C3: classification populated with correct confidence
        assert result.classification is not None
        assert result.classification.confidence == confidence

        # C4: prompt_pack_id is a governed prompt
        assert isinstance(result.prompt_pack_id, str)
        assert result.prompt_pack_id.startswith("PRM-")

    def test_does_not_execute_handler(self):
        """route_query() must NOT call any handler function."""
        self._set_intent("list_packages", 0.95)
        with patch(
            "modules.admin_agent.handlers.tools_first.list_installed"
        ) as mock_h:
            route_query("list packages")
            mock_h.assert_not_called()

    def test_calls_classify_intent_exactly_once(self):
        """route_query() calls classify_intent exactly once per call."""
        self._set_intent("general", 0.50)
        route_query("hello")
        assert self._mock_ci.call_count == 1

    def test_confidence_0_8_is_tools_first(self):
        """Confidence == 0.8 (boundary) routes to TOOLS_FIRST."""
        self._set_intent("list_packages", 0.8)
        assert route_query("test").mode == RouteMode.TOOLS_FIRST

    def test_confidence_below_0_8_is_llm_assisted(self):
        """Confidence < 0.8 routes to LLM_ASSISTED."""
        self._set_intent("list_packages", 0.7999)
        assert route_query("test").mode == RouteMode.LLM_ASSISTED

    def test_all_valid_intents_produce_known_handler(self):
        """Every VALID_INTENT maps to a handler that exists in the handler modules."""
        for intent in VALID_INTENTS:
            self._set_intent(intent, 0.95)
            result = route_query(f"test {intent}")
            assert result.handler in ALL_HANDLERS, (
                f"Intent '{intent}' mapped to unknown handler '{result.handler}'"
            )


# =============================================================================
# 2. Admin Turn Handler Dispatch
# =============================================================================

# (intent, confidence, expected_handler, handler_module_name)
DISPATCH_CASES = [
    # TOOLS_FIRST mode — handler found directly in tools_first
    ("list_packages",    0.95, "list_installed",    "tools_first"),
    ("explain_artifact", 0.92, "explain",           "tools_first"),
    ("health_check",     0.88, "check_health",      "tools_first"),
    ("list_frameworks",  0.90, "list_frameworks",   "tools_first"),
    # LLM_ASSISTED mode — handler found directly in llm_assisted
    ("general",          0.50, "general",           "llm_assisted"),
    ("validate",         0.70, "validate_document", "llm_assisted"),
    ("summarize",        0.60, "summarize",         "llm_assisted"),
]


def _setup_cp_dirs(root: Path):
    """Create minimal Control Plane directory structure for admin_turn."""
    (root / "planes" / "ho1" / "sessions").mkdir(parents=True, exist_ok=True)
    (root / "ledger").mkdir(parents=True, exist_ok=True)
    (root / "_staging").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)


class TestAdminTurnHandlerDispatch:
    """admin_turn() executes exactly the handler selected by the router."""

    @pytest.mark.parametrize(
        "intent,confidence,expected_handler,handler_module",
        DISPATCH_CASES,
        ids=[f"{c[2]}_via_{c[3]}" for c in DISPATCH_CASES],
    )
    def test_exactly_one_handler_called(
        self, tmp_path, intent, confidence, expected_handler, handler_module
    ):
        """admin_turn() calls exactly one handler — the one route_query() selected."""
        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent=intent,
            confidence=confidence,
            reasoning=f"test dispatch: {intent}",
        )

        # Patch ALL handler functions in both modules with mocks
        handler_mocks = {}
        patches = []

        for hname in TOOLS_FIRST_HANDLERS:
            p = patch(
                f"modules.admin_agent.handlers.tools_first.{hname}",
                return_value=f"[{hname} result]",
            )
            handler_mocks[("tools_first", hname)] = p.start()
            patches.append(p)

        for hname in LLM_ASSISTED_HANDLERS:
            p = patch(
                f"modules.admin_agent.handlers.llm_assisted.{hname}",
                return_value=f"[{hname} result]",
            )
            handler_mocks[("llm_assisted", hname)] = p.start()
            patches.append(p)

        try:
            with patch(
                "modules.router.prompt_router.classify_intent",
                return_value=mock_intent,
            ):
                from modules.admin_agent.agent import admin_turn
                admin_turn(user_query="test query", root=tmp_path)

            # The expected handler was called exactly once
            expected_mock = handler_mocks[(handler_module, expected_handler)]
            assert expected_mock.call_count == 1, (
                f"{expected_handler} should be called once, "
                f"got {expected_mock.call_count}"
            )

            # No other handler was called
            for key, mock_fn in handler_mocks.items():
                if key != (handler_module, expected_handler):
                    assert mock_fn.call_count == 0, (
                        f"{key[1]} ({key[0]}) unexpectedly called "
                        f"({mock_fn.call_count}x) — "
                        f"only {expected_handler} expected"
                    )

        finally:
            for p in patches:
                p.stop()

    def test_no_fallback_when_tools_first_handler_exists(self, tmp_path):
        """When handler exists in TOOLS_FIRST, LLM_ASSISTED fallback never reached."""
        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test: no fallback",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.admin_agent.handlers.tools_first.list_installed",
            return_value="[list result]",
        ) as mock_tools, patch(
            "modules.admin_agent.handlers.llm_assisted.general",
            return_value="[general result]",
        ) as mock_llm_general:
            from modules.admin_agent.agent import admin_turn
            admin_turn(user_query="list packages", root=tmp_path)

        assert mock_tools.call_count == 1
        assert mock_llm_general.call_count == 0

    def test_missing_handler_fails_closed(self, tmp_path):
        """Handler missing in returned mode returns error, no fallback.

        When route_query produces LLM_ASSISTED mode but the handler only exists
        in tools_first, admin_turn must NOT fall back. It returns an error and
        no handler is called.
        """
        _setup_cp_dirs(tmp_path)

        # list_packages with low confidence -> LLM_ASSISTED mode
        # "list_installed" does NOT exist in llm_assisted -> fail closed
        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.50,
            reasoning="test: fail closed",
        )

        handler_mocks = {}
        patches = []

        for hname in TOOLS_FIRST_HANDLERS:
            p = patch(
                f"modules.admin_agent.handlers.tools_first.{hname}",
                return_value=f"[{hname}]",
            )
            handler_mocks[("tools_first", hname)] = p.start()
            patches.append(p)

        for hname in LLM_ASSISTED_HANDLERS:
            p = patch(
                f"modules.admin_agent.handlers.llm_assisted.{hname}",
                return_value=f"[{hname}]",
            )
            handler_mocks[("llm_assisted", hname)] = p.start()
            patches.append(p)

        try:
            with patch(
                "modules.router.prompt_router.classify_intent",
                return_value=mock_intent,
            ):
                from modules.admin_agent.agent import admin_turn
                result = admin_turn(user_query="list packages", root=tmp_path)

            # No handler should be called — zero total
            total_calls = sum(m.call_count for m in handler_mocks.values())
            assert total_calls == 0, (
                f"Expected 0 handler calls (fail closed), got {total_calls}"
            )

            # Result should be an error string
            assert "not found" in result.lower()
            assert "no fallback" in result.lower()

        finally:
            for p in patches:
                p.stop()

    def test_missing_handler_records_denied_in_evidence(self, tmp_path):
        """When handler is missing, route_decision reason reflects DENIED."""
        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.50,
            reasoning="test: denied evidence",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            admin_turn(user_query="list packages", root=tmp_path)

        # Verify write_turn was called with evidence containing DENIED
        mock_write_turn.assert_called_once()
        call_kwargs = mock_write_turn.call_args[1]
        evidence = call_kwargs["evidence_entry"]
        route_decision = evidence.get("route_decision", {})
        assert route_decision.get("mode") == "denied"
        assert "not found" in route_decision.get("reason", "").lower()


# =============================================================================
# 3. Handler Executed Evidence
# =============================================================================

HANDLER_EXECUTED_CASES = [
    # (intent, confidence, expected_handler, expected_mode)
    ("list_packages",    0.95, "list_installed",    "tools_first"),
    ("explain_artifact", 0.92, "explain",           "tools_first"),
    ("general",          0.50, "general",           "llm_assisted"),
]


class TestHandlerExecutedEvidence:
    """handler_executed evidence records what handler actually ran."""

    @pytest.mark.parametrize(
        "intent,confidence,expected_handler,expected_mode",
        HANDLER_EXECUTED_CASES,
        ids=[c[2] for c in HANDLER_EXECUTED_CASES],
    )
    def test_handler_executed_present_and_matches(
        self, tmp_path, intent, confidence, expected_handler, expected_mode
    ):
        """Evidence contains handler_executed matching the dispatched handler."""
        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent=intent,
            confidence=confidence,
            reasoning=f"test handler_executed: {intent}",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            f"modules.admin_agent.handlers.{expected_mode}.{expected_handler}",
            return_value=f"[{expected_handler} result]",
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            admin_turn(user_query="test query", root=tmp_path)

        mock_write_turn.assert_called_once()
        evidence = mock_write_turn.call_args[1]["evidence_entry"]

        he = evidence.get("handler_executed")
        assert he is not None, "handler_executed missing from evidence"
        assert he["handler"] == expected_handler
        assert he["mode"] == expected_mode
        assert he["executed"] is True
        assert "timestamp" in he
        assert "authorization" in he

    def test_handler_executed_false_when_denied(self, tmp_path):
        """handler_executed.executed is False when handler not found."""
        _setup_cp_dirs(tmp_path)

        # list_packages at low confidence -> LLM_ASSISTED
        # list_installed not in llm_assisted -> denied
        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.50,
            reasoning="test handler_executed denied",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            admin_turn(user_query="list packages", root=tmp_path)

        evidence = mock_write_turn.call_args[1]["evidence_entry"]
        he = evidence.get("handler_executed")
        assert he is not None
        assert he["handler"] == "list_installed"
        assert he["executed"] is False
        assert he["mode"] == "denied"
        assert he["authorization"] == "none"

    def test_handler_executed_includes_confirmation_id(self, tmp_path):
        """handler_executed records the confirmation_id when RUN: token used."""
        from modules.admin_agent.handlers.confirmation import compute_confirmation_id

        _setup_cp_dirs(tmp_path)

        cid = compute_confirmation_id(
            {"handler": "list_installed", "query": "list packages"}
        )

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test handler_executed cid",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.admin_agent.handlers.tools_first.list_installed",
            return_value="[ok]",
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            admin_turn(
                user_query=f"list packages RUN:{cid}",
                root=tmp_path,
            )

        evidence = mock_write_turn.call_args[1]["evidence_entry"]
        he = evidence["handler_executed"]
        assert he["executed"] is True
        assert he["confirmation_id"] == cid

    def test_handler_executed_no_confirmation_id_when_bare(self, tmp_path):
        """handler_executed.confirmation_id is None when no RUN: token."""
        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test handler_executed bare",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            # Bare query -> dry-run, but handler_executed still recorded
            admin_turn(user_query="list packages", root=tmp_path)

        evidence = mock_write_turn.call_args[1]["evidence_entry"]
        he = evidence["handler_executed"]
        assert he["confirmation_id"] is None


# =============================================================================
# 4. Quarantine — Unmapped Handlers Unreachable
# =============================================================================

# Handlers that exist in handler modules but are NOT in INTENT_HANDLER_MAP
QUARANTINED_HANDLERS = [
    ("inventory",        RouteMode.TOOLS_FIRST),
    ("show_prompts_used", RouteMode.TOOLS_FIRST),
    ("list_files",       RouteMode.TOOLS_FIRST),
    ("explain_llm",      RouteMode.LLM_ASSISTED),
]

# Handlers that ARE in INTENT_HANDLER_MAP (should be reachable)
ROUTABLE_HANDLERS = [
    ("list_installed",      RouteMode.TOOLS_FIRST),
    ("explain",             RouteMode.TOOLS_FIRST),
    ("check_health",        RouteMode.TOOLS_FIRST),
    ("show_ledger",         RouteMode.TOOLS_FIRST),
    ("show_session_ledger", RouteMode.TOOLS_FIRST),
    ("read_file",           RouteMode.TOOLS_FIRST),
    ("list_frameworks",     RouteMode.TOOLS_FIRST),
    ("list_specs",          RouteMode.TOOLS_FIRST),
    ("validate_document",   RouteMode.LLM_ASSISTED),
    ("summarize",           RouteMode.LLM_ASSISTED),
    ("general",             RouteMode.LLM_ASSISTED),
]


class TestQuarantineUnmappedHandlers:
    """Unmapped handlers cannot be dispatched via get_handler()."""

    @pytest.mark.parametrize(
        "handler_name,mode",
        QUARANTINED_HANDLERS,
        ids=[h[0] for h in QUARANTINED_HANDLERS],
    )
    def test_quarantined_handler_returns_none(self, handler_name, mode):
        """get_handler() returns None for handlers not in INTENT_HANDLER_MAP."""
        from modules.admin_agent.handlers import get_handler
        assert get_handler(handler_name, mode) is None

    @pytest.mark.parametrize(
        "handler_name,mode",
        ROUTABLE_HANDLERS,
        ids=[h[0] for h in ROUTABLE_HANDLERS],
    )
    def test_routable_handler_returns_callable(self, handler_name, mode):
        """get_handler() returns a callable for handlers in INTENT_HANDLER_MAP."""
        from modules.admin_agent.handlers import get_handler
        handler = get_handler(handler_name, mode)
        assert handler is not None, (
            f"Routable handler '{handler_name}' should be returned by get_handler"
        )
        assert callable(handler)

    def test_legacy_path_denied(self, tmp_path):
        """admin_turn with use_router=False returns denial."""
        _setup_cp_dirs(tmp_path)

        from modules.admin_agent.agent import admin_turn
        result = admin_turn(
            user_query="list packages",
            root=tmp_path,
            use_router=False,
        )

        assert "disabled" in result.lower() or "denied" in result.lower()
        assert "legacy" in result.lower()

    def test_legacy_path_records_denied_evidence(self, tmp_path):
        """Legacy path records handler_executed with mode=denied."""
        _setup_cp_dirs(tmp_path)

        with patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            admin_turn(
                user_query="list packages",
                root=tmp_path,
                use_router=False,
            )

        mock_write_turn.assert_called_once()
        evidence = mock_write_turn.call_args[1]["evidence_entry"]
        he = evidence.get("handler_executed")
        assert he is not None
        assert he["handler"] == "legacy"
        assert he["mode"] == "denied"
        assert he["executed"] is False
        assert he["authorization"] == "none"

    def test_quarantined_handler_fails_closed_via_admin_turn(self, tmp_path):
        """Even if router returned a quarantined handler name, dispatch fails closed."""
        _setup_cp_dirs(tmp_path)

        # Simulate router returning "inventory" (quarantined) at high confidence
        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test quarantine fail-closed",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.router.decision.INTENT_HANDLER_MAP",
            {"list_packages": "inventory"},  # Force quarantined handler name
        ):
            from modules.admin_agent.agent import admin_turn
            result = admin_turn(user_query="list packages", root=tmp_path)

        # Should fail closed — inventory is quarantined
        assert "not found" in result.lower() or "error" in result.lower()


# =============================================================================
# 5. Error Path Evidence Preservation (F1)
# =============================================================================

class TestErrorPathEvidencePreservation:
    """Error path preserves route_decision and handler_executed in evidence."""

    def test_error_after_routing_preserves_route_decision(self, tmp_path):
        """If exception occurs after route_query, route_decision is in evidence."""
        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test error path",
        )

        def _raise_handler(agent, context):
            raise RuntimeError("handler exploded")

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.admin_agent.handlers.tools_first.list_installed",
            side_effect=_raise_handler,
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            result = admin_turn(user_query="list packages", root=tmp_path)

        assert "error" in result.lower()
        mock_write_turn.assert_called_once()
        evidence = mock_write_turn.call_args[1]["evidence_entry"]

        # F1: route_decision should be preserved even on error
        assert "route_decision" in evidence
        assert evidence["route_decision"]["handler"] == "list_installed"

        # handler_executed should also be preserved
        assert "handler_executed" in evidence
        assert evidence["handler_executed"]["handler"] == "list_installed"

        # error field still present
        assert "error" in evidence
        assert "handler exploded" in evidence["error"]

    def test_error_before_routing_has_no_route_decision(self, tmp_path):
        """If exception occurs before route_query, no route_decision in evidence."""
        _setup_cp_dirs(tmp_path)

        with patch(
            "modules.admin_agent.handlers.confirmation.extract_a0_execute",
            side_effect=RuntimeError("extraction failed"),
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            result = admin_turn(user_query="list packages", root=tmp_path)

        assert "error" in result.lower()
        evidence = mock_write_turn.call_args[1]["evidence_entry"]

        # No route_decision since error was before routing
        assert "route_decision" not in evidence
        assert "handler_executed" not in evidence
        assert "error" in evidence


# =============================================================================
# 6. Authorization Field in Evidence (F2)
# =============================================================================

class TestAuthorizationFieldInEvidence:
    """handler_executed.authorization disambiguates dry_run vs execution."""

    def test_dry_run_authorization(self, tmp_path):
        """Bare query (no RUN: token, no a0_execute) -> authorization='dry_run'."""
        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test dry_run auth",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            admin_turn(user_query="list packages", root=tmp_path)

        evidence = mock_write_turn.call_args[1]["evidence_entry"]
        he = evidence["handler_executed"]
        assert he["authorization"] == "dry_run"

    def test_run_token_authorization(self, tmp_path):
        """Valid RUN: token -> authorization='run_token'."""
        from modules.admin_agent.handlers.confirmation import compute_confirmation_id

        _setup_cp_dirs(tmp_path)

        cid = compute_confirmation_id(
            {"handler": "list_installed", "query": "list packages"}
        )

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test run_token auth",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.admin_agent.handlers.tools_first.list_installed",
            return_value="[ok]",
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            admin_turn(
                user_query=f"list packages RUN:{cid}",
                root=tmp_path,
            )

        evidence = mock_write_turn.call_args[1]["evidence_entry"]
        he = evidence["handler_executed"]
        assert he["authorization"] == "run_token"

    def test_a0_execute_authorization(self, tmp_path):
        """A0 + EXECUTE -> authorization='a0_execute'."""
        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test a0_execute auth",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.admin_agent.handlers.tools_first.list_installed",
            return_value="[ok]",
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            admin_turn(
                user_query="A0 list packages EXECUTE",
                root=tmp_path,
            )

        evidence = mock_write_turn.call_args[1]["evidence_entry"]
        he = evidence["handler_executed"]
        assert he["authorization"] == "a0_execute"

    def test_llm_assisted_capability_authorization(self, tmp_path):
        """LLM_ASSISTED handler -> authorization='capability'."""
        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="general",
            confidence=0.50,
            reasoning="test capability auth",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.admin_agent.handlers.llm_assisted.general",
            return_value="[llm result]",
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            admin_turn(user_query="hello", root=tmp_path)

        evidence = mock_write_turn.call_args[1]["evidence_entry"]
        he = evidence["handler_executed"]
        assert he["authorization"] == "capability"

    def test_denied_none_authorization(self, tmp_path):
        """Handler not found (denied) -> authorization='none'."""
        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.50,  # LLM_ASSISTED mode
            reasoning="test denied auth",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            admin_turn(user_query="list packages", root=tmp_path)

        evidence = mock_write_turn.call_args[1]["evidence_entry"]
        he = evidence["handler_executed"]
        assert he["authorization"] == "none"
        assert he["mode"] == "denied"


# =============================================================================
# 7. Router Provider Determinism (F3 mitigation)
# =============================================================================

class TestRouterProviderDeterminism:
    """Router classification uses an explicit, configurable provider_id."""

    def test_default_provider_is_anthropic(self):
        """Without ROUTER_LLM_PROVIDER env var, default is 'anthropic'."""
        from modules.router.prompt_router import get_router_provider_id
        import os

        # Ensure env var is not set (save and restore if it is)
        saved = os.environ.pop("ROUTER_LLM_PROVIDER", None)
        try:
            assert get_router_provider_id() == "anthropic"
        finally:
            if saved is not None:
                os.environ["ROUTER_LLM_PROVIDER"] = saved

    def test_env_var_overrides_default(self):
        """ROUTER_LLM_PROVIDER env var overrides the default."""
        from modules.router.prompt_router import get_router_provider_id
        import os

        saved = os.environ.get("ROUTER_LLM_PROVIDER")
        os.environ["ROUTER_LLM_PROVIDER"] = "mock"
        try:
            assert get_router_provider_id() == "mock"
        finally:
            if saved is not None:
                os.environ["ROUTER_LLM_PROVIDER"] = saved
            else:
                del os.environ["ROUTER_LLM_PROVIDER"]

    def test_classify_intent_passes_provider_id_to_complete(self):
        """classify_intent() passes the configured provider_id to complete()."""
        from modules.router.prompt_router import classify_intent

        with patch("modules.router.prompt_router.complete") as mock_complete, \
             patch("modules.router.prompt_router.load_prompt", return_value="## Prompt Template\n```\n{{query}}\n```"), \
             patch("modules.router.prompt_router.get_router_provider_id", return_value="test-provider"):
            from modules.stdlib_llm import LLMResponse
            mock_complete.return_value = LLMResponse(
                content='{"intent": "general", "confidence": 0.5, "reasoning": "test"}',
                model="test",
                usage={"input_tokens": 10, "output_tokens": 10},
                request_id="req-1",
                cached=False,
                evidence={},
                prompt_pack_id="PRM-ROUTER-001",
                provider_id="test-provider",
            )
            classify_intent("hello")

        mock_complete.assert_called_once()
        call_kwargs = mock_complete.call_args
        assert call_kwargs[1]["provider_id"] == "test-provider"

    def test_classify_intent_returns_provider_id_in_result(self):
        """IntentResult.provider_id reflects the provider used."""
        from modules.router.prompt_router import classify_intent

        with patch("modules.router.prompt_router.complete") as mock_complete, \
             patch("modules.router.prompt_router.load_prompt", return_value="## Prompt Template\n```\n{{query}}\n```"), \
             patch("modules.router.prompt_router.get_router_provider_id", return_value="spy-provider"):
            from modules.stdlib_llm import LLMResponse
            mock_complete.return_value = LLMResponse(
                content='{"intent": "list_packages", "confidence": 0.95, "reasoning": "lists"}',
                model="test",
                usage={"input_tokens": 10, "output_tokens": 10},
                request_id="req-2",
                cached=False,
                evidence={},
                prompt_pack_id="PRM-ROUTER-001",
                provider_id="spy-provider",
            )
            result = classify_intent("list packages")

        assert result.provider_id == "spy-provider"

    def test_route_evidence_includes_router_provider_id(self):
        """get_route_evidence() output includes router_provider_id."""
        self._mock_intent = None

        with patch("modules.router.prompt_router.classify_intent") as mock_ci:
            mock_ci.return_value = IntentResult(
                intent="list_packages",
                confidence=0.95,
                reasoning="test provider evidence",
                provider_id="mock",
            )
            result = route_query("list packages")

        from modules.router.decision import get_route_evidence
        evidence = get_route_evidence(result)
        rd = evidence["route_decision"]
        assert "router_provider_id" in rd
        assert rd["router_provider_id"] == "mock"

    def test_route_result_carries_provider_id(self):
        """RouteResult.router_provider_id is set from IntentResult."""
        with patch("modules.router.prompt_router.classify_intent") as mock_ci:
            mock_ci.return_value = IntentResult(
                intent="health_check",
                confidence=0.90,
                reasoning="test",
                provider_id="custom-provider",
            )
            result = route_query("check health")

        assert result.router_provider_id == "custom-provider"

    def test_admin_turn_evidence_includes_router_provider_id(self, tmp_path):
        """Full admin_turn evidence includes router_provider_id in route_decision."""
        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test evidence provider",
            provider_id="mock",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            admin_turn(user_query="list packages", root=tmp_path)

        evidence = mock_write_turn.call_args[1]["evidence_entry"]
        rd = evidence.get("route_decision", {})
        assert rd.get("router_provider_id") == "mock"


# =============================================================================
# 8. Pre-Router No Side Effects (Req A)
# =============================================================================

class TestPreRouterNoSideEffects:
    """admin_turn() pre-router code does only token hygiene — no I/O, no subprocess."""

    def test_no_subprocess_before_route_query(self, tmp_path):
        """No subprocess.run calls occur before route_query is invoked."""
        _setup_cp_dirs(tmp_path)

        call_order = []

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test pre-router",
        )

        import subprocess as _subprocess
        original_run = _subprocess.run

        def spy_subprocess_run(*args, **kwargs):
            call_order.append(("subprocess.run", args[0] if args else "?"))
            return original_run(*args, **kwargs)

        def spy_classify_intent(query):
            call_order.append(("classify_intent", query))
            return mock_intent

        with patch("subprocess.run", side_effect=spy_subprocess_run), \
             patch("modules.router.prompt_router.classify_intent",
                   side_effect=spy_classify_intent), \
             patch("modules.admin_agent.handlers.tools_first.list_installed",
                   return_value="[ok]"):
            from modules.admin_agent.agent import admin_turn
            admin_turn(user_query="list packages", root=tmp_path)

        # Find where classify_intent appears (first call inside route_query)
        classify_idx = None
        for i, (name, _) in enumerate(call_order):
            if name == "classify_intent":
                classify_idx = i
                break

        assert classify_idx is not None, "classify_intent was never called"

        # Assert: no subprocess.run calls before classify_intent
        # (classify_intent is the first call inside route_query, so anything
        # before it is pre-router code)
        for i in range(classify_idx):
            assert call_order[i][0] != "subprocess.run", (
                f"subprocess.run called before route_query: {call_order[i]}"
            )


# =============================================================================
# 9. Non-Mock Provider Response (Req C)
# =============================================================================

class TestNonMockProviderResponse:
    """LLM_ASSISTED_PROVIDER env var flows through to brain_call provider_id."""

    def test_general_handler_with_stub_provider(self, tmp_path, monkeypatch):
        """Setting LLM_ASSISTED_PROVIDER=stub routes through to complete(provider_id='stub')."""
        import json as _json
        _setup_cp_dirs(tmp_path)

        monkeypatch.setenv("LLM_ASSISTED_PROVIDER", "stub")

        # Build valid brain JSON
        brain_json = _json.dumps({
            "intent": "User wants guidance",
            "confidence": 0.85,
            "suggested_handler": "general",
            "mode": "llm_assisted",
            "proposed_next_step": "Review the governance ledger for recent activity.",
        })

        from modules.stdlib_llm.client import LLMResponse

        mock_response = LLMResponse(
            content=brain_json,
            model="stub-model",
            usage={"input_tokens": 100, "output_tokens": 50},
            request_id="stub-req-001",
            cached=False,
            evidence={
                "llm_call": {
                    "prompt_hash": "sha256:test",
                    "response_hash": "sha256:test",
                    "model": "stub-model",
                },
                "duration_ms": 42,
            },
            prompt_pack_id="PRM-BRAIN-001",
            provider_id="stub",
        )

        from modules.admin_agent.agent import AdminAgent
        from modules.admin_agent.handlers.llm_assisted import general

        agent = AdminAgent(root=tmp_path)
        context = {"query": "what should I do next?", "session": None}

        with patch("modules.brain.brain.complete",
                   return_value=mock_response) as mock_complete, \
             patch("modules.brain.brain.load_prompt",
                   return_value="## Prompt Template\n```\n{{query}} {{system_context}}\n```"):
            result = general(agent, context)

        # Verify env var flowed through: complete() received provider_id="stub"
        mock_complete.assert_called_once()
        assert mock_complete.call_args[1]["provider_id"] == "stub"

        # Output uses structured BrainResponse, not canned mock text
        assert "Mock response" not in result
        assert "Review the governance ledger" in result
        assert "**Intent:**" in result
        assert "**Confidence:**" in result
        assert "*Provider: stub*" in result


# =============================================================================
# 10. Tools-First Handlers Are Read-Only (Req D)
# =============================================================================

# TOOLS_FIRST intents — all are read-only observation operations
TOOLS_FIRST_READ_ONLY_INTENTS = [
    ("list_packages",    0.95, "list_installed"),
    ("explain_artifact", 0.92, "explain"),
    ("health_check",     0.88, "check_health"),
    ("show_ledger",      0.80, "show_ledger"),
    ("list_frameworks",  0.90, "list_frameworks"),
    ("list_specs",       0.85, "list_specs"),
]


class TestToolsFirstReadOnlyExecution:
    """TOOLS_FIRST handlers execute directly — they are read-only observations.

    These handlers never modify system state (no writes, no installs, no deletes).
    They are safe to execute without confirmation gating because they only read
    from registries, ledgers, and trace.py output.
    """

    @pytest.mark.parametrize(
        "intent,confidence,expected_handler",
        TOOLS_FIRST_READ_ONLY_INTENTS,
        ids=[t[2] for t in TOOLS_FIRST_READ_ONLY_INTENTS],
    )
    def test_tools_first_handler_executes_and_returns_content(
        self, tmp_path, intent, confidence, expected_handler
    ):
        """TOOLS_FIRST handlers execute directly and return real content (not errors)."""
        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent=intent,
            confidence=confidence,
            reasoning=f"test read-only execution: {intent}",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ):
            from modules.admin_agent.agent import admin_turn
            result = admin_turn(user_query="test query", root=tmp_path)

        # Handler should return a string with content (not an unhandled error)
        assert isinstance(result, str)
        assert len(result) > 0
        # Should not be a generic "No handler found" error
        assert "No handler found" not in result, (
            f"Handler '{expected_handler}' not found for intent '{intent}'"
        )


# =============================================================================
# 11. Evidence Completeness (Req D)
# =============================================================================

class TestEvidenceCompleteness:
    """Evidence contains required route_decision fields for both modes.

    admin_turn() writes evidence via write_turn() with:
    - route_decision: from get_route_evidence() containing mode, handler,
      confidence, prompt_pack_id, capabilities_used, reason
    - declared_reads/writes/external_calls: sandbox declarations
    """

    def test_tools_first_evidence_has_route_decision(self, tmp_path):
        """TOOLS_FIRST handler produces evidence with route_decision fields."""
        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="test evidence completeness TF",
            provider_id="mock",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            admin_turn(user_query="list packages", root=tmp_path)

        evidence = mock_write_turn.call_args[1]["evidence_entry"]

        # Must have route_decision from get_route_evidence()
        assert "route_decision" in evidence
        rd = evidence["route_decision"]
        assert rd["mode"] == "tools_first"
        assert rd["handler"] == "list_installed"
        assert "confidence" in rd
        assert "prompt_pack_id" in rd
        assert "reason" in rd

    def test_llm_assisted_evidence_has_route_decision(self, tmp_path):
        """LLM_ASSISTED handler produces evidence with route_decision fields."""
        _setup_cp_dirs(tmp_path)

        mock_intent = IntentResult(
            intent="general",
            confidence=0.50,
            reasoning="test evidence completeness LLM",
            provider_id="mock",
        )

        with patch(
            "modules.router.prompt_router.classify_intent",
            return_value=mock_intent,
        ), patch(
            "modules.admin_agent.handlers.llm_assisted.general",
            return_value="[general result]",
        ), patch(
            "modules.agent_runtime.ledger_writer.LedgerWriter.write_turn",
        ) as mock_write_turn:
            from modules.admin_agent.agent import admin_turn
            admin_turn(user_query="what should I do?", root=tmp_path)

        evidence = mock_write_turn.call_args[1]["evidence_entry"]

        # Must have route_decision from get_route_evidence()
        assert "route_decision" in evidence
        rd = evidence["route_decision"]
        assert rd["mode"] == "llm_assisted"
        assert rd["handler"] == "general"
        assert "confidence" in rd
        assert "prompt_pack_id" in rd
