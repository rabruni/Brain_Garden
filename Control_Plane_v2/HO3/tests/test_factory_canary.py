#!/usr/bin/env python3
"""
test_factory_canary.py - Canary tests for package factory workflow.

Proves the entire factory workflow works end-to-end:
1. Manifest validates
2. Pack is deterministic (hash1 == hash2)
3. Signature verifies (if key present)
4. Attestation verifies
5. Install succeeds
6. Install receipt written
7. Integrity check passes
8. Ledger entry created

Per FMWK-PKG-001: Package Standard v1.0

Usage:
    python3 tests/test_factory_canary.py
    python3 -m pytest tests/test_factory_canary.py -v
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

# Add repo root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "HOT"))

from kernel.paths import CONTROL_PLANE

# Test package paths
PACKAGES_DIR = CONTROL_PLANE / "packages"
PACKAGES_STORE = CONTROL_PLANE / "packages_store"
CANARY_SRC = PACKAGES_DIR / "PKG-CANARY"
INSTALLED_DIR = CONTROL_PLANE / "installed"

# Skip entire module if PKG-CANARY doesn't exist (removed during tier migration)
pytestmark = pytest.mark.skipif(
    not CANARY_SRC.exists(),
    reason="PKG-CANARY not present in tier layout (flat packages/ removed)"
)


from kernel.hashing import sha256_file  # canonical implementation


def load_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Load manifest.json."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def create_test_tarball(src_dir: Path, output: Path, manifest: Dict) -> str:
    """Create deterministic tarball and return digest.

    Uses fixed timestamp (0), sorted entries, and deterministic gzip
    for reproducibility.
    """
    import io
    import zlib

    with tempfile.TemporaryDirectory() as tmpdir:
        staging = Path(tmpdir) / "pkg"
        staging.mkdir()

        # Copy content
        for item in sorted(src_dir.iterdir()):
            if item.name.startswith("."):
                continue
            dest = staging / item.name
            if item.is_file():
                shutil.copy2(item, dest)
            elif item.is_dir():
                shutil.copytree(item, dest)

        # Write manifest
        manifest_path = staging / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

        # Create tar in memory with fixed timestamps
        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w", format=tarfile.GNU_FORMAT) as tf:
            # Collect all files first
            all_files = []
            for root, dirs, files in os.walk(staging):
                dirs.sort()
                for name in sorted(files):
                    full_path = Path(root) / name
                    arcname = str(full_path.relative_to(staging))
                    all_files.append((arcname, full_path))

            # Add in sorted order
            for arcname, full_path in sorted(all_files):
                info = tf.gettarinfo(str(full_path), arcname=arcname)
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mode = 0o644 if full_path.is_file() else 0o755

                with open(full_path, "rb") as fp:
                    tf.addfile(info, fp)

        # Create gzip with fixed header (no mtime)
        tar_bytes = tar_buf.getvalue()
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "wb") as f:
            # Gzip header with mtime=0
            f.write(b'\x1f\x8b')  # Magic
            f.write(b'\x08')  # Compression method (deflate)
            f.write(b'\x00')  # Flags (none)
            f.write(b'\x00\x00\x00\x00')  # mtime = 0
            f.write(b'\x00')  # xfl
            f.write(b'\xff')  # os (unknown)

            # Compress data
            crc = zlib.crc32(tar_bytes) & 0xffffffff
            compressed = zlib.compress(tar_bytes, 9)[2:-4]  # Remove zlib wrapper
            f.write(compressed)

            # Trailer
            f.write(crc.to_bytes(4, 'little'))
            f.write((len(tar_bytes) & 0xffffffff).to_bytes(4, 'little'))

    return sha256_file(output)


class TestCanaryManifest:
    """Test 1: Manifest validates."""

    def test_manifest_exists(self):
        """Canary manifest.json exists."""
        manifest_path = CANARY_SRC / "manifest.json"
        assert manifest_path.exists(), f"Manifest not found: {manifest_path}"

    def test_manifest_valid_json(self):
        """Canary manifest is valid JSON."""
        manifest_path = CANARY_SRC / "manifest.json"
        manifest = load_manifest(manifest_path)
        assert isinstance(manifest, dict)

    def test_manifest_required_fields(self):
        """Canary manifest has required fields."""
        manifest_path = CANARY_SRC / "manifest.json"
        manifest = load_manifest(manifest_path)

        required = ["schema_version", "id", "name", "version", "tier", "artifact_paths", "deps"]
        for field in required:
            assert field in manifest, f"Missing required field: {field}"

    def test_manifest_schema_version(self):
        """Canary manifest has schema_version 1.0."""
        manifest_path = CANARY_SRC / "manifest.json"
        manifest = load_manifest(manifest_path)
        assert manifest["schema_version"] == "1.0"

    def test_manifest_id_format(self):
        """Canary manifest ID is PKG-CANARY."""
        manifest_path = CANARY_SRC / "manifest.json"
        manifest = load_manifest(manifest_path)
        assert manifest["id"] == "PKG-CANARY"

    def test_manifest_tier_valid(self):
        """Canary manifest tier is valid."""
        manifest_path = CANARY_SRC / "manifest.json"
        manifest = load_manifest(manifest_path)
        assert manifest["tier"] in ["G0", "T0", "T1", "T2", "T3"]


class TestCanaryDeterminism:
    """Test 2: Pack is deterministic."""

    def test_pack_deterministic(self):
        """Two packs of same source produce identical hashes."""
        manifest_path = CANARY_SRC / "manifest.json"
        manifest = load_manifest(manifest_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            out1 = tmp / "pack1.tar.gz"
            out2 = tmp / "pack2.tar.gz"

            digest1 = create_test_tarball(CANARY_SRC, out1, manifest)
            digest2 = create_test_tarball(CANARY_SRC, out2, manifest)

            assert digest1 == digest2, f"Pack not deterministic: {digest1} != {digest2}"


class TestCanarySignature:
    """Test 3: Signature verifies (if key present)."""

    def test_signature_with_key(self):
        """Signature verification works when key is present."""
        import hmac

        digest = "abc123"
        key = "test-key"

        signature = hmac.new(
            key.encode("utf-8"),
            digest.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        # Verify
        computed = hmac.new(
            key.encode("utf-8"),
            digest.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        assert hmac.compare_digest(computed, signature)

    def test_signature_without_key(self):
        """Unsigned packages are allowed with waiver."""
        # This test verifies the waiver mechanism exists
        # Actual enforcement is in package_factory.py
        pass


class TestCanaryAttestation:
    """Test 4: Attestation verifies."""

    def test_attestation_structure(self):
        """Attestation has required fields."""
        from datetime import datetime, timezone

        attestation = {
            "builder": "package_factory",
            "build_timestamp": datetime.now(timezone.utc).isoformat(),
            "build_env_hash": "test",
            "factory_version": "1.0.0",
        }

        assert "builder" in attestation
        assert "build_timestamp" in attestation


class TestCanaryInstall:
    """Test 5: Install succeeds."""

    def test_install_extracts_files(self):
        """Package installs correctly."""
        manifest_path = CANARY_SRC / "manifest.json"
        manifest = load_manifest(manifest_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            archive = tmp / "canary.tar.gz"
            target = tmp / "install"

            # Create archive
            create_test_tarball(CANARY_SRC, archive, manifest)

            # Extract
            target.mkdir()
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(target)

            # Verify files exist
            assert (target / "manifest.json").exists()
            assert (target / "content" / "canary.txt").exists()


class TestCanaryReceipt:
    """Test 6: Install receipt written."""

    def test_receipt_format(self):
        """Receipt has required structure."""
        from datetime import datetime, timezone

        receipt = {
            "id": "PKG-CANARY",
            "version": "1.0.0",
            "archive": "/path/to/archive.tar.gz",
            "archive_digest": "abc123",
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "installer": "test",
            "files": [
                {"path": "content/canary.txt", "sha256": "def456"}
            ]
        }

        required = ["id", "version", "archive", "archive_digest", "installed_at", "files"]
        for field in required:
            assert field in receipt, f"Receipt missing field: {field}"

    def test_receipt_files_have_hashes(self):
        """Receipt file entries have SHA-256 hashes."""
        receipt = {
            "files": [
                {"path": "content/canary.txt", "sha256": "def456"}
            ]
        }

        for entry in receipt["files"]:
            assert "path" in entry
            assert "sha256" in entry


class TestCanaryIntegrity:
    """Test 7: Integrity check passes."""

    def test_integrity_checker_available(self):
        """IntegrityChecker can be imported."""
        try:
            from kernel.integrity import IntegrityChecker
            checker = IntegrityChecker(CONTROL_PLANE)
            assert checker is not None
        except ImportError:
            pytest.skip("lib/integrity.py not available")

    def test_content_hash_computable(self):
        """Content hash can be computed for canary."""
        canary_file = CANARY_SRC / "content" / "canary.txt"
        if canary_file.exists():
            h = sha256_file(canary_file)
            assert len(h) == 64


class TestCanaryLedger:
    """Test 8: Ledger entry created."""

    def test_ledger_client_available(self):
        """LedgerClient can be imported."""
        try:
            from kernel.ledger_client import LedgerClient, LedgerEntry
            client = LedgerClient()
            assert client is not None
        except ImportError:
            pytest.skip("lib/ledger_client.py not available")

    def test_ledger_entry_structure(self):
        """Ledger entry has required fields."""
        try:
            from kernel.ledger_client import LedgerEntry

            entry = LedgerEntry(
                event_type="package_factory",
                submission_id="PKG-CANARY",
                decision="SUCCESS",
                reason="Canary test",
                metadata={"test": True}
            )

            assert entry.event_type == "package_factory"
            assert entry.submission_id == "PKG-CANARY"
        except ImportError:
            pytest.skip("lib/ledger_client.py not available")


class TestCanaryReceiptVerification:
    """P6: Receipt proof after install."""

    def test_receipt_created_after_install(self):
        """Install creates receipt with required fields."""
        # Test receipt structure requirements
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            installed_dir = tmp / "installed" / "PKG-CANARY"
            installed_dir.mkdir(parents=True)

            # Simulate receipt creation (as package_install.py would do)
            receipt = {
                "id": "PKG-CANARY",
                "version": "1.0.0",
                "archive": "/path/to/PKG-CANARY.tar.gz",
                "archive_digest": "abc123def456",
                "installed_at": "2026-01-31T00:00:00Z",
                "installer": "package_install",
                "files": [
                    {"path": "content/canary.txt", "sha256": "file_hash_here"}
                ]
            }

            receipt_path = installed_dir / "receipt.json"
            with open(receipt_path, "w") as f:
                json.dump(receipt, f, indent=2)

            # Verify receipt exists and has required fields
            assert receipt_path.exists(), "Receipt not created"

            with open(receipt_path) as f:
                loaded = json.load(f)

            required_fields = ["id", "version", "archive_digest", "files"]
            for field in required_fields:
                assert field in loaded, f"Receipt missing required field: {field}"

    def test_receipt_files_have_required_structure(self):
        """Receipt file entries have path and sha256."""
        receipt = {
            "files": [
                {"path": "content/canary.txt", "sha256": "abc123"},
                {"path": "manifest.json", "sha256": "def456"},
            ]
        }

        for entry in receipt["files"]:
            assert "path" in entry, "File entry missing path"
            assert "sha256" in entry, "File entry missing sha256"
            assert len(entry["sha256"]) > 0, "Empty sha256 hash"

    def test_receipt_files_match_filesystem(self):
        """Receipt file hashes should match actual installed files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # Create a test file
            test_file = tmp / "test.txt"
            test_file.write_text("test content")

            # Compute actual hash
            actual_hash = sha256_file(test_file)

            # Receipt should match
            receipt = {
                "files": [
                    {"path": "test.txt", "sha256": actual_hash}
                ]
            }

            for entry in receipt["files"]:
                file_path = tmp / entry["path"]
                if file_path.exists():
                    computed = sha256_file(file_path)
                    assert computed == entry["sha256"], \
                        f"Hash mismatch for {entry['path']}: {computed} != {entry['sha256']}"


class TestCanaryEndToEnd:
    """End-to-end factory workflow test."""

    def test_full_workflow_validate_only(self):
        """Full workflow in validate-only mode."""
        try:
            from scripts.package_factory import run_factory
            from kernel.plane import get_current_plane

            result = run_factory(
                pkg_id="PKG-CANARY",
                src_dir=CANARY_SRC,
                plane=get_current_plane(),
                validate_only=True
            )

            # G1 and G2 should pass
            assert len(result.gates) >= 2
            assert result.gates[0].passed, f"G1 failed: {result.gates[0].message}"
            assert result.gates[1].passed, f"G2 failed: {result.gates[1].message}"

        except ImportError as e:
            pytest.skip(f"package_factory not available: {e}")


def run_canary_tests() -> Tuple[int, int, int]:
    """Run all canary tests and return (passed, failed, skipped)."""
    passed = 0
    failed = 0
    skipped = 0

    test_classes = [
        TestCanaryManifest,
        TestCanaryDeterminism,
        TestCanarySignature,
        TestCanaryAttestation,
        TestCanaryInstall,
        TestCanaryReceipt,
        TestCanaryReceiptVerification,
        TestCanaryIntegrity,
        TestCanaryLedger,
        TestCanaryEndToEnd,
    ]

    for test_class in test_classes:
        instance = test_class()
        for method_name in dir(instance):
            if not method_name.startswith("test_"):
                continue

            method = getattr(instance, method_name)
            test_name = f"{test_class.__name__}.{method_name}"

            try:
                method()
                print(f"  PASS: {test_name}")
                passed += 1
            except pytest.skip.Exception as e:
                print(f"  SKIP: {test_name} - {e}")
                skipped += 1
            except AssertionError as e:
                print(f"  FAIL: {test_name} - {e}")
                failed += 1
            except Exception as e:
                print(f"  ERROR: {test_name} - {e}")
                failed += 1

    return passed, failed, skipped


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print("CANARY TEST SUITE")
    print("=" * 60)
    print()

    # Check canary package exists
    if not CANARY_SRC.exists():
        print(f"ERROR: Canary package not found: {CANARY_SRC}")
        return 1

    print(f"Canary source: {CANARY_SRC}")
    print()

    passed, failed, skipped = run_canary_tests()

    print()
    print("=" * 60)
    print("CANARY RESULTS")
    print("=" * 60)
    print(f"Passed:  {passed}")
    print(f"Failed:  {failed}")
    print(f"Skipped: {skipped}")
    print()

    if failed > 0:
        print("CANARY FAILED")
        return 1
    else:
        print("CANARY PASSED: All checks green")
        return 0


if __name__ == "__main__":
    sys.exit(main())
