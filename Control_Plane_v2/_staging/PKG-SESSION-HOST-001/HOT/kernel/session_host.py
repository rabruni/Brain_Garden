"""Session Host: governed chat loop runtime.

Session Host is agent-agnostic infrastructure:
- start/end session lifecycle
- turn processing with attention -> router
- optional tool-use loop via ToolDispatcher
- in-memory history with ledger lifecycle events
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ledger_client import LedgerEntry
from prompt_router import PromptRequest, RouteOutcome
from tool_dispatch import ToolDispatcher


@dataclass
class TurnMessage:
    role: str
    content: str


@dataclass
class TurnResult:
    response: str
    outcome: str
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

    @classmethod
    def from_file(cls, path: Path) -> "AgentConfig":
        data = json.loads(Path(path).read_text())
        required = [
            "agent_id",
            "agent_class",
            "framework_id",
            "tier",
            "system_prompt",
            "attention",
            "tools",
            "budget",
            "permissions",
        ]
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"required fields missing: {', '.join(missing)}")
        return cls(**{k: data[k] for k in required})


class SessionHost:
    """Governed multi-turn host for one agent session."""

    def __init__(
        self,
        plane_root: Path,
        agent_config: AgentConfig,
        attention_service: Any,
        router: Any,
        tool_dispatcher: ToolDispatcher,
        ledger_client: Any,
        dev_mode: bool = False,
        now_fn: Callable[[], float] | None = None,
    ):
        self._plane_root = Path(plane_root)
        self._config = agent_config
        self._attention = attention_service
        self._router = router
        self._tool_dispatcher = tool_dispatcher
        self._ledger = ledger_client
        self._dev_mode = dev_mode
        self._now = now_fn or time.time

        self._session_id = ""
        self._session_start_s: float | None = None
        self._history: list[TurnMessage] = []
        self._turn_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    @property
    def history(self) -> list[TurnMessage]:
        return list(self._history)

    def start_session(self) -> str:
        """Initialize session and write SESSION_START entry."""
        if not self._session_id:
            self._session_id = f"SES-{uuid.uuid4().hex[:8]}"
            self._session_start_s = self._now()
            self._ledger.write(
                LedgerEntry(
                    event_type="SESSION_START",
                    submission_id=self._config.attention["prompt_contract"]["contract_id"],
                    decision="STARTED",
                    reason="Session started",
                    metadata={
                        "agent_id": self._config.agent_id,
                        "agent_class": self._config.agent_class,
                        "session_id": self._session_id,
                        "framework_id": self._config.framework_id,
                    },
                )
            )
        return self._session_id

    def _enforce_limits(self) -> None:
        turn_limit = int(self._config.budget.get("turn_limit", 0) or 0)
        if turn_limit and self._turn_count >= turn_limit:
            raise RuntimeError("Session turn limit reached")

        timeout_seconds = int(self._config.budget.get("timeout_seconds", 0) or 0)
        if timeout_seconds and self._session_start_s is not None:
            if (self._now() - self._session_start_s) > timeout_seconds:
                raise RuntimeError("Session timeout reached")

    def _build_attention_request(self) -> Any:
        """Build request payload for AttentionService.assemble."""
        prompt_contract = self._config.attention.get("prompt_contract", {})
        try:
            from attention_service import AttentionRequest

            return AttentionRequest(
                agent_id=self._config.agent_id,
                agent_class=self._config.agent_class,
                framework_id=self._config.framework_id,
                tier=self._config.tier,
                work_order_id=f"WO-{self._session_id}",
                session_id=self._session_id,
                prompt_contract=prompt_contract,
                template_override=self._config.attention.get("template_id"),
            )
        except Exception:
            return {
                "agent_id": self._config.agent_id,
                "agent_class": self._config.agent_class,
                "framework_id": self._config.framework_id,
                "tier": self._config.tier,
                "work_order_id": f"WO-{self._session_id}",
                "session_id": self._session_id,
                "prompt_contract": prompt_contract,
                "template_override": self._config.attention.get("template_id"),
            }

    def _build_prompt(self, user_message: str, context_text: str) -> str:
        """Construct routed prompt from system, context, history, and user message."""
        parts = [f"SYSTEM:\n{self._config.system_prompt}"]
        if context_text:
            parts.append(f"CONTEXT:\n{context_text}")

        if self._history:
            transcript = []
            for msg in self._history:
                transcript.append(f"{msg.role.upper()}: {msg.content}")
            parts.append("HISTORY:\n" + "\n".join(transcript))

        parts.append(f"USER:\n{user_message}")
        return "\n\n".join(parts)

    @staticmethod
    def _extract_tool_uses(content: str) -> list[dict[str, Any]]:
        """Parse tool_use objects from JSON response content."""
        if not content:
            return []

        try:
            parsed = json.loads(content)
        except Exception:
            return []

        value = parsed.get("tool_use") if isinstance(parsed, dict) else None
        if value is None:
            return []

        if isinstance(value, dict):
            value = [value]

        uses: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            tool_id = item.get("tool_id") or item.get("name") or ""
            args = item.get("arguments") or item.get("input") or {}
            if tool_id:
                uses.append({"tool_id": tool_id, "arguments": args})
        return uses

    def _route_prompt(self, prompt: str):
        pc = self._config.attention.get("prompt_contract", {})
        boundary = pc.get("boundary", {})
        request = PromptRequest(
            prompt=prompt,
            prompt_pack_id=pc.get("prompt_pack_id", "PRM-ADMIN-001"),
            contract_id=pc.get("contract_id", "PRC-ADMIN-001"),
            agent_id=self._config.agent_id,
            agent_class=self._config.agent_class,
            framework_id=self._config.framework_id,
            package_id="PKG-ADMIN-001",
            work_order_id=f"WO-{self._session_id}",
            session_id=self._session_id,
            tier=self._config.tier,
            max_tokens=int(boundary.get("max_tokens", 4096)),
            temperature=float(boundary.get("temperature", 0.0)),
            tools=self._tool_dispatcher.get_api_tools() or None,
            auth_token=None if self._dev_mode else "required",
        )
        return self._router.route(request)

    def process_turn(self, user_message: str) -> TurnResult:
        """One full turn: attention -> router -> optional tools -> final response."""
        self.start_session()
        # Capture turn start for timing/limits; kept even if only used implicitly.
        _turn_start_s = self._now()
        self._enforce_limits()

        # Include user turn in session memory before prompt build.
        self._history.append(TurnMessage(role="user", content=user_message))

        attention_request = self._build_attention_request()
        context = self._attention.assemble(attention_request)
        context_text = getattr(context, "context_text", "") or ""

        prompt = self._build_prompt(user_message=user_message, context_text=context_text)
        first = self._route_prompt(prompt)

        exchange_ids: list[str] = []
        if getattr(first, "exchange_entry_id", ""):
            exchange_ids.append(first.exchange_entry_id)

        self.total_input_tokens += int(getattr(first, "input_tokens", 0) or 0)
        self.total_output_tokens += int(getattr(first, "output_tokens", 0) or 0)

        tool_calls: list[dict[str, Any]] = []
        tool_uses = self._extract_tool_uses(getattr(first, "content", ""))

        final_response = first
        if tool_uses:
            tool_results = []
            for call in tool_uses:
                result = self._tool_dispatcher.execute(call["tool_id"], call.get("arguments", {}))
                payload = result.as_dict()
                tool_calls.append(payload)
                tool_results.append(payload)

                self._ledger.write(
                    LedgerEntry(
                        event_type="TOOL_CALL",
                        submission_id=self._config.attention["prompt_contract"]["contract_id"],
                        decision="OK" if result.status == "ok" else "ERROR",
                        reason=f"Tool {call['tool_id']} executed",
                        metadata={
                            "session_id": self._session_id,
                            "tool_id": call["tool_id"],
                            "status": result.status,
                        },
                    )
                )

            followup_prompt = prompt + "\n\nTOOL_RESULT:\n" + json.dumps({"tool_result": tool_results})
            final_response = self._route_prompt(followup_prompt)
            if getattr(final_response, "exchange_entry_id", ""):
                exchange_ids.append(final_response.exchange_entry_id)

            self.total_input_tokens += int(getattr(final_response, "input_tokens", 0) or 0)
            self.total_output_tokens += int(getattr(final_response, "output_tokens", 0) or 0)

        assistant_text = getattr(final_response, "content", "")
        self._history.append(TurnMessage(role="assistant", content=assistant_text))
        self._turn_count += 1

        return TurnResult(
            response=assistant_text,
            outcome=getattr(final_response, "outcome", RouteOutcome.SUCCESS),
            tool_calls=tool_calls,
            exchange_entry_ids=exchange_ids,
        )

    def end_session(self) -> None:
        """Close session and write SESSION_END entry."""
        if not self._session_id:
            return

        self._ledger.write(
            LedgerEntry(
                event_type="SESSION_END",
                submission_id=self._config.attention["prompt_contract"]["contract_id"],
                decision="ENDED",
                reason="Session ended",
                metadata={
                    "session_id": self._session_id,
                    "agent_id": self._config.agent_id,
                    "turn_count": self._turn_count,
                    "total_input_tokens": self.total_input_tokens,
                    "total_output_tokens": self.total_output_tokens,
                },
            )
        )
