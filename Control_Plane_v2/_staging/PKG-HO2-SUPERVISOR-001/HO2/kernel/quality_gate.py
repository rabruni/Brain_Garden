"""Quality Gate — Step 4 (Verification) of Modified Kitchener loop.

Binary accept/reject for MVP. Checks output_result for completeness.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class QualityGateResult:
    """Result from quality gate verification."""
    decision: str   # "accept" or "reject"
    reason: str
    wo_id: str


class QualityGate:
    """Verifies WO output against acceptance criteria.

    MVP checks:
    - output_result is not None
    - output_result is not empty
    - Contains response_text key (for synthesize WOs)
    - Response length > 0
    - No error markers
    """

    def __init__(self, config: Any = None):
        self._config = config

    @staticmethod
    def _has_source_visibility_claim(response_text: str) -> bool:
        text = (response_text or "").strip()
        if not text:
            return False
        lower = text.lower()

        # Do not flag explicit uncertainty/non-visibility statements.
        if (
            "i can't see" in lower
            or "i cannot see" in lower
            or "i do not have access" in lower
            or "i don't have access" in lower
            or "no evidence" in lower
        ):
            return False

        patterns = (
            r"\bi can see\b",
            r"\bi can read\b",
            r"\bi looked at\b",
            r"\bi checked\b",
            r"\bfrom (the )?(ledger|ledgers|file|files|code)\b",
            r"\bin (the )?(ledger|ledgers|file|files|code)\b",
        )
        return any(re.search(p, lower) for p in patterns)

    @staticmethod
    def _has_source_evidence(acceptance_criteria: Dict[str, Any]) -> bool:
        if bool(acceptance_criteria.get("source_evidence_present")):
            return True
        if bool(acceptance_criteria.get("source_evidence")):
            return True
        if bool(acceptance_criteria.get("prior_results")):
            return True
        if bool(acceptance_criteria.get("tool_outputs")):
            return True
        if bool(acceptance_criteria.get("assembled_context")):
            return True
        return False

    def verify(
        self,
        output_result: Dict[str, Any],
        acceptance_criteria: Dict[str, Any],
        wo_id: str,
    ) -> QualityGateResult:
        """Check WO output. Returns accept or reject."""
        if output_result is None:
            return QualityGateResult(
                decision="reject",
                reason="output_result is None",
                wo_id=wo_id,
            )
        if not output_result:
            return QualityGateResult(
                decision="reject",
                reason="output_result is empty",
                wo_id=wo_id,
            )
        # Check for response_text (synthesize WOs)
        response_text = output_result.get("response_text")
        if response_text is None:
            return QualityGateResult(
                decision="reject",
                reason="output_result missing response_text",
                wo_id=wo_id,
            )
        if not response_text:
            return QualityGateResult(
                decision="reject",
                reason="response_text is empty",
                wo_id=wo_id,
            )
        if self._has_source_visibility_claim(response_text) and not self._has_source_evidence(acceptance_criteria):
            return QualityGateResult(
                decision="reject",
                reason="ungrounded_source_claim: source visibility asserted without current-turn evidence",
                wo_id=wo_id,
            )
        # Check for error markers
        if output_result.get("error"):
            return QualityGateResult(
                decision="reject",
                reason=f"output contains error: {output_result['error']}",
                wo_id=wo_id,
            )
        return QualityGateResult(
            decision="accept",
            reason="output passes all quality checks",
            wo_id=wo_id,
        )
