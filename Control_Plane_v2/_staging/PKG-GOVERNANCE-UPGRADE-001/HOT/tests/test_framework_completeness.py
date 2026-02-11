"""TDD tests for PKG-GOVERNANCE-UPGRADE-001 — Completeness Validation.

RED: These tests MUST FAIL before implementation.
GREEN: Add FrameworkCompletenessValidator to preflight.py.

Tests verify:
- FrameworkCompletenessValidator exists and is callable
- Passes when all expected_specs exist and reference framework back
- Fails when an expected_spec is missing
- Fails when a spec doesn't reference the framework back
- Warns (not fails) when expected_specs is absent (grace period)
- Result gate is G1-COMPLETE
"""
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
HOT_ROOT = SCRIPT_DIR.parent
CP_ROOT = HOT_ROOT.parent
sys.path.insert(0, str(HOT_ROOT))


class TestFrameworkCompletenessValidator:
    """Test the FrameworkCompletenessValidator class."""

    def test_class_exists(self):
        """FrameworkCompletenessValidator must be importable from preflight."""
        from kernel.preflight import FrameworkCompletenessValidator
        assert FrameworkCompletenessValidator is not None

    def test_has_validate_method(self):
        """Must have a validate() method."""
        from kernel.preflight import FrameworkCompletenessValidator
        validator = FrameworkCompletenessValidator()
        assert hasattr(validator, "validate")

    def test_passes_when_all_specs_wired(self, tmp_path):
        """Should PASS when all expected_specs exist and reference back."""
        from kernel.preflight import FrameworkCompletenessValidator
        # Setup: create framework manifest with expected_specs
        fmwk_dir = tmp_path / "HOT" / "FMWK-TEST_Test"
        fmwk_dir.mkdir(parents=True)
        (fmwk_dir / "manifest.yaml").write_text(
            "framework_id: FMWK-TEST\n"
            "title: Test\nstatus: active\nversion: '1.0.0'\n"
            "ring: kernel\nplane_id: hot\n"
            "expected_specs:\n  - SPEC-A\n  - SPEC-B\n"
        )
        # Setup: create spec manifests that reference back
        spec_dir = tmp_path / "HOT" / "spec_packs"
        for spec_id in ["SPEC-A", "SPEC-B"]:
            d = spec_dir / spec_id
            d.mkdir(parents=True)
            (d / "manifest.yaml").write_text(
                f"spec_id: {spec_id}\nframework_id: FMWK-TEST\n"
                f"title: Test\nstatus: active\nversion: '1.0.0'\n"
                f"assets:\n  - file.py\n"
            )

        validator = FrameworkCompletenessValidator(plane_root=tmp_path)
        result = validator.validate({"spec_id": "SPEC-A", "framework_id": "FMWK-TEST"})
        assert result.passed, f"Should pass: {result.errors}"

    def test_fails_when_expected_spec_missing(self, tmp_path):
        """Should FAIL when an expected_spec doesn't exist."""
        from kernel.preflight import FrameworkCompletenessValidator
        fmwk_dir = tmp_path / "HOT" / "FMWK-TEST_Test"
        fmwk_dir.mkdir(parents=True)
        (fmwk_dir / "manifest.yaml").write_text(
            "framework_id: FMWK-TEST\n"
            "title: Test\nstatus: active\nversion: '1.0.0'\n"
            "expected_specs:\n  - SPEC-A\n  - SPEC-MISSING\n"
        )
        spec_dir = tmp_path / "HOT" / "spec_packs" / "SPEC-A"
        spec_dir.mkdir(parents=True)
        (spec_dir / "manifest.yaml").write_text(
            "spec_id: SPEC-A\nframework_id: FMWK-TEST\n"
            "title: Test\nstatus: active\nversion: '1.0.0'\nassets:\n  - file.py\n"
        )

        validator = FrameworkCompletenessValidator(plane_root=tmp_path)
        result = validator.validate({"spec_id": "SPEC-A", "framework_id": "FMWK-TEST"})
        assert not result.passed or any("SPEC-MISSING" in w for w in result.warnings + result.errors)

    def test_fails_when_spec_references_wrong_framework(self, tmp_path):
        """Should FAIL when expected_spec references a different framework."""
        from kernel.preflight import FrameworkCompletenessValidator
        fmwk_dir = tmp_path / "HOT" / "FMWK-TEST_Test"
        fmwk_dir.mkdir(parents=True)
        (fmwk_dir / "manifest.yaml").write_text(
            "framework_id: FMWK-TEST\n"
            "title: Test\nstatus: active\nversion: '1.0.0'\n"
            "expected_specs:\n  - SPEC-WRONG\n"
        )
        spec_dir = tmp_path / "HOT" / "spec_packs" / "SPEC-WRONG"
        spec_dir.mkdir(parents=True)
        (spec_dir / "manifest.yaml").write_text(
            "spec_id: SPEC-WRONG\nframework_id: FMWK-OTHER\n"
            "title: Test\nstatus: active\nversion: '1.0.0'\nassets:\n  - file.py\n"
        )

        validator = FrameworkCompletenessValidator(plane_root=tmp_path)
        result = validator.validate({"spec_id": "SPEC-WRONG", "framework_id": "FMWK-TEST"})
        assert not result.passed or any("FMWK-OTHER" in w or "mismatch" in w.lower()
                                        for w in result.warnings + result.errors)

    def test_warns_when_no_expected_specs(self, tmp_path):
        """Should WARN (not fail) when framework has no expected_specs — grace period."""
        from kernel.preflight import FrameworkCompletenessValidator
        fmwk_dir = tmp_path / "HOT" / "FMWK-TEST_Test"
        fmwk_dir.mkdir(parents=True)
        (fmwk_dir / "manifest.yaml").write_text(
            "framework_id: FMWK-TEST\n"
            "title: Test\nstatus: active\nversion: '1.0.0'\n"
            # No expected_specs field
        )

        validator = FrameworkCompletenessValidator(plane_root=tmp_path)
        result = validator.validate({"spec_id": "SPEC-A", "framework_id": "FMWK-TEST"})
        # Should pass (grace period) but with a warning
        assert result.passed, "Missing expected_specs should warn, not fail"
        assert len(result.warnings) > 0, "Should warn about missing expected_specs"

    def test_result_gate_is_g1_complete(self, tmp_path):
        """Result gate identifier should be G1-COMPLETE."""
        from kernel.preflight import FrameworkCompletenessValidator
        fmwk_dir = tmp_path / "HOT" / "FMWK-TEST_Test"
        fmwk_dir.mkdir(parents=True)
        (fmwk_dir / "manifest.yaml").write_text(
            "framework_id: FMWK-TEST\ntitle: Test\nstatus: active\nversion: '1.0.0'\n"
        )

        validator = FrameworkCompletenessValidator(plane_root=tmp_path)
        result = validator.validate({"spec_id": "SPEC-A", "framework_id": "FMWK-TEST"})
        assert result.gate == "G1-COMPLETE"
