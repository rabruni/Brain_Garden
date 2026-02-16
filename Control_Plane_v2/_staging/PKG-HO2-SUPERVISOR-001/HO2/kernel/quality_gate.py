"""Quality Gate — Step 4 (Verification) of Modified Kitchener loop.

Binary accept/reject for MVP. Checks output_result for completeness.
"""

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
