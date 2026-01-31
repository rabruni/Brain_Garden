"""Package audit logging helper."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from lib.ledger_client import LedgerClient, LedgerEntry


@dataclass
class PackageContext:
    package_id: str
    action: str  # install|update|remove|pack
    before_hash: str = ""
    after_hash: str = ""
    frameworks_active: List[str] | None = None
    session_id: str = ""
    work_order: str = ""
    actor: str = ""
    external_path: Optional[str] = None
    in_registry: bool = True


def log_package_event(ctx: PackageContext) -> str:
    """Write package audit event to ledger; returns ledger entry id."""
    ledger = LedgerClient()
    entry = LedgerEntry(
        event_type=f"package_{ctx.action}",
        submission_id=ctx.package_id,
        decision=ctx.action.upper(),
        reason=f"package {ctx.action}: {ctx.package_id}",
        metadata={
            "package_id": ctx.package_id,
            "before_hash": ctx.before_hash,
            "after_hash": ctx.after_hash,
            "frameworks_active": ctx.frameworks_active or [],
            "session_id": ctx.session_id,
            "work_order": ctx.work_order,
            "actor": ctx.actor,
            "external_path": ctx.external_path,
            "in_registry": ctx.in_registry,
        },
    )
    return ledger.write(entry)

