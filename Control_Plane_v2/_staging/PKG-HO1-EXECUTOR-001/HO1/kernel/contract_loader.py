"""Contract Loader — loads and validates prompt contracts from disk.

Scans a contracts directory for JSON files and matches by contract_id.
Validates against an optional JSON schema before returning.
"""

import json
from pathlib import Path
from typing import Optional


class ContractNotFoundError(Exception):
    """Raised when a contract_id cannot be found in the contracts directory."""
    pass


class ContractValidationError(Exception):
    """Raised when a contract fails schema validation."""
    pass


class ContractLoader:
    """Loads prompt contracts from a directory of JSON files.

    Args:
        contracts_dir: Path to directory containing contract JSON files.
        schema_path: Optional path to a JSON schema for validation.
    """

    def __init__(self, contracts_dir: Path, schema_path: Optional[Path] = None):
        self.contracts_dir = Path(contracts_dir)
        self.schema_path = Path(schema_path) if schema_path else None
        self._schema: Optional[dict] = None

        if self.schema_path and self.schema_path.exists():
            with open(self.schema_path, "r", encoding="utf-8") as f:
                self._schema = json.load(f)

    def load(self, contract_id: str) -> dict:
        """Load a prompt contract by its contract_id.

        Scans all JSON files in contracts_dir, loads each, and returns
        the first whose "contract_id" field matches the requested ID.

        Args:
            contract_id: The contract_id to search for.

        Returns:
            The contract dict.

        Raises:
            ContractNotFoundError: If no matching contract is found.
            ContractValidationError: If the contract fails schema validation.
        """
        if not self.contracts_dir.exists():
            raise ContractNotFoundError(
                f"Contracts directory does not exist: {self.contracts_dir}"
            )

        for json_file in sorted(self.contracts_dir.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    contract = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            if not isinstance(contract, dict):
                continue

            if contract.get("contract_id") == contract_id:
                self._validate(contract, json_file)
                return contract

        raise ContractNotFoundError(
            f"No contract found with contract_id={contract_id} "
            f"in {self.contracts_dir}"
        )

    def _validate(self, contract: dict, source_path: Path) -> None:
        """Validate a contract against the loaded schema.

        Args:
            contract: The contract dict to validate.
            source_path: Path to the source file (for error messages).

        Raises:
            ContractValidationError: If validation fails.
        """
        if self._schema is None:
            return

        errors = []

        # Check required fields
        required = self._schema.get("required", [])
        for field in required:
            if field not in contract:
                errors.append(f"Missing required field: {field}")

        # Check type constraints on properties
        properties = self._schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            if prop_name in contract:
                expected_type = prop_schema.get("type")
                value = contract[prop_name]
                if expected_type and not self._check_type(value, expected_type):
                    errors.append(
                        f"Field '{prop_name}' expected type '{expected_type}', "
                        f"got '{type(value).__name__}'"
                    )

        if errors:
            raise ContractValidationError(
                f"Contract validation failed for {source_path.name}: "
                + "; ".join(errors)
            )

    @staticmethod
    def _check_type(value, expected_type: str) -> bool:
        """Check if a value matches the expected JSON schema type."""
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }
        python_type = type_map.get(expected_type)
        if python_type is None:
            return True  # Unknown type, skip check
        return isinstance(value, python_type)
