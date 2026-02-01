"""Ledger Factory for tier-agnostic ledger creation.

Provides factory methods for creating LedgerClient instances,
either with defaults (backward compatible) or from tier manifests.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from lib.ledger_client import LedgerClient, TierContext
from lib.tier_manifest import TierManifest, TierType, migrate_tier_name


def _get_parent_hash(parent_ledger: str) -> Optional[str]:
    """Get the last entry hash from a parent ledger.

    Args:
        parent_ledger: Path to parent ledger file

    Returns:
        Hash of last entry, or None if ledger is empty or not found
    """
    try:
        parent_path = Path(parent_ledger)
        if not parent_path.exists():
            return None
        client = LedgerClient(ledger_path=parent_path)
        return client.get_last_entry_hash_value()
    except Exception:
        return None


# Default ledger names by tier (canonical names)
# HO3=highest (governance), HO2=middle (workorder), HO1=lowest (worker)
DEFAULT_LEDGER_NAMES = {
    "HO3": "governance.jsonl",
    "HO2": "workorder.jsonl",
    "HO1": "worker.jsonl",
}

# Legacy ledger name mapping for backward compatibility
# FIRST -> HO1 (lowest, worker), SECOND -> HO2 (middle, workorder)
LEGACY_LEDGER_NAMES = {
    "HOT": "governance.jsonl",
    "SECOND": "workorder.jsonl",   # SECOND -> HO2 (middle)
    "FIRST": "worker.jsonl",       # FIRST -> HO1 (lowest)
}


class LedgerFactory:
    """Factory for creating LedgerClient instances with tier support."""

    @staticmethod
    def default() -> LedgerClient:
        """Create default LedgerClient (backward compatible).

        Returns:
            LedgerClient pointing to ledger/governance.jsonl
        """
        return LedgerClient()

    @staticmethod
    def from_manifest(manifest_path: Path, with_tier_context: bool = True) -> LedgerClient:
        """Create LedgerClient from a tier manifest.

        Args:
            manifest_path: Path to tier.json file
            with_tier_context: If True, attach TierContext for entry stamping

        Returns:
            LedgerClient configured for the tier's ledger

        Raises:
            FileNotFoundError: If manifest doesn't exist
        """
        manifest = TierManifest.load(manifest_path)

        tier_context = None
        if with_tier_context:
            tier_context = TierContext(
                tier=manifest.tier,
                plane_root=manifest.tier_root,
                work_order_id=manifest.work_order_id,
                session_id=manifest.session_id,
            )

        return LedgerClient(
            ledger_path=manifest.absolute_ledger_path,
            tier_context=tier_context,
        )

    @staticmethod
    def from_tier_root(tier_root: Path, with_tier_context: bool = True) -> LedgerClient:
        """Create LedgerClient from a tier root directory.

        Args:
            tier_root: Path to tier directory containing tier.json
            with_tier_context: If True, attach TierContext for entry stamping

        Returns:
            LedgerClient configured for the tier's ledger
        """
        return LedgerFactory.from_manifest(tier_root / "tier.json", with_tier_context=with_tier_context)

    @staticmethod
    def create_tier(
        tier: TierType,
        tier_root: Path,
        work_order_id: Optional[str] = None,
        session_id: Optional[str] = None,
        parent_ledger: Optional[str] = None,
        ledger_name: Optional[str] = None,
    ) -> Tuple[TierManifest, LedgerClient]:
        """Initialize a new tier with manifest and ledger.

        Creates:
        - tier_root/ directory
        - tier_root/tier.json manifest
        - tier_root/ledger/<name>.jsonl ledger file

        Args:
            tier: Tier type (HOT, SECOND, FIRST)
            tier_root: Directory for this tier
            work_order_id: Work order ID (for SECOND tier)
            session_id: Session ID (for FIRST tier)
            parent_ledger: Path/URI to parent tier's ledger
            ledger_name: Custom ledger filename (defaults per tier)

        Returns:
            Tuple of (TierManifest, LedgerClient)

        Raises:
            ValueError: If tier_root already has a tier.json
        """
        tier_root = tier_root.resolve()

        # Check for existing manifest
        manifest_path = tier_root / "tier.json"
        if manifest_path.exists():
            raise ValueError(f"Tier already exists at {tier_root}")

        # Migrate legacy tier name to canonical
        canonical_tier = migrate_tier_name(tier)

        # Determine ledger path (check canonical names first, then legacy)
        name = ledger_name or DEFAULT_LEDGER_NAMES.get(canonical_tier) or LEGACY_LEDGER_NAMES.get(tier, "ledger.jsonl")
        ledger_path = Path("ledger") / name

        # Create manifest with canonical tier name
        manifest = TierManifest(
            tier=canonical_tier,
            tier_root=tier_root,
            ledger_path=ledger_path,
            parent_ledger=parent_ledger,
            work_order_id=work_order_id,
            session_id=session_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            status="active",
        )

        # Save manifest (creates tier_root if needed)
        manifest.save()

        # Create tier context for entry stamping
        tier_context = TierContext(
            tier=canonical_tier,
            plane_root=tier_root,
            work_order_id=work_order_id,
            session_id=session_id,
        )

        # Create ledger client (creates ledger file and indexes)
        client = LedgerClient(
            ledger_path=manifest.absolute_ledger_path,
            tier_context=tier_context,
        )

        # Get parent hash for cross-chain linking
        parent_hash = None
        if parent_ledger:
            parent_hash = _get_parent_hash(parent_ledger)

        # Write GENESIS entry as first entry
        client.write_genesis(
            tier=canonical_tier,
            plane_root=tier_root,
            parent_ledger=parent_ledger,
            parent_hash=parent_hash,
            work_order_id=work_order_id,
            session_id=session_id,
        )
        client.flush()

        return manifest, client

    @staticmethod
    def create_work_order_instance(
        base_root: Path,
        work_order_id: str,
    ) -> Tuple[TierManifest, LedgerClient]:
        """Create a work-order instance under an HO2 base plane.

        Creates a subdirectory under base_root/work_orders/{work_order_id}/
        with its own tier.json and ledger linked to the parent HO2 ledger.

        Args:
            base_root: Path to base HO2 plane root
            work_order_id: Work order ID (e.g., "WO-2026-001")

        Returns:
            Tuple of (TierManifest, LedgerClient) for the new instance

        Raises:
            ValueError: If base is not HO2 or work order already exists
        """
        base_root = base_root.resolve()
        base_manifest = TierManifest.load(base_root / "tier.json")

        if base_manifest.tier != "HO2":
            raise ValueError(f"Base must be HO2 plane, got {base_manifest.tier}")

        instance_root = base_root / "work_orders" / work_order_id
        if (instance_root / "tier.json").exists():
            raise ValueError(f"Work order already exists: {work_order_id}")

        # Parent ledger is relative path to base HO2 ledger
        parent_ledger = f"../../ledger/{base_manifest.ledger_path.name}"

        return LedgerFactory.create_tier(
            tier="HO2",
            tier_root=instance_root,
            work_order_id=work_order_id,
            parent_ledger=parent_ledger,
        )

    @staticmethod
    def create_session_instance(
        base_root: Path,
        session_id: str,
    ) -> Tuple[TierManifest, LedgerClient]:
        """Create a session instance under an HO1 base plane.

        Creates a subdirectory under base_root/sessions/{session_id}/
        with its own tier.json and ledger linked to the parent HO1 ledger.

        Args:
            base_root: Path to base HO1 plane root
            session_id: Session ID (e.g., "sess-001")

        Returns:
            Tuple of (TierManifest, LedgerClient) for the new instance

        Raises:
            ValueError: If base is not HO1 or session already exists
        """
        base_root = base_root.resolve()
        base_manifest = TierManifest.load(base_root / "tier.json")

        if base_manifest.tier != "HO1":
            raise ValueError(f"Base must be HO1 plane, got {base_manifest.tier}")

        instance_root = base_root / "sessions" / session_id
        if (instance_root / "tier.json").exists():
            raise ValueError(f"Session already exists: {session_id}")

        # Parent ledger is relative path to base HO1 ledger
        parent_ledger = f"../../ledger/{base_manifest.ledger_path.name}"

        return LedgerFactory.create_tier(
            tier="HO1",
            tier_root=instance_root,
            session_id=session_id,
            parent_ledger=parent_ledger,
        )

    @staticmethod
    def list_instances(base_root: Path) -> List[TierManifest]:
        """List all instances under a base plane.

        Returns instances in stable order (sorted by tier_root path).

        Args:
            base_root: Path to base plane root

        Returns:
            List of TierManifest for each instance (work_orders or sessions),
            sorted by tier_root path for deterministic ordering
        """
        base_root = base_root.resolve()
        instances = []

        # Check work_orders directory (HO2)
        work_orders_dir = base_root / "work_orders"
        if work_orders_dir.exists():
            # Sort by directory name for stable ordering
            for instance_dir in sorted(work_orders_dir.iterdir(), key=lambda p: p.name):
                manifest_path = instance_dir / "tier.json"
                if manifest_path.exists():
                    try:
                        instances.append(TierManifest.load(manifest_path))
                    except Exception:
                        pass

        # Check sessions directory (HO1)
        sessions_dir = base_root / "sessions"
        if sessions_dir.exists():
            # Sort by directory name for stable ordering
            for instance_dir in sorted(sessions_dir.iterdir(), key=lambda p: p.name):
                manifest_path = instance_dir / "tier.json"
                if manifest_path.exists():
                    try:
                        instances.append(TierManifest.load(manifest_path))
                    except Exception:
                        pass

        return instances

    @staticmethod
    def archive(manifest_path: Path) -> TierManifest:
        """Archive a tier (mark as read-only).

        Args:
            manifest_path: Path to tier.json

        Returns:
            Updated TierManifest with status='archived'
        """
        manifest = TierManifest.load(manifest_path)
        manifest.archive()
        return manifest

    @staticmethod
    def close(manifest_path: Path) -> TierManifest:
        """Close a tier (mark as permanently closed).

        Args:
            manifest_path: Path to tier.json

        Returns:
            Updated TierManifest with status='closed'
        """
        manifest = TierManifest.load(manifest_path)
        manifest.close()
        return manifest

    @staticmethod
    def list_tiers(root: Path) -> List[TierManifest]:
        """Discover all tiers under a root directory.

        Args:
            root: Directory to search recursively

        Returns:
            List of TierManifest instances found
        """
        return TierManifest.discover(root)

    @staticmethod
    def get_tier_for_path(path: Path) -> Optional[TierManifest]:
        """Find which tier a path belongs to.

        Args:
            path: Path to check

        Returns:
            TierManifest if path is within a tier, None otherwise
        """
        return TierManifest.find_for_path(path)
