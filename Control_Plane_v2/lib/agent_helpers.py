#!/usr/bin/env python3
"""
lib/agent_helpers.py - Shared read-only helpers for agents (PKG-CP-INSPECT-001).

Provides read-only inspection utilities for agents with evidence pointers
for replayability and auditability.

ARCHITECTURAL CONSTRAINTS:
1. Strictly read-only for PRISTINE paths
2. Append-only to HO1 ledgers ONLY when invoked by runner
3. Evidence pointers returned for replayability (ledger ranges, hashes, paths)
4. Separate from preflight (validation != inspection)

All methods return (result, EvidencePointer) tuples to enable:
- Agents staying "no-drift" - outputs reference specific ledger/file state
- Replayable - verifier can re-read same evidence
- Auditable - evidence hash proves what agent saw
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.plane import PlaneContext, load_chain_config, get_plane_by_name


@dataclass
class EvidencePointer:
    """Replayable reference to ledger/file state.

    Evidence pointers allow agents to prove what data they saw,
    enabling replay verification and audit trails.

    Attributes:
        source: Type of evidence ("ledger", "file", "registry")
        path: File path or ledger path
        range: Ledger entry range (start_idx, end_idx) if applicable
        hash: Content hash at read time
        timestamp: ISO timestamp of read
    """
    source: str              # "ledger" | "file" | "registry"
    path: str                # File path or ledger path
    range: Optional[Tuple[int, int]] = None  # Ledger entry range (start, end)
    hash: str = ""           # Content hash at read time
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "source": self.source,
            "path": self.path,
            "range": list(self.range) if self.range else None,
            "hash": self.hash,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvidencePointer":
        """Create from dictionary."""
        range_val = tuple(data["range"]) if data.get("range") else None
        return cls(
            source=data["source"],
            path=data["path"],
            range=range_val,
            hash=data.get("hash", ""),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class InstalledPackage:
    """Package info with evidence pointer."""
    package_id: str
    version: str
    manifest_hash: str
    assets_count: int
    installed_at: str
    plane_id: str = ""
    package_type: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "package_id": self.package_id,
            "version": self.version,
            "manifest_hash": self.manifest_hash,
            "assets_count": self.assets_count,
            "installed_at": self.installed_at,
            "plane_id": self.plane_id,
            "package_type": self.package_type,
        }


@dataclass
class GateFailure:
    """Gate failure with evidence pointers."""
    gate: str
    timestamp: str
    package_id: Optional[str]
    error_message: str
    evidence: List[EvidencePointer] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "gate": self.gate,
            "timestamp": self.timestamp,
            "package_id": self.package_id,
            "error_message": self.error_message,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass
class PathClassification:
    """Path classification result."""
    path: str
    classification: str  # PRISTINE, APPEND_ONLY, DERIVED
    governed_root: Optional[str]
    explanation: str

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "path": self.path,
            "classification": self.classification,
            "governed_root": self.governed_root,
            "explanation": self.explanation,
        }


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of file contents."""
    if not file_path.exists():
        return ""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of string content."""
    return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


class CPInspector:
    """Read-only Control Plane inspector.

    Provides inspection utilities that:
    - Never write to PRISTINE paths
    - Return evidence pointers for all queries
    - Support replay verification
    """

    def __init__(self, plane_root: Optional[Path] = None, plane_name: str = "ho3"):
        """Initialize inspector.

        Args:
            plane_root: Root path for the plane (defaults to CONTROL_PLANE)
            plane_name: Plane name (ho1, ho2, ho3)
        """
        self.plane_root = plane_root or CONTROL_PLANE
        self.plane_name = plane_name

    def list_installed(self, plane: str = "ho3") -> Tuple[List[InstalledPackage], EvidencePointer]:
        """List installed packages in specified plane.

        Args:
            plane: Plane to query (ho1, ho2, ho3)

        Returns:
            Tuple of (packages list, evidence pointer)
            Evidence points to installed/*/manifest.json state at read time.
        """
        packages = []
        manifest_hashes = []

        # Determine installed directory based on plane
        if plane == "ho3":
            installed_dir = self.plane_root / "installed"
        else:
            installed_dir = self.plane_root / "planes" / plane / "installed"

        if not installed_dir.exists():
            evidence = EvidencePointer(
                source="file",
                path=str(installed_dir),
                hash="",
            )
            return packages, evidence

        # Scan installed packages
        for pkg_dir in sorted(installed_dir.iterdir()):
            if not pkg_dir.is_dir():
                continue

            manifest_path = pkg_dir / "manifest.json"
            receipt_path = pkg_dir / "receipt.json"

            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text())
                    receipt = {}
                    if receipt_path.exists():
                        receipt = json.loads(receipt_path.read_text())

                    pkg = InstalledPackage(
                        package_id=manifest.get("package_id", pkg_dir.name),
                        version=manifest.get("version", "0.0.0"),
                        manifest_hash=receipt.get("manifest_hash", compute_file_hash(manifest_path)),
                        assets_count=len(manifest.get("assets", [])),
                        installed_at=receipt.get("installed_at", ""),
                        plane_id=manifest.get("plane_id", plane),
                        package_type=manifest.get("package_type", "standard"),
                    )
                    packages.append(pkg)
                    manifest_hashes.append(compute_file_hash(manifest_path))
                except (json.JSONDecodeError, IOError):
                    continue

        # Compute combined hash for evidence
        combined = "\n".join(sorted(manifest_hashes))
        combined_hash = compute_content_hash(combined) if manifest_hashes else ""

        evidence = EvidencePointer(
            source="file",
            path=str(installed_dir),
            hash=combined_hash,
        )

        return packages, evidence

    def list_governed_roots(self) -> Tuple[List[str], EvidencePointer]:
        """List governed roots from config.

        Returns:
            Tuple of (roots list, evidence pointer)
            Evidence points to config/governed_roots.json.
        """
        config_path = self.plane_root / "config" / "governed_roots.json"

        if not config_path.exists():
            evidence = EvidencePointer(
                source="file",
                path=str(config_path),
                hash="",
            )
            return [], evidence

        try:
            content = config_path.read_text()
            config = json.loads(content)
            roots = config.get("governed_roots", [])
            content_hash = compute_content_hash(content)
        except (json.JSONDecodeError, IOError):
            roots = []
            content_hash = ""

        evidence = EvidencePointer(
            source="file",
            path=str(config_path),
            hash=content_hash,
        )

        return roots, evidence

    def last_gate_failures(
        self,
        count: int = 10,
        gate: Optional[str] = None
    ) -> Tuple[List[GateFailure], EvidencePointer]:
        """Get recent gate failures with evidence.

        Args:
            count: Maximum number of failures to return
            gate: Optional gate filter (G0A, G0B, G1, G2, G3, G4, G5, G6)

        Returns:
            Tuple of (failures list, evidence pointer)
            Evidence points to ledger entry range queried.
        """
        failures = []

        # Query governance ledger for GATE_FAILED events
        ledger_path = self.plane_root / "ledger" / "governance.jsonl"
        if not ledger_path.exists():
            evidence = EvidencePointer(
                source="ledger",
                path=str(ledger_path),
                hash="",
            )
            return failures, evidence

        # Read ledger entries
        entries = []
        try:
            with open(ledger_path, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            entries.append((i, entry))
                        except json.JSONDecodeError:
                            continue
        except IOError:
            evidence = EvidencePointer(
                source="ledger",
                path=str(ledger_path),
                hash="",
            )
            return failures, evidence

        # Filter for gate failures
        gate_failures = []
        for idx, entry in entries:
            event_type = entry.get("event_type", "")
            if "FAIL" in event_type or "GATE_FAILED" in event_type:
                entry_gate = entry.get("metadata", {}).get("gate", "")
                if gate is None or entry_gate == gate:
                    gate_failures.append((idx, entry))

        # Take last N
        recent = gate_failures[-count:]

        # Convert to GateFailure objects
        for idx, entry in recent:
            metadata = entry.get("metadata", {})
            failure = GateFailure(
                gate=metadata.get("gate", entry.get("event_type", "")),
                timestamp=entry.get("timestamp", ""),
                package_id=metadata.get("package_id", entry.get("submission_id")),
                error_message=entry.get("reason", metadata.get("error", "")),
                evidence=[EvidencePointer(
                    source="ledger",
                    path=str(ledger_path),
                    range=(idx, idx + 1),
                    hash=entry.get("entry_hash", ""),
                )],
            )
            failures.append(failure)

        # Compute evidence for query
        start_idx = recent[0][0] if recent else 0
        end_idx = recent[-1][0] + 1 if recent else 0
        evidence = EvidencePointer(
            source="ledger",
            path=str(ledger_path),
            range=(start_idx, end_idx),
            hash=compute_file_hash(ledger_path),
        )

        return failures, evidence

    def read_ho2_checkpoint(
        self,
        session_id: str
    ) -> Tuple[Optional[Dict], EvidencePointer]:
        """Read HO2 checkpoint for a session.

        Args:
            session_id: Session ID to look up

        Returns:
            Tuple of (checkpoint data or None, evidence pointer)
            Evidence points to HO2 workorder.jsonl entry.
        """
        ho2_ledger = self.plane_root / "planes" / "ho2" / "ledger" / "workorder.jsonl"

        if not ho2_ledger.exists():
            evidence = EvidencePointer(
                source="ledger",
                path=str(ho2_ledger),
                hash="",
            )
            return None, evidence

        # Search for checkpoint entry
        checkpoint = None
        entry_idx = None
        entry_hash = ""

        try:
            with open(ho2_ledger, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            if entry.get("metadata", {}).get("session_id") == session_id:
                                checkpoint = entry
                                entry_idx = i
                                entry_hash = entry.get("entry_hash", "")
                        except json.JSONDecodeError:
                            continue
        except IOError:
            pass

        evidence = EvidencePointer(
            source="ledger",
            path=str(ho2_ledger),
            range=(entry_idx, entry_idx + 1) if entry_idx is not None else None,
            hash=entry_hash,
        )

        return checkpoint, evidence

    def replay_ho1(
        self,
        session_id: str,
        from_checkpoint: Optional[str] = None
    ) -> Tuple[List[Dict], EvidencePointer]:
        """Replay HO1 ledger entries for a session.

        Args:
            session_id: Session to replay
            from_checkpoint: Optional HO2 checkpoint to start from

        Returns:
            Tuple of (entries list, evidence pointer)
            Evidence points to ledger range replayed.
        """
        # Find session ledger
        sessions_dir = self.plane_root / "planes" / "ho1" / "sessions"
        session_ledger = sessions_dir / session_id / "ledger" / "session.jsonl"

        if not session_ledger.exists():
            # Try base worker.jsonl
            session_ledger = self.plane_root / "planes" / "ho1" / "ledger" / "worker.jsonl"

        if not session_ledger.exists():
            evidence = EvidencePointer(
                source="ledger",
                path=str(session_ledger),
                hash="",
            )
            return [], evidence

        # Read entries
        entries = []
        start_idx = 0
        try:
            with open(session_ledger, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            # Filter by session if specified
                            entry_session = entry.get("metadata", {}).get("session_id", "")
                            if session_id in str(session_ledger) or entry_session == session_id:
                                entries.append(entry)
                                if not start_idx:
                                    start_idx = i
                        except json.JSONDecodeError:
                            continue
        except IOError:
            pass

        evidence = EvidencePointer(
            source="ledger",
            path=str(session_ledger),
            range=(start_idx, start_idx + len(entries)),
            hash=compute_file_hash(session_ledger),
        )

        return entries, evidence

    def explain_path(self, path: str) -> Tuple[PathClassification, EvidencePointer]:
        """Explain path classification (PRISTINE/DERIVED/APPEND_ONLY).

        Args:
            path: Path to classify (relative to plane root)

        Returns:
            Tuple of (classification info, evidence pointer)
        """
        # Load governed roots
        config_path = self.plane_root / "config" / "governed_roots.json"
        governed_roots = []
        derived_roots = ["packages_store", "registries/compiled", "versions", "tmp", "_staging", "installed"]
        append_only_roots = ["ledger"]

        if config_path.exists():
            try:
                config = json.loads(config_path.read_text())
                governed_roots = config.get("governed_roots", [])
            except (json.JSONDecodeError, IOError):
                pass

        # Determine classification
        path_normalized = path.lstrip("/")
        classification = "UNKNOWN"
        governed_root = None
        explanation = ""

        # Check append-only first
        for root in append_only_roots:
            if path_normalized.startswith(root):
                classification = "APPEND_ONLY"
                governed_root = root
                explanation = f"Path is under append-only root '{root}'. Only ledger appends allowed."
                break

        # Check derived
        if classification == "UNKNOWN":
            for root in derived_roots:
                if path_normalized.startswith(root):
                    classification = "DERIVED"
                    governed_root = root
                    explanation = f"Path is under derived root '{root}'. Mutable via rebuild operations."
                    break

        # Check pristine
        if classification == "UNKNOWN":
            for root in governed_roots:
                if path_normalized.startswith(root.rstrip("/")):
                    classification = "PRISTINE"
                    governed_root = root
                    explanation = f"Path is under governed root '{root}'. Read-only except via package install."
                    break

        if classification == "UNKNOWN":
            explanation = "Path is not under any governed, derived, or append-only root."

        result = PathClassification(
            path=path,
            classification=classification,
            governed_root=governed_root,
            explanation=explanation,
        )

        evidence = EvidencePointer(
            source="file",
            path=str(config_path),
            hash=compute_file_hash(config_path) if config_path.exists() else "",
        )

        return result, evidence

    def get_registry_stats(self) -> Tuple[Dict[str, Any], EvidencePointer]:
        """Get registry statistics.

        Returns:
            Tuple of (stats dict, evidence pointer)
        """
        stats = {
            "registries": 0,
            "total_items": 0,
            "by_status": {},
            "by_registry": {},
        }

        registries_dir = self.plane_root / "registries"
        registry_files = []

        if registries_dir.exists():
            registry_files = list(registries_dir.glob("*.csv"))
            stats["registries"] = len(registry_files)

            for reg_file in registry_files:
                try:
                    with open(reg_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        rows = list(reader)
                        stats["by_registry"][reg_file.name] = len(rows)
                        stats["total_items"] += len(rows)

                        for row in rows:
                            status = row.get("status", "unknown")
                            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
                except (IOError, csv.Error):
                    continue

        # Compute evidence hash
        hashes = [compute_file_hash(f) for f in sorted(registry_files)]
        combined_hash = compute_content_hash("\n".join(hashes)) if hashes else ""

        evidence = EvidencePointer(
            source="registry",
            path=str(registries_dir),
            hash=combined_hash,
        )

        return stats, evidence

    # =========================================================================
    # Package Compliance Query API
    # =========================================================================

    def get_governance_chain(self) -> Tuple[Dict[str, Any], EvidencePointer]:
        """Get the governance chain requirements for package compliance.

        Returns:
            Tuple of (chain info dict, evidence pointer)
            Describes: Framework → Spec → Package → Files chain.
        """
        chain_info = {
            "overview": "Every package MUST be part of a governance chain",
            "chain": [
                {
                    "level": 1,
                    "name": "Framework",
                    "id_pattern": "FMWK-XXX",
                    "registry": "registries/frameworks_registry.csv",
                    "description": "Defines governance rules and invariants",
                },
                {
                    "level": 2,
                    "name": "Spec",
                    "id_pattern": "SPEC-XXX",
                    "registry": "registries/specs_registry.csv",
                    "references": "framework_id",
                    "description": "Defines assets and acceptance criteria",
                },
                {
                    "level": 3,
                    "name": "Package",
                    "id_pattern": "PKG-XXX",
                    "manifest": "manifest.json",
                    "references": "spec_id",
                    "description": "Contains files and installation metadata",
                },
                {
                    "level": 4,
                    "name": "Files",
                    "declaration": "manifest.json assets array",
                    "description": "Actual code/config files with SHA256 hashes",
                },
            ],
            "failure_consequence": "If any link is missing, G1 gate validation FAILS",
        }

        # Evidence from registries
        fw_registry = self.plane_root / "registries" / "frameworks_registry.csv"
        spec_registry = self.plane_root / "registries" / "specs_registry.csv"
        hashes = []
        if fw_registry.exists():
            hashes.append(compute_file_hash(fw_registry))
        if spec_registry.exists():
            hashes.append(compute_file_hash(spec_registry))

        evidence = EvidencePointer(
            source="registry",
            path=str(self.plane_root / "registries"),
            hash=compute_content_hash("\n".join(hashes)) if hashes else "",
        )

        return chain_info, evidence

    def get_gate_requirements(self) -> Tuple[Dict[str, Any], EvidencePointer]:
        """Get gate validation requirements for packages.

        Returns:
            Tuple of (gates info dict, evidence pointer)
            Describes all gates and their checks.
        """
        gates = {
            "MANIFEST": {
                "phase": "preflight",
                "description": "Basic manifest structure validation",
                "checks": [
                    "Valid JSON syntax",
                    "package_id present and matches filename",
                    "assets array present",
                ],
                "common_failures": [
                    "MANIFEST FAIL: Missing required field 'package_id'",
                    "MANIFEST FAIL: package_id mismatch",
                ],
            },
            "G0A": {
                "phase": "preflight",
                "description": "Package declaration consistency",
                "checks": [
                    "Every file in package declared in assets",
                    "Every declared file exists",
                    "All hashes match",
                    "No path escapes (../ or absolute paths)",
                ],
                "common_failures": [
                    "G0A FAIL: UNDECLARED: <file>",
                    "G0A FAIL: HASH_MISMATCH: <file>",
                    "G0A FAIL: PATH_ESCAPE: <path>",
                    "G0A FAIL: Invalid hash format",
                ],
            },
            "G1": {
                "phase": "preflight",
                "description": "Governance chain validation (CRITICAL)",
                "checks": [
                    "spec_id field present and non-empty",
                    "Spec exists in specs_registry.csv",
                    "Spec's framework_id exists in frameworks_registry.csv",
                    "All dependencies are valid PKG-IDs",
                ],
                "common_failures": [
                    "G1 FAIL: SPEC_MISSING: Package must have 'spec_id' field",
                    "G1 FAIL: SPEC_NOT_FOUND: <spec> not in specs_registry.csv",
                    "G1 FAIL: FRAMEWORK_NOT_FOUND: <framework> not found",
                    "G1 FAIL: INVALID_DEP: '<dep>' - must match PKG-[A-Z0-9-]+",
                ],
            },
            "OWN": {
                "phase": "preflight",
                "description": "File ownership validation",
                "checks": [
                    "No file already owned by another package",
                ],
                "common_failures": [
                    "OWN FAIL: OWNERSHIP_CONFLICT: <file> already owned by <pkg>",
                ],
            },
            "G5": {
                "phase": "install",
                "description": "Signature validation",
                "checks": [
                    "Package is signed OR CONTROL_PLANE_ALLOW_UNSIGNED=1 set",
                ],
                "common_failures": [
                    "G5 FAIL: SIGNATURE_MISSING: Package is not signed",
                ],
                "workaround": "export CONTROL_PLANE_ALLOW_UNSIGNED=1 (development only)",
            },
        }

        evidence = EvidencePointer(
            source="file",
            path=str(self.plane_root / "docs" / "PACKAGE_COMPLIANCE.md"),
            hash=compute_file_hash(self.plane_root / "docs" / "PACKAGE_COMPLIANCE.md"),
        )

        return {"gates": gates}, evidence

    def get_manifest_requirements(self) -> Tuple[Dict[str, Any], EvidencePointer]:
        """Get manifest.json field requirements.

        Returns:
            Tuple of (requirements dict, evidence pointer)
        """
        requirements = {
            "schema_version": "1.2",
            "required_fields": {
                "package_id": {
                    "format": "PKG-[A-Z0-9-]+",
                    "example": "PKG-MY-TOOL-001",
                },
                "schema_version": {
                    "format": '"1.2"',
                    "example": "1.2",
                },
                "version": {
                    "format": "Semver",
                    "example": "1.0.0",
                },
                "spec_id": {
                    "format": "SPEC-[A-Z0-9-]+",
                    "example": "SPEC-MY-001",
                    "note": "MUST reference registered spec",
                },
                "plane_id": {
                    "format": "ho1|ho2|ho3",
                    "example": "ho3",
                },
                "assets": {
                    "format": "Array of asset objects",
                    "note": "Each with path, sha256, classification",
                },
            },
            "optional_fields": {
                "package_type": {"example": "library"},
                "dependencies": {"format": "Array of PKG-IDs"},
                "metadata": {"example": '{"description": "..."}'},
            },
            "asset_object": {
                "path": "Relative path within package",
                "sha256": "sha256:<64 hex chars>",
                "classification": "library|script|test|config|schema|documentation|prompt|other",
            },
            "asset_classifications": {
                "library": {"use_for": "Python modules", "pattern": "lib/*.py"},
                "script": {"use_for": "CLI scripts", "pattern": "scripts/*.py"},
                "test": {"use_for": "Test files", "pattern": "tests/*.py"},
                "config": {"use_for": "Configuration", "pattern": "config/*.json, *.yaml"},
                "schema": {"use_for": "JSON schemas", "pattern": "schemas/*.json"},
                "documentation": {"use_for": "Docs", "pattern": "docs/*.md, README.md"},
                "prompt": {"use_for": "Agent prompts", "pattern": "prompts/*.md"},
                "other": {"use_for": "Everything else", "pattern": "-"},
            },
        }

        schema_path = self.plane_root / "schemas" / "package_manifest.json"
        evidence = EvidencePointer(
            source="file",
            path=str(schema_path),
            hash=compute_file_hash(schema_path) if schema_path.exists() else "",
        )

        return requirements, evidence

    def get_packaging_workflow(self) -> Tuple[Dict[str, Any], EvidencePointer]:
        """Get the complete packaging workflow steps.

        Returns:
            Tuple of (workflow dict, evidence pointer)
        """
        workflow = {
            "steps": [
                {
                    "step": 1,
                    "name": "Register Framework (if new)",
                    "command": "pkgutil register-framework FMWK-XXX --src frameworks/",
                    "result": "Entry in frameworks_registry.csv",
                    "skip_if": "Framework already registered",
                },
                {
                    "step": 2,
                    "name": "Register Spec (if new)",
                    "commands": [
                        "mkdir -p specs/SPEC-XXX",
                        "# Create specs/SPEC-XXX/manifest.yaml",
                        "pkgutil register-spec SPEC-XXX --src specs/SPEC-XXX",
                    ],
                    "result": "Entry in specs_registry.csv",
                    "skip_if": "Spec already registered",
                },
                {
                    "step": 3,
                    "name": "Create Package Skeleton",
                    "command": "pkgutil init PKG-XXX --spec SPEC-XXX --output _staging/",
                    "alt_command": "pkgutil init-agent PKG-XXX --framework FMWK-XXX --output _staging/",
                    "result": "_staging/PKG-XXX/ with manifest.json template",
                },
                {
                    "step": 4,
                    "name": "Implement",
                    "actions": [
                        "Add code files to package directory",
                        "Edit manifest.json to set spec_id",
                        "Hashes auto-computed by preflight/stage",
                    ],
                },
                {
                    "step": 5,
                    "name": "Preflight Validation",
                    "command": "pkgutil preflight PKG-XXX --src _staging/PKG-XXX",
                    "result": "PASS/FAIL with detailed gate results",
                },
                {
                    "step": 6,
                    "name": "Stage",
                    "command": "pkgutil stage PKG-XXX --src _staging/PKG-XXX",
                    "result": "_staging/PKG-XXX.tar.gz + .sha256 + .delta.csv",
                },
                {
                    "step": 7,
                    "name": "Install",
                    "command": "CONTROL_PLANE_ALLOW_UNSIGNED=1 package_install.py --archive _staging/PKG-XXX.tar.gz --id PKG-XXX",
                    "result": "Files installed, file_ownership.csv updated",
                },
            ],
            "pkgutil_commands": {
                "register-framework": "Register a framework in frameworks_registry.csv",
                "register-spec": "Register a spec in specs_registry.csv",
                "init": "Create standard package skeleton",
                "init-agent": "Create agent package skeleton",
                "preflight": "Validate package without installing",
                "stage": "Create installable .tar.gz bundle",
                "delta": "Generate reviewable registry delta",
                "check-framework": "Validate framework governance readiness",
            },
        }

        evidence = EvidencePointer(
            source="file",
            path=str(self.plane_root / "scripts" / "pkgutil.py"),
            hash=compute_file_hash(self.plane_root / "scripts" / "pkgutil.py"),
        )

        return workflow, evidence

    def list_available_frameworks(self) -> Tuple[List[Dict[str, str]], EvidencePointer]:
        """List all registered frameworks.

        Returns:
            Tuple of (frameworks list, evidence pointer)
        """
        frameworks = []
        registry_path = self.plane_root / "registries" / "frameworks_registry.csv"

        if registry_path.exists():
            try:
                with open(registry_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        frameworks.append({
                            "framework_id": row.get("framework_id", ""),
                            "title": row.get("title", ""),
                            "status": row.get("status", ""),
                            "version": row.get("version", ""),
                            "plane_id": row.get("plane_id", ""),
                        })
            except (IOError, csv.Error):
                pass

        evidence = EvidencePointer(
            source="registry",
            path=str(registry_path),
            hash=compute_file_hash(registry_path) if registry_path.exists() else "",
        )

        return frameworks, evidence

    def list_available_specs(self, framework_id: Optional[str] = None) -> Tuple[List[Dict[str, str]], EvidencePointer]:
        """List registered specs, optionally filtered by framework.

        Args:
            framework_id: Optional framework to filter by

        Returns:
            Tuple of (specs list, evidence pointer)
        """
        specs = []
        registry_path = self.plane_root / "registries" / "specs_registry.csv"

        if registry_path.exists():
            try:
                with open(registry_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if framework_id is None or row.get("framework_id") == framework_id:
                            specs.append({
                                "spec_id": row.get("spec_id", ""),
                                "title": row.get("title", ""),
                                "framework_id": row.get("framework_id", ""),
                                "status": row.get("status", ""),
                                "version": row.get("version", ""),
                                "plane_id": row.get("plane_id", ""),
                            })
            except (IOError, csv.Error):
                pass

        evidence = EvidencePointer(
            source="registry",
            path=str(registry_path),
            hash=compute_file_hash(registry_path) if registry_path.exists() else "",
        )

        return specs, evidence

    def get_spec_manifest(self, spec_id: str) -> Tuple[Optional[Dict[str, Any]], EvidencePointer]:
        """Get the manifest for a specific spec.

        Args:
            spec_id: Spec ID to look up

        Returns:
            Tuple of (manifest dict or None, evidence pointer)
        """
        import yaml

        manifest_path = self.plane_root / "specs" / spec_id / "manifest.yaml"

        if not manifest_path.exists():
            evidence = EvidencePointer(
                source="file",
                path=str(manifest_path),
                hash="",
            )
            return None, evidence

        try:
            content = manifest_path.read_text()
            manifest = yaml.safe_load(content)
            content_hash = compute_content_hash(content)
        except Exception:
            manifest = None
            content_hash = ""

        evidence = EvidencePointer(
            source="file",
            path=str(manifest_path),
            hash=content_hash,
        )

        return manifest, evidence

    def get_troubleshooting_guide(self, error_type: Optional[str] = None) -> Tuple[Dict[str, Any], EvidencePointer]:
        """Get troubleshooting guidance for common errors.

        Args:
            error_type: Optional error type to filter (G1, G0A, OWN, etc.)

        Returns:
            Tuple of (troubleshooting dict, evidence pointer)
        """
        guide = {
            "G1_SPEC_MISSING": {
                "symptom": "G1 FAIL: SPEC_MISSING",
                "cause": "Package manifest missing spec_id field",
                "fix": [
                    "Check spec_id in manifest.json: jq '.spec_id' manifest.json",
                    "Add spec_id field referencing registered spec",
                ],
            },
            "G1_SPEC_NOT_FOUND": {
                "symptom": "G1 FAIL: SPEC_NOT_FOUND",
                "cause": "spec_id references unregistered spec",
                "fix": [
                    "Check spec registration: grep SPEC-XXX registries/specs_registry.csv",
                    "Register spec: pkgutil register-spec SPEC-XXX --src specs/SPEC-XXX",
                ],
            },
            "G1_FRAMEWORK_NOT_FOUND": {
                "symptom": "G1 FAIL: FRAMEWORK_NOT_FOUND",
                "cause": "Spec references unregistered framework",
                "fix": [
                    "Check framework registration: grep FMWK-XXX registries/frameworks_registry.csv",
                    "Register framework: pkgutil register-framework FMWK-XXX --src frameworks/",
                ],
            },
            "G0A_UNDECLARED": {
                "symptom": "G0A FAIL: UNDECLARED: <file>",
                "cause": "File exists in package but not declared in assets",
                "fix": [
                    "Run preflight to auto-update: pkgutil preflight PKG-XXX --src <dir>",
                    "Or manually add file to assets array in manifest.json",
                ],
            },
            "G0A_HASH_MISMATCH": {
                "symptom": "G0A FAIL: HASH_MISMATCH",
                "cause": "File changed after hash was computed",
                "fix": [
                    "Re-run stage: pkgutil stage PKG-XXX --src <dir>",
                ],
            },
            "OWN_CONFLICT": {
                "symptom": "OWN FAIL: OWNERSHIP_CONFLICT",
                "cause": "File already owned by another package",
                "fix": [
                    "Remove file from your package, or",
                    "Uninstall conflicting package first",
                ],
            },
            "G5_UNSIGNED": {
                "symptom": "G5 FAIL: SIGNATURE_MISSING",
                "cause": "Package not signed (production requirement)",
                "fix": [
                    "For development: export CONTROL_PLANE_ALLOW_UNSIGNED=1",
                    "For production: sign package with authorized key",
                ],
            },
            "testing_without_chain": {
                "symptom": "Need to test package without full governance chain",
                "cause": "Development/testing scenario",
                "fix": [
                    "Use --no-strict flag: pkgutil preflight PKG-XXX --src <dir> --no-strict",
                    "Note: NOT for production use",
                ],
            },
        }

        if error_type:
            filtered = {k: v for k, v in guide.items() if error_type.upper() in k.upper()}
            guide = filtered if filtered else guide

        evidence = EvidencePointer(
            source="file",
            path=str(self.plane_root / "docs" / "PACKAGE_COMPLIANCE.md"),
            hash=compute_file_hash(self.plane_root / "docs" / "PACKAGE_COMPLIANCE.md"),
        )

        return {"troubleshooting": guide}, evidence

    def get_example_manifest(self, package_type: str = "library") -> Tuple[Dict[str, Any], EvidencePointer]:
        """Get an example manifest.json for a package type.

        Args:
            package_type: Type of package (library, agent, baseline)

        Returns:
            Tuple of (example manifest dict, evidence pointer)
        """
        if package_type == "agent":
            example = {
                "package_id": "PKG-MY-AGENT-001",
                "schema_version": "1.2",
                "version": "1.0.0",
                "spec_id": "SPEC-MY-AGENT-001",
                "plane_id": "ho3",
                "package_type": "agent",
                "capabilities": ["inspect", "explain", "list"],
                "assets": [
                    {
                        "path": "lib/agent_my.py",
                        "sha256": "sha256:<64 hex chars>",
                        "classification": "library",
                    },
                    {
                        "path": "prompts/system.md",
                        "sha256": "sha256:<64 hex chars>",
                        "classification": "prompt",
                    },
                    {
                        "path": "capabilities.yaml",
                        "sha256": "sha256:<64 hex chars>",
                        "classification": "config",
                    },
                ],
                "dependencies": [],
                "metadata": {
                    "description": "My agent package",
                },
            }
        else:
            example = {
                "package_id": "PKG-MY-LIBRARY-001",
                "schema_version": "1.2",
                "version": "1.0.0",
                "spec_id": "SPEC-MY-001",
                "plane_id": "ho3",
                "package_type": "library",
                "assets": [
                    {
                        "path": "lib/my_module.py",
                        "sha256": "sha256:<64 hex chars>",
                        "classification": "library",
                    },
                    {
                        "path": "tests/test_my_module.py",
                        "sha256": "sha256:<64 hex chars>",
                        "classification": "test",
                    },
                ],
                "dependencies": [],
                "metadata": {
                    "description": "My library package",
                },
            }

        # Get an actual example from installed packages
        example_path = self.plane_root / "installed" / "PKG-BASELINE-HO3-000" / "manifest.json"
        evidence = EvidencePointer(
            source="file",
            path=str(example_path),
            hash=compute_file_hash(example_path) if example_path.exists() else "",
        )

        return {"example": example, "note": "Replace <64 hex chars> with actual SHA256 hash"}, evidence

    def get_compliance_summary(self) -> Tuple[Dict[str, Any], EvidencePointer]:
        """Get a complete summary of package compliance requirements.

        Returns:
            Tuple of (summary dict, evidence pointer)
            Contains all key information an agent needs to build compliant packages.
        """
        chain, _ = self.get_governance_chain()
        gates, _ = self.get_gate_requirements()
        manifest, _ = self.get_manifest_requirements()
        workflow, _ = self.get_packaging_workflow()
        frameworks, _ = self.list_available_frameworks()
        specs, _ = self.list_available_specs()

        summary = {
            "governance_chain": chain,
            "gates": gates["gates"],
            "manifest_requirements": manifest,
            "workflow": workflow["steps"],
            "pkgutil_commands": workflow["pkgutil_commands"],
            "available_frameworks": frameworks,
            "available_specs": specs,
            "quick_reference": {
                "create_package": "pkgutil init PKG-XXX --spec SPEC-XXX --output _staging/",
                "validate": "pkgutil preflight PKG-XXX --src _staging/PKG-XXX",
                "stage": "pkgutil stage PKG-XXX --src _staging/PKG-XXX",
                "install": "CONTROL_PLANE_ALLOW_UNSIGNED=1 package_install.py --archive _staging/PKG-XXX.tar.gz --id PKG-XXX",
            },
        }

        # Combined evidence from multiple sources
        doc_path = self.plane_root / "docs" / "PACKAGE_COMPLIANCE.md"
        evidence = EvidencePointer(
            source="file",
            path=str(doc_path),
            hash=compute_file_hash(doc_path) if doc_path.exists() else "",
        )

        return summary, evidence
