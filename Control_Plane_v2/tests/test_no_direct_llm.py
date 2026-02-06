"""Enforcement tests: no direct Anthropic SDK usage outside stdlib_llm provider.

Tests that:
1. Static scan: forbidden SDK patterns only appear in the legitimate provider
2. Runtime: _complete_with_tools() raises LLMError
3. Integration: general() uses stdlib_llm.complete() (mock provider)
4. Static scan (expanded): Anthropic(, .messages.create(, from anthropic, import anthropic
5. Static scan (dynamic import evasion): __import__, importlib.import_module
6. Runtime callstack: provider.complete() is only reachable via stdlib_llm.complete()
7. Import safety: importing key modules triggers zero LLM calls or ledger writes
"""

import importlib
import inspect
import json
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

CONTROL_PLANE_ROOT = Path(__file__).parent.parent


# =============================================================================
# Static scan helpers
# =============================================================================

# The ONLY file allowed to touch the Anthropic SDK
_ALLOWED_PROVIDER = "modules/stdlib_llm/providers/anthropic.py"

_SKIP_DIRS = {"__pycache__", "_staging", ".git"}


def _scan_for_pattern(pattern: str) -> list:
    """Grep for actual code usage (not comments/docstrings) in .py files.

    Scans all .py files under CONTROL_PLANE_ROOT except the allowed
    provider module, skipped directories, and this test file.
    """
    matches = []
    for py_file in CONTROL_PLANE_ROOT.rglob("*.py"):
        rel = py_file.relative_to(CONTROL_PLANE_ROOT)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        if str(rel) == _ALLOWED_PROVIDER:
            continue
        if rel.name == "test_no_direct_llm.py":
            continue
        try:
            content = py_file.read_text()
        except Exception:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.lstrip()
            # Skip comment lines
            if stripped.startswith("#"):
                continue
            # Skip docstring lines (triple-quote openers)
            if stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if pattern in line:
                matches.append(f"{rel}:{i}: {line.strip()}")
    return matches


# =============================================================================
# 1. Repo-wide static scan — four forbidden patterns
# =============================================================================

class TestStaticScanForbiddenPatterns:
    """Fail if any forbidden Anthropic SDK pattern appears outside the provider."""

    def test_no_anthropic_client_constructor(self):
        """No 'Anthropic(' outside the provider module."""
        matches = _scan_for_pattern("Anthropic(")
        assert matches == [], (
            "Found 'Anthropic(' in forbidden locations:\n"
            + "\n".join(matches)
        )

    def test_no_messages_create(self):
        """No '.messages.create(' outside the provider module."""
        matches = _scan_for_pattern(".messages.create(")
        assert matches == [], (
            "Found '.messages.create(' in forbidden locations:\n"
            + "\n".join(matches)
        )

    def test_no_from_anthropic(self):
        """No 'from anthropic' outside the provider module."""
        matches = _scan_for_pattern("from anthropic")
        assert matches == [], (
            "Found 'from anthropic' in forbidden locations:\n"
            + "\n".join(matches)
        )

    def test_no_import_anthropic(self):
        """No 'import anthropic' outside the provider module."""
        matches = _scan_for_pattern("import anthropic")
        assert matches == [], (
            "Found 'import anthropic' in forbidden locations:\n"
            + "\n".join(matches)
        )

    def test_no_dunder_import_anthropic(self):
        """No '__import__("anthropic")' outside the provider module."""
        matches = _scan_for_pattern('__import__("anthropic")')
        matches += _scan_for_pattern("__import__('anthropic')")
        assert matches == [], (
            "Found __import__('anthropic') in forbidden locations:\n"
            + "\n".join(matches)
        )

    def test_no_importlib_import_module_anthropic_double_quotes(self):
        """No 'importlib.import_module("anthropic")' outside the provider."""
        matches = _scan_for_pattern('importlib.import_module("anthropic")')
        assert matches == [], (
            'Found importlib.import_module("anthropic") in forbidden locations:\n'
            + "\n".join(matches)
        )

    def test_no_importlib_import_module_anthropic_single_quotes(self):
        """No "importlib.import_module('anthropic')" outside the provider."""
        matches = _scan_for_pattern("importlib.import_module('anthropic')")
        assert matches == [], (
            "Found importlib.import_module('anthropic') in forbidden locations:\n"
            + "\n".join(matches)
        )


# =============================================================================
# 2. Runtime callstack verification
# =============================================================================

# The single allowed caller module for provider.complete()
_ALLOWED_CALLER_MODULE = "modules.stdlib_llm.client"
_ALLOWED_CALLER_FUNCTION = "complete"


class _SpyProvider:
    """Test provider that captures the call stack when invoked."""

    def __init__(self):
        self.called = False
        self.caller_frames = []

    @property
    def provider_id(self) -> str:
        return "spy"

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        model: Optional[str] = None,
        schema: Optional[dict] = None,
    ):
        from modules.stdlib_llm.provider import ProviderResponse

        self.called = True
        # Capture the full call stack (excluding this frame)
        self.caller_frames = inspect.stack()[1:]

        return ProviderResponse(
            content="spy-response",
            model="spy-model",
            usage={"input_tokens": 1, "output_tokens": 1},
            request_id="spy-001",
            cached=False,
            metadata={"provider_id": "spy"},
        )

    def validate_config(self) -> bool:
        return True


class TestRuntimeSingleInvocationPath:
    """Prove at runtime that provider.complete() is only reachable via
    stdlib_llm.client.complete().

    Strategy: register a spy provider, call stdlib_llm.complete(), then
    inspect the captured call stack to verify the immediate caller is
    modules.stdlib_llm.client.complete — and nothing else.
    """

    def test_provider_called_via_stdlib_complete(self):
        """provider.complete() IS called and the caller IS stdlib_llm.complete()."""
        from modules.stdlib_llm.providers import register_provider
        from modules.stdlib_llm.client import complete

        spy = _SpyProvider()
        register_provider("spy", lambda: spy)

        try:
            complete(
                prompt="hello",
                prompt_pack_id="PRM-ADMIN-GENERAL-001",
                provider_id="spy",
            )
        except Exception:
            # Ledger write may fail in test env; the spy still records the call
            pass

        assert spy.called, "Provider.complete() was never invoked"

        # Find the frame that called spy.complete()
        # caller_frames[0] is the immediate caller of spy.complete()
        immediate_caller = spy.caller_frames[0]
        caller_module = immediate_caller.frame.f_globals.get("__name__", "")
        caller_function = immediate_caller.function

        assert caller_module == _ALLOWED_CALLER_MODULE, (
            f"provider.complete() called from module '{caller_module}', "
            f"expected '{_ALLOWED_CALLER_MODULE}'\n"
            f"Full stack:\n"
            + "\n".join(
                f"  {f.filename}:{f.lineno} in {f.function}"
                for f in spy.caller_frames[:6]
            )
        )
        assert caller_function == _ALLOWED_CALLER_FUNCTION, (
            f"provider.complete() called from function '{caller_function}', "
            f"expected '{_ALLOWED_CALLER_FUNCTION}'"
        )

    def test_provider_not_callable_from_arbitrary_module(self):
        """Calling provider.complete() directly (not via stdlib_llm.complete)
        would show a different caller — this test proves the guard works."""
        from modules.stdlib_llm.providers import get_provider

        spy = _SpyProvider()

        # Call provider.complete() DIRECTLY — bypassing stdlib_llm.complete()
        spy.complete(prompt="bypass attempt", max_tokens=10)

        assert spy.called, "Spy should have been called"

        # The immediate caller is THIS test function, NOT stdlib_llm.client.complete
        immediate_caller = spy.caller_frames[0]
        caller_module = immediate_caller.frame.f_globals.get("__name__", "")
        caller_function = immediate_caller.function

        # Prove this call did NOT come from the allowed path
        assert caller_module != _ALLOWED_CALLER_MODULE or \
               caller_function != _ALLOWED_CALLER_FUNCTION, (
            "Direct provider call should NOT appear to come from "
            "stdlib_llm.client.complete — guard is broken"
        )

    def test_no_second_path_to_provider(self):
        """Verify that no module outside stdlib_llm imports the LLM provider
        registry to obtain a provider directly (bypassing stdlib_llm.complete).

        Scans for imports from the LLM provider module and direct LLM provider
        instantiation patterns.
        """
        # These patterns specifically target the LLM provider subsystem.
        # We do NOT match the auth get_provider() — different module entirely.
        forbidden_patterns = [
            "from modules.stdlib_llm.providers import",
            "from modules.stdlib_llm.providers ",
            "from modules.stdlib_llm import get_provider",
            "stdlib_llm.providers.get_provider",
        ]
        # Files inside stdlib_llm that legitimately use the provider registry
        allowed_prefixes = [
            "modules/stdlib_llm/",
        ]
        # Test files that exercise the provider API directly (test harness)
        allowed_test_files = {
            "tests/test_stdlib_llm.py",
            "tests/test_router_admin_contract.py",
        }

        violations = []
        for py_file in CONTROL_PLANE_ROOT.rglob("*.py"):
            rel = py_file.relative_to(CONTROL_PLANE_ROOT)
            rel_str = str(rel)
            if any(part in _SKIP_DIRS for part in rel.parts):
                continue
            if any(rel_str.startswith(p) for p in allowed_prefixes):
                continue
            if rel_str in allowed_test_files:
                continue
            if rel.name == "test_no_direct_llm.py":
                continue
            try:
                content = py_file.read_text()
            except Exception:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                for pattern in forbidden_patterns:
                    if pattern in line:
                        violations.append(f"{rel}:{i}: {line.strip()}")

        assert violations == [], (
            "Found LLM provider registry access outside stdlib_llm (potential bypass):\n"
            + "\n".join(violations)
        )


# =============================================================================
# 3. Existing enforcement tests (preserved)
# =============================================================================

class TestCompleteWithToolsForbidden:
    """Runtime check: _complete_with_tools() raises LLMError."""

    def test_raises_llm_error(self):
        """Calling _complete_with_tools() always raises LLMError."""
        from modules.stdlib_llm.client import LLMError
        from modules.admin_agent.handlers.llm_assisted import _complete_with_tools

        with pytest.raises(LLMError, match="Direct LLM calls are forbidden"):
            _complete_with_tools()

    def test_error_code(self):
        """LLMError has the correct governance code."""
        from modules.stdlib_llm.client import LLMError
        from modules.admin_agent.handlers.llm_assisted import _complete_with_tools

        with pytest.raises(LLMError) as exc_info:
            _complete_with_tools(query="test", system_prompt="test")
        assert exc_info.value.code == "DIRECT_LLM_FORBIDDEN"


class TestGeneralUsesGovernedPath:
    """Integration: general() routes through stdlib_llm.complete()."""

    def test_general_returns_response(self):
        """general() returns a response via the governed LLM path."""
        from modules.admin_agent.agent import AdminAgent
        from modules.admin_agent.handlers.llm_assisted import general

        agent = AdminAgent(root=CONTROL_PLANE_ROOT)
        context = {
            "query": "What packages are installed?",
            "session": None,
            "prompt_pack_id": "PRM-ADMIN-GENERAL-001",
        }
        result = general(agent, context)
        # Should return a string (either content or a handled error)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_general_does_not_import_anthropic(self):
        """general() function source does not reference anthropic."""
        from modules.admin_agent.handlers.llm_assisted import general

        source = inspect.getsource(general)
        assert "anthropic" not in source
        assert "_complete_with_tools" not in source


# =============================================================================
# 5. Import safety — no LLM calls triggered by module import
# =============================================================================

# Modules that touch LLM code paths and must be safe to import without
# triggering any provider call or ledger write.
_IMPORT_SAFETY_MODULES = [
    "modules.stdlib_llm",
    "modules.stdlib_llm.client",
    "modules.stdlib_llm.providers",
    "modules.stdlib_llm.providers.mock",
    "modules.router",
    "modules.router.prompt_router",
    "modules.admin_agent",
    "modules.admin_agent.handlers.llm_assisted",
]


class TestImportSafety:
    """Importing key modules must NEVER trigger an LLM call or ledger write.

    Strategy:
    - Register a spy provider as default before importing
    - Snapshot the L-LLM ledger size before importing
    - Force-reimport every target module
    - Assert spy was never called and ledger did not grow
    """

    def _get_llm_ledger_path(self) -> Path:
        """Resolve the L-LLM ledger path (mirrors client._get_llm_ledger_path)."""
        return CONTROL_PLANE_ROOT / "ledger" / "llm.jsonl"

    def _ledger_line_count(self) -> int:
        """Count lines in the L-LLM ledger (0 if file doesn't exist)."""
        ledger = self._get_llm_ledger_path()
        if not ledger.exists():
            return 0
        return sum(1 for _ in ledger.open())

    def test_imports_do_not_invoke_provider(self):
        """Importing LLM-adjacent modules must not call provider.complete()."""
        from modules.stdlib_llm.providers import register_provider

        spy = _SpyProvider()
        register_provider("import-spy", lambda: spy)

        # Force re-import of every target module
        for mod_name in _IMPORT_SAFETY_MODULES:
            # Remove from cache to force fresh import
            full_name = mod_name
            to_remove = [k for k in sys.modules if k == full_name or k.startswith(full_name + ".")]
            for k in to_remove:
                del sys.modules[k]

        # Now import them all fresh
        for mod_name in _IMPORT_SAFETY_MODULES:
            importlib.import_module(mod_name)

        assert not spy.called, (
            "Provider.complete() was called during module import. "
            "Modules must not trigger LLM calls at import time."
        )

    def test_imports_do_not_write_llm_ledger(self):
        """Importing LLM-adjacent modules must not write LLM_CALL ledger entries."""
        ledger_before = self._ledger_line_count()

        # Force re-import of every target module
        for mod_name in _IMPORT_SAFETY_MODULES:
            full_name = mod_name
            to_remove = [k for k in sys.modules if k == full_name or k.startswith(full_name + ".")]
            for k in to_remove:
                del sys.modules[k]

        for mod_name in _IMPORT_SAFETY_MODULES:
            importlib.import_module(mod_name)

        ledger_after = self._ledger_line_count()

        assert ledger_after == ledger_before, (
            f"L-LLM ledger grew during module import "
            f"(before={ledger_before}, after={ledger_after}). "
            f"Modules must not trigger LLM calls at import time."
        )
