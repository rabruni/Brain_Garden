#!/usr/bin/env python3
"""
package_sync.py

Compile packages_registry.csv into a resolved JSON view.
Outputs: registries/compiled/packages.json

Write boundary: output is DERIVED (registries/compiled/).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List

# Add repo root for imports when run from Control_Plane/
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "HOT"))

from kernel.paths import CONTROL_PLANE
from kernel.pristine import assert_write_allowed

PKG_PATH = CONTROL_PLANE / "registries" / "packages_registry.csv"
OUTPUT_PATH = CONTROL_PLANE / "registries" / "compiled" / "packages.json"


def load_rows(path: Path) -> List[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def topo_sort(graph: Dict[str, List[str]]) -> List[str]:
    visited = set()
    order: List[str] = []

    def dfs(node: str):
        if node in visited:
            return
        visited.add(node)
        for dep in graph.get(node, []):
            dfs(dep)
        order.append(node)

    for node in graph:
        dfs(node)
    return order


def build_graph(rows: List[dict]) -> Dict[str, List[str]]:
    graph: Dict[str, List[str]] = {}
    for row in rows:
        deps = [d.split("@")[0].strip() for d in (row.get("deps", "") or "").split(",") if d.strip()]
        graph[row["id"].strip()] = deps
    return graph


def main() -> int:
    rows = load_rows(PKG_PATH)
    graph = build_graph(rows)
    install_order = topo_sort(graph)

    data = {
        "packages": rows,
        "install_order": install_order,
    }

    # Enforce: output is DERIVED path (registries/compiled/)
    assert_write_allowed(OUTPUT_PATH)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
