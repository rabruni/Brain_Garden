#!/usr/bin/env python3
"""
Validate Packages Registry

Checks:
- Schema/enums
- Required fields (version, source, source_type, digest*)
- Semver + constraint parsing
- Dependency existence, cycles, conflicts
- Platform/arch enums
- Content hash recomputation

Usage:
    python3 scripts/validate_packages.py
    python3 scripts/validate_packages.py --root /path/to/plane
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Add repo root for imports when run from Control_Plane/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import REPO_ROOT, CONTROL_PLANE
from lib.plane import get_current_plane, PlaneContext

# Legacy default (used when plane not specified)
PKG_PATH = CONTROL_PLANE / "registries" / "packages_registry.csv"


def get_pkg_path(plane: Optional[PlaneContext] = None) -> Path:
    """Get the packages registry path for a plane."""
    if plane is not None:
        return plane.root / "registries" / "packages_registry.csv"
    return PKG_PATH


def get_root(plane: Optional[PlaneContext] = None) -> Path:
    """Get the root path for a plane."""
    if plane is not None:
        return plane.root
    return CONTROL_PLANE

STATUS = {"proposed", "draft", "validated", "active", "superseded", "deprecated", "retired", "archived", "yanked"}
SELECTED = {"yes", "no", ""}
PRIORITY = {"P0", "P1", "P2", "P3", ""}
SOURCE_TYPES = {"git", "pypi", "tar", "oci", "local"}
PLATFORMS = {"any", "linux", "darwin"}
ARCHES = {"any", "x86_64", "arm64"}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def warn(msg: str) -> None:
    print(f"WARN: {msg}")


def load_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        fail(f"Missing registry: {path}")
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+].*)?$")


def parse_semver(v: str) -> Tuple[int, int, int]:
    m = SEMVER_RE.match(v)
    if not m:
        raise ValueError(f"invalid semver '{v}'")
    return tuple(int(x) for x in m.groups())


def parse_constraints(spec: str) -> List[Tuple[str, Tuple[int, int, int]]]:
    constraints: List[Tuple[str, Tuple[int, int, int]]] = []
    if not spec:
        return constraints
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith(("^", "~", ">=", "==")):
            op = part[:2] if part[:2] in {">=", "=="} else part[0]
            ver = part[len(op):].strip()
        else:
            op = "=="
            ver = part
        constraints.append((op, parse_semver(ver)))
    return constraints


def satisfies(ver: Tuple[int, int, int], constraints: List[Tuple[str, Tuple[int, int, int]]]) -> bool:
    if not constraints:
        return True
    for op, target in constraints:
        if op == "==":
            if ver != target:
                return False
        elif op == ">=":
            if ver < target:
                return False
        elif op == "^":
            # same major, >= target
            if ver[0] != target[0] or ver < target:
                return False
        elif op == "~":
            # same major & minor, >= target
            if (ver[0], ver[1]) != (target[0], target[1]) or ver < target:
                return False
        else:
            return False
    return True


def sha256_row(row: Dict[str, str], headers: List[str]) -> str:
    """Compute deterministic hash over the row with ordered headers."""
    canonical = "|".join((row.get(h, "") or "").strip() for h in headers)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def build_graph(rows: List[Dict[str, str]]) -> Dict[str, List[str]]:
    graph: Dict[str, List[str]] = {}
    for row in rows:
        pkg_id = row["id"].strip()
        deps = [d.split("@")[0].strip() for d in (row.get("deps", "") or "").split(",") if d.strip()]
        graph[pkg_id] = deps
    return graph


def detect_cycle(graph: Dict[str, List[str]]) -> bool:
    visited: Set[str] = set()
    stack: Set[str] = set()

    def dfs(node: str) -> bool:
        if node in stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        stack.add(node)
        for nei in graph.get(node, []):
            if dfs(nei):
                return True
        stack.remove(node)
        return False

    return any(dfs(n) for n in graph)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate packages registry")
    ap.add_argument("--root", type=Path, help="Plane root path (for multi-plane operation)")
    args = ap.parse_args()

    # Resolve plane context
    plane_root = args.root.resolve() if args.root else None
    plane = get_current_plane(plane_root)
    pkg_path = get_pkg_path(plane)
    root = get_root(plane)

    rows = load_rows(pkg_path)
    if not rows:
        warn(f"{pkg_path.name} is empty")
        return 0

    headers = list(rows[0].keys())

    ids = set()
    for i, row in enumerate(rows, start=2):
        ctx = f"{pkg_path.name}:{i} ({row.get('id','')})"
        pid = (row.get("id") or "").strip()
        if not pid:
            fail(f"{ctx}: missing id")
        if pid in ids:
            fail(f"{ctx}: duplicate id '{pid}'")
        ids.add(pid)

        # enums
        status = (row.get("status") or "").strip()
        if status and status not in STATUS:
            fail(f"{ctx}: invalid status '{status}'")
        selected = (row.get("selected") or "").strip()
        if selected and selected not in SELECTED:
            fail(f"{ctx}: invalid selected '{selected}'")
        priority = (row.get("priority") or "").strip()
        if priority and priority not in PRIORITY:
            fail(f"{ctx}: invalid priority '{priority}'")

        # required fields
        version = (row.get("version") or "").strip()
        source = (row.get("source") or "").strip()
        source_type = (row.get("source_type") or "").strip()
        digest = (row.get("digest") or "").strip()
        if not version:
            fail(f"{ctx}: missing version")
        parse_semver(version)
        if not source:
            fail(f"{ctx}: missing source")
        if source_type not in SOURCE_TYPES:
            fail(f"{ctx}: invalid source_type '{source_type}'")
        if source_type != "local" and not digest:
            fail(f"{ctx}: digest required for non-local source")
        if digest and not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            fail(f"{ctx}: digest must be 64 hex chars")

        platform = (row.get("platform") or "any").strip()
        arch = (row.get("arch") or "any").strip()
        if platform not in PLATFORMS:
            fail(f"{ctx}: invalid platform '{platform}'")
        if arch not in ARCHES:
            fail(f"{ctx}: invalid arch '{arch}'")

        # deps/conflicts
        dep_field = (row.get("deps") or "").strip()
        conflict_field = (row.get("conflicts") or "").strip()
        dep_ids = []
        for dep in dep_field.split(","):
            dep = dep.strip()
            if not dep:
                continue
            dep_id, *_ = dep.split("@", 1)
            dep_ids.append(dep_id)
            # parse constraint if present
            if "@" in dep:
                parse_constraints(dep.split("@", 1)[1])
        for conf in conflict_field.split(","):
            conf = conf.strip()
            if not conf:
                continue
            conf_id, *_ = conf.split("@", 1)
            if conf_id in dep_ids:
                fail(f"{ctx}: conflicts cannot overlap deps ({conf_id})")

        # content hash
        expected_hash = (row.get("content_hash") or "").strip()
        actual_hash = sha256_row(row, headers)
        if expected_hash and expected_hash != actual_hash:
            fail(f"{ctx}: content_hash mismatch (expected {expected_hash}, got {actual_hash})")

    # Duplicate name/content consistency check
    name_map: Dict[str, Dict[str, str]] = {}
    hash_map: Dict[str, str] = {}
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        # Prefer explicit digest; fall back to local file hash if source_type=local
        digest = (row.get("digest") or "").strip()
        if not digest and (row.get("source_type") or "").strip() == "local":
            art = (row.get("artifact_path") or row.get("source") or "").lstrip("/")
            art_path = root / art
            if art_path.is_file():
                try:
                    digest = sha256_file(art_path)
                except Exception:
                    pass
        if name not in name_map:
            name_map[name] = row
            if digest:
                hash_map[name] = digest
            continue
        # Existing entry
        other = name_map[name]
        other_digest = (other.get("digest") or "").strip()
        if not other_digest and (other.get("source_type") or "").strip() == "local":
            art = (other.get("artifact_path") or other.get("source") or "").lstrip("/")
            art_path = root / art
            if art_path.is_file():
                try:
                    other_digest = sha256_file(art_path)
                except Exception:
                    pass
        # Compare if both have material hashes
        if digest and other_digest and digest != other_digest:
            fail(f"Duplicate name '{name}' with different content/digest detected; create a new package id or bump version.")
        elif digest and other_digest and digest == other_digest:
            warn(f"Name '{name}' already present with identical content; already installed.")

    # dep existence and cycle detection
    graph = build_graph(rows)
    for i, row in enumerate(rows, start=2):
        ctx = f"{pkg_path.name}:{i} ({row.get('id','')})"
        for dep in graph[row["id"]]:
            if dep and dep not in ids:
                fail(f"{ctx}: missing dependency '{dep}'")
    if detect_cycle(graph):
        fail("Dependency cycle detected")

    # Attestation validation
    for i, row in enumerate(rows, start=2):
        ctx = f"{pkg_path.name}:{i} ({row.get('id','')})"
        status = (row.get("status") or "").strip()
        source_type = (row.get("source_type") or "").strip()

        # Only validate attestation for active tar packages
        if status != "active" or source_type != "tar":
            continue

        attestation_path = (row.get("attestation_path") or "").strip()
        attestation_digest = (row.get("attestation_digest") or "").strip()

        # If attestation_path is set, validate it
        if attestation_path:
            # Resolve path
            if attestation_path.startswith("/"):
                att_full_path = root / attestation_path.lstrip("/")
            else:
                att_full_path = root / attestation_path

            # Check file exists
            if not att_full_path.exists():
                warn(f"{ctx}: attestation_path does not exist: {attestation_path}")
            else:
                # Verify digest if provided
                if attestation_digest:
                    actual_att_digest = sha256_file(att_full_path)
                    if attestation_digest != actual_att_digest:
                        fail(f"{ctx}: attestation_digest mismatch (expected {attestation_digest[:16]}..., got {actual_att_digest[:16]}...)")

                # Validate attestation JSON structure
                try:
                    import json
                    with att_full_path.open("r", encoding="utf-8") as f:
                        att_data = json.load(f)

                    # Check required fields
                    if att_data.get("schema_version") != "1.0":
                        warn(f"{ctx}: attestation has unknown schema_version: {att_data.get('schema_version')}")

                    att_pkg_digest = att_data.get("package_digest_sha256", "")
                    registry_digest = (row.get("digest") or "").strip()

                    # Verify package_digest_sha256 matches registry digest
                    if att_pkg_digest and registry_digest and att_pkg_digest != registry_digest:
                        fail(f"{ctx}: attestation package_digest_sha256 does not match registry digest")

                except json.JSONDecodeError as e:
                    fail(f"{ctx}: attestation file is not valid JSON: {e}")
                except Exception as e:
                    warn(f"{ctx}: could not validate attestation: {e}")

    print(f"OK: {pkg_path.name} valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
