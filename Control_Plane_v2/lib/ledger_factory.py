"""Ledger Factory for tier-agnostic ledger creation.

Provides factory methods for creating LedgerClient instances,
either with defaults (backward compatible) or from tier manifests.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from lib.ledger_client import LedgerClient
from lib.tier_manifest import TierManifest, TierType


# Default ledger names by tier
DEFAULT_LEDGER_NAMES = {
    "HOT": "governance.jsonl",
    "SECOND": "workorder.jsonl",
    "FIRST": "worker.jsonl",
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
    def from_manifest(manifest_path: Path) -> LedgerClient:
        """Create LedgerClient from a tier manifest.

        Args:
            manifest_path: Path to tier.json file

        Returns:
            LedgerClient configured for the tier's ledger

        Raises:
            FileNotFoundError: If manifest doesn't exist
        """
        manifest = TierManifest.load(manifest_path)
        return LedgerClient(ledger_path=manifest.absolute_ledger_path)

    @staticmethod
    def from_tier_root(tier_root: Path) -> LedgerClient:
        """Create LedgerClient from a tier root directory.

        Args:
            tier_root: Path to tier directory containing tier.json

        Returns:
            LedgerClient configured for the tier's ledger
        """
        return LedgerFactory.from_manifest(tier_root / "tier.json")

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

        # Determine ledger path
        name = ledger_name or DEFAULT_LEDGER_NAMES.get(tier, "ledger.jsonl")
        ledger_path = Path("ledger") / name

        # Create manifest
        manifest = TierManifest(
            tier=tier,
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

        # Create ledger client (creates ledger file and indexes)
        client = LedgerClient(ledger_path=manifest.absolute_ledger_path)

        return manifest, client

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
