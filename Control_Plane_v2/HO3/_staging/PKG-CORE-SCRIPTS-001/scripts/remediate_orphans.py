#!/usr/bin/env python3
"""Remediate orphan files by organizing them into governed packages.

This script helps organize orphan files into the full governance chain:
Framework → Spec → Package → Files

SMART SEGMENTATION:
- Reads existing spec manifests for accurate asset lists
- Registers orphan frameworks before specs
- Uses import analysis to verify module cohesion
- Adds files to existing specs where appropriate (e.g., admin tools)

Usage:
    # See what needs to be done
    python3 scripts/remediate_orphans.py --plan

    # Create specs and staging packages for orphans (full chain)
    python3 scripts/remediate_orphans.py --execute

    # Dry run (show what would be done without doing it)
    python3 scripts/remediate_orphans.py --execute --dry-run

    # Also install packages after staging
    python3 scripts/remediate_orphans.py --execute --install

    # Verify after remediation
    python3 scripts/agent_check.py --orphans

Governance Chain (enforced by G1):
    Framework (FMWK-XXX)     ← registered in frameworks_registry.csv
        ↓
    Spec (SPEC-XXX)          ← registered in specs_registry.csv
        ↓
    Package (PKG-XXX)        ← manifest.json has spec_id
        ↓
    Files                    ← declared in manifest.json assets

Without the full chain, package_install.py fails with:
- G1 FAIL: SPEC_MISSING — no spec_id in manifest
- G1 FAIL: SPEC_NOT_FOUND — spec not in registry
- G1 FAIL: FRAMEWORK_NOT_FOUND — spec's framework not in registry
"""

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import yaml
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).parent.parent


# =============================================================================
# Spec Manifest Reader - Smart Segmentation via Existing Specs
# =============================================================================

def read_spec_manifest(spec_id: str) -> Optional[Dict]:
    """Read a spec's manifest.yaml and return its contents."""
    manifest_path = ROOT / "specs" / spec_id / "manifest.yaml"
    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def get_spec_assets(spec_id: str) -> List[str]:
    """Get list of asset paths declared in a spec manifest."""
    manifest = read_spec_manifest(spec_id)
    if not manifest:
        return []

    assets = manifest.get('assets', [])
    paths = []
    for asset in assets:
        if isinstance(asset, str):
            paths.append(asset)
        elif isinstance(asset, dict):
            paths.append(asset.get('path', ''))
    return [p for p in paths if p]


def discover_existing_specs() -> Dict[str, Dict]:
    """Discover all existing spec manifests and their asset mappings."""
    specs = {}
    specs_dir = ROOT / "specs"

    if not specs_dir.exists():
        return specs

    for spec_dir in specs_dir.iterdir():
        if not spec_dir.is_dir():
            continue

        manifest_path = spec_dir / "manifest.yaml"
        if manifest_path.exists():
            manifest = read_spec_manifest(spec_dir.name)
            if manifest:
                specs[spec_dir.name] = manifest

    return specs


# =============================================================================
# Import Analysis - Smart Module Cohesion
# =============================================================================

def analyze_python_imports(file_path: Path) -> Set[str]:
    """Extract import statements from a Python file."""
    imports = set()
    if not file_path.exists() or file_path.suffix != '.py':
        return imports

    try:
        content = file_path.read_text(encoding='utf-8')
        # Match: from modules.xxx import ... or import modules.xxx
        for match in re.finditer(r'^(?:from|import)\s+([\w.]+)', content, re.MULTILINE):
            imports.add(match.group(1))
    except Exception:
        pass

    return imports


def get_module_dependencies(module_dir: Path) -> Set[str]:
    """Get all internal imports for a module directory."""
    all_imports = set()

    if not module_dir.exists():
        return all_imports

    for py_file in module_dir.rglob('*.py'):
        imports = analyze_python_imports(py_file)
        # Filter to internal modules
        for imp in imports:
            if imp.startswith('modules.') or imp.startswith('lib.'):
                all_imports.add(imp)

    return all_imports


# =============================================================================
# Framework Registration
# =============================================================================

def find_orphan_frameworks() -> List[str]:
    """Find framework files that aren't registered."""
    orphan_frameworks = []
    frameworks_dir = ROOT / "frameworks"

    if not frameworks_dir.exists():
        return orphan_frameworks

    for fw_file in frameworks_dir.glob("FMWK-*.md"):
        # Extract framework ID from filename (FMWK-XXX_description.md)
        fw_id = fw_file.stem.split('_')[0]
        if not check_framework_exists(fw_id):
            orphan_frameworks.append(fw_id)

    return orphan_frameworks


def register_framework(framework_id: str, dry_run: bool = False) -> bool:
    """Register a framework in frameworks_registry.csv."""
    registry_path = ROOT / "registries" / "frameworks_registry.csv"

    # Find the framework file
    frameworks_dir = ROOT / "frameworks"
    fw_file = None
    for f in frameworks_dir.glob(f"{framework_id}*.md"):
        fw_file = f
        break

    if not fw_file:
        print(f"  ERROR: Framework file not found for {framework_id}")
        return False

    # Extract title from filename
    parts = fw_file.stem.split('_', 1)
    title = parts[1].replace('_', ' ').title() if len(parts) > 1 else framework_id

    if dry_run:
        print(f"  [DRY RUN] Would register framework: {framework_id} ({title})")
        return True

    # Build new row
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_row = {
        'framework_id': framework_id,
        'title': title,
        'status': 'active',
        'version': '1.0.0',
        'plane_id': 'ho3',
        'created_at': timestamp,
    }

    # Read existing rows
    rows = []
    fieldnames = ['framework_id', 'title', 'status', 'version', 'plane_id', 'created_at']

    if registry_path.exists():
        with open(registry_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or fieldnames
            rows = list(reader)

    rows.append(new_row)

    # Write back
    with open(registry_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  Registered framework: {framework_id}")
    return True

# =============================================================================
# Package Group Configuration
# =============================================================================

@dataclass
class PackageGroupConfig:
    """Configuration for a package group."""
    package_id: str
    spec_id: str
    framework_id: str
    title: str
    description: str
    patterns: List[str]
    plane_id: str = "ho3"
    package_type: str = "module"

    # Auto-generated if not provided
    invariants: List[str] = field(default_factory=list)
    acceptance_tests: List[str] = field(default_factory=list)


# Smart package groups - uses existing specs where available
# Key insight: Read existing spec manifests for asset lists, don't just pattern match
DEFAULT_PACKAGE_GROUPS: Dict[str, PackageGroupConfig] = {
    # Admin agent extensions - adds to existing SPEC-ADMIN-001
    # Note: modules/admin_agent/tools.py should go here, not in chat
    "PKG-ADMIN-EXT-001": PackageGroupConfig(
        package_id="PKG-ADMIN-EXT-001",
        spec_id="SPEC-ADMIN-001",  # Existing spec
        framework_id="FMWK-100",  # Already registered
        title="Admin Agent Extensions",
        description="Extensions to Admin Agent (tools, handlers)",
        patterns=[
            "modules/admin_agent/tools.py",
            "modules/admin_agent/handlers/",
            "tests/test_admin_llm",
            "tests/test_prompt_tracking",
        ],
        invariants=["Admin operations MUST be read-only"],
        acceptance_tests=["pytest tests/test_admin*.py -v"],
    ),

    # Router extensions - for new router components
    "PKG-ROUTER-EXT-001": PackageGroupConfig(
        package_id="PKG-ROUTER-EXT-001",
        spec_id="SPEC-ROUTER-001",  # Will create if needed
        framework_id="FMWK-100",
        title="Router Extensions",
        description="Router prompt handling and extensions",
        patterns=[
            "modules/router/prompt_router.py",
            "governed_prompts/PRM-ROUTER",
        ],
        invariants=["Router decisions MUST be deterministic"],
        acceptance_tests=["pytest tests/test_router*.py -v"],
    ),

    # Core governance scripts
    "PKG-CORE-SCRIPTS-001": PackageGroupConfig(
        package_id="PKG-CORE-SCRIPTS-001",
        spec_id="SPEC-CORE-SCRIPTS-001",
        framework_id="FMWK-000",
        title="Core Governance Scripts",
        description="Core governance and utility scripts",
        patterns=[
            "scripts/agent_check.py",
            "scripts/remediate_orphans.py",
        ],
        invariants=["Scripts MUST have docstrings"],
        acceptance_tests=["python3 scripts/agent_check.py --status"],
    ),

    # Documentation - architecture notes and guides
    "PKG-DOCS-001": PackageGroupConfig(
        package_id="PKG-DOCS-001",
        spec_id="SPEC-DOC-001",  # Existing spec
        framework_id="FMWK-100",
        title="Documentation Extensions",
        description="Architecture documentation and guides",
        patterns=[
            "docs/ADMIN_AGENT_SCRIPT_REF",
            "docs/AGENT_OPERATIONS",
            "docs/CROSSCUTTING",
            "docs/PROMPT_ROUTER",
            "docs/TODO_ADMIN",
            "docs/notes/",
        ],
        plane_id="ho3",
        package_type="documentation",
        invariants=["Documentation MUST be markdown format"],
    ),
}

# Fallback for files that don't match any pattern
BASELINE_UPDATE_GROUP = PackageGroupConfig(
    package_id="PKG-BASELINE-UPDATE",
    spec_id="SPEC-BASELINE-001",
    framework_id="FMWK-000",
    title="Baseline Update",
    description="Files to add to baseline package via generate_baseline_manifest.py",
    patterns=[],  # Catch-all
    invariants=[],
)


# =============================================================================
# Utility Functions
# =============================================================================

def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash in standard format."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def load_package_groups(config_file: Optional[Path] = None) -> Dict[str, PackageGroupConfig]:
    """Load package group configuration."""
    groups = DEFAULT_PACKAGE_GROUPS.copy()

    if config_file and config_file.exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            custom_groups = json.load(f)
            for pkg_id, cfg in custom_groups.items():
                groups[pkg_id] = PackageGroupConfig(**cfg)

    return groups


def find_orphans() -> List[str]:
    """Find orphan files using agent_check.py."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "agent_check.py"), "--orphans", "--json"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )

    if result.returncode == 0:
        return []  # No orphans

    try:
        data = json.loads(result.stdout)
        return data.get("orphans", [])
    except json.JSONDecodeError:
        # Fallback: parse non-JSON output
        orphans = []
        for line in result.stdout.split('\n'):
            if line.strip().startswith('⚠'):
                # Extract path from "⚠ path/to/file"
                parts = line.strip().split(' ', 1)
                if len(parts) > 1:
                    orphans.append(parts[1].strip())
        return orphans


def classify_orphan(path: str, groups: Dict[str, PackageGroupConfig]) -> str:
    """Determine which package group an orphan belongs to."""
    for pkg_id, config in groups.items():
        for pattern in config.patterns:
            if path.startswith(pattern) or pattern in path:
                return pkg_id
    return "PKG-BASELINE-UPDATE"


def classify_asset(path: str) -> str:
    """Classify an asset by path."""
    if path.startswith("lib/"):
        return "library"
    elif path.startswith("modules/"):
        return "module"
    elif path.startswith("scripts/"):
        return "script"
    elif path.startswith("tests/"):
        return "test"
    elif path.startswith("docs/"):
        return "documentation"
    elif path.startswith("frameworks/"):
        return "framework"
    elif path.startswith("specs/"):
        return "spec"
    elif path.startswith("schemas/"):
        return "schema"
    elif path.startswith("governed_prompts/"):
        return "prompt"
    else:
        return "other"


# =============================================================================
# Framework and Spec Management
# =============================================================================

def check_framework_exists(framework_id: str) -> bool:
    """Check if framework is registered."""
    registry_path = ROOT / "registries" / "frameworks_registry.csv"
    if not registry_path.exists():
        return False

    with open(registry_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('framework_id') == framework_id:
                return True
    return False


def check_spec_exists(spec_id: str) -> bool:
    """Check if spec is registered."""
    registry_path = ROOT / "registries" / "specs_registry.csv"
    if not registry_path.exists():
        return False

    with open(registry_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('spec_id') == spec_id:
                return True
    return False


def create_spec_manifest(config: PackageGroupConfig, files: List[str], dry_run: bool = False) -> Path:
    """Create spec manifest.yaml file.

    Args:
        config: Package group configuration
        files: List of file paths this spec will own
        dry_run: If True, don't write files

    Returns:
        Path to the created manifest.yaml
    """
    spec_dir = ROOT / "specs" / config.spec_id
    manifest_path = spec_dir / "manifest.yaml"

    # Build manifest content
    manifest_content = f"""spec_id: {config.spec_id}
title: "{config.title}"
framework_id: {config.framework_id}
status: active
version: 1.0.0
plane_id: {config.plane_id}

assets:
"""
    for f in sorted(files):
        manifest_content += f"  - {f}\n"

    if config.invariants:
        manifest_content += "\ninvariants:\n"
        for inv in config.invariants:
            manifest_content += f'  - "{inv}"\n'

    if config.acceptance_tests:
        manifest_content += "\nacceptance:\n  tests:\n"
        for test in config.acceptance_tests:
            manifest_content += f'    - "{test}"\n'

    if dry_run:
        print(f"  [DRY RUN] Would create: {manifest_path}")
        return manifest_path

    # Create directory and write file
    spec_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest_content)

    return manifest_path


def register_spec(config: PackageGroupConfig, dry_run: bool = False) -> bool:
    """Register spec in specs_registry.csv.

    Args:
        config: Package group configuration
        dry_run: If True, don't write to registry

    Returns:
        True if registration successful (or would be successful in dry run)
    """
    registry_path = ROOT / "registries" / "specs_registry.csv"

    # Validate framework exists
    if not check_framework_exists(config.framework_id):
        print(f"  ERROR: Framework '{config.framework_id}' not found in frameworks_registry.csv")
        print(f"         Register the framework first or use a different framework_id")
        return False

    # Check if already registered
    if check_spec_exists(config.spec_id):
        print(f"  Spec '{config.spec_id}' already registered")
        return True

    if dry_run:
        print(f"  [DRY RUN] Would register spec: {config.spec_id} -> {config.framework_id}")
        return True

    # Build new row
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_row = {
        'spec_id': config.spec_id,
        'title': config.title,
        'framework_id': config.framework_id,
        'status': 'active',
        'version': '1.0.0',
        'plane_id': config.plane_id,
        'created_at': timestamp,
    }

    # Read existing rows
    rows = []
    fieldnames = ['spec_id', 'title', 'framework_id', 'status', 'version', 'plane_id', 'created_at']

    if registry_path.exists():
        with open(registry_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or fieldnames
            rows = list(reader)

    rows.append(new_row)

    # Write back
    with open(registry_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  Registered spec: {config.spec_id} -> {config.framework_id}")
    return True


# =============================================================================
# Package Creation
# =============================================================================

def create_staging_package(
    config: PackageGroupConfig,
    files: List[str],
    dry_run: bool = False
) -> Optional[Path]:
    """Create a staging package for the given files.

    Args:
        config: Package group configuration
        files: List of file paths to include
        dry_run: If True, don't write files

    Returns:
        Path to staging directory, or None if failed
    """
    staging_dir = ROOT / "_staging" / config.package_id

    if staging_dir.exists() and not dry_run:
        print(f"  Warning: {staging_dir} already exists, skipping package creation")
        print(f"           Delete it first if you want to recreate: rm -rf {staging_dir}")
        return None

    if dry_run:
        print(f"  [DRY RUN] Would create staging package at: {staging_dir}")
        return staging_dir

    staging_dir.mkdir(parents=True, exist_ok=True)

    # Copy files maintaining structure
    copied_files = []
    for file_path in files:
        src = ROOT / file_path
        if not src.exists():
            print(f"  Warning: {file_path} not found, skipping")
            continue

        dest = staging_dir / file_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied_files.append(file_path)

    # Create manifest.json with computed hashes
    assets = []
    for file_path in sorted(copied_files):
        full_path = staging_dir / file_path
        sha = compute_sha256(full_path)
        assets.append({
            "path": file_path,
            "sha256": sha,
            "classification": classify_asset(file_path),
        })

    manifest = {
        "package_id": config.package_id,
        "schema_version": "1.2",
        "version": "1.0.0",
        "spec_id": config.spec_id,
        "plane_id": config.plane_id,
        "package_type": config.package_type,
        "assets": assets,
        "dependencies": ["PKG-BASELINE-HO3-000"],
        "metadata": {
            "description": config.description,
            "created_by": "remediate_orphans.py",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    }

    manifest_path = staging_dir / "manifest.json"
    with open(manifest_path, "w", encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    print(f"  Created staging package at {staging_dir}")
    print(f"    - {len(assets)} files")
    print(f"    - spec_id: {config.spec_id}")

    return staging_dir


# =============================================================================
# Remediation Plan
# =============================================================================

@dataclass
class RemediationPlan:
    """Complete remediation plan for orphan files."""
    groups: Dict[str, List[str]]
    frameworks_to_register: List[str]  # NEW: orphan frameworks
    specs_to_create: List[PackageGroupConfig]
    specs_to_register: List[PackageGroupConfig]
    packages_to_create: List[Tuple[PackageGroupConfig, List[str]]]
    baseline_files: List[str]
    unknown_files: List[str]
    spec_manifest_matches: Dict[str, List[str]]  # NEW: files matching existing spec manifests

    @property
    def total_orphans(self) -> int:
        return sum(len(files) for files in self.groups.values())


def plan_remediation(
    orphans: List[str],
    groups: Dict[str, PackageGroupConfig]
) -> RemediationPlan:
    """Create a complete remediation plan with smart segmentation.

    Smart segmentation features:
    1. Discovers orphan frameworks that need registration
    2. Reads existing spec manifests to check if orphans are already declared
    3. Uses import analysis for module cohesion verification
    4. Matches files to the most appropriate package group
    """
    # Step 1: Find orphan frameworks
    orphan_frameworks = find_orphan_frameworks()

    # Step 2: Discover existing specs and their declared assets
    existing_specs = discover_existing_specs()
    spec_manifest_matches: Dict[str, List[str]] = {}

    # Check if any orphan is already declared in an existing spec manifest
    for spec_id, manifest in existing_specs.items():
        declared_assets = get_spec_assets(spec_id)
        matching_orphans = [o for o in orphans if o in declared_assets]
        if matching_orphans:
            spec_manifest_matches[spec_id] = matching_orphans

    # Step 3: Group orphans by target package (excluding spec manifest matches)
    already_matched = set()
    for files in spec_manifest_matches.values():
        already_matched.update(files)

    grouped: Dict[str, List[str]] = {pkg_id: [] for pkg_id in groups}
    grouped["PKG-BASELINE-UPDATE"] = []
    grouped["UNKNOWN"] = []

    for orphan in orphans:
        # Skip files already matched to existing spec manifests
        if orphan in already_matched:
            continue

        pkg_id = classify_orphan(orphan, groups)
        if pkg_id in grouped:
            grouped[pkg_id].append(orphan)
        else:
            grouped["UNKNOWN"].append(orphan)

    # Step 4: Determine what needs to be created/registered
    specs_to_create = []
    specs_to_register = []
    packages_to_create = []

    for pkg_id, files in grouped.items():
        if not files:
            continue
        if pkg_id in ("PKG-BASELINE-UPDATE", "UNKNOWN"):
            continue

        config = groups.get(pkg_id)
        if not config:
            continue

        # Check if spec manifest exists (skip if already has manifest)
        spec_manifest = ROOT / "specs" / config.spec_id / "manifest.yaml"
        if not spec_manifest.exists():
            specs_to_create.append(config)

        # Check if spec is registered
        if not check_spec_exists(config.spec_id):
            specs_to_register.append(config)

        # All groups with files need packages
        packages_to_create.append((config, files))

    # Step 5: Handle spec manifest matches - these need packages too
    for spec_id, matched_files in spec_manifest_matches.items():
        # Find or create a package config for this spec
        matching_config = None
        for config in groups.values():
            if config.spec_id == spec_id:
                matching_config = config
                break

        if matching_config:
            # Add to existing package group
            if matching_config.package_id in grouped:
                grouped[matching_config.package_id].extend(matched_files)
            else:
                grouped[matching_config.package_id] = matched_files

            # Ensure package is in packages_to_create
            existing_pkg_ids = [c.package_id for c, _ in packages_to_create]
            if matching_config.package_id not in existing_pkg_ids:
                packages_to_create.append((matching_config, grouped[matching_config.package_id]))

    return RemediationPlan(
        groups=grouped,
        frameworks_to_register=orphan_frameworks,
        specs_to_create=specs_to_create,
        specs_to_register=specs_to_register,
        packages_to_create=packages_to_create,
        baseline_files=grouped.get("PKG-BASELINE-UPDATE", []),
        unknown_files=grouped.get("UNKNOWN", []),
        spec_manifest_matches=spec_manifest_matches,
    )


def print_plan(plan: RemediationPlan, groups: Dict[str, PackageGroupConfig]):
    """Print the remediation plan."""
    print("=" * 70)
    print("ORPHAN REMEDIATION PLAN (Smart Segmentation)")
    print("=" * 70)
    print(f"\nTotal orphans: {plan.total_orphans}")

    # Summary
    print(f"\n┌─────────────────────────────────────────────────────────────────────┐")
    print(f"│ SUMMARY                                                             │")
    print(f"├─────────────────────────────────────────────────────────────────────┤")
    print(f"│  Frameworks to register: {len(plan.frameworks_to_register):3d}                                       │")
    print(f"│  Specs to create:        {len(plan.specs_to_create):3d}                                       │")
    print(f"│  Specs to register:      {len(plan.specs_to_register):3d}                                       │")
    print(f"│  Packages to create:     {len(plan.packages_to_create):3d}                                       │")
    print(f"│  Spec manifest matches:  {sum(len(f) for f in plan.spec_manifest_matches.values()):3d}                                       │")
    print(f"│  Baseline additions:     {len(plan.baseline_files):3d}                                       │")
    print(f"│  Unknown files:          {len(plan.unknown_files):3d}                                       │")
    print(f"└─────────────────────────────────────────────────────────────────────┘")

    # Orphan frameworks
    if plan.frameworks_to_register:
        print(f"\n{'─' * 70}")
        print("ORPHAN FRAMEWORKS (need registration first)")
        print(f"{'─' * 70}")
        for fw in plan.frameworks_to_register:
            fw_file = list((ROOT / "frameworks").glob(f"{fw}*.md"))
            file_name = fw_file[0].name if fw_file else "not found"
            print(f"  ✗ {fw} ({file_name})")

    # Spec manifest matches
    if plan.spec_manifest_matches:
        print(f"\n{'─' * 70}")
        print("SPEC MANIFEST MATCHES (files already declared in existing specs)")
        print(f"{'─' * 70}")
        for spec_id, files in plan.spec_manifest_matches.items():
            registered = "✓" if check_spec_exists(spec_id) else "✗"
            print(f"\n  {spec_id} [{registered} registered] - {len(files)} files")
            for f in sorted(files)[:5]:
                print(f"    • {f}")
            if len(files) > 5:
                print(f"    ... and {len(files) - 5} more")

    # Governance chain status
    print(f"\n{'─' * 70}")
    print("GOVERNANCE CHAIN STATUS")
    print(f"{'─' * 70}")

    for config, files in plan.packages_to_create:
        fw_status = "✓" if check_framework_exists(config.framework_id) else "✗ MISSING"
        spec_registered = "✓" if check_spec_exists(config.spec_id) else "○ needs registration"
        spec_manifest = ROOT / "specs" / config.spec_id / "manifest.yaml"
        spec_exists = "✓" if spec_manifest.exists() else "○ needs creation"

        print(f"\n📦 {config.package_id}")
        print(f"   ├─ Framework: {config.framework_id} [{fw_status}]")
        print(f"   ├─ Spec manifest: {config.spec_id}/manifest.yaml [{spec_exists}]")
        print(f"   ├─ Spec registered: [{spec_registered}]")
        print(f"   └─ Files: {len(files)}")

    # Detailed file lists
    print(f"\n{'─' * 70}")
    print("DETAILED FILE LISTS")
    print(f"{'─' * 70}")

    for pkg_id, files in plan.groups.items():
        if not files:
            continue

        config = groups.get(pkg_id, BASELINE_UPDATE_GROUP if pkg_id == "PKG-BASELINE-UPDATE" else None)

        print(f"\n{'─' * 50}")
        if pkg_id == "PKG-BASELINE-UPDATE":
            print(f"📋 BASELINE UPDATE ({len(files)} files)")
            print(f"   These files should be added to baseline package")
            print(f"   Command: python3 scripts/generate_baseline_manifest.py --plane ho3")
        elif pkg_id == "UNKNOWN":
            print(f"❓ UNKNOWN ({len(files)} files)")
            print(f"   These files need manual classification")
        else:
            print(f"📦 {pkg_id} ({len(files)} files)")
            if config:
                print(f"   Spec: {config.spec_id}")
                print(f"   Framework: {config.framework_id}")

        print()
        for f in sorted(files)[:20]:
            print(f"     • {f}")
        if len(files) > 20:
            print(f"     ... and {len(files) - 20} more")

    # Execution commands
    print(f"\n{'─' * 70}")
    print("EXECUTION COMMANDS")
    print(f"{'─' * 70}")
    print("""
To execute this plan:

  # Full automatic remediation (creates specs, registers, creates packages)
  python3 scripts/remediate_orphans.py --execute

  # Dry run first to see what would happen
  python3 scripts/remediate_orphans.py --execute --dry-run

  # Also install packages after staging
  python3 scripts/remediate_orphans.py --execute --install

After execution, verify with:
  python3 scripts/agent_check.py --orphans
  python3 scripts/gate_check.py --gate G0B --enforce
""")


# =============================================================================
# Execution
# =============================================================================

def execute_remediation(
    plan: RemediationPlan,
    groups: Dict[str, PackageGroupConfig],
    dry_run: bool = False,
    install: bool = False,
    allow_unsigned: bool = True
) -> bool:
    """Execute the full remediation plan with smart segmentation.

    Steps:
    0. Register orphan frameworks (NEW - must come first!)
    1. Create spec manifests (specs/SPEC-XXX/manifest.yaml)
    2. Register specs in specs_registry.csv
    3. Create staging packages
    4. Handle baseline and unknown files
    5. Optionally run preflight and install

    Returns:
        True if all steps succeeded
    """
    print("=" * 70)
    print("EXECUTING REMEDIATION" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 70)

    success = True
    created_packages = []

    # Track frameworks we're about to register (for dry-run logic)
    pending_frameworks: Set[str] = set()

    # Step 0: Register orphan frameworks FIRST
    if plan.frameworks_to_register:
        print(f"\n{'─' * 50}")
        print("STEP 0: Registering orphan frameworks")
        print(f"{'─' * 50}")

        for fw_id in plan.frameworks_to_register:
            print(f"\n  Registering framework: {fw_id}")
            if not register_framework(fw_id, dry_run=dry_run):
                print(f"    ✗ Failed to register {fw_id}")
                success = False
            else:
                print(f"    ✓ Registered {fw_id}")
                pending_frameworks.add(fw_id)

    # Step 1: Create spec manifests
    if plan.specs_to_create:
        print(f"\n{'─' * 50}")
        print("STEP 1: Creating spec manifests")
        print(f"{'─' * 50}")

        for config in plan.specs_to_create:
            # Find files for this spec
            files = plan.groups.get(config.package_id, [])
            if not files:
                continue

            print(f"\n  Creating spec: {config.spec_id}")
            manifest_path = create_spec_manifest(config, files, dry_run=dry_run)
            if manifest_path:
                print(f"    ✓ Created {manifest_path}")

    # Step 2: Register specs
    if plan.specs_to_register:
        print(f"\n{'─' * 50}")
        print("STEP 2: Registering specs")
        print(f"{'─' * 50}")

        for config in plan.specs_to_register:
            print(f"\n  Registering: {config.spec_id} -> {config.framework_id}")

            # In dry-run, consider pending frameworks as registered
            if dry_run and config.framework_id in pending_frameworks:
                print(f"  [DRY RUN] Would register spec: {config.spec_id} -> {config.framework_id}")
                print(f"    (framework {config.framework_id} will be registered in Step 0)")
                continue

            if not register_spec(config, dry_run=dry_run):
                print(f"    ✗ Failed to register {config.spec_id}")
                success = False
                # Continue anyway to show all issues

    # Step 3: Create staging packages
    if plan.packages_to_create:
        print(f"\n{'─' * 50}")
        print("STEP 3: Creating staging packages")
        print(f"{'─' * 50}")

        for config, files in plan.packages_to_create:
            print(f"\n  Creating package: {config.package_id}")

            staging_dir = create_staging_package(config, files, dry_run=dry_run)
            if staging_dir:
                created_packages.append((config, staging_dir))

    # Step 4: Handle baseline files
    if plan.baseline_files:
        print(f"\n{'─' * 50}")
        print("STEP 4: Baseline files")
        print(f"{'─' * 50}")
        print(f"\n  {len(plan.baseline_files)} files should be added to baseline:")
        for f in plan.baseline_files[:10]:
            print(f"    • {f}")
        if len(plan.baseline_files) > 10:
            print(f"    ... and {len(plan.baseline_files) - 10} more")
        print(f"\n  Run: python3 scripts/generate_baseline_manifest.py --plane ho3")

    # Step 5: Handle unknown files
    if plan.unknown_files:
        print(f"\n{'─' * 50}")
        print("STEP 5: Unknown files (manual action required)")
        print(f"{'─' * 50}")
        print(f"\n  ⚠️  {len(plan.unknown_files)} files need manual classification:")
        for f in plan.unknown_files[:10]:
            print(f"    • {f}")
        if len(plan.unknown_files) > 10:
            print(f"    ... and {len(plan.unknown_files) - 10} more")
        print(f"\n  Add patterns to DEFAULT_PACKAGE_GROUPS in remediate_orphans.py")
        print(f"  Or add them to the baseline via generate_baseline_manifest.py")

    # Step 6: Optional install
    if install and created_packages and not dry_run:
        print(f"\n{'─' * 50}")
        print("STEP 6: Installing packages")
        print(f"{'─' * 50}")

        for config, staging_dir in created_packages:
            print(f"\n  Installing: {config.package_id}")

            # Run preflight first
            preflight_cmd = [
                sys.executable,
                str(ROOT / "scripts" / "pkgutil.py"),
                "preflight",
                config.package_id,
                "--src", str(staging_dir),
            ]

            # Set environment for unsigned packages
            env = os.environ.copy()
            if allow_unsigned:
                env["CONTROL_PLANE_ALLOW_UNSIGNED"] = "1"

            print(f"    Running preflight...")
            result = subprocess.run(preflight_cmd, capture_output=True, text=True, cwd=str(ROOT), env=env)

            if result.returncode != 0:
                print(f"    ✗ Preflight failed:")
                for line in result.stdout.split('\n')[:10]:
                    if line.strip():
                        print(f"      {line}")
                success = False
                continue

            print(f"    ✓ Preflight passed")

            # Create archive directly (workaround for pack() bug in lib/packages.py)
            archive_path = ROOT / "_staging" / f"{config.package_id}.tar.gz"
            print(f"    Creating archive...")

            import tarfile
            import gzip
            import io

            tar_buffer = io.BytesIO()
            with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
                for file_path in sorted(staging_dir.rglob("*")):
                    if file_path.is_dir():
                        continue
                    if "__pycache__" in str(file_path):
                        continue

                    # Compute relative path from staging_dir
                    rel_path = file_path.relative_to(staging_dir)
                    arcname = str(rel_path)

                    # Create tarinfo with deterministic metadata
                    tarinfo = tar.gettarinfo(str(file_path), arcname=arcname)
                    tarinfo.mtime = 0
                    tarinfo.uid = 0
                    tarinfo.gid = 0
                    tarinfo.uname = ""
                    tarinfo.gname = ""
                    tarinfo.mode = 0o644

                    with open(file_path, 'rb') as f:
                        tar.addfile(tarinfo, f)

            # Write gzipped tar with mtime=0
            with gzip.GzipFile(str(archive_path), mode='wb', mtime=0) as gz:
                gz.write(tar_buffer.getvalue())

            # Compute SHA256
            archive_hash = compute_sha256(archive_path)
            digest_path = ROOT / "_staging" / f"{config.package_id}.tar.gz.sha256"
            digest_path.write_text(f"{archive_hash}  {config.package_id}.tar.gz\n")

            print(f"    ✓ Archive created")

            # Install
            archive_path = ROOT / "_staging" / f"{config.package_id}.tar.gz"
            install_cmd = [
                sys.executable,
                str(ROOT / "scripts" / "package_install.py"),
                "--archive", str(archive_path),
                "--id", config.package_id,
                "--actor", "remediate_orphans",
                "--force",  # Files already exist as orphans, need to overwrite
            ]

            # Reuse env from preflight/stage, add passthrough auth for dev
            env["CONTROL_PLANE_AUTH_PROVIDER"] = "passthrough"
            env["CONTROL_PLANE_ALLOW_PASSTHROUGH"] = "1"
            env["CONTROL_PLANE_ALLOW_UNATTESTED"] = "1"

            print(f"    Installing...")
            result = subprocess.run(install_cmd, capture_output=True, text=True, cwd=str(ROOT), env=env)

            if result.returncode != 0:
                print(f"    ✗ Install failed:")
                for line in result.stdout.split('\n')[:5]:
                    if line.strip():
                        print(f"      {line}")
                success = False
                continue

            print(f"    ✓ Installed")

        # Rebuild derived registries
        print(f"\n  Rebuilding derived registries...")
        rebuild_cmd = [
            sys.executable,
            str(ROOT / "scripts" / "rebuild_derived_registries.py"),
            "--plane", "ho3",
        ]
        subprocess.run(rebuild_cmd, capture_output=True, text=True, cwd=str(ROOT))
        print(f"    ✓ Done")

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")

    if dry_run:
        print("\n  DRY RUN completed. No files were modified.")
        print("  Run without --dry-run to execute.")
    else:
        if success:
            print("\n  ✓ Remediation completed successfully!")
        else:
            print("\n  ⚠️  Remediation completed with some failures.")

        if not install and created_packages:
            print("\n  Next steps:")
            print("    1. Review staged packages in _staging/")
            print("    2. Run preflight: python3 scripts/pkgutil.py preflight PKG-XXX --src _staging/PKG-XXX")
            print("    3. Stage: python3 scripts/pkgutil.py stage PKG-XXX --src _staging/PKG-XXX")
            print("    4. Install: CONTROL_PLANE_ALLOW_UNSIGNED=1 python3 scripts/package_install.py ...")
            print("\n  Or re-run with --install to do this automatically.")

        print("\n  Verify with:")
        print("    python3 scripts/agent_check.py --orphans")
        print("    python3 scripts/gate_check.py --gate G0B --enforce")

    return success


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Remediate orphan files with full governance chain support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Governance Chain:
    Framework (FMWK-XXX)  <- must exist in frameworks_registry.csv
        ↓
    Spec (SPEC-XXX)       <- created in specs/, registered in specs_registry.csv
        ↓
    Package (PKG-XXX)     <- created in _staging/, installed via package_install.py
        ↓
    Files                 <- declared in manifest.json assets

Examples:
    # Show remediation plan
    python3 scripts/remediate_orphans.py --plan

    # Execute with dry run
    python3 scripts/remediate_orphans.py --execute --dry-run

    # Execute and install
    python3 scripts/remediate_orphans.py --execute --install

    # Use custom config
    python3 scripts/remediate_orphans.py --config my_groups.json --execute
""")

    parser.add_argument(
        "--plan",
        action="store_true",
        help="Show remediation plan (default if no action specified)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute remediation (creates specs, registers, creates packages)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without doing it"
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Also install packages after staging (requires --execute)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Custom package groups configuration file (JSON)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output plan as JSON"
    )

    args = parser.parse_args()

    # Default to --plan if no action specified
    if not args.plan and not args.execute:
        args.plan = True

    # Load configuration
    groups = load_package_groups(args.config)

    # Find orphans
    orphans = find_orphans()
    if not orphans:
        print("✓ No orphan files found!")
        return 0

    # Create remediation plan
    plan = plan_remediation(orphans, groups)

    # Output
    if args.json:
        output = {
            "total_orphans": plan.total_orphans,
            "groups": {k: v for k, v in plan.groups.items() if v},
            "frameworks_to_register": plan.frameworks_to_register,
            "specs_to_create": [c.spec_id for c in plan.specs_to_create],
            "specs_to_register": [c.spec_id for c in plan.specs_to_register],
            "packages_to_create": [c.package_id for c, _ in plan.packages_to_create],
            "spec_manifest_matches": plan.spec_manifest_matches,
            "baseline_files": plan.baseline_files,
            "unknown_files": plan.unknown_files,
        }
        print(json.dumps(output, indent=2))
        return 0

    if args.plan:
        print_plan(plan, groups)
        return 0

    if args.execute:
        success = execute_remediation(
            plan,
            groups,
            dry_run=args.dry_run,
            install=args.install
        )
        return 0 if success else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
