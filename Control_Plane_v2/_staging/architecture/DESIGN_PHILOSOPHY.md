# Design Philosophy — Control Plane v2

**Status**: DRAFT — for review and comment
**Created**: 2026-02-16
**Purpose**: Define the principles that govern how the system is designed, how capabilities are built, and how the system holds together. This document answers "how should you think?" — the architecture doc answers "what are you building?"

---

## 1. This Is an Operating System

Control Plane v2 is a cognitive operating system for AI agents. Like any OS, it needs a way to define capabilities, describe how to build them, and deliver them as governed, installable artifacts.

The system has four core concepts that form a hierarchy:

```
Operating System (Control Plane v2)
│
├── Framework (FMWK-NNN)
│   │  "What capability does the OS need, and what are the rules?"
│   │  - Governance rules, boundaries, contracts
│   │  - Could be anything: agile dev interface, memory system, playlist converter
│   │
│   ├── Spec Pack (SPEC-NNN)
│   │   │  "What services are needed to deliver this capability?"
│   │   │  - Microservice descriptions (contracts, interfaces, responsibilities)
│   │   │  - The architecture an agent reads to know what to build
│   │   │
│   │   ├── Prompt Pack (PRM-NNN)
│   │   │     "How does the LLM think within this service?"
│   │   │     - Templates, contracts, structured prompts
│   │   │
│   │   ├── Modules
│   │   │     "The actual code that executes"
│   │   │     - Python scripts, classes, functions
│   │   │
│   │   └── Sub-Packs
│   │         "Nested components if the service is complex"
│   │         - Could contain their own prompt packs, modules
│   │
│   └── ... more Spec Packs under the same framework
│
├── Package (PKG-NNN)
│     "The delivery container — ships any of the above"
│     - manifest.json declares: I implement SPEC-NNN under FMWK-NNN
│     - Contains the built artifacts (code, prompts, configs)
│     - Like NPM/RPM — it's the envelope, not the content
│
└── ... more Frameworks, each with their own Spec Packs
```

### The Generative Chain

- **Framework** tells you WHY and WHAT RULES
- **Spec Pack** tells you WHAT TO BUILD and HOW IT FITS TOGETHER
- **Prompt Packs** tell the LLM HOW TO THINK
- **Modules** are the CODE
- **Packages** DELIVER all of it

**Framework + Spec Pack = sufficient specification for an agent to build.** If an LLM agent receives a framework and its spec pack, it should be able to write the modules, write the prompts, wire the governance, and deliver working packages. The agent doesn't need to understand the whole OS — it needs the framework (why, rules) and the spec pack (what, how).

---

## 2. Frameworks Define Capabilities

A framework is a capability definition for the operating system. It answers: "what does the system need to be able to do, and what are the rules for doing it?"

A framework could be anything:
- A full development framework that defines how a resident agent creates an agile interface for application development
- A new memory system for resident agents to use
- A way to store and convert song playlists
- A governance protocol for work order dispatch

### What a Framework Contains

| Component | What It Does |
|-----------|-------------|
| Governance rules | What the capability CAN do, MUST do, and MUST NOT do |
| Boundaries | Where the capability operates (which tiers, which agents, which resources) |
| Contracts | The interfaces between this capability and the rest of the system |
| Spec Packs | The service architecture that implements the capability (see Section 3) |

### What a Framework Does NOT Contain

- Code. Frameworks describe capabilities, not implementations.
- Hardcoded thresholds. Every threshold, timeout, retry count = config-driven.
- Assumptions about which agent builds it. Frameworks are agent-independent.

---

## 3. Spec Packs Describe Services

A spec pack is the microservice architecture for a framework's capability. It breaks down what the framework needs into concrete services that an agent can build.

Spec packs belong to frameworks. A spec pack without a framework is an implementation plan with no governance. A framework without spec packs is governance rules with no implementation plan. They are two halves of one thing.

### What a Spec Pack Describes

| Component | What It Does |
|-----------|-------------|
| Service descriptions | The microservices needed — their contracts, interfaces, responsibilities |
| Prompt Packs (PRM-NNN) | How the LLM agents think within each service — templates, structured prompts |
| Module definitions | What code needs to be written — scripts, classes, functions |
| Sub-packs | Nested components for complex services — each with their own prompt packs and modules |

### The Microservice Philosophy

Each service described by a spec pack follows microservice principles:

| Principle | What It Means |
|-----------|---------------|
| Single responsibility | One service, one concern |
| Explicit interfaces | A service exports specific functions/classes. Everything else is internal. |
| Own your data | A service owns its files and state. No other service writes to them. |
| Declare your dependencies | Dependencies are explicit. If you import from another service, declare it. |
| Independently testable | Every service passes its own tests in isolation |
| Contract-first | Define the API contract before implementation |

### Spec Packs Are the Governance Bridge

The governance system validates the chain: Package → Spec → Framework. But validating that the chain EXISTS (the names reference each other) is not the same as validating that the chain is TRUE (the code actually implements what the spec describes).

**Current state (names only):** G1 checks that a package's `spec_id` exists in `specs_registry.csv` and that the spec's `framework_id` exists in `frameworks_registry.csv`. This is reference validation — the table of contents lists Chapter 3.

**Target state (names + meaning):** The governance system should also verify that Chapter 3 covers what it says it covers. A spec pack declares "this service exposes functions X, Y, Z with these contracts." The gate should verify that the installed code actually exports those functions with matching signatures. A framework declares "all services must log to the ledger." The gate should verify that the installed code actually calls the ledger.

This is the difference between governance-as-paperwork and governance-as-enforcement. The system should be able to detect when a builder delivers a package that claims to implement a spec but doesn't.

---

## 4. Packages Are Delivery Containers

A package is the unit of deployment, ownership, and accountability. It is NOT the service itself — it is the envelope that delivers the service. Think NPM, RPM, or apt packages.

A package can contain anything from a single utility module to a full application. What makes it a package is not its size or complexity but its governance:

| Property | What It Means |
|----------|---------------|
| manifest.json | Declares package ID, version, spec_id, framework_id, dependencies, assets with SHA256 hashes |
| Ownership | Every file in the package is tracked in file_ownership.csv. No other package may claim those files. |
| Dependencies | Explicit list of other packages this one requires. Enforced at install time by topo-sort. |
| Gates | Must pass G0A (declaration), G0B (integrity), G1 (chain), G1-COMPLETE (frameworks) at install time |
| Ledger | Installation is recorded as an append-only ledger entry |

### Package Design Principles

- **Don't reach into another package's internals.** Import the public interface, not implementation details.
- **Don't create god packages.** If a package does three unrelated things, it should be three packages.
- **Test in isolation first, then in integration.** Package-local tests validate your contract. Full regression validates you didn't break anyone else's.
- **Dependencies flow downward.** See Section 5.

---

## 5. Three Classification Axes

Every component in the system can be described along three orthogonal axes: WHERE it executes, WHO it serves, and WHAT capability it belongs to.

### Axis 1: Tiers (WHERE)

The system has three execution tiers. Dependencies flow downward — never up, never circular.

```
HOT (Level 3 — Strategist)
│   Kernel infrastructure, governance, policy
│   Everything installed here. Frameworks live here.
│
├── HO2 (Level 2 — Critic)
│     Session state, dispatch, attention, verification
│     Depends on HOT. Never imported by HOT.
│
└── HO1 (Level 1 — Worker)
      Execution, LLM calls, tool loops, traces
      Depends on HOT. Never imported by HOT or HO2.
```

**HOT never imports from HO2 or HO1.** HO1 never imports from HO2. Lower tiers call higher tier services through syscalls (e.g., HO1 calls the LLM Gateway in HOT), but they cannot read higher tier state directly. This is what makes packages independently deployable and testable.

### Axis 2: Kernel Classification (WHO it serves)

| Classification | What | Nature |
|----------------|------|--------|
| **KERNEL.syntactic** | Deterministic infrastructure — gates, hashing, integrity, auth, LLM Gateway, ledger, pristine enforcement | Code that enforces invariants. Binary outcomes. No LLM. HOT only. |
| **KERNEL.semantic** | LLM-backed infrastructure — meta agent, cross-cutting learning, pattern detection | Infrastructure that serves the system, not users. HOT-primary, reads across tiers. |
| **Non-kernel** | User/admin-facing capabilities — ADMIN agent, RESIDENT agents | Frameworks defined in HOT, cognitive processes execute across HO1+HO2. |

The kernel/non-kernel distinction answers: "does this serve the system itself, or does it serve users?" Syntactic/semantic answers: "is this deterministic or does it need an LLM?"

### Axis 3: Framework Hierarchy (WHAT capability)

This is the hierarchy from Section 1: Framework → Spec Pack → Prompt Pack / Module → Package.

### How the Axes Intersect

A concrete example: the LLM Gateway.
- **WHERE**: HOT (it's kernel infrastructure)
- **WHO**: KERNEL.syntactic (deterministic pipe, no LLM judgment)
- **WHAT**: Framework FMWK-005, Spec SPEC-LLM-GATEWAY, delivered by PKG-LLM-GATEWAY-001

Another: the HO2 Supervisor.
- **WHERE**: Code in HO2/, uses HOT kernel
- **WHO**: Non-kernel (serves user-facing agent workflows)
- **WHAT**: Framework FMWK-010, Spec SPEC-HO2-SUPERVISOR, delivered by PKG-HO2-SUPERVISOR-001

The three axes are independent. Knowing the tier doesn't tell you the kernel classification. Knowing the framework doesn't tell you the tier. You need all three to fully locate a component.

---

## 6. The Governance Loop

Governance is not a layer on top of the system. It IS the system. The gates, ledgers, ownership tracking, and framework chains are the mechanisms that make the system trustworthy.

### Three Layers of Governance

The governance system operates at three levels that compose from bottom to top:

```
┌─────────────────────────────────────────────────────────────┐
│                     LAYER 3: UBER CHECK                     │
│           gate_check.py --all --enforce                     │
│           "Is the WHOLE SYSTEM consistent?"                 │
│                                                             │
│  Runs AFTER all packages are installed.                     │
│  Validates the final state holistically:                    │
│    G0B  — every governed file owned, hashes match           │
│    G1   — every chain intact across ALL packages            │
│    G1-C — every framework fully wired                       │
│    G2   — work order system health                          │
│    G3   — constraint system health                          │
│    G4   — acceptance test infrastructure                    │
│    G5   — signature/attestation status                      │
│    G6   — ledger chain integrity across all tiers           │
│                                                             │
│  If ANY gate fails with --enforce, the system is invalid.   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    LAYER 2: PER-PACKAGE                      │
│           package_install.py (17-step governed install)      │
│           "Is THIS PACKAGE safe to add?"                    │
│                                                             │
│  For each package, before it touches the filesystem:        │
│    G0B  — existing system integrity (pre-install re-hash)   │
│    G0A  — package self-consistency (declared = actual)       │
│    G1   — chain valid (package → spec → framework)          │
│    G1-C — framework completeness (state-gated)              │
│    G5   — signature + attestation                           │
│    OWN  — no ownership conflicts (no last-write-wins)       │
│                                                             │
│  After copy, before commit:                                 │
│    POST — re-hash every installed file against manifest     │
│    On fail: rollback from backup                            │
│                                                             │
│  Commit phase (all-or-nothing):                             │
│    15. Ledger entry (INSTALLED) — written FIRST             │
│    16. file_ownership.csv — append ownership rows           │
│    17. Receipt — written LAST (proves commit completed)     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    LAYER 1: BOOTSTRAP AXIOMS                 │
│           genesis_bootstrap.py                               │
│           "Bootstrap the governance infrastructure"          │
│                                                             │
│  PKG-GENESIS-000: Extracted raw. No gates exist yet.        │
│    Creates: kernel code, scripts, seed_registry              │
│    This is the trusted root — the one unverified package.   │
│                                                             │
│  PKG-KERNEL-001: Installed by genesis_bootstrap.py          │
│    Creates: package_install.py, gate_check.py, ledger,      │
│             hashing, pristine enforcement, file ownership    │
│    After this: full governance infrastructure exists.        │
│                                                             │
│  Every subsequent package installs through Layer 2.         │
└─────────────────────────────────────────────────────────────┘
```

Layer 1 solves the bootstrap paradox: governance can't govern its own creation, so two trusted packages bootstrap the infrastructure, then everything else is governed.

Layer 2 ensures each addition is safe. Layer 3 ensures the complete system is coherent. They compose because per-package checks validate LOCAL consistency and the uber check validates GLOBAL consistency.

### State-Gating

Some gates pass trivially when their dependencies don't exist yet. G1-COMPLETE passes trivially before the FrameworkCompletenessValidator is installed. The first package's G0B passes trivially because no receipts exist yet. This is deliberate — it allows the system to bootstrap incrementally. The uber check (Layer 3) catches anything that was state-gated during incremental install.

### What the Governance Loop Validates Today

| Gate | Validates | Level |
|------|-----------|-------|
| G0A | Package is internally self-consistent (declared assets match actual files, hashes match, no path escapes) | Filesystem |
| G0B | Every governed file is owned by exactly one package, hashes match ownership records, no orphans | Filesystem |
| G1 | Package → Spec → Framework chain exists (references resolve) | Framework (names) |
| G1-COMPLETE | Framework's expected specs exist and reference back (bidirectional) | Framework (structure) |
| G5 | Package archive has valid signature and attestation | Integrity |
| G6 | Ledger entries are well-formed and chain is intact | Audit |

### What the Governance Loop Must Also Validate (target)

| Gap | What's Missing | Why It Matters |
|-----|----------------|----------------|
| **Spec content validation** | A spec pack declares "this service exports X, Y, Z." Nothing verifies the installed code actually exports X, Y, Z. | A package can claim to implement a spec without actually implementing it. |
| **Framework rule enforcement** | A framework declares "all services must log to the ledger." Nothing verifies the installed code calls the ledger. | Frameworks are governance rules that aren't enforced at install time. |
| **Contract conformance** | A spec declares input/output schemas. Nothing verifies the code's actual function signatures match. | The spec is the architecture, but the code can diverge silently. |
| **Behavioral smoke test** | Gates verify structure (hashes, ownership, chains). Nothing verifies the system actually responds to a user prompt. Every integration bug that has shipped passed all 8 gates and all unit tests — and was caught by typing "hello." | A system can be structurally perfect and behaviorally broken. |

When these gaps are closed, G1 validates MEANING, not just NAMES. The chain isn't just "this package references this spec" — it's "this package delivers what this spec describes." And a behavioral gate ensures the system actually works, not just that it's internally consistent. This is core to how the system is supposed to work.

### Append-Only Is Intentional

The ledger is append-only. Files governed by pristine enforcement cannot be replaced. This is a design choice:

- **Provenance is preserved.** Every state the system has been in is recoverable.
- **Auditability is automatic.** The append-only ledger IS the audit trail.
- **Conflicts are surfaced, not hidden.** File replacement hides history. State-gating preserves it.
- **Trust is verifiable.** A chain of ledger entries from genesis to now can be independently verified.

Never overwrite another package's files. Never delete ledger entries. If something is wrong, append a correction that references the original.

### Built-In Tools Are Not Optional

The kernel provides specific tools for specific operations. These exist because the naive approach fails:

| Operation | Wrong Way | Right Way | Why |
|-----------|-----------|-----------|-----|
| Hash a file | `hashlib.sha256()` | `hashing.py:compute_sha256()` | Produces `sha256:<64hex>` (71 chars). Bare hex fails G0A. |
| Build an archive | `tar czf ...` | `packages.py:pack()` | Deterministic: mtime=0, uid=0, sorted entries, PAX format. Shell tar is non-deterministic. |
| Install a package | Copy files manually | `install.sh` → `package_install.py` | 17-step governed install with gates, ledger, ownership, receipts. |
| Verify the system | Spot-check a few files | `gate_check.py --all --enforce` | 8 gates covering ownership, chains, frameworks, constraints, signatures, ledger. |
| Resolve install order | Hardcode a list | `resolve_install_order.py` | Auto-discovers packages and topo-sorts by dependency. Lists go stale. Discovery doesn't. |

**If a kernel tool exists for an operation, use it. If you're about to write code that does what a kernel tool already does, stop.**

---

## 7. Agents Build Under the Same Governance They Build

A builder agent is not exempt from the system's rules. The same principles that govern runtime agents govern build-time agents:

| Runtime Principle | Build-Time Equivalent |
|-------------------|-----------------------|
| Every agent operates under a work order | Every builder operates under a handoff spec |
| Work orders are scoped and budgeted | Handoff specs define scope, files, and verification criteria |
| Results are verified by HO2 (the Critic) | Results are verified by the reviewer against the checklist |
| All actions are logged to the ledger | All results are recorded in RESULTS files with SHA256 hashes |
| The 10Q gate checks understanding before execution | The 10Q gate checks builder understanding before implementation |

- **Read the spec before building.** The handoff spec is your work order. Don't improvise.
- **DTT is non-negotiable.** Design → Test → Then implement. Tests are the acceptance criteria.
- **Verify from the installed root, not from staging.** Staging paths and installed paths differ.
- **Clean-room install is the ground truth.** If it doesn't install from CP_BOOTSTRAP.tar.gz, it doesn't work.

---

## 8. The Build Lifecycle

This is the complete sequence a builder agent follows, from receiving a handoff to delivering results. Every step is mandatory.

### The Core Discipline: Red-Green-Refactor

Before anything else, builders must internalize the TDD cycle. This is not a suggestion — it is the method.

```
┌─────────┐     ┌─────────┐     ┌───────────┐
│   RED   │────▶│  GREEN  │────▶│ REFACTOR  │──┐
│         │     │         │     │           │  │
│ Write a │     │ Write   │     │ Clean up. │  │
│ failing │     │ minimum │     │ Tests     │  │
│ test.   │     │ code to │     │ must stay │  │
│         │     │ pass it.│     │ green.    │  │
└─────────┘     └─────────┘     └───────────┘  │
     ▲                                          │
     └──────────────────────────────────────────┘
                  Next behavior
```

**Red:** Write a test for one behavior. Run it. It must FAIL. If it passes without implementation, the test is vacuous — delete it and write a real one.

**Green:** Write the minimum code to make the test pass. Not elegant code. Not complete code. Just enough to go green. Resist the urge to implement the next behavior.

**Refactor:** Now clean up. Extract helpers, remove duplication, tighten interfaces. Run the tests after every change — if anything goes red, you broke something. Fix it before moving on.

**Repeat:** Pick the next behavior. Write a failing test. Go green. Refactor. Continue until all behaviors are covered.

Builders work in **per-behavior cycles**, not all-tests-then-all-code. Each cycle produces one tested, clean behavior. The full feature emerges from the accumulation of cycles.

### The Mock Boundary

Mocks are permitted ONLY during the red-green-refactor cycle — when you are building one behavior at a time and need to isolate your unit under test. Once the behavior is green:

**Mocks stop. Real components start.**

| Test Level | Mocks Allowed? | What It Proves |
|------------|---------------|----------------|
| **Unit test** (red-green-refactor) | Yes — mock the layer below | This function does what its contract says |
| **Integration test** (per-package) | No — wire real components | This package works with its real dependencies |
| **E2E smoke test** (full system) | No — real Kitchener loop | The system responds to a user prompt |

Every package that touches the dispatch path (HO2, HO1, Gateway, Provider, Admin) MUST include at least one integration test that wires real components from the layer below. MockProvider is a red-green fixture, not an integration answer.

**The pattern that keeps shipping bugs:** HO2 tests mock HO1. HO1 tests mock Gateway. Gateway tests mock Provider. Every mock returns what the developer expects, not what the real system produces. All 487 tests pass. The user types "hello" and gets an error. This pattern is not allowed.

### The Staging Constraint

All building happens in `_staging/`. Every file edit, every test run during development, every package source — it lives in `_staging/` and only reaches the installed root through `install.sh`. Builders never create or modify files outside `_staging/`.

### Phase 1: Understand

| Step | Action | Produces |
|------|--------|----------|
| 1 | Read the handoff spec | Understanding of scope, constraints, architecture |
| 2 | Read referenced code (Section 7 of spec) | Understanding of existing patterns |
| 3 | Read the architecture doc (KERNEL_PHASE_2_v2.md) | Understanding of where this fits in the system |
| 4 | Answer the 10-question gate | Proof of understanding |
| 5 | **STOP. Wait for approval.** | — |

### Phase 2: Build (Red-Green-Refactor)

For each behavior in the spec:

| Step | Action | Produces |
|------|--------|----------|
| 6 | **RED:** Write test(s) for one behavior | Failing test(s) that define the contract |
| 7 | Run tests — they must FAIL | Proof the test is real, not vacuous |
| 8 | **GREEN:** Write minimum code to pass | Implementation of that behavior |
| 9 | Run tests — they must PASS | Confidence in the implementation |
| 10 | **REFACTOR:** Clean up code, tests stay green | Tighter, cleaner implementation |
| 11 | Repeat steps 6-10 for the next behavior | — |

### Phase 3: Govern

| Step | Action | Tool |
|------|--------|------|
| 12 | Compute SHA256 hashes for all modified files | `hashing.py:compute_sha256()` |
| 13 | Update manifest.json with new hashes | Manual edit (hashes from step 12) |
| 14 | Rebuild package archive | `packages.py:pack()` |
| 15 | Rebuild CP_BOOTSTRAP (if package is in bootstrap scope) | `packages.py:pack()` |

### Phase 4: Verify

| Step | Action | Tool |
|------|--------|------|
| 16 | Clean-room install from CP_BOOTSTRAP | `install.sh --root <tmpdir> --dev` |
| 17 | Run gate checks | `gate_check.py --all --enforce` → 8/8 PASS |
| 18 | Run full regression from installed root | `pytest` with correct PYTHONPATH |
| 19 | **E2E smoke test — MANDATORY** | Send a real prompt through the Kitchener loop, verify a real response |

**Step 19 is not optional.** If the handoff touches any package in the dispatch path (HO2, HO1, Gateway, Provider, Shell, Admin), a real prompt must enter the system and a real response must come back. "All tests pass" and "all gates pass" is necessary but NOT sufficient. The system must actually work.

### Phase 5: Report

| Step | Action | Produces |
|------|--------|----------|
| 20 | Write RESULTS file following the full template | RESULTS_HANDOFF_N.md |
| 21 | **STOP. Report completion.** | — |

### What "Done" Means

A package is done when ALL of the following are true:
1. Every behavior was built through red-green-refactor cycles
2. Integration tests use real components (not mocks) for cross-package boundaries
3. Tests pass in isolation AND in full regression (0 new failures)
4. Gates pass (8/8 from `gate_check.py --all --enforce`)
5. Clean-room install succeeds (from CP_BOOTSTRAP for bootstrap-scope packages, or via `package_install.py` for post-bootstrap packages)
6. E2E smoke test passes — a real prompt enters the system, a real response comes back
7. Manifests are current (SHA256 hashes match actual files)
8. Archives are built with `pack()` (deterministic, reproducible)
9. Framework chain is valid (G1 + G1-COMPLETE pass)
10. RESULTS file is complete (all required sections, baseline snapshot)
11. All work was done in `_staging/` — no files created or modified outside it

If any of these are missing, the package is not done. It doesn't matter how good the code is.

---

## 9. The Bootstrap Contract

### What the Bootstrap Is

CP_BOOTSTRAP is the OS installer. It installs the operating system — kernel, governance, infrastructure, and the ADMIN agent. After bootstrap, the OS is running and can manage itself.

Any agent or human should be able to install the system by:

1. Extracting the archive to a directory
2. Running `./install.sh --root <target> --dev`

That's it. No guidance needed. No external documentation. No manual steps.

### Bootstrap Scope

The bootstrap contains everything needed to bring the OS up. Nothing more.

```
CP_BOOTSTRAP scope:
│
├── Layer 0: Bootstrap Axioms
│   PKG-GENESIS-000        — seed (trusted root)
│   PKG-KERNEL-001         — governed installer, gates, ledger, hashing
│
├── Layer 1: Governance Infrastructure
│   PKG-REG-001            — registries
│   PKG-VOCABULARY-001     — gate_check.py, resolve_install_order.py
│   PKG-GOVERNANCE-UPGRADE-001
│   PKG-FRAMEWORK-WIRING-001
│   PKG-SPEC-CONFORMANCE-001
│   PKG-LAYOUT-001, PKG-LAYOUT-002
│   PKG-PHASE2-SCHEMAS-001
│
├── Layer 2: Cognitive Infrastructure (KERNEL.syntactic)
│   PKG-TOKEN-BUDGETER-001 — budget enforcement
│   PKG-WORK-ORDER-001     — the WO atom
│   PKG-LLM-GATEWAY-001    — deterministic LLM pipe
│   PKG-ANTHROPIC-PROVIDER-001 — LLM provider
│   PKG-BOOT-MATERIALIZE-001  — directory materialization
│
├── Layer 3: Cognitive Processes
│   PKG-HO1-EXECUTOR-001   — worker (LLM execution + tool loops)
│   PKG-HO2-SUPERVISOR-001 — critic (Kitchener dispatch)
│   PKG-SESSION-HOST-V2-001 — session adapter
│   PKG-SHELL-001          — REPL presentation
│
├── Layer 4: ADMIN Agent
│   PKG-ADMIN-001          — system keeper entrypoint
│
└── Layer 5: Verification
    PKG-VERIFY-001         — verification harness
```

**After bootstrap, the OS is up.** ADMIN can query, inspect, and manage the system. Builders can create frameworks, write spec packs, and deliver packages through the running system's own `package_install.py`.

**RESIDENT agents install AFTER bootstrap.** They are capabilities that run ON the OS, not part of the OS itself. A resident agent's framework, spec packs, and packages install through governed work orders — the same way any new capability is added to a running OS. The bootstrap is NOT rebuilt for every new resident.

### What the Bootstrap Contains

- `install.sh` — the orchestrator (handles genesis, kernel, then delegates to governed tools)
- `BOOTSTRAP_MANIFEST.json` — version, date, package list, changelog
- `packages/` — all package archives, each with manifest.json and governed assets

### Versioning

The bootstrap is versioned with semantic versioning: **MAJOR.MINOR.PATCH**.

| Bump | When |
|------|------|
| **MAJOR** | Breaking changes — layout restructure, removed packages, gate changes |
| **MINOR** | New packages or capabilities added (e.g., new handoff integrated) |
| **PATCH** | Bugfixes, test cleanup, governance-only changes |

Version bumps are **manual** — not every rebuild is a meaningful release. The version is tracked in `BOOTSTRAP_MANIFEST.json` inside the archive:

```json
{
  "version": "2.1.0",
  "created": "2026-02-16T00:00:00Z",
  "package_count": 21,
  "packages": [
    {"id": "PKG-GENESIS-000", "version": "1.0.0"},
    {"id": "PKG-KERNEL-001", "version": "1.2.0"}
  ],
  "changelog": [
    "2.1.0 — HANDOFF-21: Tool-use wiring (487 tests, 8/8 gates)",
    "2.0.0 — Initial bootstrap (468 tests, 8/8 gates)"
  ]
}
```

`install.sh` prints the version at the start of every install. The filename includes the version: `CP_BOOTSTRAP-2.1.0.tar.gz`. Git tags anchor each release: `bootstrap-v2.1.0`.

### How the Bootstrap Sequence Works

1. **Extract genesis** (PKG-GENESIS-000) — raw tar, no governance. Creates the seed.
2. **Install kernel** (PKG-KERNEL-001) — via `genesis_bootstrap.py`. Creates the governed installer, gate checker, and all kernel tools.
3. **Resolve install order** — the kernel's `resolve_install_order.py` reads all remaining package manifests, builds a dependency graph, and topologically sorts them.
4. **Install packages** — each remaining package goes through the 17-step governed install via `package_install.py`.
5. **Run uber check** — `gate_check.py --all` validates the entire installed system (8 gates).

Every tool used after Step 2 is a governed kernel tool — owned by a package, tracked in file_ownership.csv, hash-verified. The bootstrap contains NO loose utilities outside the package system.

### The Test

If you hand the bootstrap to an agent that has never seen the system before, and that agent can install it and get 8/8 gates PASS by reading only what's inside the archive — the bootstrap contract is met.

---

## 10. Common Traps

These are patterns that look reasonable but violate the philosophy:

| Trap | Why It's Wrong | Correct Approach |
|------|---------------|------------------|
| "All tests pass, so it works" | Every integration bug that shipped passed all tests. Mocks return what you expect, not what the system produces. | Run E2E: send a real prompt, get a real response. |
| "I'll use MockProvider for integration tests" | MockProvider is a red-green fixture. It hides every real API behavior: content format, tool_use responses, error shapes. | Mock only during unit red-green cycles. Integration tests use real (or realistic) components. |
| "I'll add framework alignment later" | A package without a framework is ungoverned. | Declare framework in manifest.json from the start. |
| "I'll test from staging, it's faster" | Staging paths differ from installed paths. | Always verify from installed root. |
| "I'll build outside _staging/" | Files outside _staging/ bypass the package system entirely. | All building happens in `_staging/`. Only `install.sh` moves files to the installed root. |
| "I'll compute the hash myself" | Manual hashes produce bare hex. | Use `compute_sha256()`. |
| "I'll install by copying files" | Bypasses gates, ledger, and ownership tracking. | Use `install.sh`. |
| "My package needs to read HO3 state directly" | Lower tiers cannot read higher tier state. | Use syscalls (call HOT services). |
| "I'll put three features in one package" | Violates single responsibility. | Split into three packages. |
| "The governance chain passes so the code is correct" | G1 validates NAMES, not MEANING. | Until content validation exists, spec conformance is manual. |
| "I don't need a spec pack, I'll just write code" | Code without a spec is unarchitected. No agent can reproduce or extend it. | Write the spec pack first. |
| "I'll put this utility outside the package system" | Ungoverned code can't be verified or owned. | Everything installs through the package system. |
