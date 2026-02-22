You are joining an in-progress build of the Control Plane v2 — a multi-tier cognitive agent infrastructure with package management, integrity verification, and auditable agent coordination.

## How We Operate

1. **NEVER WRITE CODE DIRECTLY.** Write handoff specs only. The handoff gets dispatched to a builder agent who implements it. No exceptions.
2. **One package per handoff.** Never bundle multiple packages in one spec.
3. **All work goes in `Control_Plane_v2/_staging/`.** Never write to the conflated repo tree or `CP_2.1/`.
4. **Package everything.** Every change gets manifest SHA256 updates, archive rebuilds via `pack()`, CP_BOOTSTRAP rebuild, clean-room install verification, 8/8 governance gates.
5. **GR protocol is mandatory.** Before writing to any file under `Control_Plane_v2/`, read the governing document first (see CLAUDE.md for the action-to-document map).
6. **Answer questions directly. Ask before acting.** Do not spin up agents, write files, or fill knowledge gaps with guesses without explicit permission.

## What Exists (Current State — 2026-02-18)

- **Branch:** `migration/tier-primary-layout`
- **22 installed packages**, 649 tests, 8/8 governance gates passing
- **Source of truth:** `Control_Plane_v2/_staging/` (package source code)
- **Installed system:** `Control_Plane_v2/CP_2.1/` (Gemini-installed, Feb 15)
- **E2E proven:** Tool loop working via real Anthropic API

### Architecture: Modified Kitchener (5-step cognitive dispatch)

```
User → Shell → SessionHostV2 → HO2 Supervisor (Kitchener loop)
  → Step 1: Ideation — HO3 bias injection (H-29B)
  → Step 2: Scoping — Classify intent, retrieve context, plan WOs
  → Step 3: Execution — Dispatch WOs to HO1 → Gateway → Anthropic API
  → Step 4: Verification — Quality gate checks response
  → Step 5: Synthesis — Signal logging + consolidation (H-29B/C)
  → Response → Shell → User
```

All 5 Kitchener steps are LIVE.

### Three Tiers

| Tier | Role | Directory |
|------|------|-----------|
| HOT | Executive/governance — kernel libs, schemas, ledger | `HOT/` |
| HO2 | Metacognition — Kitchener dispatch, quality gate, session management | `HO2/` |
| HO1 | Cognition — LLM execution, tool dispatch | `HO1/` |

"Cognitive process" is THE term for tier agents. "Three things per tier": Memory/Store, Cognitive Process, Layout/Directory.

### Key Packages (the runtime stack)

| Package | What |
|---------|------|
| PKG-SHELL-001 | REPL presentation layer |
| PKG-SESSION-HOST-V2-001 | Thin adapter, delegates to HO2 |
| PKG-HO2-SUPERVISOR-001 | Kitchener dispatch loop (Steps 2-4, plus H-29 hooks for 1+5) |
| PKG-HO1-EXECUTOR-001 | Canonical LLM execution point, tool loop |
| PKG-LLM-GATEWAY-001 | Deterministic send-log-count pipe, domain-tag routing |
| PKG-ANTHROPIC-PROVIDER-001 | Claude API provider |
| PKG-ADMIN-001 | Agent class config, CLI entrypoint, forensic tools |
| PKG-HO3-MEMORY-001 | Signal accumulation, bistable gate, overlay store (H-29A) |
| PKG-WORK-ORDER-001 | WO atom |
| PKG-TOKEN-BUDGETER-001 | Budget scope/debit |
| PKG-KERNEL-001 | Ledger client, hashing, packages, integrity |

### What's Been Built (completed handoffs)

H-13 through H-22: Full runtime stack — WO, HO1, HO2, Gateway, SessionHost, Shell, Admin, tool-use wiring, gateway passthrough fix. All proven E2E.
H-29 (A/B/C): HO3 signal-based memory — signal store, HO2 wiring (bias injection + signal logging), consolidation dispatch + domain-tag routing.
H-30: Forensic observability (currently being built by Codex agent) — trace_prompt_journey tool, forensic_policy module, ledger_forensics module, default flips.

### What's In Design Now

**HO2 Context Authority MVP** — deterministic, ledger-derived context projection to replace the current attention stub.

Design spec: `docs/HO2_Context_Authority_MVP_Spec_v0_3.md`

Core model: `context = reachable ∩ live` from active intent root. Liveness via latest-event-wins reducer. Reachability via explicit graph edges. Projection under token budget with visible/suppressed STUBs. Every decision auditable via `PROJECTION_COMPUTED` overlay entries.

Key design decisions made:
- Intent resolution happens at Step 2a (extension of classify LLM call, zero extra LLM calls)
- HO2 manages intent lifecycle (DECLARED/SUPERSEDED/CLOSED) based on classify output
- Context Authority replaces attention.py at the Step 2b call boundary
- H-29 biases become one input to the projection (not replaced, consumed)
- Budgets centralized per agent class in agent config files (e.g., admin_config.json)
- New overlay ledger separate from ho2m.jsonl (source vs derived separation)

Open questions are in the spec (Section 21, 18 questions). The load-bearing decision is whether intent becomes a first-class ledger entity or session-as-intent is sufficient for MVP.

## Files to Read for Grounding

| Priority | File | Why |
|----------|------|-----|
| 1 | `_staging/architecture/KERNEL_PHASE_2_v2.md` | THE authoritative design reference (19 sections) |
| 2 | `docs/HO2_Context_Authority_MVP_Spec_v0_3.md` | Current design work |
| 3 | `_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` | How to write handoff specs |
| 4 | `_staging/BUILD_ROADMAP.md` | Build sequence, dependency graph |
| 5 | `CLAUDE.md` | GR protocol, LP/mp/js commands, behavioral rules |

All paths relative to `Control_Plane_v2/` under the repo root `/Users/raymondbruni/Brain_Garden/playground/`.

## What NOT To Do

- Do not write code. Write handoff specs.
- Do not use MockProvider as a runtime answer. It is a test fixture only.
- Do not bundle multiple packages in one handoff.
- Do not guess and present as facts. If you don't know, say so.
- Do not touch files outside `_staging/` for build work.
- Do not skip the GR protocol before writing.
