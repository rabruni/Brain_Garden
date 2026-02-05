"""Package Handlers.

Handlers for package management operations including listing, inspecting,
preflight validation, install, uninstall, and staging.

Example:
    result = package_list({}, "list packages", session)
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from modules.chat_interface.registry import register
from modules.chat_interface.classifier import extract_package_id


def _find_package_archive(package_id: str, root: Path) -> Optional[Path]:
    """Find package archive in staging or packages_store."""
    # Check staging first
    staging = root / "_staging" / f"{package_id}.tar.gz"
    if staging.exists():
        return staging

    # Check packages_store
    store = root / "packages_store" / f"{package_id}.tar.gz"
    if store.exists():
        return store

    # Check packages_store subdirectory
    store_dir = root / "packages_store" / package_id
    if store_dir.is_dir():
        archive = store_dir / f"{package_id}.tar.gz"
        if archive.exists():
            return archive

    return None


@register(
    "package_list",
    description="List installed and available packages",
    category="packages",
    patterns=["list packages", "installed packages", "packages"],
)
def package_list(context: Dict[str, Any], query: str, session) -> str:
    """List all packages.

    Shows:
    - Installed packages (from installed/ directory)
    - Staged packages (from _staging/ directory)
    - Available packages (from packages_store/)

    Args:
        context: Query context
        query: Original query
        session: ChatSession instance

    Returns:
        Formatted package list
    """
    lines = ["# Packages", ""]

    # Installed packages
    installed_dir = session.root / "installed"
    installed = []
    if installed_dir.exists():
        for pkg_dir in sorted(installed_dir.iterdir()):
            if pkg_dir.is_dir() and pkg_dir.name.startswith("PKG-"):
                receipt = pkg_dir / "receipt.json"
                if receipt.exists():
                    try:
                        data = json.loads(receipt.read_text())
                        version = data.get("version", "?")
                        file_count = len(data.get("files", []))
                        installed.append((pkg_dir.name, version, file_count))
                    except Exception:
                        installed.append((pkg_dir.name, "?", 0))

    if installed:
        lines.append("## Installed")
        lines.append("")
        lines.append("| Package ID | Version | Files |")
        lines.append("|------------|---------|-------|")
        for pkg_id, version, files in installed:
            lines.append(f"| {pkg_id} | {version} | {files} |")
        lines.append("")

    # Staged packages
    staging_dir = session.root / "_staging"
    staged = []
    if staging_dir.exists():
        for f in sorted(staging_dir.glob("PKG-*.tar.gz")):
            pkg_id = f.name.replace(".tar.gz", "")
            staged.append(pkg_id)

    if staged:
        lines.append("## Staged (ready to install)")
        lines.append("")
        for pkg_id in staged:
            lines.append(f"- {pkg_id}")
        lines.append("")

    # Available packages
    store_dir = session.root / "packages_store"
    available = []
    if store_dir.exists():
        for item in sorted(store_dir.iterdir()):
            if item.is_dir() and item.name.startswith("PKG-"):
                manifest = item / "manifest.json"
                if manifest.exists():
                    try:
                        data = json.loads(manifest.read_text())
                        version = data.get("version", "?")
                        available.append((item.name, version))
                    except Exception:
                        available.append((item.name, "?"))

    if available:
        lines.append("## Available (in packages_store)")
        lines.append("")
        for pkg_id, version in available:
            lines.append(f"- {pkg_id} v{version}")
        lines.append("")

    if not installed and not staged and not available:
        lines.append("*No packages found*")

    # Summary
    lines.append("---")
    lines.append(f"**Total:** {len(installed)} installed, {len(staged)} staged, {len(available)} available")

    return "\n".join(lines)


@register(
    "package_inspect",
    description="Inspect a package's manifest and files",
    category="packages",
    patterns=["inspect PKG-X", "show PKG-X", "describe PKG-X"],
)
def package_inspect(context: Dict[str, Any], query: str, session) -> str:
    """Inspect a package.

    Shows manifest contents and file listing.

    Args:
        context: Query context (may have package_id)
        query: Original query
        session: ChatSession instance

    Returns:
        Package details
    """
    package_id = context.get("package_id") or extract_package_id(query)

    if not package_id:
        return (
            "Please specify a package ID.\n\n"
            "**Examples:**\n"
            "- `inspect PKG-KERNEL-001`\n"
            "- `show PKG-ADMIN-001`"
        )

    package_id = package_id.upper()
    lines = [f"# {package_id}", ""]

    # Check installed
    installed_dir = session.root / "installed" / package_id
    if installed_dir.exists():
        lines.append("**Status:** Installed")
        lines.append("")

        receipt = installed_dir / "receipt.json"
        if receipt.exists():
            try:
                data = json.loads(receipt.read_text())
                lines.append(f"**Version:** {data.get('version', '?')}")
                lines.append(f"**Installed:** {data.get('installed_at', '?')}")

                if data.get("framework_id"):
                    lines.append(f"**Framework:** {data['framework_id']}")
                if data.get("spec_id"):
                    lines.append(f"**Spec:** {data['spec_id']}")

                lines.append("")
                lines.append("## Files")
                lines.append("")
                for f in data.get("files", [])[:20]:
                    lines.append(f"- `{f.get('path', f)}`")
                if len(data.get("files", [])) > 20:
                    lines.append(f"- *... and {len(data['files']) - 20} more*")

            except Exception as e:
                lines.append(f"*Error reading receipt: {e}*")

        return "\n".join(lines)

    # Check packages_store
    store_dir = session.root / "packages_store" / package_id
    if store_dir.exists():
        lines.append("**Status:** Available (not installed)")
        lines.append("")

        manifest = store_dir / "manifest.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text())
                lines.append(f"**Version:** {data.get('version', '?')}")
                lines.append(f"**Type:** {data.get('package_type', '?')}")

                if data.get("framework_id"):
                    lines.append(f"**Framework:** {data['framework_id']}")
                if data.get("spec_id"):
                    lines.append(f"**Spec:** {data['spec_id']}")

                if data.get("description") or data.get("metadata", {}).get("description"):
                    desc = data.get("description") or data.get("metadata", {}).get("description")
                    lines.append("")
                    lines.append(f"**Description:** {desc}")

                lines.append("")
                lines.append("## Assets")
                lines.append("")
                for asset in data.get("assets", [])[:20]:
                    path = asset.get("path", asset) if isinstance(asset, dict) else asset
                    lines.append(f"- `{path}`")
                if len(data.get("assets", [])) > 20:
                    lines.append(f"- *... and {len(data['assets']) - 20} more*")

            except Exception as e:
                lines.append(f"*Error reading manifest: {e}*")

        return "\n".join(lines)

    # Check staging
    staging = session.root / "_staging" / package_id
    if staging.exists():
        lines.append("**Status:** Staged (ready to install)")
        # Similar to above...
        return "\n".join(lines)

    return f"Package not found: `{package_id}`\n\nUse `list packages` to see available packages."


@register(
    "package_preflight",
    description="Run preflight validation on a package",
    category="packages",
    requires_capability="admin",
    patterns=["preflight PKG-X", "validate PKG-X"],
)
def package_preflight(context: Dict[str, Any], query: str, session) -> str:
    """Run preflight validation.

    Args:
        context: Query context (may have package_id)
        query: Original query
        session: ChatSession instance

    Returns:
        Preflight results
    """
    package_id = context.get("package_id") or extract_package_id(query)

    if not package_id:
        return "Please specify a package ID. Example: `preflight PKG-TEST-001`"

    package_id = package_id.upper()

    # Find package source
    src_paths = [
        session.root / "_staging" / package_id,
        session.root / "packages_store" / package_id,
    ]

    src_path = None
    for p in src_paths:
        if p.exists() and p.is_dir():
            src_path = p
            break

    if not src_path:
        return f"Package source not found: `{package_id}`\n\nLooking in: _staging/, packages_store/"

    # Run preflight via pkgutil
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(session.root / "scripts" / "pkgutil.py"),
                "preflight",
                package_id,
                "--src", str(src_path),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            return f"# Preflight PASSED for {package_id}\n\n```json\n{result.stdout}\n```"
        else:
            return f"# Preflight FAILED for {package_id}\n\n```\n{result.stdout}\n{result.stderr}\n```"

    except subprocess.TimeoutExpired:
        return f"Preflight timed out for {package_id}"
    except Exception as e:
        return f"Preflight error: {e}"


@register(
    "package_install",
    description="Install a package",
    category="packages",
    requires_capability="admin",
    patterns=["install PKG-X"],
)
def package_install(context: Dict[str, Any], query: str, session) -> str:
    """Install a package.

    Args:
        context: Query context (may have package_id)
        query: Original query
        session: ChatSession instance

    Returns:
        Install result
    """
    package_id = context.get("package_id") or extract_package_id(query)

    if not package_id:
        return "Please specify a package ID. Example: `install PKG-TEST-001`"

    package_id = package_id.upper()

    # Find archive
    archive = _find_package_archive(package_id, session.root)
    if not archive:
        return (
            f"Package archive not found: `{package_id}`\n\n"
            f"Use `stage {package_id}` to create an installable archive."
        )

    # Run install
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(session.root / "scripts" / "package_install.py"),
                "--archive", str(archive),
                "--id", package_id,
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            # Log to session
            session.log_event("PACKAGE_INSTALLED", package_id, {
                "archive": str(archive),
            })
            return f"# Installed {package_id}\n\n{result.stdout}"
        else:
            return f"# Install FAILED for {package_id}\n\n```\n{result.stderr}\n```"

    except subprocess.TimeoutExpired:
        return f"Install timed out for {package_id}"
    except FileNotFoundError:
        return f"Install script not found. Check scripts/package_install.py exists."
    except Exception as e:
        return f"Install error: {e}"


@register(
    "package_uninstall",
    description="Uninstall a package",
    category="packages",
    requires_capability="admin",
    patterns=["uninstall PKG-X", "remove PKG-X"],
)
def package_uninstall(context: Dict[str, Any], query: str, session) -> str:
    """Uninstall a package.

    Args:
        context: Query context (may have package_id)
        query: Original query
        session: ChatSession instance

    Returns:
        Uninstall result
    """
    package_id = context.get("package_id") or extract_package_id(query)

    if not package_id:
        return "Please specify a package ID. Example: `uninstall PKG-TEST-001`"

    package_id = package_id.upper()

    # Check if installed
    installed_path = session.root / "installed" / package_id
    if not installed_path.exists():
        return f"Package not installed: `{package_id}`"

    # Load receipt
    receipt_path = installed_path / "receipt.json"
    if not receipt_path.exists():
        return f"No receipt found for {package_id}. Cannot safely uninstall."

    try:
        receipt = json.loads(receipt_path.read_text())
    except Exception as e:
        return f"Error reading receipt: {e}"

    # Remove files
    removed = 0
    errors = []
    for file_info in receipt.get("files", []):
        path = file_info.get("path") if isinstance(file_info, dict) else file_info
        file_path = session.root / path
        if file_path.exists():
            try:
                file_path.unlink()
                removed += 1
            except Exception as e:
                errors.append(f"Failed to remove {path}: {e}")

    # Remove installed directory
    try:
        shutil.rmtree(installed_path)
    except Exception as e:
        errors.append(f"Failed to remove installed directory: {e}")

    # Log to session
    session.log_event("PACKAGE_UNINSTALLED", package_id, {
        "files_removed": removed,
        "errors": errors,
    })

    lines = [f"# Uninstalled {package_id}", ""]
    lines.append(f"**Files removed:** {removed}")

    if errors:
        lines.append("")
        lines.append("**Errors:**")
        for err in errors:
            lines.append(f"- {err}")

    return "\n".join(lines)


@register(
    "package_stage",
    description="Stage a package for installation",
    category="packages",
    requires_capability="admin",
    patterns=["stage PKG-X"],
)
def package_stage(context: Dict[str, Any], query: str, session) -> str:
    """Stage a package.

    Args:
        context: Query context (may have package_id)
        query: Original query
        session: ChatSession instance

    Returns:
        Stage result
    """
    package_id = context.get("package_id") or extract_package_id(query)

    if not package_id:
        return "Please specify a package ID. Example: `stage PKG-TEST-001`"

    package_id = package_id.upper()

    # Find source
    src_paths = [
        session.root / "_staging" / package_id,
        session.root / "packages_store" / package_id,
    ]

    src_path = None
    for p in src_paths:
        if p.exists() and p.is_dir():
            src_path = p
            break

    if not src_path:
        return f"Package source not found: `{package_id}`"

    # Run stage via pkgutil
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(session.root / "scripts" / "pkgutil.py"),
                "stage",
                package_id,
                "--src", str(src_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            return f"# Staged {package_id}\n\n```\n{result.stderr}\n```"
        else:
            return f"# Stage FAILED for {package_id}\n\n```\n{result.stderr}\n```"

    except subprocess.TimeoutExpired:
        return f"Stage timed out for {package_id}"
    except Exception as e:
        return f"Stage error: {e}"
