#!/usr/bin/env python3
"""Resolve package install order from archive manifests.

Reads every .tar.gz in a packages/ directory, extracts manifest.json,
and outputs the install order: sorted by layer (from bootstrap_sequence.json
in PKG-GENESIS-000), then topologically sorted within each layer.

Layer 0 packages (PKG-GENESIS-000, PKG-KERNEL-001) are excluded — they
use the genesis bootstrap path, not package_install.py.

Usage:
    python3 resolve_install_order.py <packages_dir>

Output:
    One package ID per line, in install order.

Exit codes:
    0  Success
    1  Error (missing dir, broken manifest, circular deps)
"""

import json
import sys
import tarfile
from pathlib import Path


# Layer 0 is handled specially by install.sh (genesis bootstrap)
LAYER0_IDS = {"PKG-GENESIS-000", "PKG-KERNEL-001"}


def read_manifest_from_archive(archive_path: Path) -> dict:
    """Extract and parse manifest.json from a .tar.gz archive."""
    with tarfile.open(archive_path, "r:gz") as tf:
        for member in tf.getmembers():
            if member.name == "manifest.json" or member.name.endswith("/manifest.json"):
                if member.name.count("/") <= 1:
                    f = tf.extractfile(member)
                    if f:
                        return json.loads(f.read().decode("utf-8"))
    raise ValueError(f"No manifest.json found in {archive_path.name}")


def read_layer_map(packages_dir: Path) -> dict[str, int]:
    """Read layer assignments from bootstrap_sequence.json in PKG-GENESIS-000.

    Returns: {package_id: layer_number}
    """
    genesis_archive = packages_dir / "PKG-GENESIS-000.tar.gz"
    if not genesis_archive.exists():
        return {}

    try:
        with tarfile.open(genesis_archive, "r:gz") as tf:
            for member in tf.getmembers():
                if member.name.endswith("bootstrap_sequence.json"):
                    f = tf.extractfile(member)
                    if f:
                        data = json.loads(f.read().decode("utf-8"))
                        break
            else:
                return {}
    except (tarfile.TarError, json.JSONDecodeError):
        return {}

    # Parse: {"layers": [{"name": "...", "packages": ["PKG-..."]}]}
    layer_map = {}
    for i, layer in enumerate(data.get("layers", [])):
        for pkg_id in layer.get("packages", []):
            layer_map[pkg_id] = i
    return layer_map


def topological_sort_by_layer(packages: dict[str, dict], layer_map: dict[str, int]) -> list[str]:
    """Sort packages: by layer first, then topological within each layer.

    Args:
        packages: {package_id: {"dependencies": [str]}}
        layer_map: {package_id: layer_number} from bootstrap_sequence.json

    Returns:
        Ordered list of package IDs.
    """
    # Assign layers: from bootstrap_sequence if known, else max+1 (install last)
    max_known_layer = max(layer_map.values()) if layer_map else 0
    default_layer = max_known_layer + 1

    # Group by layer
    layers: dict[int, list[str]] = {}
    for pid in packages:
        layer = layer_map.get(pid, default_layer)
        layers.setdefault(layer, []).append(pid)

    result = []

    for layer_num in sorted(layers.keys()):
        layer_pkgs = set(layers[layer_num])
        # Everything already installed (prior layers + Layer 0)
        installed = set(result) | LAYER0_IDS

        # Kahn's within this layer
        remaining = set(layer_pkgs)
        ordered = []
        changed = True

        while remaining and changed:
            changed = False
            for pid in sorted(remaining):
                deps = set(packages[pid].get("dependencies", []))
                # Unmet = deps that are in THIS layer and not yet ordered
                unmet = deps - installed - set(ordered)
                # Only block on deps that are in our package set
                unmet_in_scope = unmet & set(packages.keys())
                if not unmet_in_scope:
                    ordered.append(pid)
                    remaining.remove(pid)
                    changed = True

        if remaining:
            print(f"ERROR: Circular or unresolvable dependencies in layer {layer_num}:", file=sys.stderr)
            for pid in sorted(remaining):
                deps = set(packages[pid].get("dependencies", []))
                unmet = deps - installed - set(ordered)
                print(f"  {pid} needs: {unmet}", file=sys.stderr)
            sys.exit(1)

        result.extend(ordered)

    return result


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <packages_dir>", file=sys.stderr)
        sys.exit(1)

    packages_dir = Path(sys.argv[1])
    if not packages_dir.is_dir():
        print(f"ERROR: Not a directory: {packages_dir}", file=sys.stderr)
        sys.exit(1)

    # Read layer assignments from genesis
    layer_map = read_layer_map(packages_dir)

    # Read all manifests
    packages = {}
    for archive in sorted(packages_dir.glob("*.tar.gz")):
        try:
            manifest = read_manifest_from_archive(archive)
        except (ValueError, tarfile.TarError, json.JSONDecodeError) as e:
            print(f"WARNING: Skipping {archive.name}: {e}", file=sys.stderr)
            continue

        pkg_id = manifest.get("package_id", archive.stem)

        if pkg_id in LAYER0_IDS:
            continue

        deps = manifest.get("dependencies", [])
        packages[pkg_id] = {"dependencies": deps}

    if not packages:
        print("ERROR: No installable packages found", file=sys.stderr)
        sys.exit(1)

    # Sort and output
    order = topological_sort_by_layer(packages, layer_map)
    for pkg_id in order:
        print(pkg_id)


if __name__ == "__main__":
    main()
