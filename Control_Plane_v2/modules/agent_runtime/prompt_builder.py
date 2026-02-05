"""Prompt header builder for agent turns.

Assembles context headers from ledger state for agent prompts.

Example:
    from modules.agent_runtime.prompt_builder import PromptBuilder

    builder = PromptBuilder(tier="ho1")
    header = builder.build(
        session_id="SES-abc123",
        turn_number=1,
        declared_inputs=[{"path": "config.json", "hash": "sha256:..."}],
        declared_outputs=[{"path": "output/result.json", "role": "result"}]
    )
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import json


class PromptBuilder:
    """Build prompt headers from ledger state."""

    def __init__(self, tier: str = "ho1", root: Optional[Path] = None):
        """Initialize builder.

        Args:
            tier: Execution tier (ho1, ho2, ho3)
            root: Optional root directory
        """
        self.tier = tier
        self.root = root or self._get_default_root()

    def _get_default_root(self) -> Path:
        """Get default Control Plane root."""
        current = Path(__file__).resolve()
        while current.name != "Control_Plane_v2" and current.parent != current:
            current = current.parent
        if current.name == "Control_Plane_v2":
            return current
        return Path.cwd()

    def build(
        self,
        session_id: str,
        turn_number: int,
        declared_inputs: List[Dict[str, Any]],
        declared_outputs: List[Dict[str, Any]],
        work_order_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        capabilities: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Build prompt header with declared context.

        Args:
            session_id: Session identifier
            turn_number: Turn number (1-indexed)
            declared_inputs: List of input files with paths and hashes
            declared_outputs: List of output files with paths and roles
            work_order_id: Optional work order reference
            agent_id: Optional agent package ID
            capabilities: Optional capabilities dict

        Returns:
            Prompt header dictionary
        """
        header = {
            "role": agent_id or "agent",
            "tier": self.tier,
            "session_id": session_id,
            "turn_number": turn_number,
            "context_as_of": datetime.now(timezone.utc).isoformat(),
            "declared_inputs": declared_inputs,
            "declared_outputs": declared_outputs,
        }

        if work_order_id:
            header["work_order_id"] = work_order_id

        if capabilities:
            header["capabilities"] = {
                "read": len(capabilities.get("read", [])),
                "write": len(capabilities.get("write", [])),
                "execute": len(capabilities.get("execute", [])),
            }

        return header

    def format_as_markdown(self, header: Dict[str, Any]) -> str:
        """Format header as markdown for inclusion in prompts.

        Args:
            header: Prompt header dictionary

        Returns:
            Markdown-formatted header string
        """
        lines = [
            "# Agent Context",
            "",
            f"**Session:** {header['session_id']}",
            f"**Turn:** {header['turn_number']}",
            f"**Tier:** {header['tier']}",
            f"**Context as of:** {header['context_as_of']}",
        ]

        if header.get("work_order_id"):
            lines.append(f"**Work Order:** {header['work_order_id']}")

        lines.append("")
        lines.append("## Declared Inputs")
        if header.get("declared_inputs"):
            for inp in header["declared_inputs"]:
                lines.append(f"- `{inp['path']}` ({inp.get('hash', 'no hash')[:20]}...)")
        else:
            lines.append("- None")

        lines.append("")
        lines.append("## Declared Outputs")
        if header.get("declared_outputs"):
            for out in header["declared_outputs"]:
                lines.append(f"- `{out['path']}` ({out.get('role', 'unknown role')})")
        else:
            lines.append("- None (read-only)")

        return "\n".join(lines)

    def format_as_json(self, header: Dict[str, Any]) -> str:
        """Format header as JSON.

        Args:
            header: Prompt header dictionary

        Returns:
            JSON string
        """
        return json.dumps(header, indent=2, ensure_ascii=False)
