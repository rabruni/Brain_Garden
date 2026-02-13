"""
Attention Service: assembles context for an agent before a prompt is sent.

Read-only at runtime. Runs a config-driven pipeline (attention templates)
to gather fragments from ledger, registries, and files.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kernel.attention_stages import (
    STAGE_RUNNERS,
    ContextFragment,
    ContextProvider,
    PipelineState,
    StageOutput,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AttentionRequest:
    """Input to the attention service."""
    agent_id: str
    agent_class: str
    framework_id: str
    tier: str
    work_order_id: str
    session_id: str
    prompt_contract: dict
    template_override: str | None = None


@dataclass
class BudgetUsed:
    """Actual budget consumption."""
    tokens_assembled: int
    queries_executed: int
    elapsed_ms: int


@dataclass
class StageResult:
    """Trace entry for one pipeline stage."""
    stage: str
    type: str
    fragments_produced: int
    tokens_produced: int
    duration_ms: int
    status: str


@dataclass
class AssembledContext:
    """Output from the attention service."""
    context_text: str
    context_hash: str
    fragments: list[ContextFragment]
    template_id: str
    pipeline_trace: list[StageResult]
    budget_used: BudgetUsed
    warnings: list[str]


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def estimate_tokens(text: str, chars_per_token: int = 4) -> int:
    """Rough estimate: ~4 chars per token for English text."""
    return len(text) // chars_per_token


# ---------------------------------------------------------------------------
# Budget Tracker
# ---------------------------------------------------------------------------

class BudgetTracker:
    """Tracks budget consumption against limits."""

    def __init__(
        self,
        max_tokens: int | None = None,
        max_queries: int | None = None,
        timeout_ms: int | None = None,
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

    def check(self) -> tuple[bool, str]:
        """Check if any budget limit is exceeded. Returns (exceeded, which_limit)."""
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


# ---------------------------------------------------------------------------
# Context Cache
# ---------------------------------------------------------------------------

class ContextCache:
    """In-memory TTL cache for assembled contexts."""

    def __init__(self, default_ttl_seconds: int = 60):
        self.default_ttl_seconds = default_ttl_seconds
        self._store: dict[tuple, tuple[float, AssembledContext]] = {}

    def get(self, key: tuple) -> AssembledContext | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, ctx = entry
        if time.monotonic() - ts > self.default_ttl_seconds:
            del self._store[key]
            return None
        return ctx

    def put(self, key: tuple, context: AssembledContext) -> None:
        self._store[key] = (time.monotonic(), context)

    def _make_key(self, request: AttentionRequest) -> tuple:
        return (
            request.template_override or "__resolved__",
            request.agent_class,
            request.work_order_id,
            request.session_id,
        )


# ---------------------------------------------------------------------------
# Attention Service
# ---------------------------------------------------------------------------

class AttentionService:
    """Main entry point. Resolves template, merges required_context, runs pipeline."""

    def __init__(self, plane_root: Path, config: dict | None = None):
        self.plane_root = plane_root
        self.config = config or {}
        self.cache = ContextCache(
            default_ttl_seconds=self.config.get("cache_ttl_seconds", 60),
        )
        self.context_provider: Any = ContextProvider(plane_root)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def assemble(self, request: AttentionRequest) -> AssembledContext:
        """Main entry point. Runs full pipeline."""
        # 1. Check cache
        cache_key = self.cache._make_key(request)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        # 2. Resolve template
        template = self.resolve_template(request)
        template_id = template["template_id"]

        # 3. Merge required_context from prompt contract
        required_context = request.prompt_contract.get("required_context", {})
        pipeline_def = list(template.get("pipeline", []))
        pipeline_def = self._merge_required_context(pipeline_def, required_context)

        # 4. Create BudgetTracker
        budget_config = template.get("budget", {})
        budget_tracker = BudgetTracker(
            max_tokens=budget_config.get("max_context_tokens"),
            max_queries=budget_config.get("max_queries"),
            timeout_ms=budget_config.get("timeout_ms"),
        )

        # 5. Run pipeline
        fallback = template.get("fallback", {})
        fragments, trace, warnings = self._run_pipeline(
            pipeline_def, budget_tracker, fallback,
        )

        # 6. Check on_empty fallback
        if not fragments:
            on_empty = fallback.get("on_empty", "proceed_empty")
            if on_empty == "fail":
                raise RuntimeError("No context assembled and on_empty is 'fail'")
            # proceed_empty or use_default: continue with empty

        # 7. Build AssembledContext
        context_text = "\n\n".join(f.content for f in fragments)
        context_hash = hashlib.sha256(context_text.encode()).hexdigest()

        result = AssembledContext(
            context_text=context_text,
            context_hash=context_hash,
            fragments=fragments,
            template_id=template_id,
            pipeline_trace=trace,
            budget_used=budget_tracker.to_budget_used(),
            warnings=warnings,
        )

        # 8. Cache result
        self.cache.put(cache_key, result)

        return result

    # -----------------------------------------------------------------------
    # Template Resolution
    # -----------------------------------------------------------------------

    def resolve_template(self, request: AttentionRequest) -> dict:
        """Find matching attention template."""
        templates_dir = self.plane_root / "HOT" / "attention_templates"

        # If template_override, load directly
        if request.template_override:
            tpl_path = templates_dir / f"{request.template_override}.json"
            if tpl_path.exists():
                return json.loads(tpl_path.read_text())
            # Try all files for matching template_id
            for p in templates_dir.glob("*.json"):
                tpl = json.loads(p.read_text())
                if tpl.get("template_id") == request.template_override:
                    return tpl
            # Not found — return default
            return self._default_template(request)

        # Scan all templates and score matches
        candidates: list[tuple[int, dict]] = []  # (specificity, template)
        for p in templates_dir.glob("*.json"):
            try:
                tpl = json.loads(p.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            applies_to = tpl.get("applies_to", {})
            specificity = self._match_specificity(applies_to, request)
            if specificity > 0:
                candidates.append((specificity, tpl))

        if not candidates:
            return self._default_template(request)

        # Sort by specificity descending
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_spec = candidates[0][0]
        best = [tpl for spec, tpl in candidates if spec == best_spec]

        if len(best) > 1:
            ids = [t["template_id"] for t in best]
            raise ValueError(
                f"Ambiguous template match: {ids} all match at specificity {best_spec}"
            )

        return best[0]

    def _match_specificity(self, applies_to: dict, request: AttentionRequest) -> int:
        """Score how well applies_to matches the request. Higher = more specific."""
        score = 0
        # framework_id match = 3 (highest specificity)
        fw_ids = applies_to.get("framework_id", [])
        if fw_ids and request.framework_id in fw_ids:
            score = max(score, 3)
        # agent_class match = 2
        classes = applies_to.get("agent_class", [])
        if classes and request.agent_class in classes:
            score = max(score, 2)
        # tier match = 1
        tiers = applies_to.get("tier", [])
        if tiers and request.tier in tiers:
            score = max(score, 1)
        return score

    def _default_template(self, request: AttentionRequest) -> dict:
        """Minimal default template when no match found."""
        pipeline = []
        # If prompt contract has file_refs, add file_read stages
        required_context = request.prompt_contract.get("required_context", {})
        file_refs = required_context.get("file_refs", [])
        if file_refs:
            pipeline.append({
                "stage": "default_file_read",
                "type": "file_read",
                "config": {"paths": file_refs},
            })
        pipeline.append({
            "stage": "default_structuring",
            "type": "structuring",
            "config": {"strategy": "chronological", "max_tokens": 8000},
        })
        return {
            "template_id": "__default__",
            "version": "0.0.0",
            "pipeline": pipeline,
        }

    # -----------------------------------------------------------------------
    # Required Context Merge
    # -----------------------------------------------------------------------

    def _merge_required_context(self, pipeline: list, required_context: dict) -> list:
        """Merge prompt contract's required_context into pipeline stages."""
        if not required_context:
            return pipeline

        new_stages = []

        # Ledger queries
        for lq in required_context.get("ledger_queries", []):
            event_type = lq.get("event_type")
            # Check if pipeline already has a ledger_query with same event_type
            already_present = any(
                s["type"] == "ledger_query"
                and s.get("config", {}).get("event_type") == event_type
                for s in pipeline
            )
            if not already_present:
                new_stages.append({
                    "stage": f"merged_ledger_{event_type}",
                    "type": "ledger_query",
                    "config": lq,
                })

        # Framework refs -> registry queries
        for fw_ref in required_context.get("framework_refs", []):
            new_stages.append({
                "stage": f"merged_framework_{fw_ref}",
                "type": "registry_query",
                "config": {"registry": "frameworks", "filters": {"framework_id": fw_ref}},
            })

        # File refs -> file_read stages
        file_refs = required_context.get("file_refs", [])
        if file_refs:
            # Check if pipeline already has a file_read with these paths
            existing_paths = set()
            for s in pipeline:
                if s["type"] == "file_read":
                    existing_paths.update(s.get("config", {}).get("paths", []))
            new_paths = [p for p in file_refs if p not in existing_paths]
            if new_paths:
                new_stages.append({
                    "stage": "merged_file_read",
                    "type": "file_read",
                    "config": {"paths": new_paths},
                })

        if not new_stages:
            return pipeline

        # Insert merged stages before structuring/halting
        insert_idx = len(pipeline)
        for i, stage in enumerate(pipeline):
            if stage["type"] in ("structuring", "halting"):
                insert_idx = i
                break

        return pipeline[:insert_idx] + new_stages + pipeline[insert_idx:]

    # -----------------------------------------------------------------------
    # Pipeline Runner
    # -----------------------------------------------------------------------

    def _run_pipeline(
        self,
        pipeline: list,
        budget_tracker: BudgetTracker,
        fallback: dict,
    ) -> tuple[list[ContextFragment], list[StageResult], list[str]]:
        """Execute pipeline stages sequentially."""
        fragments: list[ContextFragment] = []
        trace: list[StageResult] = []
        warnings: list[str] = []
        retry_done = False

        state = PipelineState(
            tier_scope=["hot"],
            fragments=fragments,
            budget_tracker=budget_tracker,
            warnings=warnings,
        )

        i = 0
        while i < len(pipeline):
            stage_def = pipeline[i]
            stage_name = stage_def.get("stage", f"stage_{i}")
            stage_type = stage_def.get("type", "unknown")
            stage_config = stage_def.get("config", {})
            enabled = stage_def.get("enabled", True)

            if not enabled:
                trace.append(StageResult(
                    stage=stage_name,
                    type=stage_type,
                    fragments_produced=0,
                    tokens_produced=0,
                    duration_ms=0,
                    status="skipped",
                ))
                i += 1
                continue

            # Check budget before running
            exceeded, which = budget_tracker.check()
            if exceeded:
                on_timeout = fallback.get("on_timeout", "return_partial")
                if on_timeout == "fail":
                    raise RuntimeError(f"Budget exceeded ({which}) and on_timeout is 'fail'")
                if on_timeout == "use_cached":
                    # Caller handles cache lookup
                    pass
                # return_partial: break and return what we have
                warnings.append(f"Budget exceeded ({which}) at stage {stage_name}")
                break

            # Run the stage
            runner = STAGE_RUNNERS.get(stage_type)
            if runner is None:
                warnings.append(f"Unknown stage type: {stage_type}")
                trace.append(StageResult(
                    stage=stage_name,
                    type=stage_type,
                    fragments_produced=0,
                    tokens_produced=0,
                    duration_ms=0,
                    status="skipped",
                ))
                i += 1
                continue

            start_ms = time.monotonic()
            try:
                # Update state.fragments to current list so structuring/halting can see them
                state.fragments = fragments
                output = runner(stage_config, self.context_provider, state)
            except Exception as exc:
                warnings.append(f"Stage {stage_name} failed: {exc}")
                trace.append(StageResult(
                    stage=stage_name,
                    type=stage_type,
                    fragments_produced=0,
                    tokens_produced=0,
                    duration_ms=int((time.monotonic() - start_ms) * 1000),
                    status="error",
                ))
                i += 1
                continue

            duration_ms = int((time.monotonic() - start_ms) * 1000)

            # Collect fragments from the stage
            tokens_produced = sum(f.token_estimate for f in output.fragments)
            if stage_type == "structuring":
                # Structuring replaces the fragment list
                fragments = output.fragments
                state.fragments = fragments
                # Reset token count to match the structuring output
                budget_tracker.tokens_used = sum(f.token_estimate for f in fragments)
            elif output.fragments:
                fragments.extend(output.fragments)
                state.fragments = fragments
                budget_tracker.add_tokens(tokens_produced)

            trace.append(StageResult(
                stage=stage_name,
                type=stage_type,
                fragments_produced=len(output.fragments),
                tokens_produced=tokens_produced,
                duration_ms=duration_ms,
                status=output.status,
            ))

            # Handle halting retry
            if stage_type == "halting" and output.status == "retry" and not retry_done:
                retry_done = True
                # Re-run horizontal_search stages with relaxed params
                for j, s in enumerate(pipeline):
                    if s.get("type") == "horizontal_search" and s.get("enabled", True):
                        relaxed_config = dict(s.get("config", {}))
                        threshold = relaxed_config.get("relevance_threshold", 0.5)
                        relaxed_config["relevance_threshold"] = threshold * 0.5
                        max_r = relaxed_config.get("max_results", 20)
                        relaxed_config["max_results"] = max_r * 2
                        start_ms2 = time.monotonic()
                        try:
                            state.fragments = fragments
                            retry_output = STAGE_RUNNERS["horizontal_search"](
                                relaxed_config, self.context_provider, state
                            )
                            if retry_output.fragments:
                                fragments.extend(retry_output.fragments)
                                state.fragments = fragments
                            trace.append(StageResult(
                                stage=f"{s.get('stage', 'search')}_retry",
                                type="horizontal_search",
                                fragments_produced=len(retry_output.fragments),
                                tokens_produced=sum(f.token_estimate for f in retry_output.fragments),
                                duration_ms=int((time.monotonic() - start_ms2) * 1000),
                                status=retry_output.status,
                            ))
                        except Exception as exc:
                            warnings.append(f"Retry search failed: {exc}")
                # After retry, don't loop back to halting — just continue

            i += 1

        return fragments, trace, warnings
