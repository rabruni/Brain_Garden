"""
Attention pipeline stage implementations.

Each stage is a pure function: (config, provider, state) -> StageOutput.
All I/O goes through ContextProvider (injectable for testing).
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ContextFragment:
    """A single piece of assembled context."""
    source: str          # "ledger", "registry", "file", "search", "custom"
    source_id: str       # Specific entry/file/query that produced this
    content: str         # The text content
    token_estimate: int  # Estimated tokens (for budget tracking)
    relevance_score: float | None  # 0-1 if scored, None otherwise


@dataclass
class StageOutput:
    """Result from a single pipeline stage."""
    fragments: list[ContextFragment]
    status: str  # "ok", "truncated", "timeout", "empty", "skipped", "retry"


@dataclass
class PipelineState:
    """Mutable state passed through the pipeline."""
    tier_scope: list[str]
    fragments: list[ContextFragment]
    budget_tracker: Any  # BudgetTracker from attention_service
    warnings: list[str]


# ---------------------------------------------------------------------------
# Context Provider (Dependency Injection)
# ---------------------------------------------------------------------------

class ContextProvider:
    """Injectable I/O layer for pipeline stages."""

    def __init__(self, plane_root: Path):
        self.plane_root = plane_root

    def read_ledger_entries(
        self,
        event_type: str | None = None,
        max_entries: int | None = None,
        recency: str | None = None,
        filters: dict | None = None,
    ) -> list[dict]:
        """Read entries from the ledger JSONL files."""
        entries = []
        ledger_dir = self.plane_root / "HOT" / "ledger"
        if not ledger_dir.exists():
            return entries
        for jsonl_file in sorted(ledger_dir.glob("*.jsonl")):
            try:
                for line in jsonl_file.read_text().strip().splitlines():
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    entries.append(entry)
            except (json.JSONDecodeError, OSError):
                continue
        if event_type:
            entries = [e for e in entries if e.get("event_type") == event_type]
        if filters:
            for key, val in filters.items():
                entries = [e for e in entries if e.get(key) == val]
        if max_entries:
            entries = entries[-max_entries:]
        return entries

    def read_registry(
        self,
        registry_name: str,
        filters: dict | None = None,
    ) -> list[dict]:
        """Read from a CSV registry."""
        registry_map = {
            "frameworks": "frameworks_registry.csv",
            "specs": "specs_registry.csv",
            "file_ownership": "file_ownership.csv",
        }
        filename = registry_map.get(registry_name, f"{registry_name}.csv")
        csv_path = self.plane_root / "HOT" / "registries" / filename
        if not csv_path.exists():
            return []
        rows = []
        try:
            with open(csv_path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(dict(row))
        except OSError:
            return []
        if filters:
            for key, val in filters.items():
                rows = [r for r in rows if r.get(key) == val]
        return rows

    def read_file(
        self,
        rel_path: str,
        max_size_bytes: int | None = None,
    ) -> str | None:
        """Read a file relative to plane_root."""
        full_path = self.plane_root / rel_path
        if not full_path.exists():
            return None
        try:
            content = full_path.read_text()
            if max_size_bytes is not None:
                content = content[:max_size_bytes]
            return content
        except OSError:
            return None

    def search_text(
        self,
        query: str,
        sources: list[str],
        tiers: list[str],
    ) -> list[tuple[str, str, float]]:
        """Simple keyword search across sources. Returns (content, source_id, score)."""
        results = []
        words = query.lower().split()
        if not words:
            return results

        if "ledger" in sources:
            for entry in self.read_ledger_entries():
                text = json.dumps(entry)
                matches = sum(1 for w in words if w in text.lower())
                if matches > 0:
                    score = matches / len(words)
                    results.append((text, f"ledger:{entry.get('event_type', 'unknown')}", score))

        if "files" in sources:
            for tier in tiers:
                tier_dir = self.plane_root / tier.upper()
                if not tier_dir.exists():
                    continue
                for fpath in tier_dir.rglob("*"):
                    if not fpath.is_file():
                        continue
                    try:
                        text = fpath.read_text()
                    except (OSError, UnicodeDecodeError):
                        continue
                    matches = sum(1 for w in words if w in text.lower())
                    if matches > 0:
                        score = matches / len(words)
                        rel = str(fpath.relative_to(self.plane_root))
                        results.append((text, f"file:{rel}", score))

        if "registry" in sources:
            for reg_name in ("frameworks", "specs", "file_ownership"):
                rows = self.read_registry(reg_name)
                for row in rows:
                    text = json.dumps(row)
                    matches = sum(1 for w in words if w in text.lower())
                    if matches > 0:
                        score = matches / len(words)
                        results.append((text, f"registry:{reg_name}", score))

        return results


# ---------------------------------------------------------------------------
# Token estimation helper
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str, chars_per_token: int = 4) -> int:
    """Rough estimate: ~4 chars per token for English text."""
    return len(text) // chars_per_token


# ---------------------------------------------------------------------------
# Stage implementations
# ---------------------------------------------------------------------------

def run_tier_select(config: dict, provider: ContextProvider, state: PipelineState) -> StageOutput:
    """Set tier scope from config. No fragments produced."""
    tiers = config.get("tiers", ["hot"])
    state.tier_scope = tiers
    return StageOutput(fragments=[], status="ok")


def run_ledger_query(config: dict, provider: ContextProvider, state: PipelineState) -> StageOutput:
    """Query ledger entries, wrap as fragments."""
    event_type = config.get("event_type")
    max_entries = config.get("max_entries")
    recency = config.get("recency")
    filters = config.get("filters")

    entries = provider.read_ledger_entries(
        event_type=event_type,
        max_entries=max_entries,
        recency=recency,
        filters=filters,
    )
    state.budget_tracker.add_query()

    fragments = []
    for entry in entries:
        content = json.dumps(entry)
        fragments.append(ContextFragment(
            source="ledger",
            source_id=entry.get("event_type", "unknown"),
            content=content,
            token_estimate=_estimate_tokens(content),
            relevance_score=None,
        ))

    status = "ok" if fragments else "empty"
    return StageOutput(fragments=fragments, status=status)


def run_registry_query(config: dict, provider: ContextProvider, state: PipelineState) -> StageOutput:
    """Query registry, wrap as fragments."""
    registry_name = config.get("registry", "frameworks")
    filters = config.get("filters")

    rows = provider.read_registry(registry_name, filters=filters)
    state.budget_tracker.add_query()

    fragments = []
    for row in rows:
        content = json.dumps(row)
        fragments.append(ContextFragment(
            source="registry",
            source_id=f"{registry_name}:{row.get(next(iter(row), ''), 'unknown')}",
            content=content,
            token_estimate=_estimate_tokens(content),
            relevance_score=None,
        ))

    status = "ok" if fragments else "empty"
    return StageOutput(fragments=fragments, status=status)


def run_file_read(config: dict, provider: ContextProvider, state: PipelineState) -> StageOutput:
    """Read files into fragments. Missing files warn but don't error."""
    paths = config.get("paths", [])
    max_size_bytes = config.get("max_size_bytes")

    fragments = []
    for rel_path in paths:
        content = provider.read_file(rel_path, max_size_bytes=max_size_bytes)
        if content is None:
            state.warnings.append(f"File not found: {rel_path}")
            continue
        fragments.append(ContextFragment(
            source="file",
            source_id=rel_path,
            content=content,
            token_estimate=_estimate_tokens(content),
            relevance_score=None,
        ))

    return StageOutput(fragments=fragments, status="ok")


def run_horizontal_search(config: dict, provider: ContextProvider, state: PipelineState) -> StageOutput:
    """Search across sources, score by relevance."""
    query = config.get("query", "")
    sources = config.get("sources", ["ledger", "files"])
    tiers = config.get("tiers", state.tier_scope)
    max_results = config.get("max_results", 20)
    relevance_threshold = config.get("relevance_threshold", 0.5)

    results = provider.search_text(query, sources, tiers)
    state.budget_tracker.add_query()

    # Filter by relevance threshold and sort descending
    results = [(content, src, score) for content, src, score in results if score >= relevance_threshold]
    results.sort(key=lambda x: x[2], reverse=True)
    results = results[:max_results]

    fragments = []
    for content, source_id, score in results:
        fragments.append(ContextFragment(
            source="search",
            source_id=source_id,
            content=content,
            token_estimate=_estimate_tokens(content),
            relevance_score=score,
        ))

    status = "ok" if fragments else "empty"
    return StageOutput(fragments=fragments, status=status)


def run_structuring(config: dict, provider: ContextProvider, state: PipelineState) -> StageOutput:
    """Dedup, sort, and truncate fragments to budget."""
    strategy = config.get("strategy", "chronological")
    max_tokens = config.get("max_tokens", 8000)

    fragments = list(state.fragments)

    # Dedup by content hash
    seen_hashes = set()
    deduped = []
    for frag in fragments:
        content_hash = hashlib.sha256(frag.content.encode()).hexdigest()
        if content_hash not in seen_hashes:
            seen_hashes.add(content_hash)
            deduped.append(frag)
    fragments = deduped

    # Sort
    if strategy == "relevance":
        fragments.sort(key=lambda f: f.relevance_score if f.relevance_score is not None else 0.0, reverse=True)
    elif strategy == "hierarchical":
        # Group by source type: registry > ledger > file > search
        source_order = {"registry": 0, "ledger": 1, "file": 2, "search": 3, "custom": 4}
        fragments.sort(key=lambda f: source_order.get(f.source, 5))
    # chronological = original order (default)

    # Truncate to max_tokens
    kept = []
    total_tokens = 0
    for frag in fragments:
        if total_tokens + frag.token_estimate > max_tokens:
            continue
        kept.append(frag)
        total_tokens += frag.token_estimate

    status = "truncated" if len(kept) < len(fragments) else "ok"
    return StageOutput(fragments=kept, status=status)


def run_halting(config: dict, provider: ContextProvider, state: PipelineState) -> StageOutput:
    """Check if assembled context is sufficient."""
    min_fragments = config.get("min_fragments", 1)
    min_tokens = config.get("min_tokens", 0)

    total_fragments = len(state.fragments)
    total_tokens = sum(f.token_estimate for f in state.fragments)

    fragments_ok = total_fragments >= min_fragments
    tokens_ok = total_tokens >= min_tokens

    if fragments_ok and tokens_ok:
        return StageOutput(fragments=[], status="ok")

    # Check if budget allows retry
    exceeded, _ = state.budget_tracker.check()
    if not exceeded:
        return StageOutput(fragments=[], status="retry")

    # Budget exhausted, can't retry
    return StageOutput(fragments=[], status="empty")


def run_custom(config: dict, provider: ContextProvider, state: PipelineState) -> StageOutput:
    """Call a registered custom handler."""
    handler_name = config.get("handler", "")
    handler = _CUSTOM_HANDLERS.get(handler_name)
    if handler is None:
        state.warnings.append(f"Custom handler not found: {handler_name}")
        return StageOutput(fragments=[], status="skipped")
    return handler(config, provider, state)


# Registry for custom handlers (extensibility hook)
_CUSTOM_HANDLERS: dict[str, Callable] = {}


# ---------------------------------------------------------------------------
# Stage dispatcher
# ---------------------------------------------------------------------------

STAGE_RUNNERS: dict[str, Callable] = {
    "tier_select": run_tier_select,
    "ledger_query": run_ledger_query,
    "registry_query": run_registry_query,
    "file_read": run_file_read,
    "horizontal_search": run_horizontal_search,
    "structuring": run_structuring,
    "halting": run_halting,
    "custom": run_custom,
}
