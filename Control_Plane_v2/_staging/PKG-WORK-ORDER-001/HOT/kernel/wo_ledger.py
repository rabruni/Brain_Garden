"""WO-specific ledger entry helper.

Creates properly structured LedgerEntry instances for each WO lifecycle event.
Every entry includes metadata.relational fields per FMWK-008 Section 5b.

Usage:
    from kernel.wo_ledger import WOLedgerHelper

    helper = WOLedgerHelper(ledger_client)
    entry_id = helper.write_wo_planned(work_order, root_event_id=None)
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add own HOT/ to path (works when installed)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# Add PKG-KERNEL-001/HOT/kernel to path (works in staging)
_staging = Path(__file__).resolve().parents[3]
_kernel_dir = _staging / "PKG-KERNEL-001" / "HOT" / "kernel"
if _kernel_dir.exists():
    sys.path.insert(0, str(_kernel_dir))
    sys.path.insert(0, str(_kernel_dir.parent))

try:
    from kernel.ledger_client import LedgerClient, LedgerEntry
except ImportError:
    from ledger_client import LedgerClient, LedgerEntry


class WOLedgerHelper:
    """Helper for writing WO lifecycle events to the ledger.

    Each method creates a properly structured LedgerEntry with:
    - Correct event_type
    - metadata.provenance (agent_id, agent_class, work_order_id, session_id)
    - metadata.relational (parent_event_id, root_event_id, related_artifacts)
    - Calls LedgerClient.write() (NOT append())

    7 event types:
    - HO2 ledger: WO_PLANNED, WO_DISPATCHED, WO_CHAIN_COMPLETE, WO_QUALITY_GATE
    - HO1 ledger: WO_EXECUTING, WO_COMPLETED, WO_FAILED
    """

    def __init__(self, ledger_client: LedgerClient):
        """Initialize with a LedgerClient instance.

        Args:
            ledger_client: Initialized LedgerClient for writing entries
        """
        self.ledger_client = ledger_client

    def _build_provenance(
        self,
        wo: Optional[Any] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_class: str = "ADMIN",
    ) -> Dict[str, Any]:
        """Build provenance metadata from WO or explicit values."""
        prov: Dict[str, Any] = {
            "agent_class": agent_class,
        }
        if wo is not None:
            prov["agent_id"] = wo.created_by
            prov["work_order_id"] = wo.wo_id
            prov["session_id"] = wo.session_id
        else:
            if agent_id:
                prov["agent_id"] = agent_id
            if session_id:
                prov["session_id"] = session_id
        return prov

    def _build_relational(
        self,
        parent_event_id: Optional[str] = None,
        root_event_id: Optional[str] = None,
        related_artifacts: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Build relational metadata."""
        rel: Dict[str, Any] = {}
        if parent_event_id:
            rel["parent_event_id"] = parent_event_id
        if root_event_id:
            rel["root_event_id"] = root_event_id
        if related_artifacts:
            rel["related_artifacts"] = related_artifacts
        return rel

    # -------------------------------------------------------------------
    # HO2 Ledger Events
    # -------------------------------------------------------------------

    def write_wo_planned(
        self,
        wo: Any,
        root_event_id: Optional[str] = None,
    ) -> str:
        """Write WO_PLANNED event to HO2 ledger.

        Called when HO2 creates a new work order.

        Args:
            wo: WorkOrder instance
            root_event_id: Root event ID (None for first WO in chain)

        Returns:
            Ledger entry ID
        """
        entry = LedgerEntry(
            event_type="WO_PLANNED",
            submission_id=wo.wo_id,
            decision="WO_CREATED",
            reason=f"Work order {wo.wo_id} created: type={wo.wo_type}",
            metadata={
                "provenance": self._build_provenance(wo),
                "relational": self._build_relational(
                    root_event_id=root_event_id,
                    related_artifacts=[{"type": "ledger_entry", "id": wo.wo_id}],
                ),
                "wo_type": wo.wo_type,
                "tier_target": wo.tier_target,
            },
        )
        return self.ledger_client.write(entry)

    def write_wo_dispatched(
        self,
        wo: Any,
        parent_event_id: str,
    ) -> str:
        """Write WO_DISPATCHED event to HO2 ledger.

        Called when HO2 sends a work order to HO1.

        Args:
            wo: WorkOrder instance
            parent_event_id: ID of the WO_PLANNED entry

        Returns:
            Ledger entry ID
        """
        entry = LedgerEntry(
            event_type="WO_DISPATCHED",
            submission_id=wo.wo_id,
            decision="WO_SENT_TO_HO1",
            reason=f"Work order {wo.wo_id} dispatched to {wo.tier_target}",
            metadata={
                "provenance": self._build_provenance(wo),
                "relational": self._build_relational(
                    parent_event_id=parent_event_id,
                ),
                "tier_target": wo.tier_target,
            },
        )
        return self.ledger_client.write(entry)

    def write_wo_chain_complete(
        self,
        session_id: str,
        wo_ids: List[str],
        total_cost: Dict[str, Any],
        trace_hash: str,
        root_event_id: str,
    ) -> str:
        """Write WO_CHAIN_COMPLETE event to HO2 ledger.

        Called when all WOs in a turn are completed.

        Args:
            session_id: Session ID
            wo_ids: List of completed WO IDs
            total_cost: Aggregated cost across all WOs
            trace_hash: SHA256 hash of assembled context
            root_event_id: Root event ID of the chain

        Returns:
            Ledger entry ID
        """
        entry = LedgerEntry(
            event_type="WO_CHAIN_COMPLETE",
            submission_id=session_id,
            decision="CHAIN_DONE",
            reason=f"All {len(wo_ids)} WOs completed for session {session_id}",
            metadata={
                "provenance": self._build_provenance(session_id=session_id),
                "relational": self._build_relational(
                    root_event_id=root_event_id,
                    related_artifacts=[{"type": "ledger_entry", "id": wid} for wid in wo_ids],
                ),
                "context_fingerprint": {
                    "context_hash": trace_hash,
                },
                "cost": total_cost,
                "wo_ids": wo_ids,
            },
        )
        return self.ledger_client.write(entry)

    def write_wo_quality_gate(
        self,
        session_id: str,
        decision: str,
        parent_event_id: str,
        trace_hash: str,
    ) -> str:
        """Write WO_QUALITY_GATE event to HO2 ledger.

        Called when HO2 approves or rejects WO output.

        Args:
            session_id: Session ID
            decision: "accept" or "reject"
            parent_event_id: ID of the WO_CHAIN_COMPLETE entry
            trace_hash: SHA256 hash of assembled context

        Returns:
            Ledger entry ID
        """
        entry = LedgerEntry(
            event_type="WO_QUALITY_GATE",
            submission_id=session_id,
            decision=decision.upper(),
            reason=f"Quality gate {decision} for session {session_id}",
            metadata={
                "provenance": self._build_provenance(session_id=session_id),
                "relational": self._build_relational(
                    parent_event_id=parent_event_id,
                ),
                "context_fingerprint": {
                    "context_hash": trace_hash,
                },
                "decision": decision,
            },
        )
        return self.ledger_client.write(entry)

    # -------------------------------------------------------------------
    # HO1 Ledger Events
    # -------------------------------------------------------------------

    def write_wo_executing(
        self,
        wo: Any,
        parent_event_id: str,
        root_event_id: str,
    ) -> str:
        """Write WO_EXECUTING event to HO1 ledger.

        Called when HO1 picks up a work order.

        Args:
            wo: WorkOrder instance
            parent_event_id: ID of the HO2 WO_DISPATCHED entry
            root_event_id: Root event ID of the chain

        Returns:
            Ledger entry ID
        """
        entry = LedgerEntry(
            event_type="WO_EXECUTING",
            submission_id=wo.wo_id,
            decision="EXECUTION_STARTED",
            reason=f"HO1 executing work order {wo.wo_id}",
            metadata={
                "provenance": self._build_provenance(wo),
                "relational": self._build_relational(
                    parent_event_id=parent_event_id,
                    root_event_id=root_event_id,
                ),
                "wo_type": wo.wo_type,
            },
        )
        return self.ledger_client.write(entry)

    def write_wo_completed(
        self,
        wo: Any,
        parent_event_id: str,
        root_event_id: str,
    ) -> str:
        """Write WO_COMPLETED event to HO1 ledger.

        Called when HO1 successfully completes a work order.

        Args:
            wo: WorkOrder instance (with cost populated)
            parent_event_id: ID of the WO_EXECUTING entry
            root_event_id: Root event ID of the chain

        Returns:
            Ledger entry ID
        """
        entry = LedgerEntry(
            event_type="WO_COMPLETED",
            submission_id=wo.wo_id,
            decision="EXECUTION_SUCCEEDED",
            reason=f"Work order {wo.wo_id} completed successfully",
            metadata={
                "provenance": self._build_provenance(wo),
                "relational": self._build_relational(
                    parent_event_id=parent_event_id,
                    root_event_id=root_event_id,
                ),
                "cost": wo.cost,
                "wo_type": wo.wo_type,
            },
        )
        return self.ledger_client.write(entry)

    def write_wo_failed(
        self,
        wo: Any,
        parent_event_id: str,
        root_event_id: str,
    ) -> str:
        """Write WO_FAILED event to HO1 ledger.

        Called when HO1 fails to complete a work order.

        Args:
            wo: WorkOrder instance (with error populated)
            parent_event_id: ID of the WO_EXECUTING entry
            root_event_id: Root event ID of the chain

        Returns:
            Ledger entry ID
        """
        entry = LedgerEntry(
            event_type="WO_FAILED",
            submission_id=wo.wo_id,
            decision="EXECUTION_FAILED",
            reason=f"Work order {wo.wo_id} failed: {wo.error or 'unknown error'}",
            metadata={
                "provenance": self._build_provenance(wo),
                "relational": self._build_relational(
                    parent_event_id=parent_event_id,
                    root_event_id=root_event_id,
                ),
                "error": wo.error or "unknown error",
                "cost": wo.cost,
                "wo_type": wo.wo_type,
            },
        )
        return self.ledger_client.write(entry)
