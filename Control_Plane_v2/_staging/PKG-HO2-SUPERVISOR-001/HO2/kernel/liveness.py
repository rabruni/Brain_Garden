"""Pure liveness reducer for Context Authority snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LivenessState:
    intents: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    work_orders: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    active_intents: List[str] = field(default_factory=list)
    open_work_orders: List[str] = field(default_factory=list)
    failed_items: List[Dict[str, Any]] = field(default_factory=list)
    escalations: List[Dict[str, Any]] = field(default_factory=list)


def _entry_timestamp(entry: Dict[str, Any]) -> str:
    ts = entry.get("timestamp")
    return ts if isinstance(ts, str) else ""


def _entry_id(entry: Dict[str, Any], idx: int) -> str:
    eid = entry.get("id")
    if isinstance(eid, str) and eid:
        return eid
    return f"idx-{idx:08d}"


def _metadata(entry: Dict[str, Any]) -> Dict[str, Any]:
    meta = entry.get("metadata", {})
    return meta if isinstance(meta, dict) else {}


def _session_id(entry: Dict[str, Any]) -> str:
    meta = _metadata(entry)
    prov = meta.get("provenance", {})
    if isinstance(prov, dict):
        sid = prov.get("session_id")
        if isinstance(sid, str) and sid:
            return sid
    sid = meta.get("_session_id")
    if isinstance(sid, str) and sid:
        return sid
    sub = entry.get("submission_id")
    if isinstance(sub, str) and sub.startswith("SES-"):
        return sub
    return ""


def _intent_id(entry: Dict[str, Any]) -> str:
    meta = _metadata(entry)
    intent_id = meta.get("intent_id")
    return intent_id if isinstance(intent_id, str) else ""


def _work_order_id(entry: Dict[str, Any]) -> str:
    meta = _metadata(entry)
    prov = meta.get("provenance", {})
    if isinstance(prov, dict):
        wo = prov.get("work_order_id")
        if isinstance(wo, str) and wo:
            return wo
    wo = meta.get("wo_id")
    if isinstance(wo, str) and wo:
        return wo
    sub = entry.get("submission_id")
    if isinstance(sub, str) and sub.startswith("WO-"):
        return sub
    return ""


def _event_sort_key(entry: Dict[str, Any], idx: int):
    return (_entry_timestamp(entry), _entry_id(entry, idx), idx)


def reduce_liveness(
    ho2m_entries: List[Dict[str, Any]],
    ho1m_entries: List[Dict[str, Any]],
    session_id: Optional[str] = None,
) -> LivenessState:
    """Reduce lifecycle events into live/open/failed state using latest-event-wins."""
    state = LivenessState()
    all_entries = list(ho2m_entries or []) + list(ho1m_entries or [])

    if session_id:
        all_entries = [e for e in all_entries if _session_id(e) == session_id]

    # --- Intent lifecycle ---
    intent_events: Dict[str, List[Dict[str, Any]]] = {}
    for idx, entry in enumerate(all_entries):
        et = entry.get("event_type")
        if et not in ("INTENT_DECLARED", "INTENT_SUPERSEDED", "INTENT_CLOSED"):
            continue
        intent_id = _intent_id(entry)
        if not intent_id:
            continue
        intent_events.setdefault(intent_id, []).append({"entry": entry, "idx": idx})

    for intent_id, events in intent_events.items():
        events.sort(key=lambda e: _event_sort_key(e["entry"], e["idx"]))
        summary = {
            "status": "UNKNOWN",
            "scope": "session",
            "objective": "",
            "declared_at": None,
            "closed_at": None,
        }
        for ev in events:
            entry = ev["entry"]
            et = entry.get("event_type")
            meta = _metadata(entry)
            ts = _entry_timestamp(entry)
            if et == "INTENT_DECLARED":
                summary["status"] = "LIVE"
                summary["declared_at"] = summary["declared_at"] or ts
                summary["scope"] = meta.get("scope", summary["scope"])
                summary["objective"] = meta.get("objective", summary["objective"])
            elif et == "INTENT_SUPERSEDED":
                summary["status"] = "SUPERSEDED"
                summary["closed_at"] = ts
            elif et == "INTENT_CLOSED":
                summary["status"] = "CLOSED"
                summary["closed_at"] = ts
        state.intents[intent_id] = summary

    state.active_intents = sorted(
        [intent_id for intent_id, info in state.intents.items() if info.get("status") == "LIVE"]
    )

    # --- Work-order lifecycle ---
    wo_events: Dict[str, List[Dict[str, Any]]] = {}
    for idx, entry in enumerate(all_entries):
        et = entry.get("event_type")
        if et not in ("WO_PLANNED", "WO_DISPATCHED", "WO_COMPLETED", "ESCALATION"):
            continue
        wo_id = _work_order_id(entry)
        if not wo_id:
            continue
        wo_events.setdefault(wo_id, []).append({"entry": entry, "idx": idx})

    for wo_id, events in wo_events.items():
        events.sort(key=lambda e: _event_sort_key(e["entry"], e["idx"]))
        summary = {
            "status": "UNKNOWN",
            "intent_id": None,
            "wo_type": "",
            "planned_at": None,
            "completed_at": None,
        }
        for ev in events:
            entry = ev["entry"]
            et = entry.get("event_type")
            meta = _metadata(entry)
            ts = _entry_timestamp(entry)
            if et == "WO_PLANNED":
                summary["status"] = "OPEN"
                summary["planned_at"] = summary["planned_at"] or ts
                summary["wo_type"] = meta.get("wo_type", summary["wo_type"])
                summary["intent_id"] = meta.get("intent_id", summary["intent_id"])
            elif et == "WO_DISPATCHED":
                summary["status"] = "DISPATCHED"
                summary["planned_at"] = summary["planned_at"] or ts
                summary["wo_type"] = meta.get("wo_type", summary["wo_type"])
                summary["intent_id"] = meta.get("intent_id", summary["intent_id"])
            elif et == "WO_COMPLETED":
                summary["status"] = "COMPLETED"
                summary["completed_at"] = ts
            elif et == "ESCALATION":
                summary["status"] = "FAILED"
                summary["completed_at"] = ts
                state.escalations.append({
                    "wo_id": wo_id,
                    "reason": entry.get("reason", ""),
                    "timestamp": ts,
                })
        state.work_orders[wo_id] = summary
        if summary["status"] in ("OPEN", "DISPATCHED"):
            state.open_work_orders.append(wo_id)
        if summary["status"] == "FAILED":
            state.failed_items.append({
                "wo_id": wo_id,
                "reason": events[-1]["entry"].get("reason", ""),
                "timestamp": summary["completed_at"],
            })

    state.open_work_orders = sorted(set(state.open_work_orders))
    state.failed_items.sort(key=lambda x: (x.get("timestamp", ""), x.get("wo_id", "")))
    state.escalations.sort(key=lambda x: (x.get("timestamp", ""), x.get("wo_id", "")))
    return state

