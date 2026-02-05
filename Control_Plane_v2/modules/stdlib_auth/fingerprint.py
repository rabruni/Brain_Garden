"""Secret fingerprinting for safe logging.

Provides a way to reference secrets in logs without exposing the actual value.
Uses SHA256 hash truncated to 16 characters.

Example:
    from modules.stdlib_auth.fingerprint import fingerprint_secret

    fp = fingerprint_secret("my-api-key")
    # Returns: "fp:sha256:a1b2c3d4e5f6g7h8"
"""

from hashlib import sha256


def fingerprint_secret(secret: str) -> str:
    """Create a safe fingerprint of a secret for logging.

    Args:
        secret: The secret value to fingerprint

    Returns:
        Fingerprint string in format "fp:sha256:<first16chars>"

    Example:
        >>> fingerprint_secret("my-secret")
        'fp:sha256:...'
    """
    if not secret:
        return "fp:sha256:empty"

    hash_hex = sha256(secret.encode()).hexdigest()
    return f"fp:sha256:{hash_hex[:16]}"
