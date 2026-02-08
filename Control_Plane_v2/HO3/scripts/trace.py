#!/usr/bin/env python3
"""
Kernel-native Explain/Trace capability.

Provides human-readable explanations of any artifact in the control plane
by traversing the chain of authority:

    Framework -> Spec -> Artifact -> File -> Package

Commands:
    --explain <id-or-path>   Explain anything (auto-detects type)
    --inventory              Full system inventory
    --verify                 Health check (exit 0 if healthy, 1 if issues)
    --json                   Machine-readable JSON output

Examples:
    python3 scripts/trace.py --explain FMWK-000
    python3 scripts/trace.py --explain lib/merkle.py
    python3 scripts/trace.py --explain PKG-KERNEL-001
    python3 scripts/trace.py --inventory
    python3 scripts/trace.py --verify
"""

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "HOT"))

from kernel.paths import CONTROL_PLANE
from kernel.registry import (
    find_all_registries,
    read_registry,
    find_item,
    find_registry_by_name,
)
from kernel.merkle import hash_file


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class FileInfo:
    """Information about a single file."""
    path: str
    purpose: str = ""
    package: str = ""
    sha256: str = ""
    classification: str = ""
    hash_verified: bool = False


@dataclass
class SpecInfo:
    """Information about a spec and its files."""
    spec_id: str
    title: str
    framework_id: str
    status: str = "active"
    files: List[FileInfo] = field(default_factory=list)


@dataclass
class FrameworkInfo:
    """Information about a framework and its specs."""
    framework_id: str
    title: str
    status: str = "active"
    specs: List[SpecInfo] = field(default_factory=list)
    total_files: int = 0
    packages: List[str] = field(default_factory=list)


@dataclass
class PackageInfo:
    """Information about a package."""
    package_id: str
    files: List[FileInfo] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    specs: List[str] = field(default_factory=list)
    tier_status: Dict[str, str] = field(default_factory=dict)
    parity: bool = True


@dataclass
class InventoryInfo:
    """Full system inventory."""
    frameworks: List[FrameworkInfo] = field(default_factory=list)
    packages: List[str] = field(default_factory=list)
    total_files: int = 0
    orphans: int = 0
    health: str = "healthy"


@dataclass
class InstalledPackageInfo:
    """Information about an installed package."""
    package_id: str
    version: str = ""
    file_count: int = 0
    manifest_hash: str = ""
    installed_at: str = ""
    tier: str = "HO3"


@dataclass
class VerifyResult:
    """Verification result."""
    passed: bool
    checks: List[Dict[str, Any]] = field(default_factory=list)
    message: str = ""


# ============================================================================
# TraceEngine - Core Logic
# ============================================================================

class TraceEngine:
    """Engine for tracing artifacts through the chain of authority."""

    def __init__(self, root: Path = CONTROL_PLANE):
        self.root = root
        self._frameworks: Dict[str, Dict] = {}
        self._specs: Dict[str, Dict] = {}
        self._artifacts: Dict[str, Dict] = {}
        self._files: Dict[str, Dict] = {}
        self._load_registries()

    def _load_registries(self):
        """Load all registry data into memory."""
        # Load frameworks
        fw_reg = self.root / "registries" / "frameworks_registry.csv"
        if fw_reg.exists():
            _, rows = read_registry(fw_reg)
            for row in rows:
                fid = row.get("framework_id", "")
                if fid:
                    self._frameworks[fid] = row

        # Load specs
        spec_reg = self.root / "registries" / "specs_registry.csv"
        if spec_reg.exists():
            _, rows = read_registry(spec_reg)
            for row in rows:
                sid = row.get("spec_id", "")
                if sid:
                    self._specs[sid] = row

        # Load control plane registry (artifacts)
        cp_reg = self.root / "registries" / "control_plane_registry.csv"
        if cp_reg.exists():
            _, rows = read_registry(cp_reg)
            for row in rows:
                aid = row.get("id", "")
                if aid:
                    self._artifacts[aid] = row

        # Load file ownership
        fo_reg = self.root / "registries" / "file_ownership.csv"
        if fo_reg.exists():
            _, rows = read_registry(fo_reg)
            for row in rows:
                fpath = row.get("file_path", "")
                if fpath:
                    self._files[fpath] = row

    def _detect_type(self, query: str) -> Tuple[str, Optional[Dict]]:
        """Detect what type of thing the query refers to.

        Returns: (type, data) where type is one of:
            'framework', 'spec', 'artifact', 'file', 'package', 'unknown'
        """
        query_upper = query.upper().strip()
        query_normalized = query.lstrip("/").strip()

        # Check frameworks
        if query_upper in self._frameworks:
            return ("framework", self._frameworks[query_upper])
        if query_upper.startswith("FMWK-"):
            for fid, fdata in self._frameworks.items():
                if fid.upper() == query_upper:
                    return ("framework", fdata)

        # Check specs
        if query_upper in self._specs:
            return ("spec", self._specs[query_upper])
        if query_upper.startswith("SPEC-"):
            for sid, sdata in self._specs.items():
                if sid.upper() == query_upper:
                    return ("spec", sdata)

        # Check packages
        if query_upper.startswith("PKG-"):
            # Check if it's in file_ownership
            for fpath, fdata in self._files.items():
                if fdata.get("owner_package_id", "").upper() == query_upper:
                    return ("package", {"package_id": query_upper})
            # Still return as package even if no files found
            return ("package", {"package_id": query_upper})

        # Check artifacts by ID
        if query_upper in self._artifacts:
            return ("artifact", self._artifacts[query_upper])

        # Check files by path
        if query_normalized in self._files:
            return ("file", self._files[query_normalized])

        # Try artifact path matching
        for aid, adata in self._artifacts.items():
            apath = adata.get("artifact_path", "").lstrip("/")
            if apath == query_normalized:
                return ("artifact", adata)

        # Check if it's a file path that exists
        full_path = self.root / query_normalized
        if full_path.exists() and full_path.is_file():
            return ("file", {"file_path": query_normalized})

        return ("unknown", None)

    def _get_files_for_spec(self, spec_id: str) -> List[FileInfo]:
        """Get all files belonging to a spec."""
        files = []
        for aid, adata in self._artifacts.items():
            if adata.get("source_spec_id", "").upper() == spec_id.upper():
                path = adata.get("artifact_path", "").lstrip("/")
                purpose = adata.get("purpose", "")

                # Get file ownership info
                fdata = self._files.get(path, {})
                package = fdata.get("owner_package_id", "")
                sha256 = fdata.get("sha256", "")
                classification = fdata.get("classification", "")

                # Verify hash
                hash_verified = False
                full_path = self.root / path
                if full_path.exists() and sha256:
                    current = f"sha256:{hash_file(full_path)}"
                    hash_verified = current == sha256

                files.append(FileInfo(
                    path=path,
                    purpose=purpose,
                    package=package,
                    sha256=sha256,
                    classification=classification,
                    hash_verified=hash_verified,
                ))
        return files

    def _get_specs_for_framework(self, framework_id: str) -> List[SpecInfo]:
        """Get all specs belonging to a framework."""
        specs = []
        for sid, sdata in self._specs.items():
            if sdata.get("framework_id", "").upper() == framework_id.upper():
                files = self._get_files_for_spec(sid)
                specs.append(SpecInfo(
                    spec_id=sid,
                    title=sdata.get("title", ""),
                    framework_id=framework_id,
                    status=sdata.get("status", "active"),
                    files=files,
                ))
        return specs

    def _extract_docstring(self, path: Path) -> str:
        """Extract module docstring from a Python file."""
        if not path.exists() or not path.suffix == ".py":
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content)
            docstring = ast.get_docstring(tree)
            return docstring or ""
        except Exception:
            return ""

    def _extract_functions(self, path: Path) -> List[Dict[str, str]]:
        """Extract function signatures from a Python file."""
        if not path.exists() or not path.suffix == ".py":
            return []
        functions = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not node.name.startswith("_"):
                        doc = ast.get_docstring(node) or ""
                        # Get first line of docstring
                        first_line = doc.split("\n")[0] if doc else ""
                        functions.append({
                            "name": node.name,
                            "purpose": first_line,
                        })
        except Exception:
            pass
        return functions

    def explain_framework(self, framework_id: str) -> FrameworkInfo:
        """Explain a framework with all its specs and files."""
        fdata = self._frameworks.get(framework_id.upper(), {})
        specs = self._get_specs_for_framework(framework_id)

        # Collect unique packages
        packages = set()
        total_files = 0
        for spec in specs:
            for f in spec.files:
                if f.package:
                    packages.add(f.package)
                total_files += 1

        return FrameworkInfo(
            framework_id=framework_id,
            title=fdata.get("title", ""),
            status=fdata.get("status", "active"),
            specs=specs,
            total_files=total_files,
            packages=sorted(packages),
        )

    def explain_spec(self, spec_id: str) -> Dict:
        """Explain a spec with its framework and files."""
        sdata = self._specs.get(spec_id.upper(), {})
        framework_id = sdata.get("framework_id", "")
        fdata = self._frameworks.get(framework_id, {})
        files = self._get_files_for_spec(spec_id)

        packages = set(f.package for f in files if f.package)

        return {
            "spec_id": spec_id,
            "title": sdata.get("title", ""),
            "status": sdata.get("status", "active"),
            "framework": {
                "framework_id": framework_id,
                "title": fdata.get("title", ""),
            },
            "files": [asdict(f) for f in files],
            "packages": sorted(packages),
        }

    def explain_file(self, path: str) -> Dict:
        """Explain a file with its full ownership chain."""
        path_normalized = path.lstrip("/").strip()
        fdata = self._files.get(path_normalized, {})

        # Find artifact info
        artifact_info = None
        spec_id = ""
        for aid, adata in self._artifacts.items():
            apath = adata.get("artifact_path", "").lstrip("/")
            if apath == path_normalized:
                artifact_info = adata
                spec_id = adata.get("source_spec_id", "")
                break

        # Get spec and framework
        sdata = self._specs.get(spec_id, {})
        framework_id = sdata.get("framework_id", "")
        fwdata = self._frameworks.get(framework_id, {})

        # Verify hash
        full_path = self.root / path_normalized
        current_hash = ""
        hash_verified = False
        recorded_hash = fdata.get("sha256", "")
        if full_path.exists():
            current_hash = f"sha256:{hash_file(full_path)}"
            if recorded_hash:
                hash_verified = current_hash == recorded_hash

        # Extract docstring and functions
        docstring = self._extract_docstring(full_path)
        functions = self._extract_functions(full_path)

        return {
            "path": path_normalized,
            "exists": full_path.exists(),
            "ownership": {
                "package": fdata.get("owner_package_id", ""),
                "spec_id": spec_id,
                "spec_title": sdata.get("title", ""),
                "framework_id": framework_id,
                "framework_title": fwdata.get("title", ""),
            },
            "artifact_id": artifact_info.get("id", "") if artifact_info else "",
            "purpose": artifact_info.get("purpose", "") if artifact_info else "",
            "classification": fdata.get("classification", ""),
            "hash": {
                "recorded": recorded_hash,
                "current": current_hash,
                "verified": hash_verified,
            },
            "docstring": docstring,
            "functions": functions,
        }

    def explain_package(self, package_id: str) -> PackageInfo:
        """Explain a package with its files and chain."""
        pkg_upper = package_id.upper()
        files = []
        specs = set()
        frameworks = set()

        # For kernel packages, read from manifest
        manifest_path = self.root / "installed" / package_id / "manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
                for asset in manifest.get("assets", []):
                    fpath = asset.get("path", "")
                    sha256 = asset.get("sha256", "")

                    # Find artifact info
                    purpose = ""
                    spec_id = ""
                    for aid, adata in self._artifacts.items():
                        apath = adata.get("artifact_path", "").lstrip("/")
                        if apath == fpath:
                            purpose = adata.get("purpose", "")
                            spec_id = adata.get("source_spec_id", "")
                            break

                    if spec_id:
                        specs.add(spec_id)
                        sdata = self._specs.get(spec_id, {})
                        fw = sdata.get("framework_id", "")
                        if fw:
                            frameworks.add(fw)

                    # Verify hash
                    full_path = self.root / fpath
                    hash_verified = False
                    if full_path.exists() and sha256:
                        current = f"sha256:{hash_file(full_path)}"
                        hash_verified = current == sha256

                    files.append(FileInfo(
                        path=fpath,
                        purpose=purpose,
                        package=pkg_upper,
                        sha256=sha256,
                        classification=self._files.get(fpath, {}).get("classification", ""),
                        hash_verified=hash_verified,
                    ))
            except Exception:
                pass

        # Fallback: check file_ownership for non-manifest packages
        if not files:
            for fpath, fdata in self._files.items():
                if fdata.get("owner_package_id", "").upper() == pkg_upper:
                    # Find artifact for this file
                    purpose = ""
                    spec_id = ""
                    for aid, adata in self._artifacts.items():
                        apath = adata.get("artifact_path", "").lstrip("/")
                        if apath == fpath:
                            purpose = adata.get("purpose", "")
                            spec_id = adata.get("source_spec_id", "")
                            break

                    if spec_id:
                        specs.add(spec_id)
                        sdata = self._specs.get(spec_id, {})
                        fw = sdata.get("framework_id", "")
                        if fw:
                            frameworks.add(fw)

                    # Verify hash
                    full_path = self.root / fpath
                    hash_verified = False
                    sha256 = fdata.get("sha256", "")
                    if full_path.exists() and sha256:
                        current = f"sha256:{hash_file(full_path)}"
                        hash_verified = current == sha256

                    files.append(FileInfo(
                        path=fpath,
                        purpose=purpose,
                        package=pkg_upper,
                        sha256=sha256,
                        classification=fdata.get("classification", ""),
                        hash_verified=hash_verified,
                    ))

        # Check tier status for kernel packages
        tier_status = {}
        parity = True
        if "KERNEL" in pkg_upper:
            for tier in ["ho3", "ho2", "ho1"]:
                if tier == "ho3":
                    tier_manifest = self.root / "installed" / package_id / "manifest.json"
                else:
                    tier_manifest = self.root / "planes" / tier / "installed" / package_id / "manifest.json"

                if tier_manifest.exists():
                    tier_status[tier.upper()] = "installed"
                else:
                    tier_status[tier.upper()] = "missing"
                    parity = False

        return PackageInfo(
            package_id=pkg_upper,
            files=files,
            frameworks=sorted(frameworks),
            specs=sorted(specs),
            tier_status=tier_status,
            parity=parity,
        )

    def explain(self, query: str) -> Dict:
        """Explain anything - auto-detect type and provide full chain."""
        item_type, data = self._detect_type(query)

        if item_type == "framework":
            info = self.explain_framework(data.get("framework_id", query))
            return {"type": "framework", "data": asdict(info)}

        elif item_type == "spec":
            info = self.explain_spec(data.get("spec_id", query))
            return {"type": "spec", "data": info}

        elif item_type == "file":
            info = self.explain_file(data.get("file_path", query))
            return {"type": "file", "data": info}

        elif item_type == "package":
            info = self.explain_package(data.get("package_id", query))
            return {"type": "package", "data": asdict(info)}

        elif item_type == "artifact":
            # Treat artifacts as files
            path = data.get("artifact_path", "").lstrip("/")
            info = self.explain_file(path)
            return {"type": "file", "data": info}

        else:
            return {"type": "unknown", "data": {"query": query, "message": "Not found"}}

    def _load_governed_config(self) -> dict:
        """Load governed roots configuration."""
        config_path = self.root / "config" / "governed_roots.json"
        if config_path.exists():
            with open(config_path) as f:
                return json.load(f)
        return {"governed_roots": [], "excluded_patterns": []}

    def _matches_exclusion(self, path: str, patterns: List[str]) -> bool:
        """Check if path matches any exclusion pattern."""
        from fnmatch import fnmatch
        for pattern in patterns:
            if fnmatch(path, pattern):
                return True
            # Handle ** patterns
            if "**" in pattern:
                simple = pattern.replace("**", "*")
                if fnmatch(path, simple):
                    return True
        return False

    def inventory(self) -> InventoryInfo:
        """Generate full system inventory."""
        frameworks = []
        all_packages = set()
        total_files = 0

        for fid in sorted(self._frameworks.keys()):
            finfo = self.explain_framework(fid)
            frameworks.append(finfo)
            total_files += finfo.total_files
            all_packages.update(finfo.packages)

        # Count orphans using G0B definition with exclusions from governed_roots.json
        config = self._load_governed_config()
        governed_roots = [r.rstrip("/") for r in config.get("governed_roots", [])]
        excluded_patterns = config.get("excluded_patterns", [])

        orphans = 0
        for root in governed_roots:
            root_path = self.root / root
            if root_path.is_dir():
                for fpath in root_path.rglob("*"):
                    if fpath.is_file():
                        rel_path = str(fpath.relative_to(self.root))
                        # Skip pycache and hidden files
                        if "__pycache__" in rel_path:
                            continue
                        if any(part.startswith(".") for part in Path(rel_path).parts):
                            continue
                        # Skip excluded patterns (same as G0B)
                        if self._matches_exclusion(rel_path, excluded_patterns):
                            continue
                        if rel_path not in self._files:
                            orphans += 1

        health = "healthy" if orphans == 0 else "orphans_detected"

        return InventoryInfo(
            frameworks=frameworks,
            packages=sorted(all_packages),
            total_files=len(self._files),
            orphans=orphans,
            health=health,
        )

    def list_installed(self) -> List[InstalledPackageInfo]:
        """List all installed packages with details."""
        installed = []
        installed_dir = self.root / "installed"

        if not installed_dir.exists():
            return installed

        for pkg_dir in sorted(installed_dir.iterdir()):
            if not pkg_dir.is_dir():
                continue

            manifest_path = pkg_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)

                # Get installation time from receipt if available
                receipt_path = pkg_dir / "receipt.json"
                installed_at = ""
                if receipt_path.exists():
                    with open(receipt_path) as f:
                        receipt = json.load(f)
                        installed_at = receipt.get("installed_at", "")

                installed.append(InstalledPackageInfo(
                    package_id=manifest.get("package_id", pkg_dir.name),
                    version=manifest.get("version", ""),
                    file_count=len(manifest.get("assets", [])),
                    manifest_hash=manifest.get("manifest_hash", ""),
                    installed_at=installed_at or manifest.get("metadata", {}).get("built_at", ""),
                    tier="HO3",
                ))
            except Exception:
                continue

        return installed

    def verify(self) -> VerifyResult:
        """Run verification checks and return pass/fail result."""
        checks = []
        all_passed = True

        # Check 1: Orphan count
        inv = self.inventory()
        orphan_passed = inv.orphans == 0
        checks.append({
            "name": "Registry orphans",
            "passed": orphan_passed,
            "message": f"{inv.orphans} orphans" if not orphan_passed else "0 orphans",
        })
        if not orphan_passed:
            all_passed = False

        # Check 2: File hash integrity
        hash_mismatches = []
        for fpath, fdata in self._files.items():
            recorded = fdata.get("sha256", "")
            if not recorded:
                continue
            full_path = self.root / fpath
            if full_path.exists():
                current = f"sha256:{hash_file(full_path)}"
                if current != recorded:
                    hash_mismatches.append(fpath)

        hash_passed = len(hash_mismatches) == 0
        checks.append({
            "name": "File hash integrity",
            "passed": hash_passed,
            "message": f"{len(hash_mismatches)} mismatches" if not hash_passed else f"{len(self._files)} files verified",
            "details": hash_mismatches[:5] if hash_mismatches else None,
        })
        if not hash_passed:
            all_passed = False

        # Check 3: Kernel parity (if kernel exists)
        kernel_info = self.explain_package("PKG-KERNEL-001")
        if kernel_info.tier_status:
            parity_passed = kernel_info.parity
            checks.append({
                "name": "Kernel parity (G0K)",
                "passed": parity_passed,
                "message": "All tiers match" if parity_passed else "Parity failed",
                "details": kernel_info.tier_status,
            })
            if not parity_passed:
                all_passed = False

        # Check 4: Ledger chain (basic check)
        ledger_path = self.root / "ledger" / "governance.jsonl"
        ledger_passed = ledger_path.exists()
        checks.append({
            "name": "Ledger exists",
            "passed": ledger_passed,
            "message": "governance.jsonl found" if ledger_passed else "Ledger missing",
        })
        if not ledger_passed:
            all_passed = False

        return VerifyResult(
            passed=all_passed,
            checks=checks,
            message="VERIFIED" if all_passed else "FAILED",
        )


# ============================================================================
# Formatters
# ============================================================================

class MarkdownFormatter:
    """Format output as human-readable Markdown."""

    def format_framework(self, info: FrameworkInfo) -> str:
        """Format framework explanation."""
        lines = [
            f"# {info.framework_id}: {info.title}",
            "",
            f"**Status:** {info.status} | **Specs:** {len(info.specs)} | **Files:** {info.total_files}",
            "",
        ]

        for spec in info.specs:
            lines.append("---")
            lines.append("")
            lines.append(f"## {spec.spec_id}: {spec.title}")
            lines.append("")

            if spec.files:
                lines.append("| File | Purpose | Package |")
                lines.append("|------|---------|---------|")
                for f in spec.files:
                    purpose = f.purpose[:50] + "..." if len(f.purpose) > 50 else f.purpose
                    lines.append(f"| {f.path} | {purpose} | {f.package} |")
                lines.append("")

        if info.packages:
            lines.append("---")
            lines.append("")
            lines.append("## Packages")
            lines.append("")
            for pkg in info.packages:
                lines.append(f"- {pkg}")
            lines.append("")

        return "\n".join(lines)

    def format_spec(self, data: Dict) -> str:
        """Format spec explanation."""
        lines = [
            f"# {data['spec_id']}: {data['title']}",
            "",
            f"**Status:** {data['status']}",
            "",
            "## Framework",
            "",
            f"- **{data['framework']['framework_id']}**: {data['framework']['title']}",
            "",
            "## Files",
            "",
        ]

        if data['files']:
            lines.append("| File | Purpose | Package |")
            lines.append("|------|---------|---------|")
            for f in data['files']:
                purpose = f['purpose'][:50] + "..." if len(f['purpose']) > 50 else f['purpose']
                lines.append(f"| {f['path']} | {purpose} | {f['package']} |")
        else:
            lines.append("No files registered.")

        lines.append("")
        return "\n".join(lines)

    def format_file(self, data: Dict) -> str:
        """Format file explanation."""
        own = data['ownership']
        lines = [
            f"# {data['path']}",
            "",
        ]

        if data['docstring']:
            # First paragraph of docstring
            first_para = data['docstring'].split("\n\n")[0]
            lines.append(f"> {first_para}")
            lines.append("")

        lines.append("## Ownership Chain")
        lines.append("")
        lines.append("```")
        lines.append(f"{own['framework_id']} ({own['framework_title']})")
        lines.append(f"  └── {own['spec_id']} ({own['spec_title']})")
        lines.append(f"        └── {data['path']} ← YOU ARE HERE")
        lines.append(f"              └── {own['package']}")
        lines.append("```")
        lines.append("")

        lines.append("## Details")
        lines.append("")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| **Package** | {own['package']} |")
        lines.append(f"| **Spec** | {own['spec_id']} |")
        lines.append(f"| **Framework** | {own['framework_id']} |")
        lines.append(f"| **Classification** | {data['classification']} |")

        hash_status = "verified" if data['hash']['verified'] else "MISMATCH"
        if data['hash']['recorded']:
            lines.append(f"| **SHA256** | `{data['hash']['recorded'][:20]}...` {hash_status} |")
        lines.append("")

        if data['functions']:
            lines.append("## Functions")
            lines.append("")
            lines.append("| Function | Purpose |")
            lines.append("|----------|---------|")
            for func in data['functions'][:10]:
                lines.append(f"| `{func['name']}()` | {func['purpose']} |")
            lines.append("")

        return "\n".join(lines)

    def format_package(self, info: PackageInfo) -> str:
        """Format package explanation."""
        lines = [
            f"# {info.package_id}",
            "",
        ]

        if info.tier_status:
            lines.append("## Tier Status")
            lines.append("")
            lines.append("| Tier | Status | Hash |")
            lines.append("|------|--------|------|")
            for tier, status in info.tier_status.items():
                icon = "+" if status == "installed" else "x"
                lines.append(f"| {tier} | {icon} {status} | - |")
            lines.append("")
            parity_icon = "+" if info.parity else "x"
            lines.append(f"**Parity:** {parity_icon} {'All tiers match' if info.parity else 'MISMATCH'}")
            lines.append("")

        lines.append("## Contents")
        lines.append("")
        if info.files:
            lines.append("| File | Spec | Purpose |")
            lines.append("|------|------|---------|")
            for f in info.files:
                # Find spec for this file
                spec = ""
                for aid, adata in TraceEngine(CONTROL_PLANE)._artifacts.items():
                    if adata.get("artifact_path", "").lstrip("/") == f.path:
                        spec = adata.get("source_spec_id", "")
                        break
                purpose = f.purpose[:40] + "..." if len(f.purpose) > 40 else f.purpose
                lines.append(f"| {f.path} | {spec} | {purpose} |")
            lines.append("")
        else:
            lines.append("No files registered.")
            lines.append("")

        if info.frameworks:
            lines.append("## Frameworks Covered")
            lines.append("")
            for fw in info.frameworks:
                lines.append(f"- {fw}")
            lines.append("")

        return "\n".join(lines)

    def format_inventory(self, info: InventoryInfo) -> str:
        """Format inventory."""
        lines = [
            "# Control Plane Inventory",
            "",
            f"**Health:** {'+ healthy' if info.health == 'healthy' else 'x ' + info.health}",
            f"**Orphans:** {info.orphans}",
            "",
            "## By Framework",
            "",
            "| Framework | Specs | Files | Packages |",
            "|-----------|-------|-------|----------|",
        ]

        for fw in info.frameworks:
            lines.append(f"| {fw.framework_id} | {len(fw.specs)} | {fw.total_files} | {len(fw.packages)} |")

        lines.append(f"| **Total** | **{sum(len(f.specs) for f in info.frameworks)}** | **{info.total_files}** | **{len(info.packages)}** |")
        lines.append("")

        lines.append("## Packages")
        lines.append("")
        for pkg in info.packages:
            lines.append(f"- {pkg}")
        lines.append("")

        return "\n".join(lines)

    def format_installed(self, packages: List[InstalledPackageInfo]) -> str:
        """Format installed packages list."""
        lines = [
            "# Installed Packages",
            "",
            f"**Total:** {len(packages)} packages",
            "",
            "| Package | Version | Files | Manifest Hash | Installed |",
            "|---------|---------|-------|---------------|-----------|",
        ]

        for pkg in packages:
            hash_short = pkg.manifest_hash[:20] + "..." if pkg.manifest_hash else "-"
            installed = pkg.installed_at[:10] if pkg.installed_at else "-"
            lines.append(f"| {pkg.package_id} | {pkg.version or '-'} | {pkg.file_count} | `{hash_short}` | {installed} |")

        lines.append("")
        return "\n".join(lines)

    def format_verify(self, result: VerifyResult) -> str:
        """Format verification result."""
        lines = [
            "# Verification Report",
            "",
            "| Check | Status |",
            "|-------|--------|",
        ]

        for check in result.checks:
            icon = "+" if check['passed'] else "x"
            status = "PASS" if check['passed'] else "FAIL"
            lines.append(f"| {check['name']} | {icon} {status} ({check['message']}) |")

        lines.append("")
        icon = "+" if result.passed else "x"
        lines.append(f"**Result:** {icon} {result.message}")
        lines.append("")

        # Show failure details
        if not result.passed:
            lines.append("## Failures")
            lines.append("")
            for check in result.checks:
                if not check['passed'] and check.get('details'):
                    lines.append(f"### {check['name']}")
                    for item in check['details']:
                        lines.append(f"- {item}")
                    lines.append("")

        return "\n".join(lines)

    def format_unknown(self, data: Dict) -> str:
        """Format unknown result."""
        return f"# Not Found\n\nQuery: `{data['query']}`\n\n{data['message']}\n"


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Explain and trace Control Plane artifacts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/trace.py --explain FMWK-000
  python3 scripts/trace.py --explain lib/merkle.py
  python3 scripts/trace.py --explain PKG-KERNEL-001
  python3 scripts/trace.py --inventory
  python3 scripts/trace.py --verify
        """,
    )

    parser.add_argument(
        "--explain",
        metavar="ID",
        help="Explain anything (framework, spec, file, or package)",
    )
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="Show full system inventory",
    )
    parser.add_argument(
        "--installed",
        action="store_true",
        help="List all installed packages",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run verification checks (exit 0 if healthy, 1 if issues)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of Markdown",
    )
    parser.add_argument(
        "--agent-context",
        action="store_true",
        help="Return structured context for agent prompt headers",
    )

    args = parser.parse_args()

    if not any([args.explain, args.inventory, args.installed, args.verify, args.agent_context]):
        parser.print_help()
        sys.exit(0)

    engine = TraceEngine()
    formatter = MarkdownFormatter()

    if args.explain:
        result = engine.explain(args.explain)

        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if result['type'] == 'framework':
                info = FrameworkInfo(**result['data'])
                # Reconstruct nested dataclasses
                info.specs = [SpecInfo(**s) for s in result['data']['specs']]
                for spec in info.specs:
                    spec.files = [FileInfo(**f) for f in spec.files] if isinstance(spec.files[0], dict) else spec.files
                print(formatter.format_framework(info))
            elif result['type'] == 'spec':
                print(formatter.format_spec(result['data']))
            elif result['type'] == 'file':
                print(formatter.format_file(result['data']))
            elif result['type'] == 'package':
                info = PackageInfo(**result['data'])
                info.files = [FileInfo(**f) for f in result['data']['files']]
                print(formatter.format_package(info))
            else:
                print(formatter.format_unknown(result['data']))

    elif args.inventory:
        result = engine.inventory()

        if args.json:
            print(json.dumps(asdict(result), indent=2, default=str))
        else:
            print(formatter.format_inventory(result))

    elif args.installed:
        result = engine.list_installed()

        if args.json:
            print(json.dumps([asdict(p) for p in result], indent=2, default=str))
        else:
            print(formatter.format_installed(result))

    elif args.verify:
        result = engine.verify()

        if args.json:
            print(json.dumps(asdict(result), indent=2, default=str))
        else:
            print(formatter.format_verify(result))

        sys.exit(0 if result.passed else 1)

    elif args.agent_context:
        # Return structured context for agent prompt headers
        from datetime import datetime, timezone

        installed = engine.list_installed()
        verify_result = engine.verify()

        # Get recent governance entries (last 10)
        recent_governance = []
        ledger_path = engine.root / "ledger" / "governance.jsonl"
        if ledger_path.exists():
            with open(ledger_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in lines[-10:]:
                if line.strip():
                    try:
                        entry = json.loads(line.strip())
                        recent_governance.append({
                            "event_type": entry.get("event_type", "unknown"),
                            "timestamp": entry.get("timestamp", ""),
                            "decision": entry.get("decision", ""),
                            "submission_id": entry.get("submission_id", ""),
                        })
                    except json.JSONDecodeError:
                        pass

        context = {
            "tier": "HO1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "installed_packages": [
                {
                    "package_id": p.package_id,
                    "version": p.version,
                    "file_count": p.file_count,
                }
                for p in installed
            ],
            "recent_governance": recent_governance,
            "integrity_status": {
                "passed": verify_result.passed,
                "checks": [
                    {"name": c["name"], "passed": c["passed"]}
                    for c in verify_result.checks
                ],
            },
            "governed_roots": engine._load_governed_config().get("governed_roots", []),
        }

        print(json.dumps(context, indent=2, default=str))


if __name__ == "__main__":
    main()
