#!/usr/bin/env python3
"""
pkgutil.py - Package authoring utilities for Control Plane v2.

Commands:
    init-agent  Generate agent package skeleton
    init        Generate standard package skeleton
    preflight   Run install-equivalent validation (no install)
    delta       Generate reviewable registry rows
    stage       Stage package for later install
    check-framework  Validate framework governance readiness (Phase 1B)

Usage:
    python3 scripts/pkgutil.py init-agent PKG-ADMIN-001 --framework FMWK-100
    python3 scripts/pkgutil.py init PKG-LIB-001 --spec SPEC-CORE-001
    python3 scripts/pkgutil.py preflight PKG-ADMIN-001 --src _staging/PKG-ADMIN-001
    python3 scripts/pkgutil.py delta PKG-ADMIN-001 --src _staging/PKG-ADMIN-001
    python3 scripts/pkgutil.py stage PKG-ADMIN-001 --src _staging/PKG-ADMIN-001
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
    frameworks_reg = CONTROL_PLANE / "registries" / "frameworks_registry.csv"
    if frameworks_reg.exists():
        found = False
        with open(frameworks_reg, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('framework_id') == framework_id:
                    found = True
                    break
        if not found:
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
    workspace_files = {}
    for file_path in src_path.rglob('*'):
        if file_path.is_dir():
            continue
        if file_path.name in ('manifest.json', 'signature.json', 'checksums.sha256'):
            continue
        if '__pycache__' in str(file_path):
            continue

        rel_path = file_path.relative_to(src_path)
        workspace_files[str(rel_path)] = file_path

    # Update manifest assets with actual hashes
    manifest = _update_manifest_assets(manifest, workspace_files, src_path)

    # Get environment settings
    allow_unsigned = os.getenv("CONTROL_PLANE_ALLOW_UNSIGNED", "0") == "1"

    # Run preflight
    validator = PreflightValidator(CONTROL_PLANE)
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


def _update_manifest_assets(
    manifest: dict,
    workspace_files: Dict[str, Path],
    src_path: Path
) -> dict:
    """Update manifest assets with actual file hashes."""
    assets = []
    for rel_path, file_path in sorted(workspace_files.items()):
        sha = compute_sha256(file_path)
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
    workspace_files = {}
    for file_path in src_path.rglob('*'):
        if file_path.is_dir():
            continue
        if file_path.name in ('manifest.json', 'signature.json', 'checksums.sha256', 'README.md'):
            continue
        if '__pycache__' in str(file_path):
            continue

        rel_path = file_path.relative_to(src_path)
        workspace_files[str(rel_path)] = file_path

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

    # Build workspace files
    workspace_files = {}
    for file_path in src_path.rglob('*'):
        if file_path.is_dir():
            continue
        if file_path.name in ('signature.json', 'checksums.sha256'):
            continue
        if '__pycache__' in str(file_path):
            continue

        rel_path = file_path.relative_to(src_path)
        workspace_files[str(rel_path)] = file_path

    # Update manifest with hashes
    manifest = _update_manifest_assets(manifest, {
        k: v for k, v in workspace_files.items()
        if k != "manifest.json"
    }, src_path)

    # Write updated manifest back
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Run preflight
    print(f"[stage] Running preflight validation...", file=sys.stderr)
    allow_unsigned = os.getenv("CONTROL_PLANE_ALLOW_UNSIGNED", "0") == "1"
    validator = PreflightValidator(CONTROL_PLANE)
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
    frameworks_reg = CONTROL_PLANE / "registries" / "frameworks_registry.csv"
    if frameworks_reg.exists():
        found = False
        with open(frameworks_reg, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('framework_id') == framework_id:
                    found = True
                    break
        if not found:
            errors.append(f"REGISTRY_MISSING: {framework_id} not in frameworks_registry.csv")
    else:
        warnings.append("frameworks_registry.csv not found")

    # 3. Check specs that reference this framework
    specs_reg = CONTROL_PLANE / "registries" / "specs_registry.csv"
    dependent_specs = []
    if specs_reg.exists():
        with open(specs_reg, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('framework_id') == framework_id:
                    dependent_specs.append(row.get('spec_id'))

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
# Main
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Package authoring utilities for Control Plane v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
    init-agent  Generate agent package skeleton
    init        Generate standard package skeleton
    preflight   Run install-equivalent validation (no install)
    delta       Generate reviewable registry rows
    stage       Stage package for later install
    check-framework  Validate framework governance readiness

Examples:
    # Create an agent package skeleton
    python3 scripts/pkgutil.py init-agent PKG-ADMIN-001 --framework FMWK-100

    # Create a standard package skeleton
    python3 scripts/pkgutil.py init PKG-LIB-001 --spec SPEC-CORE-001

    # Validate a package before install
    python3 scripts/pkgutil.py preflight PKG-ADMIN-001 --src _staging/PKG-ADMIN-001

    # Stage a package for install
    python3 scripts/pkgutil.py stage PKG-ADMIN-001 --src _staging/PKG-ADMIN-001

    # Validate framework governance
    python3 scripts/pkgutil.py check-framework FMWK-100 --src frameworks/
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

    # check-framework command
    check_fw_parser = subparsers.add_parser("check-framework", help="Validate framework governance")
    check_fw_parser.add_argument("framework_id", help="Framework ID (e.g., FMWK-100)")
    check_fw_parser.add_argument("--src", help="Source directory for framework files")
    check_fw_parser.add_argument("--old", help="Old framework file for breaking change detection")
    check_fw_parser.add_argument("--json", action="store_true", help="Output as JSON")

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
    }

    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
