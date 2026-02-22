"""Pure bias selection policy for HO2 context injection."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, Iterable, List, Set


def _normalize_set(value: Any) -> Set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value} if value else set()
    if isinstance(value, Iterable):
        result = set()
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                result.add(text)
        return result
    text = str(value).strip()
    return {text} if text else set()


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _context_line(artifact: Dict[str, Any]) -> str:
    line = artifact.get("context_line")
    if isinstance(line, str) and line.strip():
        return line.strip()
    content = artifact.get("content", {})
    if isinstance(content, dict):
        bias = content.get("bias")
        if isinstance(bias, str) and bias.strip():
            return bias.strip()
    return ""


def _recency_score(artifact: Dict[str, Any], as_of_ts: str) -> float:
    as_of = _parse_iso(as_of_ts)
    if as_of is None:
        return 1.0
    stamp = (
        artifact.get("consolidation_event_ts")
        or artifact.get("window_end")
        or artifact.get("last_seen")
    )
    when = _parse_iso(stamp)
    if when is None:
        return 1.0
    age_hours = max((as_of - when).total_seconds() / 3600.0, 0.0)
    if age_hours <= 24.0:
        return 1.0
    if age_hours >= 168.0:
        return 0.5
    span = 168.0 - 24.0
    return 1.0 - ((age_hours - 24.0) / span) * 0.5


def _token_estimate(text: str) -> int:
    return max(1, math.ceil(len(text) / 4.0))


def select_biases(
    artifacts: List[Dict[str, Any]],
    turn_labels: Dict[str, Any],
    ho3_bias_budget: int,
    as_of_ts: str,
) -> List[Dict[str, Any]]:
    """Filter/rank HO3 artifacts for prompt injection without side effects."""
    turn_domain = _normalize_set(turn_labels.get("domain") if isinstance(turn_labels, dict) else None)
    turn_task = _normalize_set(turn_labels.get("task") if isinstance(turn_labels, dict) else None)
    has_turn_labels = bool(turn_domain or turn_task)
    as_of = _parse_iso(as_of_ts)

    eligible: List[Dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        if artifact.get("enabled", True) is False:
            continue

        expires = _parse_iso(artifact.get("expires_at_event_ts"))
        if as_of is not None and expires is not None and as_of >= expires:
            continue

        scope = str(artifact.get("scope", "session"))
        labels = artifact.get("labels", {})
        domain_labels = _normalize_set(labels.get("domain")) if isinstance(labels, dict) else set()
        task_labels = _normalize_set(labels.get("task")) if isinstance(labels, dict) else set()

        if not has_turn_labels:
            if scope != "global" and "labels" in artifact:
                continue
        else:
            label_match = bool((domain_labels & turn_domain) or (task_labels & turn_task))
            if scope != "global" and not label_match:
                continue

        line = _context_line(artifact)
        if not line:
            continue

        weight = float(artifact.get("weight", artifact.get("salience_weight", 0.5)) or 0.0)
        decay = float(artifact.get("decay_modifier", 1.0) or 0.0)
        score = weight * decay * _recency_score(artifact, as_of_ts)

        candidate = dict(artifact)
        candidate["context_line"] = line
        candidate["_score"] = score
        candidate["_token_estimate"] = _token_estimate(line)
        eligible.append(candidate)

    eligible.sort(key=lambda a: (a["_score"], a.get("artifact_id", "")), reverse=True)

    selected: List[Dict[str, Any]] = []
    budget_used = 0
    for artifact in eligible:
        token_cost = int(artifact["_token_estimate"])
        if budget_used + token_cost > max(0, int(ho3_bias_budget)):
            continue
        selected.append({
            k: v for k, v in artifact.items()
            if not k.startswith("_")
        })
        budget_used += token_cost

    return selected

