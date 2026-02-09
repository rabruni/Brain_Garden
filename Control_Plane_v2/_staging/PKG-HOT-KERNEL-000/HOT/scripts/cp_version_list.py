#!/usr/bin/env python3
"""
cp_version_list.py - List available Control Plane checkpoints.

Usage:
    python3 scripts/cp_version_list.py

Outputs table of version_id, timestamp, label, registry_hash, manifest_hash, registry_snapshot path.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.paths import CONTROL_PLANE

VERSIONS_DIR = CONTROL_PLANE / "versions"


def main() -> int:
    if not VERSIONS_DIR.exists():
        print("No versions directory.")
        return 0

    entries = []
    for meta_path in sorted(VERSIONS_DIR.glob("VER-*.json")):
        data = json.loads(meta_path.read_text())
        entries.append({
            "version_id": data.get("version_id"),
            "timestamp": data.get("timestamp"),
            "label": data.get("label", ""),
            "registry_hash": data.get("registry_hash", ""),
            "manifest_hash": data.get("manifest_hash", ""),
            "snapshot": data.get("registry_snapshot", ""),
        })

    if not entries:
        print("No checkpoints found.")
        return 0

    # simple table
    cols = ["version_id", "timestamp", "label", "registry_hash", "manifest_hash", "snapshot"]
    print("\t".join(cols))
    for e in entries:
        print("\t".join(e.get(c, "") or "" for c in cols))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
