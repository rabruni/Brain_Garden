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
from intent_resolver import resolve_intent_transition, make_intent_id, TransitionDecision
from bias_selector import select_biases

# Optional HO3 memory integration (PKG-HO3-MEMORY-001)
try:
    from ho3_memory import HO3Memory
except ImportError:
    HO3Memory = None


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
    # HO3 memory integration (all optional, all defaulted to off)
    ho3_enabled: bool = False
    ho3_memory_dir: Optional[Path] = None
    ho3_gate_count_threshold: int = 5
    ho3_gate_session_threshold: int = 3
    ho3_gate_window_hours: int = 168
    ho3_bias_budget: int = 2000
    # Consolidation config (29C)
    consolidation_budget: int = 4000
    consolidation_contract_id: str = "PRC-CONSOLIDATE-001"


@dataclass
class TurnResult:
    """Return type from handle_turn. Adapted from PKG-SESSION-HOST-001."""
    response: str
    wo_chain_summary: List[Dict[str, Any]]
    cost_summary: Dict[str, Any]
    session_id: str
    quality_gate_passed: bool
    consolidation_candidates: List[str] = field(default_factory=list)


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
        ho3_memory=None,
    ):
        self._plane_root = plane_root
        self._agent_class = agent_class
        self._ho1 = ho1_executor
        self._ledger = ledger_client
        self._budgeter = token_budgeter
        self._config = config
        self._ho3_memory = ho3_memory

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
        self._active_intents: List[Dict[str, Any]] = []
        self._intent_sequence: int = 0

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
        turn_event_ts = datetime.now(timezone.utc).isoformat()

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

            # ------ Step 2a+: Intent lifecycle (31C) ------
            active_intents = self._scan_active_intents(session_id)
            intent_decision = resolve_intent_transition(
                active_intents, classification, session_id, self._intent_sequence + 1,
            )
            self._apply_intent_decision(intent_decision, session_id)

            # ------ Step 2b: Attention retrieval ------
            horizontal = self._attention.horizontal_scan(session_id)
            priority = self._attention.priority_probe()

            # ------ Step 2b+: HO3 bias injection (29B) ------
            ho3_biases = []
            if self._ho3_memory and self._config.ho3_enabled:
                try:
                    all_artifacts = self._ho3_memory.read_active_biases(as_of_ts=turn_event_ts)
                except TypeError:
                    # Backward compatibility with older HO3 memory API.
                    all_artifacts = self._ho3_memory.read_active_biases()
                turn_labels = classification.get("labels", {}) if isinstance(classification, dict) else {}
                ho3_biases = select_biases(
                    all_artifacts,
                    turn_labels if isinstance(turn_labels, dict) else {},
                    self._config.ho3_bias_budget,
                    turn_event_ts,
                )

            # ------ Step 2c: Assemble context for synthesize WO ------
            assembled_context = self._attention.assemble_wo_context(
                horizontal, priority, user_message, classification,
            )
            if ho3_biases:
                context_lines = []
                for artifact in ho3_biases:
                    if not isinstance(artifact, dict):
                        continue
                    line = artifact.get("context_line")
                    if not line and isinstance(artifact.get("content", {}), dict):
                        line = artifact.get("content", {}).get("bias")
                    if isinstance(line, str) and line.strip():
                        context_lines.append(line.strip())
                if context_lines:
                    assembled_context["ho3_biases"] = context_lines

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

            # ------ Post-turn: HO3 signal accumulation (29B) ------
            consolidation_candidates: List[str] = []
            if self._ho3_memory and self._config.ho3_enabled:
                # Extract deterministic signals from the turn
                signals_this_turn: List[str] = []
                seen_signals = set()

                def _emit_signal(sig_id: str) -> None:
                    if not sig_id or sig_id in seen_signals:
                        return
                    evt_id = f"EVT-{hashlib.sha256(f'{session_id}:{sig_id}:{time.time_ns()}'.encode()).hexdigest()[:8]}"
                    self._ho3_memory.log_signal(sig_id, session_id, evt_id)
                    signals_this_turn.append(sig_id)
                    seen_signals.add(sig_id)

                # Intent signal from classify WO result
                classification_type = classification.get("speech_act")
                if classification_type:
                    _emit_signal(f"intent:{classification_type}")

                # Domain/task signals from classify labels
                labels = classification.get("labels", {}) if isinstance(classification, dict) else {}
                if isinstance(labels, dict):
                    for domain_label in self._normalize_label_values(labels.get("domain")):
                        _emit_signal(f"domain:{domain_label}")
                    for task_label in self._normalize_label_values(labels.get("task")):
                        _emit_signal(f"task:{task_label}")

                # Tool signals from WO chain cost.tool_ids_used (29C)
                for wo_result in wo_chain:
                    for tid in wo_result.get("cost", {}).get("tool_ids_used", []):
                        _emit_signal(f"tool:{tid}")

                # Outcome signal from final synthesize WO result
                synth_state = synth_result.get("state", "unknown")
                if synth_state == "completed":
                    outcome = "success"
                elif synth_state == "failed":
                    outcome = "failed"
                else:
                    outcome = "unknown"
                _emit_signal(f"outcome:{outcome}")

                # Gate check for each signal logged this turn
                for sig_id in signals_this_turn:
                    gate = self._ho3_memory.check_gate(sig_id)
                    if gate.crossed:
                        consolidation_candidates.append(sig_id)

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
                consolidation_candidates=consolidation_candidates,
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
                consolidation_candidates=[],
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

    def _normalize_label_values(self, value: Any) -> List[str]:
        """Normalize classify label values into a list of non-empty strings."""
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value else []
        if isinstance(value, list):
            return [str(v) for v in value if str(v)]
        return [str(value)] if str(value) else []

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

    # -----------------------------------------------------------------------
    # Intent lifecycle (31C)
    # -----------------------------------------------------------------------

    def _scan_active_intents(self, session_id: str = None) -> List[Dict[str, Any]]:
        """Return currently active intents (in-memory cache)."""
        return list(self._active_intents)

    def _apply_intent_decision(self, decision: TransitionDecision, session_id: str) -> None:
        """Write intent lifecycle events to ledger and update in-memory state."""
        if decision.action in ("noop", "continue"):
            return

        # Handle supersede or close: write event for the closed intent
        if decision.action in ("supersede", "close") and decision.closed_intent_id:
            if decision.action == "supersede":
                self._ledger.write(LedgerEntry(
                    event_type="INTENT_SUPERSEDED",
                    submission_id=session_id,
                    decision="SUPERSEDED",
                    reason="User started new topic",
                    metadata={
                        "provenance": {
                            "agent_id": f"{self._agent_class}.ho2",
                            "agent_class": self._agent_class,
                            "session_id": session_id,
                        },
                        "intent_id": decision.closed_intent_id,
                        "superseded_by_intent_id": decision.new_intent["intent_id"] if decision.new_intent else None,
                        "reason": "User started new topic",
                    },
                ))
            else:  # close
                self._ledger.write(LedgerEntry(
                    event_type="INTENT_CLOSED",
                    submission_id=session_id,
                    decision="CLOSED",
                    reason="User farewell",
                    metadata={
                        "provenance": {
                            "agent_id": f"{self._agent_class}.ho2",
                            "agent_class": self._agent_class,
                            "session_id": session_id,
                        },
                        "intent_id": decision.closed_intent_id,
                        "outcome": "completed",
                        "reason": "User farewell",
                    },
                ))
            # Remove closed intent from active list
            self._active_intents = [
                i for i in self._active_intents
                if i.get("intent_id") != decision.closed_intent_id
            ]

        # Handle declare: write INTENT_DECLARED and add to active list
        if decision.new_intent:
            self._ledger.write(LedgerEntry(
                event_type="INTENT_DECLARED",
                submission_id=session_id,
                decision="DECLARED",
                reason=f"Intent declared: {decision.new_intent.get('objective', '')}",
                metadata={
                    "provenance": {
                        "agent_id": f"{self._agent_class}.ho2",
                        "agent_class": self._agent_class,
                        "session_id": session_id,
                    },
                    "intent_id": decision.new_intent["intent_id"],
                    "scope": decision.new_intent.get("scope", "session"),
                    "objective": decision.new_intent.get("objective", ""),
                    "parent_intent_id": None,
                },
            ))
            self._active_intents.append(decision.new_intent)
            self._intent_sequence += 1

    # -----------------------------------------------------------------------
    # Consolidation (29C)
    # -----------------------------------------------------------------------

    def run_consolidation(self, signal_ids: List[str]) -> List[Dict[str, Any]]:
        """Dispatch bounded consolidation WOs for gate-crossing signals.

        Called AFTER the user response is delivered. Out-of-band.
        Single-shot per signal_id. Idempotent within the gate window.

        Returns list of completed consolidation WO dicts.
        """
        if not signal_ids or not self._ho3_memory or not self._config.ho3_enabled:
            return []

        completed = []
        session_id = self._session_mgr.session_id

        for sig_id in signal_ids:
            # Re-check gate (idempotency)
            gate = self._ho3_memory.check_gate(sig_id)
            if not gate.crossed:
                continue

            # Read signal accumulator
            accumulators = self._ho3_memory.read_signals(signal_id=sig_id)
            if not accumulators:
                continue
            acc = accumulators[0]

            # Create consolidation WO
            consolidation_wo = self._create_wo(
                wo_type="consolidate",
                input_context={
                    "signal_id": sig_id,
                    "count": acc.count,
                    "session_count": len(acc.session_ids),
                    "recent_events": json.dumps(acc.event_ids[-10:]),
                },
                constraints={
                    "prompt_contract_id": self._config.consolidation_contract_id,
                    "token_budget": self._config.consolidation_budget,
                    "followup_min_remaining": self._config.followup_min_remaining,
                    "budget_mode": self._config.budget_mode,
                    "turn_limit": 1,
                    "domain_tags": ["consolidation"],
                },
            )
            self._log_wo_event("WO_PLANNED", consolidation_wo)
            result = self._dispatch_wo(consolidation_wo)

            # On success: write overlay with source_event_ids
            if result.get("state") == "completed":
                output = result.get("output_result", {}) or {}
                now_iso = datetime.now(timezone.utc).isoformat()
                overlay = {
                    "signal_id": sig_id,
                    "salience_weight": output.get("salience_weight", 0.5),
                    "decay_modifier": output.get("decay_modifier", 0.95),
                    "source_event_ids": acc.event_ids,
                    "content": {
                        "bias": output.get("bias", ""),
                        "category": output.get("category", ""),
                    },
                    "window_start": acc.last_seen if acc.event_ids else now_iso,
                    "window_end": now_iso,
                }
                self._ho3_memory.log_overlay(overlay)
                completed.append(result)

        return completed
