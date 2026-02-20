"""Derived projection snapshot writer for Context Authority."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from kernel.ledger_client import LedgerClient, LedgerEntry

from liveness import LivenessState


def write_projection(
    liveness: LivenessState,
    session_id: str,
    turn_id: str,
    token_budget: int,
    overlay_ledger: LedgerClient,
) -> Dict[str, Any]:
    """Write a PROJECTION_COMPUTED snapshot to the overlay ledger."""
    active_intents = [
        {
            "intent_id": intent_id,
            "objective": liveness.intents.get(intent_id, {}).get("objective", ""),
            "scope": liveness.intents.get(intent_id, {}).get("scope", "session"),
        }
        for intent_id in liveness.active_intents
    ]
    open_work_orders = [
        {
            "wo_id": wo_id,
            "wo_type": liveness.work_orders.get(wo_id, {}).get("wo_type", ""),
            "intent_id": liveness.work_orders.get(wo_id, {}).get("intent_id"),
        }
        for wo_id in liveness.open_work_orders
    ]

    metadata = {
        "session_id": session_id,
        "turn_id": turn_id,
        "token_budget": int(token_budget),
        "active_intents": active_intents,
        "open_work_orders": open_work_orders,
        "failed_items": list(liveness.failed_items),
        "escalations": list(liveness.escalations),
        "intent_count": len(active_intents),
        "open_wo_count": len(open_work_orders),
        "failed_count": len(liveness.failed_items),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    overlay_ledger.write(
        LedgerEntry(
            event_type="PROJECTION_COMPUTED",
            submission_id=session_id,
            decision="COMPUTED",
            reason=f"Liveness projection computed for {turn_id}",
            metadata=metadata,
        )
    )
    return metadata

