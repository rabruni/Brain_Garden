"""Session Host V2: thin adapter delegating to HO2 Supervisor.

Replaces v1 flat loop. V2 does exactly three things:
1. start_session() / end_session() → delegates to HO2
2. process_turn() → delegates to HO2 Supervisor's handle_turn()
3. Catches exceptions → degrades to direct LLM call through Gateway

Under 100 lines of logic. Everything else lives in HO2 Supervisor.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TurnResult:
    response: str
    outcome: str  # "success", "degraded", "error"
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    exchange_entry_ids: list[str] = field(default_factory=list)


@dataclass
class AgentConfig:
    agent_id: str
    agent_class: str
    framework_id: str
    tier: str
    system_prompt: str
    attention: dict[str, Any]
    tools: list[dict[str, Any]]
    budget: dict[str, Any]
    permissions: dict[str, Any]


class SessionHostV2:
    """Thin adapter: delegates to HO2, degrades to Gateway on failure."""

    def __init__(self, ho2_supervisor, gateway, agent_config: AgentConfig,
                 ledger_client=None):
        self._ho2 = ho2_supervisor
        self._gateway = gateway
        self._config = agent_config
        self._ledger = ledger_client
        self._session_id = ""

    def start_session(self, agent_config: AgentConfig | None = None) -> str:
        config = agent_config or self._config
        self._session_id = self._ho2.start_session()
        return self._session_id

    def process_turn(self, user_message: str) -> TurnResult:
        if not self._session_id:
            self.start_session()

        try:
            result = self._ho2.handle_turn(user_message)
            return TurnResult(
                response=getattr(result, "response", str(result)),
                outcome="success",
                tool_calls=getattr(result, "tool_calls", []),
                exchange_entry_ids=getattr(result, "exchange_entry_ids", []),
            )
        except Exception as ho2_exc:
            return self._degrade(user_message, ho2_exc)

    def _degrade(self, user_message: str, ho2_exc: Exception) -> TurnResult:
        logger.warning("HO2 failed (%s), degrading to direct LLM call", ho2_exc)
        self._log_degradation(ho2_exc)

        try:
            from llm_gateway import PromptRequest
            request = PromptRequest(
                prompt=user_message,
                prompt_pack_id="PRM-DEGRADED-001",
                contract_id="PRC-DEGRADED-001",
                agent_id=self._config.agent_id,
                agent_class=self._config.agent_class,
                framework_id=self._config.framework_id,
                package_id="PKG-SESSION-HOST-V2-001",
                work_order_id=f"WO-DEGRADED-{uuid.uuid4().hex[:8]}",
                session_id=self._session_id,
                tier=self._config.tier,
                max_tokens=4096,
                temperature=0.0,
            )
            response = self._gateway.route(request)
            return TurnResult(
                response=getattr(response, "content", str(response)),
                outcome="degraded",
            )
        except Exception as gw_exc:
            logger.error("Gateway also failed (%s), returning error", gw_exc)
            return TurnResult(
                response="Service temporarily unavailable. Both HO2 supervisor "
                         "and LLM gateway failed. Please try again.",
                outcome="error",
            )

    def _log_degradation(self, exc: Exception) -> None:
        if self._ledger is None:
            return
        try:
            import sys
            from pathlib import Path
            _staging = Path(__file__).resolve().parents[3]
            _kernel = _staging / "PKG-KERNEL-001" / "HOT" / "kernel"
            if _kernel.exists() and str(_kernel) not in sys.path:
                sys.path.insert(0, str(_kernel))
            from ledger_client import LedgerEntry
            self._ledger.write(
                LedgerEntry(
                    event_type="DEGRADATION",
                    submission_id="PKG-SESSION-HOST-V2-001",
                    decision="DEGRADED",
                    reason=f"HO2 failed: {exc}",
                    metadata={
                        "session_id": self._session_id,
                        "agent_id": self._config.agent_id,
                        "error_type": type(exc).__name__,
                    },
                )
            )
        except Exception:
            logger.warning("Failed to log degradation event to ledger")

    def end_session(self) -> None:
        if self._session_id:
            try:
                self._ho2.end_session()
            except Exception as exc:
                logger.warning("HO2 end_session failed (%s)", exc)
            self._session_id = ""
