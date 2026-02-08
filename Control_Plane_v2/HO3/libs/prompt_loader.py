"""Prompt Loader with Hash Verification.

Loads governed prompts from the governed_prompts/ directory.
Verifies prompt content against registered hashes.

Example:
    from kernel.prompt_loader import load_prompt, verify_prompt_hash

    # Load a governed prompt
    content = load_prompt("PRM-ADMIN-EXPLAIN-001")

    # Verify hash matches
    if verify_prompt_hash("PRM-ADMIN-EXPLAIN-001", content):
        print("Hash verified")
"""

import csv
import os
from hashlib import sha256
from pathlib import Path
from typing import Dict, List, Optional


class PromptError(Exception):
    """Base exception for prompt operations."""

    def __init__(self, message: str, code: str = "PROMPT_ERROR", details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class PromptNotFoundError(PromptError):
    """Raised when prompt file doesn't exist."""

    def __init__(self, prompt_id: str, path: str = None):
        super().__init__(
            f"Prompt not found: {prompt_id}",
            code="PROMPT_NOT_FOUND",
            details={"prompt_id": prompt_id, "path": path},
        )


class PromptHashMismatchError(PromptError):
    """Raised when prompt content doesn't match registered hash."""

    def __init__(self, prompt_id: str, expected: str, actual: str):
        super().__init__(
            f"Prompt hash mismatch: {prompt_id}",
            code="PROMPT_HASH_MISMATCH",
            details={
                "prompt_id": prompt_id,
                "expected_hash": expected,
                "actual_hash": actual,
            },
        )


class PromptNotRegisteredError(PromptError):
    """Raised when prompt is not in registry."""

    def __init__(self, prompt_id: str):
        super().__init__(
            f"Prompt not registered: {prompt_id}",
            code="PROMPT_NOT_REGISTERED",
            details={"prompt_id": prompt_id},
        )


class InvalidPromptIdError(PromptError):
    """Raised when prompt ID format is invalid."""

    def __init__(self, prompt_id: str):
        super().__init__(
            f"Invalid prompt ID format: {prompt_id}",
            code="INVALID_PROMPT_ID",
            details={
                "prompt_id": prompt_id,
                "expected_format": "PRM-<DOMAIN>-<SEQ>",
            },
        )


def _get_control_plane_root() -> Path:
    """Get Control Plane root directory."""
    current = Path(__file__).resolve()
    while current.name != "Control_Plane_v2" and current.parent != current:
        current = current.parent
    if current.name == "Control_Plane_v2":
        return current
    return Path.cwd()


def _get_prompts_dir() -> Path:
    """Get governed_prompts directory."""
    return _get_control_plane_root() / "governed_prompts"


def _get_registry_path() -> Path:
    """Get prompts_registry.csv path."""
    return _get_control_plane_root() / "registries" / "prompts_registry.csv"


def _compute_hash(content: str) -> str:
    """Compute SHA256 hash of content.

    Args:
        content: Content to hash

    Returns:
        Hash string in format "sha256:<hexdigest>"
    """
    return f"sha256:{sha256(content.encode()).hexdigest()}"


def _validate_prompt_id(prompt_id: str) -> bool:
    """Validate prompt ID format.

    Args:
        prompt_id: Prompt identifier

    Returns:
        True if valid format

    Raises:
        InvalidPromptIdError: If format is invalid
    """
    if not prompt_id:
        raise InvalidPromptIdError(prompt_id)

    if not prompt_id.startswith("PRM-"):
        raise InvalidPromptIdError(prompt_id)

    parts = prompt_id.split("-")
    if len(parts) < 3:
        raise InvalidPromptIdError(prompt_id)

    return True


def load_registry() -> Dict[str, dict]:
    """Load prompts registry into a dictionary.

    Returns:
        Dict mapping prompt_id to registry entry

    Raises:
        PromptError: If registry cannot be loaded
    """
    registry_path = _get_registry_path()

    if not registry_path.exists():
        return {}

    try:
        prompts = {}
        with open(registry_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                prompts[row["prompt_id"]] = row
        return prompts
    except Exception as e:
        raise PromptError(
            f"Failed to load registry: {e}",
            code="REGISTRY_ERROR",
            details={"path": str(registry_path)},
        )


def get_prompt_info(prompt_id: str) -> dict:
    """Get registry info for a prompt.

    Args:
        prompt_id: Prompt identifier

    Returns:
        Registry entry dict

    Raises:
        PromptNotRegisteredError: If prompt not in registry
    """
    _validate_prompt_id(prompt_id)
    registry = load_registry()

    if prompt_id not in registry:
        raise PromptNotRegisteredError(prompt_id)

    return registry[prompt_id]


def get_prompt_hash(prompt_id: str) -> str:
    """Get registered hash for a prompt.

    Args:
        prompt_id: Prompt identifier

    Returns:
        Hash string from registry

    Raises:
        PromptNotRegisteredError: If prompt not in registry
    """
    info = get_prompt_info(prompt_id)
    return info.get("hash", "")


def verify_prompt_hash(prompt_id: str, content: str) -> bool:
    """Verify prompt content matches registered hash.

    Args:
        prompt_id: Prompt identifier
        content: Content to verify

    Returns:
        True if hash matches

    Raises:
        PromptNotRegisteredError: If prompt not in registry
        PromptHashMismatchError: If hash doesn't match
    """
    expected_hash = get_prompt_hash(prompt_id)
    actual_hash = _compute_hash(content)

    if expected_hash != actual_hash:
        raise PromptHashMismatchError(prompt_id, expected_hash, actual_hash)

    return True


def load_prompt(prompt_id: str, verify: bool = True) -> str:
    """Load a governed prompt by ID.

    Args:
        prompt_id: Prompt identifier (e.g., PRM-ADMIN-001)
        verify: Whether to verify hash (default: True)

    Returns:
        Prompt template content

    Raises:
        InvalidPromptIdError: If ID format is invalid
        PromptNotFoundError: If prompt file doesn't exist
        PromptNotRegisteredError: If prompt not in registry
        PromptHashMismatchError: If hash verification fails
    """
    _validate_prompt_id(prompt_id)

    # Check registry first
    if verify:
        get_prompt_info(prompt_id)

    # Get prompt file path
    prompt_path = _get_prompts_dir() / f"{prompt_id}.md"

    if not prompt_path.exists():
        raise PromptNotFoundError(prompt_id, str(prompt_path))

    # Read content
    content = prompt_path.read_text()

    # Verify hash if requested
    if verify:
        verify_prompt_hash(prompt_id, content)

    return content


def list_prompts(status: Optional[str] = "active") -> List[dict]:
    """List prompts by status.

    Args:
        status: Filter by status (active, deprecated, draft, all)

    Returns:
        List of prompt metadata dicts
    """
    registry = load_registry()
    prompts = list(registry.values())

    if status and status != "all":
        prompts = [p for p in prompts if p.get("status") == status]

    return prompts


def verify_registry() -> dict:
    """Verify all registered prompts exist and have valid hashes.

    Returns:
        Dict with verification results
    """
    registry = load_registry()
    results = {
        "total": len(registry),
        "valid": 0,
        "missing": [],
        "hash_mismatch": [],
        "errors": [],
    }

    for prompt_id, info in registry.items():
        try:
            content = load_prompt(prompt_id, verify=True)
            results["valid"] += 1
        except PromptNotFoundError:
            results["missing"].append(prompt_id)
        except PromptHashMismatchError as e:
            results["hash_mismatch"].append({
                "prompt_id": prompt_id,
                "expected": e.details.get("expected_hash"),
                "actual": e.details.get("actual_hash"),
            })
        except Exception as e:
            results["errors"].append({
                "prompt_id": prompt_id,
                "error": str(e),
            })

    results["passed"] = (
        len(results["missing"]) == 0 and
        len(results["hash_mismatch"]) == 0 and
        len(results["errors"]) == 0
    )

    return results
