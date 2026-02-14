"""Tests for boot-time tier materialization and ledger path fixes."""

from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest


STAGING_ROOT = Path(__file__).resolve().parents[3]
LAYOUT_SOURCE = STAGING_ROOT / "PKG-LAYOUT-002" / "HOT" / "config" / "layout.json"

for p in [
    STAGING_ROOT / "PKG-BOOT-MATERIALIZE-001" / "HOT" / "scripts",
    STAGING_ROOT / "PKG-LAYOUT-002" / "HOT" / "scripts",
    STAGING_ROOT / "PKG-KERNEL-001" / "HOT",
    STAGING_ROOT / "PKG-KERNEL-001" / "HOT" / "kernel",
]:
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from ledger_client import (  # noqa: E402
    LedgerClient,
    get_session_ledger_path,
    list_session_ledgers,
    read_recent_from_tier,
)


def _import_boot_materialize():
    return importlib.import_module("boot_materialize")


def _setup_plane_root(tmp_path: Path, layout: dict | None = None) -> Path:
    root = tmp_path / "plane"
    cfg_dir = root / "HOT" / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    if layout is None:
        layout = json.loads(LAYOUT_SOURCE.read_text())
    (cfg_dir / "layout.json").write_text(json.dumps(layout, indent=2))
    return root


def _load_layout(root: Path) -> dict:
    return json.loads((root / "HOT" / "config" / "layout.json").read_text())


def _tier_dir_map(layout: dict) -> dict[str, Path]:
    return {tier_name: Path(dir_name) for tier_name, dir_name in layout["tiers"].items()}


def _run_boot(root: Path) -> int:
    module = _import_boot_materialize()
    return module.boot_materialize(root)


def _ledger_path(root: Path, tier_dir: Path) -> Path:
    return root / tier_dir / "ledger" / "governance.jsonl"


def _read_tier_json(root: Path, tier_dir: Path) -> dict:
    return json.loads((root / tier_dir / "tier.json").read_text())


def _write_minimal_entry(path: Path, submission_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "event_type": "TEST",
                "submission_id": submission_id,
                "decision": "OK",
                "reason": "test",
            }
        )
        + "\n"
    )


class TestBootMaterialize:
    def test_fresh_boot_creates_ho2_directories(self, tmp_path: Path):
        root = _setup_plane_root(tmp_path)
        layout = _load_layout(root)
        tiers = _tier_dir_map(layout)

        rc = _run_boot(root)

        assert rc == 0
        for subdir in layout["tier_dirs"].values():
            assert (root / tiers["HO2"] / subdir).is_dir()

    def test_fresh_boot_creates_ho1_directories(self, tmp_path: Path):
        root = _setup_plane_root(tmp_path)
        layout = _load_layout(root)
        tiers = _tier_dir_map(layout)

        rc = _run_boot(root)

        assert rc == 0
        for subdir in layout["tier_dirs"].values():
            assert (root / tiers["HO1"] / subdir).is_dir()

    def test_fresh_boot_creates_ho2_tier_json(self, tmp_path: Path):
        root = _setup_plane_root(tmp_path)
        layout = _load_layout(root)

        _run_boot(root)

        assert (root / layout["tiers"]["HO2"] / "tier.json").exists()

    def test_fresh_boot_creates_ho1_tier_json(self, tmp_path: Path):
        root = _setup_plane_root(tmp_path)
        layout = _load_layout(root)

        _run_boot(root)

        assert (root / layout["tiers"]["HO1"] / "tier.json").exists()

    def test_ho2_tier_json_parent_is_hot(self, tmp_path: Path):
        root = _setup_plane_root(tmp_path)
        layout = _load_layout(root)
        tiers = _tier_dir_map(layout)

        _run_boot(root)

        ho2 = _read_tier_json(root, tiers["HO2"])
        assert ho2["parent_ledger"] == str(_ledger_path(root, tiers["HOT"]))

    def test_ho1_tier_json_parent_is_ho2(self, tmp_path: Path):
        root = _setup_plane_root(tmp_path)
        layout = _load_layout(root)
        tiers = _tier_dir_map(layout)

        _run_boot(root)

        ho1 = _read_tier_json(root, tiers["HO1"])
        assert ho1["parent_ledger"] == str(_ledger_path(root, tiers["HO2"]))

    def test_hot_genesis_created_if_empty(self, tmp_path: Path):
        root = _setup_plane_root(tmp_path)
        layout = _load_layout(root)
        tiers = _tier_dir_map(layout)

        _run_boot(root)

        entries = LedgerClient(ledger_path=_ledger_path(root, tiers["HOT"])).read_all()
        assert entries
        assert entries[0].event_type == "GENESIS"

    def test_ho2_genesis_created(self, tmp_path: Path):
        root = _setup_plane_root(tmp_path)
        layout = _load_layout(root)
        tiers = _tier_dir_map(layout)

        _run_boot(root)

        entries = LedgerClient(ledger_path=_ledger_path(root, tiers["HO2"])).read_all()
        assert entries
        assert entries[0].event_type == "GENESIS"

    def test_ho1_genesis_created(self, tmp_path: Path):
        root = _setup_plane_root(tmp_path)
        layout = _load_layout(root)
        tiers = _tier_dir_map(layout)

        _run_boot(root)

        entries = LedgerClient(ledger_path=_ledger_path(root, tiers["HO1"])).read_all()
        assert entries
        assert entries[0].event_type == "GENESIS"

    def test_genesis_chain_ho2_to_hot(self, tmp_path: Path):
        root = _setup_plane_root(tmp_path)
        layout = _load_layout(root)
        tiers = _tier_dir_map(layout)

        _run_boot(root)

        hot_client = LedgerClient(ledger_path=_ledger_path(root, tiers["HOT"]))
        ho2_client = LedgerClient(ledger_path=_ledger_path(root, tiers["HO2"]))
        ho2_genesis = ho2_client.read_all()[0]

        assert ho2_genesis.metadata["parent_hash"] == hot_client.get_last_entry_hash_value()

    def test_genesis_chain_ho1_to_ho2(self, tmp_path: Path):
        root = _setup_plane_root(tmp_path)
        layout = _load_layout(root)
        tiers = _tier_dir_map(layout)

        _run_boot(root)

        ho2_client = LedgerClient(ledger_path=_ledger_path(root, tiers["HO2"]))
        ho1_client = LedgerClient(ledger_path=_ledger_path(root, tiers["HO1"]))
        ho1_genesis = ho1_client.read_all()[0]

        assert ho1_genesis.metadata["parent_hash"] == ho2_client.get_last_entry_hash_value()

    def test_chain_verification_passes(self, tmp_path: Path):
        root = _setup_plane_root(tmp_path)
        layout = _load_layout(root)
        tiers = _tier_dir_map(layout)

        _run_boot(root)

        ho2_client = LedgerClient(ledger_path=_ledger_path(root, tiers["HO2"]))
        ho1_client = LedgerClient(ledger_path=_ledger_path(root, tiers["HO1"]))

        ok_ho2, _ = ho2_client.verify_chain_link(_ledger_path(root, tiers["HOT"]))
        ok_ho1, _ = ho1_client.verify_chain_link(_ledger_path(root, tiers["HO2"]))

        assert ok_ho2 is True
        assert ok_ho1 is True

    def test_idempotent_second_boot(self, tmp_path: Path):
        root = _setup_plane_root(tmp_path)
        layout = _load_layout(root)
        tiers = _tier_dir_map(layout)

        rc1 = _run_boot(root)
        rc2 = _run_boot(root)

        assert rc1 == 0
        assert rc2 == 0
        for tier_dir in tiers.values():
            entries = LedgerClient(ledger_path=_ledger_path(root, tier_dir)).read_all()
            assert len([e for e in entries if e.event_type == "GENESIS"]) == 1

    def test_partial_recovery_missing_ho1_only(self, tmp_path: Path):
        root = _setup_plane_root(tmp_path)
        layout = _load_layout(root)
        tiers = _tier_dir_map(layout)

        _run_boot(root)
        ho2_before = len(LedgerClient(ledger_path=_ledger_path(root, tiers["HO2"])).read_all())

        shutil.rmtree(root / tiers["HO1"])

        rc = _run_boot(root)

        assert rc == 0
        assert (root / tiers["HO1"] / "tier.json").exists()
        ho2_after = len(LedgerClient(ledger_path=_ledger_path(root, tiers["HO2"])).read_all())
        assert ho2_after == ho2_before

    def test_paths_derived_from_layout_json(self, tmp_path: Path):
        layout = json.loads(LAYOUT_SOURCE.read_text())
        layout["tiers"] = {
            "HOT": "TOP",
            "HO2": "MIDDLE",
            "HO1": "BOTTOM",
        }
        remapped_hot_dirs = {}
        for key, value in layout["hot_dirs"].items():
            if value == "HOT":
                remapped_hot_dirs[key] = "TOP"
            elif value.startswith("HOT/"):
                remapped_hot_dirs[key] = "TOP/" + value.split("/", 1)[1]
            else:
                remapped_hot_dirs[key] = value
        layout["hot_dirs"] = remapped_hot_dirs

        root = _setup_plane_root(tmp_path, layout=layout)

        rc = _run_boot(root)

        assert rc == 0
        assert (root / "TOP").exists()
        assert (root / "MIDDLE").exists()
        assert (root / "BOTTOM").exists()
        assert not (root / "HO2").exists()
        assert not (root / "HO1").exists()

    def test_returns_zero_on_success(self, tmp_path: Path):
        root = _setup_plane_root(tmp_path)

        rc = _run_boot(root)

        assert rc == 0

    def test_returns_one_on_missing_layout_json(self, tmp_path: Path):
        root = tmp_path / "plane"
        root.mkdir(parents=True, exist_ok=True)

        rc = _run_boot(root)

        assert rc == 1


class TestLedgerPathFixes:
    def test_read_recent_from_tier_correct_path(self, tmp_path: Path):
        root = tmp_path / "plane"
        expected = root / "HO2" / "ledger" / "governance.jsonl"
        legacy = root / "planes" / "ho2" / "ledger" / "governance.jsonl"

        _write_minimal_entry(expected, "expected-ho2")
        _write_minimal_entry(legacy, "wrong-legacy")

        entries = read_recent_from_tier("HO2", limit=10, root=root)

        assert entries
        assert entries[-1].submission_id == "expected-ho2"

    def test_read_recent_from_tier_hot_path(self, tmp_path: Path):
        root = tmp_path / "plane"
        expected = root / "HOT" / "ledger" / "governance.jsonl"
        wrong = root / "ledger" / "governance.jsonl"

        _write_minimal_entry(expected, "expected-hot")
        _write_minimal_entry(wrong, "wrong-root")

        entries = read_recent_from_tier("hot", limit=10, root=root)

        assert entries
        assert entries[-1].submission_id == "expected-hot"

    def test_get_session_ledger_path_correct(self):
        path = get_session_ledger_path("ho1", "SES-001", root=Path("/cp"))

        assert str(path) == "/cp/HO1/sessions/SES-001/ledger/exec.jsonl"
        assert "planes" not in str(path)

    def test_list_session_ledgers_correct_path(self, tmp_path: Path):
        root = tmp_path / "plane"

        (root / "HO2" / "sessions" / "SES-001" / "ledger").mkdir(parents=True, exist_ok=True)
        (root / "HO2" / "sessions" / "SES-001" / "ledger" / "exec.jsonl").write_text("")
        (root / "HO2" / "sessions" / "SES-001" / "ledger" / "evidence.jsonl").write_text("")

        (root / "planes" / "ho2" / "sessions" / "SES-LEGACY" / "ledger").mkdir(parents=True, exist_ok=True)
        (root / "planes" / "ho2" / "sessions" / "SES-LEGACY" / "ledger" / "exec.jsonl").write_text("")
        (root / "planes" / "ho2" / "sessions" / "SES-LEGACY" / "ledger" / "evidence.jsonl").write_text("")

        sessions = list_session_ledgers("ho2", root=root)
        session_ids = {s["session_id"] for s in sessions}

        assert "SES-001" in session_ids
        assert "SES-LEGACY" not in session_ids
