# D5: Research — Dark Factory Orchestrator

**Component:** Dark Factory Orchestrator
**Spec Version:** 0.1.0 (matches D2)
**Status:** Complete
**Open Questions:** 0

---

## Research Log

#### RQ-001: How should the orchestrator parse D-template markdown documents?

**Prompted By:** D2 SC-001 (validate spec), D3 E-001 (ProductSpec)
**Priority:** Blocking (must resolve before Plan — determines core parsing architecture)

**Sources Consulted:**
- test/ directory (filled HO1 example — actual D1-D10 documents to parse)
- D-template structure (Factory_Spec_Test templates — define expected sections)
- Python markdown parsing libraries: python-markdown, mistune, markdown-it-py

**Findings:**
The D-documents follow a consistent structure: H1 title, metadata block (key: value lines), H2/H3 sections with known names, and structured content within sections (tables, code blocks, bullet lists). The content is not arbitrary markdown — it follows the template structure defined in the Factory_Spec_Test templates. This means parsing can be heading-based (split by H2/H3 headings) rather than full AST parsing.

Key patterns observed in test/ documents:
- D2 scenarios follow `#### SC-NNN:` heading pattern with GIVEN/WHEN/THEN keywords
- D4 contracts follow `#### IN-NNN:`, `#### OUT-NNN:`, `#### SIDE-NNN:`, `#### ERR-NNN:` patterns
- D6 clarifications have `**Status:**` lines with OPEN/RESOLVED/ASSUMED values
- D8 tasks follow `#### T-NNN:` with `**Depends On:**` and `**Scenarios Satisfied:**` fields
- D9 holdouts follow `### HS-NNN:` with `**Validates:**` and `**Contracts:**` fields

**Options Considered:**

| Option | Pros | Cons |
|--------|------|------|
| Full markdown AST parsing (python-markdown) | Handles any markdown | Overkill — we only need heading-level structure |
| Regex-based heading extraction | Simple, fast, no dependencies | Fragile if heading format varies |
| Heading-based section splitter + regex for structured fields | Right level of abstraction | Requires test coverage for each D-doc format |

**Decision:** Heading-based section splitter with regex extraction for structured fields.
**Rationale:** The D-documents have known structure (templates define it). A heading splitter + field extractor is testable, lightweight, and sufficient. Full AST parsing adds complexity without benefit.

#### RQ-002: How should the orchestrator dispatch builder agents?

**Prompted By:** D2 SC-005 (full pipeline), D2 NEEDS CLARIFICATION on agent backend
**Priority:** Blocking (determines dispatch interface in D4)

**Sources Consulted:**
- Claude Code CLI documentation (subprocess invocation)
- Anthropic Messages API (direct API calls)
- test/ D10_AGENT_CONTEXT.md (commands section — shows how builders operate)

**Findings:**
Two viable dispatch mechanisms:

1. **Claude Code subprocess:** `claude --print --allowedTools ... -p "prompt"`. The orchestrator launches Claude Code as a child process, passes the agent prompt via stdin or -p flag, and collects output. Claude Code handles tool use (file reads, writes, bash), context management, and conversation flow. The orchestrator only needs to invoke the subprocess and collect the results file when done.

2. **Claude API direct:** Use the Anthropic Messages API with tool_use to simulate Claude Code's behavior. The orchestrator would need to implement tool dispatch (file read, write, bash execution) and conversation loop management. This is significantly more complex but gives full control over the interaction.

**Options Considered:**

| Option | Pros | Cons |
|--------|------|------|
| Claude Code subprocess | Simple dispatch, proven tool use, full capability | Less control over agent behavior, dependency on Claude Code CLI |
| Claude API direct | Full control, custom tool definitions | Must implement tool loop, file I/O, conversation management — essentially rebuilding Claude Code |
| Both (configurable) | Flexibility | Two code paths to maintain |

**Decision:** Claude Code subprocess as the primary (and initially only) dispatch mechanism.
**Rationale:** Claude Code already handles the hard problems (tool use, conversation management, file operations). The orchestrator's job is dispatch and validation, not agent runtime. Direct API can be added later if needed (DEF-003 in D2).

#### RQ-003: How should holdout scenarios be executed?

**Prompted By:** D2 SC-004 (run holdouts), D2 NEEDS CLARIFICATION on holdout execution
**Priority:** Blocking (determines holdout runner interface)

**Sources Consulted:**
- test/ D9_HOLDOUT_SCENARIOS.md (actual holdout format — Setup/Execute/Verify with bash commands and check tables)
- Dark Factory pattern (StrongDM HackerNoon article — holdouts as YAML with assertions)
- pytest subprocess execution patterns

**Findings:**
The test/ D9 holdouts describe verification in two forms:
1. **Bash commands** in Setup/Execute blocks (e.g., "dispatch a classify work order")
2. **Check tables** in Verify blocks with PASS/FAIL conditions stated in prose

For automated execution, the orchestrator needs to:
- Run Setup commands (bash subprocess)
- Run Execute commands (bash subprocess, capturing output)
- Evaluate Verify conditions (this is the hard part — conditions are stated in prose, not as executable assertions)

The pragmatic approach: D9 holdouts should include executable verify commands alongside the prose descriptions. The orchestrator executes the commands and checks exit codes (0 = PASS, non-zero = FAIL). Prose descriptions remain for the human reviewer.

**Options Considered:**

| Option | Pros | Cons |
|--------|------|------|
| Bash-only verification (exit codes) | Simple, universal | Requires D9 author to write executable checks |
| Python test functions (imported) | Rich assertions, structured output | Requires D9 to include Python code |
| Hybrid (bash commands + optional Python) | Flexible | Two execution paths |

**Decision:** Bash-only verification with exit codes. D9 authors write executable `verify.sh` scripts or inline bash commands with explicit exit codes.
**Rationale:** Keeps the holdout execution simple and universal. Python assertions can be wrapped in bash commands (`python3 -c "assert ..."`). The orchestrator's job is to run commands and report results, not to interpret prose.

---

## Prior Art Review

### What Worked
- The test/ directory proves the D1-D10 pipeline produces coherent, traceable specs
- FINDINGS.md confirms that D-templates naturally produce handoff content (extraction, not authoring)
- The 13-question gate catches misunderstanding before code is written
- D9 holdout scenarios caught edge cases the builder wouldn't think of

### What Failed
- No orchestrator exists — the test/ run was entirely manual
- The task-to-handoff mapping (D8 task T-001 → handoff H-TEST-01) was done by hand
- Holdout execution was described but not actually run (simulated results)
- The 7-deliverable model (PRODUCT_SPEC_FRAMEWORK.md) and 10-deliverable model (D1-D10 templates) are not aligned — numbering differs

### Lessons for This Build
- The orchestrator should support both the 7-deliverable and 10-deliverable models (the 7 is a condensed view of the 10; the mapping is: D1→Constitution, D2→Spec+Stories, D3→DataModel+Interfaces, D4→DependencySurface, D5→Research, D6→GapAnalysis+Clarifications, D7→Plan, D8→Tasks, D9→Holdouts, D10→AgentContext). For MVP, support the 10-deliverable model (it's what the test/ directory uses).
- The handoff ID scheme (H-FACTORY-NNN) should be auto-generated from D8 task IDs to eliminate manual mapping
- Holdout execution must be tested with real (not simulated) results before claiming the factory works
