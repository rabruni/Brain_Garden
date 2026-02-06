# Memory Model: HO Tiers
**Version**: 1.0
**Locked**: 2026-02-04

---

## Core Insight

The HO (Higher Order) tier system serves multiple dimensions simultaneously:

```
Dimension 1: INTEGRITY (System of Record)
├── All ledgers are hash-chained
├── Append-only
└── Verifiable

Dimension 2: COGNITION (Altitude)
├── HO1: First Order  → "Do this one thing"
├── HO2: Second Order → "Meta-aware of what's happening"
└── HO3: Higher Order → "Learn from all of it"

Dimension 3: WORK TYPE
├── HO1: Jobs         → 1-shot prompts, lowest cognitive unit
├── HO2: Work Orders  → Coordinated outcomes
└── HO3: Intent       → Strategic direction

Dimension 4: MEMORY
├── HO1: NO memory    → Stateless, no drift possible
├── HO2: Outcome memory → Knows goal + meta-aware of progress
└── HO3: Learning memory → Accumulates wisdom
```

---

## HO1: First Order (Fast Memory)

### Characteristics
- **Cognitive Level**: Do this one thing
- **Memory**: None (stateless)
- **Drift Risk**: Zero
- **Work Type**: Jobs, 1-shot prompts

### Behavior
```
Agent executes:
├── Has NO memory of what it did
├── If it retries → same inputs = same behavior
├── Cannot drift because it cannot remember
└── Ledger is FOR OTHERS to read, not for the agent
```

### Ledgers
- Writes to: L-EXEC, L-EVIDENCE
- Reads from: Nothing (inputs provided)

### Why No Memory?
If an agent can't remember, it can't:
- Contradict itself
- Hallucinate history
- Drift from expected behavior
- Compound errors across turns

---

## HO2: Second Order (Slow Memory)

### Characteristics
- **Cognitive Level**: Meta-aware of what's happening
- **Memory**: Session/work order scoped
- **Drift Risk**: Controlled (external memory)
- **Work Type**: Work Orders, coordination

### Behavior
```
Agent coordinates:
├── Knows the OUTCOME it's seeking
├── Meta-aware: "Is this working?"
├── Can adjust approach based on L-EXEC entries
└── Memory is scoped to work order/session
```

### Ledgers
- Writes to: L-WORKORDER, session ledgers
- Reads from: L-EXEC, L-EVIDENCE (from HO1)

### Memory Scope
Memory is:
- Bounded by session/work order
- External (in ledger, not context)
- Verifiable (hash-chained)

---

## HO3: Higher Order (Learning Memory)

### Characteristics
- **Cognitive Level**: Learn from all of it
- **Memory**: Long-term, strategic
- **Drift Risk**: Controlled (governed artifacts)
- **Work Type**: Intent, frameworks, wisdom

### Behavior
```
Agent learns:
├── Sees patterns across work orders
├── Can evolve frameworks
├── Long-term strategic memory
└── This is where wisdom accumulates
```

### Ledgers
- Writes to: L-INTENT, L-PACKAGE
- Reads from: All lower-tier ledgers

### Learning Scope
Learning is:
- Accumulated across sessions
- Codified in frameworks/specs
- Governed (package installs)
- Versioned and auditable

---

## Read Hierarchy

```
HO3 reads → L-INTENT + L-WORKORDER + L-EXEC (full view)
HO2 reads → L-WORKORDER + L-EXEC (coordination view)
HO1 reads → Nothing from ledgers (stateless execution)
      ↓
   writes → L-EXEC (for others to observe)
```

Each tier reads DOWN, writes to its own level.

---

## The Recursion

An agent at HO1 writes to L-EXEC, but **it doesn't read its own L-EXEC**.

The ledger is for the TIER ABOVE to observe.

This prevents the agent from "remembering" and drifting.

```
┌─────────────────────────────────────────────────────────────┐
│                          HO3                                │
│                   (reads everything)                        │
│                                                             │
│   Sees all patterns, learns, evolves frameworks             │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │ reads
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                          HO2                                │
│                   (reads HO1 + own)                         │
│                                                             │
│   Coordinates work, tracks progress, adjusts approach       │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │ reads
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                          HO1                                │
│                   (reads nothing)                           │
│                                                             │
│   Executes, forgets, writes for others to see               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## ADMIN Memory Model

ADMIN agents get their own HO stack:

```
planes/admin/
├── ho1/                    # ADMIN execution (what did I do this turn)
│   └── ledger/
│       └── exec.jsonl
├── ho2/                    # ADMIN session (what is this conversation about)
│   └── ledger/
│       └── session-{id}.jsonl
└── ho3/                    # ADMIN learning (patterns across sessions)
    └── ledger/
        └── insights.jsonl
```

### Why ADMIN Needs All Three

| Without HO1 | Each turn is isolated, can't audit what was done |
| Without HO2 | "I don't see a previous prompt" - loses conversation |
| Without HO3 | Can't learn, improve, or recognize patterns |

### But ADMIN is Crosscutting

ADMIN also reads from the tier ledgers:
- Can read `planes/ho1/ledger/` (Resident execution)
- Can read `planes/ho2/ledger/` (Work orders)
- Can read `ledger/` (HO3 governance)

Writes breadcrumbs to observed tier's `observe.jsonl`.

---

## Anti-Drift by Design

### Why Traditional Agents Drift

```
Turn 1: User says "My name is Ray"
        Agent stores in context: {"name": "Ray"}

Turn 50: Context compressed, name becomes "Raymond" or lost

Turn 100: User asks "What's my name?"
          Agent: "I believe you mentioned Brian?" (DRIFT)
```

### Why HO Model Doesn't Drift

```
Turn 1: User says "My name is Ray"
        Agent writes to L-EXEC: {"query": "My name is Ray", "hash": "..."}
        Agent forgets (HO1 stateless)

Turn 50: Context irrelevant (agent reads ledger, not context)

Turn 100: User asks "What's my name?"
          Agent reads L-EXEC Turn 1: "My name is Ray"
          Agent: "According to turn 1, your name is Ray" (NO DRIFT)
```

---

## Session Chaining

Sessions chain through the tiers:

```
Session SES-001:
├── HO1: Turns 1-5 written to L-EXEC
├── HO2: Session state in session-SES-001.jsonl
└── HO3: (available for learning)

Session SES-002:
├── HO1: Turns 1-3 written to L-EXEC
├── HO2: Session state in session-SES-002.jsonl
│         CAN read SES-001 session state if needed
└── HO3: CAN see patterns across SES-001 and SES-002
```

---

## Ledger Types by Tier

| Tier | Ledger | Purpose |
|------|--------|---------|
| HO1 | L-EXEC | Task execution logs |
| HO1 | L-EVIDENCE | Artifact provenance |
| HO2 | L-WORKORDER | Work authorization |
| HO2 | session-{id}.jsonl | Per-session state |
| HO3 | L-INTENT | Framework evolution |
| HO3 | L-PACKAGE | Package lifecycle |
| All | L-OBSERVE | Crosscutting observation |

---

## User Experience Benefits

### Trust
"This agent won't gaslight me about what I said"

### Continuity
"This agent knows my context from the ledger"

### Verifiability
"I can check exactly what the agent read/did"

### Improvement
"The agent gets better because HO3 learns"

### Recovery
"If something breaks, we can replay from ledger"

---

## Summary

| Tier | Memory | Reads | Writes | Drift |
|------|--------|-------|--------|-------|
| HO1 | None | Nothing | L-EXEC | Impossible |
| HO2 | Session | L-EXEC | L-WORKORDER | Controlled |
| HO3 | Learning | All | L-INTENT | Governed |

The key: **Externalize memory, don't trust context, read from ledgers.**
