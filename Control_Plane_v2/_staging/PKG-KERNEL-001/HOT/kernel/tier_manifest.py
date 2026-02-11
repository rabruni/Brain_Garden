"""Tier Manifest for multi-tier ledger support.

Defines the TierManifest dataclass that declares tier configuration
for HOT/HO2/HO1 tier replicas, enabling tier-agnostic ledger capability.

Each tier root directory contains a tier.json manifest file.

Canonical naming:
- HOT: Executive tier (highest privilege)
- HO2 (Higher Order 2): Middle tier
- HO1 (Higher Order 1): Lowest tier
"""

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Literal


# Canonical tier names
TierType = Literal["HOT", "HO2", "HO1"]
TierStatus = Literal["active", "archived", "closed"]

# Migration mapping from legacy names to canonical names
# FIRST -> HO1 (lowest), SECOND -> HO2 (middle)
TIER_MIGRATION = {
    "SECOND": "HO2",
    "FIRST": "HO1",
    "FIRST_ORDER": "HO1",
    "SECOND_ORDER": "HO2",
}

# Reverse mapping for backward compatibility output
TIER_LEGACY_NAMES = {
    "HOT": "HOT",
    "HO2": "SECOND",
    "HO1": "FIRST",
}


def migrate_tier_name(tier: str) -> str:
    """Migrate a tier name from legacy to canonical form.

    Args:
        tier: Tier name (legacy or canonical)

    Returns:
        Canonical tier name (HOT, HO2, or HO1)
    """
    return TIER_MIGRATION.get(tier, tier)


@dataclass
class TierManifest:
    """Manifest declaring tier configuration.

    Attributes:
        tier: Tier level (HOT, HO2, or HO1)
        tier_root: Absolute path to tier directory
        ledger_path: Path to ledger file, relative to tier_root
        parent_ledger: Path/URI to parent tier's ledger (None for HOT)
        work_order_id: Work order ID (for SECOND tier)
        session_id: Session ID (for FIRST tier)
        created_at: ISO timestamp when tier was created
        status: Current status (active, archived, closed)
    """

    tier: TierType
    tier_root: Path
    ledger_path: Path
    parent_ledger: Optional[str] = None
    work_order_id: Optional[str] = None
    session_id: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: TierStatus = "active"

    def __post_init__(self):
        """Normalize paths to Path objects."""
        if isinstance(self.tier_root, str):
            self.tier_root = Path(self.tier_root)
        if isinstance(self.ledger_path, str):
            self.ledger_path = Path(self.ledger_path)

    @property
    def manifest_path(self) -> Path:
        """Path to tier.json file."""
        return self.tier_root / "tier.json"

    @property
    def absolute_ledger_path(self) -> Path:
        """Absolute path to ledger file."""
        return self.tier_root / self.ledger_path

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "tier": self.tier,
            "tier_root": str(self.tier_root),
            "ledger_path": str(self.ledger_path),
            "parent_ledger": self.parent_ledger,
            "work_order_id": self.work_order_id,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "status": self.status,
        }

    def save(self) -> None:
        """Save manifest to tier.json in tier_root."""
        self.tier_root.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
            f.write("\n")

    def archive(self) -> None:
        """Mark tier as archived and save."""
        self.status = "archived"
        self.save()

    def close(self) -> None:
        """Mark tier as closed and save."""
        self.status = "closed"
        self.save()

    @classmethod
    def load(cls, path: Path) -> "TierManifest":
        """Load manifest from tier.json file.

        Args:
            path: Path to tier.json file

        Returns:
            TierManifest instance

        Raises:
            FileNotFoundError: If tier.json doesn't exist
            ValueError: If tier.json is invalid

        Note:
            Legacy tier names (HOT, SECOND, FIRST) are automatically
            migrated to canonical names (HOT, HO2, HO1).
        """
        if not path.exists():
            raise FileNotFoundError(f"Tier manifest not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Migrate legacy tier name to canonical
        tier = migrate_tier_name(data["tier"])

        return cls(
            tier=tier,
            tier_root=Path(data["tier_root"]),
            ledger_path=Path(data["ledger_path"]),
            parent_ledger=data.get("parent_ledger"),
            work_order_id=data.get("work_order_id"),
            session_id=data.get("session_id"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            status=data.get("status", "active"),
        )

    @classmethod
    def discover(cls, search_root: Path) -> list["TierManifest"]:
        """Discover all tier manifests under a root directory.

        Args:
            search_root: Directory to search recursively

        Returns:
            List of TierManifest instances found
        """
        manifests = []
        for manifest_path in search_root.rglob("tier.json"):
            try:
                manifests.append(cls.load(manifest_path))
            except (json.JSONDecodeError, KeyError, ValueError):
                # Skip invalid manifests
                continue
        return manifests

    @classmethod
    def find_for_path(cls, path: Path) -> Optional["TierManifest"]:
        """Find tier manifest for a given path by walking up.

        Args:
            path: Path to find tier for

        Returns:
            TierManifest if found, None otherwise
        """
        path = path.resolve()
        for parent in [path] + list(path.parents):
            manifest_path = parent / "tier.json"
            if manifest_path.exists():
                try:
                    return cls.load(manifest_path)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
        return None
