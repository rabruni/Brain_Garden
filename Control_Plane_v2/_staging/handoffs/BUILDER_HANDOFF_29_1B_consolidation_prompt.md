# BUILDER_HANDOFF_29.1B: Consolidation Prompt for Structured Artifacts

## 1. Mission

Update the consolidation prompt (PRM-CONSOLIDATE-001.txt) and contract (consolidate.json) to produce structured artifacts instead of free-form prose. The LLM's job at consolidation time: assign artifact_type from a closed set, assign labels from the classify vocabulary, write a one-sentence context_line, and assign initial weight. Modifies **PKG-HO1-EXECUTOR-001** only.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**.
2. **DTT: Design → Test → Then implement.**
3. **Package everything.** Use `compute_sha256()` and `pack()`.
4. **End-to-end verification.** Clean-room install → all gates pass.
5. **Tar archive format:** `tar czf ... -C dir $(ls dir)`.
6. **Results file.** `_staging/handoffs/RESULTS_HANDOFF_29_1B.md`.
7. **Full regression.** ALL staged tests. New failures are blockers.
8. **Baseline:** 22 packages, 693 installed tests, 8/8 gates.
9. **Scope:** PKG-HO1-EXECUTOR-001 ONLY.
10. **Budget check.** The expanded prompt + response must fit within consolidation_budget (4000 tokens).
11. **Same closed vocabulary as classify.** Domain and task labels are identical to H-31B.

## 3. Architecture / Design

### Current Consolidation Prompt (PRM-CONSOLIDATE-001.txt)

```
You are analyzing patterns in user interaction signals.

Signal: {{signal_id}}
Observation count: {{count}}
Across sessions: {{session_count}}
Recent events:
{{recent_events}}

Based on these observations, produce a concise bias statement...

Respond with valid JSON matching this schema:
{
  "bias": "one sentence describing the pattern",
  "category": "one of: tool_preference, topic_interest, interaction_style, workflow_pattern",
  "salience_weight": 0.0 to 1.0,
  "decay_modifier": 0.0 to 1.0
}
```

### New Consolidation Prompt

```
You are analyzing patterns in user interaction signals for a cognitive control plane.

Signal: {{signal_id}}
Observation count: {{count}}
Across sessions: {{session_count}}
Recent events:
{{recent_events}}

Based on these observations, produce a structured learning artifact.

Respond with valid JSON matching this schema:
{
  "artifact_type": one of "topic_affinity", "interaction_style", "task_pattern", "constraint",
  "labels": {
    "domain": list of matching domains from ["system", "config", "session", "tools", "docs", "general"],
    "task": list of matching tasks from ["inspect", "modify", "create", "debug", "plan", "general"]
  },
  "weight": 0.0 to 1.0 (how strong is this pattern?),
  "scope": one of "agent", "session", "global",
  "context_line": "one sentence plain language description of the pattern (this will be injected into future prompts verbatim)",
  "expires_after_days": null or integer (null = never expires)
}

Artifact type rules:
- "topic_affinity": user repeatedly engages with a specific domain/topic
- "interaction_style": user has a consistent communication preference
- "task_pattern": user performs the same type of task repeatedly
- "constraint": user has stated or demonstrated a rule/preference

Label rules:
- Domain: what area the pattern relates to (use the closed vocabulary above)
- Task: what action type the pattern involves
- Multiple labels allowed if the pattern spans domains/tasks
- Use "general" only if no specific domain/task fits

context_line rules:
- One sentence, plain language
- Describes the pattern, not the evidence
- Will be injected verbatim into future LLM prompts as context
- Example: "User frequently inspects package manifests and governance gates"

Do not include any text outside the JSON object.
```

### Contract Changes (consolidate.json)

Replace `output_schema`:

```json
"output_schema": {
  "type": "object",
  "required": ["artifact_type", "labels", "weight", "scope", "context_line"],
  "properties": {
    "artifact_type": {
      "type": "string",
      "enum": ["topic_affinity", "interaction_style", "task_pattern", "constraint"]
    },
    "labels": {
      "type": "object",
      "properties": {
        "domain": {"type": "array", "items": {"type": "string"}},
        "task": {"type": "array", "items": {"type": "string"}}
      }
    },
    "weight": {"type": "number", "minimum": 0, "maximum": 1},
    "scope": {"type": "string", "enum": ["agent", "session", "global"]},
    "context_line": {"type": "string"},
    "expires_after_days": {"type": ["integer", "null"]}
  }
}
```

### Budget Analysis

Current prompt: ~17 lines, ~150 tokens. New prompt: ~40 lines, ~350 tokens. Max response: ~200 tokens (structured JSON). Total: ~550 tokens within 4000 consolidation_budget. Safe.

### Adversarial Analysis: Label Drift

**Hurdles**: Consolidation and classify use the same label vocabulary. If classify vocabulary grows (new domain added), consolidation prompt must update too.
**Not Enough**: Hardcoding labels in both prompts creates a sync problem.
**Too Much**: Building a shared label registry is over-engineering for MVP.
**Synthesis**: Both prompts hardcode the same 6×6 vocabulary. Document in the handoff that label vocabulary changes require updating BOTH PRM-CLASSIFY-001.txt and PRM-CONSOLIDATE-001.txt. A config-driven vocabulary (from admin_config.json) can be added later.

## 4. Implementation Steps

### Step 1: Replace PRM-CONSOLIDATE-001.txt

Replace entire content with the new structured artifact prompt.

### Step 2: Update consolidate.json output_schema

Replace `output_schema` with the new structured schema. Update `required` array.

### Step 3: Write tests

Add tests verifying the new prompt template has the expected variables, the contract schema has the required fields, and mock LLM responses with structured artifacts parse correctly.

### Step 4: Governance cycle

Update hashes, rebuild archives, clean-room install, gates.

## 5. Package Plan

### PKG-HO1-EXECUTOR-001 (modified)

| Field | Value |
|-------|-------|
| Package ID | PKG-HO1-EXECUTOR-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | ho1 |

Modified assets:
- `HO1/prompt_packs/PRM-CONSOLIDATE-001.txt` — structured artifact prompt
- `HO1/contracts/consolidate.json` — updated output_schema
- `HO1/tests/test_ho1_executor.py` — new tests
- `manifest.json` — hash updates

## 6. Test Plan

### New tests (10)

| Test | Description | Expected |
|------|-------------|----------|
| `test_consolidation_prompt_has_variables` | Prompt contains {{signal_id}}, {{count}}, {{session_count}}, {{recent_events}} | All 4 present |
| `test_consolidation_schema_requires_artifact_type` | consolidate.json required includes artifact_type | In required array |
| `test_consolidation_schema_requires_labels` | consolidate.json required includes labels | In required array |
| `test_consolidation_schema_requires_context_line` | consolidate.json required includes context_line | In required array |
| `test_consolidation_structured_output_parsed` | Mock LLM returns structured artifact → parsed | output_result has artifact_type, labels, weight, scope, context_line |
| `test_consolidation_artifact_type_enum` | Schema has enum for artifact_type | 4 values present |
| `test_consolidation_scope_enum` | Schema has enum for scope | 3 values: agent, session, global |
| `test_consolidation_labels_domain_list` | Labels.domain is array of strings | Type matches |
| `test_consolidation_backward_compat` | Old-style output (bias/category) still parseable by HO1 | No crash (additionalProperties) |
| `test_consolidation_budget_check` | Prompt + response estimate within 4000 tokens | Within budget |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| PRM-CONSOLIDATE-001.txt | `_staging/PKG-HO1-EXECUTOR-001/HO1/prompt_packs/` | File to replace |
| consolidate.json | `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/` | Schema to update |
| ho1_executor.py | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` | How prompts are rendered |
| HO2 run_consolidation | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py:537-603` | How consolidation WO is created |
| HO3 log_overlay | `_staging/PKG-HO3-MEMORY-001/HOT/kernel/ho3_memory.py:169-220` | Where output is stored |

## 8. End-to-End Verification

```bash
TMPDIR=$(mktemp -d)
cd Control_Plane_v2/_staging && tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
cd "$TMPDIR" && bash install.sh --root "$TMPDIR" --dev
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 -m pytest "$TMPDIR/HOT/tests" "$TMPDIR/HO1/tests" "$TMPDIR/HO2/tests" -v
python3 "$TMPDIR/HOT/scripts/gate_check.py" --root "$TMPDIR" --all --enforce
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `PRM-CONSOLIDATE-001.txt` | `_staging/PKG-HO1-EXECUTOR-001/HO1/prompt_packs/` | MODIFY |
| `consolidate.json` | `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/` | MODIFY |
| `test_ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO1-EXECUTOR-001/` | MODIFY |
| `PKG-HO1-EXECUTOR-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_29_1B.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Structured over prose.** Artifacts have typed fields. HO2 can filter/rank/scope without reading meaning.
2. **Same vocabulary.** Consolidation uses the same closed label set as classify. No vocabulary drift.
3. **Context line is the interface.** LLM writes it once at consolidation time. HO2 injects it verbatim. No re-interpretation.
4. **Budget safe.** ~550 tokens total << 4000 consolidation_budget.
5. **Backward compatible.** Old free-form output doesn't crash anything. New structured output has all fields.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project.

**Agent: HANDOFF-29.1B** — Consolidation prompt for structured artifacts (PKG-HO1-EXECUTOR-001)

Read: `Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_29_1B_consolidation_prompt.md`

**Rules:** 1. _staging/ only. 2. DTT. 3. compute_sha256()+pack(). 4. sha256:<64hex>. 5. Clean-room. 6. Full regression. 7. Results file. 8. CP_BOOTSTRAP rebuild. 9. PKG-HO1-EXECUTOR-001 ONLY.

**10 Questions:**

1. What package? What TWO files in prompt_packs/contracts are changed?
2. What are the 4 artifact_type values? What does each mean?
3. What are the 3 scope values?
4. What is context_line? How is it used by HO2? Does HO2 interpret its meaning?
5. Are the label vocabularies identical to H-31B's classify labels? Why does that matter?
6. What fields are in the new output_schema's required array?
7. What budget is this prompt constrained by? Estimate the token usage.
8. What happens if the LLM returns old-style output (bias/category instead of artifact_type/labels)?
9. How many new tests? Name them.
10. What downstream code reads consolidation output and stores it? What handoff modifies that code?

**Adversarial:**
11. If labels vocabulary grows (new domain added to classify), what must also change?
12. The prompt says "multiple labels allowed" — could the LLM return 6 domains and 6 tasks? What's the impact?
13. expires_after_days is in the prompt but expires_at_event_ts is what HO3 stores. Who converts?

STOP AFTER ANSWERING.
```

### Expected Answers

1. PKG-HO1-EXECUTOR-001. PRM-CONSOLIDATE-001.txt and consolidate.json.
2. topic_affinity (repeated domain engagement), interaction_style (communication preference), task_pattern (repeated task type), constraint (stated/demonstrated rule).
3. agent (persists across sessions for this agent class), session (only for current session), global (all agent classes).
4. A one-sentence plain language description of the pattern. HO2 copies it verbatim into the synthesize prompt context. HO2 never reads it for meaning — it's opaque text that the LLM wrote once at consolidation time.
5. Yes, identical: 6 domain labels (system, config, session, tools, docs, general) + 6 task labels (inspect, modify, create, debug, plan, general). This matters because HO2's consumption model does set intersection between turn labels (from classify) and artifact labels (from consolidation). If vocabularies diverge, matching breaks.
6. artifact_type, labels, weight, scope, context_line. (5 required fields)
7. consolidation_budget = 4000 tokens. Estimated usage: ~350 prompt + ~200 response = ~550 tokens total. Safe.
8. HO1 executor does json.loads on the output. The old fields (bias, category) would be parsed as extra properties. consolidate.json's new required array demands artifact_type, labels, etc. If using structured_output enforcement, the LLM would be forced to produce the new shape. If not (pre-deployment), the WO would fail quality gate (missing required fields) — an acceptable failure mode during rollout.
9. 10 tests (list all).
10. HO2's run_consolidation() (ho2_supervisor.py:537-603) reads the consolidation WO output and calls ho3_memory.log_overlay(). H-29.1A modifies log_overlay to accept structured artifact fields. This handoff (29.1B) ensures the LLM produces the right shape; H-29.1A ensures HO3 can store it.
11. PRM-CONSOLIDATE-001.txt must also update to include the new label. Both prompts (classify + consolidation) hardcode the same vocabulary. Document this sync requirement.
12. The LLM could return all 6 domains. Impact: the artifact matches every turn (all labels intersect). This is equivalent to scope=global. Not harmful but imprecise. The weight and decay still control injection priority. A future improvement could cap labels to 2-3 per dimension.
13. HO2's run_consolidation() code. When it reads `expires_after_days` from the LLM output, it computes `expires_at_event_ts = consolidation_event_ts + timedelta(days=expires_after_days)` and passes that to log_overlay. The conversion happens in HO2 (H-29.1C), not in this handoff.
