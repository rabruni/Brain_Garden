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
