#!/usr/bin/env python3
"""
validate_attention_policy.py - Validate attention policy documents.

Validates attention policy YAML files against the policy schema and
attention-specific rules.

Usage:
    python3 scripts/validate_attention_policy.py
    python3 scripts/validate_attention_policy.py --policy scripts/policies/attention_default.yaml
    python3 scripts/validate_attention_policy.py --strict
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Add repo root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "HOT"))

from kernel.paths import CONTROL_PLANE

# Try to import yaml
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# Attention-specific validation rules
VALID_ATTENTION_TYPES = {
    "policy_update",
    "compliance_check",
    "audit_request",
    "escalation",
    "notification",
    "directive",
}

VALID_PRIORITIES = {"critical", "high", "medium", "low"}
VALID_PLANES = {"hot", "first", "second"}
VALID_EFFECTS = {"allow", "deny", "require_approval", "audit", "warn"}
VALID_DELIVERY_MODES = {"immediate", "batched", "scheduled"}


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
        # Fallback: try to parse as JSON (YAML is a superset of JSON)
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
    """Validate a single attention policy rule."""
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
        # Validate attention_type if present
        if "attention_type" in condition:
            att_type = condition["attention_type"]
            if att_type not in VALID_ATTENTION_TYPES:
                errors.append(ValidationError(
                    f"{prefix}.condition.attention_type",
                    f"Invalid attention_type: {att_type}"
                ))

        # Validate priority if present
        if "priority" in condition:
            priority = condition["priority"]
            if priority not in VALID_PRIORITIES:
                errors.append(ValidationError(
                    f"{prefix}.condition.priority",
                    f"Invalid priority: {priority}"
                ))

        # Validate source_plane if present
        if "source_plane" in condition:
            plane = condition["source_plane"]
            if plane not in VALID_PLANES:
                errors.append(ValidationError(
                    f"{prefix}.condition.source_plane",
                    f"Invalid source_plane: {plane}"
                ))

    # Check effect
    effect = rule.get("effect", "")
    if not effect:
        errors.append(ValidationError(f"{prefix}.effect", "Missing effect"))
    elif effect not in VALID_EFFECTS:
        errors.append(ValidationError(f"{prefix}.effect", f"Invalid effect: {effect}"))

    # Check priority (rule priority, not attention priority)
    rule_priority = rule.get("priority")
    if rule_priority is not None:
        if not isinstance(rule_priority, int) or rule_priority < 0 or rule_priority > 1000:
            errors.append(ValidationError(
                f"{prefix}.priority",
                f"Rule priority must be integer 0-1000, got: {rule_priority}"
            ))

    # Validate routing if present
    routing = rule.get("routing", {})
    if routing:
        if "delivery_mode" in routing:
            mode = routing["delivery_mode"]
            if mode not in VALID_DELIVERY_MODES:
                errors.append(ValidationError(
                    f"{prefix}.routing.delivery_mode",
                    f"Invalid delivery_mode: {mode}"
                ))

        if "max_retries" in routing:
            retries = routing["max_retries"]
            if not isinstance(retries, int) or retries < 0 or retries > 10:
                errors.append(ValidationError(
                    f"{prefix}.routing.max_retries",
                    f"max_retries must be integer 0-10, got: {retries}"
                ))

    return errors


def validate_plane_routing(routing: Dict[str, Any]) -> List[ValidationError]:
    """Validate plane routing configuration."""
    errors = []

    for plane_name, config in routing.items():
        prefix = f"plane_routing.{plane_name}"

        if plane_name not in VALID_PLANES:
            errors.append(ValidationError(prefix, f"Unknown plane: {plane_name}"))
            continue

        # Validate receive_priorities
        if "receive_priorities" in config:
            for prio in config["receive_priorities"]:
                if prio not in VALID_PRIORITIES:
                    errors.append(ValidationError(
                        f"{prefix}.receive_priorities",
                        f"Invalid priority: {prio}"
                    ))

        # Validate forward_to
        if "forward_to" in config:
            for target in config["forward_to"]:
                if target not in VALID_PLANES:
                    errors.append(ValidationError(
                        f"{prefix}.forward_to",
                        f"Invalid target plane: {target}"
                    ))

    return errors


def validate_attention_policy(policy: Dict[str, Any]) -> Tuple[List[ValidationError], List[str]]:
    """Validate an attention policy document.

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
    if policy_type and policy_type != "attention":
        errors.append(ValidationError(
            "policy_type",
            f"Expected policy_type 'attention', got: {policy_type}"
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

    # Validate plane_routing if present
    if "plane_routing" in policy:
        routing_errors = validate_plane_routing(policy["plane_routing"])
        errors.extend(routing_errors)

    # Validate applies_to if present
    applies_to = policy.get("applies_to", {})
    if applies_to:
        if "planes" in applies_to:
            for plane in applies_to["planes"]:
                if plane not in VALID_PLANES and plane != "all":
                    errors.append(ValidationError(
                        "applies_to.planes",
                        f"Invalid plane: {plane}"
                    ))

    # Check for metadata
    if "metadata" not in policy:
        warnings.append("No metadata section found")

    return errors, warnings


def find_policy_files() -> List[Path]:
    """Find all attention policy files."""
    policies_dir = CONTROL_PLANE / "scripts" / "policies"
    if not policies_dir.exists():
        return []

    files = []
    for f in policies_dir.glob("attention*.yaml"):
        files.append(f)
    for f in policies_dir.glob("attention*.yml"):
        files.append(f)
    for f in policies_dir.glob("attention*.json"):
        files.append(f)

    return sorted(files)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate attention policy documents"
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
        print("No attention policy files found.")
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

        errors, warnings = validate_attention_policy(policy)

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

    print("\nOK: Attention policy validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
