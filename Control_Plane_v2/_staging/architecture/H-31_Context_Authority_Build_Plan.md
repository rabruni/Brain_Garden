# H-31 Build Plan: Context Authority + HO3 Learning + Budget
**Purpose:** This is the plan. Agents write the builder handoffs from this. Do not treat this as a handoff itself.

**Last completed handoff:** H-30 (forensic observability). Baseline: 22 packages, 693 installed tests, 8/8 gates.

**What we're building:** Three things that belong together:
1. **Context Authority** — replace the dumb-pipe attention system with a deterministic projection that knows what's alive, what's relevant, and what fits in budget.
2. **HO3 Learning Model** — complete H-29's skeleton so learning artifacts are structured, governed, replay-safe, and consumable without an LLM call.
3. **Budget Centralization** — one source of truth for all token budgets, admin-editable, no code defaults that silently diverge.

---

## Cross-Cutting Constraint #1: Budget Centralization

**Rule:** `admin_config.json` is the single source of truth for ALL budgets. No defaults in code that silently diverge from config. Every handoff in this sequence must respect this.

**Current problem — budgets are scattered:**
- `admin_config.json` → `budget.classify_budget` (2000), `budget.synthesize_budget` (100000), `budget.session_token_limit` (200000)
- `HO2Config` dataclass → has its own defaults (classify_budget=2000, synthesize_budget=16000) that can diverge from config
- `PRC-CLASSIFY-001` boundary → `max_tokens: 500` (output cap, separate from classify_budget)
- `TokenBudgeter` → `BudgetConfig` with its own `session_token_limit`
- Projection budget → doesn't exist yet
- Consolidation budget → doesn't exist yet
- HO3 bias injection budget → doesn't exist yet

**Required state after this plan is complete:**
```json
"budget": {
    "session_token_limit": 200000,
    "classify_budget": 2000,
    "synthesize_budget": 100000,
    "projection_budget": 10000,
    "consolidation_budget": 4000,
    "ho3_bias_budget": 2000,
    "followup_min_remaining": 500,
    "budget_mode": "warn",
    "turn_limit": 50,
    "timeout_seconds": 7200
}
```

All budget values in one place. HO2Config reads from this. TokenBudgeter reads from this. Contracts reference this. No code-level defaults that override config without the admin knowing.

**Per-handoff budget responsibility:**
- H-31A: Add `consolidation_budget` and `ho3_bias_budget` to budget section. Audit HO2Config — verify every budget field reads from config, flag any hardcoded defaults that diverge.
- H-31B: Verify classify prompt + response fits within `classify_budget`. If it doesn't after adding intent + labels, increase in config — not in code.
- H-29.1: Bias consumption respects `ho3_bias_budget` (top-k artifacts that fit within this token allocation).
- H-31D: Add `projection_budget` to budget section.
- H-31E: Projection reads budget from config. Remove redundant attention budget constants from HO2Config.

**Enforcement:** Every handoff's test suite must include a test that verifies the relevant budget value comes from config, not a hardcoded default. If a test passes with config removed, the budget isn't properly centralized.

---

## Cross-Cutting Constraint #2: HO3 Consumption Model

**This is the mechanical contract for how HO2 uses learning artifacts. Six lines, no drift:**

1. **Filter:** HO2 checks structured fields (type, scope, enabled, expiry).
2. **Rank:** HO2 sorts by numbers only (weight × decay × recency).
3. **Scope:** HO2 matches labels (current context labels ∈ artifact.scope).
4. **Budget:** Top-k artifacts that fit within `ho3_bias_budget` tokens.
5. **Inject:** HO2 copies a stored text field (`context_line`) verbatim into the prompt.
6. **HO2 never reads meaning.** LLM only wrote that text once, at consolidation time.

**Label matching:** Classify emits labels from a closed vocabulary every turn. Artifacts carry labels from the same vocabulary. HO2 does set intersection — `artifact.labels ∩ turn.labels != empty` → candidate for injection. Pure string matching, no semantics.

**Two learning paths, same artifact shape:**
- **Explicit:** Human states something directly ("always give concise answers") → artifact created immediately from classify recognition.
- **Implicit:** Pattern recurs across interactions → bistable gate fires → consolidation produces artifact.

Both paths produce identical artifact structure. The difference is the trigger, not the output.

---

## The Sequence (Serial, Each Depends on Prior)

### H-31A: Wire H-29 Into ADMIN Runtime

**What:** Connect the already-built HO3Memory to the ADMIN runtime. H-29 built everything — HO3Memory class, HO2 supervisor hooks, consolidation plumbing. None of it is active because `build_session_host_v2()` in `main.py` doesn't instantiate HO3Memory or pass it to HO2Supervisor. This handoff is **instrumentation** — signals start flowing, consolidation can fire, but the output is experimental data collection, not a trusted steering layer.

**Package scope:** PKG-ADMIN-001 (config + wiring in main.py), PKG-SESSION-HOST-V2-001 (consolidation caller)

**Exact changes:**

1. In `build_session_host_v2()` (main.py:1122), after the HO2 supervisor construction (step 7):
   - Import HO3Memory, HO3MemoryConfig from ho3_memory (try/except pattern)
   - Read HO3 config from admin_config.json (new `ho3` section)
   - Instantiate HO3Memory with config
   - Pass `ho3_memory=ho3_memory` to HO2Supervisor constructor
   - The HO2Supervisor already accepts this parameter (H-29B added it), guarded by `if self._ho3_memory and self._config.ho3_enabled`

2. In admin_config.json, add `ho3` config section:
   ```json
   "ho3": {
     "enabled": true,
     "memory_dir": "HOT/memory",
     "gate_count_threshold": 5,
     "gate_session_threshold": 3,
     "gate_window_hours": 168
   }
   ```

3. Map ho3 config values to HO2Config fields that H-29B added:
   - `ho3_enabled` from ho3.enabled
   - `ho3_memory_dir` from ho3.memory_dir (resolved against plane_root)
   - `ho3_gate_count_threshold`, `ho3_gate_session_threshold`, `ho3_gate_window_hours`

4. Wire the consolidation caller (the missing piece from H-29):
   - `SessionHostV2.process_turn()` (session_host_v2.py:63-69) currently drops `consolidation_candidates` from the HO2 TurnResult — it only copies response, tool_calls, exchange_entry_ids
   - `run_consolidation()` exists on HO2Supervisor (ho2_supervisor.py:537) but has no runtime caller — only tests call it
   - Fix: In SessionHostV2.process_turn(), after constructing the return TurnResult, check if the HO2 result has non-empty consolidation_candidates. If so, call `self._ho2.run_consolidation(candidates)`. This runs AFTER response is ready but BEFORE return — or alternatively, after return in Shell._dispatch_turn() after _format_result().
   - The consolidation is out-of-band to the user — it doesn't change the response. It dispatches a consolidation WO to HO1 which writes an overlay to HO3 memory.
   - Package scope expansion: PKG-SESSION-HOST-V2-001 gets a small modification (read consolidation_candidates, call run_consolidation)

5. Add `consolidation_budget: 4000` and `ho3_bias_budget: 2000` to admin_config.json budget section. Audit all HO2Config budget fields against config values — document any divergence.

**What this enables:** After this handoff, every ADMIN session will:
- Inject HO3 biases into synthesize context (Step 2b+)
- Log `intent:<speech_act>` signals after each turn
- Check the bistable gate post-turn
- Populate `consolidation_candidates` on TurnResult
- Actually invoke `run_consolidation()` when candidates exist (completing the H-29 loop)

**What this does NOT do yet:** The injected biases are unstructured prose from H-29's current consolidation prompt. They're not filtered/ranked/scoped. This is okay — H-29.1 fixes the artifact model. For now, we're collecting signal data and proving the plumbing works.

**Risk:** Low. All HO3 code paths already exist and have tests. The consolidation caller is ~10 lines. This is wiring, not new logic.

**Tests:** Verify HO3Memory is instantiated when config.ho3.enabled=true. Verify it's None when enabled=false. Verify signals appear in HOT/memory/signals.jsonl after a turn. Verify existing behavior unchanged when ho3 section missing from config. Verify consolidation_candidates flow through SessionHostV2. Verify run_consolidation is called when candidates are non-empty. Verify budget values come from admin_config.json not HO2Config defaults.

**Definition of Done:** Run a real ADMIN session. After the session, `HOT/memory/signals.jsonl` exists and contains signal events. `read_active_biases()` returns data (even if empty initially — that's correct, no gate has crossed yet). If enough signals accumulate across sessions to cross the gate, `run_consolidation()` fires and `HOT/memory/overlays.jsonl` gets an entry.

---

### H-31B: Extend Classify (Intent + Labels)

**What:** Add intent recognition AND a closed label vocabulary to the classify LLM call. Zero additional LLM calls — the classify prompt already sees the user message. We're asking it to also tell us (a) whether this is a continuation/new/close, and (b) what domain/task labels apply.

**Package scope:** PKG-HO1-EXECUTOR-001 (prompt pack + contract)

**Exact changes:**

1. Update PRM-CLASSIFY-001.txt (currently 10 lines):
   ```
   Current output schema:
   {
     "speech_act": one of "greeting", "question", "command", "reentry_greeting", "farewell",
     "ambiguity": one of "low", "medium", "high"
   }

   Extended output schema:
   {
     "speech_act": one of "greeting", "question", "command", "reentry_greeting", "farewell",
     "ambiguity": one of "low", "medium", "high",
     "intent_signal": {
       "action": one of "new", "continue", "close", "unclear",
       "candidate_objective": "short description of what user is trying to do",
       "confidence": 0.0 to 1.0
     },
     "labels": {
       "domain": one of <closed domain list>,
       "task": one of <closed task list>
     }
   }
   ```

   Intent instructions:
   - "new" = user is starting a new topic/task
   - "continue" = user is continuing the same thread as previous turns
   - "close" = user is done with current thread (farewell, thanks, etc.)
   - "unclear" = can't determine intent relationship
   - First message in a session is always "new"
   - candidate_objective is a short phrase describing the goal

2. Define the closed label vocabulary (ADMIN-scoped, start small):

   **Domain labels** (what area):
   - `system` — control plane, packages, gates, manifests
   - `config` — admin_config, agent setup, budget settings
   - `session` — session management, history, turns
   - `tools` — tool usage, tool configuration
   - `docs` — documentation, specs, design
   - `general` — doesn't fit other domains

   **Task labels** (what action):
   - `inspect` — reading, examining, listing, querying
   - `modify` — changing, updating, fixing, configuring
   - `create` — building, generating, writing new things
   - `debug` — troubleshooting, diagnosing, tracing
   - `plan` — designing, strategizing, scoping
   - `general` — doesn't fit other tasks

   This is 6×6 = 36 possible combinations. Small enough for exact string matching. The vocabulary is defined in admin_config.json (not hardcoded in the prompt pack) so it can grow without a code change:
   ```json
   "classify_labels": {
     "domain": ["system", "config", "session", "tools", "docs", "general"],
     "task": ["inspect", "modify", "create", "debug", "plan", "general"]
   }
   ```
   The prompt template reads this list and includes it in the classify instructions.

3. Update PRC-CLASSIFY-001 (classify.json) output_schema:
   - Add `intent_signal` and `labels` to properties
   - Keep `additionalProperties: true` (already set — backward compatible)
   - Do NOT add intent_signal or labels to `required` yet — optional during rollout

**What this enables:**
- HO2 gets intent signals to manage lifecycle (H-31C)
- HO2 gets labels to match against learning artifacts (H-29.1 consumption model)
- HO2 gets richer signals to log to HO3 (beyond just `intent:<speech_act>`)

**After this handoff, HO2 post-turn signal extraction can produce:**
- `intent:<speech_act>` (existing)
- `tool:<tool_id>` (existing)
- `domain:<domain_label>` (new — from classify labels)
- `task:<task_label>` (new — from classify labels)

This directly addresses the "signal vocabulary too thin" gap. Not by inventing 50 signal types, but by having classify emit labels that naturally become signals.

**Risk:** Low. Optional fields, backward compatible. If LLM doesn't produce labels, everything still works.

**Critical concern — classify budget:** Current classify_budget is 2000 tokens. The prompt is currently tiny (10 lines). Adding intent + labels instructions will grow it. The prompt template needs to include the label vocabulary list from config. Agent should verify total prompt + response fits within classify_budget. If not, increase in admin_config.json.

**Tests:** Existing classify tests still pass. intent_signal parsed when present. Labels parsed when present. Missing fields don't break downstream. Each intent action value maps correctly. Domain and task labels are from the closed vocabulary.

**Definition of Done:** Classify on "what packages are installed?" → intent_signal.action = "new" (or "continue"), labels.domain = "system", labels.task = "inspect". Classify on "thanks, bye" → intent_signal.action = "close". Labels come from the vocabulary defined in config.

---

### H-29.1: HO3 Learning Model Completion

**What:** Close the six design gaps in H-29 so learning artifacts are structured, governed, replay-safe, and consumable by the mechanical model (filter/rank/scope/inject). This is NOT a rewrite of HO3Memory — it's adding what's missing to make the existing skeleton trustworthy.

**Package scope:** PKG-HO3-MEMORY-001 (primary), PKG-HO2-SUPERVISOR-001 (signal extraction + consumption), PKG-HO1-EXECUTOR-001 (consolidation prompt)

**Why now:** H-31A wires H-29 as instrumentation. H-31B gives us labels. Before H-31E promotes learning artifacts into the projection, those artifacts need to be structured and governed. This is the window.

**Six gaps to close (from design review):**

#### Gap 1: Structured Artifact Model (replaces free-form bias statements)

Current: consolidation produces `{"bias": "prose text", "salience_weight": 0.6}` — unstructured, can't be filtered/scoped/matched.

New artifact shape:
```json
{
  "artifact_id": "ART-<hash of source signals + gate window + model + prompt version>",
  "artifact_type": "topic_affinity | interaction_style | task_pattern | constraint",
  "labels": {
    "domain": ["system", "config"],
    "task": ["inspect"]
  },
  "weight": 0.7,
  "scope": "agent | session | global",
  "context_line": "User frequently explores package structure and manifest contents",
  "enabled": true,
  "created_at_event_ts": "2026-02-18T...",
  "expires_at_event_ts": null,
  "source_signal_ids": ["domain:system", "tool:read_file"],
  "source_event_ids": ["E-001", "E-025", "E-040"],
  "gate_snapshot": {"count": 12, "sessions": 3},
  "model": "claude-sonnet-4-20250514",
  "prompt_pack_version": "PRM-CONSOLIDATE-001-v2",
  "consolidation_event_ts": "2026-02-18T..."
}
```

**HO2 reads:** artifact_type, labels, weight, scope, enabled, expires_at_event_ts, context_line
**HO2 never reads for meaning:** context_line is passed through verbatim

Update PRM-CONSOLIDATE-001.txt to produce this structured shape instead of free-form prose. The LLM's job at consolidation time:
- Assign artifact_type from a closed set
- Assign labels from the same closed vocabulary as classify
- Write a human-readable context_line (one sentence, plain language)
- Assign initial weight (0.0-1.0)

#### Gap 2: Event-Time Decay (replaces wall-clock decay)

Current: `read_signals()` and `read_active_biases()` compute decay from `datetime.now()` — breaks deterministic replay.

Fix: All time-dependent computations take `as_of_ts` parameter:
- `read_signals(signal_id=None, min_count=None, as_of_ts=None)` — if as_of_ts provided, decay computed relative to it. If None, uses wall clock (backward compatible but non-deterministic).
- `read_active_biases(as_of_ts=None)` — same pattern.
- HO2 passes the current turn's event timestamp as `as_of_ts`, making the computation replay-safe.
- During replay, supply the original turn timestamp → get identical decay values.

#### Gap 3: Overlay Lifecycle (revoke/deactivate)

Current: overlays can only be added. No way to deactivate, revoke, or expire them. Learning can only grow, never shrink.

Add to HO3Memory API:
- `deactivate_overlay(artifact_id, reason, event_ts)` — sets enabled=false. Overlay stays in ledger (immutable) but stops being returned by `read_active_biases()`.
- `update_overlay_weight(artifact_id, new_weight, reason, event_ts)` — appends weight-change event. Latest weight wins.
- Expiry: `read_active_biases(as_of_ts)` filters out artifacts where `expires_at_event_ts < as_of_ts`.

These are append-only operations — a deactivation is a new event, not a mutation. The overlay file remains immutable.

#### Gap 4: Idempotency + Duplicate Control

Current: repeated consolidation for the same signals can create duplicate overlays.

Fix: `artifact_id = hash(sorted(source_signal_ids) + gate_window_key + model + prompt_pack_version)`. Before writing, check if an artifact with this ID already exists. If so, skip or update weight — don't create a duplicate.

#### Gap 5: Richer Signal Extraction

Current: HO2 post-turn only extracts `intent:<speech_act>` and `tool:<tool_id>`.

After H-31B, classify returns labels. HO2 post-turn signal extraction expands to:
- `intent:<speech_act>` (existing)
- `tool:<tool_id>` (existing)
- `domain:<domain_label>` (new, from classify labels)
- `task:<task_label>` (new, from classify labels)
- `outcome:<success|failed|escalated>` (new, from WO result)

This gives the bistable gate meaningful patterns to detect — not just "user sends commands" but "user inspects system packages frequently" or "tool calls in config domain keep failing."

#### Gap 6: Consumption Policy in HO2

This implements the six-line mechanical model at Step 2b+. Replace the current "dump all biases into context" with:

```python
def select_biases(
    artifacts: list[dict],       # from read_active_biases(as_of_ts)
    turn_labels: dict,           # from classify result {"domain": "system", "task": "inspect"}
    ho3_bias_budget: int,        # from admin_config.json
    as_of_ts: str                # current turn event timestamp
) -> list[dict]:
    # 1. Filter: enabled=True, not expired, scope matches
    # 2. Scope match: artifact.labels ∩ turn_labels != empty (or scope=global)
    # 3. Rank: weight × decay(as_of_ts) × recency, descending
    # 4. Budget: take top-k that fit within ho3_bias_budget tokens
    # 5. Return: list of context_lines to inject verbatim
```

Pure function. No LLM. Deterministic. Replay-safe.

**Explicit learning path (bonus, not required for MVP):**
If classify recognizes an explicit user statement ("always give concise answers"), HO2 can write a learning artifact directly — no gate needed. Same artifact shape, different trigger. This can be deferred if the handoff is too large.

**Risk:** Medium. Touches HO3Memory API, consolidation prompt, HO2 signal extraction, and HO2 bias consumption. But each gap is a bounded change with clear tests.

**Tests:**
- Structured artifact: consolidation produces all required fields from closed vocabulary
- Event-time decay: same inputs + same as_of_ts → identical decay values across runs
- Overlay lifecycle: deactivated artifact not returned by read_active_biases
- Expiry: expired artifact not returned when as_of_ts > expires_at
- Idempotency: duplicate consolidation for same signals → no duplicate artifact
- Richer signals: domain and task labels appear in signals.jsonl after a turn
- Consumption: select_biases returns only matching, non-expired, budget-fitting artifacts
- Label matching: artifact with labels.domain=["system"] matches turn with labels.domain="system"
- Budget enforcement: artifacts beyond ho3_bias_budget tokens are excluded

**Definition of Done:** After several sessions, overlays.jsonl contains structured artifacts with types, labels, and context_lines. HO2's bias injection at Step 2b+ only injects artifacts whose labels match the current turn's classify labels. Artifacts that exceed the bias budget are excluded. Deactivated artifacts are not injected. Replay with same inputs produces identical bias selection.

---

### H-31C: Intent Lifecycle in HO2

**What:** HO2 gains a pure deterministic function that reads the classify output's intent_signal and manages intent as a first-class lifecycle entity in ho2m.jsonl.

**Package scope:** PKG-HO2-SUPERVISOR-001

**Exact changes:**

1. New file: `HO2/kernel/intent_resolver.py`

   Pure function, no LLM calls:
   ```python
   def resolve_intent_transition(
       active_intents: list[dict],  # currently live intents from ledger
       classify_result: dict,        # includes intent_signal if present
       ruleset: dict                 # policy config (from admin_config or static)
   ) -> TransitionDecision
   ```

   TransitionDecision contains:
   - action: "declare" | "continue" | "supersede" | "close" | "noop"
   - new_intent: dict (if declare or supersede) with intent_id, scope, objective
   - closed_intent_id: str (if supersede or close)
   - conflict_flag: dict or None (if multiple active intents, unclear signal)

   Transition table:
   - No active intent + action != close → DECLARE new intent
   - Active intent + continue → CONTINUE (no event written)
   - Active intent + new → SUPERSEDE old + DECLARE new
   - Active intent + close → CLOSE active intent
   - Active intent + unclear → CONTINUE + emit CONFLICT_FLAG
   - No intent_signal in classify result → CONTINUE if active intent exists, DECLARE if not (bridge mode)

2. Bridge mode (session start):
   - In handle_turn(), before Step 2a (classify), check if session has an active intent
   - If not (first turn), auto-declare: write INTENT_DECLARED to ho2m.jsonl with scope=SESSION, objective derived from first classify result
   - This is a real intent entity with real lifecycle — not a session alias

3. New event types written to ho2m.jsonl:
   - `INTENT_DECLARED { intent_id, scope, objective, parent_intent_id? }`
   - `INTENT_SUPERSEDED { intent_id, superseded_by_intent_id, reason }`
   - `INTENT_CLOSED { intent_id, outcome, reason }`

4. In handle_turn(), after Step 2a (classify), before Step 2b (attention):
   - Call resolve_intent_transition()
   - Write lifecycle events to ho2m.jsonl based on decision
   - Store current active intent_id for use by projection (H-31D/E)

5. Intent ID format: `INT-<session_id>-<sequence>` (e.g., INT-SES-F8805C46-001)

6. Active intent tracking: scan ho2m.jsonl for INTENT_DECLARED events not followed by INTENT_CLOSED or INTENT_SUPERSEDED for the same intent_id. This is the "latest event wins" reducer applied to intents.

**Multi-thread awareness:** For MVP (ADMIN), one active intent per session. If multiple active intents are detected, emit CONFLICT_FLAG and continue with most recent. When RESIDENT/DoPeJar launches with multi-thread awareness, the resolver grows to support multiple concurrent intents — but the data model supports it from day one.

**Risk:** Medium. New logic in dispatch path. But pure function, no LLM calls, fully testable.

**Tests:**
- No active intent + new → DECLARE
- Active intent + continue → CONTINUE (no event)
- Active intent + new → SUPERSEDE + DECLARE
- Active intent + close → CLOSE
- Active intent + unclear → CONTINUE + CONFLICT_FLAG
- Missing intent_signal → bridge mode behavior
- Multiple active intents → conflict detection + most-recent-wins
- Determinism: same inputs → same output
- Bridge mode: first turn auto-declares intent

**Definition of Done:** After a 3-turn session, ho2m.jsonl contains INTENT_DECLARED (turn 1), no intent events (turns 2-3 if "continue"). After a session where user switches topic, ho2m.jsonl contains INTENT_DECLARED, INTENT_SUPERSEDED, INTENT_DECLARED.

---

### H-31D: Liveness Reducer + Projection Snapshot

**What:** A pure function that reads ho2m.jsonl + ho1m.jsonl and computes what's alive. Writes PROJECTION_COMPUTED snapshots to a new overlay ledger.

**Package scope:** PKG-HO2-SUPERVISOR-001

**Exact changes:**

1. New file: `HO2/kernel/liveness.py`

   ```python
   def reduce_liveness(
       ho2m_entries: list[dict],
       ho1m_entries: list[dict]
   ) -> LivenessState
   ```

   LivenessState contains:
   - intents: dict[intent_id → {status, scope, objective, declared_at, closed_at?}]
   - work_orders: dict[wo_id → {status, intent_id, wo_type, planned_at, completed_at?}]
   - active_intents: list[intent_id] (LIVE intents)
   - open_work_orders: list[wo_id] (planned/dispatched, no completion)
   - failed_items: list[{wo_id, reason, timestamp}]
   - escalations: list[{wo_id, reason, timestamp}]

   Rules ("latest event wins"):
   - For each entity, gather all lifecycle events, sort by (timestamp, entry_id)
   - Last event determines state
   - LIVE events: INTENT_DECLARED, WO_PLANNED, WO_DISPATCHED
   - NOT LIVE events: INTENT_CLOSED, INTENT_SUPERSEDED, WO_COMPLETED, ESCALATION
   - Cross-ledger join: WO_PLANNED in ho2m, WO_COMPLETED in ho1m, matched by work_order_id
   - Event adapter: WO_PLANNED → WO_OPENED, WO_COMPLETED → WO_CLOSED(success), ESCALATION after WO → WO_CLOSED(failed)

2. New file: `HO2/kernel/overlay_writer.py`

   ```python
   def write_projection(
       liveness: LivenessState,
       session_id: str,
       turn_id: str,
       token_budget: int,
       overlay_path: Path
   ) -> dict
   ```

   Appends PROJECTION_COMPUTED entry to ho2_context_authority.jsonl:
   ```json
   {
     "overlay_type": "PROJECTION_COMPUTED",
     "timestamp": "...",
     "session_id": "...",
     "turn_id": "...",
     "token_budget": 2400,
     "active_intents": [...],
     "open_work_orders": [...],
     "failed_items": [...],
     "escalations": [...],
     "ho3_artifacts_injected": [...],
     "ruleset_hash": "sha256:..."
   }
   ```

3. Overlay ledger path: `HO2/ledger/ho2_context_authority.jsonl`
   - Separate from ho2m.jsonl (source vs derived)
   - Uses LedgerClient (append-only, hash-chained)
   - Created by overlay_writer on first projection

**Risk:** Low. Pure functions, no side effects beyond ledger append. Fully testable with synthetic data.

**Tests:**
- Zombie WO: WO_PLANNED with no WO_COMPLETED → appears in open_work_orders
- Complete WO: WO_PLANNED → WO_COMPLETED → status=completed, not in open list
- Failed WO: ESCALATION after WO → appears in failed_items
- Open session: SESSION_START with no SESSION_END → open
- Intent lifecycle: INTENT_DECLARED → INTENT_SUPERSEDED → not in active_intents
- Cross-ledger join: WO_PLANNED (ho2m) matched with WO_COMPLETED (ho1m) by wo_id
- Determinism: same entries in different order → same LivenessState
- Overlay written: PROJECTION_COMPUTED appears in ho2_context_authority.jsonl

**Definition of Done:** Given the actual ho2m.jsonl and ho1m.jsonl from a real session, reduce_liveness correctly identifies which WOs are open, which are completed, which intents are active. Projection snapshot is written to overlay ledger.

---

### H-31E: Replace Attention.py

**What:** Swap the attention system at Step 2b. Instead of dumping raw serialized ledger entries, compute a structured projection from liveness state + HO3 learning artifacts, under budget.

**Package scope:** PKG-HO2-SUPERVISOR-001 (primary), PKG-ADMIN-001 (config)

**Exact change points in ho2_supervisor.py:**
- Line 37: `from attention import AttentionRetriever, ContextProvider, AttentionContext` → import new module
- Line 129: `self._attention = AttentionRetriever(...)` → construct new projection engine
- Lines 188-199: Replace 3-call sequence (horizontal_scan, priority_probe, assemble_wo_context) with single call that combines liveness projection + HO3 bias selection
- HO2Config: attention_templates, attention_budget_tokens, attention_budget_queries, attention_timeout_ms replaced with projection_budget

**Other files that reference attention.py:**
- test_ho2_supervisor.py:28 and :222-309 → update tests
- manifest.json:24,39 → remove attention.py asset, add new module assets
- main.py:1260-1262 → update HO2Config construction if fields change

**Critical constraint — output shape must match:**
```python
{
    "user_input": user_message,
    "classification": classification,
    "assembled_context": {
        "context_text": ...,    # NOW: structured projection + HO3 context_lines
        "context_hash": ...,
        "fragment_count": ...,
        "tokens_used": ...,
    },
}
```
This flows into PRM-SYNTHESIZE-001.txt via `{{assembled_context}}`. If the shape is preserved, HO1 and the synthesize prompt don't change. The CONTENT of context_text changes (structured projection + learning artifacts vs raw JSON dump) but the shape is the same.

**What the new projection contains (assembled from prior handoffs):**
1. Active intent header (from H-31C intent lifecycle)
2. Open/failed WOs in priority order (from H-31D liveness)
3. HO3 learning artifacts matching current turn labels (from H-29.1 consumption model)
4. All within projection_budget tokens (from budget config)

**Rollout:**
1. Shadow mode first: compute projection AND run old attention. Log both. Compare. Don't change what HO1 sees.
2. After validation: swap to projection output. Remove old attention calls.
3. After stable: remove attention.py from package.

**Risk:** Medium-high. This changes what the LLM sees. Shadow mode mitigates — compare outputs before committing.

**Tests:**
- Same output shape as old assemble_wo_context
- Structured projection contains active intent info
- Open WOs appear in projection
- Failed WOs appear with higher priority
- HO3 artifacts injected when labels match, excluded when they don't
- Token budget is respected (projection_budget from config)
- Shadow mode: both old and new produce output, new is logged but old is used
- Enforcement mode: new output is used

**Definition of Done:** In shadow mode, every turn logs both old attention output and new projection output to the overlay ledger. In enforcement mode, the synthesize LLM sees structured context with liveness state + learning artifacts instead of raw JSON dump, and response quality is maintained or improved.

---

## What This Plan Does NOT Include (Explicitly Deferred)

- **Constraint/dependency/error lifecycle entities** — nothing writes these today. No phantom models.
- **Multi-intent unions** — ADMIN uses single active intent. Multi-thread is a RESIDENT/DoPeJar concern.
- **Semantic constraint refinement** — no subset reasoning.
- **Auto-supersession from text** — supersession is always explicit.
- **Hot/cold storage tiers** — deferred.
- **Explicit learning path** — classify recognizing direct user preferences (e.g., "always be concise") and writing artifacts without the bistable gate. Can be added to H-29.1 if scope allows, otherwise separate.

---

## Dependency Graph

```
H-31A: Wire H-29 (PKG-ADMIN-001 + PKG-SESSION-HOST-V2-001)
  │     Signals flow. Consolidation fires. Instrumentation.
  │
  ▼
H-31B: Extend Classify (PKG-HO1-EXECUTOR-001)
  │     Intent signals + closed label vocabulary.
  │
  ├─────────────────────────┐
  ▼                         ▼
H-29.1: HO3 Learning      H-31C: Intent Lifecycle
  Model Completion           (PKG-HO2-SUPERVISOR-001)
  (PKG-HO3-MEMORY-001 +     │
   PKG-HO2-SUPERVISOR-001 + │
   PKG-HO1-EXECUTOR-001)    │
  │                         │
  │  ┌──────────────────────┘
  ▼  ▼
H-31D: Liveness + Overlay (PKG-HO2-SUPERVISOR-001)
  │
  ▼
H-31E: Replace Attention (PKG-HO2-SUPERVISOR-001 + PKG-ADMIN-001)
        Consumes BOTH liveness projection AND HO3 artifacts.
```

**Note:** H-29.1 and H-31C can run in parallel after H-31B — they touch different packages (mostly). But both must complete before H-31D/E.

Each step produces working code with tests. Each step is independently valuable. If you stop after H-31A, you have HO3 memory flowing. If you stop after H-31C, you have intent tracking. If you stop after H-29.1, you have governed learning artifacts. The system gets smarter at each step.

---

## Agent Team Notes

- **ChatGPT** has the high-level design understanding — intent model, HO3/HOT architecture, how we arrived at H-29/signal memory, the consumption model, bistable gates, epigenetic memory. Use for design validation and gap analysis.
- **Claude Code** writes the handoffs. Give it this plan + the handoff standard (BUILDER_HANDOFF_STANDARD.md) and it produces the builder handoff documents.
- **Codex** does root cause analysis and handoff improvements. Has depth of codebase view. Use for verifying code paths, finding seams, and improving handoff specificity after first draft.
