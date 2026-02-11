# Control Plane v2 - Design Decisions

## Decision 1: Physical Structure - Separate Codebases Per Tier

**Decision:** Each tier (HOT, Second Order, First Order) has its own separate codebase.

**Reasoning:**
- One codebase = single point of compromise
- If First Order can influence shared code, HOT falls too
- Kernel/arena separation requires defense in depth

**Structure:**
- HOT codebase: signed/locked, changes require highest authority
- Second Order codebase: separate, changes require meta-level authority
- First Order codebase: the only one agents can touch

**Trade-off:** Harder to maintain (3 codebases), but integrity over convenience.

---

## Decision 2: Ledger Count is Behavioral, Not Structural

**Decision:** The "1 ledger at HOT, few at Second Order, many at First Order" constraint emerges from cognitive behavior, not code architecture.

**Reasoning:**
- HOT only focuses on 1 thing at a time → 1 active ledger
- Second Order has limited parallelism → few active ledgers
- First Order can fan out → many active ledgers
- The ledger mechanism is identical everywhere
- The constraint is cognitive (like attention), not syntactic

**Implication:** Same ledger system, tiers enforce different concurrency based on cognitive model.

---

## Decision 3: Memory Loops Per Tier

**Decision:** Each tier has a different memory structure.

| Tier | Fast Loop | Slow Loop |
|------|-----------|-----------|
| First Order | (none - it IS the fast loop) | (none - single loop memory) |
| Second Order | T1 ledger entries (live) | Its own ledger (work order history) |
| HOT | T2 promoted signals | Its own ledger (project/goal history) |

**Pattern:**
- Each tier's fast loop = the tier below
- Each tier's slow loop = its own ledger
- T1 doesn't remember - it just does
- T2 remembers the work order + sees T1 live
- HOT remembers the goal + sees T2 filtered

---

## Decision 4: Semantic Exchange (Prompts, Not Signals)

**Decision:** Tiers exchange prompts, not just status signals.

**Reasoning:**
- T2 → HOT isn't "status: failed" - it's a prompt with context
- "Here's what happened, here's the context, what should I do?"
- HOT responds with a prompt back
- This leverages LLM semantic capabilities
- Unlike syntactic systems, we're exchanging meaning

**Implication:** The "conversation" = the ledger trail of prompts, responses, constraints, budget, signals flowing through tiers.

---

## Decision 5: No Context Windows in Control Plane

**Decision:** Each turn is isolated. The ledger IS the memory, not context windows.

**Reasoning:**
- Prevents drift
- Prevents context contamination
- Prevents runaway token growth
- Forces everything to be recorded (auditable)
- Context is only open for that turn

**Implication:** Agents don't accumulate context. They read from ledger, act, write to ledger. Clean isolation.

---

## Decision 6: Lessons Become New Prompt Versions

**Decision:** When HOT detects patterns and proposes improvements, they become new prompt versions.

**Open:** Deployment method TBD (hot deploy vs framework update).

**Flow:**
1. HOT sees degradation in prompt effectiveness
2. HOT proposes new prompt / lessons learned
3. Human approves
4. New prompt package deployed
5. Version tracked (PC-C-001 v1.0 → v1.1)

---

## Decision 7: Quality Over Speed

**Decision:** Governance and accuracy take priority over speed, within reason.

**Reasoning:**
- Everything going through ledger exchanges adds latency
- But: accurate + learning system > fast + drifting system
- Scale concerns are premature - need to prove the model works first
- If things are accurate and learn, quality wins

**Trade-off accepted:** Latency cost is acceptable for governance benefits.

---

## Decision 8: Packages Contain Code, Changes Are Audited

**Decision:** Packages contain code (not just specs). Changes can be requested but are fully audited.

**Model:**
- Packages ship with code (deterministic, auditable baseline)
- System can request changes (create new, update existing)
- All changes: ledger audited, versioned, rollback-able

**What this means:**
- Known-good starting point (shipped code)
- Adaptability (system can evolve it via human-approved requests)
- Safety net (full audit + easy rollback)

---

## Decision 9: Control Plane Builds Things, Doesn't Self-Modify

**Decision:** The control plane is a BUILDER, not a self-modifier.

**Model:**
- Control plane = the factory (stable, governed)
- Applications = what the factory builds (generated, versioned)
- The control plane's own packages don't self-evolve

**Flow:**
```
Human: "Build me X"
    ↓
Control plane helps shape the spec
    ↓
Human approves spec
    ↓
Control plane generates code from spec
    ↓
Output delivered (separate from control plane)
```

---

## Decision 10: Anti-Recursion via Signature + Human Approval

**Decision:** Built apps are signed as "BUILT" and cannot invoke build capabilities. Human approves all installs.

**Enforcement:**
- Apps signed as "BUILT" (not "BUILDER")
- Signature checked at install and at build invocation
- "BUILT" cannot access build frameworks/orchestrations
- Human approves all installs (firewall against hacks)
- Suspicious requests flagged for human review

**Why human in the loop:**
- Catches edge cases signatures might miss
- Accountable (logged approval)
- Simpler than complex automated schemes

---

## Decision 11: Three Output Types for Built Artifacts

**Decision:** Built things can live in three places depending on type.

| Type | Where | Governance |
|------|-------|------------|
| Extension | Inside repo, merges into control plane | Parent governs |
| Module/Agent | Inside control plane | Parent governs |
| External app | Outside repo, standalone | Delivered and done |

**Governed by framework:** The framework that guides the build specifies output location.

**No recursive governance:** External apps are delivered and signed BUILT. Parent's job is done. No need for child to have its own control plane.

---

## Code Required - Grouped by Area

### Group A: Tier Communication Infrastructure

| Component | Description |
|-----------|-------------|
| Memory loops | T2 subscribes to T1 ledgers, HOT subscribes to T2 signals |
| Cross-tier ledger pointers | Signed hashes - T2 includes hash of T1 segment, HOT includes hash of T2 |
| Event subscription | Push/pull mechanism for tier-to-tier communication |

### Group B: Prompt System

| Component | Description |
|-----------|-------------|
| Prompt executor | Execute prompt contracts, validate input/output schema, log exchange |
| Prompt versioning | Track versions (PC-C-001 v1.0 → v1.1), propose updates, deploy new versions |

### Group C: Governance & Tracking

| Component | Description |
|-----------|-------------|
| Framework lineage | source_framework in registry, frameworks_active in ledger entries |
| Session/work order lifecycle | Session create/track/close, work order state machine |
| Pass/fail aggregation | T1 signals 0/1, T2 aggregates rates, HOT detects patterns |

### Group D: Control Flow

| Component | Description |
|-----------|-------------|
| Control messages | Schema for "stop", "correct" signals flowing down |
| Enforcement | T1 must honor control messages from T2/HOT |

### Group E: Human-in-the-Loop

| Component | Description |
|-----------|-------------|
| Human approval queue | Queue for pending approvals (installs, specs, prompts) |
| Signature + approval flow | Check signatures, route to human, log decisions |

### Group F: Package System

| Component | Description |
|-----------|-------------|
| Package audit logging | Log all package changes to ledger |
| Output type routing | Route built artifacts to correct location based on framework |

### Group G: Build Orchestration

| Component | Description |
|-----------|-------------|
| Spec shaping | Orchestration: idea → clarify → spec → human approval |
| Code generation | Orchestration: approved spec → generate → validate → deliver |

---

## Already Have (pieces to build on)

| File | What it provides |
|------|------------------|
| auth.py | Identity, authentication providers |
| authz.py | Role → action mapping, permission checks |
| packages.py | Pack/unpack tar.gz, hash verification |
| ledger_client.py | Basic ledger write/read |
| merkle.py | Hash trees, merkle roots |
| integrity.py | Integrity checking |
| gate_operations.py | CREATE/INSTALL/UPDATE/REMOVE flow |

---

## Open Questions

- Where exactly do lessons persist? (prompt versions, framework updates, or both?)
- Hot deploy vs staged deployment for prompt updates?
- Escalation path when human is unavailable?
- Specific trigger thresholds for T2 → HOT attention?
- How do extensions get promoted from CANDIDATE to BUILDER-level?

