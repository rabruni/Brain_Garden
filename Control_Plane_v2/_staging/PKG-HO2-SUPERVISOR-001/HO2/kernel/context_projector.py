"""Context projector for HO2 context assembly (HANDOFF-31E-1)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from liveness import LivenessState


def _estimate_tokens(text: str, chars_per_token: int = 4) -> int:
    if not text:
        return 0
    return max(1, len(text) // chars_per_token)


@dataclass
class ProjectionConfig:
    projection_budget: int = 10000
    projection_mode: str = "shadow"
    intent_header_budget: int = 500
    wo_status_budget: int = 2000
    ho3_budget: int = 2000


class ContextProjector:
    """Build structured context text with stable output shape."""

    def __init__(self, config: ProjectionConfig):
        self._config = config

    def project(
        self,
        liveness: Optional[LivenessState],
        ho3_artifacts: List[Dict[str, Any]],
        user_message: str,
        classification: Dict[str, Any],
        session_id: str,
    ) -> Dict[str, Any]:
        del session_id  # Reserved for future formatting/scoping.
        live = liveness or LivenessState()
        artifacts = ho3_artifacts if isinstance(ho3_artifacts, list) else []
        budget = max(1, int(self._config.projection_budget))

        active_intent_lines = self._render_active_intent(live)
        failed_lines = self._render_failed_items(live)
        open_wo_lines = self._render_open_work_orders(live)
        learning_lines = self._render_learning_context(artifacts)

        lines: List[str] = []
        tokens_used = 0

        sections = [
            (active_intent_lines, max(1, int(self._config.intent_header_budget))),
            (failed_lines, max(1, int(self._config.wo_status_budget // 2))),
            (open_wo_lines, max(1, int(self._config.wo_status_budget // 2))),
            (learning_lines, max(1, int(self._config.ho3_budget))),
        ]

        for section_lines, section_budget in sections:
            section_used = 0
            for line in section_lines:
                line_tokens = _estimate_tokens(line + "\n")
                if section_used + line_tokens > section_budget:
                    break
                if tokens_used + line_tokens > budget:
                    break
                lines.append(line)
                section_used += line_tokens
                tokens_used += line_tokens
            if tokens_used >= budget:
                break

        context_text = "\n".join(lines).strip()
        context_hash = hashlib.sha256(context_text.encode()).hexdigest()
        fragment_count = sum(1 for line in lines if line.startswith("- "))

        return {
            "user_input": user_message,
            "classification": classification,
            "assembled_context": {
                "context_text": context_text,
                "context_hash": context_hash,
                "fragment_count": fragment_count,
                "tokens_used": tokens_used,
            },
        }

    def _render_active_intent(self, liveness: LivenessState) -> List[str]:
        lines = ["## Active Intent"]
        if not liveness.active_intents:
            lines.append("(none)")
            return lines

        active_id = liveness.active_intents[0]
        intent = liveness.intents.get(active_id, {})
        objective = intent.get("objective") or "(unspecified)"
        status = intent.get("status") or "LIVE"
        declared = intent.get("declared_at") or "unknown"
        lines.append(f"Objective: {objective}")
        lines.append(f"Status: {status}")
        lines.append(f"Declared: {declared}")
        return lines

    def _render_failed_items(self, liveness: LivenessState) -> List[str]:
        lines = ["## Failed Items"]
        if not liveness.failed_items:
            lines.append("(none)")
            return lines
        for item in liveness.failed_items:
            wo_id = item.get("wo_id", "unknown")
            reason = item.get("reason", "").strip()
            if reason:
                lines.append(f"- {wo_id}: {reason}")
            else:
                lines.append(f"- {wo_id}")
        return lines

    def _render_open_work_orders(self, liveness: LivenessState) -> List[str]:
        lines = ["## Open Work Orders"]
        if not liveness.open_work_orders:
            lines.append("(none)")
            return lines
        for wo_id in liveness.open_work_orders:
            wo = liveness.work_orders.get(wo_id, {})
            wo_type = wo.get("wo_type") or "unknown"
            status = wo.get("status") or "OPEN"
            lines.append(f"- {wo_id} ({wo_type}): {status}")
        return lines

    def _render_learning_context(self, artifacts: List[Dict[str, Any]]) -> List[str]:
        lines = ["## Learning Context"]
        seen = set()
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            context_line = artifact.get("context_line")
            if not context_line and isinstance(artifact.get("content"), dict):
                context_line = artifact["content"].get("bias")
            if not isinstance(context_line, str):
                continue
            text = context_line.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            lines.append(f"- {text}")
        if len(lines) == 1:
            lines.append("(none)")
        return lines
