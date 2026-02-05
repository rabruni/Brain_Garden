"""Unit tests for the Evidence Emission Standard Library."""

import json
import pytest
from pathlib import Path

from modules.stdlib_evidence import hash_json, hash_file, hash_string, build_evidence, build_reference


class TestHashJson:
    """Tests for hash_json function."""

    def test_deterministic(self):
        """Same input produces same hash regardless of key order."""
        obj1 = {"a": 1, "b": 2, "c": [3, 4]}
        obj2 = {"c": [3, 4], "b": 2, "a": 1}
        assert hash_json(obj1) == hash_json(obj2)

    def test_format(self):
        """Hash output has correct format."""
        result = hash_json({"test": "data"})
        assert result.startswith("sha256:")
        assert len(result) == 71  # "sha256:" + 64 hex chars

    def test_empty_object(self):
        """Empty object hashes consistently."""
        assert hash_json({}) == hash_json({})
        assert hash_json({}).startswith("sha256:")

    def test_nested_objects(self):
        """Nested objects hash deterministically."""
        obj1 = {"outer": {"inner": {"deep": True}}}
        obj2 = {"outer": {"inner": {"deep": True}}}
        assert hash_json(obj1) == hash_json(obj2)

    def test_different_values_different_hash(self):
        """Different values produce different hashes."""
        assert hash_json({"a": 1}) != hash_json({"a": 2})
        assert hash_json({"a": 1}) != hash_json({"b": 1})


class TestHashFile:
    """Tests for hash_file function."""

    def test_hash_file(self, tmp_path):
        """File hash returns expected format."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")
        result = hash_file(test_file)
        assert result.startswith("sha256:")
        assert len(result) == 71

    def test_same_content_same_hash(self, tmp_path):
        """Same content produces same hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("identical content")
        file2.write_text("identical content")
        assert hash_file(file1) == hash_file(file2)

    def test_different_content_different_hash(self, tmp_path):
        """Different content produces different hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content A")
        file2.write_text("content B")
        assert hash_file(file1) != hash_file(file2)

    def test_nonexistent_file_raises(self, tmp_path):
        """Non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            hash_file(tmp_path / "nonexistent.txt")


class TestHashString:
    """Tests for hash_string function."""

    def test_format(self):
        """Hash output has correct format."""
        result = hash_string("test")
        assert result.startswith("sha256:")
        assert len(result) == 71

    def test_deterministic(self):
        """Same string produces same hash."""
        assert hash_string("hello") == hash_string("hello")

    def test_different_strings(self):
        """Different strings produce different hashes."""
        assert hash_string("hello") != hash_string("world")


class TestBuildEvidence:
    """Tests for build_evidence function."""

    def test_required_fields(self):
        """Evidence envelope contains all required fields."""
        evidence = build_evidence(
            session_id="SES-123",
            turn_number=1,
            input_hash="sha256:abc",
            output_hash="sha256:def"
        )
        assert evidence["session_id"] == "SES-123"
        assert evidence["turn_number"] == 1
        assert evidence["input_hash"] == "sha256:abc"
        assert evidence["output_hash"] == "sha256:def"
        assert "timestamp" in evidence

    def test_optional_fields(self):
        """Evidence envelope includes optional fields when provided."""
        evidence = build_evidence(
            session_id="SES-123",
            turn_number=1,
            input_hash="sha256:abc",
            output_hash="sha256:def",
            work_order_id="WO-456",
            declared_reads=[{"path": "test.json", "hash": "sha256:xyz"}],
            declared_writes=[],
            external_calls=[],
            duration_ms=100
        )
        assert evidence["work_order_id"] == "WO-456"
        assert evidence["declared_reads"] == [{"path": "test.json", "hash": "sha256:xyz"}]
        assert evidence["duration_ms"] == 100

    def test_missing_session_id_raises(self):
        """Missing session_id raises ValueError."""
        with pytest.raises(ValueError, match="session_id"):
            build_evidence(
                session_id="",
                turn_number=1,
                input_hash="sha256:abc",
                output_hash="sha256:def"
            )

    def test_invalid_turn_number_raises(self):
        """Invalid turn_number raises ValueError."""
        with pytest.raises(ValueError, match="turn_number"):
            build_evidence(
                session_id="SES-123",
                turn_number=0,
                input_hash="sha256:abc",
                output_hash="sha256:def"
            )

    def test_kwargs_included(self):
        """Additional kwargs are included in evidence."""
        evidence = build_evidence(
            session_id="SES-123",
            turn_number=1,
            input_hash="sha256:abc",
            output_hash="sha256:def",
            custom_field="custom_value"
        )
        assert evidence["custom_field"] == "custom_value"


class TestBuildReference:
    """Tests for build_reference function."""

    def test_required_fields(self):
        """Reference contains required fields."""
        ref = build_reference("ART-001", "sha256:abc")
        assert ref["artifact_id"] == "ART-001"
        assert ref["hash"] == "sha256:abc"
        assert "timestamp" in ref

    def test_optional_fields(self):
        """Reference includes optional fields when provided."""
        ref = build_reference(
            artifact_id="ART-001",
            hash="sha256:abc",
            artifact_type="package",
            path="packages/PKG-001"
        )
        assert ref["artifact_type"] == "package"
        assert ref["path"] == "packages/PKG-001"

    def test_kwargs_included(self):
        """Additional kwargs are included in reference."""
        ref = build_reference(
            artifact_id="ART-001",
            hash="sha256:abc",
            custom="value"
        )
        assert ref["custom"] == "value"
