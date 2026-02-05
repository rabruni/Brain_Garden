"""SHA256 hashing utilities for evidence generation.

Provides deterministic hashing of JSON objects, files, and strings.
All hashes are returned in the format "sha256:<64_hex_chars>".

Example:
    from modules.stdlib_evidence.hasher import hash_json, hash_file

    # Hash a JSON object
    data = {"key": "value", "nested": {"a": 1}}
    h = hash_json(data)  # sha256:...

    # Hash a file
    h = hash_file(Path("myfile.txt"))  # sha256:...
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Union


def hash_string(s: str) -> str:
    """Compute SHA256 hash of a string.

    Args:
        s: Input string

    Returns:
        Hash string in format "sha256:<64_hex_chars>"
    """
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return f"sha256:{h}"


def hash_json(obj: Dict[str, Any]) -> str:
    """Compute deterministic SHA256 hash of JSON object.

    Keys are sorted to ensure identical objects produce identical hashes
    regardless of key order in the original dict.

    Args:
        obj: JSON-serializable dictionary

    Returns:
        Hash string in format "sha256:<64_hex_chars>"

    Example:
        >>> hash_json({"b": 2, "a": 1}) == hash_json({"a": 1, "b": 2})
        True
    """
    # Sort keys for deterministic serialization
    json_str = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hash_string(json_str)


def hash_file(path: Union[str, Path]) -> str:
    """Compute SHA256 hash of file contents.

    Reads file in binary mode to handle both text and binary files.

    Args:
        path: Path to file

    Returns:
        Hash string in format "sha256:<64_hex_chars>"

    Raises:
        FileNotFoundError: If file doesn't exist
        PermissionError: If file cannot be read
    """
    path = Path(path)
    h = hashlib.sha256()

    with open(path, "rb") as f:
        # Read in chunks for memory efficiency with large files
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)

    return f"sha256:{h.hexdigest()}"
