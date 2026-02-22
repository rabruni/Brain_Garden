# Builder Handoff Standard

## Purpose

This document defines the standard format for all builder handoff documents in the Control Plane v2 project. Every handoff — whether a new component, a follow-up fix, or an upgrade — must follow this template.

---

## File Organization

Each handoff gets its own directory under `_reboot/_staging/handoffs/`:

```
_reboot/_staging/handoffs/<handoff_id>/
├── <handoff_id>_BUILDER_HANDOFF.md    ← the spec
├── <handoff_id>_RESULTS.md            ← the results (written by builder)
└── <handoff_id>_AGENT_PROMPT.md       ← the dispatched prompt (optional, for audit)
```

**Handoff ID patterns:**

| Type | ID Pattern | Example Directory |
|------|------------|-------------------|
| New component | `H-<N>` | `_reboot/_staging/handoffs/H-32/` |
| Follow-up | `H-<N><letter>` | `_reboot/_staging/handoffs/H-32A/` |
| Cleanup | `CLEANUP-<N>` | `_reboot/_staging/handoffs/CLEANUP-5/` |

Numbering follows the build sequence. Letters (A, B, C...) are follow-ups to a numbered handoff.

**Migration note:** Existing flat handoff files in `_reboot/_staging/handoffs/` will be migrated into this per-handoff directory structure.

---

## Required Sections

Every handoff document MUST contain these sections in order:

### 1. Mission
One paragraph: what the agent is building and why. Include the package ID(s).

### 2. Critical Constraints
Numbered list. Always includes these non-negotiable rules:

1. **ALL work goes in `Control_Plane_v2/_reboot/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Per-behavior TDD cycles: write a failing test for one behavior, write minimum code to pass, refactor, repeat. NOT all-tests-then-all-code.
3. **Package everything.** New code ships as packages in `_reboot/_staging/PKG-<NAME>/` with manifest.json, SHA256 hashes, proper dependencies. Manifests MUST use `"assets"` array (not `"files"` dict), `"dependencies"` (not `"depends_on"`), and include `schema_version`, `spec_id`, `framework_id`.
4. **End-to-end verification.** After building, run the full test suite. All tests must pass.
5. **No hardcoding.** Every threshold, timeout, retry count, rate limit — all config-driven. This is the #1 lesson from 7 layers of prior art.
6. **No file replacement.** Packages must NEVER overwrite another package's files. Use state-gating instead.
7. **Archive creation.** Use deterministic archive creation for ALL archives. NEVER use shell `tar` — it produces non-deterministic metadata (mtime, uid vary between builds).
8. **Results file.** When finished, write `_reboot/_staging/handoffs/<handoff_id>/<handoff_id>_RESULTS.md`. See Results File section below.
9. **Full regression test.** Run ALL staged package tests (not just yours) and report results. New failures you introduced are blockers. Pre-existing failures from unvalidated packages are noted but not blockers.
10. **Baseline snapshot.** Your results file must include a baseline snapshot (package count, total tests) so the next agent can diff against it.

Add task-specific constraints as needed.

### 3. Architecture / Design
Explain WHAT to build. Diagrams, data flows, component relationships. Be explicit about interfaces and boundaries.

### 4. Implementation Steps
Numbered, ordered steps. Include file paths, function signatures, and enough detail that the agent can execute without interpretation.

### 5. Package Plan
For each package:
- Package ID, layer, spec_id, framework_id, plane_id
- Assets list with paths and classifications
- Dependencies (other package IDs)
- Framework manifest (if the package introduces one)

### 6. Test Plan
List every test method with:
- Name
- One-line description of what it validates
- Expected behavior

Minimum test counts:
- Small packages (1-2 source files): 10+ tests
- Medium packages (3-5 source files): 25+ tests
- Large packages (6+ source files): 40+ tests

### 7. Existing Code to Reference
Table of files the agent should read before building. Format:

| What | Where | Why |
|------|-------|-----|
| Example | `_reboot/_staging/PKG-<NAME>/path/to/file.py` | Pattern to follow |

### 8. End-to-End Verification
Exact commands for clean-room verification. Copy-pasteable. Include expected output.

### 9. Files Summary
Table of every file created or modified:

| File | Location | Action |
|------|----------|--------|
| `name.py` | `_reboot/_staging/PKG-NAME/HOT/kernel/` | CREATE |

### 10. Design Principles
Non-negotiable design rules for this specific component. Usually 4-6 bullet points.

---

## Results File

**Every handoff agent MUST write a results file when finished.**

**File:** `Control_Plane_v2/_reboot/_staging/handoffs/<handoff_id>/<handoff_id>_RESULTS.md`

Example: `_reboot/_staging/handoffs/H-32/H-32_RESULTS.md`

**Required content:**

```markdown
# Results: <Handoff Title>

## Status: PASS | FAIL | PARTIAL

## Files Created
- path/to/file1.py (SHA256: abc123...)
- path/to/file2.json (SHA256: def456...)

## Files Modified
- path/to/existing.py (SHA256 before: xxx, after: yyy)

## Archives Built
- PKG-NAME-001.tar.gz (SHA256: ghi789...)

## Test Results — THIS PACKAGE
- Total: N tests
- Passed: N
- Failed: N
- Skipped: N
- Command: `python3 -m pytest <path> -v`

## Full Regression Test — ALL STAGED PACKAGES
- Total: N tests
- Passed: N
- Failed: N
- Skipped: N
- Command: `CONTROL_PLANE_ROOT="$TMPDIR" python3 -m pytest Control_Plane_v2/_reboot/_staging/ -v --ignore=<any unvalidated packages>`
- New failures introduced by this agent: [list or NONE]

## Baseline Snapshot (AFTER this agent's work)
- Packages installed: N
- Total tests (all staged): N

## Clean-Room Verification
- Packages installed: N
- Install order: PKG-A → PKG-B → PKG-C
- All tests pass after each install: YES/NO
- Full command log: [paste or reference]

## Issues Encountered
- [Any problems, workarounds, or deviations from the handoff spec]
- [Pre-existing failures and why they're not regressions]

## Notes for Reviewer
- [Anything the reviewer should pay attention to]
- [Design decisions made that weren't in the spec]
```

**Why:** The results file lets the reviewer validate the agent's work by reading one file instead of re-running everything. SHA256 hashes enable spot-checking without extraction. Test counts confirm coverage. Gate results confirm governance. The baseline snapshot captures system state so the NEXT agent's reviewer can diff against it.

### Full Regression Test (MANDATORY)

Every agent MUST run the full staged test suite after completing their work — not just their own package's tests. This catches cross-package regressions.

```bash
CONTROL_PLANE_ROOT="$TMPDIR" python3 -m pytest Control_Plane_v2/_reboot/_staging/ -v \
    --ignore=<any packages known to be unvalidated>
```

Report: total tests, pass/fail counts, and explicitly state whether any NEW failures were introduced. Pre-existing failures (from unvalidated packages) should be noted but are not blockers.

### Execution Shortcuts (Recommended)

Use these patterns to reduce avoidable failures and speed up validation:

- Use two-stage testing: package-local tests first for fast confidence, then mandatory full staged regression.
- Always run the exact mandatory full staged command and report blockers separately if collection is polluted by temporary rebuild trees.
- Avoid quoted heredoc mistakes in shell-to-python snippets; verify `$TMPDIR` variables are expanded as intended.
- Remove `__pycache__` and `.pyc` from package directories before archive rebuild to avoid undeclared asset failures.
- Persist verification outputs to `$TMPDIR` logs and reference them in results files.

### Baseline Snapshot (MANDATORY)

Every results file MUST include a baseline snapshot capturing the system state AFTER the agent's work. This is the starting point for the next agent's validation. Include:

- **Packages installed:** count and list
- **Total tests:** across ALL staged packages

The reviewer uses this to validate: "Agent N+1 started from Agent N's baseline. Did anything regress?"

---

## Agent Prompt Contract

The agent prompt template, behavior rules, 13-question gate protocol, and adversarial simulation are defined in a separate prompt contract:

**`handoffs/BUILDER_PROMPT_CONTRACT.md`**

This contract is the first prompt pack for the build process framework. Every handoff uses it to generate the agent prompt. As the framework matures, additional prompt contracts will join it (e.g., review, integration, conformance). When the build process is formalized as a DoPeJar framework, these become prompt packs (PRM-NNN) under that framework's spec pack.

---

## Tier Model

Three tiers: **HOT** (executive/kernel) > **HO2** (session/admin) > **HO1** (stateless/fast).

HO3 IS the correct name for the executive/governance tier. HOT and HO3 are synonyms — both refer to the same tier. HOT = HO-Three (shorthand).

Currently all packages target `plane_id: "hot"`. Multi-tier deployment is a future capability.

---

## Reviewer Checklist

**Before marking any handoff as VALIDATED, the reviewer MUST verify ALL of these:**

- [ ] RESULTS file exists at `_reboot/_staging/handoffs/<handoff_id>/<handoff_id>_RESULTS.md`
- [ ] RESULTS file has ALL required sections: Files Created, Test Results, Full Regression, Clean-Room Verification, Baseline Snapshot
- [ ] Clean-Room Verification section shows: package count, install order, all tests PASS
- [ ] Baseline Snapshot section shows: package count, total test count
- [ ] Full regression test was run (ALL staged packages, not just this one)
- [ ] No new test failures introduced (compare against previous baseline)
- [ ] Manifest hashes use `sha256:<64hex>` format (not bare hex)
- [ ] RESULTS file location matches naming convention (`<handoff_id>_RESULTS.md` in handoff directory)

**This checklist exists because Phase 2 handoffs (H-13 through H-17) were accepted without these checks, resulting in: 4 missing RESULTS files, no clean-room verification, no registry updates, stale CP_BOOTSTRAP, and broken entrypoint wiring. The standard had the right requirements. The review process didn't enforce them.**

---

## Multi-Package Builds (Parallel Waves)

When building multiple packages across parallel waves:

### During Each Wave
1. Each package in the wave gets its own RESULTS file following the full template
2. Reviewer validates each RESULTS file against the Reviewer Checklist above
3. Clean-room verification runs for EACH wave (not deferred to the end)

### After the Final Wave: Integration Handoff (MANDATORY)
When a set of packages constitutes a system change (new dispatch loop, new tier, etc.), an **Integration Handoff** is required after all code packages are built. This is a separate handoff spec that:

1. **Wires new packages into the entrypoint** (main.py or equivalent)
2. **Resolves package lifecycle** (mark superseded packages, update dependencies)
3. **Runs E2E smoke test** (not just unit tests — verify the integrated system works end-to-end)
4. **Writes RESULTS file** with full system baseline snapshot

**The integration handoff is where component packages become a working system.** Without it, you have tested parts but no tested whole.

