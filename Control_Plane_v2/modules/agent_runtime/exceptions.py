"""Custom exceptions for the agent runtime."""


class CapabilityViolation(Exception):
    """Raised when an operation violates declared capabilities.

    Attributes:
        operation: The attempted operation (read/write/execute)
        path: The path that was accessed
        message: Human-readable description
        details: Additional violation details
    """

    def __init__(
        self,
        message: str,
        operation: str = None,
        path: str = None,
        details: dict = None,
    ):
        super().__init__(message)
        self.operation = operation
        self.path = path
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/serialization."""
        return {
            "error_type": "CapabilityViolation",
            "message": self.message,
            "operation": self.operation,
            "path": self.path,
            "details": self.details,
        }


class PackageNotFoundError(Exception):
    """Raised when a package cannot be found.

    Attributes:
        package_id: The package that was not found
        searched_paths: Paths that were searched
    """

    def __init__(self, package_id: str, searched_paths: list = None):
        message = f"Package not found: {package_id}"
        super().__init__(message)
        self.package_id = package_id
        self.searched_paths = searched_paths or []


class SessionError(Exception):
    """Raised for session-related errors.

    Attributes:
        session_id: The session ID if available
        reason: The reason for the error
    """

    def __init__(self, message: str, session_id: str = None, reason: str = None):
        super().__init__(message)
        self.session_id = session_id
        self.reason = reason


class SandboxError(Exception):
    """Raised for sandbox-related errors.

    Attributes:
        session_id: The session ID
        undeclared_writes: List of undeclared files written
        missing_writes: List of declared files not written
    """

    def __init__(
        self,
        message: str,
        session_id: str = None,
        undeclared_writes: list = None,
        missing_writes: list = None,
    ):
        super().__init__(message)
        self.session_id = session_id
        self.undeclared_writes = undeclared_writes or []
        self.missing_writes = missing_writes or []

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/serialization."""
        return {
            "error_type": "SandboxError",
            "message": str(self),
            "session_id": self.session_id,
            "undeclared_writes": self.undeclared_writes,
            "missing_writes": self.missing_writes,
        }
