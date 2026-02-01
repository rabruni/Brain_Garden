#!/usr/bin/env python3
"""
validate_install_policy.py - Validate install policy documents.

Validates install policy YAML files against the policy schema and
installation-specific rules.

Usage:
    python3 scripts/validate_install_policy.py
    python3 scripts/validate_install_policy.py --policy policies/install_policy.yaml
    python3 scripts/validate_install_policy.py --strict
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Add repo root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE

# Try to import yaml
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# Install-specific validation rules
VALID_ACTIONS = {
    "install",
    "uninstall",
    "update",
    "verify",
    "pack",
    "sign",
    "recover",
    "doctor_fix",
    "*",
}

VALID_TIERS = {"G0", "T0", "T1", "T2", "T3", "*", "all"}
VALID_PLANES = {"hot", "first", "second", "*", "all"}
VALID_ENVIRONMENTS = {"dev", "staging", "prod", "*", "all"}
VALID_EFFECTS = {"allow", "deny", "require_approval", "audit", "warn"}
VALID_ROLES = {"admin", "maintainer", "auditor", "reader"}
VALID_REQUIREMENTS = {
    "signature",
    "attestation",
    "approval",
    "audit_log",
    "integrity_check",
    "tier_validation",
}


class ValidationError:
    """Represents a validation error."""

    def __init__(self, path: str, message: str, severity: str = "error"):
        self.path = path
        self.message = message
        self.severity = severity

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.path}: {self.message}"


def load_yaml_file(path: Path) -> Optional[Dict[str, Any]]:
    """Load a YAML file."""
    if not HAS_YAML:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except (yaml.YAMLError, IOError):
        return None


def validate_rule(rule: Dict[str, Any], rule_index: int) -> List[ValidationError]:
    """Validate a single install policy rule."""
    errors = []
    prefix = f"rules[{rule_index}]"

    # Check rule_id format
    rule_id = rule.get("rule_id", "")
    if not rule_id:
        errors.append(ValidationError(prefix, "Missing rule_id"))
    elif not rule_id.startswith("R") or not rule_id[1:].isdigit():
        errors.append(ValidationError(f"{prefix}.rule_id", f"Invalid rule_id format: {rule_id}"))

    # Check condition
    condition = rule.get("condition", {})
    if not condition:
        errors.append(ValidationError(f"{prefix}.condition", "Missing condition"))
    else:
        # Validate action if present
        if "action" in condition:
            action = condition["action"]
            if action not in VALID_ACTIONS:
                errors.append(ValidationError(
                    f"{prefix}.condition.action",
                    f"Invalid action: {action}"
                ))

        # Validate tier if present
        if "tier" in condition:
            tier = condition["tier"]
            if tier not in VALID_TIERS:
                errors.append(ValidationError(
                    f"{prefix}.condition.tier",
                    f"Invalid tier: {tier}"
                ))

        # Validate plane if present
        if "plane" in condition:
            plane = condition["plane"]
            if plane not in VALID_PLANES:
                errors.append(ValidationError(
                    f"{prefix}.condition.plane",
                    f"Invalid plane: {plane}"
                ))

        # Validate environment if present
        if "environment" in condition:
            env = condition["environment"]
            if env not in VALID_ENVIRONMENTS:
                errors.append(ValidationError(
                    f"{prefix}.condition.environment",
                    f"Invalid environment: {env}"
                ))

    # Check effect
    effect = rule.get("effect", "")
    if not effect:
        errors.append(ValidationError(f"{prefix}.effect", "Missing effect"))
    elif effect not in VALID_EFFECTS:
        errors.append(ValidationError(f"{prefix}.effect", f"Invalid effect: {effect}"))

    # Check requirements
    requirements = rule.get("requirements", [])
    for req in requirements:
        if req not in VALID_REQUIREMENTS:
            errors.append(ValidationError(
                f"{prefix}.requirements",
                f"Invalid requirement: {req}"
            ))

    # Check allowed_roles
    allowed_roles = rule.get("allowed_roles", [])
    for role in allowed_roles:
        if role not in VALID_ROLES:
            errors.append(ValidationError(
                f"{prefix}.allowed_roles",
                f"Invalid role: {role}"
            ))

    # Check priority
    rule_priority = rule.get("priority")
    if rule_priority is not None:
        if not isinstance(rule_priority, int) or rule_priority < 0 or rule_priority > 1000:
            errors.append(ValidationError(
                f"{prefix}.priority",
                f"Rule priority must be integer 0-1000, got: {rule_priority}"
            ))

    return errors


def validate_plane_restrictions(restrictions: Dict[str, Any]) -> List[ValidationError]:
    """Validate plane restriction configuration."""
    errors = []

    for plane_name, config in restrictions.items():
        prefix = f"plane_restrictions.{plane_name}"

        if plane_name not in {"hot", "first", "second"}:
            errors.append(ValidationError(prefix, f"Unknown plane: {plane_name}"))
            continue

        # Validate allowed_tiers
        if "allowed_tiers" in config:
            for tier in config["allowed_tiers"]:
                if tier not in {"G0", "T0", "T1", "T2", "T3"}:
                    errors.append(ValidationError(
                        f"{prefix}.allowed_tiers",
                        f"Invalid tier: {tier}"
                    ))

        # Validate required_for_all
        if "required_for_all" in config:
            for req in config["required_for_all"]:
                if req not in VALID_REQUIREMENTS:
                    errors.append(ValidationError(
                        f"{prefix}.required_for_all",
                        f"Invalid requirement: {req}"
                    ))

        # Validate min_role
        if "min_role" in config:
            role = config["min_role"]
            if role not in VALID_ROLES:
                errors.append(ValidationError(
                    f"{prefix}.min_role",
                    f"Invalid role: {role}"
                ))

    return errors


def validate_environment_overrides(overrides: Dict[str, Any]) -> List[ValidationError]:
    """Validate environment override configuration."""
    errors = []

    for env_name, config in overrides.items():
        prefix = f"environment_overrides.{env_name}"

        if env_name not in {"dev", "staging", "prod"}:
            errors.append(ValidationError(prefix, f"Unknown environment: {env_name}"))
            continue

        # Validate require_approval_for
        if "require_approval_for" in config:
            for tier in config["require_approval_for"]:
                if tier not in {"G0", "T0", "T1", "T2", "T3"}:
                    errors.append(ValidationError(
                        f"{prefix}.require_approval_for",
                        f"Invalid tier: {tier}"
                    ))

    return errors


def validate_install_policy(policy: Dict[str, Any]) -> Tuple[List[ValidationError], List[str]]:
    """Validate an install policy document.

    Args:
        policy: Parsed policy dictionary

    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []

    # Required fields
    required_fields = [
        "schema_version",
        "policy_id",
        "policy_type",
        "version",
        "effective_date",
        "rules",
    ]

    for field in required_fields:
        if field not in policy:
            errors.append(ValidationError("root", f"Missing required field: {field}"))

    # Schema version
    schema_version = policy.get("schema_version")
    if schema_version and schema_version != "1.0":
        errors.append(ValidationError(
            "schema_version",
            f"Unsupported schema_version: {schema_version}"
        ))

    # Policy type
    policy_type = policy.get("policy_type")
    if policy_type and policy_type != "install":
        errors.append(ValidationError(
            "policy_type",
            f"Expected policy_type 'install', got: {policy_type}"
        ))

    # Policy ID format
    policy_id = policy.get("policy_id", "")
    if policy_id and not policy_id.startswith("POL-"):
        errors.append(ValidationError("policy_id", f"Invalid policy_id format: {policy_id}"))

    # Validate rules
    rules = policy.get("rules", [])
    if not rules:
        errors.append(ValidationError("rules", "Policy must have at least one rule"))
    else:
        rule_ids = set()
        for i, rule in enumerate(rules):
            rule_errors = validate_rule(rule, i)
            errors.extend(rule_errors)

            # Check for duplicate rule IDs
            rule_id = rule.get("rule_id", "")
            if rule_id in rule_ids:
                errors.append(ValidationError(
                    f"rules[{i}].rule_id",
                    f"Duplicate rule_id: {rule_id}"
                ))
            rule_ids.add(rule_id)

    # Validate plane_restrictions if present
    if "plane_restrictions" in policy:
        restriction_errors = validate_plane_restrictions(policy["plane_restrictions"])
        errors.extend(restriction_errors)

    # Validate environment_overrides if present
    if "environment_overrides" in policy:
        override_errors = validate_environment_overrides(policy["environment_overrides"])
        errors.extend(override_errors)

    # Validate applies_to if present
    applies_to = policy.get("applies_to", {})
    if applies_to:
        if "planes" in applies_to:
            for plane in applies_to["planes"]:
                if plane not in VALID_PLANES:
                    errors.append(ValidationError(
                        "applies_to.planes",
                        f"Invalid plane: {plane}"
                    ))

        if "tiers" in applies_to:
            for tier in applies_to["tiers"]:
                if tier not in VALID_TIERS:
                    errors.append(ValidationError(
                        "applies_to.tiers",
                        f"Invalid tier: {tier}"
                    ))

        if "environments" in applies_to:
            for env in applies_to["environments"]:
                if env not in VALID_ENVIRONMENTS:
                    errors.append(ValidationError(
                        "applies_to.environments",
                        f"Invalid environment: {env}"
                    ))

    # Check for metadata
    if "metadata" not in policy:
        warnings.append("No metadata section found")

    # Check for plane restriction completeness
    if "plane_restrictions" in policy:
        defined_planes = set(policy["plane_restrictions"].keys())
        expected_planes = {"hot", "first", "second"}
        missing = expected_planes - defined_planes
        if missing:
            warnings.append(f"Missing plane restrictions for: {missing}")

    return errors, warnings


def find_policy_files() -> List[Path]:
    """Find all install policy files."""
    policies_dir = CONTROL_PLANE / "policies"
    if not policies_dir.exists():
        return []

    files = []
    for f in policies_dir.glob("install*.yaml"):
        files.append(f)
    for f in policies_dir.glob("install*.yml"):
        files.append(f)
    for f in policies_dir.glob("install*.json"):
        files.append(f)

    return sorted(files)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate install policy documents"
    )
    parser.add_argument(
        "--policy",
        type=Path,
        help="Specific policy file to validate"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    if not HAS_YAML:
        print("WARNING: PyYAML not installed. Only JSON policy files supported.")
        print("Install with: pip install pyyaml")

    # Find files to validate
    if args.policy:
        policy_path = args.policy
        if not policy_path.is_absolute():
            policy_path = CONTROL_PLANE / policy_path
        files = [policy_path]
    else:
        files = find_policy_files()

    if not files:
        print("No install policy files found.")
        return 0

    all_errors = []
    all_warnings = []
    results = {}

    for f in files:
        print(f"Validating: {f}")

        if not f.exists():
            all_errors.append(ValidationError(str(f), "File not found"))
            results[str(f)] = {"status": "error", "errors": ["File not found"]}
            continue

        policy = load_yaml_file(f)
        if policy is None:
            all_errors.append(ValidationError(str(f), "Failed to parse policy file"))
            results[str(f)] = {"status": "error", "errors": ["Failed to parse"]}
            continue

        errors, warnings = validate_install_policy(policy)

        for e in errors:
            e.path = f"{f.name}:{e.path}"
        all_errors.extend(errors)

        for w in warnings:
            all_warnings.append(f"{f.name}: {w}")

        status = "valid" if not errors else "invalid"
        if not errors and warnings:
            status = "valid_with_warnings"

        results[str(f)] = {
            "status": status,
            "errors": [str(e) for e in errors],
            "warnings": warnings,
        }

    # Output results
    if args.json:
        output = {
            "files_checked": len(files),
            "total_errors": len(all_errors),
            "total_warnings": len(all_warnings),
            "results": results,
        }
        print(json.dumps(output, indent=2))
    else:
        print()
        if all_errors:
            print("ERRORS:")
            for e in all_errors:
                print(f"  {e}")

        if all_warnings:
            print("\nWARNINGS:")
            for w in all_warnings:
                print(f"  {w}")

        print()
        print(f"Validation complete:")
        print(f"  Files checked: {len(files)}")
        print(f"  Errors: {len(all_errors)}")
        print(f"  Warnings: {len(all_warnings)}")

    # Exit code
    if all_errors:
        print("\nFAIL: Validation errors found")
        return 1

    if args.strict and all_warnings:
        print("\nFAIL: Warnings present in strict mode")
        return 1

    print("\nOK: Install policy validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
