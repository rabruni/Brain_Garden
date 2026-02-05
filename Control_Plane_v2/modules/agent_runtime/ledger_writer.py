"""Dual ledger writer for agent runtime.

Writes to both L-EXEC (execution tape) and L-EVIDENCE (evidence with hashes)
ledgers for each agent turn.

Example:
    from modules.agent_runtime.ledger_writer import LedgerWriter
    from modules.agent_runtime.session import Session

    with Session(tier="ho1") as session:
        writer = LedgerWriter(session)
        writer.write_turn(
            turn_number=1,
            exec_entry={"query_hash": "sha256:...", "result_hash": "sha256:...", "status": "ok"},
            evidence_entry={
                "declared_reads": [],
                "declared_writes": [],
                "external_calls": []
            }
        )
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class LedgerWriter:
    """Write to both L-EXEC and L-EVIDENCE ledgers."""

    def __init__(self, session):
        """Initialize for session.

        Args:
            session: Session object with ledger paths
        """
        self.session = session
        self._exec_last_hash = ""
        self._evidence_last_hash = ""

    def _compute_hash(self, entry_dict: Dict) -> str:
        """Compute hash of entry content."""
        import hashlib
        content = {k: v for k, v in entry_dict.items() if k != "entry_hash"}
        json_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
        h = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
        return f"sha256:{h}"

    def _write_entry(self, path: Path, entry: Dict, last_hash: str) -> str:
        """Write a single entry to a ledger file.

        Args:
            path: Path to ledger file
            entry: Entry dictionary
            last_hash: Hash of previous entry

        Returns:
            Hash of this entry
        """
        # Add hash chaining
        entry["previous_hash"] = last_hash
        entry["entry_hash"] = self._compute_hash(entry)

        # Append to file
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return entry["entry_hash"]

    def write_turn(
        self,
        turn_number: int,
        exec_entry: Dict[str, Any],
        evidence_entry: Dict[str, Any],
        work_order_id: Optional[str] = None,
    ) -> None:
        """Write entries to both ledgers.

        Args:
            turn_number: Turn number within session
            exec_entry: Entry for L-EXEC with query_hash, result_hash, status
            evidence_entry: Entry for L-EVIDENCE with declared_reads, declared_writes, external_calls
            work_order_id: Optional work order reference
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        # Build L-EXEC entry
        full_exec = {
            "event_type": "agent_turn",
            "session_id": self.session.session_id,
            "turn_number": turn_number,
            "timestamp": timestamp,
            **exec_entry,
        }
        if work_order_id:
            full_exec["work_order_id"] = work_order_id

        # Build L-EVIDENCE entry
        full_evidence = {
            "event_type": "turn_evidence",
            "session_id": self.session.session_id,
            "turn_number": turn_number,
            "timestamp": timestamp,
            **evidence_entry,
        }
        if work_order_id:
            full_evidence["work_order_id"] = work_order_id

        # Write to both ledgers
        self._exec_last_hash = self._write_entry(
            self.session.exec_ledger_path,
            full_exec,
            self._exec_last_hash,
        )
        self._evidence_last_hash = self._write_entry(
            self.session.evidence_ledger_path,
            full_evidence,
            self._evidence_last_hash,
        )

    def write_violation(
        self,
        turn_number: int,
        violation: Dict[str, Any],
        work_order_id: Optional[str] = None,
    ) -> None:
        """Write capability violation to L-EVIDENCE.

        Args:
            turn_number: Turn number within session
            violation: Violation details
            work_order_id: Optional work order reference
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        entry = {
            "event_type": "capability_violation",
            "session_id": self.session.session_id,
            "turn_number": turn_number,
            "timestamp": timestamp,
            "violation": violation,
        }
        if work_order_id:
            entry["work_order_id"] = work_order_id

        self._evidence_last_hash = self._write_entry(
            self.session.evidence_ledger_path,
            entry,
            self._evidence_last_hash,
        )

    def write_query(
        self,
        turn_number: int,
        content: str,
        work_order_id: Optional[str] = None,
    ) -> None:
        """Write user query entry to L-EXEC ledger.

        Creates a separate entry for the user's query, written before
        handler execution begins. This provides granular visibility
        into when queries arrive.

        Args:
            turn_number: Turn number within session
            content: The user's query text
            work_order_id: Optional work order reference
        """
        import hashlib
        timestamp = datetime.now(timezone.utc).isoformat()

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        entry = {
            "event_type": "user_query",
            "session_id": self.session.session_id,
            "turn_number": turn_number,
            "timestamp": timestamp,
            "content": content,
            "content_hash": f"sha256:{content_hash}",
        }
        if work_order_id:
            entry["work_order_id"] = work_order_id

        self._exec_last_hash = self._write_entry(
            self.session.exec_ledger_path,
            entry,
            self._exec_last_hash,
        )

    def write_response(
        self,
        turn_number: int,
        content: str,
        status: str = "ok",
        work_order_id: Optional[str] = None,
    ) -> None:
        """Write agent response entry to L-EXEC ledger.

        Creates a separate entry for the agent's response, written after
        handler execution completes. This provides granular visibility
        into when responses were generated.

        Args:
            turn_number: Turn number within session
            content: The agent's response text
            status: Response status (ok, error)
            work_order_id: Optional work order reference
        """
        import hashlib
        timestamp = datetime.now(timezone.utc).isoformat()

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        entry = {
            "event_type": "agent_response",
            "session_id": self.session.session_id,
            "turn_number": turn_number,
            "timestamp": timestamp,
            "content": content,
            "content_hash": f"sha256:{content_hash}",
            "status": status,
        }
        if work_order_id:
            entry["work_order_id"] = work_order_id

        self._exec_last_hash = self._write_entry(
            self.session.exec_ledger_path,
            entry,
            self._exec_last_hash,
        )
