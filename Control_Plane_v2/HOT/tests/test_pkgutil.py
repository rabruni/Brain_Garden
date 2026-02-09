#!/usr/bin/env python3
"""
Tests for scripts/pkgutil.py - Package authoring utilities.

Tests commands:
- init-agent: Agent skeleton generation
- init: Standard package skeleton
- preflight: Validation without install
- delta: Registry delta generation
- stage: Package staging
- check-framework: Framework validation
"""
import hashlib
import json
import os
import pytest
import subprocess
import sys
import tempfile
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _sha256(file_path: Path) -> str:
    """Compute sha256:<hex> hash for a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def run_pkgutil(*args, env=None, cwd=None):
    """Run pkgutil.py with given arguments."""
    # pkgutil.py lives in HO3/scripts/, not HOT/scripts/
    cp_root = Path(__file__).resolve().parent.parent.parent  # Control_Plane_v2/
    script = cp_root / "HO3" / "scripts" / "pkgutil.py"
    cmd = [sys.executable, str(script)] + list(args)

    # Set up environment
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    run_env["CONTROL_PLANE_ALLOW_UNSIGNED"] = "1"

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=run_env,
        cwd=cwd or str(Path(__file__).resolve().parent.parent),
    )
    return result


class TestInitAgentCommand:
    """Test init-agent command."""

    def test_init_agent_creates_skeleton(self, tmp_path):
        """Test init-agent creates expected files."""
        output_dir = tmp_path / "PKG-TEST-AGENT-001"

        result = run_pkgutil(
            "init-agent", "PKG-TEST-AGENT-001",
            "--framework", "FMWK-000",
            "--output", str(output_dir)
        )

        assert result.returncode == 0, f"Error: {result.stderr}"

        # Check core files created (prompts only populated when templates exist)
        assert (output_dir / "manifest.json").exists()
        assert (output_dir / "README.md").exists()

        # Check lib and tests directories
        lib_files = list((output_dir / "lib").glob("*.py"))
        assert len(lib_files) > 0

        test_files = list((output_dir / "tests").glob("*.py"))
        assert len(test_files) > 0

    def test_init_agent_manifest_content(self, tmp_path):
        """Test init-agent manifest has correct content."""
        output_dir = tmp_path / "PKG-ADMIN-001"

        result = run_pkgutil(
            "init-agent", "PKG-ADMIN-001",
            "--framework", "FMWK-000",
            "--output", str(output_dir)
        )

        assert result.returncode == 0

        manifest_path = output_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())

        assert manifest["package_id"] == "PKG-ADMIN-001"
        assert manifest["package_type"] == "agent"
        assert manifest["framework_id"] == "FMWK-000"
        assert "schema_version" in manifest


class TestInitCommand:
    """Test init command for standard packages."""

    def test_init_creates_skeleton(self, tmp_path):
        """Test init creates expected files."""
        output_dir = tmp_path / "PKG-LIB-001"

        result = run_pkgutil(
            "init", "PKG-LIB-001",
            "--output", str(output_dir)
        )

        assert result.returncode == 0, f"Error: {result.stderr}"

        # Check files created
        assert (output_dir / "manifest.json").exists()
        assert (output_dir / "lib").is_dir()
        assert (output_dir / "tests").is_dir()

    def test_init_with_spec(self, tmp_path):
        """Test init with spec_id."""
        output_dir = tmp_path / "PKG-SPEC-001"

        result = run_pkgutil(
            "init", "PKG-SPEC-001",
            "--spec", "SPEC-CORE-001",
            "--output", str(output_dir)
        )

        assert result.returncode == 0

        manifest = json.loads((output_dir / "manifest.json").read_text())
        assert manifest["spec_id"] == "SPEC-CORE-001"


class TestPreflightCommand:
    """Test preflight command."""

    def test_preflight_valid_package(self, tmp_path):
        """Test preflight passes for valid package."""
        # Create a minimal valid package
        pkg_dir = tmp_path / "PKG-VALID-001"
        pkg_dir.mkdir()

        lib_dir = pkg_dir / "lib"
        lib_dir.mkdir()
        test_file = lib_dir / "test.py"
        test_file.write_text("# Test module")

        manifest = {
            "package_id": "PKG-VALID-001",
            "assets": [
                {"path": "lib/test.py", "sha256": _sha256(test_file), "classification": "library"},
            ],
        }
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest))

        result = run_pkgutil(
            "preflight", "PKG-VALID-001",
            "--src", str(pkg_dir),
            "--no-strict"
        )

        # Should pass (manifest will be updated with assets)
        assert "PASS" in result.stdout or result.returncode == 0

    def test_preflight_json_output(self, tmp_path):
        """Test preflight JSON output."""
        pkg_dir = tmp_path / "PKG-JSON-001"
        pkg_dir.mkdir()

        manifest = {
            "package_id": "PKG-JSON-001",
            "assets": [],
        }
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest))

        result = run_pkgutil(
            "preflight", "PKG-JSON-001",
            "--src", str(pkg_dir),
            "--json",
            "--no-strict"
        )

        # Should produce valid JSON
        output = json.loads(result.stdout)
        assert "package_id" in output
        assert "results" in output

    def test_preflight_missing_manifest(self, tmp_path):
        """Test preflight fails without manifest."""
        pkg_dir = tmp_path / "PKG-NO-MANIFEST"
        pkg_dir.mkdir()

        result = run_pkgutil(
            "preflight", "PKG-NO-MANIFEST",
            "--src", str(pkg_dir)
        )

        assert result.returncode != 0
        assert "manifest.json not found" in result.stderr


class TestDeltaCommand:
    """Test delta command."""

    def test_delta_generates_csv(self, tmp_path):
        """Test delta generates registry CSV."""
        pkg_dir = tmp_path / "PKG-DELTA-001"
        pkg_dir.mkdir()

        lib_dir = pkg_dir / "lib"
        lib_dir.mkdir()
        (lib_dir / "module.py").write_text("# Module")

        manifest = {
            "package_id": "PKG-DELTA-001",
            "assets": [],
        }
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest))

        result = run_pkgutil(
            "delta", "PKG-DELTA-001",
            "--src", str(pkg_dir)
        )

        assert result.returncode == 0

        # Check output contains CSV format
        assert "file_ownership.csv" in result.stdout
        assert "PKG-DELTA-001" in result.stdout

    def test_delta_to_file(self, tmp_path):
        """Test delta output to file."""
        pkg_dir = tmp_path / "PKG-DELTA-002"
        pkg_dir.mkdir()

        manifest = {
            "package_id": "PKG-DELTA-002",
            "assets": [],
        }
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest))

        output_file = tmp_path / "delta.csv"

        result = run_pkgutil(
            "delta", "PKG-DELTA-002",
            "--src", str(pkg_dir),
            "--output", str(output_file)
        )

        assert result.returncode == 0
        assert output_file.exists()


class TestStageCommand:
    """Test stage command."""

    def test_stage_creates_archive(self, tmp_path):
        """Test stage creates tar.gz archive."""
        pkg_dir = tmp_path / "PKG-STAGE-001"
        pkg_dir.mkdir()

        lib_dir = pkg_dir / "lib"
        lib_dir.mkdir()
        module_file = lib_dir / "module.py"
        module_file.write_text("# Module code")

        manifest = {
            "package_id": "PKG-STAGE-001",
            "version": "1.0.0",
            "assets": [
                {"path": "lib/module.py", "sha256": _sha256(module_file), "classification": "library"},
            ],
        }
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest))

        staging_dir = tmp_path / "staging"

        result = run_pkgutil(
            "stage", "PKG-STAGE-001",
            "--src", str(pkg_dir),
            "--staging-dir", str(staging_dir),
            "--no-strict"
        )

        assert result.returncode == 0, f"Error: {result.stderr}"

        # Check archive created
        archive = staging_dir / "PKG-STAGE-001.tar.gz"
        assert archive.exists()

        # Check digest file
        digest_file = staging_dir / "PKG-STAGE-001.tar.gz.sha256"
        assert digest_file.exists()

        # Check delta file
        delta_file = staging_dir / "PKG-STAGE-001.delta.csv"
        assert delta_file.exists()


class TestCheckFrameworkCommand:
    """Test check-framework command."""

    def test_check_framework_existing(self):
        """Test check-framework with existing framework."""
        result = run_pkgutil(
            "check-framework", "FMWK-000"
        )

        # Should pass since FMWK-000 exists
        assert "FMWK-000" in result.stdout

    def test_check_framework_json(self):
        """Test check-framework JSON output."""
        result = run_pkgutil(
            "check-framework", "FMWK-000",
            "--json"
        )

        output = json.loads(result.stdout)
        assert output["framework_id"] == "FMWK-000"
        assert "passed" in output

    def test_check_framework_nonexistent(self, tmp_path):
        """Test check-framework with nonexistent framework."""
        result = run_pkgutil(
            "check-framework", "FMWK-NONEXISTENT",
            "--src", str(tmp_path)
        )

        # Should fail
        assert result.returncode != 0 or "FAIL" in result.stdout


class TestEndToEndWorkflow:
    """Test full workflow: init -> preflight -> stage."""

    def test_agent_workflow(self, tmp_path):
        """Test complete agent package workflow."""
        staging_dir = tmp_path / "staging"

        # 1. Init agent
        result = run_pkgutil(
            "init-agent", "PKG-E2E-AGENT-001",
            "--framework", "FMWK-000",
            "--output", str(tmp_path / "PKG-E2E-AGENT-001")
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        pkg_dir = tmp_path / "PKG-E2E-AGENT-001"
        assert pkg_dir.exists()

        # Populate manifest assets from generated files (init leaves assets empty)
        manifest_path = pkg_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        assets = []
        for fp in sorted(pkg_dir.rglob("*")):
            if fp.is_dir() or fp.name in ("manifest.json", "signature.json"):
                continue
            if "__pycache__" in str(fp):
                continue
            rel = str(fp.relative_to(pkg_dir))
            assets.append({"path": rel, "sha256": _sha256(fp), "classification": "other"})
        manifest["assets"] = assets
        manifest_path.write_text(json.dumps(manifest, indent=2))

        # 2. Preflight (use --no-strict for isolated testing)
        result = run_pkgutil(
            "preflight", "PKG-E2E-AGENT-001",
            "--src", str(pkg_dir),
            "--no-strict"
        )
        # Should pass with --no-strict
        assert result.returncode == 0, f"Preflight failed: {result.stdout}\n{result.stderr}"

        # 3. Stage (use --no-strict for isolated testing)
        result = run_pkgutil(
            "stage", "PKG-E2E-AGENT-001",
            "--src", str(pkg_dir),
            "--staging-dir", str(staging_dir),
            "--no-strict"
        )
        # Should pass with --no-strict
        assert result.returncode == 0, f"Stage failed: {result.stderr}"
        assert (staging_dir / "PKG-E2E-AGENT-001.tar.gz").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
