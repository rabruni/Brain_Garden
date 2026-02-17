"""HO2 Supervisor — Modified Kitchener cognitive dispatch loop.

HO2 owns Steps 2 (Scoping) and 4 (Verification):
- Step 2: Classify user intent, retrieve context, plan WO chain
- Step 3: Dispatch WOs to HO1 for execution
- Step 4: Verify results via quality gate

HO2 NEVER calls LLM Gateway directly (Invariant #1).
All cognitive work is dispatched as WorkOrders to HO1.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

import sys

_staging = Path(__file__).resolve().parents[3]
_kernel_dir = _staging / "PKG-KERNEL-001" / "HOT" / "kernel"
if _kernel_dir.exists():
    sys.path.insert(0, str(_kernel_dir))
    sys.path.insert(0, str(_kernel_dir.parent))
_wo_dir = _staging / "PKG-WORK-ORDER-001" / "HOT" / "kernel"
if _wo_dir.exists():
    sys.path.insert(0, str(_wo_dir))

try:
    from ledger_client import LedgerClient, LedgerEntry
except ImportError:
    from kernel.ledger_client import LedgerClient, LedgerEntry

from session_manager import SessionManager, TurnMessage
from attention import AttentionRetriever, ContextProvider, AttentionContext
from quality_gate import QualityGate, QualityGateResult


# ---------------------------------------------------------------------------
# Protocols and Data Classes
# ---------------------------------------------------------------------------

class HO1ExecutorProtocol(Protocol):
    """Interface HO2 depends on for HO1 execution."""
    def execute(self, work_order: dict) -> dict: ...


@dataclass
class HO2Config:
    """Per-agent-class configuration. Factory pattern per FMWK-010."""
    attention_templates: List[str]
    ho2m_path: Path
    ho1m_path: Path
    budget_ceiling: int = 100000
    max_wo_chain_length: int = 10
    max_retries: int = 2
    classify_contract_id: str = "PRC-CLASSIFY-001"
    synthesize_contract_id: str = "PRC-SYNTHESIZE-001"
    verify_contract_id: str = "PRC-VERIFY-001"
    classify_budget: int = 2000
    synthesize_budget: int = 16000
    followup_min_remaining: int = 500
    budget_mode: str = "enforce"
    attention_budget_tokens: int = 10000
    attention_budget_queries: int = 20
    attention_timeout_ms: int = 5000
    tools_allowed: List[str] = field(default_factory=list)


@dataclass
class TurnResult:
    """Return type from handle_turn. Adapted from PKG-SESSION-HOST-001."""
    response: str
    wo_chain_summary: List[Dict[str, Any]]
    cost_summary: Dict[str, Any]
    session_id: str
    quality_gate_passed: bool


# ---------------------------------------------------------------------------
# HO2 Supervisor
# ---------------------------------------------------------------------------

class HO2Supervisor:
    """Deliberative supervisor for the Modified Kitchener loop.

    Written once, instantiated per agent class with different HO2Config.
    Factory pattern per FMWK-010 Invariant #7.
    """

    def __init__(
        self,
        plane_root: Path,
        agent_class: str,
        ho1_executor: HO1ExecutorProtocol,
        ledger_client: LedgerClient,
        token_budgeter: Any,
        config: HO2Config,
    ):
        self._plane_root = plane_root
        self._agent_class = agent_class
        self._ho1 = ho1_executor
        self._ledger = ledger_client
        self._budgeter = token_budgeter
        self._config = config

        agent_id = f"{agent_class}.ho2"
        self._session_mgr = SessionManager(ledger_client, agent_class, agent_id)
        self._attention = AttentionRetriever(
            plane_root,
            ContextProvider(plane_root),
            config,
        )
        self._quality_gate = QualityGate(config)
        self._total_cost: Dict[str, int] = {
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
            "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0,
        }

    def start_session(self) -> str:
        """Initialize session. Returns session_id."""
        return self._session_mgr.start_session()

    def end_session(self) -> None:
        """Close session. Write SESSION_END to HO2m."""
        self._session_mgr.end_session(
            turn_count=self._session_mgr.turn_count,
            total_cost=dict(self._total_cost),
        )

    def handle_turn(self, user_message: str) -> TurnResult:
        """Main entry: classify -> attention -> synthesize -> verify -> return.

        Kitchener Steps 2 (Scope) -> 3 (Execute via HO1) -> 4 (Verify).
        """
        # Auto-start session if needed
        session_id = self._session_mgr.session_id
        if session_id is None:
            session_id = self.start_session()

        wo_chain: List[Dict[str, Any]] = []
        chain_cost: Dict[str, int] = {
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
            "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0,
        }

        try:
            # ------ Step 2a: Classify user intent ------
            classify_wo = self._create_wo(
                wo_type="classify",
                input_context={"user_input": user_message},
                constraints={
                    "prompt_contract_id": self._config.classify_contract_id,
                    "token_budget": self._config.classify_budget,
                    "followup_min_remaining": self._config.followup_min_remaining,
                    "budget_mode": self._config.budget_mode,
                    "turn_limit": 1,
                },
            )
            self._log_wo_event("WO_PLANNED", classify_wo)
            classify_result = self._dispatch_wo(classify_wo)
            wo_chain.append(classify_result)
            self._accumulate_cost(chain_cost, classify_result.get("cost", {}))

            classification = classify_result.get("output_result", {}) or {}

            # ------ Step 2b: Attention retrieval ------
            horizontal = self._attention.horizontal_scan(session_id)
            priority = self._attention.priority_probe()

            # ------ Step 2c: Assemble context for synthesize WO ------
            assembled_context = self._attention.assemble_wo_context(
                horizontal, priority, user_message, classification,
            )

            # ------ Step 3: Dispatch synthesize WO to HO1 ------
            synthesize_wo = self._create_wo(
                wo_type="synthesize",
                input_context={
                    **assembled_context,
                    "prior_results": [classify_result.get("output_result", {})],
                },
                constraints={
                    "prompt_contract_id": self._config.synthesize_contract_id,
                    "token_budget": self._config.synthesize_budget,
                    "followup_min_remaining": self._config.followup_min_remaining,
                    "budget_mode": self._config.budget_mode,
                    "turn_limit": 10 if self._config.tools_allowed else 1,
                    "tools_allowed": list(self._config.tools_allowed),
                },
                acceptance_criteria={
                    "requires_response_text": True,
                    "min_response_length": 1,
                },
            )
            self._log_wo_event("WO_PLANNED", synthesize_wo)
            synth_result = self._dispatch_wo(synthesize_wo)
            wo_chain.append(synth_result)
            self._accumulate_cost(chain_cost, synth_result.get("cost", {}))

            # ------ Step 4: Quality gate ------
            output_result = synth_result.get("output_result", {}) or {}
            if synth_result.get("state") == "failed" and synth_result.get("error"):
                wo_error = synth_result["error"]
                error_result = {"response_text": f"[Error: {wo_error}]", "error": wo_error}
                output_result = error_result
                synth_result["output_result"] = error_result
            gate_result = self._quality_gate.verify(
                output_result=output_result,
                acceptance_criteria=synthesize_wo.get("acceptance_criteria", {}),
                wo_id=synth_result.get("wo_id", ""),
            )

            quality_passed = gate_result.decision == "accept"

            # Retry loop on rejection
            retry_count = 0
            while not quality_passed and retry_count < self._config.max_retries:
                retry_count += 1
                retry_wo = self._create_wo(
                    wo_type="synthesize",
                    input_context={
                        **assembled_context,
                        "prior_results": [classify_result.get("output_result", {})],
                        "retry_reason": gate_result.reason,
                        "retry_attempt": retry_count,
                    },
                    constraints={
                        "prompt_contract_id": self._config.synthesize_contract_id,
                        "token_budget": self._config.synthesize_budget,
                        "followup_min_remaining": self._config.followup_min_remaining,
                        "budget_mode": self._config.budget_mode,
                        "turn_limit": 10 if self._config.tools_allowed else 1,
                        "tools_allowed": list(self._config.tools_allowed),
                    },
                    acceptance_criteria={
                        "requires_response_text": True,
                        "min_response_length": 1,
                    },
                )
                self._log_wo_event("WO_PLANNED", retry_wo)
                retry_result = self._dispatch_wo(retry_wo)
                wo_chain.append(retry_result)
                self._accumulate_cost(chain_cost, retry_result.get("cost", {}))

                output_result = retry_result.get("output_result", {}) or {}
                if retry_result.get("state") == "failed" and retry_result.get("error"):
                    wo_error = retry_result["error"]
                    error_result = {"response_text": f"[Error: {wo_error}]", "error": wo_error}
                    output_result = error_result
                    retry_result["output_result"] = error_result
                gate_result = self._quality_gate.verify(
                    output_result=output_result,
                    acceptance_criteria=retry_wo.get("acceptance_criteria", {}),
                    wo_id=retry_result.get("wo_id", ""),
                )
                quality_passed = gate_result.decision == "accept"
                synth_result = retry_result

            # If still rejected after retries, log escalation
            if not quality_passed:
                self._log_escalation(session_id, gate_result)

            # ------ Log chain events ------
            wo_ids = [w.get("wo_id", "") for w in wo_chain]
            trace_hash = self._compute_trace_hash(wo_ids, session_id)

            self._log_chain_complete(session_id, wo_ids, chain_cost, trace_hash)
            self._log_quality_gate(session_id, gate_result, trace_hash)

            # Accumulate to session total
            self._accumulate_cost(self._total_cost, chain_cost)

            # Track turn
            response_text = output_result.get("response_text", "") if quality_passed else (
                output_result.get("response_text", "") or f"[Quality gate failed: {gate_result.reason}]"
            )
            self._session_mgr.add_turn(user_message, response_text)

            return TurnResult(
                response=response_text,
                wo_chain_summary=[{
                    "wo_id": w.get("wo_id", ""),
                    "wo_type": w.get("wo_type", ""),
                    "state": w.get("state", ""),
                    "cost": w.get("cost", {}),
                } for w in wo_chain],
                cost_summary=dict(chain_cost),
                session_id=session_id,
                quality_gate_passed=quality_passed,
            )

        except Exception as exc:
            # Degradation path: log governance violation
            self._log_degradation(session_id, str(exc))
            degradation_response = f"[Degradation: {exc}]"
            self._session_mgr.add_turn(user_message, degradation_response)
            return TurnResult(
                response=degradation_response,
                wo_chain_summary=[{
                    "wo_id": w.get("wo_id", ""),
                    "wo_type": w.get("wo_type", ""),
                    "state": w.get("state", ""),
                    "cost": w.get("cost", {}),
                } for w in wo_chain],
                cost_summary=dict(chain_cost),
                session_id=session_id,
                quality_gate_passed=False,
            )

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _create_wo(
        self,
        wo_type: str,
        input_context: Dict[str, Any],
        constraints: Dict[str, Any],
        acceptance_criteria: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a WorkOrder dict using SessionManager for ID generation."""
        wo_id = self._session_mgr.next_wo_id()
        session_id = self._session_mgr.session_id
        return {
            "wo_id": wo_id,
            "session_id": session_id,
            "wo_type": wo_type,
            "tier_target": "HO1",
            "state": "planned",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": f"{self._agent_class}.ho2",
            "input_context": input_context,
            "constraints": constraints,
            "acceptance_criteria": acceptance_criteria or {},
            "output_result": None,
            "error": None,
            "completed_at": None,
            "cost": {
                "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0,
            },
        }

    def _dispatch_wo(self, wo: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch WO to HO1 and log events."""
        wo["state"] = "dispatched"
        self._log_wo_event("WO_DISPATCHED", wo)
        result = self._ho1.execute(wo)
        return result

    def _accumulate_cost(self, target: Dict[str, int], source: Dict[str, Any]) -> None:
        for key in ("input_tokens", "output_tokens", "total_tokens", "llm_calls", "tool_calls", "elapsed_ms"):
            target[key] = target.get(key, 0) + int(source.get(key, 0))

    def _compute_trace_hash(self, wo_ids: List[str], session_id: str) -> str:
        """SHA256 of concatenated HO1m entries for this WO chain."""
        ho1m_path = self._config.ho1m_path
        provider = ContextProvider(self._plane_root)
        entries = provider.read_ledger_entries(
            ledger_path=ho1m_path,
            filters={"session_id": session_id},
        )
        # Filter to entries matching our WO IDs
        chain_entries = [
            e for e in entries
            if e.get("submission_id") in wo_ids or
            (isinstance(e.get("metadata", {}), dict) and
             e.get("metadata", {}).get("provenance", {}).get("work_order_id") in wo_ids)
        ]
        serialized = "".join(json.dumps(e, sort_keys=True) for e in chain_entries)
        return hashlib.sha256(serialized.encode()).hexdigest()

    # -----------------------------------------------------------------------
    # Ledger event helpers
    # -----------------------------------------------------------------------

    def _log_wo_event(self, event_type: str, wo: Dict[str, Any]) -> None:
        self._ledger.write(LedgerEntry(
            event_type=event_type,
            submission_id=wo.get("wo_id", ""),
            decision=event_type,
            reason=f"{event_type} for {wo.get('wo_id', '')}",
            metadata={
                "provenance": {
                    "agent_id": f"{self._agent_class}.ho2",
                    "agent_class": self._agent_class,
                    "work_order_id": wo.get("wo_id", ""),
                    "session_id": wo.get("session_id", ""),
                },
                "wo_type": wo.get("wo_type", ""),
                "tier_target": wo.get("tier_target", "HO1"),
            },
        ))

    def _log_chain_complete(
        self, session_id: str, wo_ids: List[str],
        total_cost: Dict[str, Any], trace_hash: str,
    ) -> None:
        self._ledger.write(LedgerEntry(
            event_type="WO_CHAIN_COMPLETE",
            submission_id=session_id,
            decision="CHAIN_DONE",
            reason=f"All {len(wo_ids)} WOs completed for session {session_id}",
            metadata={
                "provenance": {
                    "agent_id": f"{self._agent_class}.ho2",
                    "agent_class": self._agent_class,
                    "session_id": session_id,
                },
                "relational": {
                    "related_artifacts": [{"type": "ledger_entry", "id": wid} for wid in wo_ids],
                },
                "context_fingerprint": {"context_hash": trace_hash},
                "cost": total_cost,
                "wo_ids": wo_ids,
            },
        ))

    def _log_quality_gate(
        self, session_id: str, gate_result: QualityGateResult, trace_hash: str,
    ) -> None:
        self._ledger.write(LedgerEntry(
            event_type="WO_QUALITY_GATE",
            submission_id=session_id,
            decision=gate_result.decision.upper(),
            reason=gate_result.reason,
            metadata={
                "provenance": {
                    "agent_id": f"{self._agent_class}.ho2",
                    "agent_class": self._agent_class,
                    "session_id": session_id,
                },
                "context_fingerprint": {"context_hash": trace_hash},
                "decision": gate_result.decision,
                "wo_id": gate_result.wo_id,
            },
        ))

    def _log_degradation(self, session_id: str, error: str) -> None:
        self._ledger.write(LedgerEntry(
            event_type="DEGRADATION",
            submission_id=session_id or "unknown",
            decision="DEGRADED",
            reason=f"HO1 dispatch failed: {error}",
            metadata={
                "provenance": {
                    "agent_id": f"{self._agent_class}.ho2",
                    "agent_class": self._agent_class,
                    "session_id": session_id or "unknown",
                },
                "governance_violation": True,
                "error": error,
            },
        ))

    def _log_escalation(self, session_id: str, gate_result: QualityGateResult) -> None:
        self._ledger.write(LedgerEntry(
            event_type="ESCALATION",
            submission_id=session_id,
            decision="ESCALATED",
            reason=f"Quality gate rejected after {self._config.max_retries} retries: {gate_result.reason}",
            metadata={
                "provenance": {
                    "agent_id": f"{self._agent_class}.ho2",
                    "agent_class": self._agent_class,
                    "session_id": session_id,
                },
                "max_retries": self._config.max_retries,
                "final_decision": gate_result.decision,
                "wo_id": gate_result.wo_id,
            },
        ))
