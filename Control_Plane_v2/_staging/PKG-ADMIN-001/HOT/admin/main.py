"""ADMIN agent entrypoint.

Usage:
    python3 HOT/admin/main.py --root /path/to/cp --dev
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable
from unittest.mock import patch


REQUIRED_CONFIG_FIELDS = {
    "agent_id",
    "agent_class",
    "framework_id",
    "tier",
    "system_prompt",
    "attention",
    "tools",
    "budget",
    "permissions",
}


def _staging_root() -> Path:
    # .../PKG-ADMIN-001/HOT/admin/main.py -> .../_staging
    return Path(__file__).resolve().parents[3]


def _ensure_import_paths(root: Path | None = None) -> None:
    staging = _staging_root()
    add: list[Path] = [
        staging / "PKG-KERNEL-001" / "HOT" / "kernel",
        staging / "PKG-ANTHROPIC-PROVIDER-001" / "HOT" / "kernel",
        staging / "PKG-BOOT-MATERIALIZE-001" / "HOT" / "scripts",
        staging / "PKG-LAYOUT-002" / "HOT" / "scripts",
        staging / "PKG-KERNEL-001" / "HOT",
        # V2 Kitchener loop packages
        staging / "PKG-WORK-ORDER-001" / "HOT" / "kernel",
        staging / "PKG-LLM-GATEWAY-001" / "HOT" / "kernel",
        staging / "PKG-HO1-EXECUTOR-001" / "HO1" / "kernel",
        staging / "PKG-HO2-SUPERVISOR-001" / "HO2" / "kernel",
        staging / "PKG-SESSION-HOST-V2-001" / "HOT" / "kernel",
        staging / "PKG-SHELL-001" / "HOT" / "kernel",
        staging / "PKG-TOKEN-BUDGETER-001" / "HOT" / "kernel",
        staging / "PKG-HO3-MEMORY-001" / "HOT" / "kernel",
        staging / "PKG-HO3-MEMORY-001" / "HOT",
    ]
    if root is not None:
        add = [
            Path(root) / "HOT", Path(root) / "HOT" / "kernel", Path(root) / "HOT" / "scripts",
            Path(root) / "HO1" / "kernel", Path(root) / "HO2" / "kernel",
        ] + add
    for path in add:
        p = str(path)
        if p not in sys.path:
            sys.path.insert(0, p)


def load_admin_config(config_path: Path) -> dict:
    """Load and validate ADMIN config JSON."""
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(str(config_path))

    data = json.loads(config_path.read_text())
    missing = sorted(REQUIRED_CONFIG_FIELDS - set(data.keys()))
    if missing:
        raise ValueError(f"required fields missing: {', '.join(missing)}")
    return data


def _register_admin_tools(dispatcher, root: Path, runtime_config: dict | None = None) -> None:
    """Register built-in ADMIN tool handlers."""
    import re
    from collections import Counter
    try:
        from forensic_policy import DEFAULT_POLICY
        from ledger_forensics import (
            correlate_by_wo,
            entry_matches_session as lf_entry_matches_session,
            entry_session_id as lf_entry_session_id,
            entry_wo_id as lf_entry_wo_id,
            extract_stages,
            get_ledger_map as lf_get_ledger_map,
            parse_ts as lf_parse_ts,
            read_all_ledgers,
            read_entries as lf_read_entries,
            resolve_ledger_source as lf_resolve_ledger_source,
        )
    except ImportError:  # pragma: no cover - package-import fallback
        from .forensic_policy import DEFAULT_POLICY
        from .ledger_forensics import (
            correlate_by_wo,
            entry_matches_session as lf_entry_matches_session,
            entry_session_id as lf_entry_session_id,
            entry_wo_id as lf_entry_wo_id,
            extract_stages,
            get_ledger_map as lf_get_ledger_map,
            parse_ts as lf_parse_ts,
            read_all_ledgers,
            read_entries as lf_read_entries,
            resolve_ledger_source as lf_resolve_ledger_source,
        )

    runtime = dict(runtime_config or {})

    def _gate_check(args):
        gate = args.get("gate", "all")
        script = root / "HOT" / "scripts" / "gate_check.py"
        if not script.exists():
            return {"status": "error", "error": "gate_check.py not found"}
        cmd = [sys.executable, str(script), "--root", str(root)]
        if gate != "all":
            cmd.extend(["--gate", str(gate)])
        else:
            cmd.append("--all")
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return {
            "status": "ok" if proc.returncode == 0 else "error",
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    def _read_file(args):
        rel = args.get("path", "")
        path = (root / rel).resolve()
        if not str(path).startswith(str(root.resolve())):
            return {"status": "error", "error": "path escapes root"}
        if not path.exists() or not path.is_file():
            return {"status": "error", "error": "file not found"}
        return {"status": "ok", "path": rel, "content": path.read_text()}

    def _query_ledger(args):
        from ledger_client import LedgerClient

        ledger_map = {
            "governance": root / "HOT" / "ledger" / "governance.jsonl",
            "ho2m": root / "HO2" / "ledger" / "ho2m.jsonl",
            "ho1m": root / "HO1" / "ledger" / "ho1m.jsonl",
        }
        source = str(args.get("ledger", "governance"))
        ledger_path = ledger_map.get(source)
        if ledger_path is None:
            return {
                "status": "error",
                "error": f"Unknown ledger: {source}. Valid: governance, ho2m, ho1m",
            }

        ledger = LedgerClient(ledger_path=ledger_path)
        event_type = args.get("event_type")
        max_entries = int(args.get("max_entries", 10))
        if event_type:
            entries = ledger.read_by_event_type(str(event_type))[-max_entries:]
        else:
            entries = ledger.read_all()[-max_entries:]
        return {
            "status": "ok",
            "source": source,
            "count": len(entries),
            "entries": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "submission_id": e.submission_id,
                    "decision": e.decision,
                    "reason": e.reason or "",
                    "timestamp": e.timestamp,
                    "metadata": e.metadata or {},
                    "metadata_keys": sorted(e.metadata.keys()) if e.metadata else [],
                }
                for e in entries
            ],
        }

    def _parse_int(value, default: int, minimum: int = 0, maximum: int = 1000) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        if parsed < minimum:
            return minimum
        if parsed > maximum:
            return maximum
        return parsed

    def _paginate(items: list, limit_default: int = 20) -> tuple[list, int, int, int]:
        # Placeholder to keep compatibility with existing call sites.
        limit = _parse_int(limit_default, limit_default, minimum=1, maximum=1000)
        return items[:limit], len(items), limit, 0

    def _get_ledger_map() -> dict[str, Path]:
        return lf_get_ledger_map(root)

    def _resolve_ledger_source(source: str) -> tuple[Path | None, str | None]:
        return lf_resolve_ledger_source(root, source)

    def _read_entries(source: str) -> tuple[list, str | None]:
        return lf_read_entries(root, source)

    def _entry_session_id(entry) -> str | None:
        return lf_entry_session_id(entry)

    def _entry_wo_id(entry) -> str | None:
        return lf_entry_wo_id(entry)

    def _entry_matches_session(entry, session_id: str) -> bool:
        return lf_entry_matches_session(entry, session_id)

    def _parse_ts(ts: str):
        return lf_parse_ts(ts)

    def _apply_pagination(items: list, limit: int, offset: int) -> list:
        return items[offset: offset + limit]

    def _list_sessions(args):
        entries, err = _read_entries("ho2m")
        if err:
            return {"status": "error", "error": err}

        limit = _parse_int(args.get("limit", 20), 20, minimum=1, maximum=500)
        offset = _parse_int(args.get("offset", 0), 0, minimum=0, maximum=100000)

        sessions: dict[str, dict] = {}
        ordered = sorted(entries, key=lambda e: _parse_ts(e.timestamp))
        for entry in ordered:
            sid = _entry_session_id(entry)
            if not sid:
                continue
            current = sessions.setdefault(
                sid,
                {
                    "session_id": sid,
                    "started_at": None,
                    "ended_at": None,
                    "duration_seconds": None,
                    "turn_count": 0,
                    "status": "active",
                    "first_user_message": "",
                    "last_response_preview": "",
                    "_last_event_type": "",
                },
            )
            current["_last_event_type"] = entry.event_type
            if entry.event_type == "SESSION_START" and not current["started_at"]:
                current["started_at"] = entry.timestamp
            elif entry.event_type == "SESSION_END":
                current["ended_at"] = entry.timestamp
            elif entry.event_type == "TURN_RECORDED":
                current["turn_count"] += 1
                md = entry.metadata or {}
                if not current["first_user_message"] and md.get("user_message"):
                    current["first_user_message"] = str(md.get("user_message"))
                if md.get("response"):
                    current["last_response_preview"] = str(md.get("response"))[:160]

        session_rows = []
        for sid, data in sessions.items():
            if data["started_at"] and data["ended_at"]:
                data["status"] = "completed"
                duration = int((_parse_ts(data["ended_at"]) - _parse_ts(data["started_at"])).total_seconds())
                data["duration_seconds"] = max(0, duration)
            elif data["_last_event_type"] == "DEGRADATION":
                data["status"] = "errored"
            else:
                data["status"] = "active"
            data.pop("_last_event_type", None)
            session_rows.append(data)

        session_rows.sort(key=lambda s: _parse_ts(s.get("started_at") or ""), reverse=True)
        total = len(session_rows)
        paged = _apply_pagination(session_rows, limit, offset)
        return {
            "status": "ok",
            "count": total,
            "limit": limit,
            "offset": offset,
            "sessions": paged,
        }

    def _session_overview(args):
        session_id = str(args.get("session_id", "")).strip()
        if not session_id:
            return {"status": "error", "error": "session_id is required"}

        limit = _parse_int(args.get("limit", 20), 20, minimum=1, maximum=500)
        offset = _parse_int(args.get("offset", 0), 0, minimum=0, maximum=100000)

        all_sources = {}
        for source in ("ho2m", "ho1m", "governance"):
            entries, err = _read_entries(source)
            if err:
                return {"status": "error", "error": err}
            all_sources[source] = [e for e in entries if _entry_matches_session(e, session_id)]

        if not any(all_sources.values()):
            return {"status": "error", "error": f"session not found: {session_id}"}

        ho2_entries = sorted(all_sources["ho2m"], key=lambda e: _parse_ts(e.timestamp))
        ho1_entries = all_sources["ho1m"]
        gov_entries = all_sources["governance"]
        all_entries = ho2_entries + ho1_entries + gov_entries

        start_events = [e for e in ho2_entries if e.event_type == "SESSION_START"]
        end_events = [e for e in ho2_entries if e.event_type == "SESSION_END"]
        started_at = start_events[0].timestamp if start_events else ""
        ended_at = end_events[-1].timestamp if end_events else ""

        turn_events = [e for e in ho2_entries if e.event_type == "TURN_RECORDED"]
        turn_count = len(turn_events)
        first_user_message = ""
        if turn_events:
            first_user_message = str((turn_events[0].metadata or {}).get("user_message", ""))

        user_messages = [
            str((e.metadata or {}).get("user_message", ""))
            for e in turn_events
            if (e.metadata or {}).get("user_message")
        ]
        user_counter = Counter(user_messages)
        top_user_messages = [msg for msg, _ in user_counter.most_common()]

        errors = []
        warnings = []
        for e in sorted(all_entries, key=lambda x: _parse_ts(x.timestamp)):
            reason = str(e.reason or "")
            if e.event_type == "BUDGET_WARNING":
                warnings.append({"type": "budget_warning", "message": reason})
            if e.event_type in {"DEGRADATION", "WO_FAILED", "PROMPT_REJECTED"} or "budget_exhausted" in reason:
                errors.append({"type": e.event_type.lower(), "message": reason})

        tool_calls = [e for e in all_entries if e.event_type == "TOOL_CALL"]
        tool_stats: dict[str, dict[str, int]] = {}
        for e in tool_calls:
            md = e.metadata or {}
            tool_id = str(md.get("tool_id", "unknown"))
            status = str(md.get("status", "")).lower()
            stat = tool_stats.setdefault(tool_id, {"called": 0, "succeeded": 0, "failed": 0})
            stat["called"] += 1
            if status in {"ok", "success", "completed"}:
                stat["succeeded"] += 1
            else:
                stat["failed"] += 1

        input_total = 0
        output_total = 0
        for e in all_entries:
            md = e.metadata or {}
            input_total += int(md.get("input_tokens", 0) or 0)
            output_total += int(md.get("output_tokens", 0) or 0)

        wo_type_counter = Counter()
        for e in all_entries:
            md = e.metadata or {}
            wo_type = md.get("wo_type")
            if wo_type:
                wo_type_counter[str(wo_type)] += 1

        by_state = {
            "completed": len([e for e in all_entries if e.event_type == "WO_COMPLETED"]),
            "failed": len([e for e in all_entries if e.event_type == "WO_FAILED"]),
        }

        quality_gate_entries = [e for e in all_entries if e.event_type == "WO_QUALITY_GATE"]
        quality_passed = len([e for e in quality_gate_entries if str(e.decision).upper().startswith("ACCEPT")])
        quality_rejected = len(quality_gate_entries) - quality_passed

        tools_used = sorted(tool_stats.keys())
        if first_user_message:
            lead = f"User started with: {first_user_message}."
        else:
            lead = "Session activity was recorded."
        if tools_used:
            tools_text = f" Tools used: {', '.join(tools_used[:3])}."
        else:
            tools_text = " No tool calls were recorded."
        err_text = f" Encountered {len(errors)} errors." if errors else ""
        warn_text = f" Observed {len(warnings)} warnings." if warnings else ""
        end_text = " Session ended cleanly." if ended_at else " Session is still active."
        about = f"{lead}{tools_text}{err_text}{warn_text}{end_text}"

        duration_text = ""
        status = "completed" if ended_at else "active"
        if started_at and ended_at:
            duration_sec = max(0, int((_parse_ts(ended_at) - _parse_ts(started_at)).total_seconds()))
            duration_text = (
                f"{duration_sec // 60} minutes" if duration_sec >= 60 else f"{duration_sec} seconds"
            )
        elif errors:
            status = "errored"

        return {
            "status": "ok",
            "summary": {
                "session_id": session_id,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration": duration_text,
                "turn_count": turn_count,
                "status": status,
                "about": about,
                "top_user_messages": _apply_pagination(top_user_messages, limit, offset),
                "errors": _apply_pagination(errors, limit, offset),
                "warnings": _apply_pagination(warnings, limit, offset),
            },
            "diagnostics": {
                "tokens": {
                    "input_total": input_total,
                    "output_total": output_total,
                    "grand_total": input_total + output_total,
                },
                "work_orders": {
                    "total": len({wo for wo in (_entry_wo_id(e) for e in all_entries) if wo}),
                    "by_type": dict(wo_type_counter),
                    "by_state": by_state,
                },
                "tools": {
                    "total_calls": len(tool_calls),
                    "by_tool": tool_stats,
                },
                "quality_gates": {
                    "passed": quality_passed,
                    "rejected": quality_rejected,
                },
                "ledger_events": {
                    "ho2m": len(all_sources["ho2m"]),
                    "ho1m": len(all_sources["ho1m"]),
                    "governance": len(all_sources["governance"]),
                },
            },
            "limit": limit,
            "offset": offset,
        }

    def _reconstruct_session(args):
        session_id = str(args.get("session_id", "")).strip()
        if not session_id:
            return {"status": "error", "error": "session_id is required"}

        limit = _parse_int(args.get("limit", 100), 100, minimum=1, maximum=2000)
        offset = _parse_int(args.get("offset", 0), 0, minimum=0, maximum=100000)
        max_bytes = _parse_int(args.get("max_bytes", DEFAULT_POLICY.max_bytes), DEFAULT_POLICY.max_bytes, minimum=256, maximum=2_000_000)
        verbosity = str(args.get("verbosity", DEFAULT_POLICY.verbosity)).lower()
        if verbosity not in {"compact", "full"}:
            verbosity = DEFAULT_POLICY.verbosity
        include_prompts = bool(args.get("include_prompts", DEFAULT_POLICY.include_prompts))
        include_tool_payloads = bool(args.get("include_tool_payloads", DEFAULT_POLICY.include_tool_payloads))

        source_priority = {"ho2m": 0, "ho1m": 1, "governance": 2}
        normalized = []
        for source in ("ho2m", "ho1m", "governance"):
            entries, err = _read_entries(source)
            if err:
                return {"status": "error", "error": err}
            for e in entries:
                if not _entry_matches_session(e, session_id):
                    continue
                md = dict(e.metadata or {})
                payload = dict(md)
                if verbosity == "compact":
                    if e.event_type == "TURN_RECORDED":
                        payload = {
                            "user_message": md.get("user_message", ""),
                            "response": md.get("response", ""),
                        }
                    elif e.event_type == "TOOL_CALL":
                        payload = {
                            "tool_id": md.get("tool_id", ""),
                            "status": md.get("status", ""),
                        }
                        if include_tool_payloads:
                            if "arguments" in md:
                                payload["arguments"] = md.get("arguments")
                            if "result" in md:
                                payload["result"] = md.get("result")
                    elif e.event_type == "EXCHANGE":
                        payload = {
                            "input_tokens": md.get("input_tokens", 0),
                            "output_tokens": md.get("output_tokens", 0),
                            "outcome": md.get("outcome", ""),
                        }
                if not include_prompts:
                    payload.pop("prompt", None)
                    payload.pop("response", None)
                if not include_tool_payloads:
                    payload.pop("arguments", None)
                    payload.pop("result", None)

                actor = "ho2" if source == "ho2m" else ("ho1" if source == "ho1m" else "gateway")
                if e.event_type == "TURN_RECORDED":
                    actor = "user"
                elif e.event_type == "TOOL_CALL":
                    actor = "tool"

                normalized.append(
                    {
                        "timestamp": e.timestamp,
                        "source": source,
                        "event_type": e.event_type,
                        "actor": actor,
                        "turn_number": md.get("turn_number"),
                        "wo_id": _entry_wo_id(e),
                        "payload": payload,
                        "_id": e.id,
                    }
                )

        normalized.sort(
            key=lambda e: (
                _parse_ts(e.get("timestamp", "")),
                source_priority.get(e.get("source", "governance"), 99),
                str(e.get("_id", "")),
            )
        )
        total = len(normalized)
        page = _apply_pagination(normalized, limit, offset)

        base = {
            "status": "ok",
            "session_id": session_id,
            "event_count": total,
            "returned": 0,
            "limit": limit,
            "offset": offset,
            "truncated": False,
            "timeline": [],
        }
        timeline = []
        truncated = False
        for item in page:
            candidate = {
                "timestamp": item["timestamp"],
                "source": item["source"],
                "event_type": item["event_type"],
                "actor": item["actor"],
                "turn_number": item["turn_number"],
                "wo_id": item["wo_id"],
                "payload": item["payload"],
            }
            probe = dict(base)
            probe["timeline"] = timeline + [candidate]
            probe["returned"] = len(timeline) + 1
            size = len(json.dumps(probe, default=str).encode("utf-8"))
            if size > max_bytes:
                truncated = True
                break
            timeline.append(candidate)
        base["timeline"] = timeline
        base["returned"] = len(timeline)
        base["truncated"] = truncated
        return base

    def _query_ledger_full(args):
        source = str(args.get("ledger", "governance"))
        event_type = args.get("event_type")
        limit = _parse_int(
            args.get("limit", args.get("max_entries", DEFAULT_POLICY.max_entries)),
            DEFAULT_POLICY.max_entries,
            minimum=1,
            maximum=500,
        )
        offset = _parse_int(args.get("offset", 0), 0, minimum=0, maximum=100000)

        entries, err = _read_entries(source)
        if err:
            return {"status": "error", "error": err}
        if event_type:
            filtered = [e for e in entries if e.event_type == str(event_type)]
        else:
            filtered = list(entries)
        filtered = list(reversed(filtered))
        total = len(filtered)
        page = _apply_pagination(filtered, limit, offset)
        return {
            "status": "ok",
            "source": source,
            "count": total,
            "limit": limit,
            "offset": offset,
            "entries": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "submission_id": e.submission_id,
                    "decision": e.decision,
                    "reason": e.reason or "",
                    "timestamp": e.timestamp,
                    "metadata": e.metadata or {},
                }
                for e in page
            ],
        }

    def _grep_jsonl(args):
        source = str(args.get("ledger", "governance"))
        pattern = str(args.get("pattern", ""))
        if not pattern:
            return {"status": "error", "error": "pattern is required"}
        ledger_path, err = _resolve_ledger_source(source)
        if err:
            return {"status": "error", "error": err}
        if not ledger_path.exists():
            return {"status": "ok", "source": source, "pattern": pattern, "count": 0, "limit": 0, "offset": 0, "entries": []}
        limit = _parse_int(args.get("limit", DEFAULT_POLICY.max_entries), DEFAULT_POLICY.max_entries, minimum=1, maximum=1000)
        offset = _parse_int(args.get("offset", 0), 0, minimum=0, maximum=100000)
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return {"status": "error", "error": f"invalid regex: {e}"}

        matches = []
        with open(ledger_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                raw = line.rstrip("\n")
                if raw and regex.search(raw):
                    matches.append({"line_number": idx, "raw": raw})
        total = len(matches)
        page = _apply_pagination(matches, limit, offset)
        return {
            "status": "ok",
            "source": source,
            "pattern": pattern,
            "count": total,
            "limit": limit,
            "offset": offset,
            "entries": page,
        }

    def _trace_prompt_journey(args):
        session_id = str(args.get("session_id", "")).strip()
        if not session_id:
            return {"status": "error", "error": "session_id is required"}

        wo_filter = str(args.get("wo_id", "")).strip()
        turn_filter = args.get("turn_number")
        include_prompts = bool(args.get("include_prompts", DEFAULT_POLICY.include_prompts))
        include_tool_payloads = bool(args.get("include_tool_payloads", DEFAULT_POLICY.include_tool_payloads))
        include_responses = bool(args.get("include_responses", DEFAULT_POLICY.include_responses))
        include_evidence_ids = bool(args.get("include_evidence_ids", DEFAULT_POLICY.include_evidence_ids))
        limit = _parse_int(args.get("limit", DEFAULT_POLICY.max_entries), DEFAULT_POLICY.max_entries, minimum=1, maximum=5000)
        offset = _parse_int(args.get("offset", 0), 0, minimum=0, maximum=100000)
        max_bytes = _parse_int(args.get("max_bytes", DEFAULT_POLICY.max_bytes), DEFAULT_POLICY.max_bytes, minimum=256, maximum=2_000_000)

        entries_by_source = read_all_ledgers(root, session_id)
        grouped = correlate_by_wo(entries_by_source)

        if wo_filter:
            grouped = {wo_id: rows for wo_id, rows in grouped.items() if wo_id == wo_filter}

        ordered_wos = sorted(
            grouped.items(),
            key=lambda kv: _parse_ts(kv[1][0]["entry"].timestamp if kv[1] else ""),
        )
        ordered_wos = ordered_wos[offset: offset + limit]

        turns = []
        current_turn = None
        turn_counter = 0

        for wo_id, wo_entries in ordered_wos:
            wo_type = "unknown"
            for row in wo_entries:
                meta = row["entry"].metadata or {}
                if meta.get("wo_type"):
                    wo_type = str(meta.get("wo_type"))
                    break

            if wo_type == "classify" or current_turn is None:
                turn_counter += 1
                current_turn = {"turn_number": turn_counter, "wo_chain": []}
                turns.append(current_turn)

            stages = extract_stages(
                wo_entries,
                include_prompts=include_prompts,
                include_tool_payloads=include_tool_payloads,
                include_responses=include_responses,
                include_evidence_ids=include_evidence_ids,
            )
            current_turn["wo_chain"].append(
                {"wo_id": wo_id, "wo_type": wo_type, "stages": stages}
            )

            quality_stage = next((s for s in stages if s.get("stage") == "quality_gate"), None)
            if quality_stage and "quality_gate" not in current_turn:
                current_turn["quality_gate"] = {
                    key: quality_stage[key]
                    for key in ("decision", "reason", "evidence_id", "timestamp", "source")
                    if key in quality_stage
                }

        if turn_filter is not None:
            try:
                turn_num = int(turn_filter)
                turns = [t for t in turns if t.get("turn_number") == turn_num]
            except (TypeError, ValueError):
                return {"status": "error", "error": "turn_number must be an integer"}

        base = {
            "status": "ok",
            "session_id": session_id,
            "wo_count": 0,
            "llm_call_count": 0,
            "tool_call_count": 0,
            "turns": [],
            "limit": limit,
            "offset": offset,
            "truncated": False,
        }

        for turn in turns:
            probe = dict(base)
            probe["turns"] = base["turns"] + [turn]
            # recompute counts for probe
            probe_wo_count = 0
            probe_llm_calls = 0
            probe_tool_calls = 0
            for t in probe["turns"]:
                for wo in t.get("wo_chain", []):
                    probe_wo_count += 1
                    for stage in wo.get("stages", []):
                        if stage.get("stage") == "llm_response":
                            probe_llm_calls += 1
                        if stage.get("stage") == "tool_call":
                            probe_tool_calls += 1
            probe["wo_count"] = probe_wo_count
            probe["llm_call_count"] = probe_llm_calls
            probe["tool_call_count"] = probe_tool_calls

            size = len(json.dumps(probe, default=str).encode("utf-8"))
            if size > max_bytes:
                base["truncated"] = True
                base["truncation_marker"] = DEFAULT_POLICY.truncation_marker.format(bytes=max_bytes)
                break
            base = probe

        return base

    def _list_files(args):
        import fnmatch

        resolved_root = root.resolve()
        rel = str(args.get("path", "."))
        target = (root / rel).resolve()
        if not str(target).startswith(str(resolved_root)):
            return {"status": "error", "error": "path escapes root"}
        if not target.exists() or not target.is_dir():
            return {"status": "error", "error": "directory not found"}

        try:
            requested_depth = int(args.get("max_depth", 3))
        except (TypeError, ValueError):
            requested_depth = 3
        max_depth = max(1, min(requested_depth, 5))
        pattern = str(args.get("glob", "*"))
        files = []

        def _walk(dir_path: Path, depth: int):
            if depth > max_depth:
                return
            try:
                for entry in sorted(dir_path.iterdir()):
                    if entry.name.startswith(".") or entry.name == "__pycache__":
                        continue
                    entry_resolved = entry.resolve()
                    if not str(entry_resolved).startswith(str(resolved_root)):
                        continue
                    rel_path = str(entry_resolved.relative_to(resolved_root))
                    if entry.is_dir():
                        files.append({"path": rel_path + "/", "type": "dir"})
                        _walk(entry_resolved, depth + 1)
                    elif fnmatch.fnmatch(entry.name, pattern):
                        files.append({"path": rel_path, "type": "file", "size": entry_resolved.stat().st_size})
            except PermissionError:
                return

        _walk(target, 1)
        return {
            "status": "ok",
            "root": rel,
            "count": len(files),
            "files": files[:500],
        }

    def _list_packages(_args):
        installed_dir = root / "HOT" / "installed"
        if not installed_dir.exists():
            return {"status": "ok", "packages": []}
        packages = sorted(p.name for p in installed_dir.glob("PKG-*") if p.is_dir())
        return {"status": "ok", "packages": packages}

    def _show_runtime_config(_args):
        return {"status": "ok", "runtime": dict(runtime)}

    def _list_tuning_files(_args):
        files = [
            "HOT/config/admin_config.json",
            "HOT/config/layout.json",
            "HO1/contracts/classify.json",
            "HO1/contracts/synthesize.json",
            "HO1/prompt_packs/PRM-SYNTHESIZE-001.txt",
            "HO2/kernel/quality_gate.py",
            "HOT/kernel/llm_gateway.py",
            "HOT/admin/main.py",
        ]
        existing = [p for p in files if (root / p).exists()]
        return {
            "status": "ok",
            "count": len(files),
            "files": files,
            "existing": existing,
        }

    dispatcher.register_tool("gate_check", _gate_check)
    dispatcher.register_tool("read_file", _read_file)
    dispatcher.register_tool("query_ledger", _query_ledger)
    dispatcher.register_tool("list_files", _list_files)
    dispatcher.register_tool("list_packages", _list_packages)
    dispatcher.register_tool("list_sessions", _list_sessions)
    dispatcher.register_tool("session_overview", _session_overview)
    dispatcher.register_tool("reconstruct_session", _reconstruct_session)
    dispatcher.register_tool("query_ledger_full", _query_ledger_full)
    dispatcher.register_tool("grep_jsonl", _grep_jsonl)
    dispatcher.register_tool("trace_prompt_journey", _trace_prompt_journey)
    dispatcher.register_tool("show_runtime_config", _show_runtime_config)
    dispatcher.register_tool("list_tuning_files", _list_tuning_files)


def _register_dev_tools(dispatcher, root: Path, permissions: dict) -> list[dict]:
    """Register development-only tools. Only called when dual gate passes.

    Returns list of tool config dicts for tools_allowed construction.
    """
    import fnmatch
    import re
    import subprocess
    import time

    forbidden_patterns = permissions.get("forbidden", [])

    def _is_forbidden(rel_path: str) -> bool:
        for pattern in forbidden_patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
        return False

    def _resolve_safe(rel: str) -> tuple[Path | None, str | None]:
        """Resolve path relative to root, block traversal."""
        resolved_root = root.resolve()
        target = (root / rel).resolve()
        if not str(target).startswith(str(resolved_root)):
            return None, "path escapes root"
        return target, None

    # -- write_file_dev --
    def _write_file_dev(args):
        rel = str(args.get("path", ""))
        content = str(args.get("content", ""))
        create_dirs = bool(args.get("create_dirs", False))

        if not rel:
            return {"status": "error", "error": "path is required"}
        if len(content) > 1_000_000:
            return {"status": "error", "error": "content exceeds 1MB limit"}
        if _is_forbidden(rel):
            return {"status": "error", "error": f"path matches forbidden pattern: {rel}"}

        target, err = _resolve_safe(rel)
        if err:
            return {"status": "error", "error": err}

        created_dirs = False
        if create_dirs and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            created_dirs = True

        target.write_text(content)
        return {
            "status": "ok",
            "path": rel,
            "bytes_written": len(content.encode("utf-8")),
            "created_dirs": created_dirs,
        }

    # -- edit_file_dev --
    def _edit_file_dev(args):
        rel = str(args.get("path", ""))
        old_string = str(args.get("old_string", ""))
        new_string = str(args.get("new_string", ""))
        replace_all = bool(args.get("replace_all", False))

        if not rel or not old_string:
            return {"status": "error", "error": "path and old_string are required"}
        if _is_forbidden(rel):
            return {"status": "error", "error": f"path matches forbidden pattern: {rel}"}

        target, err = _resolve_safe(rel)
        if err:
            return {"status": "error", "error": err}
        if not target.exists() or not target.is_file():
            return {"status": "error", "error": "file not found"}

        original = target.read_text()
        count = original.count(old_string)
        if count == 0:
            return {"status": "error", "error": "old_string not found in file"}
        if not replace_all and count > 1:
            return {"status": "error", "error": f"old_string found {count} times; use replace_all=true or provide more context"}

        if replace_all:
            result = original.replace(old_string, new_string)
        else:
            result = original.replace(old_string, new_string, 1)

        target.write_text(result)
        return {
            "status": "ok",
            "path": rel,
            "replacements": count if replace_all else 1,
            "bytes_before": len(original.encode("utf-8")),
            "bytes_after": len(result.encode("utf-8")),
        }

    # -- grep_dev --
    def _grep_dev(args):
        pattern_str = str(args.get("pattern", ""))
        rel = str(args.get("path", "."))
        file_glob = str(args.get("glob", "*"))
        max_results = min(int(args.get("max_results", 50)), 200)
        context_lines = min(int(args.get("context_lines", 0)), 5)

        if not pattern_str:
            return {"status": "error", "error": "pattern is required"}

        try:
            regex = re.compile(pattern_str)
        except re.error as e:
            return {"status": "error", "error": f"invalid regex: {e}"}

        target, err = _resolve_safe(rel)
        if err:
            return {"status": "error", "error": err}
        if not target.exists():
            return {"status": "error", "error": "path not found"}

        results = []
        files_searched = 0
        skip_dirs = {".git", "__pycache__", ".DS_Store", "node_modules"}

        def search_file(fpath: Path):
            nonlocal files_searched
            try:
                if fpath.stat().st_size > 1_000_000:
                    return
                text = fpath.read_text(errors="replace")
            except (PermissionError, OSError):
                return
            files_searched += 1
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if len(results) >= max_results:
                    return
                if regex.search(line):
                    resolved_root = root.resolve()
                    rel_file = str(fpath.resolve().relative_to(resolved_root))
                    ctx_before = lines[max(0, i - context_lines):i] if context_lines else []
                    ctx_after = lines[i + 1:i + 1 + context_lines] if context_lines else []
                    results.append({
                        "file": rel_file,
                        "line_number": i + 1,
                        "line": line,
                        "context_before": ctx_before,
                        "context_after": ctx_after,
                    })

        if target.is_file():
            search_file(target)
        else:
            for fpath in sorted(target.rglob("*")):
                if len(results) >= max_results:
                    break
                if any(skip in fpath.parts for skip in skip_dirs):
                    continue
                if fpath.is_file() and fnmatch.fnmatch(fpath.name, file_glob):
                    search_file(fpath)

        return {
            "status": "ok",
            "pattern": pattern_str,
            "match_count": len(results),
            "files_searched": files_searched,
            "results": results,
        }

    # -- run_shell_dev --
    def _run_shell_dev(args):
        command = str(args.get("command", ""))
        timeout_sec = min(int(args.get("timeout", 30)), 120)
        cwd_rel = str(args.get("cwd", "."))
        max_output = 50000

        if not command:
            return {"status": "error", "error": "command is required"}

        cwd_target, err = _resolve_safe(cwd_rel)
        if err:
            return {"status": "error", "error": f"cwd: {err}"}
        if not cwd_target.is_dir():
            return {"status": "error", "error": "cwd is not a directory"}

        start = time.time()
        timed_out = False
        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout_sec, cwd=str(cwd_target),
            )
            stdout = proc.stdout
            stderr = proc.stderr
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            stdout = ""
            stderr = f"Command timed out after {timeout_sec} seconds"
            exit_code = -1
        duration = round(time.time() - start, 2)

        if len(stdout) > max_output:
            stdout = stdout[:max_output] + f"\n[TRUNCATED at {max_output} chars]"
        if len(stderr) > max_output:
            stderr = stderr[:max_output] + f"\n[TRUNCATED at {max_output} chars]"

        return {
            "status": "ok",
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "duration_seconds": duration,
        }

    # Register handlers
    dispatcher.register_tool("write_file_dev", _write_file_dev)
    dispatcher.register_tool("edit_file_dev", _edit_file_dev)
    dispatcher.register_tool("grep_dev", _grep_dev)
    dispatcher.register_tool("run_shell_dev", _run_shell_dev)

    # Return tool configs for tools_allowed and dispatcher injection
    dev_configs = [
        {
            "tool_id": "write_file_dev",
            "description": "Write or create a file within the plane root (dev only)",
            "handler": "tools.write_file_dev",
            "profile": "development",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path from plane root"},
                    "content": {"type": "string", "description": "File content to write"},
                    "create_dirs": {"type": "boolean", "default": False, "description": "Create parent directories if needed"},
                },
                "required": ["path", "content"],
            },
        },
        {
            "tool_id": "edit_file_dev",
            "description": "Find-and-replace in a file (dev only)",
            "handler": "tools.edit_file_dev",
            "profile": "development",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path from plane root"},
                    "old_string": {"type": "string", "description": "Exact string to find"},
                    "new_string": {"type": "string", "description": "Replacement string"},
                    "replace_all": {"type": "boolean", "default": False, "description": "Replace all occurrences"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
        {
            "tool_id": "grep_dev",
            "description": "Search file contents with regex (dev only)",
            "handler": "tools.grep_dev",
            "profile": "development",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for"},
                    "path": {"type": "string", "default": ".", "description": "Relative path to search in"},
                    "glob": {"type": "string", "default": "*", "description": "Filename glob filter"},
                    "max_results": {"type": "integer", "default": 50, "description": "Max matching lines (cap 200)"},
                    "context_lines": {"type": "integer", "default": 0, "description": "Lines of context (0-5)"},
                },
                "required": ["pattern"],
            },
        },
        {
            "tool_id": "run_shell_dev",
            "description": "Run a shell command with timeout (dev only)",
            "handler": "tools.run_shell_dev",
            "profile": "development",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {"type": "integer", "default": 30, "description": "Timeout in seconds (max 120)"},
                    "cwd": {"type": "string", "default": ".", "description": "Working directory (relative to plane root)"},
                },
                "required": ["command"],
            },
        },
    ]
    return dev_configs


def build_session_host_v2(
    root: Path,
    config_path: Path,
    dev_mode: bool = False,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
):
    """Compose the V2 Kitchener loop and return a Shell instance."""
    _ensure_import_paths(root=Path(root))

    from anthropic_provider import AnthropicProvider
    from contract_loader import ContractLoader
    from ho1_executor import HO1Executor
    from ho2_supervisor import HO2Config, HO2Supervisor
    from ledger_client import LedgerClient
    from llm_gateway import LLMGateway, RouterConfig
    from session_host_v2 import AgentConfig as V2AgentConfig, SessionHostV2
    from shell import Shell
    from token_budgeter import BudgetConfig, TokenBudgeter
    from tool_dispatch import ToolDispatcher
    from work_order import WorkOrder  # verify import works

    root = Path(root)
    cfg_dict = load_admin_config(config_path)

    # 1. Ledger clients — three separate paths
    (root / "HO2" / "ledger").mkdir(parents=True, exist_ok=True)
    (root / "HO1" / "ledger").mkdir(parents=True, exist_ok=True)
    ledger_gov = LedgerClient(ledger_path=root / "HOT" / "ledger" / "governance.jsonl")
    ledger_ho2m = LedgerClient(ledger_path=root / "HO2" / "ledger" / "ho2m.jsonl")
    ledger_ho1m = LedgerClient(ledger_path=root / "HO1" / "ledger" / "ho1m.jsonl")

    # 2. Token budgeter
    budget_cfg = cfg_dict.get("budget", {})
    budget_mode = str(budget_cfg.get("budget_mode", "enforce")).lower()
    if budget_mode not in {"enforce", "warn", "off"}:
        budget_mode = "enforce"
    budgeter = TokenBudgeter(
        ledger_client=ledger_gov,
        config=BudgetConfig(
            session_token_limit=budget_cfg.get("session_token_limit", 200000),
            enforcement_hard_limit=(budget_mode == "enforce"),
        ),
    )

    # 3. Contract loader + Tool dispatcher
    contract_loader = ContractLoader(contracts_dir=root / "HO1" / "contracts")
    dispatcher = ToolDispatcher(
        plane_root=root,
        tool_configs=cfg_dict.get("tools", []),
        permissions=cfg_dict.get("permissions", {}),
    )
    # 3b. Dev tools: dual gate check
    import os as _os
    tool_profile = cfg_dict.get("tool_profile", "production")
    env_flag = _os.environ.get("CP_ADMIN_ENABLE_RISKY_TOOLS", "0")
    dev_tool_configs: list[dict] = []
    if tool_profile == "development" and env_flag == "1":
        dev_tool_configs = _register_dev_tools(
            dispatcher, root=root, permissions=cfg_dict.get("permissions", {}),
        )
        # Inject dev tool configs into dispatcher for get_api_tools()
        for dtc in dev_tool_configs:
            dispatcher._tool_configs.append(dtc)
            dispatcher._declared.add(dtc["tool_id"])

    # Merge static + dev configs for tools_allowed
    all_tools = cfg_dict.get("tools", []) + dev_tool_configs

    # 4. LLM router tuning
    router_cfg = cfg_dict.get("router", {}) if isinstance(cfg_dict.get("router", {}), dict) else {}

    def _to_int(value, default: int, min_value: int = 0) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(min_value, parsed)

    llm_timeout_ms = _to_int(router_cfg.get("llm_timeout_ms", cfg_dict.get("llm_timeout_ms", 30000)), 30000, 1)
    llm_max_retries = _to_int(router_cfg.get("llm_max_retries", cfg_dict.get("llm_max_retries", 0)), 0, 0)
    llm_retry_backoff_ms = _to_int(router_cfg.get("llm_retry_backoff_ms", cfg_dict.get("llm_retry_backoff_ms", 0)), 0, 0)

    _register_admin_tools(
        dispatcher,
        root=root,
        runtime_config={
            "provider_id": "anthropic",
            "model_id": "claude-sonnet-4-5-20250929",
            "llm_timeout_ms": llm_timeout_ms,
            "llm_max_retries": llm_max_retries,
            "llm_retry_backoff_ms": llm_retry_backoff_ms,
            "budget_mode": budget_mode,
            "session_token_limit": budget_cfg.get("session_token_limit", 200000),
            "classify_budget": budget_cfg.get("classify_budget", 2000),
            "synthesize_budget": budget_cfg.get("synthesize_budget", 16000),
            "tool_profile": tool_profile,
            "enabled_tool_ids": [t["tool_id"] for t in all_tools],
        },
    )

    # 5. LLM Gateway
    gateway = LLMGateway(
        ledger_client=ledger_gov,
        budgeter=budgeter,
        config=RouterConfig(
            default_provider="anthropic",
            default_model="claude-sonnet-4-5-20250929",
            default_timeout_ms=llm_timeout_ms,
            max_retries=llm_max_retries,
            retry_backoff_ms=llm_retry_backoff_ms,
        ),
        dev_mode=dev_mode,
        budget_mode=budget_mode,
    )
    gateway.register_provider("anthropic", AnthropicProvider())

    # 6. HO1 Executor
    ho1_config = {
        "agent_id": cfg_dict.get("agent_id", "admin-001") + ".ho1",
        "agent_class": cfg_dict.get("agent_class", "ADMIN"),
        "tier": "ho1",
        "framework_id": cfg_dict.get("framework_id", "FMWK-000"),
        "package_id": "PKG-HO1-EXECUTOR-001",
        "budget_mode": budget_mode,
        "followup_min_remaining": budget_cfg.get("followup_min_remaining", 500),
    }
    ho1 = HO1Executor(
        gateway=gateway,
        ledger=ledger_ho1m,
        budgeter=budgeter,
        tool_dispatcher=dispatcher,
        contract_loader=contract_loader,
        config=ho1_config,
    )

    # 7. HO2 Supervisor
    ho3_cfg = cfg_dict.get("ho3", {})
    projection_cfg = cfg_dict.get("projection", {})
    ho2_config = HO2Config(
        attention_templates=["ATT-ADMIN-001"],
        ho2m_path=root / "HO2" / "ledger" / "ho2m.jsonl",
        ho1m_path=root / "HO1" / "ledger" / "ho1m.jsonl",
        budget_ceiling=budget_cfg.get("session_token_limit", 200000),
        classify_budget=budget_cfg.get("classify_budget", 2000),
        synthesize_budget=budget_cfg.get("synthesize_budget", 16000),
        followup_min_remaining=budget_cfg.get("followup_min_remaining", 500),
        budget_mode=budget_mode,
        tools_allowed=[t["tool_id"] for t in all_tools],
        # HO3 fields — all from config, no silent defaults
        ho3_enabled=ho3_cfg.get("enabled", False),
        ho3_memory_dir=Path(ho3_cfg["memory_dir"]) if ho3_cfg.get("memory_dir") else None,
        ho3_gate_count_threshold=ho3_cfg.get("gate_count_threshold", 5),
        ho3_gate_session_threshold=ho3_cfg.get("gate_session_threshold", 3),
        ho3_gate_window_hours=ho3_cfg.get("gate_window_hours", 168),
        consolidation_budget=budget_cfg.get("consolidation_budget", 4000),
        projection_budget=budget_cfg.get("projection_budget", 10000),
        projection_mode=projection_cfg.get("mode", "shadow"),
    )

    # 7b. HO3 Memory (optional — enabled via ho3.enabled in config)
    ho3_memory = None
    if ho3_cfg.get("enabled", False):
        try:
            from ho3_memory import HO3Memory, HO3MemoryConfig
            memory_dir = root / ho3_cfg.get("memory_dir", "HOT/memory")
            memory_dir.mkdir(parents=True, exist_ok=True)
            ho3_config = HO3MemoryConfig(
                memory_dir=memory_dir,
                gate_count_threshold=ho3_cfg.get("gate_count_threshold", 5),
                gate_session_threshold=ho3_cfg.get("gate_session_threshold", 3),
                gate_window_hours=ho3_cfg.get("gate_window_hours", 168),
                enabled=True,
            )
            ho3_memory = HO3Memory(plane_root=root, config=ho3_config)
        except ImportError:
            pass  # PKG-HO3-MEMORY-001 not installed — ho3_memory stays None

    ho2 = HO2Supervisor(
        plane_root=root,
        agent_class=cfg_dict.get("agent_class", "ADMIN"),
        ho1_executor=ho1,
        ledger_client=ledger_ho2m,
        token_budgeter=budgeter,
        config=ho2_config,
        ho3_memory=ho3_memory,
    )

    # 8. V2 Agent Config
    v2_agent_config = V2AgentConfig(
        agent_id=cfg_dict["agent_id"],
        agent_class=cfg_dict["agent_class"],
        framework_id=cfg_dict["framework_id"],
        tier=cfg_dict["tier"],
        system_prompt=cfg_dict["system_prompt"],
        attention=cfg_dict["attention"],
        tools=cfg_dict["tools"],
        budget=cfg_dict["budget"],
        permissions=cfg_dict["permissions"],
    )

    # 9. Session Host V2
    sh_v2 = SessionHostV2(
        ho2_supervisor=ho2,
        gateway=gateway,
        agent_config=v2_agent_config,
        ledger_client=ledger_gov,
    )

    # 10. Shell
    return Shell(sh_v2, v2_agent_config, input_fn, output_fn)


def run_cli(
    root: Path,
    config_path: Path,
    dev_mode: bool = False,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    """Interactive ADMIN loop."""
    root = Path(root)
    _ensure_import_paths(root=root)

    pristine_patch = None
    if dev_mode:
        # Dev/test mode may run outside governed roots; bypass append-only guard.
        pristine_patch = patch("kernel.pristine.assert_append_only", return_value=None)
        pristine_patch.start()
    from boot_materialize import boot_materialize

    mat_result = boot_materialize(root)
    if mat_result != 0:
        output_fn(f"WARNING: Boot materialization returned {mat_result} (non-fatal)")

    shell = build_session_host_v2(root, config_path, dev_mode, input_fn, output_fn)
    shell.run()
    if pristine_patch is not None:
        pristine_patch.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ADMIN Session Host")
    parser.add_argument("--root", required=True, help="Control Plane root path")
    parser.add_argument("--config", default="HOT/config/admin_config.json", help="Path to ADMIN config")
    parser.add_argument("--dev", action="store_true", help="Enable dev mode")
    args = parser.parse_args(argv)

    root = Path(args.root)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path

    return run_cli(root=root, config_path=config_path, dev_mode=args.dev)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
