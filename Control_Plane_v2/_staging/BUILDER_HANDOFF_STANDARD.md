# Builder Handoff Standard

## Purpose

This document defines the standard format for all builder handoff documents in the Control Plane v2 project. Every handoff — whether a new component, a follow-up fix, or an upgrade — must follow this template.

---

## File Naming

| Type | Pattern | Example |
|------|---------|---------|
| New component | `BUILDER_HANDOFF_<N>_<name>.md` | `BUILDER_HANDOFF_3_prompt_router.md` |
| Follow-up | `BUILDER_FOLLOWUP_<N><letter>_<name>.md` | `BUILDER_FOLLOWUP_3A_governance_health.md` |

Numbering follows the build sequence. Letters (A, B, C...) are follow-ups to a numbered handoff.

---

## Required Sections

Every handoff document MUST contain these sections in order:

### 1. Mission
One paragraph: what the agent is building and why. Include the package ID(s).

### 2. Critical Constraints
Numbered list. Always includes these non-negotiable rules:

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** New code ships as packages in `_staging/PKG-<NAME>/` with manifest.json, SHA256 hashes, proper dependencies. Follow existing package patterns.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → install Layers 0-2 (8 packages) → install YOUR new packages. All gates must pass.
5. **No hardcoding.** Every threshold, timeout, retry count, rate limit — all config-driven. This is the #1 lesson from 7 layers of prior art.
6. **No file replacement.** Packages must NEVER overwrite another package's files. Use state-gating instead.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`).
8. **Results file.** When finished, write `_staging/RESULTS_<handoff_id>.md` (see Results File section below).
9. **Full regression test.** Run ALL staged package tests (not just yours) and report results. New failures you introduced are blockers. Pre-existing failures from unvalidated packages are noted but not blockers.
10. **Baseline snapshot.** Your results file must include a baseline snapshot (package count, file_ownership rows, total tests, all gate results) so the next agent can diff against it.

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
| Example | `_staging/PKG-KERNEL-001/HOT/kernel/file.py` | Pattern to follow |

### 8. End-to-End Verification
Exact commands for clean-room verification. Copy-pasteable. Include expected output.

### 9. Files Summary
Table of every file created or modified:

| File | Location | Action |
|------|----------|--------|
| `name.py` | `_staging/PKG-NAME/HOT/kernel/` | CREATE |

### 10. Design Principles
Non-negotiable design rules for this specific component. Usually 4-6 bullet points.

---

## Results File

**Every handoff agent MUST write a results file when finished.**

**File:** `Control_Plane_v2/_staging/RESULTS_<handoff_id>.md`

Example: `RESULTS_HANDOFF_3.md`, `RESULTS_FOLLOWUP_3A.md`

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
- CP_BOOTSTRAP.tar.gz (SHA256: jkl012...) [if rebuilt]

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
- Command: `CONTROL_PLANE_ROOT="$TMPDIR" python3 -m pytest Control_Plane_v2/_staging/ -v --ignore=<any unvalidated packages>`
- New failures introduced by this agent: [list or NONE]

## Gate Check Results
- G0B: PASS/FAIL (N files, N orphans)
- G1: PASS/FAIL (N chains)
- G1-COMPLETE: PASS/FAIL (N frameworks)
- [Any new gates]: PASS/FAIL

## Baseline Snapshot (AFTER this agent's work)
- Packages installed: N
- file_ownership.csv rows: N (N unique files, N supersession rows)
- Total tests (all staged): N
- Gate results: [list all gates and PASS/FAIL]

## Clean-Room Verification
- Packages installed: N
- Install order: PKG-A → PKG-B → PKG-C
- All gates pass after each install: YES/NO
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
CONTROL_PLANE_ROOT="$TMPDIR" python3 -m pytest Control_Plane_v2/_staging/ -v \
    --ignore=<any packages known to be unvalidated>
```

Report: total tests, pass/fail counts, and explicitly state whether any NEW failures were introduced. Pre-existing failures (from unvalidated packages) should be noted but are not blockers.

### Execution Shortcuts (Recommended)

Use these patterns to reduce avoidable failures and speed up validation:

- Prefer bootstrap orchestrator over manual install chains: run `./install.sh --root "$TMPDIR" --dev` from extracted bootstrap root.
- Use two-stage testing: package-local tests first for fast confidence, then mandatory full staged regression.
- Always run the exact mandatory full staged command and report blockers separately if collection is polluted by temporary rebuild trees.
- For smoke scripts writing temporary ledgers, patch pristine append-only guard in test scope (`patch("kernel.pristine.assert_append_only", ...)`) when ledger path is outside governed boundaries.
- Avoid quoted heredoc mistakes in shell-to-python snippets; verify `$TMPDIR` variables are expanded as intended.
- Remove `__pycache__` and `.pyc` from package directories before archive rebuild to avoid undeclared asset failures.
- Keep tar format strict: `tar czf ... -C dir $(ls dir)` and never `tar czf ... -C dir .`.
- Persist verification outputs to `$TMPDIR` logs (`install_stdout.txt`, `install_stderr.txt`, `gates_all.txt`, pytest outputs) and reference them in results files.

### Baseline Snapshot (MANDATORY)

Every results file MUST include a baseline snapshot capturing the system state AFTER the agent's work. This is the starting point for the next agent's validation. Include:

- **Packages installed:** count and list
- **file_ownership.csv:** total rows, unique files, supersession rows
- **Total tests:** across ALL staged packages
- **Gate results:** every gate from `gate_check.py --all`

The reviewer uses this to validate: "Agent N+1 started from Agent N's baseline. Did anything regress?"

---

## Agent Prompt Template

Every handoff includes a copy-paste agent prompt. Format:

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**YOUR IDENTITY — print this FIRST before doing anything else:**
> **Agent: [HANDOFF_ID]** — [one-line mission summary]
> Example: **Agent: FOLLOWUP-3C** — PKG-LAYOUT-002: remove HO3, materialize HO2/HO1 tier directories

This identifies you in the user's terminal. Always print your identity line as your very first output.

**Read this file FIRST — it is your complete specification:**
`Control_Plane_v2/_staging/<HANDOFF_FILE>.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` — NEVER `tar czf ... -C dir .`
4. End-to-end verification: [specific to handoff]
5. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_<id>.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. [Question]
2. [Question]
...
10. [Question]

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

### Agent Self-Identification

**Every agent MUST print an identity line as its very first output.** Format:

> **Agent: [HANDOFF_ID]** — [one-line mission]

Examples:
- **Agent: HANDOFF-3** — PKG-PROMPT-ROUTER-001 + PKG-TOKEN-BUDGETER-001
- **Agent: FOLLOWUP-3A** — Governance health tests: ownership-based validation
- **Agent: FOLLOWUP-3B** — install.sh + INSTALL.md for CP_BOOTSTRAP.tar.gz
- **Agent: FOLLOWUP-3C** — PKG-LAYOUT-002: remove HO3, materialize tier directories
- **Agent: HANDOFF-4** — PKG-ATTENTION-001: context assembly pipeline

This lets the user immediately identify which agent is reporting in their terminal without reading through code or feedback.

### 10-Question Gate (STOP and WAIT)

The 10-question verification is a **checkpoint, not a warm-up**. The agent:
1. Prints its identity line
2. Reads the handoff document and referenced code
3. Answers all 10 questions
4. **STOPS and WAITS for user approval**

The agent must NOT:
- Start creating directories after answering questions
- Begin writing tests or code
- Create task lists or plans

The user may:
- Correct a wrong answer and tell the agent to proceed
- Ask follow-up questions
- Redirect the agent to a different approach
- Greenlight: "Go ahead" / "Proceed" / "Looks good, implement"

Only after explicit greenlight does the agent begin DTT.

### 10-Question Guidelines

Every agent prompt MUST include 10 verification questions:
- Questions 1-3: Scope (what are you building, what are you NOT building)
- Questions 4-6: Technical details (APIs, file locations, data formats)
- Questions 7-8: Packaging and archives (tar format, manifest hashes, dependencies)
- Question 9: Test count or verification criteria
- Question 10: Integration concern (how does this connect to existing components)

Include expected answers after the prompt (visible to the reviewer, not to the agent).

---

## Governance Chain for New Packages

All Layer 3+ packages use this pattern until framework auto-registration is built:

```json
{
  "spec_id": "SPEC-GATE-001",
  "framework_id": "FMWK-000",
  "plane_id": "hot"
}
```

If the package introduces a NEW framework (e.g., FMWK-003), ship the framework manifest as an asset inside the package. It won't be in the registry yet, but it's on disk and governed. When auto-registration lands (future kernel upgrade), these manifests get registered automatically.

---

## Tier Model

Three tiers: **HOT** (executive/kernel) > **HO2** (session/admin) > **HO1** (stateless/fast).

HO3 does not exist. It was a prior agent mistake. If you see HO3 anywhere, flag it.

Currently all packages target `plane_id: "hot"`. Multi-tier deployment is a future capability.

---

## Cross-Cutting Concerns Registry

Track architectural concerns that span multiple handoffs. These are NOT immediate action items — they're decisions to make when the relevant component is built.

| Concern | Affects | Decision Point | Current Status |
|---------|---------|---------------|----------------|
| Cross-tier ledger reads | Handoffs #6 (ledger query), #8 (learning loops) | When first HO2 package exists | Data centralized in HOT. `scope.tier` field enables filtered queries. Physical split deferred. |
| Tier privilege enforcement | authz.py, package_install.py, flow runner | When first HO2 agent is built | Unimplemented. Isolation is conceptual. Will be enforced in authz.py at API boundary. |
| Per-tier registries | file_ownership.csv, gate_check.py | When first package targets HO2 | Single centralized registry. `plane_id` in manifests enables future split. |
| Framework auto-registration | package_install.py, registry CSVs | After flow runner is stable | State-gating: FMWK manifests ship as assets, registered when capability exists. |
| Dynamic tier provisioning | flow runner, layout.json | When a framework requests a non-base tier | Not built. Base 3 tiers created at bootstrap. |

---

## Agent Registry

**Maintained in MEMORY.md** under `### Agent Registry`. This is the single source of truth for which agents have been dispatched, their status, and where to find their results.

Every time a handoff is dispatched to an agent, the reviewer MUST add a row:

| Handoff ID | Package(s) | Platform | Status | Blocked By | Results File |
|------------|-----------|----------|--------|-----------|-------------|
| FOLLOWUP-3D | genesis fix + G0K removal | Claude | DISPATCHED | — | — |
| HANDOFF-4 | PKG-ATTENTION-001 | ? | COMPLETE (unvalidated) | FOLLOWUP-3D | Missing |
| HANDOFF-5 | PKG-FLOW-RUNNER-001 | ? | COMPLETE (unvalidated) | FOLLOWUP-3D, HANDOFF-4 | Missing |
| ... | ... | ... | ... | ... | ... |

**Status values:**
- `NOT DISPATCHED` — handoff doc written, not yet sent to an agent
- `DISPATCHED` — handoff sent to agent, awaiting 10-question answers
- `APPROVED` — 10-question answers reviewed, agent told to proceed
- `COMPLETE` — agent finished, results file written
- `VALIDATED` — reviewer verified results file + spot-checked hashes/tests
- `FAILED` — agent failed, see notes
- `BLOCKED` — waiting on dependency (see Blocked By column)

**Blocked By column:**
- Lists handoff IDs that must reach VALIDATED before this handoff can be dispatched or validated
- Empty (`—`) means no dependencies
- When all blockers reach VALIDATED, the handoff is unblocked
- This is how we know what's safe to run in parallel vs. what's serial

**Rules:**
1. Update the registry when dispatching, approving, and validating
2. Always record the agent platform (Claude, Codex, Gemini, etc.)
3. Link to results file when COMPLETE
4. Agents that predate the standard get backdated entries with `(predates standard)` for results
5. Always set Blocked By when creating a registry entry — think about what must be stable first
6. When validating an agent, compare its baseline snapshot against the previous agent's baseline to detect regressions

---

## Common Mistakes

1. **Wrong staging path.** `Control_Plane_v2/_staging/`, NOT `CP_2.1/_staging/`.
2. **Tar `./` prefix.** NEVER `tar czf ... -C dir .` — always `tar czf ... -C dir $(ls dir)`.
3. **Missing PKG-TOKEN-BUDGETER-001 dependency.** Router depends on budgeter.
4. **HO3 references.** HO3 is dead. Flag and remove.
5. **Hardcoded thresholds.** Every number must come from config. No magic constants.
6. **File replacement.** Packages never overwrite another package's files. Use state-gating.
7. **Forgetting results file.** Agent MUST write RESULTS_<id>.md when finished.
8. **No self-identification.** Agent MUST print `**Agent: [ID]** — [mission]` as its FIRST output.
9. **Proceeding without approval.** After the 10-question verification, STOP and WAIT. Do NOT start building until the user says go.
10. **Only testing own package.** Run ALL staged tests, not just yours. Cross-package regressions are real.
11. **Missing baseline snapshot.** Results file MUST include package count, file_ownership rows, total test count, and all gate results. Without this, the next agent starts blind.
