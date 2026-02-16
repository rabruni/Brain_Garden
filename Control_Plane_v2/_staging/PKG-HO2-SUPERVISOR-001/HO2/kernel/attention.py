"""Attention retriever for HO2 cognitive dispatch.

Absorbed from PKG-ATTENTION-001. Two operations:
- horizontal_scan: reads HO2m + HO1m recent entries
- priority_probe: reads HO3m for north stars (initially empty)

Per FMWK-009: HO2 can read HO2m + HO1m. HO3m via POLICY_LOOKUP or pushed-down params.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ContextFragment:
    """A single piece of assembled context. Absorbed from attention_stages.py."""
    source: str          # "ledger", "registry", "file", "search"
    source_id: str
    content: str
    token_estimate: int
    relevance_score: Optional[float] = None


@dataclass
class BudgetUsed:
    """Actual budget consumption."""
    tokens_assembled: int
    queries_executed: int
    elapsed_ms: int


@dataclass
class AttentionContext:
    """Assembled context from attention retrieval."""
    context_text: str
    context_hash: str
    fragments: List[ContextFragment]
    template_id: str
    budget_used: BudgetUsed


class BudgetTracker:
    """Tracks budget consumption against limits. Absorbed from attention_service.py."""

    def __init__(
        self,
        max_tokens: Optional[int] = None,
        max_queries: Optional[int] = None,
        timeout_ms: Optional[int] = None,
    ):
        self.max_tokens = max_tokens
        self.max_queries = max_queries
        self.timeout_ms = timeout_ms
        self.tokens_used = 0
        self.queries_used = 0
        self._start_time = time.monotonic()

    def add_tokens(self, n: int) -> None:
        self.tokens_used += n

    def add_query(self) -> None:
        self.queries_used += 1

    def check(self) -> tuple:
        """Returns (exceeded: bool, which_limit: str)."""
        if self.max_tokens is not None and self.tokens_used > self.max_tokens:
            return True, "tokens"
        if self.max_queries is not None and self.queries_used > self.max_queries:
            return True, "queries"
        if self.timeout_ms is not None and self.elapsed_ms > self.timeout_ms:
            return True, "timeout"
        return False, ""

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._start_time) * 1000)

    def to_budget_used(self) -> BudgetUsed:
        return BudgetUsed(
            tokens_assembled=self.tokens_used,
            queries_executed=self.queries_used,
            elapsed_ms=self.elapsed_ms,
        )


class ContextProvider:
    """Injectable I/O layer for reading ledger entries. Absorbed from attention_stages.py."""

    def __init__(self, plane_root: Path):
        self.plane_root = plane_root

    def read_ledger_entries(
        self,
        ledger_path: Optional[Path] = None,
        event_type: Optional[str] = None,
        max_entries: Optional[int] = None,
        filters: Optional[Dict] = None,
    ) -> List[Dict]:
        """Read entries from a ledger JSONL file."""
        entries = []
        if ledger_path is None:
            ledger_dir = self.plane_root / "HOT" / "ledger"
        else:
            ledger_dir = ledger_path if ledger_path.is_dir() else ledger_path.parent
        if not ledger_dir.exists():
            return entries
        pattern = "*.jsonl"
        for jsonl_file in sorted(ledger_dir.glob(pattern)):
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
                entries = [e for e in entries if e.get(key) == val or
                           (isinstance(e.get("metadata", {}), dict) and
                            e.get("metadata", {}).get("provenance", {}).get(key) == val)]
        if max_entries:
            entries = entries[-max_entries:]
        return entries


def _estimate_tokens(text: str, chars_per_token: int = 4) -> int:
    return len(text) // chars_per_token


class AttentionRetriever:
    """Retrieves context for HO2 cognitive dispatch.

    Two operations per FMWK-009 visibility:
    - horizontal_scan: reads HO2m + HO1m (HO2 can read both)
    - priority_probe: reads HO3m via POLICY_LOOKUP (initially empty)
    """

    def __init__(
        self,
        plane_root: Path,
        context_provider: ContextProvider,
        config: Any,
    ):
        self._plane_root = plane_root
        self._provider = context_provider
        self._config = config

    def horizontal_scan(self, session_id: str) -> AttentionContext:
        """Read recent HO2m entries for this session."""
        budget = BudgetTracker(
            max_tokens=getattr(self._config, 'attention_budget_tokens', 10000),
            max_queries=getattr(self._config, 'attention_budget_queries', 20),
            timeout_ms=getattr(self._config, 'attention_timeout_ms', 5000),
        )

        fragments: List[ContextFragment] = []

        # Read HO2m entries
        ho2m_path = getattr(self._config, 'ho2m_path', None)
        ho2m_entries = self._provider.read_ledger_entries(
            ledger_path=ho2m_path,
            max_entries=20,
            filters={"session_id": session_id},
        )
        budget.add_query()

        for entry in ho2m_entries:
            content = json.dumps(entry, sort_keys=True)
            tokens = _estimate_tokens(content)
            exceeded, _ = budget.check()
            if exceeded:
                break
            budget.add_tokens(tokens)
            fragments.append(ContextFragment(
                source="ledger",
                source_id=f"ho2m:{entry.get('event_type', 'unknown')}",
                content=content,
                token_estimate=tokens,
            ))

        # Read HO1m entries (per FMWK-009: HO2 can read HO1m)
        ho1m_path = getattr(self._config, 'ho1m_path', None)
        if ho1m_path:
            ho1m_entries = self._provider.read_ledger_entries(
                ledger_path=ho1m_path,
                max_entries=10,
                filters={"session_id": session_id},
            )
            budget.add_query()

            for entry in ho1m_entries:
                content = json.dumps(entry, sort_keys=True)
                tokens = _estimate_tokens(content)
                exceeded, _ = budget.check()
                if exceeded:
                    break
                budget.add_tokens(tokens)
                fragments.append(ContextFragment(
                    source="ledger",
                    source_id=f"ho1m:{entry.get('event_type', 'unknown')}",
                    content=content,
                    token_estimate=tokens,
                ))

        # Resolve template
        template_id = self._resolve_template_id()

        context_text = "\n\n".join(f.content for f in fragments)
        context_hash = hashlib.sha256(context_text.encode()).hexdigest()

        return AttentionContext(
            context_text=context_text,
            context_hash=context_hash,
            fragments=fragments,
            template_id=template_id,
            budget_used=budget.to_budget_used(),
        )

    def priority_probe(self) -> AttentionContext:
        """Read HO3m for north stars and salience anchors.
        Initially returns empty context (HO3m not yet populated).
        Per FMWK-009: HO2 accesses HO3m via POLICY_LOOKUP syscall."""
        return AttentionContext(
            context_text="",
            context_hash=hashlib.sha256(b"").hexdigest(),
            fragments=[],
            template_id="__priority_probe__",
            budget_used=BudgetUsed(tokens_assembled=0, queries_executed=0, elapsed_ms=0),
        )

    def assemble_wo_context(
        self,
        horizontal: AttentionContext,
        priority: AttentionContext,
        user_message: str,
        classification: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge horizontal + priority context into assembled_context dict."""
        all_fragments = horizontal.fragments + priority.fragments
        budget_tokens = getattr(self._config, 'attention_budget_tokens', 10000)

        # Truncate to budget
        kept = []
        total = 0
        for f in all_fragments:
            if total + f.token_estimate > budget_tokens:
                break
            kept.append(f)
            total += f.token_estimate

        context_text = "\n\n".join(f.content for f in kept)
        context_hash = hashlib.sha256(context_text.encode()).hexdigest()

        return {
            "user_input": user_message,
            "classification": classification,
            "assembled_context": {
                "context_text": context_text,
                "context_hash": context_hash,
                "fragment_count": len(kept),
                "tokens_used": total,
            },
        }

    def _resolve_template_id(self) -> str:
        """Resolve attention template for this agent class."""
        templates = getattr(self._config, 'attention_templates', [])
        if templates:
            return templates[0]
        return "__default__"
