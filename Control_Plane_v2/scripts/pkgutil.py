#!/usr/bin/env python3
"""
pkgutil.py - Package authoring utilities for Control Plane v2.

Commands:
    init-agent       Generate agent package skeleton
    init             Generate standard package skeleton
    preflight        Run install-equivalent validation (no install)
    delta            Generate reviewable registry rows
    stage            Stage package for later install
    check-framework  Validate framework governance readiness
    register-framework  Register a framework in frameworks_registry.csv
    register-spec    Register a spec in specs_registry.csv
    compliance       Query package compliance requirements (for agents)

Usage:
    python3 scripts/pkgutil.py init-agent PKG-ADMIN-001 --framework FMWK-100
    python3 scripts/pkgutil.py init PKG-LIB-001 --spec SPEC-CORE-001
    python3 scripts/pkgutil.py preflight PKG-ADMIN-001 --src _staging/PKG-ADMIN-001
    python3 scripts/pkgutil.py delta PKG-ADMIN-001 --src _staging/PKG-ADMIN-001
    python3 scripts/pkgutil.py stage PKG-ADMIN-001 --src _staging/PKG-ADMIN-001
    python3 scripts/pkgutil.py compliance summary --json

Agent API:
    The 'compliance' command provides a queryable API for agents to understand
    packaging requirements. Use --json for machine-readable output.

    Example queries:
        compliance summary     - Complete compliance overview
        compliance gates       - Gate validations explained
        compliance troubleshoot --error G1  - Fix G1 errors
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.preflight import (
    PreflightValidator,
    PreflightResult,
    compute_sha256,
    load_file_ownership,
)
from lib.packages import pack, sha256_file


# === Constants ===
STAGING_DIR = CONTROL_PLANE / "_staging"
TEMPLATES_DIR = CONTROL_PLANE / "templates"


def ensure_staging_dir() -> Path:
    """Ensure staging directory exists."""
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    return STAGING_DIR


# =============================================================================
# Template Rendering (Simple - no Jinja2 dependency)
# =============================================================================

def render_template(template_path: Path, context: dict) -> str:
    """Render a template file with simple variable substitution.

    Supports:
    - {{ variable }} replacement
    - {{ variable | default('value') }} with defaults
    - {{ list | tojson }} for JSON arrays
    - {{ var | default([]) | tojson }} combined filters

    Note: This is a simple implementation. For complex templates,
    consider using Jinja2.
    """
    import re
    content = template_path.read_text()

    # Handle {{ var | default([]) | tojson }} combined patterns (must be first)
    # Matches: {{ capabilities | default([]) | tojson }}
    default_tojson_pattern = r'\{\{\s*(\w+)\s*\|\s*default\(\s*\[\s*\]\s*\)\s*\|\s*tojson\s*\}\}'
    for match in re.finditer(default_tojson_pattern, content):
        var_name = match.group(1)
        value = context.get(var_name, [])
        content = content.replace(match.group(0), json.dumps(value))

    # Handle {{ var | default('value') }} patterns
    default_pattern = r"\{\{\s*(\w+)\s*\|\s*default\(['\"]([^'\"]*)['\"]?\)\s*\}\}"
    for match in re.finditer(default_pattern, content):
        var_name = match.group(1)
        default_val = match.group(2)
        value = context.get(var_name, default_val)
        content = content.replace(match.group(0), str(value))

    # Handle {{ list | tojson }} patterns
    tojson_pattern = r'\{\{\s*(\w+)\s*\|\s*tojson\s*\}\}'
    for match in re.finditer(tojson_pattern, content):
        var_name = match.group(1)
        value = context.get(var_name, [])
        content = content.replace(match.group(0), json.dumps(value))

    # Handle simple {{ variable }} patterns
    simple_pattern = r'\{\{\s*(\w+)\s*\}\}'
    for match in re.finditer(simple_pattern, content):
        var_name = match.group(1)
        if var_name in context:
            content = content.replace(match.group(0), str(context[var_name]))

    return content


# =============================================================================
# init-agent Command
# =============================================================================

def cmd_init_agent(args: argparse.Namespace) -> int:
    """Generate agent package skeleton.

    Creates:
    - manifest.json
    - capabilities.yaml
    - prompts/system.md
    - prompts/turn.md
    - lib/agent_<name>.py
    - tests/test_agent_<name>.py
    """
    package_id = args.package_id
    framework_id = args.framework
    output_dir = Path(args.output) if args.output else STAGING_DIR / package_id

    # Validate framework exists
    from lib.registry import framework_exists
    if not framework_exists(framework_id):
        print(f"Warning: Framework '{framework_id}' not found in frameworks_registry", file=sys.stderr)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir = output_dir / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    lib_dir = output_dir / "lib"
    lib_dir.mkdir(exist_ok=True)
    tests_dir = output_dir / "tests"
    tests_dir.mkdir(exist_ok=True)

    # Template context
    agent_name_short = package_id.replace('PKG-', '').replace('-', '_').lower()
    target_id = package_id.lower().replace('pkg-', '')
    context = {
        "package_id": package_id,
        "framework_id": framework_id,
        "spec_id": args.spec or "",
        "plane_id": "ho1",
        "target_id": target_id,
        "agent_name": package_id.replace('PKG-', '').replace('-', ' ').title(),
        "capabilities": ["list_items", "describe_item", "explain"],
        "dependencies": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "author": os.getenv("USER", ""),
        "description": f"Agent package for {package_id}",
    }

    # Render templates
    template_dir = TEMPLATES_DIR / "agent"
    if template_dir.exists():
        # manifest.json
        manifest_tmpl = template_dir / "manifest.json.j2"
        if manifest_tmpl.exists():
            manifest_content = render_template(manifest_tmpl, context)
            (output_dir / "manifest.json").write_text(manifest_content)
        else:
            _write_default_agent_manifest(output_dir / "manifest.json", context)

        # capabilities.yaml
        cap_tmpl = template_dir / "capabilities.yaml.j2"
        if cap_tmpl.exists():
            cap_content = render_template(cap_tmpl, context)
            (output_dir / "capabilities.yaml").write_text(cap_content)

        # prompts
        for prompt_file in ["system.md", "turn.md"]:
            prompt_tmpl = template_dir / "prompts" / prompt_file
            if prompt_tmpl.exists():
                prompt_content = render_template(prompt_tmpl, context)
                (prompts_dir / prompt_file).write_text(prompt_content)
    else:
        _write_default_agent_manifest(output_dir / "manifest.json", context)

    # Generate agent module
    agent_module = f'''#!/usr/bin/env python3
"""
{package_id}: Agent implementation.

Capabilities:
- list_items: List items in the system
- describe_item: Describe a specific item
- explain: Explain system behavior
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional


@dataclass
class {agent_name_short.title().replace("_", "")}Agent:
    """Agent implementation for {package_id}."""
    plane_root: Path

    def list_items(self, **kwargs) -> Dict[str, Any]:
        """List items in the system."""
        # TODO: Implement
        return {{"items": [], "evidence": None}}

    def describe_item(self, item_id: str, **kwargs) -> Dict[str, Any]:
        """Describe a specific item."""
        # TODO: Implement
        return {{"item": None, "evidence": None}}

    def explain(self, topic: str, **kwargs) -> Dict[str, Any]:
        """Explain system behavior."""
        # TODO: Implement
        return {{"explanation": "", "evidence": None}}
'''
    (lib_dir / f"agent_{agent_name_short}.py").write_text(agent_module)

    # Generate test file
    test_module = f'''#!/usr/bin/env python3
"""Tests for {package_id} agent."""
import pytest
from pathlib import Path

# Import will work after package install
# from lib.agent_{agent_name_short} import {agent_name_short.title().replace("_", "")}Agent


class TestAgent:
    """Test {package_id} agent capabilities."""

    def test_list_items(self):
        """Test list_items capability."""
        # TODO: Implement
        pass

    def test_describe_item(self):
        """Test describe_item capability."""
        # TODO: Implement
        pass

    def test_explain(self):
        """Test explain capability."""
        # TODO: Implement
        pass
'''
    (tests_dir / f"test_agent_{agent_name_short}.py").write_text(test_module)

    # Create README
    readme = f'''# {package_id}

Agent package generated by pkgutil.

## Capabilities

- **list_items**: List items in the system
- **describe_item**: Describe a specific item
- **explain**: Explain system behavior

## Framework

{framework_id}

## Installation

```bash
# Validate
python3 scripts/pkgutil.py preflight {package_id} --src {output_dir}

# Stage
python3 scripts/pkgutil.py stage {package_id} --src {output_dir}

# Install
python3 scripts/package_install.py --archive _staging/{package_id}.tar.gz --id {package_id}
```
'''
    (output_dir / "README.md").write_text(readme)

    print(f"Created agent skeleton at: {output_dir}")
    print(f"  - manifest.json")
    print(f"  - capabilities.yaml")
    print(f"  - prompts/system.md")
    print(f"  - prompts/turn.md")
    print(f"  - lib/agent_{agent_name_short}.py")
    print(f"  - tests/test_agent_{agent_name_short}.py")
    print(f"  - README.md")
    print()
    print("Next steps:")
    print(f"  1. Edit files in {output_dir}")
    print(f"  2. Run: python3 scripts/pkgutil.py preflight {package_id} --src {output_dir}")

    return 0


def _write_default_agent_manifest(path: Path, context: dict):
    """Write default agent manifest without templates."""
    manifest = {
        "package_id": context["package_id"],
        "package_type": "agent",
        "version": "0.1.0",
        "schema_version": "1.2",
        "framework_id": context["framework_id"],
        "spec_id": context.get("spec_id", ""),
        "plane_id": "ho1",
        "assets": [],
        "capabilities": context.get("capabilities", []),
        "dependencies": [],
        "metadata": {
            "created_at": context["timestamp"],
            "author": context.get("author", ""),
            "description": context.get("description", ""),
        }
    }
    path.write_text(json.dumps(manifest, indent=2))


# =============================================================================
# init Command (Standard Package)
# =============================================================================

def cmd_init(args: argparse.Namespace) -> int:
    """Generate standard package skeleton."""
    package_id = args.package_id
    spec_id = args.spec
    output_dir = Path(args.output) if args.output else STAGING_DIR / package_id

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    lib_dir = output_dir / "lib"
    lib_dir.mkdir(exist_ok=True)
    tests_dir = output_dir / "tests"
    tests_dir.mkdir(exist_ok=True)

    # Template context
    module_name = package_id.replace('PKG-', '').replace('-', '_').lower()
    target_id = package_id.lower().replace('pkg-', '')
    context = {
        "package_id": package_id,
        "spec_id": spec_id or "",
        "plane_id": "ho3",
        "namespace": "lib",
        "target_id": target_id,
        "dependencies": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "author": os.getenv("USER", ""),
        "description": f"Package for {package_id}",
    }

    # Render manifest template
    template_dir = TEMPLATES_DIR / "standard"
    manifest_tmpl = template_dir / "manifest.json.j2"
    if manifest_tmpl.exists():
        manifest_content = render_template(manifest_tmpl, context)
        (output_dir / "manifest.json").write_text(manifest_content)
    else:
        manifest = {
            "package_id": package_id,
            "package_type": "standard",
            "version": "0.1.0",
            "schema_version": "1.2",
            "spec_id": spec_id or "",
            "plane_id": "ho3",
            "assets": [],
            "dependencies": [],
            "metadata": {
                "created_at": context["timestamp"],
                "author": context.get("author", ""),
                "description": context.get("description", ""),
            }
        }
        (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # Generate module
    module_content = f'''#!/usr/bin/env python3
"""
{package_id}: Module implementation.
"""
from pathlib import Path
from typing import Dict, Any


def main() -> Dict[str, Any]:
    """Main entry point."""
    # TODO: Implement
    return {{"status": "ok"}}


if __name__ == "__main__":
    print(main())
'''
    (lib_dir / f"{module_name}.py").write_text(module_content)

    # Generate test file
    test_content = f'''#!/usr/bin/env python3
"""Tests for {package_id}."""
import pytest


class TestModule:
    """Test {package_id} module."""

    def test_main(self):
        """Test main function."""
        # TODO: Implement
        pass
'''
    (tests_dir / f"test_{module_name}.py").write_text(test_content)

    print(f"Created package skeleton at: {output_dir}")
    print(f"  - manifest.json")
    print(f"  - lib/{module_name}.py")
    print(f"  - tests/test_{module_name}.py")

    return 0


# =============================================================================
# preflight Command
# =============================================================================

def cmd_preflight(args: argparse.Namespace) -> int:
    """Run preflight validation without install.

    Validates:
    - G0A: Package declaration consistency
    - G1: Dependency chain
    - OWN: Ownership conflicts
    - G5: Signature policy
    """
    package_id = args.package_id
    src_path = Path(args.src).resolve()
    plane = args.plane or "ho3"
    output_json = args.json

    if not src_path.exists():
        print(f"Error: Source path not found: {src_path}", file=sys.stderr)
        return 1

    # Load manifest
    manifest_path = src_path / "manifest.json"
    if not manifest_path.exists():
        print(f"Error: manifest.json not found in {src_path}", file=sys.stderr)
        return 1

    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        print(f"Error: Invalid manifest.json: {e}", file=sys.stderr)
        return 1

    # Build workspace files dict
    from lib.paths import discover_workspace_files, PACKAGE_META_FILES
    workspace_files = discover_workspace_files(src_path, exclude_names=PACKAGE_META_FILES)

    # Get environment settings
    allow_unsigned = os.getenv("CONTROL_PLANE_ALLOW_UNSIGNED", "0") == "1"

    # Run preflight
    strict = not getattr(args, 'no_strict', False)
    validator = PreflightValidator(CONTROL_PLANE, strict=strict)
    results = validator.run_all(
        manifest=manifest,
        workspace_files=workspace_files,
        package_id=package_id,
        allow_unsigned=allow_unsigned,
    )

    # Output results
    if output_json:
        print(validator.to_json(results, package_id))
    else:
        print(validator.format_results(results, package_id))

    # Return exit code
    all_passed = all(r.passed for r in results)
    return 0 if all_passed else 1


def _compute_asset_hashes(workspace_files: Dict[str, Path]) -> Dict[str, str]:
    """Compute SHA256 hashes for all workspace files."""
    return {path: compute_sha256(fp) for path, fp in sorted(workspace_files.items())}


def _update_manifest_assets(
    manifest: dict,
    workspace_files: Dict[str, Path],
    src_path: Path
) -> dict:
    """Update manifest assets with actual file hashes."""
    hashes = _compute_asset_hashes(workspace_files)
    assets = []
    for rel_path in sorted(workspace_files):
        sha = hashes[rel_path]
        # Determine classification from path
        classification = _classify_file(rel_path)
        assets.append({
            "path": rel_path,
            "sha256": sha,
            "classification": classification,
        })

    manifest["assets"] = assets
    return manifest


def _classify_file(path: str) -> str:
    """Classify file based on path."""
    if path.startswith("lib/"):
        return "library"
    elif path.startswith("scripts/"):
        return "script"
    elif path.startswith("tests/"):
        return "test"
    elif path.startswith("prompts/"):
        return "prompt"
    elif path.startswith("schemas/"):
        return "schema"
    elif path.startswith("config/"):
        return "config"
    elif path.endswith(".md"):
        return "documentation"
    elif path.endswith(".yaml") or path.endswith(".yml"):
        return "config"
    else:
        return "other"


def _sync_manifest_hashes(
    manifest: dict,
    workspace_files: Dict[str, Path],
    src_path: Path,
) -> dict:
    """Update hashes for declared assets. Warn about undeclared files.

    Unlike _update_manifest_assets(), this preserves the user's asset list
    and classifications — it only refreshes sha256 hashes for assets already
    declared in the manifest, and warns about discrepancies.
    """
    assets = manifest.get("assets", [])
    declared_paths = {a["path"] for a in assets}

    # Pre-compute hashes for all workspace files
    hashes = _compute_asset_hashes(workspace_files)

    # Update hashes for declared assets
    for asset in assets:
        path = asset["path"]
        if path in hashes:
            asset["sha256"] = hashes[path]
        else:
            print(f"  Warning: declared asset '{path}' not found on disk", file=sys.stderr)

    # Warn about undeclared files
    for rel_path in sorted(workspace_files):
        if rel_path not in declared_paths:
            print(f"  Warning: '{rel_path}' on disk but not in manifest (skipped)", file=sys.stderr)

    return manifest


# =============================================================================
# delta Command
# =============================================================================

def cmd_delta(args: argparse.Namespace) -> int:
    """Generate reviewable registry delta.

    Produces CSV rows showing what would be added to:
    - file_ownership.csv
    - packages_registry.csv (if applicable)
    """
    package_id = args.package_id
    src_path = Path(args.src).resolve()
    output_file = Path(args.output) if args.output else None

    if not src_path.exists():
        print(f"Error: Source path not found: {src_path}", file=sys.stderr)
        return 1

    # Load manifest
    manifest_path = src_path / "manifest.json"
    if not manifest_path.exists():
        print(f"Error: manifest.json not found in {src_path}", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text())

    # Build workspace files
    from lib.paths import discover_workspace_files, PACKAGE_META_FILES
    workspace_files = discover_workspace_files(
        src_path,
        exclude_names=PACKAGE_META_FILES | {"README.md"},
    )

    # Generate delta
    lines = []
    lines.append(f"# Registry delta for {package_id}")
    lines.append(f"# Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")

    # File ownership additions
    lines.append("# file_ownership.csv additions:")
    lines.append("file_path,owner_package_id,sha256,classification")
    for rel_path, file_path in sorted(workspace_files.items()):
        sha = compute_sha256(file_path)
        classification = _classify_file(rel_path)
        lines.append(f"{rel_path},{package_id},{sha},{classification}")

    lines.append("")

    # Packages registry addition
    lines.append("# packages_registry.csv additions:")
    lines.append("id,source,source_type,digest,status")
    archive_name = f"_staging/{package_id}.tar.gz"
    lines.append(f"{package_id},{archive_name},tar,<computed_after_pack>,staged")

    delta_content = "\n".join(lines)

    if output_file:
        output_file.write_text(delta_content)
        print(f"Delta written to: {output_file}")
    else:
        print(delta_content)

    return 0


# =============================================================================
# stage Command
# =============================================================================

def cmd_stage(args: argparse.Namespace) -> int:
    """Stage package for later install.

    1. Run preflight (must pass)
    2. Build tar.gz archive
    3. Copy to _staging/<PKG-ID>.tar.gz
    4. Write delta file to _staging/<PKG-ID>.delta.csv
    """
    package_id = args.package_id
    src_path = Path(args.src).resolve()
    staging_dir = Path(args.staging_dir) if args.staging_dir else STAGING_DIR

    if not src_path.exists():
        print(f"Error: Source path not found: {src_path}", file=sys.stderr)
        return 1

    # Load manifest
    manifest_path = src_path / "manifest.json"
    if not manifest_path.exists():
        print(f"Error: manifest.json not found in {src_path}", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text())

    # Build workspace files (include manifest.json in staging archive)
    from lib.paths import discover_workspace_files
    workspace_files = discover_workspace_files(
        src_path,
        exclude_names={"signature.json", "checksums.sha256"},
    )

    # Sync manifest hashes (preserves user classifications)
    non_meta_files = {k: v for k, v in workspace_files.items() if k != "manifest.json"}
    manifest = _sync_manifest_hashes(manifest, non_meta_files, src_path)

    # Write updated manifest back
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Run preflight
    print(f"[stage] Running preflight validation...", file=sys.stderr)
    allow_unsigned = os.getenv("CONTROL_PLANE_ALLOW_UNSIGNED", "0") == "1"
    strict = not getattr(args, 'no_strict', False)
    validator = PreflightValidator(CONTROL_PLANE, strict=strict)
    results = validator.run_all(
        manifest=manifest,
        workspace_files={k: v for k, v in workspace_files.items() if k != "manifest.json"},
        package_id=package_id,
        allow_unsigned=allow_unsigned,
    )

    all_passed = all(r.passed for r in results)
    if not all_passed:
        print(f"\n[stage] Preflight FAILED:", file=sys.stderr)
        print(validator.format_results(results, package_id), file=sys.stderr)
        return 1

    print(f"[stage] Preflight PASSED", file=sys.stderr)

    # Ensure staging directory exists
    staging_dir.mkdir(parents=True, exist_ok=True)

    # Build archive
    archive_path = staging_dir / f"{package_id}.tar.gz"
    print(f"[stage] Building archive: {archive_path}", file=sys.stderr)

    # Create archive with package_id as root directory
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_dir = Path(tmpdir) / package_id
        shutil.copytree(src_path, pkg_dir)

        # Pack
        digest = pack(pkg_dir, archive_path)
        print(f"[stage] Archive SHA256: {digest}", file=sys.stderr)

    # Write digest file
    # Note: archive_path.with_suffix() would replace only .gz, not .tar.gz
    digest_path = staging_dir / f"{package_id}.tar.gz.sha256"
    digest_path.write_text(f"{digest}  {archive_path.name}\n")

    # Write delta file
    delta_path = staging_dir / f"{package_id}.delta.csv"
    with open(delta_path, 'w', encoding='utf-8') as f:
        f.write(f"# Registry delta for {package_id}\n")
        f.write(f"# Generated: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"# Archive: {archive_path.name}\n")
        f.write(f"# Digest: {digest}\n")
        f.write("\n")
        f.write("file_path,owner_package_id,sha256,classification\n")
        for asset in manifest.get("assets", []):
            path = asset["path"]
            sha = asset["sha256"]
            cls = asset.get("classification", "other")
            f.write(f"{path},{package_id},{sha},{cls}\n")

    print(f"\n[stage] Package staged successfully!", file=sys.stderr)
    print(f"  Archive: {archive_path}", file=sys.stderr)
    print(f"  Digest:  {digest_path}", file=sys.stderr)
    print(f"  Delta:   {delta_path}", file=sys.stderr)
    print(f"\nTo install:", file=sys.stderr)
    print(f"  python3 scripts/package_install.py --archive {archive_path} --id {package_id}", file=sys.stderr)

    return 0


# =============================================================================
# check-framework Command (Phase 1B)
# =============================================================================

def cmd_check_framework(args: argparse.Namespace) -> int:
    """Validate framework governance readiness.

    Checks:
    - Spec completeness (required docs exist)
    - Registry coherence (frameworks + specs registries consistent)
    - Gate compatibility (no contradictions)
    - Tier safety (no PRISTINE write requirements at runtime)
    - Dependency closure (all refs exist)

    If --old is provided, also checks for breaking changes.
    """
    framework_id = args.framework_id
    src_path = Path(args.src).resolve() if args.src else CONTROL_PLANE / "frameworks"
    old_path = Path(args.old).resolve() if args.old else None

    errors = []
    warnings = []

    # 1. Check framework file exists
    framework_file = None
    for pattern in [f"{framework_id}.md", f"{framework_id}_*.md"]:
        matches = list(src_path.glob(pattern))
        if matches:
            framework_file = matches[0]
            break

    if not framework_file:
        errors.append(f"FRAMEWORK_FILE_MISSING: {framework_id} not found in {src_path}")
        _print_check_results(framework_id, errors, warnings, args.json)
        return 1

    # 2. Check framework is in registry
    from lib.registry import framework_exists as _fw_exists, load_registry_as_dict
    if not _fw_exists(framework_id):
        errors.append(f"REGISTRY_MISSING: {framework_id} not in frameworks_registry.csv")

    # 3. Check specs that reference this framework
    specs_reg = CONTROL_PLANE / "registries" / "specs_registry.csv"
    specs_dict = load_registry_as_dict(specs_reg, "spec_id")
    dependent_specs = [
        sid for sid, row in specs_dict.items()
        if row.get("framework_id") == framework_id
    ]

    # 4. Check spec manifest files exist for dependent specs
    specs_dir = CONTROL_PLANE / "specs"
    for spec_id in dependent_specs:
        spec_manifest = specs_dir / spec_id / "manifest.yaml"
        if not spec_manifest.exists():
            warnings.append(f"SPEC_MANIFEST_MISSING: {spec_id}/manifest.yaml not found")

    # 5. Check for breaking changes if old version provided
    if old_path and old_path.exists():
        breaking = _check_breaking_changes(old_path, framework_file)
        for change in breaking:
            errors.append(f"BREAKING_CHANGE: {change}")

    # Print results
    _print_check_results(framework_id, errors, warnings, args.json)

    return 1 if errors else 0


def _check_breaking_changes(old_path: Path, new_path: Path) -> List[str]:
    """Compare framework files for breaking changes.

    Breaking changes include:
    - Removed invariants
    - Removed path authorizations
    - Added required gates
    """
    breaking = []

    old_content = old_path.read_text()
    new_content = new_path.read_text()

    # Simple heuristic: look for MUST/MUST NOT lines
    old_musts = set(line.strip() for line in old_content.split('\n')
                    if 'MUST' in line and line.strip().startswith('-'))
    new_musts = set(line.strip() for line in new_content.split('\n')
                    if 'MUST' in line and line.strip().startswith('-'))

    removed_musts = old_musts - new_musts
    for must in removed_musts:
        breaking.append(f"Removed invariant: {must[:60]}...")

    return breaking


def _print_check_results(framework_id: str, errors: List[str], warnings: List[str], as_json: bool):
    """Print check-framework results."""
    if as_json:
        result = {
            "framework_id": framework_id,
            "passed": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }
        print(json.dumps(result, indent=2))
    else:
        print(f"CHECK-FRAMEWORK: {framework_id}")
        print("─" * 40)

        if errors:
            print(f"\nErrors ({len(errors)}):")
            for error in errors:
                print(f"  ✗ {error}")

        if warnings:
            print(f"\nWarnings ({len(warnings)}):")
            for warning in warnings:
                print(f"  ! {warning}")

        print()
        if errors:
            print("RESULT: FAIL")
        else:
            print("RESULT: PASS")


# =============================================================================
# register-framework Command
# =============================================================================

def cmd_register_framework(args: argparse.Namespace) -> int:
    """Register a framework in frameworks_registry.csv.

    Validates:
    1. Framework file exists
    2. Framework ID matches filename pattern
    3. Framework not already registered
    4. Framework file has required sections

    Then adds to registries/frameworks_registry.csv.
    """
    framework_id = args.framework_id
    src_path = Path(args.src) if args.src else CONTROL_PLANE / "frameworks"

    # Find framework file
    if src_path.is_file():
        framework_file = src_path
    else:
        framework_file = src_path / f"{framework_id}_*.md"
        matches = list(src_path.glob(f"{framework_id}_*.md"))
        if not matches:
            matches = list(src_path.glob(f"{framework_id}.md"))
        if not matches:
            print(f"Error: Framework file not found for {framework_id} in {src_path}", file=sys.stderr)
            return 1
        framework_file = matches[0]

    if not framework_file.exists():
        print(f"Error: Framework file not found: {framework_file}", file=sys.stderr)
        return 1

    # Validate framework ID format
    if not framework_id.startswith("FMWK-"):
        print(f"Error: Framework ID must start with 'FMWK-': {framework_id}", file=sys.stderr)
        return 1

    # Check if already registered
    from lib.registry import framework_exists as _fw_exists
    registry_path = CONTROL_PLANE / "registries" / "frameworks_registry.csv"
    if _fw_exists(framework_id):
        print(f"Error: Framework '{framework_id}' already registered", file=sys.stderr)
        return 1

    # Parse framework file for metadata
    content = framework_file.read_text()
    title = _extract_framework_title(content, framework_id)
    version = _extract_metadata(content, 'version') or "1.0.0"
    status = _extract_metadata(content, 'status') or "active"
    plane_id = _extract_metadata(content, 'plane') or "ho3"

    # Validate required sections
    errors = []
    if '## Invariants' not in content and '## invariants' not in content.lower():
        errors.append("Missing '## Invariants' section")
    if 'MUST' not in content:
        errors.append("No MUST requirements found")

    if errors and not args.force:
        print(f"Error: Framework validation failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(f"\nUse --force to register anyway", file=sys.stderr)
        return 1

    # Add to registry
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_row = {
        'framework_id': framework_id,
        'title': title,
        'status': status,
        'version': version,
        'plane_id': plane_id,
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

    if args.json:
        print(json.dumps({
            "action": "register-framework",
            "framework_id": framework_id,
            "source": str(framework_file),
            "registry": str(registry_path),
            "success": True,
        }, indent=2))
    else:
        print(f"Registered framework: {framework_id}")
        print(f"  Title: {title}")
        print(f"  Version: {version}")
        print(f"  Source: {framework_file}")
        print(f"  Registry: {registry_path}")

    return 0


def _extract_framework_title(content: str, framework_id: str) -> str:
    """Extract title from framework markdown."""
    lines = content.split('\n')
    for line in lines:
        if line.startswith('# '):
            # Extract title, removing framework ID prefix if present
            title = line[2:].strip()
            if ':' in title:
                title = title.split(':', 1)[1].strip()
            return title
    return framework_id


def _extract_metadata(content: str, key: str) -> Optional[str]:
    """Extract metadata value from markdown content."""
    import re
    # Look for patterns like "- version: 1.0.0" or "version: 1.0.0"
    pattern = rf'[-*]?\s*{key}\s*:\s*([^\n]+)'
    match = re.search(pattern, content, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


# =============================================================================
# register-spec Command
# =============================================================================

def cmd_register_spec(args: argparse.Namespace) -> int:
    """Register a spec in specs_registry.csv.

    Validates:
    1. Spec directory exists with manifest.yaml
    2. Spec ID matches directory name
    3. Spec not already registered
    4. Referenced framework_id exists in frameworks_registry
    5. Spec has required fields (assets, interfaces)

    Then adds to registries/specs_registry.csv.
    """
    spec_id = args.spec_id
    src_path = Path(args.src) if args.src else CONTROL_PLANE / "specs" / spec_id

    # Find spec directory
    if src_path.is_file():
        print(f"Error: --src must be a directory, not a file: {src_path}", file=sys.stderr)
        return 1

    if not src_path.exists():
        # Try specs/<spec_id>
        alt_path = CONTROL_PLANE / "specs" / spec_id
        if alt_path.exists():
            src_path = alt_path
        else:
            print(f"Error: Spec directory not found: {src_path}", file=sys.stderr)
            return 1

    # Check for manifest.yaml
    manifest_path = src_path / "manifest.yaml"
    if not manifest_path.exists():
        print(f"Error: manifest.yaml not found in {src_path}", file=sys.stderr)
        return 1

    # Validate spec ID format
    if not spec_id.startswith("SPEC-"):
        print(f"Error: Spec ID must start with 'SPEC-': {spec_id}", file=sys.stderr)
        return 1

    # Check if already registered
    from lib.registry import spec_exists as _sp_exists
    registry_path = CONTROL_PLANE / "registries" / "specs_registry.csv"
    if _sp_exists(spec_id):
        print(f"Error: Spec '{spec_id}' already registered", file=sys.stderr)
        return 1

    # Parse manifest.yaml
    try:
        import yaml
        manifest = yaml.safe_load(manifest_path.read_text())
    except ImportError:
        # Fallback: simple YAML parsing for basic fields
        manifest = _parse_simple_yaml(manifest_path.read_text())
    except Exception as e:
        print(f"Error: Failed to parse manifest.yaml: {e}", file=sys.stderr)
        return 1

    # Extract metadata
    manifest_spec_id = manifest.get('spec_id', '')
    if manifest_spec_id and manifest_spec_id != spec_id:
        print(f"Error: Spec ID mismatch - argument: {spec_id}, manifest: {manifest_spec_id}", file=sys.stderr)
        return 1

    title = manifest.get('title', spec_id)
    framework_id = manifest.get('framework_id', '')
    version = manifest.get('version', '1.0.0')
    status = manifest.get('status', 'draft')
    plane_id = manifest.get('plane_id', 'ho3')

    # Validate framework_id exists
    if not framework_id:
        print(f"Error: manifest.yaml missing required 'framework_id' field", file=sys.stderr)
        return 1

    from lib.registry import framework_exists as _fw_check
    if not _fw_check(framework_id):
        print(f"Error: Framework '{framework_id}' not found in frameworks_registry.csv", file=sys.stderr)
        print(f"  Register the framework first: pkgutil register-framework {framework_id}", file=sys.stderr)
        return 1

    # Validate required fields
    errors = []
    if not manifest.get('assets'):
        errors.append("Missing 'assets' field (list of owned files)")

    if errors and not args.force:
        print(f"Error: Spec validation failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(f"\nUse --force to register anyway", file=sys.stderr)
        return 1

    # Add to registry
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_row = {
        'spec_id': spec_id,
        'title': title,
        'framework_id': framework_id,
        'status': status,
        'version': version,
        'plane_id': plane_id,
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

    if args.json:
        print(json.dumps({
            "action": "register-spec",
            "spec_id": spec_id,
            "framework_id": framework_id,
            "source": str(src_path),
            "registry": str(registry_path),
            "success": True,
        }, indent=2))
    else:
        print(f"Registered spec: {spec_id}")
        print(f"  Title: {title}")
        print(f"  Framework: {framework_id}")
        print(f"  Version: {version}")
        print(f"  Assets: {len(manifest.get('assets', []))} files")
        print(f"  Source: {src_path}")
        print(f"  Registry: {registry_path}")

    return 0


def _parse_simple_yaml(content: str) -> dict:
    """Simple YAML parser for basic key: value pairs."""
    result = {}
    current_key = None
    current_list = None

    for line in content.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        # Check for list item
        if stripped.startswith('- ') and current_key:
            if current_list is None:
                current_list = []
                result[current_key] = current_list
            current_list.append(stripped[2:].strip())
            continue

        # Check for key: value
        if ':' in stripped:
            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if value:
                result[key] = value
                current_key = None
                current_list = None
            else:
                current_key = key
                current_list = None

    return result


# =============================================================================
# compliance Command - Queryable Package Compliance API
# =============================================================================

def cmd_compliance(args: argparse.Namespace) -> int:
    """Query package compliance requirements.

    Provides agents and developers with programmatic access to:
    - Governance chain requirements
    - Gate validations and what they check
    - Manifest field requirements
    - Packaging workflow steps
    - Available frameworks and specs
    - Troubleshooting guidance
    """
    from lib.agent_helpers import CPInspector

    inspector = CPInspector(CONTROL_PLANE)
    query = args.query

    # Map query types to inspector methods
    if query == "summary":
        result, evidence = inspector.get_compliance_summary()
    elif query == "chain":
        result, evidence = inspector.get_governance_chain()
    elif query == "gates":
        result, evidence = inspector.get_gate_requirements()
    elif query == "manifest":
        result, evidence = inspector.get_manifest_requirements()
    elif query == "workflow":
        result, evidence = inspector.get_packaging_workflow()
    elif query == "frameworks":
        result, evidence = inspector.list_available_frameworks()
    elif query == "specs":
        framework_filter = getattr(args, 'framework', None)
        result, evidence = inspector.list_available_specs(framework_filter)
    elif query == "troubleshoot":
        error_filter = getattr(args, 'error', None)
        result, evidence = inspector.get_troubleshooting_guide(error_filter)
    elif query == "example":
        pkg_type = getattr(args, 'type', 'library')
        result, evidence = inspector.get_example_manifest(pkg_type)
    else:
        print(f"Unknown query type: {query}", file=sys.stderr)
        print("Available queries: summary, chain, gates, manifest, workflow, frameworks, specs, troubleshoot, example", file=sys.stderr)
        return 1

    # Output
    if args.json:
        output = {
            "query": query,
            "result": result if isinstance(result, (dict, list)) else [r.to_dict() if hasattr(r, 'to_dict') else r for r in result],
            "evidence": evidence.to_dict(),
        }
        print(json.dumps(output, indent=2))
    else:
        _print_compliance_result(query, result, evidence)

    return 0


def _print_compliance_result(query: str, result: Any, evidence) -> None:
    """Pretty-print compliance query result."""
    print(f"COMPLIANCE QUERY: {query}")
    print("═" * 60)

    if query == "summary":
        print("\n📋 GOVERNANCE CHAIN:")
        for item in result.get("governance_chain", {}).get("chain", []):
            id_pattern = item.get('id_pattern', item.get('declaration', ''))
            print(f"  Level {item['level']}: {item['name']} ({id_pattern})")

        print("\n🚦 GATES:")
        for gate_id, gate in result.get("gates", {}).items():
            status = "✓" if gate.get("phase") == "preflight" else "⚡"
            print(f"  {status} {gate_id}: {gate['description']}")

        print("\n📦 QUICK REFERENCE:")
        for cmd, usage in result.get("quick_reference", {}).items():
            print(f"  {cmd}: {usage}")

        print(f"\n🔧 Available Frameworks: {len(result.get('available_frameworks', []))}")
        print(f"📑 Available Specs: {len(result.get('available_specs', []))}")

    elif query == "chain":
        print(f"\n{result.get('overview', '')}\n")
        for item in result.get("chain", []):
            indent = "  " * (item["level"] - 1)
            print(f"{indent}↓ {item['name']} ({item['id_pattern']})")
            print(f"{indent}  {item['description']}")
        print(f"\n⚠️  {result.get('failure_consequence', '')}")

    elif query == "gates":
        for gate_id, gate in result.get("gates", {}).items():
            print(f"\n{gate_id} [{gate.get('phase', 'unknown')}]")
            print(f"  {gate['description']}")
            print("  Checks:")
            for check in gate.get("checks", []):
                print(f"    • {check}")
            if gate.get("common_failures"):
                print("  Common failures:")
                for fail in gate.get("common_failures", [])[:2]:
                    print(f"    ✗ {fail}")

    elif query == "manifest":
        print("\n📝 REQUIRED FIELDS:")
        for field, info in result.get("required_fields", {}).items():
            print(f"  {field}: {info.get('format', '')} (e.g., {info.get('example', '')})")
            if info.get("note"):
                print(f"    ⚠️  {info['note']}")

        print("\n📎 ASSET CLASSIFICATIONS:")
        for cls, info in result.get("asset_classifications", {}).items():
            print(f"  {cls}: {info.get('use_for', '')} [{info.get('pattern', '')}]")

    elif query == "workflow":
        print("\n📋 PACKAGING WORKFLOW:\n")
        for step in result.get("steps", []):
            print(f"Step {step['step']}: {step['name']}")
            if step.get("command"):
                print(f"  $ {step['command']}")
            if step.get("result"):
                print(f"  → {step['result']}")
            if step.get("skip_if"):
                print(f"  (Skip if: {step['skip_if']})")
            print()

    elif query == "frameworks":
        print("\n📚 AVAILABLE FRAMEWORKS:\n")
        for fw in result:
            print(f"  {fw['framework_id']}: {fw['title']} [{fw['status']}]")

    elif query == "specs":
        print("\n📑 AVAILABLE SPECS:\n")
        for spec in result:
            print(f"  {spec['spec_id']}: {spec['title']}")
            print(f"    Framework: {spec['framework_id']} | Status: {spec['status']}")

    elif query == "troubleshoot":
        print("\n🔧 TROUBLESHOOTING GUIDE:\n")
        for key, item in result.get("troubleshooting", {}).items():
            print(f"  {item.get('symptom', key)}")
            print(f"  Cause: {item.get('cause', 'Unknown')}")
            print(f"  Fix:")
            for fix in item.get("fix", []):
                print(f"    • {fix}")
            print()

    elif query == "example":
        print("\n📄 EXAMPLE MANIFEST:\n")
        print(json.dumps(result.get("example", {}), indent=2))
        if result.get("note"):
            print(f"\n⚠️  {result['note']}")

    print(f"\n─────────────────────────────────────────────────────────────")
    print(f"Evidence: {evidence.source}:{evidence.path}")
    if evidence.hash:
        print(f"Hash: {evidence.hash[:50]}...")


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Package authoring utilities for Control Plane v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
    init-agent         Generate agent package skeleton
    init               Generate standard package skeleton
    preflight          Run install-equivalent validation (no install)
    delta              Generate reviewable registry rows
    stage              Stage package for later install
    check-framework    Validate framework governance readiness
    register-framework Register a framework in frameworks_registry.csv
    register-spec      Register a spec in specs_registry.csv
    compliance         Query package compliance requirements (for agents)

Workflow (in order):
    1. register-framework  - Register framework first
    2. register-spec       - Register spec (must reference existing framework)
    3. init/init-agent     - Create package skeleton
    4. preflight           - Validate package (must reference registered spec)
    5. stage               - Stage for install

Compliance Queries (for agents):
    compliance summary     - Full compliance requirements overview
    compliance chain       - Governance chain (Framework→Spec→Package→Files)
    compliance gates       - Gate validations and what they check
    compliance manifest    - Required manifest.json fields
    compliance workflow    - Step-by-step packaging workflow
    compliance frameworks  - List available frameworks
    compliance specs       - List available specs
    compliance troubleshoot - Troubleshooting guidance
    compliance example     - Example manifest.json

Examples:
    # Register a new framework
    python3 scripts/pkgutil.py register-framework FMWK-200 --src frameworks/FMWK-200_ledger.md

    # Register a new spec (framework must exist first)
    python3 scripts/pkgutil.py register-spec SPEC-LEDGER-001 --src specs/SPEC-LEDGER-001

    # Create an agent package skeleton
    python3 scripts/pkgutil.py init-agent PKG-ADMIN-001 --framework FMWK-100

    # Validate a package before install
    python3 scripts/pkgutil.py preflight PKG-ADMIN-001 --src _staging/PKG-ADMIN-001

    # Stage a package for install
    python3 scripts/pkgutil.py stage PKG-ADMIN-001 --src _staging/PKG-ADMIN-001

    # Query compliance requirements (for agents)
    python3 scripts/pkgutil.py compliance summary --json
    python3 scripts/pkgutil.py compliance gates
    python3 scripts/pkgutil.py compliance troubleshoot --error G1
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # init-agent command
    init_agent_parser = subparsers.add_parser("init-agent", help="Generate agent package skeleton")
    init_agent_parser.add_argument("package_id", help="Package ID (e.g., PKG-ADMIN-001)")
    init_agent_parser.add_argument("--framework", required=True, help="Framework ID (e.g., FMWK-100)")
    init_agent_parser.add_argument("--spec", help="Spec ID (optional)")
    init_agent_parser.add_argument("--output", "-o", help="Output directory (default: _staging/<PKG-ID>)")

    # init command
    init_parser = subparsers.add_parser("init", help="Generate standard package skeleton")
    init_parser.add_argument("package_id", help="Package ID (e.g., PKG-LIB-001)")
    init_parser.add_argument("--spec", help="Spec ID (optional)")
    init_parser.add_argument("--output", "-o", help="Output directory (default: _staging/<PKG-ID>)")

    # preflight command
    preflight_parser = subparsers.add_parser("preflight", help="Run install validation without install")
    preflight_parser.add_argument("package_id", help="Package ID")
    preflight_parser.add_argument("--src", required=True, help="Source directory containing package files")
    preflight_parser.add_argument("--plane", choices=["ho1", "ho2", "ho3"], help="Target plane")
    preflight_parser.add_argument("--json", action="store_true", help="Output as JSON")
    preflight_parser.add_argument("--no-strict", action="store_true", help="Skip spec_id requirement (testing only)")

    # delta command
    delta_parser = subparsers.add_parser("delta", help="Generate reviewable registry rows")
    delta_parser.add_argument("package_id", help="Package ID")
    delta_parser.add_argument("--src", required=True, help="Source directory")
    delta_parser.add_argument("--output", "-o", help="Output file (default: stdout)")

    # stage command
    stage_parser = subparsers.add_parser("stage", help="Stage package for later install")
    stage_parser.add_argument("package_id", help="Package ID")
    stage_parser.add_argument("--src", required=True, help="Source directory")
    stage_parser.add_argument("--staging-dir", help="Staging directory (default: _staging)")
    stage_parser.add_argument("--no-strict", action="store_true", help="Skip spec_id requirement (testing only)")

    # check-framework command
    check_fw_parser = subparsers.add_parser("check-framework", help="Validate framework governance")
    check_fw_parser.add_argument("framework_id", help="Framework ID (e.g., FMWK-100)")
    check_fw_parser.add_argument("--src", help="Source directory for framework files")
    check_fw_parser.add_argument("--old", help="Old framework file for breaking change detection")
    check_fw_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # register-framework command
    reg_fw_parser = subparsers.add_parser("register-framework", help="Register framework in registry")
    reg_fw_parser.add_argument("framework_id", help="Framework ID (e.g., FMWK-100)")
    reg_fw_parser.add_argument("--src", help="Source file or directory (default: frameworks/)")
    reg_fw_parser.add_argument("--force", action="store_true", help="Register even if validation warnings")
    reg_fw_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # register-spec command
    reg_spec_parser = subparsers.add_parser("register-spec", help="Register spec in registry")
    reg_spec_parser.add_argument("spec_id", help="Spec ID (e.g., SPEC-CORE-001)")
    reg_spec_parser.add_argument("--src", help="Source directory (default: specs/<SPEC-ID>)")
    reg_spec_parser.add_argument("--force", action="store_true", help="Register even if validation warnings")
    reg_spec_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # compliance command - Queryable compliance API for agents
    compliance_parser = subparsers.add_parser("compliance", help="Query package compliance requirements")
    compliance_parser.add_argument("query", nargs="?", default="summary",
        choices=["summary", "chain", "gates", "manifest", "workflow", "frameworks", "specs", "troubleshoot", "example"],
        help="Query type (default: summary)")
    compliance_parser.add_argument("--framework", help="Filter specs by framework ID")
    compliance_parser.add_argument("--error", help="Filter troubleshooting by error type (G1, G0A, OWN, etc.)")
    compliance_parser.add_argument("--type", default="library", choices=["library", "agent"],
        help="Package type for example manifest (default: library)")
    compliance_parser.add_argument("--json", action="store_true", help="Output as JSON (for agent consumption)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "init-agent": cmd_init_agent,
        "init": cmd_init,
        "preflight": cmd_preflight,
        "delta": cmd_delta,
        "stage": cmd_stage,
        "check-framework": cmd_check_framework,
        "register-framework": cmd_register_framework,
        "register-spec": cmd_register_spec,
        "compliance": cmd_compliance,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
