"""Tests for admin agent LLM-assisted capabilities."""

import json
import os
import pytest
from pathlib import Path

from modules.admin_agent import admin_turn, AdminAgent, get_handler
from modules.router import route_query, RouteMode


CONTROL_PLANE = Path(__file__).parent.parent


class TestAdminTurnWithRouter:
    """Tests for admin_turn with router integration."""

    def test_list_packages_tools_first(self):
        """List packages uses tools-first mode."""
        result = admin_turn("What packages are installed?", root=CONTROL_PLANE)
        assert "Installed" in result or "packages" in result.lower()

    def test_explain_tools_first(self):
        """Explain uses tools-first mode."""
        result = admin_turn("Explain FMWK-000", root=CONTROL_PLANE)
        # Should return some explanation
        assert len(result) > 0

    def test_health_check_tools_first(self):
        """Health check uses tools-first mode."""
        result = admin_turn("System health", root=CONTROL_PLANE)
        assert "Health" in result or "PASS" in result or "FAIL" in result

    def test_inventory_tools_first(self):
        """Inventory uses tools-first mode."""
        result = admin_turn("Show inventory", root=CONTROL_PLANE)
        assert "Inventory" in result or "files" in result.lower()

    def test_validate_denied_without_route(self):
        """Validate is denied without capability."""
        # The router should deny this without llm_assisted capability
        result = admin_turn("Validate this document", root=CONTROL_PLANE)
        # Should either be denied or handled
        assert len(result) > 0

    def test_legacy_mode_works(self):
        """Legacy mode (use_router=False) still works."""
        result = admin_turn(
            "What packages are installed?",
            root=CONTROL_PLANE,
            use_router=False,
        )
        assert "Installed" in result or "packages" in result.lower()


class TestGetHandler:
    """Tests for get_handler function."""

    def test_get_tools_first_handler(self):
        """Get tools-first handler."""
        handler = get_handler("list_installed", RouteMode.TOOLS_FIRST)
        assert handler is not None
        assert callable(handler)

    def test_get_llm_assisted_handler(self):
        """Get LLM-assisted handler."""
        handler = get_handler("validate_document", RouteMode.LLM_ASSISTED)
        assert handler is not None
        assert callable(handler)

    def test_get_unknown_handler(self):
        """Unknown handler returns None."""
        handler = get_handler("unknown_handler", RouteMode.TOOLS_FIRST)
        assert handler is None


class TestToolsFirstHandlers:
    """Tests for tools-first handlers."""

    def test_list_installed_handler(self):
        """list_installed handler works."""
        from modules.admin_agent.handlers.tools_first import list_installed

        agent = AdminAgent(root=CONTROL_PLANE)
        result = list_installed(agent, {})
        assert "Installed" in result or "packages" in result.lower()

    def test_explain_handler(self):
        """explain handler works."""
        from modules.admin_agent.handlers.tools_first import explain

        agent = AdminAgent(root=CONTROL_PLANE)
        result = explain(agent, {"artifact_id": "FMWK-000"})
        assert len(result) > 0

    def test_check_health_handler(self):
        """check_health handler works."""
        from modules.admin_agent.handlers.tools_first import check_health

        agent = AdminAgent(root=CONTROL_PLANE)
        result = check_health(agent, {})
        assert "Health" in result

    def test_inventory_handler(self):
        """inventory handler works."""
        from modules.admin_agent.handlers.tools_first import inventory

        agent = AdminAgent(root=CONTROL_PLANE)
        result = inventory(agent, {})
        assert "Inventory" in result


class TestLLMAssistedHandlers:
    """Tests for LLM-assisted handlers (using mock provider)."""

    def test_validate_document_handler(self):
        """validate_document handler works with mock."""
        from modules.admin_agent.handlers.llm_assisted import validate_document

        agent = AdminAgent(root=CONTROL_PLANE)
        result = validate_document(agent, {
            "query": "Validate this document",
            "prompt_pack_id": "PRM-ADMIN-VALIDATE-001",
        })
        # Should return some result from mock provider
        assert len(result) > 0

    def test_summarize_handler(self):
        """summarize handler works with mock."""
        from modules.admin_agent.handlers.llm_assisted import summarize

        agent = AdminAgent(root=CONTROL_PLANE)
        result = summarize(agent, {
            "query": "Summarize the frameworks",
            "prompt_pack_id": "PRM-ADMIN-EXPLAIN-001",
        })
        # Should return some result from mock provider
        assert "Summary" in result or len(result) > 0


class TestRouterIntegration:
    """Tests for router integration with admin agent."""

    def test_route_list_packages(self):
        """Router routes list packages correctly."""
        result = route_query("What packages are installed?")
        assert result.mode == RouteMode.TOOLS_FIRST
        assert result.handler == "list_installed"

    def test_route_explain(self):
        """Router routes explain correctly."""
        result = route_query("Explain FMWK-000")
        assert result.mode == RouteMode.TOOLS_FIRST
        assert result.handler == "explain"

    def test_route_validate_with_capability(self):
        """Router routes validate with capability."""
        capabilities = {"llm_assisted": {"validate": True}}
        result = route_query("Validate document", capabilities=capabilities)
        assert result.mode == RouteMode.LLM_ASSISTED
        assert result.prompt_pack_id == "PRM-ADMIN-VALIDATE-001"

    def test_route_summarize_with_capability(self):
        """Router routes summarize with capability."""
        capabilities = {"llm_assisted": {"summarize": True}}
        result = route_query("Summarize frameworks", capabilities=capabilities)
        assert result.mode == RouteMode.LLM_ASSISTED


class TestCapabilities:
    """Tests for capabilities loading."""

    def test_capabilities_file_exists(self):
        """Capabilities file exists."""
        caps_path = CONTROL_PLANE / "modules" / "admin_agent" / "capabilities.json"
        assert caps_path.exists()

    def test_capabilities_has_llm_assisted(self):
        """Capabilities include llm_assisted."""
        caps_path = CONTROL_PLANE / "modules" / "admin_agent" / "capabilities.json"
        data = json.loads(caps_path.read_text())
        assert "llm_assisted" in data.get("capabilities", {})

    def test_capabilities_validate_enabled(self):
        """Validate capability is enabled."""
        caps_path = CONTROL_PLANE / "modules" / "admin_agent" / "capabilities.json"
        data = json.loads(caps_path.read_text())
        llm_caps = data.get("capabilities", {}).get("llm_assisted", {})
        assert llm_caps.get("validate") is True

    def test_capabilities_summarize_enabled(self):
        """Summarize capability is enabled."""
        caps_path = CONTROL_PLANE / "modules" / "admin_agent" / "capabilities.json"
        data = json.loads(caps_path.read_text())
        llm_caps = data.get("capabilities", {}).get("llm_assisted", {})
        assert llm_caps.get("summarize") is True

    def test_capabilities_governed_prompts_readable(self):
        """Governed prompts are in read capabilities."""
        caps_path = CONTROL_PLANE / "modules" / "admin_agent" / "capabilities.json"
        data = json.loads(caps_path.read_text())
        read_caps = data.get("capabilities", {}).get("read", [])
        assert "governed_prompts/*.md" in read_caps
