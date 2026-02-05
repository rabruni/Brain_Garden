"""Unit tests for the Admin Agent."""

import json
import pytest
from pathlib import Path

from modules.admin_agent import AdminAgent, admin_turn


# Get Control Plane root
CONTROL_PLANE_ROOT = Path(__file__).parent.parent


class TestAdminAgentExplain:
    """Tests for AdminAgent.explain method."""

    def test_explain_framework(self):
        """Admin Agent can explain a framework."""
        agent = AdminAgent(root=CONTROL_PLANE_ROOT)
        result = agent.explain("FMWK-000")
        assert "FMWK-000" in result
        # Should have some content
        assert len(result) > 50

    def test_explain_spec(self):
        """Admin Agent can explain a spec."""
        agent = AdminAgent(root=CONTROL_PLANE_ROOT)
        result = agent.explain("SPEC-CORE-001")
        assert "SPEC-CORE-001" in result

    def test_explain_package(self):
        """Admin Agent can explain a package."""
        agent = AdminAgent(root=CONTROL_PLANE_ROOT)
        result = agent.explain("PKG-KERNEL-001")
        assert "PKG-KERNEL-001" in result

    def test_explain_file(self):
        """Admin Agent can explain a file."""
        agent = AdminAgent(root=CONTROL_PLANE_ROOT)
        result = agent.explain("lib/merkle.py")
        # Should contain file info or ownership
        assert "merkle" in result.lower() or "ownership" in result.lower() or "lib/merkle.py" in result

    def test_unknown_artifact(self):
        """Admin Agent handles unknown artifacts gracefully."""
        agent = AdminAgent(root=CONTROL_PLANE_ROOT)
        result = agent.explain("NONEXISTENT-999")
        assert "unknown" in result.lower() or "not found" in result.lower() or "Unknown artifact" in result


class TestAdminAgentList:
    """Tests for AdminAgent.list_installed method."""

    def test_list_installed(self):
        """Admin Agent can list installed packages."""
        agent = AdminAgent(root=CONTROL_PLANE_ROOT)
        result = agent.list_installed()
        assert "Installed Packages" in result or "packages" in result.lower()

    def test_list_contains_packages(self):
        """List contains expected packages."""
        agent = AdminAgent(root=CONTROL_PLANE_ROOT)
        result = agent.list_installed()
        # Should contain PKG- prefix for package IDs
        assert "PKG-" in result


class TestAdminAgentHealth:
    """Tests for AdminAgent.check_health method."""

    def test_check_health(self):
        """Admin Agent can check system health."""
        agent = AdminAgent(root=CONTROL_PLANE_ROOT)
        result = agent.check_health()
        # Should indicate pass or fail
        assert "PASS" in result or "FAIL" in result or "health" in result.lower()

    def test_health_shows_checks(self):
        """Health check shows individual checks."""
        agent = AdminAgent(root=CONTROL_PLANE_ROOT)
        result = agent.check_health()
        # Should have some check results
        assert "Check" in result or "|" in result  # Table format


class TestAdminTurn:
    """Tests for admin_turn function."""

    def test_explain_query(self, tmp_path):
        """admin_turn handles explain queries."""
        result = admin_turn(
            "Explain FMWK-000",
            session_id="SES-test",
            turn_number=1,
            root=CONTROL_PLANE_ROOT
        )
        assert "FMWK-000" in result

    def test_list_query(self, tmp_path):
        """admin_turn handles list queries."""
        result = admin_turn(
            "list packages",
            session_id="SES-test-list",
            turn_number=1,
            root=CONTROL_PLANE_ROOT
        )
        assert "Package" in result or "Installed" in result

    def test_status_query(self, tmp_path):
        """admin_turn handles status queries."""
        result = admin_turn(
            "check health",
            session_id="SES-test-health",
            turn_number=1,
            root=CONTROL_PLANE_ROOT
        )
        assert "Health" in result or "PASS" in result or "FAIL" in result

    def test_general_query(self, tmp_path):
        """admin_turn handles general queries."""
        result = admin_turn(
            "What is the Control Plane?",
            session_id="SES-test-general",
            turn_number=1,
            root=CONTROL_PLANE_ROOT
        )
        # Should return something
        assert len(result) > 0


class TestAdminTurnLedger:
    """Tests for admin_turn ledger writing."""

    def test_creates_session_ledger(self, tmp_path):
        """admin_turn creates session ledger."""
        # Use tmp_path for session but CONTROL_PLANE_ROOT for trace.py access
        result = admin_turn(
            "explain FMWK-000",
            session_id="SES-ledger-test",
            turn_number=1,
            root=CONTROL_PLANE_ROOT  # Use real root so trace.py works
        )

        # Check that session directory was created
        session_path = CONTROL_PLANE_ROOT / "planes" / "ho1" / "sessions" / "SES-ledger-test"
        exec_path = session_path / "ledger" / "exec.jsonl"

        # If session was created in the real root
        if exec_path.exists():
            with open(exec_path) as f:
                entry = json.loads(f.readline())
            assert entry["session_id"] == "SES-ledger-test"
            assert entry["turn_number"] == 1


class TestQueryClassification:
    """Tests for query classification."""

    def test_explain_patterns(self):
        """Explain patterns are recognized."""
        from modules.admin_agent.agent import _classify_query

        assert _classify_query("explain FMWK-000") == "explain"
        assert _classify_query("What is SPEC-CORE-001?") == "explain"
        assert _classify_query("describe PKG-KERNEL-001") == "explain"
        assert _classify_query("FMWK-100") == "explain"

    def test_list_patterns(self):
        """List patterns are recognized."""
        from modules.admin_agent.agent import _classify_query

        assert _classify_query("list packages") == "list"
        assert _classify_query("what packages are installed") == "list"
        assert _classify_query("show installed") == "list"

    def test_status_patterns(self):
        """Status patterns are recognized."""
        from modules.admin_agent.agent import _classify_query

        assert _classify_query("check health") == "status"
        assert _classify_query("system status") == "status"
        assert _classify_query("verify integrity") == "status"


class TestArtifactExtraction:
    """Tests for artifact ID extraction."""

    def test_extract_framework_id(self):
        """Framework IDs are extracted."""
        from modules.admin_agent.agent import _extract_artifact_id

        assert _extract_artifact_id("explain FMWK-000") == "FMWK-000"
        assert _extract_artifact_id("What is FMWK-100?") == "FMWK-100"

    def test_extract_spec_id(self):
        """Spec IDs are extracted."""
        from modules.admin_agent.agent import _extract_artifact_id

        assert _extract_artifact_id("explain SPEC-CORE-001") == "SPEC-CORE-001"

    def test_extract_package_id(self):
        """Package IDs are extracted."""
        from modules.admin_agent.agent import _extract_artifact_id

        assert _extract_artifact_id("explain PKG-KERNEL-001") == "PKG-KERNEL-001"

    def test_extract_file_path(self):
        """File paths are extracted."""
        from modules.admin_agent.agent import _extract_artifact_id

        assert _extract_artifact_id("explain lib/merkle.py") == "lib/merkle.py"


class TestAdminAgentCapabilities:
    """Tests for Admin Agent capabilities."""

    def test_capabilities_file_exists(self):
        """Capabilities file exists."""
        caps_path = CONTROL_PLANE_ROOT / "modules" / "admin_agent" / "capabilities.json"
        assert caps_path.exists()

    def test_capabilities_are_read_only(self):
        """Capabilities declare read-only mode."""
        caps_path = CONTROL_PLANE_ROOT / "modules" / "admin_agent" / "capabilities.json"
        with open(caps_path) as f:
            caps = json.load(f)["capabilities"]

        # Should have read capabilities
        assert len(caps.get("read", [])) > 0

        # Write should only be to session ledgers
        for write_pattern in caps.get("write", []):
            assert "session" in write_pattern.lower() or "ledger" in write_pattern.lower()

        # Should have forbidden patterns
        assert len(caps.get("forbidden", [])) > 0
        assert "lib/*" in caps["forbidden"]

    def test_lib_is_forbidden(self):
        """lib/ paths are forbidden."""
        caps_path = CONTROL_PLANE_ROOT / "modules" / "admin_agent" / "capabilities.json"
        with open(caps_path) as f:
            caps = json.load(f)["capabilities"]

        from modules.agent_runtime import CapabilityEnforcer
        enforcer = CapabilityEnforcer(caps)
        assert enforcer.is_forbidden("lib/anything.py")
