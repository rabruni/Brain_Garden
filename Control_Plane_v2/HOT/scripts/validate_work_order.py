#!/usr/bin/env python3
"""
validate_work_order.py - Validate Work Order against JSON Schema.

Validates:
1. JSON Schema compliance (work_order.schema.json)
2. Work Order ID format matches filename
3. Referenced spec_id and framework_id exist in registries
4. Scope files are valid paths

Usage:
    python3 scripts/validate_work_order.py --wo work_orders/ho3/WO-20260201-001.json
    python3 scripts/validate_work_order.py --wo WO-20260201-001
    python3 scripts/validate_work_order.py --all  # Validate all work orders
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.paths import CONTROL_PLANE

# Try to import jsonschema, fall back to manual validation
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


def load_schema(schema_name: str, plane_root: Path = CONTROL_PLANE) -> dict:
    """Load a JSON Schema from the schemas directory."""
    schema_path = plane_root / 'schemas' / schema_name
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_work_order(wo_path: Path) -> dict:
    """Load Work Order JSON file."""
    with open(wo_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def discover_wo_path(wo_id: str, plane_root: Path = CONTROL_PLANE) -> Path:
    """Discover Work Order file path from ID."""
    if '/' in wo_id or wo_id.endswith('.json'):
        path = plane_root / wo_id.lstrip('/')
        if path.exists():
            return path
        raise FileNotFoundError(f"Work Order file not found: {path}")

    for plane_id in ['ho3', 'ho2', 'ho1']:
        wo_path = plane_root / 'work_orders' / plane_id / f"{wo_id}.json"
        if wo_path.exists():
            return wo_path

    raise FileNotFoundError(f"Work Order {wo_id} not found")


def get_all_work_orders(plane_root: Path = CONTROL_PLANE) -> List[Path]:
    """Get all Work Order files in the work_orders directory."""
    wo_files = []
    wo_dir = plane_root / 'work_orders'
    if wo_dir.exists():
        for plane_dir in wo_dir.iterdir():
            if plane_dir.is_dir():
                for wo_file in plane_dir.glob('WO-*.json'):
                    wo_files.append(wo_file)
    return sorted(wo_files)


def load_registry_ids(plane_root: Path = CONTROL_PLANE) -> Tuple[set, set]:
    """Load framework and spec IDs from registries."""
    framework_ids = set()
    spec_ids = set()

    # Load framework IDs from control_plane_registry.csv
    cp_registry = plane_root / 'registries' / 'control_plane_registry.csv'
    if cp_registry.exists():
        with open(cp_registry, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                item_id = row.get('id', '')
                if item_id.startswith('FMWK-'):
                    framework_ids.add(item_id)

    # Load spec IDs from specs_registry.csv (if it exists)
    specs_registry = plane_root / 'registries' / 'specs_registry.csv'
    if specs_registry.exists():
        with open(specs_registry, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                spec_ids.add(row.get('id', ''))

    return framework_ids, spec_ids


class ValidationResult:
    """Result of Work Order validation."""

    def __init__(self, wo_path: Path):
        self.wo_path = wo_path
        self.errors: List[str] = []
        self.warnings: List[str] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def to_dict(self) -> dict:
        return {
            "work_order_path": str(self.wo_path),
            "valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings
        }


def validate_schema(wo: dict, schema: dict, result: ValidationResult) -> None:
    """Validate Work Order against JSON Schema."""
    if HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=wo, schema=schema)
        except jsonschema.ValidationError as e:
            result.add_error(f"Schema validation failed: {e.message}")
        except jsonschema.SchemaError as e:
            result.add_error(f"Invalid schema: {e.message}")
    else:
        # Manual validation of required fields
        required = schema.get('required', [])
        for field in required:
            if field not in wo:
                result.add_error(f"Missing required field: {field}")


def validate_id_format(wo: dict, wo_path: Path, result: ValidationResult) -> None:
    """Validate Work Order ID format and filename match."""
    wo_id = wo.get('work_order_id', '')

    # Check format
    if not re.match(r'^WO-\d{8}-\d{3}$', wo_id):
        result.add_error(f"Invalid work_order_id format: {wo_id} (expected WO-YYYYMMDD-NNN)")
        return

    # Check filename matches ID
    expected_filename = f"{wo_id}.json"
    if wo_path.name != expected_filename:
        result.add_error(f"Filename mismatch: {wo_path.name} != {expected_filename}")


def validate_references(wo: dict, framework_ids: set, spec_ids: set, result: ValidationResult) -> None:
    """Validate that referenced framework and spec exist."""
    framework_id = wo.get('framework_id', '')
    spec_id = wo.get('spec_id', '')

    if framework_id and framework_id not in framework_ids:
        result.add_warning(f"Framework not found in registry: {framework_id}")

    if spec_id and spec_ids and spec_id not in spec_ids:
        # Only warn if specs_registry exists and has entries
        result.add_warning(f"Spec not found in registry: {spec_id}")


def validate_scope(wo: dict, plane_root: Path, result: ValidationResult) -> None:
    """Validate scope definitions."""
    scope = wo.get('scope', {})
    allowed_files = scope.get('allowed_files', [])
    forbidden_files = scope.get('forbidden_files', [])

    # Check for overlap
    overlap = set(allowed_files) & set(forbidden_files)
    if overlap:
        result.add_error(f"Files in both allowed and forbidden: {overlap}")

    # Warn if allowed_files is empty
    if not allowed_files:
        result.add_warning("scope.allowed_files is empty - no files can be modified")


def validate_outputs(wo: dict, result: ValidationResult) -> None:
    """Validate outputs are within scope."""
    scope = wo.get('scope', {})
    outputs = wo.get('outputs', {})

    allowed_files = set(scope.get('allowed_files', []))
    output_files = set(outputs.get('files', []))

    # Check outputs are subset of allowed
    outside_scope = output_files - allowed_files
    if outside_scope:
        result.add_error(f"Output files outside scope: {outside_scope}")


def validate_work_order(
    wo_path: Path,
    schema: dict,
    framework_ids: set,
    spec_ids: set,
    plane_root: Path = CONTROL_PLANE
) -> ValidationResult:
    """Perform full validation of a Work Order."""
    result = ValidationResult(wo_path)

    # Load Work Order
    try:
        wo = load_work_order(wo_path)
    except json.JSONDecodeError as e:
        result.add_error(f"Invalid JSON: {e}")
        return result
    except FileNotFoundError:
        result.add_error(f"File not found: {wo_path}")
        return result

    # Run all validations
    validate_schema(wo, schema, result)
    validate_id_format(wo, wo_path, result)
    validate_references(wo, framework_ids, spec_ids, result)
    validate_scope(wo, plane_root, result)
    validate_outputs(wo, result)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Validate Work Order against schema and constraints"
    )
    parser.add_argument(
        "--wo", "-w",
        help="Work Order ID or path to validate"
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Validate all work orders"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=CONTROL_PLANE,
        help="Plane root path"
    )

    args = parser.parse_args()

    if not args.wo and not args.all:
        parser.error("Either --wo or --all is required")

    try:
        # Load schema and registries
        schema = load_schema('work_order.schema.json', args.root)
        framework_ids, spec_ids = load_registry_ids(args.root)

        # Determine which files to validate
        if args.all:
            wo_paths = get_all_work_orders(args.root)
            if not wo_paths:
                if args.json:
                    print(json.dumps({"message": "No work orders found", "valid": True}))
                else:
                    print("No work orders found in work_orders/")
                return 0
        else:
            wo_paths = [discover_wo_path(args.wo, args.root)]

        # Validate each
        results = []
        all_valid = True

        for wo_path in wo_paths:
            result = validate_work_order(wo_path, schema, framework_ids, spec_ids, args.root)

            # Apply strict mode
            if args.strict and result.warnings:
                for warning in result.warnings:
                    result.add_error(f"(strict) {warning}")
                result.warnings = []

            results.append(result)
            if not result.is_valid:
                all_valid = False

        # Output
        if args.json:
            if len(results) == 1:
                print(json.dumps(results[0].to_dict(), indent=2))
            else:
                print(json.dumps({
                    "all_valid": all_valid,
                    "results": [r.to_dict() for r in results]
                }, indent=2))
        else:
            for result in results:
                print(f"\n{result.wo_path}")
                print("=" * 60)
                if result.is_valid:
                    print("VALID")
                else:
                    print("INVALID")
                    for error in result.errors:
                        print(f"  ERROR: {error}")
                for warning in result.warnings:
                    print(f"  WARNING: {warning}")

            if len(results) > 1:
                print(f"\nSummary: {sum(1 for r in results if r.is_valid)}/{len(results)} valid")

        return 0 if all_valid else 1

    except FileNotFoundError as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
