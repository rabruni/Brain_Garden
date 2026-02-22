"""Ledger forensics helpers for deterministic ADMIN tracing."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from ledger_client import LedgerClient
except ImportError:  # pragma: no cover - clean-room fallback path
    from kernel.ledger_client import LedgerClient


SOURCE_PRIORITY = {"ho2m": 0, "ho1m": 1, "governance": 2}


def get_ledger_map(root: Path) -> dict[str, Path]:
    return {
        "governance": root / "HOT" / "ledger" / "governance.jsonl",
        "ho2m": root / "HO2" / "ledger" / "ho2m.jsonl",
        "ho1m": root / "HO1" / "ledger" / "ho1m.jsonl",
    }


def resolve_ledger_source(root: Path, source: str) -> tuple[Path | None, str | None]:
    ledger_path = get_ledger_map(root).get(source)
    if ledger_path is None:
        return None, f"Unknown ledger: {source}. Valid: governance, ho2m, ho1m"
    return ledger_path, None


def read_entries(root: Path, source: str) -> tuple[list, str | None]:
    ledger_path, err = resolve_ledger_source(root, source)
    if err:
        return [], err
    if not ledger_path.exists():
        return [], None
    ledger = LedgerClient(ledger_path=ledger_path)
    return ledger.read_all(), None


def parse_ts(ts: str):
    if not ts:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def entry_session_id(entry) -> str | None:
    md = entry.metadata or {}
    prov = md.get("provenance", {}) if isinstance(md.get("provenance", {}), dict) else {}
    return (
        md.get("session_id")
        or prov.get("session_id")
        or md.get("_session_id")
        or (entry.submission_id if str(entry.submission_id).startswith("SES-") else None)
    )


def entry_wo_id(entry) -> str | None:
    md = entry.metadata or {}
    prov = md.get("provenance", {}) if isinstance(md.get("provenance", {}), dict) else {}
    work_order_id = prov.get("work_order_id") or md.get("work_order_id") or md.get("wo_id")
    if work_order_id:
        return str(work_order_id)
    if str(entry.submission_id).startswith("WO-"):
        return str(entry.submission_id)
    return None


def entry_matches_session(entry, session_id: str) -> bool:
    sid = entry_session_id(entry)
    if sid == session_id:
        return True
    wo_id = entry_wo_id(entry)
    return bool(wo_id and wo_id.startswith(f"WO-{session_id}-"))


def read_all_ledgers(root: Path, session_id: str) -> dict[str, list]:
    grouped: dict[str, list] = {"ho2m": [], "ho1m": [], "governance": []}
    for source in ("ho2m", "ho1m", "governance"):
        entries, _err = read_entries(root, source)
        grouped[source] = [e for e in entries if entry_matches_session(e, session_id)]
    return grouped


def order_chronologically(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        entries,
        key=lambda e: (
            parse_ts((e.get("entry").timestamp if e.get("entry") is not None else e.get("timestamp", ""))),
            SOURCE_PRIORITY.get(e.get("source", "governance"), 99),
            str((e.get("entry").id if e.get("entry") is not None else e.get("_id", ""))),
        ),
    )


def correlate_by_wo(entries_by_source: dict[str, list]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for source, entries in entries_by_source.items():
        for entry in entries:
            wo_id = entry_wo_id(entry)
            if not wo_id:
                continue
            grouped.setdefault(wo_id, []).append({"source": source, "entry": entry})

    for wo_id in list(grouped.keys()):
        grouped[wo_id] = order_chronologically(grouped[wo_id])
    return grouped


def _stage_base(stage: str, source: str, entry, include_evidence_ids: bool) -> dict[str, Any]:
    base = {
        "stage": stage,
        "timestamp": entry.timestamp,
        "source": source,
    }
    if include_evidence_ids:
        base["evidence_id"] = entry.id
    return base


def extract_stages(
    wo_entries: list[dict[str, Any]],
    include_prompts: bool = True,
    include_tool_payloads: bool = True,
    include_responses: bool = True,
    include_evidence_ids: bool = True,
) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []

    for item in order_chronologically(wo_entries):
        source = item["source"]
        entry = item["entry"]
        md = entry.metadata or {}
        event_type = entry.event_type

        if event_type == "WO_PLANNED":
            row = _stage_base("wo_planned", source, entry, include_evidence_ids)
            row["wo_type"] = md.get("wo_type", "")
            row["tier_target"] = md.get("tier_target", "")
            stages.append(row)
        elif event_type == "WO_DISPATCHED":
            row = _stage_base("wo_dispatched", source, entry, include_evidence_ids)
            row["tier_target"] = md.get("tier_target", "")
            stages.append(row)
        elif event_type == "WO_EXECUTING":
            stages.append(_stage_base("wo_executing", source, entry, include_evidence_ids))
        elif event_type == "DISPATCH":
            row = _stage_base("dispatch", source, entry, include_evidence_ids)
            row["decision"] = entry.decision
            stages.append(row)
        elif event_type == "EXCHANGE":
            prompt = md.get("prompt", "")
            response = md.get("response", "")
            prompt_stage = _stage_base("prompt_sent", source, entry, include_evidence_ids)
            if include_prompts and prompt:
                prompt_stage["prompt_text"] = prompt
            if prompt:
                prompt_stage["prompt_hash"] = f"sha256:{hashlib.sha256(str(prompt).encode()).hexdigest()}"
            prompt_stage["model_id"] = md.get("model_id", "")
            prompt_stage["provider_id"] = md.get("provider_id", "")
            stages.append(prompt_stage)

            response_stage = _stage_base("llm_response", source, entry, include_evidence_ids)
            if include_responses:
                response_stage["response_text"] = response
            response_stage["input_tokens"] = md.get("input_tokens", 0)
            response_stage["output_tokens"] = md.get("output_tokens", 0)
            response_stage["finish_reason"] = md.get("finish_reason", "")
            response_stage["latency_ms"] = md.get("latency_ms", 0)
            response_stage["outcome"] = md.get("outcome", "")
            stages.append(response_stage)
        elif event_type == "LLM_CALL":
            row = _stage_base("llm_call", source, entry, include_evidence_ids)
            row["input_tokens"] = md.get("input_tokens", 0)
            row["output_tokens"] = md.get("output_tokens", 0)
            row["model_id"] = md.get("model_id", "")
            row["latency_ms"] = md.get("latency_ms", 0)
            stages.append(row)
        elif event_type == "TOOL_CALL":
            row = _stage_base("tool_call", source, entry, include_evidence_ids)
            row["tool_id"] = md.get("tool_id", "")
            row["status"] = md.get("status", "")
            if include_tool_payloads:
                row["arguments"] = md.get("arguments")
                row["result"] = md.get("result")
                if "tool_error" in md:
                    row["tool_error"] = md.get("tool_error")
            stages.append(row)
        elif event_type == "WO_COMPLETED":
            row = _stage_base("wo_completed", source, entry, include_evidence_ids)
            row["cost"] = md.get("cost", {})
            row["output_result"] = md.get("output_result")
            stages.append(row)
        elif event_type == "WO_FAILED":
            row = _stage_base("wo_failed", source, entry, include_evidence_ids)
            row["error"] = md.get("error_message", entry.reason)
            row["error_code"] = md.get("error_code", "")
            stages.append(row)
        elif event_type == "WO_QUALITY_GATE":
            row = _stage_base("quality_gate", source, entry, include_evidence_ids)
            row["decision"] = md.get("decision", entry.decision)
            row["reason"] = entry.reason
            stages.append(row)

    return stages
