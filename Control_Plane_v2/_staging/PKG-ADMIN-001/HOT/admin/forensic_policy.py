"""Shared forensic policy defaults for ADMIN tools."""

from dataclasses import dataclass


@dataclass
class ForensicPolicy:
    """Shared defaults for forensic tool behavior.

    Used by forensic tools that expose raw evidence timelines.
    """

    verbosity: str = "full"
    include_prompts: bool = True
    include_tool_payloads: bool = True
    include_responses: bool = True
    include_evidence_ids: bool = True
    max_bytes: int = 500_000
    max_entries: int = 200
    truncation_marker: str = "[TRUNCATED at {bytes} bytes — use offset to continue]"


DEFAULT_POLICY = ForensicPolicy()
