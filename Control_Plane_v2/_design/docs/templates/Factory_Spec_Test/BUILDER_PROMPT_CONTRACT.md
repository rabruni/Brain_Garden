# Builder Agent Prompt Contract

**Type**: Prompt contract for the build process framework
**Version**: 1.2.0
**Process standard**: `handoffs/BUILDER_HANDOFF_STANDARD.md`
**Note**: This is the first prompt contract for the build process framework. It will be joined by additional contracts as the framework matures (e.g., review, integration, conformance). When the build process is formalized as a DoPeJar framework, this becomes a prompt pack (PRM-NNN) under that framework's spec pack.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-02-21 | Initial extraction from BUILDER_HANDOFF_STANDARD.md |
| 1.1.0 | 2026-02-21 | Adversarial simulation mandatory (not bonus). DTT clarified as per-behavior TDD. Archive rule uses pack() not shell tar. Results path uses per-handoff directory. Gate reference in adversarial TBD (pending gate audit). |
| 1.2.0 | 2026-02-22 | Genesis cleanup: removed kernel tool, gate, governance pipeline, and CP_BOOTSTRAP references (infrastructure not yet built). Template adversarial defaults to genesis set. Paths updated to _reboot/_staging/. |

**Contract version MUST be recorded in the agent prompt when dispatched.** The reviewer checks that the prompt version matches the current contract version. If the contract was updated between spec authoring and dispatch, re-generate the prompt from the current contract.

---

## Template

Every handoff includes a copy-paste agent prompt built from this contract. Variables in `[BRACKETS]` are filled per handoff.

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: [HANDOFF_ID]** — [ONE_LINE_MISSION]
**Prompt Contract Version: [CONTRACT_VERSION]**

Read your specification, answer the 13 questions below (10 verification + 3 adversarial), then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_reboot/_staging/handoffs/[HANDOFF_ID]/[HANDOFF_ID]_BUILDER_HANDOFF.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_reboot/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Per-behavior TDD cycles: write a failing test for one behavior, write minimum code to pass, refactor, repeat. NOT all-tests-then-all-code.
3. Archive creation: Use deterministic archive creation for ALL archives. NEVER use shell `tar`.
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total).
5. Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail, and whether you introduced new failures.
6. Results file: Write `Control_Plane_v2/_reboot/_staging/handoffs/[HANDOFF_ID]/[HANDOFF_ID]_RESULTS.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md. MUST include: Clean-Room Verification section, Baseline Snapshot section, Full Regression section. Missing sections = incomplete handoff.
7. No hardcoding: Every threshold, timeout, retry count, rate limit — all config-driven.

**Before writing ANY code, answer ALL 13 questions to confirm your understanding:**

Verification (10):
1. [QUESTION]
2. [QUESTION]
...
10. [QUESTION]

Adversarial (3 — MANDATORY, Genesis set):
11. The Dependency Trap: What does your deliverable depend on that doesn't exist yet? How do you handle that absence without inventing infrastructure?
12. The Scope Creep Check: What is the closest thing to 'building infrastructure' in your plan, and why is it actually in scope?
13. The Semantic Audit: Identify one word in your current plan that is ambiguous according to the Lexicon of Precision and redefine it now.

**STOP AFTER ANSWERING ALL 13.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The verification is a gate, not a formality. Wait for approval.
```

---

## Agent Behavior Rules

### Self-Identification

The first line of the prompt IS the identity. The agent does not need to "print" it — it's stated as context. The user sees which agent is active from the prompt itself.

### 13-Question Gate (STOP and WAIT)

The verification is a **checkpoint, not a warm-up**. The agent:
1. Reads the handoff document and referenced code
2. Answers all 10 verification questions + 3 adversarial questions
3. **STOPS and WAITS for user approval**

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

---

## 13-Question Guidelines

Every agent prompt MUST include 13 questions (10 verification + 3 adversarial):
- Questions 1-3: Scope (what are you building, what are you NOT building)
- Questions 4-6: Technical details (APIs, file locations, data formats)
- Questions 7-8: Packaging and archives (manifest hashes, dependencies)
- Question 9: Test count or verification criteria
- Question 10: Integration concern (how does this connect to existing components)

### Adversarial Simulation (MANDATORY)

Questions 11-13 are mandatory, not optional. Before executing the first command, the builder MUST answer all three.

The spec writer (HO2) selects the appropriate adversarial set based on system maturity. Two sets exist:

#### Genesis Adversarial (use when infrastructure does not yet exist)

> **Active when:** No kernel tools, no gates, no governance pipeline, no packages. The system is being built from nothing.

11. **The Dependency Trap:** "What does your deliverable depend on that doesn't exist yet? How do you handle that absence without inventing infrastructure?"
12. **The Scope Creep Check:** "What is the closest thing to 'building infrastructure' in your plan, and why is it actually in scope?"
13. **The Semantic Audit:** "Identify one word in your current plan that is ambiguous according to the Lexicon of Precision and redefine it now."

#### Infrastructure Adversarial (use when governance pipeline is operational)

> **Activates when:** Kernel tools exist (compute_sha256, pack), gates are running, packages install through the governed pipeline. The builder has real infrastructure to test against.
>
> <!-- TODO: Switch to this set once HO1 kernel is built and governance pipeline is operational. -->
> <!-- TRIGGER: First handoff where the builder can run gate_check.py and produce SHA256 hashes. -->

11. **The Failure Mode:** "Which specific file/hash in your scope is the most likely culprit if a gate check fails?"
12. **The Shortcut Check:** "Is there a Kernel tool you are tempted to skip in favor of a standard shell command? If yes, explain why you will NOT do that."
13. **The Semantic Audit:** "Identify one word in your current plan that is ambiguous according to the Lexicon of Precision and redefine it now."

#### Selection Rule

The Semantic Audit (Q13) is universal — it applies in both sets. Questions 11 and 12 evolve as the system matures. The spec writer picks the set that matches reality. Using infrastructure adversarial against a genesis handoff produces meaningless answers. Using genesis adversarial against a mature handoff misses the real risks.

Include expected answers after the prompt (visible to the reviewer, not to the agent).

---

## Variables

| Variable | Source | Example |
|----------|--------|---------|
| `[HANDOFF_ID]` | Handoff ID | `H-32` |
| `[ONE_LINE_MISSION]` | Mission section of handoff | `Build HO3 cognitive process (Steps 1+5)` |
| `[CONTRACT_VERSION]` | This document's version header | `1.2.0` |
| `[QUESTION]` | Per-handoff verification questions | See 13-Question Guidelines |
