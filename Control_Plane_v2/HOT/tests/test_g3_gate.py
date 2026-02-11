#!/usr/bin/env python3
"""
test_g3_gate.py - Tests for G3 CONSTRAINTS gate.

Tests the constraint validation logic:
- Dependency file changes require dependency_add WO type
- New files generate warnings (Phase 3)
- Constraints field is logged
"""

import json
import pytest
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.g3_gate import (
    run_g3_gate,
    check_dependency_changes,
    check_new_files,
    check_constraints_field,
    is_dependency_file,
    G3Result,
)


class TestDependencyFileDetection:
    """Test dependency file detection."""

    def test_requirements_txt_is_dependency_file(self):
        """requirements.txt should be detected as dependency file."""
        assert is_dependency_file('requirements.txt') is True
        assert is_dependency_file('path/to/requirements.txt') is True

    def test_pyproject_toml_is_dependency_file(self):
        """pyproject.toml should be detected as dependency file."""
        assert is_dependency_file('pyproject.toml') is True

    def test_setup_py_is_dependency_file(self):
        """setup.py should be detected as dependency file."""
        assert is_dependency_file('setup.py') is True

    def test_regular_python_file_is_not_dependency_file(self):
        """Regular Python files should not be detected as dependency files."""
        assert is_dependency_file('lib/paths.py') is False
        assert is_dependency_file('scripts/gate_check.py') is False


class TestDependencyChanges:
    """Test dependency change detection."""

    def test_rejects_requirements_change_without_dependency_add_type(self):
        """WO modifying requirements.txt without dependency_add type should fail."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'type': 'code_change',
            'scope': {
                'allowed_files': ['requirements.txt', 'lib/paths.py']
            }
        }

        is_valid, errors, warnings = check_dependency_changes(wo)

        assert is_valid is False
        assert len(errors) > 0
        assert 'requirements.txt' in errors[0]
        assert 'dependency_add' in errors[1]

    def test_accepts_requirements_change_with_dependency_add_type(self):
        """WO modifying requirements.txt with dependency_add type should pass."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'type': 'dependency_add',
            'scope': {
                'allowed_files': ['requirements.txt']
            }
        }

        is_valid, errors, warnings = check_dependency_changes(wo)

        assert is_valid is True
        assert len(errors) == 0

    def test_accepts_code_change_without_dependency_files(self):
        """WO not touching dependency files should pass regardless of type."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'type': 'code_change',
            'scope': {
                'allowed_files': ['lib/paths.py', 'lib/output.py']
            }
        }

        is_valid, errors, warnings = check_dependency_changes(wo)

        assert is_valid is True
        assert len(errors) == 0

    def test_rejects_pyproject_change_without_dependency_add_type(self):
        """WO modifying pyproject.toml without dependency_add type should fail."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'type': 'code_change',
            'scope': {
                'allowed_files': ['pyproject.toml']
            }
        }

        is_valid, errors, warnings = check_dependency_changes(wo)

        assert is_valid is False
        assert 'pyproject.toml' in errors[0]


class TestNewFilesCheck:
    """Test new files detection (Phase 3: warnings only)."""

    def test_new_file_generates_warning_not_error(self):
        """New file in scope should generate warning, not error (Phase 3)."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'type': 'code_change',
            'scope': {
                'allowed_files': ['lib/new_module.py']
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            # Don't create the file - it's "new"

            is_valid, errors, warnings = check_new_files(wo, workspace)

            # Phase 3: should pass but with warning
            assert is_valid is True
            assert len(errors) == 0
            assert len(warnings) > 0
            assert 'new_module.py' in warnings[0]

    def test_existing_file_no_warning(self):
        """Existing file in scope should not generate warning."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'type': 'code_change',
            'scope': {
                'allowed_files': ['lib/existing.py']
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / 'lib').mkdir(parents=True)
            (workspace / 'lib' / 'existing.py').write_text('# existing')

            is_valid, errors, warnings = check_new_files(wo, workspace)

            assert is_valid is True
            assert len(warnings) == 0


class TestConstraintsField:
    """Test constraints field validation."""

    def test_empty_constraints_passes(self):
        """WO without constraints field should pass."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'type': 'code_change'
        }

        is_valid, errors, warnings = check_constraints_field(wo)

        assert is_valid is True
        assert len(errors) == 0

    def test_constraints_are_logged_as_warnings(self):
        """Constraints should be logged as warnings for audit."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'type': 'code_change',
            'constraints': {
                'no_new_deps_unless': 'approved',
                'no_api_change_unless': 'version_bump'
            }
        }

        is_valid, errors, warnings = check_constraints_field(wo)

        assert is_valid is True
        assert len(warnings) == 2
        assert 'no_new_deps_unless' in warnings[0]


class TestG3GateFull:
    """Test full G3 gate execution."""

    def test_clean_wo_passes(self):
        """WO with no constraint violations should pass."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'type': 'code_change',
            'scope': {
                'allowed_files': ['lib/paths.py']
            }
        }

        result = run_g3_gate(wo)

        assert result.passed is True
        assert 'G3 CONSTRAINTS gate passed' in result.message

    def test_dependency_violation_fails(self):
        """WO with dependency violation should fail."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'type': 'code_change',
            'scope': {
                'allowed_files': ['requirements.txt']
            }
        }

        result = run_g3_gate(wo)

        assert result.passed is False
        assert 'failed' in result.message.lower()
        assert len(result.errors) > 0

    def test_result_contains_details(self):
        """G3 result should contain check details."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'type': 'code_change',
            'scope': {
                'allowed_files': ['lib/paths.py']
            }
        }

        result = run_g3_gate(wo)

        assert 'dependency_check' in result.details
        assert 'new_files_check' in result.details
        assert 'constraints_check' in result.details

    def test_result_serializable_to_json(self):
        """G3Result should be JSON serializable."""
        wo = {
            'work_order_id': 'WO-TEST-001',
            'type': 'code_change',
            'scope': {
                'allowed_files': ['lib/paths.py']
            }
        }

        result = run_g3_gate(wo)
        result_dict = result.to_dict()

        # Should not raise
        json_str = json.dumps(result_dict)
        assert 'G3' in json_str


class TestAcceptanceCriteriaAC1:
    """AC1: G3 blocks WO modifying requirements.txt without dependency_add type."""

    def test_ac1_blocks_unauthorized_dep_change(self):
        """
        AC1: G3 blocks WO modifying requirements.txt without dependency_add type.

        This is the primary acceptance criterion for G3.
        """
        wo = {
            'work_order_id': 'WO-AC1-TEST',
            'type': 'code_change',  # NOT dependency_add
            'plane_id': 'ho3',
            'spec_id': 'SPEC-TEST-001',
            'framework_id': 'FMWK-000',
            'scope': {
                'allowed_files': ['requirements.txt'],
                'forbidden_files': []
            },
            'acceptance': {
                'tests': [],
                'checks': []
            }
        }

        result = run_g3_gate(wo)

        # MUST fail
        assert result.passed is False, "G3 must block unauthorized dependency changes"
        assert 'dependency_add' in ' '.join(result.errors), "Error must mention dependency_add"
