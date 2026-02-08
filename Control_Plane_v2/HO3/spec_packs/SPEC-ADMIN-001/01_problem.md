# Problem Statement

## Problem Description

The Control Plane is a complex governance system with multiple frameworks, specs, packages, ledgers, and tiers. Humans need a way to understand and navigate this system without reading raw JSON or CSV files directly.

Current challenges:

1. **Understanding artifacts**: Users don't know what a framework, spec, or package does without reading source files and documentation manually.

2. **Tracing ownership**: Determining which spec owns which file, and which framework governs which spec, requires navigating multiple registry files.

3. **System health**: Verifying the system is healthy requires running multiple scripts and interpreting their output.

4. **Context reconstruction**: Understanding what the system has done recently requires reading ledger files and interpreting hash chains.

While `trace.py` provides machine-readable (JSON) and markdown output, it doesn't provide conversational, context-aware explanations that adapt to the user's questions.

## Impact

**Who is affected:**
- Developers working with the Control Plane need to understand artifacts
- Operators need to verify system health and trace issues
- Auditors need to understand the governance chain
- Anyone onboarding to the system needs orientation

**Severity:**
- Medium: The system works without an Admin Agent, but is harder to understand
- Opportunity: Demonstrates agents can operate within governance (proof of concept)

## Non-Goals

- This spec does NOT provide write capabilities (install, approve, modify)
- This spec does NOT implement multi-turn conversation memory
- This spec does NOT handle LLM prompt engineering (uses simple wrapper)
- This spec does NOT manage API keys (reads from environment)

## Constraints

- Must operate in read-only mode (no PRISTINE writes)
- Must log all queries to L-EXEC
- Must be installed as a governed package (not loose code)
- Must wrap trace.py rather than reimplementing its logic
