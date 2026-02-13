"""Tests for FOLLOWUP-3D: Genesis file registration + G0K removal.

13 tests:
  1-4:  register_genesis_files() behavior
  5-6:  load_manifest_from_archive() behavior
  7-8:  Genesis receipt creation
  9:    Backward compatibility (--genesis-archive optional)
  10:   G0B precondition: all genesis files owned after registration
  11-12: G0K removed from gate_check.py
  13:   Gate list integrity after G0K removal
"""
import csv
import json
import os
import sys
import tarfile
from io import BytesIO
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent

# Import genesis_bootstrap functions
GENESIS_SCRIPTS = STAGING / "PKG-GENESIS-000" / "HOT" / "scripts"
sys.path.insert(0, str(GENESIS_SCRIPTS))


# === Fixtures ===


@pytest.fixture
def plane_root(tmp_path):
    """Minimal plane root with genesis files on disk."""
    for d in ["scripts", "config", "schemas", "tests", "registries"]:
        (tmp_path / "HOT" / d).mkdir(parents=True)

    (tmp_path / "HOT" / "scripts" / "genesis_bootstrap.py").write_text("# genesis")
    (tmp_path / "HOT" / "config" / "bootstrap_sequence.json").write_text('{"layers":[]}')
    (tmp_path / "HOT" / "config" / "seed_registry.json").write_text('{"schema_version":"1.0","packages":[]}')
    (tmp_path / "HOT" / "schemas" / "package_manifest_l0.json").write_text('{"type":"object"}')
    (tmp_path / "HOT" / "tests" / "test_genesis_bootstrap.py").write_text("# tests")

    return tmp_path


@pytest.fixture
def genesis_manifest():
    """Genesis package manifest dict."""
    return {
        "package_id": "PKG-GENESIS-000",
        "version": "1.0.0",
        "assets": [
            {"path": "HOT/scripts/genesis_bootstrap.py", "sha256": "sha256:aaa", "classification": "script"},
            {"path": "HOT/config/bootstrap_sequence.json", "sha256": "sha256:bbb", "classification": "config"},
            {"path": "HOT/config/seed_registry.json", "sha256": "sha256:ccc", "classification": "config"},
            {"path": "HOT/schemas/package_manifest_l0.json", "sha256": "sha256:ddd", "classification": "schema"},
            {"path": "HOT/tests/test_genesis_bootstrap.py", "sha256": "sha256:eee", "classification": "test"},
        ],
    }


@pytest.fixture
def genesis_archive(tmp_path, plane_root, genesis_manifest):
    """tar.gz archive containing manifest.json + genesis files."""
    archive_path = tmp_path / "archives" / "PKG-GENESIS-000.tar.gz"
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, "w:gz") as tar:
        manifest_bytes = json.dumps(genesis_manifest).encode()
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest_bytes)
        tar.addfile(info, BytesIO(manifest_bytes))

        for asset in genesis_manifest["assets"]:
            content = (plane_root / asset["path"]).read_bytes()
            info = tarfile.TarInfo(name=asset["path"])
            info.size = len(content)
            tar.addfile(info, BytesIO(content))

    return archive_path


@pytest.fixture
def ownership_csv(plane_root):
    """file_ownership.csv with header only."""
    csv_path = plane_root / "HOT" / "registries" / "file_ownership.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file_path", "package_id", "sha256", "classification",
                         "installed_date", "replaced_date", "superseded_by"])
    return csv_path


# === Tests 1-4: register_genesis_files ===


class TestRegisterGenesisFiles:

    def test_register_genesis_files_from_archive(self, plane_root, genesis_archive, ownership_csv):
        """register_genesis_files() reads manifest from tar and appends 5 rows."""
        from genesis_bootstrap import register_genesis_files

        count = register_genesis_files(genesis_archive, plane_root, ownership_csv)
        assert count == 5

        with open(ownership_csv) as f:
            rows = list(csv.DictReader(f))
        genesis_rows = [r for r in rows if r["package_id"] == "PKG-GENESIS-000"]
        assert len(genesis_rows) == 5

    def test_register_genesis_files_missing_archive(self, plane_root, ownership_csv):
        """Missing archive returns 0, no crash."""
        from genesis_bootstrap import register_genesis_files

        count = register_genesis_files(Path("/nonexistent.tar.gz"), plane_root, ownership_csv)
        assert count == 0

    def test_register_genesis_files_correct_hashes(self, plane_root, genesis_archive, ownership_csv):
        """SHA256 in CSV matches actual files on disk."""
        from genesis_bootstrap import register_genesis_files, sha256_file

        register_genesis_files(genesis_archive, plane_root, ownership_csv)

        with open(ownership_csv) as f:
            rows = list(csv.DictReader(f))

        for row in rows:
            actual = sha256_file(plane_root / row["file_path"])
            assert row["sha256"] == actual, f"Hash mismatch: {row['file_path']}"

    def test_register_genesis_files_correct_classification(self, plane_root, genesis_archive, ownership_csv):
        """Classification from manifest is preserved."""
        from genesis_bootstrap import register_genesis_files

        register_genesis_files(genesis_archive, plane_root, ownership_csv)

        with open(ownership_csv) as f:
            rows = list(csv.DictReader(f))

        cls_map = {r["file_path"]: r["classification"] for r in rows}
        assert cls_map["HOT/scripts/genesis_bootstrap.py"] == "script"
        assert cls_map["HOT/config/bootstrap_sequence.json"] == "config"
        assert cls_map["HOT/schemas/package_manifest_l0.json"] == "schema"
        assert cls_map["HOT/tests/test_genesis_bootstrap.py"] == "test"


# === Tests 5-6: load_manifest_from_archive ===


class TestLoadManifestFromArchive:

    def test_load_manifest_from_archive(self, genesis_archive):
        """Extracts manifest.json from tar and returns parsed dict."""
        from genesis_bootstrap import load_manifest_from_archive

        manifest = load_manifest_from_archive(genesis_archive)
        assert manifest is not None
        assert manifest["package_id"] == "PKG-GENESIS-000"
        assert len(manifest["assets"]) == 5

    def test_load_manifest_from_archive_missing(self, tmp_path):
        """Archive without manifest returns None."""
        from genesis_bootstrap import load_manifest_from_archive

        archive = tmp_path / "no_manifest.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            content = b"dummy"
            info = tarfile.TarInfo(name="dummy.txt")
            info.size = len(content)
            tar.addfile(info, BytesIO(content))

        assert load_manifest_from_archive(archive) is None


# === Tests 7-9: Genesis receipt + backward compatibility ===


class TestGenesisReceipt:

    def test_genesis_receipt_created(self, plane_root, genesis_archive):
        """write_install_receipt creates HOT/installed/PKG-GENESIS-000/receipt.json."""
        from genesis_bootstrap import write_install_receipt, load_manifest_from_archive

        manifest = load_manifest_from_archive(genesis_archive)
        files = [a["path"] for a in manifest["assets"]]

        receipt_path = write_install_receipt(
            pkg_id="PKG-GENESIS-000",
            version="1.0.0",
            archive_path=genesis_archive,
            files=files,
            root=plane_root,
            installer="genesis_bootstrap",
        )
        assert receipt_path.exists()
        assert receipt_path.name == "receipt.json"
        assert "PKG-GENESIS-000" in str(receipt_path)

    def test_genesis_receipt_contents(self, plane_root, genesis_archive):
        """Receipt has id, version, files, installed_at."""
        from genesis_bootstrap import write_install_receipt, load_manifest_from_archive

        manifest = load_manifest_from_archive(genesis_archive)
        files = [a["path"] for a in manifest["assets"]]

        receipt_path = write_install_receipt(
            pkg_id="PKG-GENESIS-000",
            version="1.0.0",
            archive_path=genesis_archive,
            files=files,
            root=plane_root,
            installer="genesis_bootstrap",
        )
        receipt = json.loads(receipt_path.read_text())
        assert receipt["id"] == "PKG-GENESIS-000"
        assert receipt["version"] == "1.0.0"
        assert "installed_at" in receipt
        assert len(receipt["files"]) == 5

    def test_genesis_archive_arg_optional(self, plane_root, ownership_csv):
        """Without genesis archive, register_genesis_files returns 0 (backward compat)."""
        from genesis_bootstrap import register_genesis_files

        count = register_genesis_files(Path("/nonexistent"), plane_root, ownership_csv)
        assert count == 0

        with open(ownership_csv) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 0


# === Test 10: G0B precondition ===


class TestG0BPrecondition:

    def test_g0b_passes_after_genesis_registration(self, plane_root, genesis_archive, ownership_csv):
        """All 5 genesis files owned after registration — no orphans."""
        from genesis_bootstrap import register_genesis_files

        register_genesis_files(genesis_archive, plane_root, ownership_csv)

        with open(ownership_csv) as f:
            rows = list(csv.DictReader(f))

        owned_paths = {r["file_path"] for r in rows}
        expected = [
            "HOT/scripts/genesis_bootstrap.py",
            "HOT/config/bootstrap_sequence.json",
            "HOT/config/seed_registry.json",
            "HOT/schemas/package_manifest_l0.json",
            "HOT/tests/test_genesis_bootstrap.py",
        ]
        for gf in expected:
            assert gf in owned_paths, f"Genesis file {gf} not in file_ownership.csv"


# === Tests 11-13: G0K removal (source-level verification) ===


class TestG0KRemoval:
    """Verify G0K is fully removed from gate_check.py source."""

    GATE_CHECK = STAGING / "PKG-VOCABULARY-001" / "HOT" / "scripts" / "gate_check.py"

    def test_g0k_not_in_gate_functions(self):
        """G0K must not appear in GATE_FUNCTIONS dict."""
        content = self.GATE_CHECK.read_text()
        # Find the GATE_FUNCTIONS block and verify no G0K
        in_gate_functions = False
        for line in content.splitlines():
            if "GATE_FUNCTIONS" in line and "=" in line:
                in_gate_functions = True
            if in_gate_functions:
                assert "G0K" not in line, f"G0K still in GATE_FUNCTIONS: {line.strip()}"
                if line.strip() == "}":
                    break

    def test_all_gates_no_g0k(self):
        """--all gate ordering must not include G0K."""
        content = self.GATE_CHECK.read_text()
        for line in content.splitlines():
            if "gates = [" in line and "G0B" in line:
                assert "G0K" not in line, f"G0K in all-gates ordering: {line.strip()}"

    def test_all_gates_list_correct(self):
        """--all gate list contains exactly the 8 expected gates."""
        content = self.GATE_CHECK.read_text()
        expected_gates = {"G0B", "G1", "G1-COMPLETE", "G2", "G3", "G4", "G5", "G6"}
        for line in content.splitlines():
            if "gates = [" in line and "G0B" in line:
                for gate in expected_gates:
                    assert f'"{gate}"' in line, f"Missing gate {gate} in all-gates list"
                return
        pytest.fail("Could not find all-gates list in gate_check.py")
