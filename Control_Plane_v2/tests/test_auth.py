#!/usr/bin/env python3
"""
test_auth.py - Unit tests for auth module.

Tests _parse_env_file function supporting both KEY=VALUE and export KEY=VALUE formats.
"""
from __future__ import annotations

import tempfile
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.auth import _parse_env_file


class TestParseEnvFile:
    """Test _parse_env_file supports both KEY=VALUE and export KEY=VALUE."""

    def test_parse_mixed_formats(self):
        """Parse file with export and non-export lines."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("""export A=1
B=2
# comment
export C=three

# blank lines above
D=four
""")
            f.flush()
            path = Path(f.name)

        try:
            result = _parse_env_file(path)
            assert result == {"A": "1", "B": "2", "C": "three", "D": "four"}
        finally:
            path.unlink()

    def test_parse_empty_file(self):
        """Empty file returns empty dict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("")
            f.flush()
            path = Path(f.name)

        try:
            result = _parse_env_file(path)
            assert result == {}
        finally:
            path.unlink()

    def test_parse_comments_only(self):
        """File with only comments returns empty dict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("""# comment 1
# comment 2
""")
            f.flush()
            path = Path(f.name)

        try:
            result = _parse_env_file(path)
            assert result == {}
        finally:
            path.unlink()

    def test_parse_value_with_equals(self):
        """Values containing = are preserved."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("export TOKEN=abc:def=ghi\n")
            f.flush()
            path = Path(f.name)

        try:
            result = _parse_env_file(path)
            assert result == {"TOKEN": "abc:def=ghi"}
        finally:
            path.unlink()

    def test_parse_whitespace_handling(self):
        """Whitespace around keys and values is trimmed."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("  KEY  =  value  \n")
            f.flush()
            path = Path(f.name)

        try:
            result = _parse_env_file(path)
            assert result == {"KEY": "value"}
        finally:
            path.unlink()

    def test_parse_lines_without_equals_ignored(self):
        """Lines without = are ignored."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("""export A=1
invalid line
B=2
""")
            f.flush()
            path = Path(f.name)

        try:
            result = _parse_env_file(path)
            assert result == {"A": "1", "B": "2"}
        finally:
            path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
