#!/usr/bin/env python3
"""
governance_walk.py — Framework-First Governance Walk

Walks the authority chain top-down:
  HOT/FMWK-* → HO3/spec_packs/SPEC-* → HO3/installed/PKG-* → files on disk

Classifies every file as GOVERNED / SHIM / DUPLICATE / ORPHAN / MISSING.
Generates corrected registries and manifests.

Usage:
  python3 governance_walk.py --dry-run     # analyze + report
  python3 governance_walk.py --apply       # install new registries + fix manifests
"""

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CP_ROOT = Path(__file__).resolve().parent
HOT = CP_ROOT / "HOT"
HO3 = CP_ROOT / "HO3"
OUTPUT_DIR = CP_ROOT / "walk_output"

TIMESTAMP = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

# Framework rename map: old_id → new_id (from previous_id in manifests)
FMWK_RENAME = {}  # populated at runtime

# Paths that are excluded from governance (match governed_roots.json excluded_patterns)
EXCLUDED_PATTERNS = {
    "__pycache__",
    ".pyc",
    "__init__.py",
}

# Tiers where real files live
TIER_ROOTS = {
    "HOT": HOT,
    "HO3": HO3,
}

# Governed directories within each tier
HOT_GOVERNED_DIRS = ["kernel", "scripts", "config", "schemas", "registries",
                     "versions", "work_orders", "tests"]
HO3_GOVERNED_DIRS = ["libs", "scripts", "tests", "spec_packs", "installed",
                     "packages_store", "prompt_packs", "registries"]

# Old flat directories that may contain shims/duplicates
OLD_FLAT_DIRS = ["lib", "scripts", "frameworks", "specs", "installed",
                 "config", "schemas", "registries", "tests", "docs",
                 "modules", "governed_prompts"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    """Compute sha256:HASH for a file."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return f"sha256:{h.hexdigest()}"
    except (OSError, IOError):
        return "sha256:ERROR"


def is_excluded(path: Path) -> bool:
    """Check if a path should be excluded from governance."""
    name = path.name
    if name == "__init__.py":
        return True
    if name.endswith(".pyc"):
        return True
    if "__pycache__" in path.parts:
        return True
    if name.startswith("."):
        return True
    return False


def rel(path: Path) -> str:
    """Get path relative to CP_ROOT."""
    try:
        return str(path.relative_to(CP_ROOT))
    except ValueError:
        return str(path)


def load_yaml(path: Path) -> dict:
    """Load a YAML file."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path) as f:
        return json.load(f)


def classify_lib_file(path: Path) -> str:
    """Classify a file in lib/ as SHIM or REAL."""
    try:
        size = path.stat().st_size
        if size < 400:
            content = path.read_text(errors="replace")
            if "shim" in content.lower() or "backward-compatibility" in content.lower():
                return "SHIM"
        return "REAL"
    except OSError:
        return "UNKNOWN"


# ---------------------------------------------------------------------------
# Phase 1: Authority Tree
# ---------------------------------------------------------------------------

class AuthorityTree:
    """Builds the FMWK → SPEC → PKG → file authority chain."""

    def __init__(self):
        self.frameworks = {}       # fmwk_id → {manifest data + dir}
        self.fmwk_rename = {}      # old_id → new_id
        self.specs = {}            # spec_id → {manifest data + dir}
        self.packages = {}         # pkg_id → {manifest data + dir + location}
        self.fmwk_to_specs = {}    # fmwk_id → [spec_ids]
        self.spec_to_pkgs = {}     # spec_id → [pkg_ids]
        self.governed_files = {}   # rel_path → {owner_pkg, sha256, classification}
        self.path_translation = {} # old_path → tier_path

    def walk_frameworks(self):
        """Phase 1.1: Parse HOT/FMWK-*/manifest.yaml"""
        for fmwk_dir in sorted(HOT.glob("FMWK-*")):
            manifest_path = fmwk_dir / "manifest.yaml"
            if not manifest_path.exists():
                continue
            data = load_yaml(manifest_path)
            fmwk_id = data.get("framework_id", fmwk_dir.name.split("_")[0])
            data["_dir"] = str(fmwk_dir)
            data["_assets_on_disk"] = []
            for f in sorted(fmwk_dir.iterdir()):
                if f.name != "manifest.yaml" and not is_excluded(f):
                    data["_assets_on_disk"].append(rel(f))
            self.frameworks[fmwk_id] = data

            # Build rename map from previous_id
            prev = data.get("previous_id")
            if prev:
                self.fmwk_rename[prev] = fmwk_id

        global FMWK_RENAME
        FMWK_RENAME = self.fmwk_rename

    def walk_specs(self):
        """Phase 1.2: Parse HO3/spec_packs/SPEC-*/manifest.yaml"""
        for spec_dir in sorted(HO3.glob("spec_packs/SPEC-*")):
            manifest_path = spec_dir / "manifest.yaml"
            if not manifest_path.exists():
                continue
            data = load_yaml(manifest_path)
            spec_id = data.get("spec_id", spec_dir.name)
            data["_dir"] = str(spec_dir)

            # Resolve framework_id through rename map
            fmwk_id = data.get("framework_id", "")
            resolved_fmwk = self.fmwk_rename.get(fmwk_id, fmwk_id)
            data["_resolved_framework_id"] = resolved_fmwk

            self.specs[spec_id] = data

            # Map framework → specs
            self.fmwk_to_specs.setdefault(resolved_fmwk, []).append(spec_id)

    def walk_packages(self):
        """Phase 1.3: Parse installed/PKG-*/manifest.json from all tiers."""
        # HOT installed packages
        for pkg_dir in sorted(HOT.glob("installed/PKG-*")):
            self._load_package(pkg_dir, "HOT")

        # HO3 installed packages
        for pkg_dir in sorted(HO3.glob("installed/PKG-*")):
            pkg_id = pkg_dir.name
            if pkg_id not in self.packages:
                self._load_package(pkg_dir, "HO3")

        # Root installed packages (legacy flat layout)
        root_installed = CP_ROOT / "installed"
        if root_installed.exists():
            for pkg_dir in sorted(root_installed.glob("PKG-*")):
                pkg_id = pkg_dir.name
                if pkg_id not in self.packages:
                    self._load_package(pkg_dir, "root")

    def _load_package(self, pkg_dir: Path, location: str):
        manifest_path = pkg_dir / "manifest.json"
        if not manifest_path.exists():
            return
        try:
            data = load_json(manifest_path)
        except (json.JSONDecodeError, OSError):
            return
        pkg_id = data.get("package_id", pkg_dir.name)
        data["_dir"] = str(pkg_dir)
        data["_location"] = location

        # Map spec → packages
        spec_id = data.get("spec_id")
        if spec_id:
            self.spec_to_pkgs.setdefault(spec_id, []).append(pkg_id)

        self.packages[pkg_id] = data

    def build_path_translation(self):
        """Phase 1.4: Build translation map from old flat paths to tier paths.

        After tier migration is complete, flat directories (lib/, scripts/) no
        longer exist.  When they are absent we skip the scan — no translation
        is needed because all paths are already in their tier locations.
        """
        # lib/ shims → HOT/kernel/
        lib_dir = CP_ROOT / "lib"
        if lib_dir.exists():
            for lib_file in sorted(lib_dir.glob("*.py")):
                if is_excluded(lib_file):
                    continue
                classification = classify_lib_file(lib_file)
                old_rel = f"lib/{lib_file.name}"
                if classification == "SHIM":
                    new_rel = f"HOT/kernel/{lib_file.name}"
                    self.path_translation[old_rel] = new_rel
                elif classification == "REAL":
                    new_rel = f"HO3/libs/{lib_file.name}"
                    self.path_translation[old_rel] = new_rel

        # scripts/ → check HOT/scripts/ or HO3/scripts/
        scripts_dir = CP_ROOT / "scripts"
        if scripts_dir.exists():
            for script_file in sorted(scripts_dir.iterdir()):
                if is_excluded(script_file) or script_file.is_dir():
                    continue
                old_rel = f"scripts/{script_file.name}"
                hot_path = HOT / "scripts" / script_file.name
                ho3_path = HO3 / "scripts" / script_file.name
                if hot_path.exists():
                    self.path_translation[old_rel] = f"HOT/scripts/{script_file.name}"
                elif ho3_path.exists():
                    self.path_translation[old_rel] = f"HO3/scripts/{script_file.name}"

            # scripts/policies/ and scripts/templates/
            for subdir in ["policies", "templates"]:
                old_dir = scripts_dir / subdir
                if old_dir.exists():
                    for f in old_dir.rglob("*"):
                        if f.is_file() and not is_excluded(f):
                            old_rel = str(f.relative_to(CP_ROOT))
                            sub_rel = str(f.relative_to(old_dir))
                            hot_sub = HOT / "scripts" / subdir / sub_rel
                            ho3_sub = HO3 / "scripts" / subdir / sub_rel
                            if hot_sub.exists():
                                self.path_translation[old_rel] = str(hot_sub.relative_to(CP_ROOT))
                            elif ho3_sub.exists():
                                self.path_translation[old_rel] = str(ho3_sub.relative_to(CP_ROOT))
                            else:
                                self.path_translation[old_rel] = f"HO3/scripts/{subdir}/{sub_rel}"

        # frameworks/ → HOT/FMWK-*/
        old_fmwk_to_new = {
            "FMWK-000_governance_framework.md": "HOT/FMWK-000_Governance/governance_framework.md",
            "FMWK-100_agent_development_standard.md": "HOT/FMWK-100_Agent_Development/agent_development_standard.md",
            "FMWK-107_package_management_standard.md": "HOT/FMWK-007_Package_Management/package_management_standard.md",
            "FMWK-200_ledger_protocol.md": "HOT/FMWK-002_Ledger_Protocol/ledger_protocol.md",
            "FMWK-ATT-001_provenance_attestation_standard.md": "HOT/FMWK-001_Provenance_Attestation/provenance_attestation_standard.md",
            "FMWK-PKG-001_package_standard.md": "HOT/FMWK-003_Package_Standard/package_standard.md",
            "FMWK-PROMPT-001_prompt_governance.md": "HOT/FMWK-004_Prompt_Governance/prompt_governance.md",
        }
        for old_name, new_path in old_fmwk_to_new.items():
            old_rel = f"frameworks/{old_name}"
            self.path_translation[old_rel] = new_path

        # specs/SPEC-X/ → HO3/spec_packs/SPEC-X/
        specs_dir = CP_ROOT / "specs"
        if specs_dir.exists():
            for spec_dir in sorted(specs_dir.glob("SPEC-*")):
                spec_id = spec_dir.name
                old_prefix = f"specs/{spec_id}/"
                new_prefix = f"HO3/spec_packs/{spec_id}/"
                for f in spec_dir.rglob("*"):
                    if f.is_file() and not is_excluded(f):
                        old_rel = str(f.relative_to(CP_ROOT))
                        self.path_translation[old_rel] = new_prefix + str(f.relative_to(spec_dir))

        # config/ → HOT/config/
        config_dir = CP_ROOT / "config"
        if config_dir.exists():
            for f in sorted(config_dir.iterdir()):
                if f.is_file() and not is_excluded(f):
                    old_rel = f"config/{f.name}"
                    hot_path = HOT / "config" / f.name
                    if hot_path.exists():
                        self.path_translation[old_rel] = f"HOT/config/{f.name}"

        # schemas/ → HOT/schemas/
        schemas_dir = CP_ROOT / "schemas"
        if schemas_dir.exists():
            for f in sorted(schemas_dir.iterdir()):
                if f.is_file() and not is_excluded(f):
                    old_rel = f"schemas/{f.name}"
                    hot_path = HOT / "schemas" / f.name
                    if hot_path.exists():
                        self.path_translation[old_rel] = f"HOT/schemas/{f.name}"

        # registries/ → HOT/registries/
        registries_dir = CP_ROOT / "registries"
        if registries_dir.exists():
            for f in sorted(registries_dir.iterdir()):
                if f.is_file() and not is_excluded(f):
                    old_rel = f"registries/{f.name}"
                    hot_path = HOT / "registries" / f.name
                    if hot_path.exists():
                        self.path_translation[old_rel] = f"HOT/registries/{f.name}"

        # tests/ → HO3/tests/
        tests_dir = CP_ROOT / "tests"
        if tests_dir.exists():
            for f in sorted(tests_dir.iterdir()):
                if f.is_file() and not is_excluded(f):
                    old_rel = f"tests/{f.name}"
                    ho3_path = HO3 / "tests" / f.name
                    if ho3_path.exists():
                        self.path_translation[old_rel] = f"HO3/tests/{f.name}"

    def build_governed_set(self):
        """Phase 1.5: Build GOVERNED set from authority chain."""
        # Framework assets (the .md files in HOT/FMWK-*/)
        for fmwk_id, data in self.frameworks.items():
            fmwk_dir = Path(data["_dir"])
            for asset_name in data.get("assets", []):
                asset_path = fmwk_dir / asset_name
                if asset_path.exists():
                    r = rel(asset_path)
                    self.governed_files[r] = {
                        "owner": f"FMWK-{fmwk_id}",
                        "sha256": sha256_file(asset_path),
                        "classification": "law_doc",
                        "source": "framework",
                    }

        # Package assets → resolve to tier paths
        for pkg_id, data in self.packages.items():
            for asset in data.get("assets", []):
                asset_path = asset.get("path", asset) if isinstance(asset, dict) else asset
                classification = asset.get("classification", "unknown") if isinstance(asset, dict) else "unknown"

                # Translate old flat path to tier path
                tier_path = self.path_translation.get(asset_path, asset_path)

                # Check if tier_path file exists on disk
                abs_path = CP_ROOT / tier_path
                if abs_path.exists():
                    disk_hash = sha256_file(abs_path)
                else:
                    # Try original path
                    abs_path = CP_ROOT / asset_path
                    if abs_path.exists():
                        disk_hash = sha256_file(abs_path)
                        tier_path = asset_path  # keep original if tier doesn't exist
                    else:
                        disk_hash = "sha256:MISSING"

                self.governed_files[tier_path] = {
                    "owner": pkg_id,
                    "sha256": disk_hash,
                    "classification": classification,
                    "source": "package",
                    "original_path": asset_path if asset_path != tier_path else None,
                }


# ---------------------------------------------------------------------------
# Phase 2: Physical Inventory
# ---------------------------------------------------------------------------

class PhysicalInventory:
    """Walk disk, hash files, classify old flat directory files."""

    def __init__(self, tree: AuthorityTree):
        self.tree = tree
        self.tier_files = {}        # rel_path → sha256 (files in HOT/ and HO3/)
        self.flat_files = {}        # rel_path → {sha256, classification}
        self.all_disk_files = set() # every file found on disk

    def scan_tier(self, tier_name: str, tier_root: Path, governed_dirs: list):
        """Scan governed directories within a tier."""
        for gdir_name in governed_dirs:
            gdir = tier_root / gdir_name
            if not gdir.exists():
                continue
            for f in gdir.rglob("*"):
                if f.is_file() and not is_excluded(f):
                    r = rel(f)
                    self.tier_files[r] = sha256_file(f)
                    self.all_disk_files.add(r)

        # Also scan FMWK-* directories in HOT
        if tier_name == "HOT":
            for fmwk_dir in sorted(tier_root.glob("FMWK-*")):
                for f in fmwk_dir.rglob("*"):
                    if f.is_file() and not is_excluded(f):
                        r = rel(f)
                        self.tier_files[r] = sha256_file(f)
                        self.all_disk_files.add(r)

    def scan_flat_dirs(self):
        """Scan old flat directories, classify files."""
        for dir_name in OLD_FLAT_DIRS:
            flat_dir = CP_ROOT / dir_name
            if not flat_dir.exists():
                continue

            # Skip if dir_name matches a tier subdir (e.g., tests/ might be
            # both a flat dir and inside HO3)
            for f in flat_dir.rglob("*"):
                if f.is_file() and not is_excluded(f):
                    r = rel(f)
                    file_hash = sha256_file(f)
                    self.all_disk_files.add(r)

                    # Classify
                    classification = "UNKNOWN"
                    if dir_name == "lib":
                        classification = classify_lib_file(f)
                    elif dir_name == "frameworks":
                        # Check if duplicate of HOT/FMWK-*/ file
                        tier_path = self.tree.path_translation.get(r)
                        if tier_path and (CP_ROOT / tier_path).exists():
                            tier_hash = sha256_file(CP_ROOT / tier_path)
                            # Content might differ (old name vs new), mark as DEPRECATED_NAME
                            classification = "DEPRECATED_NAME"
                        else:
                            classification = "UNKNOWN"
                    elif dir_name == "specs":
                        # Check if duplicate of HO3/spec_packs/
                        tier_path = self.tree.path_translation.get(r)
                        if tier_path and (CP_ROOT / tier_path).exists():
                            tier_hash = sha256_file(CP_ROOT / tier_path)
                            if file_hash == tier_hash:
                                classification = "DUPLICATE"
                            else:
                                classification = "STALE_COPY"
                        else:
                            classification = "DUPLICATE"  # dir exists in HO3
                    elif dir_name in ("scripts", "config", "schemas", "registries", "tests"):
                        tier_path = self.tree.path_translation.get(r)
                        if tier_path and (CP_ROOT / tier_path).exists():
                            tier_hash = sha256_file(CP_ROOT / tier_path)
                            if file_hash == tier_hash:
                                classification = "DUPLICATE"
                            else:
                                classification = "STALE_COPY"
                        else:
                            classification = "FLAT_ONLY"

                    self.flat_files[r] = {
                        "sha256": file_hash,
                        "classification": classification,
                    }

    def run(self):
        self.scan_tier("HOT", HOT, HOT_GOVERNED_DIRS)
        self.scan_tier("HO3", HO3, HO3_GOVERNED_DIRS)
        self.scan_flat_dirs()


# ---------------------------------------------------------------------------
# Phase 3: Classify + Dead Package Detection
# ---------------------------------------------------------------------------

class Classifier:
    """Classify every file and every package."""

    def __init__(self, tree: AuthorityTree, inventory: PhysicalInventory):
        self.tree = tree
        self.inventory = inventory
        self.file_verdicts = {}     # rel_path → verdict string
        self.package_verdicts = {}  # pkg_id → verdict string
        self.orphans = []
        self.missing = []
        self.shims = []
        self.duplicates = []

    def classify_files(self):
        """Classify every file on disk."""
        # First: mark all governed files
        for path, info in self.tree.governed_files.items():
            if info["sha256"] == "sha256:MISSING":
                self.file_verdicts[path] = "MISSING"
                self.missing.append(path)
            else:
                self.file_verdicts[path] = "GOVERNED"

        # Second: mark flat dir files
        for path, info in self.inventory.flat_files.items():
            if path in self.file_verdicts:
                continue  # already classified as GOVERNED
            cls = info["classification"]
            if cls == "SHIM":
                self.file_verdicts[path] = "SHIM"
                self.shims.append(path)
            elif cls in ("DUPLICATE", "DEPRECATED_NAME", "STALE_COPY"):
                self.file_verdicts[path] = cls
                self.duplicates.append(path)
            else:
                self.file_verdicts[path] = cls

        # Third: mark tier files not in governed set
        for path in self.inventory.tier_files:
            if path not in self.file_verdicts:
                # Structural / metadata files
                if path.endswith("manifest.yaml") or path.endswith("manifest.json"):
                    self.file_verdicts[path] = "STRUCTURAL"
                elif path.endswith("receipt.json") or path.endswith("checksums.sha256"):
                    self.file_verdicts[path] = "STRUCTURAL"
                elif path.endswith("conftest.py"):
                    self.file_verdicts[path] = "STRUCTURAL"
                # Staging area
                elif "/_staging/" in path:
                    self.file_verdicts[path] = "STAGING"
                # Package store archives
                elif "/packages_store/" in path:
                    self.file_verdicts[path] = "ARCHIVE"
                # Derived registries (rebuilt from manifests, not owned by packages)
                elif "/registries/compiled/" in path:
                    self.file_verdicts[path] = "DERIVED"
                elif path in ("HOT/registries/file_ownership.csv",
                              "HOT/registries/packages_state.csv"):
                    self.file_verdicts[path] = "DERIVED"
                elif path == "HOT/config/seal.json":
                    self.file_verdicts[path] = "STRUCTURAL"
                # Version checkpoints and work orders
                elif "/versions/" in path or "/work_orders/" in path:
                    self.file_verdicts[path] = "STRUCTURAL"
                # HOT/tests/ are tier copies of HO3/tests/ (migration artifact)
                elif path.startswith("HOT/tests/"):
                    ho3_equiv = "HO3/tests/" + Path(path).name
                    if ho3_equiv in self.inventory.tier_files:
                        self.file_verdicts[path] = "TIER_COPY"
                    else:
                        self.file_verdicts[path] = "ORPHAN"
                        self.orphans.append(path)
                else:
                    self.file_verdicts[path] = "ORPHAN"
                    self.orphans.append(path)

    def classify_packages(self):
        """Classify every package as LIVE, DEAD, or PARTIAL."""
        for pkg_id, data in self.tree.packages.items():
            pkg_dir = Path(data["_dir"])
            if not pkg_dir.exists():
                self.package_verdicts[pkg_id] = "DEAD"
                continue

            assets = data.get("assets", [])
            if not assets:
                self.package_verdicts[pkg_id] = "LIVE"  # no assets = metadata-only
                continue

            present = 0
            total = len(assets)
            for asset in assets:
                asset_path = asset.get("path", asset) if isinstance(asset, dict) else asset
                tier_path = self.tree.path_translation.get(asset_path, asset_path)
                if (CP_ROOT / tier_path).exists() or (CP_ROOT / asset_path).exists():
                    present += 1

            if present == total:
                self.package_verdicts[pkg_id] = "LIVE"
            elif present == 0:
                self.package_verdicts[pkg_id] = "DEAD"
            else:
                self.package_verdicts[pkg_id] = "PARTIAL"

    def run(self):
        self.classify_files()
        self.classify_packages()


# ---------------------------------------------------------------------------
# Phase 4: Generate Outputs
# ---------------------------------------------------------------------------

class OutputGenerator:
    """Generate corrected manifests, registries, and reports."""

    def __init__(self, tree: AuthorityTree, inventory: PhysicalInventory,
                 classifier: Classifier):
        self.tree = tree
        self.inventory = inventory
        self.classifier = classifier
        self.output_dir = OUTPUT_DIR

    def _ensure_dirs(self):
        for d in ["new_registries", "new_manifests/spec_packs",
                   "new_manifests/installed", "new_baselines",
                   "new_baselines/PKG-HOT-KERNEL-000",
                   "new_baselines/PKG-BASELINE-HO3-000",
                   "actions"]:
            (self.output_dir / d).mkdir(parents=True, exist_ok=True)

    def generate_walk_report(self):
        """Generate walk_report.json with full structured data."""
        report = {
            "timestamp": TIMESTAMP,
            "frameworks": {
                fid: {
                    "title": d.get("title"),
                    "status": d.get("status"),
                    "previous_id": d.get("previous_id"),
                    "assets": d.get("_assets_on_disk", []),
                }
                for fid, d in self.tree.frameworks.items()
            },
            "framework_rename_map": self.tree.fmwk_rename,
            "specs": {
                sid: {
                    "title": d.get("title"),
                    "framework_id": d.get("framework_id"),
                    "resolved_framework_id": d.get("_resolved_framework_id"),
                    "status": d.get("status"),
                    "asset_count": len(d.get("assets", [])),
                }
                for sid, d in self.tree.specs.items()
            },
            "fmwk_to_specs": self.tree.fmwk_to_specs,
            "spec_to_pkgs": self.tree.spec_to_pkgs,
            "packages": {
                pid: {
                    "spec_id": d.get("spec_id"),
                    "version": d.get("version"),
                    "location": d.get("_location"),
                    "asset_count": len(d.get("assets", [])),
                    "dependencies": d.get("dependencies", []),
                    "verdict": self.classifier.package_verdicts.get(pid, "UNKNOWN"),
                }
                for pid, d in self.tree.packages.items()
            },
            "path_translation": self.tree.path_translation,
            "file_verdicts_summary": {
                v: len([p for p, vv in self.classifier.file_verdicts.items() if vv == v])
                for v in sorted(set(self.classifier.file_verdicts.values()))
            },
            "orphans": sorted(self.classifier.orphans),
            "missing": sorted(self.classifier.missing),
            "shims": sorted(self.classifier.shims),
            "duplicates": sorted(self.classifier.duplicates),
        }
        with open(self.output_dir / "walk_report.json", "w") as f:
            json.dump(report, f, indent=2)

    def generate_walk_summary(self):
        """Generate walk_summary.txt with human-readable output."""
        lines = []
        lines.append("=" * 72)
        lines.append("GOVERNANCE WALK SUMMARY")
        lines.append(f"Generated: {TIMESTAMP}")
        lines.append("=" * 72)
        lines.append("")

        # Authority tree
        lines.append("AUTHORITY TREE")
        lines.append("-" * 40)
        for fid in sorted(self.tree.frameworks):
            fdata = self.tree.frameworks[fid]
            prev = fdata.get("previous_id", "")
            prev_str = f" (was {prev})" if prev else ""
            lines.append(f"  FMWK: {fid}{prev_str} — {fdata.get('title', '?')}")

            spec_ids = self.tree.fmwk_to_specs.get(fid, [])
            for sid in sorted(spec_ids):
                sdata = self.tree.specs.get(sid, {})
                lines.append(f"    SPEC: {sid} — {sdata.get('title', '?')}")

                pkg_ids = self.tree.spec_to_pkgs.get(sid, [])
                for pid in sorted(pkg_ids):
                    verdict = self.classifier.package_verdicts.get(pid, "?")
                    lines.append(f"      PKG: {pid} [{verdict}]")

        # Unlinked specs (framework resolved but not in tree)
        unlinked_specs = [sid for sid in self.tree.specs
                          if sid not in [s for slist in self.tree.spec_to_pkgs.values() for s in slist]
                          and not self.tree.spec_to_pkgs.get(sid)]
        # Actually let's find specs with no packages
        specs_without_pkgs = [sid for sid in self.tree.specs
                              if sid not in self.tree.spec_to_pkgs]
        if specs_without_pkgs:
            lines.append("")
            lines.append(f"  SPECS WITHOUT PACKAGES ({len(specs_without_pkgs)}):")
            for sid in sorted(specs_without_pkgs):
                lines.append(f"    {sid}")

        # Packages without spec link
        pkgs_no_spec = [pid for pid, d in self.tree.packages.items()
                        if not d.get("spec_id")]
        if pkgs_no_spec:
            lines.append("")
            lines.append(f"  PACKAGES WITHOUT SPEC ({len(pkgs_no_spec)}):")
            for pid in sorted(pkgs_no_spec):
                lines.append(f"    {pid}")

        lines.append("")
        lines.append("FILE CLASSIFICATION SUMMARY")
        lines.append("-" * 40)
        verdicts = {}
        for v in self.classifier.file_verdicts.values():
            verdicts[v] = verdicts.get(v, 0) + 1
        for v in sorted(verdicts):
            lines.append(f"  {v:20s}: {verdicts[v]:4d}")

        lines.append("")
        lines.append("PACKAGE VERDICTS")
        lines.append("-" * 40)
        pkg_verdicts = {}
        for v in self.classifier.package_verdicts.values():
            pkg_verdicts[v] = pkg_verdicts.get(v, 0) + 1
        for v in sorted(pkg_verdicts):
            lines.append(f"  {v:10s}: {pkg_verdicts[v]:3d}")

        if self.classifier.orphans:
            lines.append("")
            lines.append(f"ORPHANS ({len(self.classifier.orphans)})")
            lines.append("-" * 40)
            for p in sorted(self.classifier.orphans):
                lines.append(f"  {p}")

        if self.classifier.missing:
            lines.append("")
            lines.append(f"MISSING ({len(self.classifier.missing)})")
            lines.append("-" * 40)
            for p in sorted(self.classifier.missing):
                lines.append(f"  {p}")

        if self.classifier.shims:
            lines.append("")
            lines.append(f"SHIMS ({len(self.classifier.shims)})")
            lines.append("-" * 40)
            for p in sorted(self.classifier.shims):
                target = self.tree.path_translation.get(p, "?")
                lines.append(f"  {p} → {target}")

        lines.append("")
        lines.append(f"PATH TRANSLATIONS ({len(self.tree.path_translation)})")
        lines.append("-" * 40)
        for old, new in sorted(self.tree.path_translation.items()):
            lines.append(f"  {old}")
            lines.append(f"    → {new}")

        lines.append("")
        with open(self.output_dir / "walk_summary.txt", "w") as f:
            f.write("\n".join(lines))

    def generate_governed_roots(self):
        """Phase 4e: Generate governed_roots.json (digital twin)."""
        # Collect all directories containing governed files
        roots = set()
        for path in self.tree.governed_files:
            # Get the tier-level directory
            parts = Path(path).parts
            if len(parts) >= 2:
                if parts[0] in ("HOT", "HO3", "HO2", "HO1"):
                    roots.add(f"{parts[0]}/{parts[1]}/")
                else:
                    roots.add(f"{parts[0]}/")

        governed_roots = {
            "schema_version": "2.0",
            "description": "Generated by governance_walk.py from framework authority chain",
            "generated_at": TIMESTAMP,
            "hot_governed_roots": sorted([r for r in roots if r.startswith("HOT/")]),
            "ho3_governed_roots": sorted([r for r in roots if r.startswith("HO3/")]),
            "legacy_flat_roots": sorted([r for r in roots if not r.startswith(("HOT/", "HO3/", "HO2/", "HO1/"))]),
            "excluded_patterns": [
                "**/__pycache__/**",
                "**/*.pyc",
                "**/__init__.py",
                "**/manifest.yaml",
                "**/manifest.json",
                "**/receipt.json",
                "**/checksums.sha256",
            ],
        }
        with open(self.output_dir / "new_registries" / "governed_roots.json", "w") as f:
            json.dump(governed_roots, f, indent=2)

    def generate_file_ownership(self):
        """Phase 4f: Generate file_ownership.csv."""
        rows = []
        for path, info in sorted(self.tree.governed_files.items()):
            if info["sha256"] == "sha256:MISSING":
                continue
            rows.append({
                "file_path": path,
                "owner_package_id": info["owner"],
                "sha256": info["sha256"],
                "classification": info["classification"],
                "installed_at": TIMESTAMP,
            })

        csv_path = self.output_dir / "new_registries" / "file_ownership.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["file_path", "owner_package_id",
                                                    "sha256", "classification",
                                                    "installed_at"])
            writer.writeheader()
            writer.writerows(rows)

    def generate_control_plane_registry(self):
        """Phase 4g: Generate control_plane_registry.csv."""
        # Read existing registry to preserve artifact IDs
        existing = {}
        old_csv = HOT / "registries" / "control_plane_registry.csv"
        if not old_csv.exists():
            old_csv = CP_ROOT / "registries" / "control_plane_registry.csv"
        if old_csv.exists():
            with open(old_csv) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Match by basename for ID preservation
                    basename = Path(row.get("path", row.get("file_path", ""))).name
                    if basename:
                        existing[basename] = row

        rows = []
        for path, info in sorted(self.tree.governed_files.items()):
            if info["sha256"] == "sha256:MISSING":
                continue
            basename = Path(path).name
            old_row = existing.get(basename, {})
            rows.append({
                "artifact_id": old_row.get("artifact_id", ""),
                "path": path,
                "sha256": info["sha256"],
                "classification": info["classification"],
                "owner_package_id": info["owner"],
                "source_spec_id": "",  # filled below
                "status": "active",
            })

        # Fill source_spec_id from package → spec mapping
        pkg_to_spec = {pid: d.get("spec_id", "") for pid, d in self.tree.packages.items()}
        for row in rows:
            owner = row["owner_package_id"]
            row["source_spec_id"] = pkg_to_spec.get(owner, "")

        csv_path = self.output_dir / "new_registries" / "control_plane_registry.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["artifact_id", "path", "sha256",
                                                    "classification", "owner_package_id",
                                                    "source_spec_id", "status"])
            writer.writeheader()
            writer.writerows(rows)

    def generate_packages_state(self):
        """Phase 4h: Generate packages_state.csv."""
        rows = []
        for pkg_id in sorted(self.tree.packages):
            verdict = self.classifier.package_verdicts.get(pkg_id, "UNKNOWN")
            data = self.tree.packages[pkg_id]
            rows.append({
                "package_id": pkg_id,
                "spec_id": data.get("spec_id", ""),
                "version": data.get("version", ""),
                "status": "removed" if verdict == "DEAD" else "active",
                "verdict": verdict,
                "location": data.get("_location", ""),
                "installed_at": TIMESTAMP,
            })

        csv_path = self.output_dir / "new_registries" / "packages_state.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["package_id", "spec_id", "version",
                                                    "status", "verdict", "location",
                                                    "installed_at"])
            writer.writeheader()
            writer.writerows(rows)

    def generate_fixed_spec_manifests(self):
        """Phase 4a: Fix spec manifest asset paths to tier locations."""
        for spec_id, data in self.tree.specs.items():
            assets = data.get("assets", [])
            if not assets:
                continue

            fixed_assets = []
            changed = False
            for asset in assets:
                if isinstance(asset, dict):
                    path = asset.get("path", "")
                    new_path = self.tree.path_translation.get(path, path)
                    if new_path != path:
                        asset = dict(asset)
                        asset["path"] = new_path
                        changed = True
                    fixed_assets.append(asset)
                elif isinstance(asset, str):
                    new_path = self.tree.path_translation.get(asset, asset)
                    if new_path != asset:
                        changed = True
                    fixed_assets.append(new_path)

            if changed:
                fixed_data = dict(data)
                # Remove internal keys
                fixed_data = {k: v for k, v in fixed_data.items() if not k.startswith("_")}
                fixed_data["assets"] = fixed_assets

                out_dir = self.output_dir / "new_manifests" / "spec_packs" / spec_id
                out_dir.mkdir(parents=True, exist_ok=True)
                with open(out_dir / "manifest.yaml", "w") as f:
                    yaml.dump(fixed_data, f, default_flow_style=False, sort_keys=False)

    def generate_fixed_package_manifests(self):
        """Phase 4b: Fix package manifest asset paths and recompute hashes."""
        for pkg_id, data in self.tree.packages.items():
            assets = data.get("assets", [])
            if not assets:
                continue

            fixed_assets = []
            changed = False
            for asset in assets:
                if isinstance(asset, dict):
                    old_path = asset.get("path", "")
                    new_path = self.tree.path_translation.get(old_path, old_path)
                    new_asset = dict(asset)
                    if new_path != old_path:
                        new_asset["path"] = new_path
                        changed = True
                    # Recompute SHA256 from tier-canonical file
                    abs_path = CP_ROOT / new_path
                    if abs_path.exists():
                        new_hash = sha256_file(abs_path)
                        if new_hash != asset.get("sha256", ""):
                            new_asset["sha256"] = new_hash
                            changed = True
                    fixed_assets.append(new_asset)
                else:
                    new_path = self.tree.path_translation.get(asset, asset)
                    if new_path != asset:
                        changed = True
                    fixed_assets.append(new_path)

            # Also fix install_targets
            install_targets = data.get("install_targets", [])
            fixed_targets = []
            for target in install_targets:
                fixed_files = []
                for f in target.get("files", []):
                    old_rel = f
                    # install_targets use basenames, need to check with prefix
                    # They typically use the directory from the target
                    tgt_dir = target.get("target", "")
                    full_old = f"{tgt_dir}/{f}" if tgt_dir else f
                    new_f = self.tree.path_translation.get(full_old)
                    if new_f:
                        # Extract just the filename portion for install_targets
                        fixed_files.append(f)
                        # Actually install_targets should reference new paths too
                    else:
                        fixed_files.append(f)
                fixed_target = dict(target)
                fixed_target["files"] = fixed_files
                fixed_targets.append(fixed_target)

            if changed:
                fixed_data = dict(data)
                fixed_data = {k: v for k, v in fixed_data.items() if not k.startswith("_")}
                fixed_data["assets"] = fixed_assets
                if fixed_targets:
                    fixed_data["install_targets"] = fixed_targets

                out_dir = self.output_dir / "new_manifests" / "installed" / pkg_id
                out_dir.mkdir(parents=True, exist_ok=True)
                with open(out_dir / "manifest.json", "w") as f:
                    json.dump(fixed_data, f, indent=2)

    def generate_hot_baseline(self):
        """Phase 4c: Create PKG-HOT-KERNEL-000 baseline manifest."""
        assets = []
        hot_dirs = ["kernel", "scripts", "config", "schemas"]
        for dir_name in hot_dirs:
            d = HOT / dir_name
            if not d.exists():
                continue
            for f in sorted(d.rglob("*")):
                if f.is_file() and not is_excluded(f):
                    r = rel(f)
                    h = sha256_file(f)
                    # Determine classification
                    if dir_name == "kernel":
                        cls = "library"
                    elif dir_name == "scripts":
                        cls = "script"
                    elif dir_name == "config":
                        cls = "config"
                    elif dir_name == "schemas":
                        cls = "schema"
                    else:
                        cls = "other"
                    assets.append({
                        "path": r,
                        "sha256": h,
                        "classification": cls,
                    })

        # Also include FMWK manifest.yaml files
        for fmwk_dir in sorted(HOT.glob("FMWK-*")):
            for f in sorted(fmwk_dir.rglob("*")):
                if f.is_file() and not is_excluded(f):
                    r = rel(f)
                    h = sha256_file(f)
                    assets.append({
                        "path": r,
                        "sha256": h,
                        "classification": "law_doc" if f.suffix == ".md" else "manifest",
                    })

        manifest = {
            "package_id": "PKG-HOT-KERNEL-000",
            "version": "1.0.0",
            "title": "HOT Tier Baseline",
            "description": "Owns all files in the HOT tier (kernel, scripts, config, schemas, frameworks)",
            "plane_id": "hot",
            "created_at": TIMESTAMP,
            "assets": assets,
            "dependencies": [],
        }

        out_path = self.output_dir / "new_baselines" / "PKG-HOT-KERNEL-000" / "manifest.json"
        with open(out_path, "w") as f:
            json.dump(manifest, f, indent=2)

    def generate_updated_ho3_baseline(self):
        """Phase 4d: Update PKG-BASELINE-HO3-000 to tier paths, remove HOT-owned files."""
        pkg_data = self.tree.packages.get("PKG-BASELINE-HO3-000", {})
        old_assets = pkg_data.get("assets", [])

        new_assets = []
        for asset in old_assets:
            if isinstance(asset, dict):
                old_path = asset.get("path", "")
            else:
                old_path = asset
                asset = {"path": old_path}

            new_path = self.tree.path_translation.get(old_path, old_path)

            # Skip files now owned by HOT tier
            if new_path.startswith("HOT/"):
                continue

            # Recompute hash from actual file
            abs_path = CP_ROOT / new_path
            if not abs_path.exists():
                abs_path = CP_ROOT / old_path
            if abs_path.exists():
                new_hash = sha256_file(abs_path)
            else:
                new_hash = asset.get("sha256", "sha256:MISSING")

            new_asset = dict(asset)
            new_asset["path"] = new_path
            new_asset["sha256"] = new_hash
            new_assets.append(new_asset)

        manifest = dict(pkg_data)
        manifest = {k: v for k, v in manifest.items() if not k.startswith("_")}
        manifest["assets"] = new_assets

        out_path = self.output_dir / "new_baselines" / "PKG-BASELINE-HO3-000" / "manifest.json"
        with open(out_path, "w") as f:
            json.dump(manifest, f, indent=2)

    def generate_action_files(self):
        """Generate action files for dead packages, orphans, missing."""
        with open(self.output_dir / "actions" / "dead_packages.json", "w") as f:
            dead = {pid: self.tree.packages[pid].get("_dir", "")
                    for pid, v in self.classifier.package_verdicts.items()
                    if v == "DEAD"}
            json.dump(dead, f, indent=2)

        with open(self.output_dir / "actions" / "orphans.json", "w") as f:
            json.dump(sorted(self.classifier.orphans), f, indent=2)

        with open(self.output_dir / "actions" / "missing.json", "w") as f:
            json.dump(sorted(self.classifier.missing), f, indent=2)

    def run(self, apply_mode: bool = False):
        self._ensure_dirs()
        self.generate_walk_report()
        self.generate_walk_summary()
        self.generate_governed_roots()
        self.generate_file_ownership()
        self.generate_control_plane_registry()
        self.generate_packages_state()
        self.generate_fixed_spec_manifests()
        self.generate_fixed_package_manifests()
        self.generate_hot_baseline()
        self.generate_updated_ho3_baseline()
        self.generate_action_files()

        if apply_mode:
            self._apply()

    def _apply(self):
        """Install generated outputs into the live tree."""
        print("\n[APPLY] Installing generated outputs...")

        # 1. Install fixed spec manifests
        spec_out = self.output_dir / "new_manifests" / "spec_packs"
        for spec_dir in sorted(spec_out.glob("SPEC-*")):
            target = HO3 / "spec_packs" / spec_dir.name / "manifest.yaml"
            if target.exists():
                shutil.copy2(spec_dir / "manifest.yaml", target)
                print(f"  Updated: {rel(target)}")

        # 2. Install fixed package manifests
        pkg_out = self.output_dir / "new_manifests" / "installed"
        for pkg_dir in sorted(pkg_out.glob("PKG-*")):
            target = HO3 / "installed" / pkg_dir.name / "manifest.json"
            if target.exists():
                shutil.copy2(pkg_dir / "manifest.json", target)
                print(f"  Updated: {rel(target)}")

        # 3. Install PKG-HOT-KERNEL-000 baseline
        hot_baseline_src = self.output_dir / "new_baselines" / "PKG-HOT-KERNEL-000"
        hot_baseline_dst = HOT / "installed" / "PKG-HOT-KERNEL-000"
        hot_baseline_dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(hot_baseline_src / "manifest.json",
                      hot_baseline_dst / "manifest.json")
        print(f"  Created: {rel(hot_baseline_dst / 'manifest.json')}")

        # 4. Update HO3 baseline
        ho3_baseline_src = self.output_dir / "new_baselines" / "PKG-BASELINE-HO3-000"
        for target_dir in [HO3 / "installed" / "PKG-BASELINE-HO3-000",
                           CP_ROOT / "installed" / "PKG-BASELINE-HO3-000"]:
            if target_dir.exists():
                shutil.copy2(ho3_baseline_src / "manifest.json",
                              target_dir / "manifest.json")
                print(f"  Updated: {rel(target_dir / 'manifest.json')}")

        # 5. Install governed_roots.json
        gr_src = self.output_dir / "new_registries" / "governed_roots.json"
        gr_dst = HOT / "config" / "governed_roots.json"
        shutil.copy2(gr_src, gr_dst)
        print(f"  Updated: {rel(gr_dst)}")

        # 6. Install file_ownership.csv
        fo_src = self.output_dir / "new_registries" / "file_ownership.csv"
        fo_dst = HOT / "registries" / "file_ownership.csv"
        shutil.copy2(fo_src, fo_dst)
        print(f"  Updated: {rel(fo_dst)}")

        # 7. Install packages_state.csv
        ps_src = self.output_dir / "new_registries" / "packages_state.csv"
        ps_dst = HOT / "registries" / "packages_state.csv"
        shutil.copy2(ps_src, ps_dst)
        print(f"  Updated: {rel(ps_dst)}")

        print("\n[APPLY] Done. Run governance_walk.py --dry-run to verify.")


# ---------------------------------------------------------------------------
# Phase 5: Self-Validation
# ---------------------------------------------------------------------------

class Validator:
    """Validate the authority chain and output consistency."""

    def __init__(self, tree: AuthorityTree, classifier: Classifier):
        self.tree = tree
        self.classifier = classifier
        self.errors = []
        self.warnings = []

    def validate_chain_links(self):
        """Every PKG → SPEC → FMWK chain must resolve."""
        for pkg_id, data in self.tree.packages.items():
            spec_id = data.get("spec_id")
            if not spec_id:
                if pkg_id != "PKG-BASELINE-HO3-000" and pkg_id != "PKG-KERNEL-001":
                    self.warnings.append(f"Package {pkg_id} has no spec_id")
                continue
            if spec_id not in self.tree.specs:
                self.errors.append(f"Package {pkg_id} references missing spec {spec_id}")
                continue
            fmwk_id = self.tree.specs[spec_id].get("_resolved_framework_id")
            if fmwk_id and fmwk_id not in self.tree.frameworks:
                self.errors.append(
                    f"Spec {spec_id} references missing framework {fmwk_id}")

    def validate_no_dual_ownership(self):
        """No file should be owned by two packages without dependency declared."""
        owners = {}  # path → [pkg_ids]
        for pkg_id, data in self.tree.packages.items():
            for asset in data.get("assets", []):
                path = asset.get("path", asset) if isinstance(asset, dict) else asset
                tier_path = self.tree.path_translation.get(path, path)
                owners.setdefault(tier_path, []).append(pkg_id)

        for path, pkg_ids in owners.items():
            if len(pkg_ids) > 1:
                # Check if dependency is declared
                for i, pid1 in enumerate(pkg_ids):
                    for pid2 in pkg_ids[i+1:]:
                        deps1 = self.tree.packages[pid1].get("dependencies", [])
                        deps2 = self.tree.packages[pid2].get("dependencies", [])
                        if pid2 not in deps1 and pid1 not in deps2:
                            self.warnings.append(
                                f"Dual ownership of {path}: {pid1}, {pid2} "
                                f"(no dependency declared)")

    def validate_hashes(self):
        """Every SHA256 must be computed from actual disk file."""
        for path, info in self.tree.governed_files.items():
            if info["sha256"] == "sha256:MISSING":
                continue
            if info["sha256"] == "sha256:ERROR":
                self.errors.append(f"Hash error for {path}")

    def run(self):
        self.validate_chain_links()
        self.validate_no_dual_ownership()
        self.validate_hashes()

        if self.errors:
            print(f"\n  VALIDATION ERRORS ({len(self.errors)}):")
            for e in self.errors:
                print(f"    ERROR: {e}")
        if self.warnings:
            print(f"\n  VALIDATION WARNINGS ({len(self.warnings)}):")
            for w in self.warnings[:20]:
                print(f"    WARN:  {w}")
            if len(self.warnings) > 20:
                print(f"    ... and {len(self.warnings) - 20} more")

        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Framework-first governance walk",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 governance_walk.py --dry-run     # analyze + report
  python3 governance_walk.py --apply       # install new registries + fix manifests
        """,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true",
                       help="Analyze and generate reports without modifying files")
    group.add_argument("--apply", action="store_true",
                       help="Generate reports AND install corrected files")
    args = parser.parse_args()

    print("=" * 60)
    print("GOVERNANCE WALK")
    print("=" * 60)

    # Phase 1: Authority Tree
    print("\n[Phase 1] Building authority tree...")
    tree = AuthorityTree()
    tree.walk_frameworks()
    print(f"  Frameworks: {len(tree.frameworks)}")
    if tree.fmwk_rename:
        print(f"  Rename map: {tree.fmwk_rename}")

    tree.walk_specs()
    print(f"  Specs: {len(tree.specs)}")

    tree.walk_packages()
    print(f"  Packages: {len(tree.packages)}")

    tree.build_path_translation()
    print(f"  Path translations: {len(tree.path_translation)}")

    tree.build_governed_set()
    print(f"  Governed files: {len(tree.governed_files)}")

    # Phase 2: Physical Inventory
    print("\n[Phase 2] Scanning physical inventory...")
    inventory = PhysicalInventory(tree)
    inventory.run()
    print(f"  Tier files: {len(inventory.tier_files)}")
    print(f"  Flat files: {len(inventory.flat_files)}")
    print(f"  Total disk files: {len(inventory.all_disk_files)}")

    # Phase 3: Classify
    print("\n[Phase 3] Classifying files and packages...")
    classifier = Classifier(tree, inventory)
    classifier.run()
    verdicts = {}
    for v in classifier.file_verdicts.values():
        verdicts[v] = verdicts.get(v, 0) + 1
    for v in sorted(verdicts):
        print(f"  {v:20s}: {verdicts[v]:4d}")
    print(f"  Package verdicts:")
    pkg_v = {}
    for v in classifier.package_verdicts.values():
        pkg_v[v] = pkg_v.get(v, 0) + 1
    for v in sorted(pkg_v):
        print(f"    {v:10s}: {pkg_v[v]:3d}")

    # Phase 4: Generate Outputs
    print(f"\n[Phase 4] Generating outputs to {rel(OUTPUT_DIR)}/...")
    output = OutputGenerator(tree, inventory, classifier)
    output.run(apply_mode=args.apply)
    print("  Done.")

    # Phase 5: Self-Validation
    print("\n[Phase 5] Validating...")
    validator = Validator(tree, classifier)
    valid = validator.run()

    # Summary
    print("\n" + "=" * 60)
    if args.dry_run:
        print(f"DRY RUN COMPLETE. Outputs in {rel(OUTPUT_DIR)}/")
    else:
        print("APPLY COMPLETE.")
    print(f"  Governed: {verdicts.get('GOVERNED', 0)}")
    print(f"  Orphans:  {len(classifier.orphans)}")
    print(f"  Missing:  {len(classifier.missing)}")
    print(f"  Shims:    {len(classifier.shims)}")
    print(f"  Valid:    {'YES' if valid else 'NO'}")
    print("=" * 60)

    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
