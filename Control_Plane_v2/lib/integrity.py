"""Integrity Library - Three-check integrity validation for Control Plane.

Provides:
1. Registry ↔ Filesystem check (every row has a file, every governed file has a row)
2. Content ↔ Hash check (stored hash matches computed hash)
3. Merkle root check (computed root matches stored root)

Per SPEC-025: Gate System for artifact lifecycle management.
"""
import csv
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.merkle import hash_file, merkle_root


@dataclass
class IntegrityIssue:
    """A single integrity issue."""
    check: str  # "registry_filesystem", "content_hash", "merkle_root"
    severity: str  # "error", "warning"
    artifact_id: Optional[str]
    message: str
    path: Optional[str] = None


@dataclass
class IntegrityResult:
    """Result of integrity validation."""
    passed: bool
    timestamp: str
    checks_run: list[str]
    issues: list[IntegrityIssue] = field(default_factory=list)
    computed_merkle_root: Optional[str] = None
    stored_merkle_root: Optional[str] = None
    registry_count: int = 0
    filesystem_count: int = 0

    def summary(self) -> dict:
        return {
            "passed": self.passed,
            "checks_run": self.checks_run,
            "issue_count": len(self.issues),
            "errors": len([i for i in self.issues if i.severity == "error"]),
            "warnings": len([i for i in self.issues if i.severity == "warning"]),
            "registry_count": self.registry_count,
            "computed_merkle_root": self.computed_merkle_root,
        }


class IntegrityChecker:
    """
    Three-check integrity validation.

    Usage:
        checker = IntegrityChecker(control_plane_root)
        result = checker.validate()

        if not result.passed:
            for issue in result.issues:
                print(f"{issue.severity}: {issue.message}")
    """

    # Directories to scan for orphan detection
    GOVERNED_DIRS = [
        "frameworks",
        "lib",
        "modules",
        "prompts",
        "registries",
        "scripts",
        "specs",
    ]

    # Extensions that should be governed
    GOVERNED_EXTENSIONS = {".py", ".md", ".csv", ".json"}

    # Files to exclude from orphan detection
    EXCLUDED_FILES = {
        "__init__.py",
        "__pycache__",
        ".DS_Store",
        ".gitkeep",
    }

    def __init__(self, control_plane_root: Path = None):
        if control_plane_root is None:
            control_plane_root = Path(__file__).resolve().parent.parent
        self.root = control_plane_root
        self.registry_path = self.root / "registries" / "control_plane_registry.csv"
        self.manifest_path = self.root / "MANIFEST.json"

    def validate(self, checks: list[str] = None) -> IntegrityResult:
        """
        Run integrity validation.

        Args:
            checks: List of checks to run. Default: all three.
                   Options: "registry_filesystem", "content_hash", "merkle_root"

        Returns:
            IntegrityResult with pass/fail and any issues found.
        """
        if checks is None:
            checks = ["registry_filesystem", "content_hash", "merkle_root"]

        issues = []
        registry_items = self._load_registry()
        computed_root = None
        stored_root = None
        filesystem_count = 0

        # Check 1: Registry ↔ Filesystem
        if "registry_filesystem" in checks:
            rf_issues, filesystem_count = self._check_registry_filesystem(registry_items)
            issues.extend(rf_issues)

        # Check 2: Content ↔ Hash
        if "content_hash" in checks:
            ch_issues = self._check_content_hash(registry_items)
            issues.extend(ch_issues)

        # Check 3: Merkle root
        if "merkle_root" in checks:
            mr_issues, computed_root, stored_root = self._check_merkle_root(registry_items)
            issues.extend(mr_issues)

        # Determine pass/fail (errors fail, warnings don't)
        has_errors = any(i.severity == "error" for i in issues)

        return IntegrityResult(
            passed=not has_errors,
            timestamp=datetime.now(timezone.utc).isoformat(),
            checks_run=checks,
            issues=issues,
            computed_merkle_root=computed_root,
            stored_merkle_root=stored_root,
            registry_count=len(registry_items),
            filesystem_count=filesystem_count,
        )

    def _load_registry(self) -> list[dict]:
        """Load control plane registry."""
        if not self.registry_path.exists():
            return []

        items = []
        with open(self.registry_path, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                items.append(row)
        return items

    def _check_registry_filesystem(self, registry_items: list[dict]) -> tuple[list[IntegrityIssue], int]:
        """
        Check 1: Registry matches filesystem.
        - Every registry row has a file
        - Every governed file has a registry row (orphan detection)
        """
        issues = []

        # Get all registered paths
        registered_paths = set()
        for item in registry_items:
            artifact_path = item.get("artifact_path", "")
            if artifact_path:
                # Normalize path
                if artifact_path.startswith("/"):
                    artifact_path = artifact_path[1:]
                registered_paths.add(artifact_path)

                # Check if file exists
                full_path = self.root / artifact_path
                if not full_path.exists():
                    issues.append(IntegrityIssue(
                        check="registry_filesystem",
                        severity="error",
                        artifact_id=item.get("id"),
                        message=f"Registered artifact missing from filesystem",
                        path=artifact_path,
                    ))

        # Scan filesystem for orphans
        filesystem_files = set()
        for dir_name in self.GOVERNED_DIRS:
            dir_path = self.root / dir_name
            if dir_path.exists():
                for file_path in dir_path.rglob("*"):
                    if file_path.is_file():
                        # Skip excluded files
                        if file_path.name in self.EXCLUDED_FILES:
                            continue
                        if "__pycache__" in str(file_path):
                            continue

                        # Only check governed extensions
                        if file_path.suffix not in self.GOVERNED_EXTENSIONS:
                            continue

                        rel_path = str(file_path.relative_to(self.root))
                        filesystem_files.add(rel_path)

                        # Normalize for comparison (handle leading slash)
                        normalized = rel_path
                        normalized_with_slash = "/" + rel_path

                        if normalized not in registered_paths and normalized_with_slash not in registered_paths:
                            issues.append(IntegrityIssue(
                                check="registry_filesystem",
                                severity="warning",
                                artifact_id=None,
                                message=f"Orphan file not in registry",
                                path=rel_path,
                            ))

        return issues, len(filesystem_files)

    def _check_content_hash(self, registry_items: list[dict]) -> list[IntegrityIssue]:
        """
        Check 2: Content matches stored hash.
        """
        issues = []

        for item in registry_items:
            artifact_path = item.get("artifact_path", "")
            stored_hash = item.get("content_hash", "")

            if not artifact_path or not stored_hash:
                continue

            # Normalize path
            if artifact_path.startswith("/"):
                artifact_path = artifact_path[1:]

            full_path = self.root / artifact_path
            if not full_path.exists():
                # Already caught in registry_filesystem check
                continue

            # Handle directories (hash the directory)
            if full_path.is_dir():
                computed = self._hash_directory(full_path)
            else:
                computed = hash_file(full_path)

            if computed != stored_hash:
                issues.append(IntegrityIssue(
                    check="content_hash",
                    severity="error",
                    artifact_id=item.get("id"),
                    message=f"Content hash mismatch (stored: {stored_hash[:16]}..., computed: {computed[:16]}...)",
                    path=artifact_path,
                ))

        return issues

    def _hash_directory(self, dir_path: Path) -> str:
        """Hash a directory by combining hashes of all files."""
        hashes = []
        for file_path in sorted(dir_path.rglob("*")):
            if file_path.is_file() and file_path.name not in self.EXCLUDED_FILES:
                if "__pycache__" not in str(file_path):
                    hashes.append(hash_file(file_path))

        if not hashes:
            return hashlib.sha256(b"").hexdigest()

        return merkle_root(hashes)

    def _check_merkle_root(self, registry_items: list[dict]) -> tuple[list[IntegrityIssue], str, Optional[str]]:
        """
        Check 3: Merkle root matches stored root.
        """
        issues = []

        # Collect all content hashes
        hashes = []
        for item in registry_items:
            content_hash = item.get("content_hash", "")
            if content_hash:
                hashes.append(content_hash)

        # Sort for determinism
        hashes.sort()

        # Compute merkle root
        computed_root = merkle_root(hashes) if hashes else ""

        # Load stored root from manifest
        stored_root = None
        if self.manifest_path.exists():
            import json
            try:
                with open(self.manifest_path) as f:
                    manifest = json.load(f)
                stored_root = manifest.get("merkle_root")
            except (json.JSONDecodeError, IOError):
                pass

        if stored_root and stored_root != computed_root:
            issues.append(IntegrityIssue(
                check="merkle_root",
                severity="error",
                artifact_id=None,
                message=f"Merkle root mismatch (stored: {stored_root[:16]}..., computed: {computed_root[:16]}...)",
                path="MANIFEST.json",
            ))

        return issues, computed_root, stored_root

    def compute_file_hash(self, file_path: Path) -> str:
        """Compute hash for a single file."""
        if file_path.is_dir():
            return self._hash_directory(file_path)
        return hash_file(file_path)


def validate_integrity(control_plane_root: Path = None) -> IntegrityResult:
    """Convenience function for running integrity validation."""
    checker = IntegrityChecker(control_plane_root)
    return checker.validate()


@dataclass
class OrphanFile:
    """An orphan file with lineage information."""
    path: str
    created: str
    modified: str
    size_bytes: int
    category: str
    git_author: Optional[str]
    git_date: Optional[str]
    git_commit: Optional[str]
    recommended_action: str
    reason: str


class OrphanAuditor:
    """
    Audit orphan files with lineage tracking.

    Finds all files not in registry and traces their origin.
    """

    def __init__(self, control_plane_root: Path = None):
        if control_plane_root is None:
            control_plane_root = Path(__file__).resolve().parent.parent
        self.root = control_plane_root
        self.checker = IntegrityChecker(control_plane_root)

    def audit(self) -> list[OrphanFile]:
        """
        Audit all orphan files and return detailed lineage.
        """
        result = self.checker.validate(checks=["registry_filesystem"])
        orphans = []

        for issue in result.issues:
            if issue.message == "Orphan file not in registry" and issue.path:
                orphan = self._analyze_orphan(issue.path)
                orphans.append(orphan)

        return orphans

    def _analyze_orphan(self, rel_path: str) -> OrphanFile:
        """Analyze a single orphan file."""
        full_path = self.root / rel_path

        # File stats
        try:
            stat = full_path.stat()
            created = datetime.fromtimestamp(stat.st_birthtime).strftime("%Y-%m-%d")
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
            size = stat.st_size
        except (OSError, AttributeError):
            created = "unknown"
            modified = "unknown"
            size = 0

        # Category from path
        parts = rel_path.split("/")
        if parts[0] == "modules" and len(parts) > 1:
            category = f"modules/{parts[1]}"
        else:
            category = parts[0]

        # Git lineage
        git_author, git_date, git_commit = self._get_git_lineage(rel_path)

        # Recommended action based on analysis
        action, reason = self._recommend_action(rel_path, category, modified)

        return OrphanFile(
            path=rel_path,
            created=created,
            modified=modified,
            size_bytes=size,
            category=category,
            git_author=git_author,
            git_date=git_date,
            git_commit=git_commit,
            recommended_action=action,
            reason=reason,
        )

    def _get_git_lineage(self, rel_path: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Get git history for a file."""
        import subprocess
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%an|%ad|%H", "--date=short", "--", rel_path],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("|")
                if len(parts) == 3:
                    return parts[0], parts[1], parts[2][:8]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None, None, None

    def _recommend_action(self, path: str, category: str, modified: str) -> tuple[str, str]:
        """Recommend action for an orphan file."""

        # Check if it's in a decoupled module (should be deleted)
        decoupled_modules = ["locked_system"]
        for mod in decoupled_modules:
            if f"modules/{mod}" in path:
                return "DELETE", f"Module '{mod}' is decoupled to separate repo per CLAUDE.md"

        # Specs should be registered
        if category == "specs":
            return "REGISTER", "Specs are governance artifacts and must be in registry"

        # Backup files should be archived
        if "_backup" in path or "backup" in path.lower():
            return "ARCHIVE", "Backup file should be in _archive/"

        # Recently modified = likely active
        if modified >= "2026-01-27":
            return "REGISTER", "Recently modified, likely active artifact"

        # Old files = archive candidate
        if modified < "2026-01-20":
            return "ARCHIVE", "Not recently modified, may be obsolete"

        # Default
        return "REVIEW", "Requires manual review to determine status"

    def report(self) -> str:
        """Generate human-readable audit report."""
        orphans = self.audit()

        lines = []
        lines.append("=" * 80)
        lines.append("ORPHAN FILE AUDIT REPORT")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"Total orphans: {len(orphans)}")
        lines.append("=" * 80)
        lines.append("")

        # Group by recommended action
        by_action = {}
        for o in orphans:
            by_action.setdefault(o.recommended_action, []).append(o)

        # Summary
        lines.append("SUMMARY BY ACTION:")
        lines.append("-" * 40)
        for action in ["DELETE", "ARCHIVE", "REGISTER", "REVIEW"]:
            count = len(by_action.get(action, []))
            lines.append(f"  {action}: {count} files")
        lines.append("")

        # Detail by action
        for action in ["DELETE", "ARCHIVE", "REGISTER", "REVIEW"]:
            files = by_action.get(action, [])
            if not files:
                continue

            lines.append("=" * 80)
            lines.append(f"ACTION: {action} ({len(files)} files)")
            lines.append("=" * 80)
            lines.append("")

            # Group by category within action
            by_cat = {}
            for o in files:
                by_cat.setdefault(o.category, []).append(o)

            for cat in sorted(by_cat.keys()):
                cat_files = by_cat[cat]
                lines.append(f"  [{cat}] - {len(cat_files)} files")
                for o in cat_files:
                    git_info = f"by {o.git_author} on {o.git_date}" if o.git_author else "no git history"
                    lines.append(f"    {o.path}")
                    lines.append(f"      Modified: {o.modified} | {git_info}")
                    lines.append(f"      Reason: {o.reason}")
                lines.append("")

        return "\n".join(lines)


def audit_orphans(control_plane_root: Path = None) -> str:
    """Convenience function to run orphan audit and get report."""
    auditor = OrphanAuditor(control_plane_root)
    return auditor.report()
