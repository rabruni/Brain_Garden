"""Boot-time tier materialization.

Ensures tier directories, tier manifests (tier.json), and GENESIS
ledger chains exist before ADMIN starts the session loop.

Idempotent: safe to call on every boot.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from materialize_layout import load_layout_config, materialize
from kernel.ledger_client import LedgerClient
from kernel.tier_manifest import TierManifest


def _ledger_rel_path(layout: dict) -> Path:
    tier_dirs = layout.get("tier_dirs", {})
    ledger_files = layout.get("ledger_files", {})

    ledger_dir = tier_dirs.get("ledger")
    governance_name = ledger_files.get("governance")
    if not ledger_dir or not governance_name:
        raise ValueError("layout.json missing tier_dirs.ledger or ledger_files.governance")

    return Path(str(ledger_dir)) / str(governance_name)


def _ordered_tiers(layout: dict) -> list[tuple[str, str]]:
    tiers = layout.get("tiers")
    if not isinstance(tiers, dict) or not tiers:
        raise ValueError("layout.json missing tiers map")
    return [(str(tier_name), str(dir_name)) for tier_name, dir_name in tiers.items()]


def _ensure_tier_manifests(
    plane_root: Path,
    ordered_tiers: list[tuple[str, str]],
    ledger_rel_path: Path,
) -> None:
    for idx, (tier_name, tier_dir_name) in enumerate(ordered_tiers):
        tier_root = plane_root / tier_dir_name
        manifest_path = tier_root / "tier.json"
        if manifest_path.exists():
            continue

        parent_ledger = None
        if idx > 0:
            parent_dir_name = ordered_tiers[idx - 1][1]
            parent_ledger = str(plane_root / parent_dir_name / ledger_rel_path)

        manifest = TierManifest(
            tier=tier_name,
            tier_root=tier_root,
            ledger_path=ledger_rel_path,
            parent_ledger=parent_ledger,
        )
        manifest.save()


def _ensure_genesis_chain(
    plane_root: Path,
    ordered_tiers: list[tuple[str, str]],
    ledger_rel_path: Path,
) -> None:
    for idx, (tier_name, tier_dir_name) in enumerate(ordered_tiers):
        ledger_path = plane_root / tier_dir_name / ledger_rel_path
        client = LedgerClient(ledger_path=ledger_path)

        if client.count() > 0:
            continue

        parent_ledger = None
        parent_hash = None
        if idx > 0:
            parent_dir_name = ordered_tiers[idx - 1][1]
            parent_ledger_path = plane_root / parent_dir_name / ledger_rel_path
            parent_ledger = str(parent_ledger_path)
            parent_hash = LedgerClient(ledger_path=parent_ledger_path).get_last_entry_hash_value()

        client.write_genesis(
            tier=tier_name,
            plane_root=plane_root,
            parent_ledger=parent_ledger,
            parent_hash=parent_hash,
        )


def boot_materialize(plane_root: Path) -> int:
    """Materialize tier directories, manifests, and GENESIS chains.

    Args:
        plane_root: Path to control plane root.

    Returns:
        0 on success, 1 on config error, 2 on permission error.
    """
    plane_root = Path(plane_root)

    rc = materialize(plane_root)
    if rc != 0:
        return rc

    try:
        layout = load_layout_config(plane_root)
        ordered_tiers = _ordered_tiers(layout)
        ledger_rel_path = _ledger_rel_path(layout)
        _ensure_tier_manifests(plane_root, ordered_tiers, ledger_rel_path)
        _ensure_genesis_chain(plane_root, ordered_tiers, ledger_rel_path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(f"[boot_materialize] ERROR: {exc}", file=sys.stderr)
        return 1
    except PermissionError as exc:
        print(f"[boot_materialize] ERROR: Permission denied: {exc}", file=sys.stderr)
        return 2

    return 0


__all__ = ["boot_materialize"]
