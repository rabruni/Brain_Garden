# Builder Handoff #6: Ledger Query Service

## Mission

Build the ledger query service — the structured, provenance-indexed read layer over the append-only ledger. This is the foundation that attention's `ledger_query` stage, the signal detector, and the learning loops all depend on.

The existing `LedgerClient` has basic read capabilities (`read_all()`, `query_by_event_type()`, `read_recent()`, `read_entries_range()`), but these are all full-scan operations. The query service adds provenance-indexed filtering, time-windowed queries, aggregation, and cross-tier search — without modifying LedgerClient.

**CRITICAL CONSTRAINTS — read before doing anything:**

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. No exceptions.
3. **Package everything.** New code ships as packages with manifest.json, SHA256 hashes, proper dependencies.
4. **End-to-end verification.** Full install chain must pass all gates.
5. **No hardcoding.** Cache TTLs, page sizes, index rebuild thresholds — all config-driven.
6. **No file replacement.** Packages must NEVER overwrite another package's files.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .`
8. **Governance chain:** Use `spec_id: "SPEC-GATE-001"` and `framework_id: "FMWK-000"` in manifest.json (same pattern as PKG-PHASE2-SCHEMAS-001). Ship FMWK-006 manifest.yaml as an asset — it deploys to disk but isn't registry-registered yet.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                      CONSUMERS                               │
│  Attention Service (ledger_query stage)                       │
│  Signal Detector (pattern analysis)                          │
│  Learning Loops (outcome tracking)                           │
│  Flow Runner (WO history)                                    │
└────────────────────────┬─────────────────────────────────────┘
                         │ LedgerQuery
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                  LEDGER QUERY SERVICE                         │
│                                                              │
│  1. Parse query (structured filter object)                   │
│  2. Resolve tiers (which ledgers to search)                  │
│  3. Check index (use index if fresh, rebuild if stale)       │
│  4. Execute query (filter, window, sort)                     │
│  5. Aggregate (if requested: counts, sums, averages)         │
│  6. Paginate (offset + limit)                                │
│  7. Return results                                           │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│              LEDGER CLIENT (existing, not modified)           │
│  read_all(), read_recent(), query_by_event_type()            │
│  Segment rotation, hash chains, Merkle verification          │
└──────────────────────────────────────────────────────────────┘
```

The query service **wraps** LedgerClient — it does NOT modify it. It reads raw entries and provides structured filtering, indexing, and aggregation on top.

---

## Core Interface

```python
@dataclass
class LedgerQueryRequest:
    """Structured query over ledger entries."""

    # Provenance filters (all optional — unset = no filter)
    agent_id: str | None = None
    agent_class: str | None = None        # KERNEL.syntactic | KERNEL.semantic | ADMIN | RESIDENT
    framework_id: str | None = None       # FMWK-XXX
    package_id: str | None = None         # PKG-XXX
    work_order_id: str | None = None      # WO-YYYYMMDD-NNN
    session_id: str | None = None         # SES-XXXXXXXX

    # Event filters
    event_type: str | None = None         # PROMPT_SENT, WO_STARTED, etc.
    event_types: list[str] | None = None  # Multiple event types (OR)

    # Outcome filters
    outcome_status: str | None = None     # success, failure, partial, timeout, rejected
    min_quality_signal: float | None = None  # Minimum quality_signal (0-1)

    # Scope filters
    tier: str | None = None               # hot, ho2, ho1
    tiers: list[str] | None = None        # Multiple tiers (cross-tier query)
    domain_tags: list[str] | None = None  # Entries tagged with ALL these tags

    # Time window
    since: str | None = None              # ISO8601 timestamp or duration ("1h", "24h", "7d")
    until: str | None = None              # ISO8601 timestamp
    recency: str | None = None            # "session" (this session only), "today", "all"

    # Relational
    parent_event_id: str | None = None    # Direct parent
    root_event_id: str | None = None      # Root of causal chain

    # Pagination
    offset: int = 0
    limit: int = 50                       # Config-driven default
    sort: str = "timestamp_desc"          # timestamp_desc, timestamp_asc, quality_desc

    # Aggregation (if set, returns aggregates instead of entries)
    aggregate: str | None = None          # "count", "token_sum", "quality_avg", "group_by"
    group_by: str | None = None           # Field to group by (e.g., "agent_class", "framework_id")


@dataclass
class LedgerQueryResult:
    """Result of a ledger query."""
    entries: list[dict]           # Matching entries (empty if aggregate)
    total_count: int              # Total matches (before pagination)
    offset: int
    limit: int
    has_more: bool                # True if more results beyond this page
    query_ms: int                 # Query execution time
    tiers_searched: list[str]     # Which tiers were searched
    index_used: bool              # Whether index was used vs full scan
    aggregates: dict | None = None  # Aggregate results if requested


@dataclass
class AggregateResult:
    """Aggregation result."""
    count: int
    token_sum_input: int | None = None
    token_sum_output: int | None = None
    quality_avg: float | None = None
    quality_min: float | None = None
    quality_max: float | None = None
    groups: dict | None = None     # For group_by: {group_value: AggregateResult}
```

### Core Methods

```python
class LedgerQueryService:

    def __init__(self, plane_root: Path, config: dict | None = None):
        """Initialize with plane root and optional config."""

    def query(self, request: LedgerQueryRequest) -> LedgerQueryResult:
        """Execute a structured query. Main entry point."""

    def query_provenance(self, work_order_id: str) -> list[dict]:
        """Convenience: get all entries for a work order, across tiers."""

    def query_agent_history(self, agent_id: str, limit: int = 50) -> list[dict]:
        """Convenience: get an agent's execution history."""

    def query_session(self, session_id: str) -> list[dict]:
        """Convenience: get all entries for a session."""

    def query_outcomes(self, framework_id: str, since: str = "7d") -> AggregateResult:
        """Convenience: aggregate outcomes for a framework over a time window."""

    def rebuild_index(self, tier: str | None = None) -> dict:
        """Rebuild the in-memory index from ledger entries. Returns index stats."""

    def get_index_stats(self) -> dict:
        """Return current index state: size, freshness, hit rate."""
```

---

## Indexing Strategy

The existing LedgerClient reads `.jsonl` files sequentially. For small ledgers this is fine. For larger ledgers, the query service maintains an in-memory index.

### Index Structure

```python
# In-memory index built from ledger entries
index = {
    "by_agent_id":       defaultdict(list),   # agent_id → [entry_idx, ...]
    "by_agent_class":    defaultdict(list),   # agent_class → [entry_idx, ...]
    "by_framework_id":   defaultdict(list),   # framework_id → [entry_idx, ...]
    "by_work_order_id":  defaultdict(list),   # work_order_id → [entry_idx, ...]
    "by_session_id":     defaultdict(list),   # session_id → [entry_idx, ...]
    "by_event_type":     defaultdict(list),   # event_type → [entry_idx, ...]
    "by_outcome_status": defaultdict(list),   # outcome.status → [entry_idx, ...]
    "by_tier":           defaultdict(list),   # tier → [entry_idx, ...]
}
```

### Index Lifecycle

1. **Build on first query:** Index is built lazily on first query (not on init)
2. **Staleness detection:** Track last entry count per ledger. If new entries exist, index is stale.
3. **Incremental rebuild:** Only index new entries since last build (don't re-scan everything)
4. **Config-driven:** `index_rebuild_threshold` (number of new entries before auto-rebuild), `index_ttl_seconds` (max age before forced rebuild)
5. **No persistence:** Index is in-memory only. Rebuilds on service restart. This is intentional — the ledger is truth, the index is a cache.

### Index Field Extraction

Provenance fields live in `metadata` dict of LedgerEntry. The index builder extracts:
```python
def _extract_index_fields(entry: dict) -> dict:
    metadata = entry.get("metadata", {})
    provenance = metadata.get("provenance", {})
    outcome = metadata.get("outcome", {})
    scope = metadata.get("scope", {})
    return {
        "agent_id": provenance.get("agent_id"),
        "agent_class": provenance.get("agent_class"),
        "framework_id": provenance.get("framework_id"),
        "package_id": provenance.get("package_id"),
        "work_order_id": provenance.get("work_order_id"),
        "session_id": provenance.get("session_id"),
        "event_type": entry.get("event_type"),
        "outcome_status": outcome.get("status"),
        "tier": scope.get("tier"),
        "timestamp": entry.get("timestamp"),
    }
```

This maps directly to the `ledger_entry_metadata.schema.json` we built in Phase 2.

---

## Cross-Tier Queries

When `tiers` is set (e.g., `["hot", "ho2"]`), the query service:
1. Discovers ledger paths for each tier using `paths.py` (`get_control_plane_root()`)
2. Creates a LedgerClient for each tier
3. Reads entries from each
4. Merges results by timestamp
5. Applies filters across the merged set
6. Returns with `tiers_searched` indicating which tiers were included

Tier discovery uses the existing tier layout:
- HOT: `{plane_root}/ledger/` (governance ledger)
- HO2: `{plane_root}/ledger/work_orders/{wo_id}/` (per-WO ledgers)
- HO1: `{plane_root}/ledger/sessions/{session_id}/` (per-session ledgers)

---

## Time Window Parsing

The `since` field accepts:
- ISO8601 timestamps: `"2026-02-10T00:00:00Z"`
- Duration strings: `"1h"`, `"24h"`, `"7d"`, `"30d"`
- Special values: `"session"` (entries from current session only)

```python
def _parse_time_window(since: str) -> datetime:
    """Parse since string to datetime."""
    # Duration pattern: Nd, Nh, Nm
    # ISO8601 pattern: standard parse
    # "session": resolve from session_id in query
```

---

## Config Schema: query_config.schema.json

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://control-plane.local/schemas/query_config.schema.json",
  "title": "Ledger Query Configuration v1.0",
  "type": "object",
  "properties": {
    "default_page_size": {
      "type": "integer",
      "minimum": 1,
      "maximum": 1000,
      "default": 50,
      "description": "Default page size for queries"
    },
    "max_page_size": {
      "type": "integer",
      "minimum": 1,
      "maximum": 10000,
      "default": 500,
      "description": "Maximum allowed page size"
    },
    "index_rebuild_threshold": {
      "type": "integer",
      "minimum": 1,
      "default": 100,
      "description": "New entries before auto-rebuild of index"
    },
    "index_ttl_seconds": {
      "type": "integer",
      "minimum": 1,
      "default": 300,
      "description": "Max age of index before forced rebuild"
    },
    "cross_tier_enabled": {
      "type": "boolean",
      "default": true,
      "description": "Allow queries across multiple tiers"
    },
    "max_tiers_per_query": {
      "type": "integer",
      "minimum": 1,
      "default": 3,
      "description": "Maximum tiers searchable in one query"
    },
    "query_timeout_ms": {
      "type": "integer",
      "minimum": 100,
      "default": 5000,
      "description": "Timeout for a single query execution"
    }
  },
  "additionalProperties": true
}
```

---

## Framework: FMWK-006 Ledger Query

```yaml
framework_id: FMWK-006
title: Ledger Query Framework
version: "1.0.0"
status: active
ring: kernel
plane_id: hot
created_at: "2026-02-10T00:00:00Z"
assets:
  - ledger_query_standard.md
expected_specs:
  - SPEC-QUERY-001
invariants:
  - level: MUST
    statement: The query service MUST NOT modify ledger entries — it is read-only
  - level: MUST
    statement: All query filters MUST map to fields defined in ledger_entry_metadata.schema.json
  - level: MUST NOT
    statement: Page sizes, index TTLs, and rebuild thresholds MUST NOT be hardcoded
  - level: MUST
    statement: Cross-tier queries MUST merge results by timestamp and indicate which tiers were searched
  - level: MUST
    statement: The index is a cache, not truth — the ledger is always authoritative
  - level: MUST NOT
    statement: The query service MUST NOT depend on index freshness for correctness — stale index = slower, not wrong
path_authorizations:
  - "HOT/kernel/ledger_query.py"
  - "HOT/schemas/query_config.schema.json"
  - "HOT/FMWK-006_Ledger_Query/*.yaml"
  - "HOT/FMWK-006_Ledger_Query/*.md"
  - "HOT/tests/test_ledger_query.py"
required_gates:
  - G0
  - G1
  - G5
```

---

## Package Plan

### PKG-LEDGER-QUERY-001 (Layer 3)

Assets:
- `HOT/kernel/ledger_query.py` — query service: filtering, indexing, aggregation, cross-tier
- `HOT/schemas/query_config.schema.json` — query configuration schema
- `HOT/FMWK-006_Ledger_Query/manifest.yaml` — framework manifest
- `HOT/tests/test_ledger_query.py` — all tests

Dependencies:
- `PKG-KERNEL-001` (for LedgerClient, paths.py)

**Governance chain:** `spec_id: "SPEC-GATE-001"`, `framework_id: "FMWK-000"` in manifest.json.

---

## Test Plan (DTT — Tests First)

### Write ALL tests BEFORE any implementation.

**Basic Queries:**
1. `test_query_by_event_type` — filter by single event type
2. `test_query_by_event_types` — filter by multiple event types (OR)
3. `test_query_by_agent_id` — filter by specific agent
4. `test_query_by_agent_class` — filter by agent class
5. `test_query_by_framework_id` — filter by framework
6. `test_query_by_work_order_id` — filter by work order
7. `test_query_by_session_id` — filter by session
8. `test_query_by_outcome_status` — filter by success/failure/etc
9. `test_query_by_min_quality` — filter by minimum quality_signal
10. `test_query_by_domain_tags` — filter by tags (AND)

**Combined Filters:**
11. `test_combined_provenance_filters` — agent_class + framework_id together
12. `test_combined_provenance_and_outcome` — framework + success status
13. `test_combined_filters_narrow` — multiple filters narrow results correctly

**Time Windows:**
14. `test_since_iso8601` — filter by ISO8601 timestamp
15. `test_since_duration_hours` — filter by "24h"
16. `test_since_duration_days` — filter by "7d"
17. `test_since_session` — filter to current session only
18. `test_until_timestamp` — upper bound on time range
19. `test_since_and_until_range` — both bounds

**Relational:**
20. `test_query_by_parent_event_id` — find children of a specific entry
21. `test_query_by_root_event_id` — find all entries in a causal chain

**Pagination:**
22. `test_pagination_offset_limit` — correct slice returned
23. `test_pagination_has_more` — has_more flag correct
24. `test_pagination_total_count` — total count reflects all matches
25. `test_sort_timestamp_desc` — newest first (default)
26. `test_sort_timestamp_asc` — oldest first
27. `test_sort_quality_desc` — highest quality first

**Aggregation:**
28. `test_aggregate_count` — count of matching entries
29. `test_aggregate_token_sum` — sum of input + output tokens
30. `test_aggregate_quality_avg` — average quality_signal
31. `test_aggregate_group_by_agent_class` — grouped counts
32. `test_aggregate_group_by_framework` — grouped by framework

**Cross-Tier:**
33. `test_cross_tier_query` — search across hot + ho2
34. `test_cross_tier_merge_by_timestamp` — merged results in timestamp order
35. `test_single_tier_query` — restrict to one tier
36. `test_tiers_searched_reported` — tiers_searched in result

**Indexing:**
37. `test_index_built_on_first_query` — lazy initialization
38. `test_index_staleness_detected` — new entries trigger rebuild
39. `test_incremental_rebuild` — only new entries indexed
40. `test_stale_index_still_correct` — stale index → full scan fallback, still correct results
41. `test_index_stats` — get_index_stats() returns useful info

**Convenience Methods:**
42. `test_query_provenance_wo` — all entries for a work order
43. `test_query_agent_history` — agent's execution history
44. `test_query_session` — all entries in a session
45. `test_query_outcomes` — aggregate outcomes for a framework

**Edge Cases:**
46. `test_empty_ledger` — query on empty ledger returns empty
47. `test_no_matches` — query with filters that match nothing
48. `test_query_timeout` — query exceeding timeout_ms
49. `test_entries_without_metadata` — handles entries missing metadata fields gracefully
50. `test_query_ms_reported` — execution time in result

### End-to-End Install Test
1. Clean-room extract CP_BOOTSTRAP → install Layers 0-2
2. Install PKG-PHASE2-SCHEMAS-001
3. Install PKG-LEDGER-QUERY-001
4. All gates pass
5. Write test entries to ledger → query them → verify results

---

## Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| LedgerClient | `HOT/kernel/ledger_client.py` (conflated repo) | Underlying read API |
| LedgerEntry dataclass | `HOT/kernel/ledger_client.py:~line 46` | Entry structure |
| Ledger metadata schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/ledger_entry_metadata.schema.json` | Provenance field definitions |
| LedgerFactory | `HOT/kernel/ledger_factory.py` | Tier-aware ledger creation |
| paths.py | `_staging/PKG-KERNEL-001/HOT/kernel/paths.py` | get_control_plane_root() |
| Attention handoff | `_staging/BUILDER_HANDOFF_4_attention_service.md` | ledger_query stage (your consumer) |

---

## Design Principles (Non-Negotiable)

1. **Read-only.** The query service never modifies ledger entries. It is a pure read layer.
2. **Wraps, doesn't replace.** LedgerClient stays as-is. The query service imports and wraps it.
3. **Index is cache, not truth.** A stale index means slower queries, not wrong results. If the index is stale, fall back to full scan.
4. **Config-driven.** Page sizes, index TTLs, timeouts, rebuild thresholds — all from config.
5. **Graceful degradation.** Missing metadata fields → skip that filter, don't crash. Entries from before Phase 2 won't have provenance fields.
6. **Cross-tier by default.** The system is multi-tier. Queries should naturally span tiers unless restricted.
