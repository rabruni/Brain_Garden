"""
schema_validator.py - Lightweight manifest validation (no jsonschema dependency).

Validates package manifest structure against essential rules from
schemas/package_manifest.json without requiring the jsonschema library.

Usage:
    from kernel.schema_validator import validate_manifest
    from kernel.schema_validator import validate_framework, validate_spec

    valid, errors = validate_manifest(manifest_data)
    valid, errors = validate_framework(framework_data)
    valid, errors = validate_spec(spec_data)
"""
import re
from typing import Dict, List, Tuple, Any


# Pattern for package IDs
_PKG_ID_PATTERN = re.compile(r"^PKG-[A-Z0-9-]+$")

# Pattern for sha256 hash format
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")

# Pattern for semver
_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+].*)?$"
)

# Pattern for framework IDs
_FMWK_ID_PATTERN = re.compile(r"^FMWK-[A-Z0-9-]+$")

# Pattern for spec IDs
_SPEC_ID_PATTERN = re.compile(r"^SPEC-[A-Z0-9-]+$")

# Valid values for enumerated fields
_VALID_STATUSES = {"active", "draft", "deprecated"}
_VALID_RINGS = {"kernel", "admin", "resident"}
_VALID_PLANE_IDS = {"hot", "ho3", "ho2", "ho1"}


def validate_manifest(data: Any) -> Tuple[bool, List[str]]:
    """Validate a package manifest dict against essential schema rules.

    Checks:
    - Required fields (package_id, assets, version)
    - Type correctness (assets is list, each asset has path/sha256)
    - ID pattern (PKG-*)
    - Hash format (sha256:<64hex>)
    - Path safety (no .., no absolute paths)

    Args:
        data: Manifest dict to validate

    Returns:
        Tuple of (valid: bool, errors: list[str])
    """
    errors: List[str] = []

    if not isinstance(data, dict):
        return False, ["Manifest must be a JSON object"]

    schema_version = data.get("schema_version")

    # Auto-detect format: if package_id present, treat as v1.2
    if schema_version is None:
        schema_version = "1.2" if "package_id" in data else "1.0"

    # v1.2 format: requires package_id + assets
    if schema_version == "1.2":
        if "package_id" not in data:
            errors.append("Missing required field: 'package_id'")
        if "assets" not in data:
            errors.append("Missing required field: 'assets'")
    # Legacy format: requires id + tier + artifact_paths + deps
    elif schema_version in ("1.0", "1.1"):
        for field in ("id", "tier", "artifact_paths", "deps"):
            if field not in data:
                errors.append(f"Missing required field: '{field}'")
    else:
        errors.append(f"Unknown schema_version: '{schema_version}'")

    # version is always required
    if "version" not in data:
        errors.append("Missing required field: 'version'")
    elif not _SEMVER_PATTERN.match(str(data["version"])):
        errors.append(f"Invalid semver format: '{data['version']}'")

    # Validate package_id pattern
    pkg_id = data.get("package_id") or data.get("id")
    if pkg_id and not _PKG_ID_PATTERN.match(pkg_id):
        errors.append(f"Invalid package ID format: '{pkg_id}' (must match PKG-[A-Z0-9-]+)")

    # Validate assets array
    assets = data.get("assets")
    if assets is not None:
        if not isinstance(assets, list):
            errors.append("'assets' must be a list")
        else:
            for i, asset in enumerate(assets):
                if not isinstance(asset, dict):
                    errors.append(f"assets[{i}]: must be an object")
                    continue

                path = asset.get("path")
                if not path:
                    errors.append(f"assets[{i}]: missing 'path'")
                else:
                    if ".." in path:
                        errors.append(f"assets[{i}]: path '{path}' contains '..'")
                    if path.startswith("/"):
                        errors.append(f"assets[{i}]: path '{path}' is absolute")

                sha = asset.get("sha256")
                if not sha:
                    errors.append(f"assets[{i}]: missing 'sha256'")
                elif not _SHA256_PATTERN.match(sha):
                    errors.append(f"assets[{i}]: invalid sha256 format: '{sha[:30]}...'")

    return len(errors) == 0, errors


def validate_framework(data: Any) -> Tuple[bool, List[str]]:
    """Validate framework manifest.yaml against Layer 1 rules.

    Checks: framework_id pattern, title, status, version present.
    Ring in (kernel, admin, resident). expected_specs is list of SPEC-*.
    plane or plane_id present and valid.

    Args:
        data: Framework manifest dict to validate

    Returns:
        Tuple of (valid: bool, errors: list[str])
    """
    errors: List[str] = []

    if not isinstance(data, dict):
        return False, ["Framework manifest must be a dict"]

    # Required fields
    if "framework_id" not in data:
        errors.append("Missing required field: 'framework_id'")
    elif not _FMWK_ID_PATTERN.match(str(data["framework_id"])):
        errors.append(
            f"Invalid framework_id pattern: '{data['framework_id']}' "
            f"(must match FMWK-[A-Z0-9-]+)"
        )

    if "title" not in data:
        errors.append("Missing required field: 'title'")

    if "status" not in data:
        errors.append("Missing required field: 'status'")
    elif data["status"] not in _VALID_STATUSES:
        errors.append(
            f"Invalid status: '{data['status']}' "
            f"(must be one of: {', '.join(sorted(_VALID_STATUSES))})"
        )

    if "version" not in data:
        errors.append("Missing required field: 'version'")

    # Optional fields with validation
    if "ring" in data and data["ring"] not in _VALID_RINGS:
        errors.append(
            f"Invalid ring: '{data['ring']}' "
            f"(must be one of: {', '.join(sorted(_VALID_RINGS))})"
        )

    if "plane_id" in data and data["plane_id"] not in _VALID_PLANE_IDS:
        errors.append(
            f"Invalid plane_id: '{data['plane_id']}' "
            f"(must be one of: {', '.join(sorted(_VALID_PLANE_IDS))})"
        )

    if "plane" in data and data["plane"] not in _VALID_PLANE_IDS:
        errors.append(
            f"Invalid plane: '{data['plane']}' "
            f"(must be one of: {', '.join(sorted(_VALID_PLANE_IDS))})"
        )

    if "expected_specs" in data:
        specs = data["expected_specs"]
        if not isinstance(specs, list):
            errors.append("'expected_specs' must be a list")
        else:
            for spec in specs:
                if not isinstance(spec, str) or not _SPEC_ID_PATTERN.match(spec):
                    errors.append(
                        f"Invalid expected_specs entry: '{spec}' "
                        f"(must match SPEC-[A-Z0-9-]+)"
                    )

    return len(errors) == 0, errors


def validate_spec(data: Any) -> Tuple[bool, List[str]]:
    """Validate spec manifest.yaml against Layer 1 rules.

    Checks: spec_id pattern, framework_id pattern, title, status, version,
    assets present. Assets is non-empty list. Status in (active, draft, deprecated).

    Args:
        data: Spec manifest dict to validate

    Returns:
        Tuple of (valid: bool, errors: list[str])
    """
    errors: List[str] = []

    if not isinstance(data, dict):
        return False, ["Spec manifest must be a dict"]

    # Required fields
    if "spec_id" not in data:
        errors.append("Missing required field: 'spec_id'")
    elif not _SPEC_ID_PATTERN.match(str(data["spec_id"])):
        errors.append(
            f"Invalid spec_id pattern: '{data['spec_id']}' "
            f"(must match SPEC-[A-Z0-9-]+)"
        )

    if "title" not in data:
        errors.append("Missing required field: 'title'")

    if "framework_id" not in data:
        errors.append("Missing required field: 'framework_id'")
    elif not _FMWK_ID_PATTERN.match(str(data["framework_id"])):
        errors.append(
            f"Invalid framework_id pattern: '{data['framework_id']}' "
            f"(must match FMWK-[A-Z0-9-]+)"
        )

    if "status" not in data:
        errors.append("Missing required field: 'status'")
    elif data["status"] not in _VALID_STATUSES:
        errors.append(
            f"Invalid status: '{data['status']}' "
            f"(must be one of: {', '.join(sorted(_VALID_STATUSES))})"
        )

    if "version" not in data:
        errors.append("Missing required field: 'version'")

    if "assets" not in data:
        errors.append("Missing required field: 'assets'")
    elif not isinstance(data["assets"], list):
        errors.append("'assets' must be a list")
    elif len(data["assets"]) == 0:
        errors.append("'assets' must not be empty")

    # Optional fields with validation
    if "plane_id" in data and data["plane_id"] not in _VALID_PLANE_IDS:
        errors.append(
            f"Invalid plane_id: '{data['plane_id']}' "
            f"(must be one of: {', '.join(sorted(_VALID_PLANE_IDS))})"
        )

    return len(errors) == 0, errors
