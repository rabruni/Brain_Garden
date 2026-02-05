"""Tests for prompt_loader library."""

import pytest

from lib.prompt_loader import (
    load_prompt,
    verify_prompt_hash,
    get_prompt_hash,
    get_prompt_info,
    list_prompts,
    verify_registry,
    load_registry,
    PromptNotFoundError,
    PromptHashMismatchError,
    PromptNotRegisteredError,
    InvalidPromptIdError,
    _compute_hash,
    _validate_prompt_id,
)


class TestComputeHash:
    """Tests for _compute_hash function."""

    def test_hash_format(self):
        """Hash has correct format."""
        h = _compute_hash("test content")
        assert h.startswith("sha256:")
        assert len(h) == len("sha256:") + 64

    def test_hash_deterministic(self):
        """Same content produces same hash."""
        h1 = _compute_hash("my content")
        h2 = _compute_hash("my content")
        assert h1 == h2

    def test_hash_different_content(self):
        """Different content produces different hash."""
        h1 = _compute_hash("content-1")
        h2 = _compute_hash("content-2")
        assert h1 != h2


class TestValidatePromptId:
    """Tests for _validate_prompt_id function."""

    def test_valid_id(self):
        """Valid ID returns True."""
        assert _validate_prompt_id("PRM-ADMIN-001") is True
        assert _validate_prompt_id("PRM-CLASSIFY-001") is True
        assert _validate_prompt_id("PRM-ADMIN-EXPLAIN-001") is True

    def test_invalid_empty(self):
        """Empty ID raises error."""
        with pytest.raises(InvalidPromptIdError):
            _validate_prompt_id("")

    def test_invalid_no_prefix(self):
        """ID without PRM- prefix raises error."""
        with pytest.raises(InvalidPromptIdError):
            _validate_prompt_id("ADMIN-001")

    def test_invalid_wrong_prefix(self):
        """ID with wrong prefix raises error."""
        with pytest.raises(InvalidPromptIdError):
            _validate_prompt_id("PROMPT-ADMIN-001")

    def test_invalid_too_few_parts(self):
        """ID with too few parts raises error."""
        with pytest.raises(InvalidPromptIdError):
            _validate_prompt_id("PRM-001")


class TestLoadRegistry:
    """Tests for load_registry function."""

    def test_load_registry(self):
        """Registry loads successfully."""
        registry = load_registry()
        assert isinstance(registry, dict)
        # Should have our test prompts
        assert "PRM-CLASSIFY-001" in registry


class TestGetPromptInfo:
    """Tests for get_prompt_info function."""

    def test_get_existing_prompt(self):
        """Get info for existing prompt."""
        info = get_prompt_info("PRM-CLASSIFY-001")
        assert info["prompt_id"] == "PRM-CLASSIFY-001"
        assert "hash" in info
        assert "status" in info

    def test_get_missing_prompt(self):
        """Missing prompt raises error."""
        with pytest.raises(PromptNotRegisteredError):
            get_prompt_info("PRM-MISSING-999")


class TestGetPromptHash:
    """Tests for get_prompt_hash function."""

    def test_get_hash_existing(self):
        """Get hash for existing prompt."""
        h = get_prompt_hash("PRM-CLASSIFY-001")
        assert h.startswith("sha256:")

    def test_get_hash_missing(self):
        """Missing prompt raises error."""
        with pytest.raises(PromptNotRegisteredError):
            get_prompt_hash("PRM-MISSING-999")


class TestLoadPrompt:
    """Tests for load_prompt function."""

    def test_load_existing_prompt(self):
        """Load existing prompt successfully."""
        content = load_prompt("PRM-CLASSIFY-001")
        assert isinstance(content, str)
        assert len(content) > 0
        assert "Query Classification" in content

    def test_load_prompt_no_verify(self):
        """Load prompt without verification."""
        content = load_prompt("PRM-CLASSIFY-001", verify=False)
        assert isinstance(content, str)
        assert len(content) > 0

    def test_load_invalid_id(self):
        """Invalid ID raises error."""
        with pytest.raises(InvalidPromptIdError):
            load_prompt("invalid")

    def test_load_unregistered_prompt(self):
        """Unregistered prompt raises error."""
        with pytest.raises(PromptNotRegisteredError):
            load_prompt("PRM-MISSING-999")


class TestVerifyPromptHash:
    """Tests for verify_prompt_hash function."""

    def test_verify_valid_hash(self):
        """Valid hash returns True."""
        content = load_prompt("PRM-CLASSIFY-001", verify=False)
        assert verify_prompt_hash("PRM-CLASSIFY-001", content) is True

    def test_verify_invalid_hash(self):
        """Invalid hash raises error."""
        with pytest.raises(PromptHashMismatchError):
            verify_prompt_hash("PRM-CLASSIFY-001", "tampered content")

    def test_verify_unregistered(self):
        """Unregistered prompt raises error."""
        with pytest.raises(PromptNotRegisteredError):
            verify_prompt_hash("PRM-MISSING-999", "any content")


class TestListPrompts:
    """Tests for list_prompts function."""

    def test_list_active(self):
        """List active prompts."""
        prompts = list_prompts("active")
        assert isinstance(prompts, list)
        # Should have our active prompts
        ids = [p["prompt_id"] for p in prompts]
        assert "PRM-CLASSIFY-001" in ids

    def test_list_all(self):
        """List all prompts."""
        prompts = list_prompts("all")
        assert isinstance(prompts, list)
        assert len(prompts) >= 3  # Our three prompts


class TestVerifyRegistry:
    """Tests for verify_registry function."""

    def test_verify_registry_passes(self):
        """Registry verification passes."""
        results = verify_registry()
        assert results["passed"] is True
        assert results["valid"] == results["total"]
        assert len(results["missing"]) == 0
        assert len(results["hash_mismatch"]) == 0
        assert len(results["errors"]) == 0

    def test_verify_registry_counts(self):
        """Registry has expected counts."""
        results = verify_registry()
        assert results["total"] >= 3  # Our three prompts


class TestIntegration:
    """Integration tests."""

    def test_load_all_registered_prompts(self):
        """All registered prompts can be loaded."""
        prompts = list_prompts("all")
        for prompt in prompts:
            prompt_id = prompt["prompt_id"]
            content = load_prompt(prompt_id)
            assert len(content) > 0

    def test_evidence_fields(self):
        """Prompts have required evidence fields."""
        prompts = list_prompts("all")
        for prompt in prompts:
            assert "prompt_id" in prompt
            assert "hash" in prompt
            assert prompt["hash"].startswith("sha256:")
