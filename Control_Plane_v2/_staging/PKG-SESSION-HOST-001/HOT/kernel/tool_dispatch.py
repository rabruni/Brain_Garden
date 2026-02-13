"""Tool dispatch for Session Host.

Registers tool handlers, enforces basic allow/forbidden rules,
and executes tool calls requested by the model.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class ToolResult:
    """Result from one tool execution."""

    tool_id: str
    status: str
    output: Any = None
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "status": self.status,
            "output": self.output,
            "error": self.error,
        }


class ToolDispatcher:
    """Dispatches tool calls against registered handlers."""

    def __init__(
        self,
        plane_root: Path,
        tool_configs: list[dict[str, Any]],
        permissions: dict[str, Any],
    ):
        self._plane_root = Path(plane_root)
        self._tool_configs = list(tool_configs or [])
        self._permissions = permissions or {}
        self._handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}
        self._declared = {tool.get("tool_id", "") for tool in self._tool_configs}

    def register_tool(
        self,
        tool_id: str,
        handler_fn: Callable[[dict[str, Any]], Any],
        schema: dict[str, Any] | None = None,
    ) -> None:
        """Register a handler for a tool id."""
        self._handlers[tool_id] = handler_fn
        if schema is not None and tool_id not in self._declared:
            self._tool_configs.append(
                {
                    "tool_id": tool_id,
                    "description": "",
                    "parameters": schema,
                }
            )
            self._declared.add(tool_id)

    def _is_allowed(self, tool_id: str) -> tuple[bool, str]:
        """Basic guardrail check for declared tools and forbidden wildcard."""
        if tool_id not in self._declared:
            return False, f"Tool '{tool_id}' is not declared for this agent"

        forbidden = self._permissions.get("forbidden", [])
        if "*" in forbidden:
            return False, "Tool use blocked by permissions"

        return True, ""

    def execute(self, tool_id: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute one tool call and return normalized result."""
        allowed, reason = self._is_allowed(tool_id)
        if not allowed:
            return ToolResult(tool_id=tool_id, status="error", error=reason)

        handler = self._handlers.get(tool_id)
        if handler is None:
            return ToolResult(
                tool_id=tool_id,
                status="error",
                error=f"No handler registered for '{tool_id}'",
            )

        try:
            result = handler(arguments or {})
            return ToolResult(tool_id=tool_id, status="ok", output=result)
        except Exception as exc:  # pragma: no cover - defensive normalization
            return ToolResult(tool_id=tool_id, status="error", error=str(exc))

    def get_api_tools(self) -> list[dict[str, Any]]:
        """Return tool definitions in Anthropic-style API shape."""
        tools = []
        for tool in self._tool_configs:
            tool_id = tool.get("tool_id", "")
            if not tool_id:
                continue
            tools.append(
                {
                    "name": tool_id,
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("parameters", {"type": "object", "properties": {}}),
                }
            )
        return tools
