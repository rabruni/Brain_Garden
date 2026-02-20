# BUILDER_HANDOFF_31B: Extend Classify With Intent + Labels

## 1. Mission

Add intent recognition and a closed label vocabulary to the classify LLM call. Zero additional LLM calls — the classify prompt already sees the user message. We ask it to also emit (a) whether this is a continuation/new/close, and (b) what domain/task labels apply. Modifies **PKG-HO1-EXECUTOR-001** only.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**.
2. **DTT: Design → Test → Then implement.**
3. **Package everything.** Use `compute_sha256()` and `pack()`.
4. **End-to-end verification.** Clean-room install → all gates pass.
5. **Tar archive format:** `tar czf ... -C dir $(ls dir)`.
6. **Results file.** `_staging/handoffs/RESULTS_HANDOFF_31B.md`.
7. **Full regression.** ALL staged tests. New failures are blockers.
8. **Baseline:** 22 packages, 693 installed tests, 8/8 gates.
9. **Scope:** PKG-HO1-EXECUTOR-001 ONLY. Do NOT modify PKG-HO2-SUPERVISOR-001 or PKG-ADMIN-001.
10. **Backward compatible.** `intent_signal` and `labels` are OPTIONAL in output. If the LLM doesn't produce them, everything works as before. The `additionalProperties: true` in classify.json already allows extra fields.
11. **Budget check.** The expanded prompt must fit within classify_budget (2000 tokens). If it doesn't, note the required increase in the results file.

## 3. Architecture / Design

### Current Classify Prompt (PRM-CLASSIFY-001.txt)

```
You are a speech act classifier for a cognitive control plane.
Analyze the following user input and classify it.
User input: {{user_input}}
Respond with valid JSON only matching this schema:
{
  "speech_act": one of "greeting", "question", "command", "reentry_greeting", "farewell",
  "ambiguity": one of "low", "medium", "high"
}
Do not include any text outside the JSON object.
```

### Extended Classify Prompt

```
You are a speech act classifier for a cognitive control plane.
Analyze the following user input and classify it.

User input:
{{user_input}}

Respond with valid JSON matching this schema:

{
  "speech_act": one of "greeting", "question", "command", "reentry_greeting", "farewell",
  "ambiguity": one of "low", "medium", "high",
  "intent_signal": {
    "action": one of "new", "continue", "close", "unclear",
    "candidate_objective": "short description of what the user is trying to do",
    "confidence": 0.0 to 1.0
  },
  "labels": {
    "domain": one of "system", "config", "session", "tools", "docs", "general",
    "task": one of "inspect", "modify", "create", "debug", "plan", "general"
  }
}

Intent rules:
- "new" = user is starting a new topic or task
- "continue" = user is continuing the same thread as previous turns
- "close" = user is done (farewell, thanks, etc.)
- "unclear" = cannot determine intent relationship
- For the FIRST message in a session, always use "new"
- candidate_objective is a short phrase (5-15 words) describing the user's goal

Domain labels (what area):
- system: control plane, packages, gates, manifests
- config: admin_config, agent setup, budget settings
- session: session management, history, turns
- tools: tool usage, tool configuration
- docs: documentation, specs, design
- general: doesn't fit other domains

Task labels (what action):
- inspect: reading, examining, listing, querying
- modify: changing, updating, fixing, configuring
- create: building, generating, writing new things
- debug: troubleshooting, diagnosing, tracing
- plan: designing, strategizing, scoping
- general: doesn't fit other tasks

Do not include any text outside the JSON object.
```

### Classify Contract Changes (classify.json)

Add to `output_schema.properties` (NOT to `required`):

```json
"intent_signal": {
  "type": "object",
  "properties": {
    "action": {"type": "string", "enum": ["new", "continue", "close", "unclear"]},
    "candidate_objective": {"type": "string"},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
  }
},
"labels": {
  "type": "object",
  "properties": {
    "domain": {"type": "string", "enum": ["system", "config", "session", "tools", "docs", "general"]},
    "task": {"type": "string", "enum": ["inspect", "modify", "create", "debug", "plan", "general"]}
  }
}
```

`additionalProperties: true` is already set. `required` stays `["speech_act", "ambiguity"]`. The new fields are optional during rollout.

### What Downstream Consumers Will Read (future handoffs, NOT this one)

- HO2 post-turn signal extraction (H-29.1C): reads `labels.domain` → logs `domain:<value>` signal, reads `labels.task` → logs `task:<value>` signal
- HO2 intent lifecycle (H-31C): reads `intent_signal.action` to manage DECLARED/SUPERSEDED/CLOSED
- HO2 consumption model (H-29.1C): matches `labels` against artifact labels for bias selection

This handoff enables those. It does NOT implement them.

### Adversarial Analysis: Budget Impact

**Hurdles**: The expanded prompt is ~40 lines vs the original ~14 lines. With the label vocabulary and intent rules, the prompt grows from ~200 tokens to ~400 tokens. The max_tokens for classify output is 500. Total: ~900 tokens within the 2000 classify_budget.

**Not Enough**: If we don't add the label vocabulary inline, the LLM won't know the closed set and will hallucinate labels.

**Too Much**: We could add 20 domain labels and 15 task labels. That bloats the prompt. 6×6 is enough for ADMIN.

**Synthesis**: 6+6 labels inline. Budget check: ~900 tokens total << 2000 classify_budget. Safe.

## 4. Implementation Steps

### Step 1: Update PRM-CLASSIFY-001.txt

Replace the entire content of `_staging/PKG-HO1-EXECUTOR-001/HO1/prompt_packs/PRM-CLASSIFY-001.txt` with the extended classify prompt shown in Section 3.

### Step 2: Update classify.json output_schema

In `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/classify.json`, add `intent_signal` and `labels` to `output_schema.properties`. Do NOT add them to `required`. Do NOT add them to `boundary.structured_output`.

### Step 3: Write tests

Add tests to `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py`.

### Step 4: Governance cycle

Update manifest hashes, rebuild archives, clean-room install, gates.

## 5. Package Plan

### PKG-HO1-EXECUTOR-001 (modified)

| Field | Value |
|-------|-------|
| Package ID | PKG-HO1-EXECUTOR-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HO1/prompt_packs/PRM-CLASSIFY-001.txt` — extended prompt
- `HO1/contracts/classify.json` — extended output_schema
- `HO1/tests/test_ho1_executor.py` — new tests
- `manifest.json` — hash updates

## 6. Test Plan

### New tests (12)

| Test | Description | Expected |
|------|-------------|----------|
| `test_classify_returns_intent_signal` | Mock LLM returns full classify with intent_signal → parsed | output_result contains intent_signal dict |
| `test_classify_returns_labels` | Mock LLM returns classify with labels → parsed | output_result contains labels dict |
| `test_classify_intent_action_new` | LLM classifies first message as "new" | intent_signal.action == "new" |
| `test_classify_intent_action_continue` | LLM classifies follow-up as "continue" | intent_signal.action == "continue" |
| `test_classify_intent_action_close` | LLM classifies "goodbye" as "close" | intent_signal.action == "close" |
| `test_classify_labels_domain_system` | "what packages are installed?" → domain="system" | labels.domain == "system" |
| `test_classify_labels_task_inspect` | "list sessions" → task="inspect" | labels.task == "inspect" |
| `test_classify_backward_compatible_no_intent` | LLM returns only speech_act + ambiguity → works | output_result has speech_act, no error |
| `test_classify_backward_compatible_no_labels` | LLM returns speech_act + ambiguity only → works | No KeyError on missing labels |
| `test_classify_prompt_template_has_user_input` | Prompt template contains {{user_input}} | Template variable present |
| `test_classify_contract_allows_additional_properties` | classify.json has additionalProperties:true | Schema allows extra fields |
| `test_classify_required_fields_unchanged` | required still only ["speech_act", "ambiguity"] | intent_signal and labels NOT in required |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| PRM-CLASSIFY-001.txt | `_staging/PKG-HO1-EXECUTOR-001/HO1/prompt_packs/` | File to replace |
| classify.json | `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/` | Schema to extend |
| ho1_executor.py | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` | _render_template, execute |
| test_ho1_executor.py | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/` | Test patterns |
| HO2 classify WO creation | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py:156-184` | How classify is called |

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
| `PRM-CLASSIFY-001.txt` | `_staging/PKG-HO1-EXECUTOR-001/HO1/prompt_packs/` | MODIFY |
| `classify.json` | `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/` | MODIFY |
| `test_ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO1-EXECUTOR-001/` | MODIFY |
| `PKG-HO1-EXECUTOR-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_31B.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Zero extra LLM calls.** Classify already sees the message. We ask for more output, not more calls.
2. **Optional output.** New fields are not required. If LLM doesn't produce them, nothing breaks.
3. **Closed vocabulary.** Labels from a fixed set. No free-form strings. Enables exact matching downstream.
4. **Inline vocabulary.** Labels listed directly in the prompt. Simple, auditable, no cross-package dependency.
5. **Budget safe.** ~900 tokens total << 2000 classify_budget. Room to grow.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project.

**Agent: HANDOFF-31B** — Extend classify with intent + labels (PKG-HO1-EXECUTOR-001)

Read: `Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_31B_extend_classify.md`

**Mandatory rules:**
1. ALL work in `Control_Plane_v2/_staging/`. 2. DTT: tests first. 3. Use compute_sha256() and pack(). 4. sha256:<64hex> format. 5. Clean-room verification. 6. Full regression. 7. Results file with all sections. 8. CP_BOOTSTRAP rebuild. 9. PKG-HO1-EXECUTOR-001 ONLY.

**10 Questions:**

1. What package does this handoff modify? What TWO files in the prompt_packs/contracts dirs are changed?
2. What are the 4 possible intent_signal.action values? When is "new" always used?
3. List all 6 domain labels and all 6 task labels.
4. Are intent_signal and labels added to the `required` array in classify.json? Why or why not?
5. What existing field in classify.json allows the new output fields without a schema violation?
6. Estimate the token budget impact: how many tokens does the expanded prompt use? Does it fit within classify_budget (2000)?
7. What happens if the LLM returns ONLY speech_act and ambiguity (no intent_signal, no labels)?
8. How many new tests are you adding? Name them.
9. What downstream handoffs will READ intent_signal and labels? Does THIS handoff implement any of those readers?
10. What tar format and hash format do you use for archives and manifests?

**Adversarial:**
11. If the LLM returns a domain label not in the closed vocabulary (e.g., "networking"), what happens? Who validates?
12. The prompt says "Do not include any text outside the JSON object" — is this still needed given structured_output in the contract?
13. Could the expanded prompt cause classify to exceed max_tokens:500 in the contract boundary?

STOP AFTER ANSWERING. Wait for approval.
```

### Expected Answers

1. PKG-HO1-EXECUTOR-001. PRM-CLASSIFY-001.txt and classify.json.
2. "new", "continue", "close", "unclear". "new" is always used for the first message in a session.
3. Domain: system, config, session, tools, docs, general. Task: inspect, modify, create, debug, plan, general.
4. No. They're optional during rollout. `required` stays `["speech_act", "ambiguity"]`. This ensures backward compatibility — if LLM doesn't produce them, the response still validates.
5. `additionalProperties: true` in the output_schema.
6. ~400 tokens for prompt, ~200 tokens for response (JSON with all fields). Total ~600, well within 2000 classify_budget.
7. Everything works. The output validates against the schema (speech_act + ambiguity are present, additionalProperties allows nothing else). Downstream code (HO2) uses `.get("intent_signal", {})` patterns and handles None gracefully.
8. 12 tests (list all).
9. H-29.1C (signal extraction reads labels), H-31C (intent lifecycle reads intent_signal.action), H-29.1C (consumption model matches labels). This handoff does NOT implement any readers — it only produces the data.
10. `pack()` for archives, `sha256:<64hex>` for manifests.
11. The LLM might hallucinate a label. The contract's boundary.structured_output enforces speech_act and ambiguity but NOT intent_signal/labels (they're not in boundary.structured_output). However, the output_schema has enum constraints for domain and task. If structured_output enforcement covers the full output_schema, the LLM would be forced to choose from the enum. If not, downstream consumers should validate against the closed vocabulary and default to "general" for unknown values.
12. Yes, it's still needed as a prompt instruction. The structured_output in boundary only enforces output shape, not the prompt's request. The instruction helps the LLM comply even in edge cases where structured_output might not fully constrain.
13. No. The response JSON with all fields is ~100-150 tokens. max_tokens:500 is for the output only. The prompt tokens are separate (counted against classify_budget, not max_tokens).
