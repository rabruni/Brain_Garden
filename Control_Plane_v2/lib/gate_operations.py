"""Gate Operations - CREATE, INSTALL, UPDATE, REMOVE operations for Control Plane.

All artifact lifecycle operations go through this single gate.
Each operation: PROPOSE → VALIDATE → APPLY → LOG

Per SPEC-025: Gate System for artifact lifecycle management.
"""
import csv
import json
import os
import shutil
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Literal
from datetime import datetime, timezone

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.merkle import hash_file, merkle_root
from lib.ledger_client import LedgerClient, LedgerEntry
from lib.integrity import IntegrityChecker
from lib.auth import get_provider, Identity
from lib import authz
from lib.pristine import assert_write_allowed, WriteViolation


@dataclass
class GateResult:
    """Result of a gate operation."""
    success: bool
    operation: str  # create, install, update, remove, validate
    artifact_id: Optional[str]
    message: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ledger_entry_id: Optional[str] = None
    new_merkle_root: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ArtifactProposal:
    """Proposal for creating or installing an artifact."""
    entity_type: str  # framework, orchestration, lib, script, etc.
    name: str
    artifact_path: str  # relative to Control Plane root
    source: str = "internal"  # "internal" or URL for imports
    content: Optional[str] = None  # file content for create
    dependencies: list[str] = field(default_factory=list)
    category: str = ""
    purpose: str = ""
    version: str = "1.0.0"
    config: Optional[dict] = None


class GateOperations:
    """
    Single entry point for all Control Plane artifact operations.

    Usage:
        gate = GateOperations()

        # Create new artifact
        result = gate.create(ArtifactProposal(
            entity_type="lib",
            name="My Library",
            artifact_path="/lib/my_lib.py",
            content="# My library code..."
        ))

        # Validate system integrity
        result = gate.validate()

        if result.success:
            print(f"Merkle root: {result.new_merkle_root}")
    """

    # ID prefixes by entity type
    ID_PREFIXES = {
        "framework": "FMWK",
        "orchestration": "ORCH",
        "module": "MOD",
        "prompt": "PROMPT",
        "script": "SCRIPT",
        "spec": "SPEC",
        "registry": "REG",
        "workflow": "WF",
        "agent": "AGENT",
        "lib": "LIB",
        "test": "TEST",
        "doc": "DOC",
        "schema": "SCHEMA",
    }

    def __init__(self, control_plane_root: Path = None, token: Optional[str] = None):
        if control_plane_root is None:
            control_plane_root = Path(__file__).resolve().parent.parent
        self.root = control_plane_root
        self.registry_path = self.root / "registries" / "control_plane_registry.csv"
        self.manifest_path = self.root / "MANIFEST.json"
        self.ledger = LedgerClient()
        self.integrity = IntegrityChecker(control_plane_root)
        self.auth_provider = get_provider()
        self.identity: Optional[Identity] = self.auth_provider.authenticate(token or self._env_token())

    def _env_token(self) -> Optional[str]:
        return os.getenv("CONTROL_PLANE_TOKEN")

    def _require(self, action: str):
        authz.require(self.identity, action)

    # ========== CREATE ==========

    def create(self, proposal: ArtifactProposal) -> GateResult:
        """
        Create a new internal artifact.

        Steps:
        1. Validate proposal
        2. Allocate ID
        3. Write file
        4. Add to registry
        5. Log to ledger
        6. Update merkle root
        """
        self._require("create")
        errors = []
        warnings = []

        # Step 1: Validate
        validation_errors = self._validate_create_proposal(proposal)
        if validation_errors:
            return GateResult(
                success=False,
                operation="create",
                artifact_id=None,
                message="Validation failed",
                errors=validation_errors,
            )

        # Step 2: Allocate ID
        artifact_id = self._allocate_id(proposal.entity_type)

        # Step 3: Write file
        artifact_path = proposal.artifact_path
        if artifact_path.startswith("/"):
            artifact_path = artifact_path[1:]
        full_path = self.root / artifact_path

        # Enforce pristine boundary (mode determined by caller context)
        try:
            assert_write_allowed(full_path, log_violation=True)
        except WriteViolation as e:
            return GateResult(success=False, operation="create", artifact_id=None,
                              message=str(e), errors=[str(e)], warnings=[],
                              ledger_entry_id=None, new_merkle_root=None)

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            if proposal.content:
                with open(full_path, "w") as f:
                    f.write(proposal.content)
            else:
                # Create empty file or directory marker
                full_path.touch()
        except IOError as e:
            return GateResult(
                success=False,
                operation="create",
                artifact_id=artifact_id,
                message=f"Failed to write file: {e}",
                errors=[str(e)],
            )

        # Step 4: Compute hash and add to registry
        content_hash = self.integrity.compute_file_hash(full_path)
        self._add_to_registry(
            artifact_id=artifact_id,
            name=proposal.name,
            entity_type=proposal.entity_type,
            artifact_path="/" + artifact_path,
            content_hash=content_hash,
            source=proposal.source,
            dependencies=proposal.dependencies,
            category=proposal.category,
            purpose=proposal.purpose,
            version=proposal.version,
            config=proposal.config,
        )

        # Step 5: Log to ledger
        ledger_entry = LedgerEntry(
            event_type="artifact_created",
            submission_id=artifact_id,
            decision="CREATED",
            reason=f"Created {proposal.entity_type}: {proposal.name}",
            metadata={
                "artifact_id": artifact_id,
                "entity_type": proposal.entity_type,
                "artifact_path": artifact_path,
                "content_hash": content_hash,
                "source": proposal.source,
            }
        )
        ledger_id = self.ledger.write(ledger_entry)

        # Step 6: Update merkle root
        new_root = self._update_merkle_root()

        return GateResult(
            success=True,
            operation="create",
            artifact_id=artifact_id,
            message=f"Created {artifact_id}: {proposal.name}",
            ledger_entry_id=ledger_id,
            new_merkle_root=new_root,
            warnings=warnings,
        )

    # ========== INSTALL ==========

    def install(self, proposal: ArtifactProposal) -> GateResult:
        """
        Install an external artifact (import from URL/source).

        Similar to create, but marks source as external.
        """
        self._require("install")
        # For now, install is like create with external source
        if proposal.source == "internal":
            proposal.source = "external"

        return self.create(proposal)

    # ========== UPDATE ==========

    def update(
        self,
        artifact_id: str,
        content: Optional[str] = None,
        name: Optional[str] = None,
        status: Optional[str] = None,
        version: Optional[str] = None,
    ) -> GateResult:
        """
        Update an existing artifact.

        Steps:
        1. Find artifact in registry
        2. Validate changes
        3. Apply changes
        4. Update hash in registry
        5. Log to ledger
        6. Update merkle root
        """
        self._require("update")
        # Step 1: Find artifact
        item = self._find_in_registry(artifact_id)
        if not item:
            return GateResult(
                success=False,
                operation="update",
                artifact_id=artifact_id,
                message=f"Artifact not found: {artifact_id}",
                errors=[f"No artifact with ID {artifact_id}"],
            )

        old_hash = item.get("content_hash", "")
        artifact_path = item.get("artifact_path", "")
        if artifact_path.startswith("/"):
            artifact_path = artifact_path[1:]
        full_path = self.root / artifact_path

        # Enforce pristine boundary (mode determined by caller context)
        try:
            assert_write_allowed(full_path, log_violation=True)
        except WriteViolation as e:
            return GateResult(success=False, operation="update", artifact_id=artifact_id,
                              message=str(e), errors=[str(e)], warnings=[],
                              ledger_entry_id=None, new_merkle_root=None)

        # Step 2 & 3: Apply content changes
        if content is not None:
            try:
                with open(full_path, "w") as f:
                    f.write(content)
            except IOError as e:
                return GateResult(
                    success=False,
                    operation="update",
                    artifact_id=artifact_id,
                    message=f"Failed to write file: {e}",
                    errors=[str(e)],
                )

        # Step 4: Update registry
        new_hash = self.integrity.compute_file_hash(full_path)
        updates = {"content_hash": new_hash}
        if name:
            updates["name"] = name
        if status:
            updates["status"] = status
        if version:
            updates["version"] = version

        self._update_registry_row(artifact_id, updates)

        # Step 5: Log to ledger
        ledger_entry = LedgerEntry(
            event_type="artifact_updated",
            submission_id=artifact_id,
            decision="UPDATED",
            reason=f"Updated {artifact_id}",
            metadata={
                "artifact_id": artifact_id,
                "old_hash": old_hash,
                "new_hash": new_hash,
                "fields_updated": list(updates.keys()),
            }
        )
        ledger_id = self.ledger.write(ledger_entry)

        # Step 6: Update merkle root
        new_root = self._update_merkle_root()

        return GateResult(
            success=True,
            operation="update",
            artifact_id=artifact_id,
            message=f"Updated {artifact_id}",
            ledger_entry_id=ledger_id,
            new_merkle_root=new_root,
        )

    # ========== REMOVE ==========

    def remove(
        self,
        artifact_id: str,
        mode: Literal["deprecate", "delete"] = "deprecate",
        force: bool = False,
    ) -> GateResult:
        """
        Remove an artifact.

        Modes:
        - deprecate: Set status to deprecated, keep files
        - delete: Remove files and registry row

        Args:
            artifact_id: ID of artifact to remove
            mode: "deprecate" (soft) or "delete" (hard)
            force: Skip dependency check
        """
        self._require("remove")
        # Step 1: Find artifact
        item = self._find_in_registry(artifact_id)
        if not item:
            return GateResult(
                success=False,
                operation="remove",
                artifact_id=artifact_id,
                message=f"Artifact not found: {artifact_id}",
                errors=[f"No artifact with ID {artifact_id}"],
            )

        # Step 2: Check dependents
        if not force:
            dependents = self._find_dependents(artifact_id)
            if dependents:
                return GateResult(
                    success=False,
                    operation="remove",
                    artifact_id=artifact_id,
                    message=f"Artifact has dependents: {dependents}",
                    errors=[f"Cannot remove: {len(dependents)} artifacts depend on this"],
                    warnings=[f"Dependents: {', '.join(dependents)}"],
                )

        artifact_path = item.get("artifact_path", "")
        if artifact_path.startswith("/"):
            artifact_path = artifact_path[1:]

        # Step 3: Apply removal
        if mode == "deprecate":
            self._update_registry_row(artifact_id, {"status": "deprecated"})
            action = "DEPRECATED"
        else:
            # Delete file
            full_path = self.root / artifact_path

            # Enforce pristine boundary (mode determined by caller context)
            try:
                assert_write_allowed(full_path, log_violation=True)
            except WriteViolation as e:
                return GateResult(success=False, operation="remove", artifact_id=artifact_id,
                                  message=str(e), errors=[str(e)], warnings=[],
                                  ledger_entry_id=None, new_merkle_root=None)
            if full_path.exists():
                if full_path.is_dir():
                    shutil.rmtree(full_path)
                else:
                    full_path.unlink()

            # Remove from registry
            self._remove_from_registry(artifact_id)
            action = "DELETED"

        # Step 4: Log to ledger
        ledger_entry = LedgerEntry(
            event_type="artifact_removed",
            submission_id=artifact_id,
            decision=action,
            reason=f"{action} {artifact_id}",
            metadata={
                "artifact_id": artifact_id,
                "mode": mode,
                "artifact_path": artifact_path,
            }
        )
        ledger_id = self.ledger.write(ledger_entry)

        # Step 5: Update merkle root
        new_root = self._update_merkle_root()

        return GateResult(
            success=True,
            operation="remove",
            artifact_id=artifact_id,
            message=f"{action} {artifact_id}",
            ledger_entry_id=ledger_id,
            new_merkle_root=new_root,
        )

    # ========== VALIDATE ==========

    def validate(self) -> GateResult:
        """
        Run full integrity validation.
        """
        result = self.integrity.validate()

        errors = [f"{i.check}: {i.message} ({i.path or i.artifact_id})"
                  for i in result.issues if i.severity == "error"]
        warnings = [f"{i.check}: {i.message} ({i.path or i.artifact_id})"
                    for i in result.issues if i.severity == "warning"]

        return GateResult(
            success=result.passed,
            operation="validate",
            artifact_id=None,
            message="Validation passed" if result.passed else f"Validation failed: {len(errors)} errors",
            errors=errors,
            warnings=warnings,
            new_merkle_root=result.computed_merkle_root,
        )

    # ========== HELPERS ==========

    def _validate_create_proposal(self, proposal: ArtifactProposal) -> list[str]:
        """Validate a create proposal."""
        errors = []

        # Check entity type
        if proposal.entity_type not in self.ID_PREFIXES:
            errors.append(f"Unknown entity type: {proposal.entity_type}")

        # Check name
        if not proposal.name or len(proposal.name) < 2:
            errors.append("Name is required and must be at least 2 characters")

        # Check path
        if not proposal.artifact_path:
            errors.append("Artifact path is required")
        else:
            path = proposal.artifact_path
            if path.startswith("/"):
                path = path[1:]
            full_path = self.root / path
            if full_path.exists():
                errors.append(f"Path already exists: {proposal.artifact_path}")

        # Check dependencies exist
        for dep in proposal.dependencies:
            if not self._find_in_registry(dep):
                errors.append(f"Dependency not found: {dep}")

        return errors

    def _allocate_id(self, entity_type: str) -> str:
        """Allocate next ID for entity type."""
        prefix = self.ID_PREFIXES.get(entity_type, "ITEM")

        # Find max existing ID
        max_num = 0
        registry_items = self._load_registry()
        for item in registry_items:
            item_id = item.get("id", "")
            if item_id.startswith(prefix + "-"):
                try:
                    num = int(item_id.split("-")[1])
                    max_num = max(max_num, num)
                except (IndexError, ValueError):
                    pass

        return f"{prefix}-{max_num + 1:03d}"

    def _load_registry(self) -> list[dict]:
        """Load registry as list of dicts."""
        if not self.registry_path.exists():
            return []

        items = []
        with open(self.registry_path, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                items.append(row)
        return items

    def _find_in_registry(self, artifact_id: str) -> Optional[dict]:
        """Find artifact by ID."""
        for item in self._load_registry():
            if item.get("id") == artifact_id:
                return item
        return None

    def _find_dependents(self, artifact_id: str) -> list[str]:
        """Find artifacts that depend on this one."""
        dependents = []
        for item in self._load_registry():
            deps = item.get("dependencies", "")
            if artifact_id in deps:
                dependents.append(item.get("id", ""))
        return dependents

    def _add_to_registry(
        self,
        artifact_id: str,
        name: str,
        entity_type: str,
        artifact_path: str,
        content_hash: str,
        source: str = "internal",
        dependencies: list[str] = None,
        category: str = "",
        purpose: str = "",
        version: str = "1.0.0",
        config: dict = None,
    ):
        """Add new row to registry."""
        items = self._load_registry()

        new_row = {
            "id": artifact_id,
            "name": name,
            "entity_type": entity_type,
            "category": category,
            "purpose": purpose,
            "artifact_path": artifact_path,
            "status": "active",
            "selected": "yes",
            "priority": "P0",
            "dependencies": ",".join(dependencies or []),
            "version": version,
            "owner": "claude",
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "source_spec_id": "",
            "content_hash": content_hash,
            "config": json.dumps(config) if config else "",
        }

        items.append(new_row)
        self._write_registry(items)

    def _update_registry_row(self, artifact_id: str, updates: dict):
        """Update specific fields in a registry row."""
        items = self._load_registry()

        for item in items:
            if item.get("id") == artifact_id:
                item.update(updates)
                break

        self._write_registry(items)

    def _remove_from_registry(self, artifact_id: str):
        """Remove row from registry."""
        items = self._load_registry()
        items = [i for i in items if i.get("id") != artifact_id]
        self._write_registry(items)

    def _write_registry(self, items: list[dict]):
        """Write registry back to disk."""
        if not items:
            return

        assert_write_allowed(self.registry_path, log_violation=True)

        fieldnames = list(items[0].keys())
        with open(self.registry_path, "w", newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(items)

    def _update_merkle_root(self) -> str:
        """Compute and store new merkle root in manifest."""
        # Collect all hashes
        hashes = []
        for item in self._load_registry():
            content_hash = item.get("content_hash", "")
            if content_hash:
                hashes.append(content_hash)

        hashes.sort()
        new_root = merkle_root(hashes) if hashes else ""

        # Update manifest
        manifest = {}
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path) as f:
                    manifest = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        manifest["merkle_root"] = new_root
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        manifest["artifact_count"] = len(hashes)

        assert_write_allowed(self.manifest_path, log_violation=True)

        with open(self.manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        return new_root


# Convenience functions
def create_artifact(proposal: ArtifactProposal) -> GateResult:
    """Create a new artifact through the gate."""
    return GateOperations().create(proposal)


def validate_system() -> GateResult:
    """Validate system integrity."""
    return GateOperations().validate()
