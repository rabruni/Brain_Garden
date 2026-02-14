# Builder Handoff #7: Signal Detector

## Mission

Build the signal detector — the component that discovers recurring patterns from ledger data. This implements "bottom-up signal emergence" from the design decisions: attention emerges from repeated useful activity, not just top-down declaration.

**Key design rule:** Signals SUGGEST, governance DECIDES. There is a hard firewall between emergence (automatic detection) and adoption (deliberate governance decision). The signal detector detects and proposes — it never adopts or changes system behavior on its own.

**Dual detection:** Statistical first (cheap, pure computation), semantic second (expensive, LLM-based). Only run semantic detection on candidates that pass statistical thresholds.

**CRITICAL CONSTRAINTS — read before doing anything:**

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. No exceptions.
3. **Package everything.** New code ships as packages with manifest.json, SHA256 hashes, proper dependencies.
4. **End-to-end verification.** Full install chain must pass all gates.
5. **No hardcoding.** Detection thresholds, window sizes, confidence levels, frequency cutoffs — all config-driven.
6. **No file replacement.** Packages must NEVER overwrite another package's files.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .`
8. **Governance chain:** Use `spec_id: "SPEC-GATE-001"` and `framework_id: "FMWK-000"` in manifest.json. Ship FMWK-008 manifest.yaml as an asset.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│              LEDGER (read via Query Service)                  │
│                                                              │
│  PROMPT_SENT, PROMPT_RECEIVED, WO_STARTED, WO_EXEC_COMPLETE │
│  Each with provenance, outcome, context_fingerprint          │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                   SIGNAL DETECTOR                            │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  STATISTICAL PASS (cheap, always runs)               │     │
│  │                                                      │     │
│  │  1. Frequency analysis: "agent class X fails 40%"    │     │
│  │  2. Anomaly detection: "response time spiked 3x"     │     │
│  │  3. Correlation: "budget exhaustion → failure"        │     │
│  │  4. Trend detection: "quality declining over 7d"      │     │
│  │                                                      │     │
│  │  Output: StatisticalCandidate[]                      │     │
│  └──────────────────────┬──────────────────────────────┘     │
│                         │ candidates above threshold          │
│                         ▼                                     │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  SEMANTIC PASS (expensive, optional, LLM-based)      │     │
│  │                                                      │     │
│  │  5. Pattern validation: "is this a real pattern?"     │     │
│  │  6. Root cause analysis: "why is this happening?"     │     │
│  │  7. Action suggestion: "what should change?"          │     │
│  │                                                      │     │
│  │  Output: SemanticCandidate[]                         │     │
│  └──────────────────────┬──────────────────────────────┘     │
│                         │                                     │
│                         ▼                                     │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  SIGNAL EMISSION                                     │     │
│  │                                                      │     │
│  │  Write SIGNAL_DETECTED to ledger                     │     │
│  │  (Governance decides what to do with it)             │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│             LEARNING LOOP ENGINE (consumer)                   │
│       Reads SIGNAL_DETECTED, generates proposals             │
└──────────────────────────────────────────────────────────────┘
```

---

## Signal Types

The detector looks for these pattern categories:

### 1. Failure Patterns
- "Agent class X fails at rate Y on task type Z" (above threshold)
- "Framework F produces failures when paired with attention template T"
- "Work orders with budget < N tokens fail 80% of the time"

### 2. Quality Patterns
- "Quality signal declining over time window for framework F"
- "Agent class X produces consistently higher quality than Y on same task type"
- "Prompt contract P produces lower quality than P' for same input type"

### 3. Resource Patterns
- "Budget exhaustion rate is N% for WOs of type T" (too low budget)
- "Average token usage for framework F is 30% of allocation" (over-allocated)
- "Response latency for provider P increased 3x over window"

### 4. Correlation Patterns
- "Context size above N tokens correlates with higher quality"
- "Attention template T with > 3 pipeline stages correlates with timeout"
- "Session-scoped queries produce better outcomes than global queries"

---

## Data Structures

```python
@dataclass
class DetectionWindow:
    """Time window for analysis."""
    since: str              # Duration: "1h", "24h", "7d"
    min_sample_size: int    # Minimum entries to analyze (below = insufficient data)

@dataclass
class StatisticalCandidate:
    """A pattern detected by statistical analysis."""
    detector_name: str       # Which detector found this
    pattern_type: str        # "failure_rate", "quality_trend", "resource_anomaly", "correlation"
    description: str         # Human-readable: "ADMIN agents fail 42% on registry_change WOs"
    confidence: float        # 0-1, statistical confidence
    evidence: dict           # Supporting data: counts, rates, p-values, etc.
    affected_scope: dict     # {agent_class, framework_id, event_type, ...} — what's affected
    window: DetectionWindow  # Time window analyzed
    sample_size: int         # How many entries were analyzed

@dataclass
class SemanticCandidate:
    """A pattern validated/enriched by LLM analysis."""
    statistical_candidate: StatisticalCandidate  # The original statistical finding
    validation: str          # "confirmed", "rejected", "inconclusive"
    root_cause: str | None   # LLM's analysis of why this pattern exists
    suggested_action: str | None  # What the LLM thinks should change
    llm_confidence: float    # 0-1, LLM's self-assessed confidence
    model_id: str            # Which model analyzed this
    tokens_used: dict        # {input: N, output: M}

@dataclass
class Signal:
    """A detected signal ready for emission to the ledger."""
    signal_id: str           # SIG-{timestamp}-{seq}
    pattern_type: str        # From StatisticalCandidate
    description: str         # Human-readable summary
    statistical_confidence: float
    semantic_confidence: float | None  # None if semantic pass was skipped
    evidence: dict           # Full evidence chain
    affected_scope: dict     # What in the system is affected
    suggested_action: str | None  # From semantic pass (or None)
    detection_method: str    # "statistical_only" or "statistical+semantic"
    created_at: str          # ISO timestamp
```

---

## Statistical Detectors

Each detector is a pluggable class. v1 ships 4 built-in detectors:

### FailureRateDetector
```python
class FailureRateDetector:
    """Detect when failure rates exceed thresholds."""

    def detect(self, entries: list[dict], config: dict) -> list[StatisticalCandidate]:
        """
        Config:
          threshold: 0.3 (30% failure rate triggers signal)
          group_by: ["agent_class", "framework_id"]  (group entries before computing rates)
          min_samples: 10 (need at least 10 entries per group)
        """
```

### QualityTrendDetector
```python
class QualityTrendDetector:
    """Detect declining or improving quality trends."""

    def detect(self, entries: list[dict], config: dict) -> list[StatisticalCandidate]:
        """
        Config:
          window_count: 3 (compare 3 consecutive windows)
          decline_threshold: 0.15 (15% decline triggers signal)
          improvement_threshold: 0.15 (15% improvement triggers signal)
          window_size: "24h" (each window is 24h)
        """
```

### ResourceAnomalyDetector
```python
class ResourceAnomalyDetector:
    """Detect unusual resource consumption patterns."""

    def detect(self, entries: list[dict], config: dict) -> list[StatisticalCandidate]:
        """
        Config:
          budget_exhaustion_threshold: 0.5 (50%+ of WOs exhaust budget)
          overallocation_threshold: 0.3 (using <30% of allocated budget)
          latency_spike_factor: 2.0 (2x normal latency triggers signal)
        """
```

### CorrelationDetector
```python
class CorrelationDetector:
    """Detect correlations between conditions and outcomes."""

    def detect(self, entries: list[dict], config: dict) -> list[StatisticalCandidate]:
        """
        Config:
          min_correlation: 0.5 (minimum correlation coefficient)
          factors: ["context_tokens", "pipeline_stages", "budget_ratio"]
          outcomes: ["quality_signal", "outcome_status"]
          min_samples: 20
        """
```

### Pluggable Detector Interface

```python
class BaseDetector:
    """Base class for statistical detectors."""

    name: str  # Detector name

    def detect(self, entries: list[dict], config: dict) -> list[StatisticalCandidate]:
        """Analyze entries and return pattern candidates."""
        raise NotImplementedError

    @staticmethod
    def extract_metric(entry: dict, field_path: str) -> Any:
        """Extract a nested field from an entry. E.g., 'outcome.quality_signal'"""
```

New detectors can be added by subclassing `BaseDetector` and registering in config.

---

## Semantic Pass

The semantic pass is **optional** and **expensive** (uses LLM tokens via the prompt router). It:
1. Takes statistical candidates above a confidence threshold
2. Formats the evidence as a structured prompt
3. Sends through the prompt router (if available)
4. Parses the LLM response into validation + root cause + suggested action

**v1 scope:** The semantic pass is a well-defined interface with a real implementation, BUT it requires the prompt router to be installed. If the router is not available (import fails), semantic detection is silently disabled and signals are emitted as statistical-only.

**State-gating pattern:** Semantic detection activates when the prompt router is installed. No import errors, no crashes — just graceful degradation to statistical-only mode.

```python
class SemanticAnalyzer:
    """LLM-based validation of statistical candidates."""

    def __init__(self, prompt_router=None):
        self._router = prompt_router
        self._available = prompt_router is not None

    @property
    def available(self) -> bool:
        return self._available

    def analyze(self, candidate: StatisticalCandidate) -> SemanticCandidate:
        """Validate a statistical candidate using LLM analysis."""
        if not self._available:
            raise RuntimeError("Semantic analysis requires prompt router")
        # Format evidence → prompt → send through router → parse response
```

---

## Detection Run Lifecycle

```python
class SignalDetector:

    def __init__(self, query_service, config: dict, prompt_router=None):
        """Initialize with query service, config, and optional router."""

    def run(self, window: DetectionWindow | None = None) -> list[Signal]:
        """Run a full detection cycle. Main entry point."""

    def run_statistical(self, entries: list[dict]) -> list[StatisticalCandidate]:
        """Run all statistical detectors on entries."""

    def run_semantic(self, candidates: list[StatisticalCandidate]) -> list[SemanticCandidate]:
        """Run semantic analysis on high-confidence statistical candidates."""

    def emit_signals(self, signals: list[Signal]) -> list[str]:
        """Write SIGNAL_DETECTED entries to ledger. Returns ledger entry IDs."""

    def get_detection_history(self, since: str = "7d") -> list[dict]:
        """Query past SIGNAL_DETECTED entries from ledger."""
```

### Run Flow

1. **Query:** Use `LedgerQueryService` to get entries within the detection window
2. **Statistical pass:** Run all enabled detectors. Each returns `StatisticalCandidate[]`
3. **Threshold filter:** Keep candidates with `confidence >= config.statistical_threshold`
4. **Semantic pass (if enabled + available):** Run semantic analysis on filtered candidates
5. **Deduplication:** Check against recent `SIGNAL_DETECTED` entries — don't re-emit known signals
6. **Emission:** Write new signals to ledger as `SIGNAL_DETECTED` entries
7. **Return:** All emitted signals

### Deduplication

Before emitting a signal, check if a similar signal was recently emitted:
- Same `pattern_type` + same `affected_scope` + within `dedup_window` (config-driven, default 24h)
- If duplicate found → skip emission, increment existing signal's occurrence count in metadata

---

## Config Schema: signal_config.schema.json

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://control-plane.local/schemas/signal_config.schema.json",
  "title": "Signal Detection Configuration v1.0",
  "type": "object",
  "properties": {
    "default_window": {
      "type": "string",
      "default": "24h",
      "description": "Default detection window"
    },
    "min_sample_size": {
      "type": "integer",
      "minimum": 1,
      "default": 10,
      "description": "Minimum entries required for analysis"
    },
    "statistical_threshold": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "default": 0.6,
      "description": "Minimum confidence for a statistical candidate to be emitted"
    },
    "semantic_threshold": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "default": 0.8,
      "description": "Minimum statistical confidence before semantic pass runs"
    },
    "semantic_enabled": {
      "type": "boolean",
      "default": false,
      "description": "Enable LLM-based semantic analysis (requires prompt router)"
    },
    "dedup_window": {
      "type": "string",
      "default": "24h",
      "description": "Window for deduplication of similar signals"
    },
    "detectors": {
      "type": "object",
      "properties": {
        "failure_rate": {
          "type": "object",
          "properties": {
            "enabled": { "type": "boolean", "default": true },
            "threshold": { "type": "number", "default": 0.3 },
            "group_by": { "type": "array", "items": { "type": "string" }, "default": ["agent_class", "framework_id"] },
            "min_samples": { "type": "integer", "default": 10 }
          }
        },
        "quality_trend": {
          "type": "object",
          "properties": {
            "enabled": { "type": "boolean", "default": true },
            "window_count": { "type": "integer", "default": 3 },
            "decline_threshold": { "type": "number", "default": 0.15 },
            "improvement_threshold": { "type": "number", "default": 0.15 },
            "window_size": { "type": "string", "default": "24h" }
          }
        },
        "resource_anomaly": {
          "type": "object",
          "properties": {
            "enabled": { "type": "boolean", "default": true },
            "budget_exhaustion_threshold": { "type": "number", "default": 0.5 },
            "overallocation_threshold": { "type": "number", "default": 0.3 },
            "latency_spike_factor": { "type": "number", "default": 2.0 }
          }
        },
        "correlation": {
          "type": "object",
          "properties": {
            "enabled": { "type": "boolean", "default": true },
            "min_correlation": { "type": "number", "default": 0.5 },
            "factors": { "type": "array", "items": { "type": "string" } },
            "outcomes": { "type": "array", "items": { "type": "string" } },
            "min_samples": { "type": "integer", "default": 20 }
          }
        }
      },
      "description": "Per-detector configuration"
    },
    "max_signals_per_run": {
      "type": "integer",
      "minimum": 1,
      "default": 20,
      "description": "Maximum signals emitted in a single detection run"
    }
  },
  "additionalProperties": true
}
```

---

## Framework: FMWK-008 Signal Detection

```yaml
framework_id: FMWK-008
title: Signal Detection Framework
version: "1.0.0"
status: active
ring: kernel
plane_id: hot
created_at: "2026-02-10T00:00:00Z"
assets:
  - signal_detection_standard.md
expected_specs:
  - SPEC-SIGNAL-001
invariants:
  - level: MUST
    statement: Signals SUGGEST, governance DECIDES — the detector MUST NOT adopt or change system behavior
  - level: MUST
    statement: Statistical detection MUST run before semantic detection (cheap before expensive)
  - level: MUST NOT
    statement: Detection thresholds, window sizes, confidence levels, and frequency cutoffs MUST NOT be hardcoded
  - level: MUST
    statement: Detectors MUST be pluggable — new detectors via subclass + config registration
  - level: MUST
    statement: Semantic detection MUST gracefully degrade to statistical-only when prompt router is unavailable
  - level: MUST
    statement: Duplicate signals within the dedup window MUST NOT be re-emitted
  - level: MUST
    statement: All detected signals MUST be written to the ledger as SIGNAL_DETECTED events
path_authorizations:
  - "HOT/kernel/signal_detector.py"
  - "HOT/kernel/statistical_detectors.py"
  - "HOT/schemas/signal_config.schema.json"
  - "HOT/FMWK-008_Signal_Detection/*.yaml"
  - "HOT/FMWK-008_Signal_Detection/*.md"
  - "HOT/tests/test_signal_detector.py"
required_gates:
  - G0
  - G1
  - G5
```

---

## Package Plan

### PKG-SIGNAL-DETECTOR-001 (Layer 3)

Assets:
- `HOT/kernel/signal_detector.py` — main detector: run lifecycle, semantic pass, signal emission
- `HOT/kernel/statistical_detectors.py` — 4 built-in detectors + BaseDetector interface
- `HOT/schemas/signal_config.schema.json` — detection configuration schema
- `HOT/FMWK-008_Signal_Detection/manifest.yaml` — framework manifest
- `HOT/tests/test_signal_detector.py` — all tests

Dependencies:
- `PKG-KERNEL-001` (for LedgerClient — signal emission writes to ledger)
- `PKG-LEDGER-QUERY-001` (for querying entries to analyze)
- `PKG-PHASE2-SCHEMAS-001` (for ledger_entry_metadata.schema.json — field paths)

**Note:** PKG-PROMPT-ROUTER-001 is NOT a hard dependency. Semantic detection uses the router if available (state-gated via ImportError guard). If router is not installed, semantic pass is silently disabled.

**Governance chain:** `spec_id: "SPEC-GATE-001"`, `framework_id: "FMWK-000"` in manifest.json.

---

## Test Plan (DTT — Tests First)

### Write ALL tests BEFORE any implementation.

**FailureRateDetector:**
1. `test_failure_rate_above_threshold` — 40% failure rate detected
2. `test_failure_rate_below_threshold` — 10% failure rate → no signal
3. `test_failure_rate_grouped` — separate rates per agent_class
4. `test_failure_rate_insufficient_samples` — too few entries → no signal

**QualityTrendDetector:**
5. `test_quality_declining` — quality drops 20% across 3 windows → signal
6. `test_quality_improving` — quality rises 20% → improvement signal
7. `test_quality_stable` — no significant change → no signal
8. `test_quality_insufficient_windows` — fewer than window_count → no signal

**ResourceAnomalyDetector:**
9. `test_budget_exhaustion_detected` — 60% of WOs exhaust budget → signal
10. `test_budget_overallocation_detected` — using <30% of budget → signal
11. `test_latency_spike_detected` — 3x normal latency → signal
12. `test_resource_normal` — all within bounds → no signal

**CorrelationDetector:**
13. `test_positive_correlation` — high context tokens → high quality → signal
14. `test_no_correlation` — random data → no signal
15. `test_correlation_insufficient_samples` — too few entries → no signal

**Pluggable Detectors:**
16. `test_custom_detector_registered` — custom detector runs via config
17. `test_disabled_detector_skipped` — enabled:false → detector not run
18. `test_base_detector_extract_metric` — nested field extraction works

**Semantic Pass:**
19. `test_semantic_confirms_candidate` — LLM validates statistical finding
20. `test_semantic_rejects_candidate` — LLM says not a real pattern
21. `test_semantic_inconclusive` — LLM can't determine
22. `test_semantic_disabled_skipped` — semantic_enabled:false → no LLM calls
23. `test_semantic_unavailable_graceful` — no router → statistical-only, no error
24. `test_semantic_threshold_filters` — only high-confidence candidates sent to LLM

**Signal Emission:**
25. `test_signal_written_to_ledger` — SIGNAL_DETECTED entry created
26. `test_signal_id_format` — SIG-{timestamp}-{seq} format
27. `test_signal_metadata_complete` — all fields populated in ledger entry
28. `test_max_signals_per_run` — respects limit

**Deduplication:**
29. `test_duplicate_signal_suppressed` — same pattern + scope within window → no re-emit
30. `test_different_scope_not_deduped` — same pattern, different scope → emitted
31. `test_expired_dedup_allows_reemit` — outside dedup window → emitted again

**Full Detection Run:**
32. `test_run_happy_path` — query → statistical → threshold → emit → return signals
33. `test_run_empty_ledger` — no entries → no signals
34. `test_run_insufficient_data` — too few entries → no signals
35. `test_run_multiple_detectors` — all enabled detectors contribute
36. `test_run_with_semantic` — statistical + semantic pipeline

**Detection History:**
37. `test_get_detection_history` — retrieves past SIGNAL_DETECTED entries
38. `test_detection_history_window` — respects time window

**Config:**
39. `test_config_loaded` — config schema applied correctly
40. `test_default_config_works` — runs with defaults

### End-to-End Install Test
1. Clean-room extract CP_BOOTSTRAP → install Layers 0-2
2. Install PKG-PHASE2-SCHEMAS-001
3. Install PKG-LEDGER-QUERY-001
4. Install PKG-SIGNAL-DETECTOR-001
5. All gates pass
6. Integration: write test entries → run detector → verify SIGNAL_DETECTED in ledger

---

## Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Ledger Query Service | Handoff #6 / PKG-LEDGER-QUERY-001 | Your data source |
| LedgerClient | `HOT/kernel/ledger_client.py` | Signal emission writes |
| Ledger metadata schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/ledger_entry_metadata.schema.json` | Field paths for extraction |
| Prompt router handoff | `_staging/BUILDER_HANDOFF_3_prompt_router.md` | Semantic pass uses router (optional) |
| paths.py | `_staging/PKG-KERNEL-001/HOT/kernel/paths.py` | get_control_plane_root() |

---

## Design Principles (Non-Negotiable)

1. **Signals suggest, governance decides.** The detector NEVER changes system behavior. It writes `SIGNAL_DETECTED` to the ledger. That's it. The learning loop engine (Handoff #8) reads signals and proposes changes. Governance approves or rejects.
2. **Cheap before expensive.** Statistical detection runs first (pure computation). Semantic detection (LLM tokens) runs only on high-confidence candidates. Every token spent on semantic detection must be justified by statistical evidence.
3. **Pluggable detectors.** New pattern detection = new subclass + config entry. No code changes to the core detector loop.
4. **Config-driven everything.** Thresholds, windows, confidence levels, detector enable/disable — all in `signal_config.schema.json`. Tuning detection = config change, not code change.
5. **Graceful degradation.** No router → no semantic pass → statistical-only signals. Insufficient data → no signals (not guesses). Missing metadata fields → skip that entry, don't crash.
6. **Deduplication prevents noise.** The same signal is not re-emitted within the dedup window. The learning loops see clean signals, not repetitive noise.
