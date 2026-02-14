# Builder Handoff #8: Learning Loop Engine

## Mission

Build the learning loop engine — the component that reads signals from the signal detector and closes the feedback cycle. Three loops at different timescales: HO2 operational (fast, per-WO), HOT governance (slow, cross-WO), and Meta (self-evaluating — did adopted changes actually help?).

This is the "brain" that makes the system improve over time. It does NOT make changes directly — it generates **proposals** that governance reviews and adopts or rejects. The meta loop then tracks whether adopted changes improved outcomes.

**CRITICAL CONSTRAINTS — read before doing anything:**

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. No exceptions.
3. **Package everything.** New code ships as packages with manifest.json, SHA256 hashes, proper dependencies.
4. **End-to-end verification.** Full install chain must pass all gates.
5. **No hardcoding.** Loop frequencies, adoption thresholds, evaluation windows — all config-driven.
6. **No file replacement.** Packages must NEVER overwrite another package's files.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .`
8. **Governance chain:** Use `spec_id: "SPEC-GATE-001"` and `framework_id: "FMWK-000"` in manifest.json. Ship FMWK-009 manifest.yaml as an asset.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                SIGNAL DETECTOR (upstream)                     │
│         Writes SIGNAL_DETECTED entries to ledger             │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                  LEARNING LOOP ENGINE                         │
│                                                              │
│  ┌───────────────────────────────────────────────┐           │
│  │  LOOP SCHEDULER                               │           │
│  │  Triggers loops at configured intervals        │           │
│  └───────┬──────────┬──────────┬─────────────────┘           │
│          │          │          │                              │
│          ▼          ▼          ▼                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐               │
│  │ HO2 LOOP   │ │ HOT LOOP   │ │ META LOOP  │               │
│  │ (fast)     │ │ (slow)     │ │ (eval)     │               │
│  │            │ │            │ │            │               │
│  │ Per-WO     │ │ Cross-WO   │ │ Did our    │               │
│  │ feedback   │ │ pattern    │ │ changes    │               │
│  │            │ │ adoption   │ │ help?      │               │
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘               │
│        │              │              │                       │
│        ▼              ▼              ▼                       │
│  ┌───────────────────────────────────────────────┐           │
│  │  PROPOSAL GENERATOR                           │           │
│  │  Creates structured change proposals          │           │
│  │  Writes LEARNING_PROPOSAL to ledger           │           │
│  └───────────────────────────────────────────────┘           │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                   GOVERNANCE (human / ADMIN)                  │
│              Reviews proposals → ADOPT / REJECT               │
└──────────────────────────────────────────────────────────────┘
```

---

## The Three Loops

### Loop 1: HO2 Operational (Fast, Per-WO)

**Trigger:** After each WO completes (reads `WO_EXEC_COMPLETE` / `WO_EXEC_FAILED` events)
**Question:** "Did this WO succeed? Should the next similar WO be adjusted?"
**Scope:** Within a session, fast turnaround
**Timescale:** Seconds to minutes after WO completion

**What it looks at:**
- The WO's outcome (success/failure/partial/timeout)
- Token usage vs. budget (over? under? just right?)
- Quality signal (if available)
- Comparison to previous WOs with same framework + agent_class

**What it proposes:**
- Budget adjustment hints: "WOs for framework F typically use 80% of budget → suggest 20% reduction"
- Prompt contract hints: "Quality improved when max_tokens was higher → suggest increase"
- Attention template hints: "Context assembly timed out → suggest higher timeout or fewer pipeline stages"

**Output:** `LEARNING_PROPOSAL` entries with `loop: "ho2_operational"`, `urgency: "immediate"`

### Loop 2: HOT Governance (Slow, Cross-WO)

**Trigger:** Periodically (configurable: every N WO completions, every N hours, or on-demand)
**Question:** "Are there patterns across WOs that should change system configuration?"
**Scope:** Cross-session, cross-WO analysis
**Timescale:** Hours to days

**What it looks at:**
- Signals from the signal detector (`SIGNAL_DETECTED` entries)
- Aggregate outcome data across frameworks, agent classes, prompt contracts
- Trends over the analysis window

**What it proposes:**
- Attention template changes: "Template T should increase max_context_tokens based on quality correlation"
- Prompt contract changes: "Contract P should add structured_output validation"
- Budget policy changes: "Default budget for ADMIN agents should increase from N to M"
- Framework configuration changes: "Framework F's path authorizations should include X"

**Output:** `LEARNING_PROPOSAL` entries with `loop: "hot_governance"`, `urgency: "standard"`

### Loop 3: Meta (Self-Evaluating)

**Trigger:** After adopted proposals have had time to take effect (configurable evaluation window)
**Question:** "Did the changes we adopted actually improve outcomes?"
**Scope:** Before-vs-after comparison of adopted changes
**Timescale:** Days to weeks

**What it looks at:**
- `PROPOSAL_ADOPTED` entries (proposals that were approved and applied)
- Outcome metrics BEFORE adoption (baseline window)
- Outcome metrics AFTER adoption (evaluation window)
- The specific metrics the proposal claimed to improve

**What it proposes:**
- Reinforcement: "Change X improved quality by 15% → keep it"
- Reversion: "Change Y made failure rate worse → propose reverting"
- Refinement: "Change Z helped ADMIN agents but hurt RESIDENT agents → propose scoped version"

**Output:** `LEARNING_PROPOSAL` entries with `loop: "meta"`, `urgency: "review"`

---

## Data Structures

```python
@dataclass
class LoopTrigger:
    """What triggers a loop run."""
    type: str               # "event" (HO2), "schedule" (HOT), "evaluation" (Meta)
    event_type: str | None  # For event triggers: "WO_EXEC_COMPLETE"
    interval: str | None    # For schedule triggers: "6h", "50_wo_completions"
    eval_window: str | None # For meta triggers: "7d" (wait 7d after adoption)

@dataclass
class Proposal:
    """A change proposal generated by a learning loop."""
    proposal_id: str         # PRP-{timestamp}-{seq}
    loop: str                # "ho2_operational", "hot_governance", "meta"
    urgency: str             # "immediate", "standard", "review"
    target_type: str         # "attention_template", "prompt_contract", "budget_policy", "framework_config"
    target_id: str           # ID of the thing to change (e.g., ATT-XXX, PRC-XXX)
    description: str         # Human-readable: "Increase max_context_tokens for ATT-ADMIN-001"
    current_value: dict      # What it is now
    proposed_value: dict     # What it should be
    evidence: dict           # Supporting signals, metrics, comparisons
    confidence: float        # 0-1, loop's confidence in this proposal
    expected_impact: str     # What improvement is expected
    created_at: str          # ISO timestamp

    # Meta loop fields (only for meta proposals)
    evaluated_proposal_id: str | None = None  # Original proposal being evaluated
    baseline_metrics: dict | None = None       # Metrics before adoption
    current_metrics: dict | None = None        # Metrics after adoption
    verdict: str | None = None                 # "reinforced", "revert", "refine"

@dataclass
class LoopRunResult:
    """Result of a single loop execution."""
    loop: str                # Which loop ran
    run_id: str              # Unique run identifier
    entries_analyzed: int    # How many ledger entries were read
    signals_consumed: int    # How many signals were processed (HOT loop)
    proposals_generated: int # How many proposals were created
    proposals: list[Proposal]
    duration_ms: int
    ledger_entry_ids: list[str]  # Ledger entries written during this run
```

---

## Loop Scheduler

```python
class LoopScheduler:
    """Manages when each loop runs."""

    def __init__(self, config: dict, query_service, signal_detector=None):
        """Initialize with config and dependencies."""

    def should_run(self, loop: str) -> bool:
        """Check if a loop should run now based on triggers."""

    def run_loop(self, loop: str) -> LoopRunResult:
        """Execute a specific loop."""

    def run_due(self) -> list[LoopRunResult]:
        """Run all loops that are currently due. Main entry point."""

    def get_schedule_status(self) -> dict:
        """Return current schedule state: last run times, next due times."""
```

### Scheduling Logic

- **HO2 loop:** Triggered by new `WO_EXEC_COMPLETE` events since last run. The scheduler checks if there are unprocessed WO completions.
- **HOT loop:** Triggered by interval (`every_n_hours`) OR event count (`every_n_wo_completions`). Whichever fires first.
- **Meta loop:** Triggered by evaluation window expiry — looks for `PROPOSAL_ADOPTED` entries where `adoption_time + eval_window < now`.

All timing is config-driven. The scheduler does NOT run in a background thread — it's called explicitly (by the flow runner after WO completion, by a cron job, or by an admin command). This keeps it deterministic and testable.

---

## Adoption Pipeline

The learning loops generate proposals. Governance adopts or rejects them. The full pipeline:

```
Signal detected → Loop analyzes → Proposal generated → LEARNING_PROPOSAL in ledger
    ↓
Governance reviews (human or ADMIN agent)
    ↓
PROPOSAL_ADOPTED or PROPOSAL_REJECTED in ledger
    ↓
If adopted: change is applied to target (attention template, prompt contract, etc.)
    ↓
Meta loop waits eval_window, then compares before/after
    ↓
LEARNING_PROPOSAL from meta loop (reinforce / revert / refine)
```

### Adoption Events

The learning loop engine writes these event types to the ledger:
- `LEARNING_PROPOSAL` — a loop generated a change proposal
- `LOOP_RUN_COMPLETE` — a loop finished executing (audit trail)

Governance (external to this package) writes:
- `PROPOSAL_ADOPTED` — a proposal was approved and applied
- `PROPOSAL_REJECTED` — a proposal was rejected with reason

The meta loop reads `PROPOSAL_ADOPTED` to know what to evaluate.

### v1 Scope

v1 generates proposals and writes them to the ledger. The adoption pipeline (applying changes to attention templates, prompt contracts, etc.) is a **v2 feature** — for v1, adoption is manual (human reads proposals from ledger, makes changes by hand or through the package system).

Define the interface for automated adoption but don't implement it:

```python
class AdoptionHandler:
    """Base class for applying adopted proposals. v2 implementation."""

    def apply(self, proposal: Proposal) -> dict:
        """Apply an adopted proposal to its target. Returns result."""
        raise NotImplementedError("Automated adoption is v2")

    def revert(self, proposal: Proposal) -> dict:
        """Revert a previously adopted proposal. Returns result."""
        raise NotImplementedError("Automated reversion is v2")
```

---

## Config Schema: learning_config.schema.json

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://control-plane.local/schemas/learning_config.schema.json",
  "title": "Learning Loop Configuration v1.0",
  "type": "object",
  "properties": {
    "ho2_operational": {
      "type": "object",
      "properties": {
        "enabled": { "type": "boolean", "default": true },
        "trigger": {
          "type": "string",
          "default": "on_wo_complete",
          "description": "When to run: 'on_wo_complete' or 'manual'"
        },
        "min_comparisons": {
          "type": "integer",
          "default": 3,
          "description": "Minimum similar WOs needed before generating proposals"
        },
        "budget_deviation_threshold": {
          "type": "number",
          "default": 0.3,
          "description": "Budget usage deviation (30%) that triggers a proposal"
        },
        "quality_deviation_threshold": {
          "type": "number",
          "default": 0.2,
          "description": "Quality change (20%) that triggers a proposal"
        }
      },
      "description": "HO2 operational loop (fast, per-WO)"
    },
    "hot_governance": {
      "type": "object",
      "properties": {
        "enabled": { "type": "boolean", "default": true },
        "interval_hours": {
          "type": "integer",
          "default": 6,
          "description": "Run every N hours"
        },
        "interval_wo_completions": {
          "type": "integer",
          "default": 50,
          "description": "Or run every N WO completions (whichever fires first)"
        },
        "signal_confidence_threshold": {
          "type": "number",
          "default": 0.7,
          "description": "Minimum signal confidence to act on"
        },
        "analysis_window": {
          "type": "string",
          "default": "7d",
          "description": "How far back to analyze"
        }
      },
      "description": "HOT governance loop (slow, cross-WO)"
    },
    "meta": {
      "type": "object",
      "properties": {
        "enabled": { "type": "boolean", "default": true },
        "eval_window": {
          "type": "string",
          "default": "7d",
          "description": "Wait this long after adoption before evaluating"
        },
        "improvement_threshold": {
          "type": "number",
          "default": 0.1,
          "description": "Minimum improvement (10%) to reinforce"
        },
        "degradation_threshold": {
          "type": "number",
          "default": 0.05,
          "description": "Any degradation above 5% triggers revert proposal"
        },
        "min_post_adoption_samples": {
          "type": "integer",
          "default": 10,
          "description": "Minimum WOs after adoption before evaluating"
        }
      },
      "description": "Meta loop (self-evaluating)"
    },
    "proposal_id_prefix": {
      "type": "string",
      "default": "PRP",
      "description": "Prefix for proposal IDs"
    },
    "max_proposals_per_run": {
      "type": "integer",
      "default": 10,
      "description": "Maximum proposals a single loop run can generate"
    }
  },
  "additionalProperties": true
}
```

---

## Framework: FMWK-009 Learning

```yaml
framework_id: FMWK-009
title: Learning Framework
version: "1.0.0"
status: active
ring: kernel
plane_id: hot
created_at: "2026-02-10T00:00:00Z"
assets:
  - learning_standard.md
expected_specs:
  - SPEC-LEARNING-001
invariants:
  - level: MUST
    statement: Learning loops MUST generate proposals — they MUST NOT apply changes directly
  - level: MUST
    statement: The adoption pipeline MUST require governance approval — no auto-adoption in v1
  - level: MUST
    statement: The meta loop MUST compare before/after metrics — no "it feels better" judgments
  - level: MUST NOT
    statement: Loop frequencies, thresholds, evaluation windows, and deviation tolerances MUST NOT be hardcoded
  - level: MUST
    statement: Each loop run MUST be recorded in the ledger (LOOP_RUN_COMPLETE)
  - level: MUST
    statement: Proposals MUST include evidence (signals, metrics, comparisons) — no unsupported claims
  - level: MUST NOT
    statement: The meta loop MUST NOT evaluate proposals before the eval_window expires
path_authorizations:
  - "HOT/kernel/learning_loops.py"
  - "HOT/kernel/loop_scheduler.py"
  - "HOT/schemas/learning_config.schema.json"
  - "HOT/FMWK-009_Learning/*.yaml"
  - "HOT/FMWK-009_Learning/*.md"
  - "HOT/tests/test_learning_loops.py"
required_gates:
  - G0
  - G1
  - G5
```

---

## Package Plan

### PKG-LEARNING-LOOPS-001 (Layer 3)

Assets:
- `HOT/kernel/learning_loops.py` — three loop implementations + proposal generator
- `HOT/kernel/loop_scheduler.py` — scheduling logic, trigger evaluation
- `HOT/schemas/learning_config.schema.json` — learning configuration schema
- `HOT/FMWK-009_Learning/manifest.yaml` — framework manifest
- `HOT/tests/test_learning_loops.py` — all tests

Dependencies:
- `PKG-KERNEL-001` (for LedgerClient — writes proposals and loop runs to ledger)
- `PKG-LEDGER-QUERY-001` (for querying outcomes, signals, adopted proposals)
- `PKG-SIGNAL-DETECTOR-001` (for reading SIGNAL_DETECTED entries — HOT loop)
- `PKG-PHASE2-SCHEMAS-001` (for ledger_entry_metadata.schema.json — field paths)

**Governance chain:** `spec_id: "SPEC-GATE-001"`, `framework_id: "FMWK-000"` in manifest.json.

---

## Test Plan (DTT — Tests First)

### Write ALL tests BEFORE any implementation.

**HO2 Operational Loop:**
1. `test_ho2_triggers_on_wo_complete` — runs when new WO_EXEC_COMPLETE exists
2. `test_ho2_compares_similar_wos` — finds similar WOs (same framework + agent_class)
3. `test_ho2_budget_deviation_proposal` — usage 50% of allocation → budget reduction proposal
4. `test_ho2_quality_improvement_proposal` — quality higher with more tokens → increase proposal
5. `test_ho2_insufficient_comparisons` — fewer than min_comparisons → no proposal
6. `test_ho2_no_deviation_no_proposal` — metrics within thresholds → no proposal
7. `test_ho2_urgency_immediate` — HO2 proposals have urgency "immediate"

**HOT Governance Loop:**
8. `test_hot_triggers_on_interval` — runs when interval_hours elapsed
9. `test_hot_triggers_on_wo_count` — runs when interval_wo_completions reached
10. `test_hot_reads_signals` — consumes SIGNAL_DETECTED entries from ledger
11. `test_hot_filters_by_confidence` — ignores signals below threshold
12. `test_hot_proposes_attention_change` — generates attention template change proposal
13. `test_hot_proposes_budget_policy` — generates budget policy change proposal
14. `test_hot_proposes_prompt_contract_change` — generates prompt contract change proposal
15. `test_hot_no_signals_no_proposals` — no signals → no proposals
16. `test_hot_urgency_standard` — HOT proposals have urgency "standard"

**Meta Loop:**
17. `test_meta_triggers_after_eval_window` — runs when adoption + eval_window < now
18. `test_meta_finds_adopted_proposals` — reads PROPOSAL_ADOPTED entries
19. `test_meta_compares_before_after` — baseline vs current metrics
20. `test_meta_reinforces_improvement` — 15% quality increase → reinforce
21. `test_meta_proposes_revert` — 10% quality decrease → revert proposal
22. `test_meta_proposes_refinement` — mixed results → scoped refinement proposal
23. `test_meta_insufficient_post_samples` — too few WOs after adoption → skip evaluation
24. `test_meta_eval_window_not_expired` — adoption too recent → skip
25. `test_meta_urgency_review` — Meta proposals have urgency "review"

**Proposal Generator:**
26. `test_proposal_id_format` — PRP-{timestamp}-{seq}
27. `test_proposal_has_evidence` — evidence field populated
28. `test_proposal_has_current_and_proposed` — both values present
29. `test_proposal_written_to_ledger` — LEARNING_PROPOSAL event created
30. `test_max_proposals_per_run` — respects limit

**Loop Scheduler:**
31. `test_should_run_ho2` — correctly identifies when HO2 is due
32. `test_should_run_hot_by_time` — HOT due by interval
33. `test_should_run_hot_by_count` — HOT due by WO count
34. `test_should_run_meta` — Meta due by eval window
35. `test_run_due_multiple` — runs all due loops
36. `test_schedule_status` — reports last run, next due
37. `test_disabled_loop_not_scheduled` — enabled:false → not run

**Loop Run Recording:**
38. `test_loop_run_logged` — LOOP_RUN_COMPLETE written to ledger
39. `test_loop_run_result_complete` — LoopRunResult has all fields

**v2 Extension Points:**
40. `test_adoption_handler_interface` — AdoptionHandler.apply raises NotImplementedError
41. `test_revert_handler_interface` — AdoptionHandler.revert raises NotImplementedError

**Edge Cases:**
42. `test_empty_ledger_all_loops` — no entries → all loops produce nothing
43. `test_no_adopted_proposals_meta` — meta loop with nothing to evaluate
44. `test_concurrent_loop_safety` — two loops running don't interfere
45. `test_config_defaults_work` — runs with default config

### End-to-End Install Test
1. Clean-room extract CP_BOOTSTRAP → install Layers 0-2
2. Install PKG-PHASE2-SCHEMAS-001
3. Install PKG-LEDGER-QUERY-001
4. Install PKG-SIGNAL-DETECTOR-001
5. Install PKG-LEARNING-LOOPS-001
6. All gates pass
7. Integration: write WO completion entries + signal entries → run scheduler → verify LEARNING_PROPOSAL and LOOP_RUN_COMPLETE in ledger

---

## Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Ledger Query Service | Handoff #6 / PKG-LEDGER-QUERY-001 | Query outcomes, signals, adoptions |
| Signal Detector | Handoff #7 / PKG-SIGNAL-DETECTOR-001 | SIGNAL_DETECTED entries (HOT loop input) |
| LedgerClient | `HOT/kernel/ledger_client.py` | Write proposals and loop runs |
| Ledger metadata schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/ledger_entry_metadata.schema.json` | Outcome, provenance fields |
| Work order schema | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/schemas/work_order.schema.json` | Budget fields for comparison |
| Attention template schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/attention_template.schema.json` | Proposal targets |
| Prompt contract schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/prompt_contract.schema.json` | Proposal targets |

---

## Design Principles (Non-Negotiable)

1. **Proposals, not actions.** Learning loops generate proposals. They NEVER apply changes directly. Governance approves. This is the firewall between emergence and adoption.
2. **Evidence-based only.** Every proposal must cite evidence — signals, metrics, comparisons. No "I think this would be better." The evidence IS the justification.
3. **Three timescales, three scopes.** HO2 = fast/narrow (this WO), HOT = slow/broad (all WOs), Meta = retrospective (did changes help?). Each loop has its own rhythm.
4. **Meta closes the loop.** Without the meta loop, the system can adopt changes that make things worse and never notice. The meta loop IS the quality control on the learning system itself.
5. **Config-driven timing.** Loop frequencies, evaluation windows, thresholds — all from config. Tuning the learning system = config change, not code change.
6. **No auto-adoption in v1.** Proposals are written to the ledger. Humans (or ADMIN agents in v2) review and decide. The AdoptionHandler interface exists but is not implemented.
7. **Scheduler is pull, not push.** The scheduler doesn't run in a background thread. It's called explicitly and returns results. Deterministic and testable.
