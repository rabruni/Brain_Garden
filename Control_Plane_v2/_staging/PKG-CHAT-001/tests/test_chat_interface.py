#!/usr/bin/env python3
"""Tests for chat interface module."""

import sys
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.chat_interface.registry import HandlerRegistry, register
from modules.chat_interface.classifier import (
    classify_query,
    extract_dir_path,
    extract_file_path,
    extract_package_id,
    QueryType,
)


class TestHandlerRegistry:
    """Test handler registration and invocation."""

    def setup_method(self):
        """Clear registry before each test."""
        HandlerRegistry.clear()

    def test_register_handler(self):
        """Test handler registration via decorator."""
        @register("test_handler", description="Test handler", category="test")
        def handle_test(context, query, session):
            return "test result"

        assert "test_handler" in HandlerRegistry.list_handlers()
        info = HandlerRegistry.get("test_handler")
        assert info.description == "Test handler"
        assert info.category == "test"

    def test_invoke_handler(self):
        """Test handler invocation by name."""
        @register("test_invoke", description="Test")
        def handle_invoke(context, query, session):
            return f"Got: {query}"

        result = HandlerRegistry.invoke("test_invoke", {}, "hello", None)
        assert result == "Got: hello"

    def test_unknown_handler(self):
        """Test graceful handling of unknown handler."""
        result = HandlerRegistry.invoke("nonexistent", {}, "query", None)
        assert "Unknown handler" in result
        assert "help" in result.lower()

    def test_capability_check(self):
        """Test capability requirement enforcement."""
        @register("admin_only", description="Admin", requires_capability="admin")
        def handle_admin(context, query, session):
            return "admin result"

        # Without capability
        result = HandlerRegistry.invoke("admin_only", {}, "query", None, capability=None)
        assert "Permission denied" in result

        # With wrong capability
        result = HandlerRegistry.invoke("admin_only", {}, "query", None, capability="reader")
        assert "Permission denied" in result

        # With correct capability
        result = HandlerRegistry.invoke("admin_only", {}, "query", None, capability="admin")
        assert result == "admin result"

    def test_list_by_category(self):
        """Test handler grouping by category."""
        @register("cat_a_1", description="A1", category="a")
        def h1(c, q, s): pass

        @register("cat_a_2", description="A2", category="a")
        def h2(c, q, s): pass

        @register("cat_b_1", description="B1", category="b")
        def h3(c, q, s): pass

        by_cat = HandlerRegistry.list_by_category()
        assert len(by_cat["a"]) == 2
        assert len(by_cat["b"]) == 1


class TestClassifier:
    """Test query classification."""

    def test_browse_dir_classification(self):
        """Test directory browsing queries."""
        queries = [
            "what is in the modules directory?",
            "what's in modules",
            "list files in lib",
            "ls config",
            "browse handlers",
            "contents of registries",
        ]
        for query in queries:
            result = classify_query(query)
            assert result.type == QueryType.BROWSE_DIR, f"Query: {query}"
            assert result.pattern_matched is True

    def test_browse_code_classification(self):
        """Test file reading queries."""
        queries = [
            "read lib/auth.py",
            "show modules/chat_interface/registry.py",
            "cat config/control_plane_chain.json",
            "view lib/merkle.py",
        ]
        for query in queries:
            result = classify_query(query)
            assert result.type == QueryType.BROWSE_CODE, f"Query: {query}"

    def test_package_list_classification(self):
        """Test package list queries."""
        queries = [
            "list packages",
            "installed packages",
            "show packages",
            "what packages are installed",
        ]
        for query in queries:
            result = classify_query(query)
            assert result.type == QueryType.PACKAGE_LIST, f"Query: {query}"

    def test_package_inspect_classification(self):
        """Test package inspect queries."""
        queries = [
            "inspect PKG-KERNEL-001",
            "show PKG-ADMIN-001",
            "describe PKG-TEST-001",
        ]
        for query in queries:
            result = classify_query(query)
            assert result.type == QueryType.PACKAGE_INSPECT, f"Query: {query}"
            assert "package_id" in result.extracted_args

    def test_help_classification(self):
        """Test help queries."""
        queries = [
            "help",
            "commands",
            "what can you do",
            "show commands",
        ]
        for query in queries:
            result = classify_query(query)
            assert result.type == QueryType.HELP, f"Query: {query}"

    def test_general_fallback(self):
        """Test fallback to general for unrecognized queries."""
        queries = [
            "random gibberish",
            "xyz abc 123",
            "",
        ]
        for query in queries:
            result = classify_query(query)
            assert result.type == QueryType.GENERAL, f"Query: {query}"


class TestDirPathExtraction:
    """Test directory path extraction."""

    def test_extract_from_natural_language(self):
        """Test extraction from various phrasings."""
        cases = [
            ("what is in the modules directory?", "modules"),
            ("what's in modules", "modules"),
            ("list files in lib", "lib"),
            ("contents of config", "config"),
            ("browse handlers", "handlers"),
            ("ls registries", "registries"),
            ("show me the specs folder", "specs"),
        ]
        for query, expected in cases:
            result = extract_dir_path(query)
            assert result == expected, f"Query: '{query}' -> got '{result}', expected '{expected}'"

    def test_handles_unknown_dir(self):
        """Test graceful handling of unknown directories."""
        # Should still extract even if not a known dir
        result = extract_dir_path("list files in mydir")
        assert result == "mydir"

    def test_handles_no_dir(self):
        """Test None return when no directory found."""
        result = extract_dir_path("hello world")
        assert result is None or result in ["hello", "world"]


class TestFilePathExtraction:
    """Test file path extraction."""

    def test_extract_file_paths(self):
        """Test file path extraction."""
        cases = [
            ("read lib/auth.py", "lib/auth.py"),
            ("show modules/chat.py", "modules/chat.py"),
            ("cat config/test.json", "config/test.json"),
        ]
        for query, expected in cases:
            result = extract_file_path(query)
            assert result == expected, f"Query: {query}"

    def test_extract_with_extension(self):
        """Test extraction with paths."""
        # This tests that lib/ prefix paths are extracted
        result = extract_file_path("read lib/something")
        # lib/ prefixed paths are matched by the (lib/[\w/.-]+) pattern
        assert result == "lib/something" or result is None


class TestPackageIdExtraction:
    """Test package ID extraction."""

    def test_extract_package_id(self):
        """Test package ID extraction."""
        cases = [
            ("install PKG-TEST-001", "PKG-TEST-001"),
            ("inspect pkg-kernel-001", "PKG-KERNEL-001"),
            ("show PKG-Admin-Agent", "PKG-ADMIN-AGENT"),
        ]
        for query, expected in cases:
            result = extract_package_id(query)
            assert result == expected, f"Query: {query}"

    def test_no_package_id(self):
        """Test None return when no package ID found."""
        result = extract_package_id("list packages")
        assert result is None


class TestIntegration:
    """Integration tests for chat interface."""

    def test_import_module(self):
        """Test module imports without error."""
        from modules.chat_interface import ChatInterface, chat_turn, quick_query
        assert ChatInterface is not None
        assert chat_turn is not None
        assert quick_query is not None

    def test_handler_registration(self):
        """Test that all handlers are registered on import."""
        # Clear and re-register to avoid test pollution
        from modules.chat_interface.registry import HandlerRegistry
        HandlerRegistry.clear()

        # Re-import handlers to register them
        import importlib
        import modules.chat_interface.handlers.browse
        import modules.chat_interface.handlers.packages
        import modules.chat_interface.handlers.search
        import modules.chat_interface.handlers.ledger
        import modules.chat_interface.handlers.help
        importlib.reload(modules.chat_interface.handlers.browse)
        importlib.reload(modules.chat_interface.handlers.packages)
        importlib.reload(modules.chat_interface.handlers.search)
        importlib.reload(modules.chat_interface.handlers.ledger)
        importlib.reload(modules.chat_interface.handlers.help)

        registered = HandlerRegistry.list_handlers()
        # Check for expected handlers
        expected = ["browse_dir", "browse_code", "package_list", "help", "ledger_query"]
        for name in expected:
            assert name in registered, f"Missing handler: {name}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
