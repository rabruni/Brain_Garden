"""Targeted tests for QualityGate grounding checks (HANDOFF-29P)."""

from __future__ import annotations

import sys
from pathlib import Path


_staging = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_staging / "PKG-HO2-SUPERVISOR-001" / "HO2" / "kernel"))

from quality_gate import QualityGate


def test_quality_gate_rejects_ungrounded_source_claim():
    gate = QualityGate()
    result = gate.verify(
        output_result={"response_text": "I can see in the ledger that your prior turn failed."},
        acceptance_criteria={},
        wo_id="WO-TEST-UNGROUNDED",
    )
    assert result.decision == "reject"
    assert "ungrounded_source_claim" in result.reason


def test_quality_gate_accepts_source_claim_when_tool_evidence_present():
    gate = QualityGate()
    result = gate.verify(
        output_result={"response_text": "I can see in the ledger that your prior turn failed."},
        acceptance_criteria={"source_evidence_present": True},
        wo_id="WO-TEST-GROUNDED",
    )
    assert result.decision == "accept"
