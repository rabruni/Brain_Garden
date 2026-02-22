# D6: Gap Analysis — Dark Factory Orchestrator

**Component:** Dark Factory Orchestrator
**Spec Version:** 0.1.0 (matches D2/D3/D4)
**Status:** Complete
**Shared Gaps:** 1
**Private Gaps:** 1
**Unresolved:** 0

---

## Boundary Analysis

### 1. Data In

The orchestrator's input is a directory of D-template markdown files. There is no external API or protocol — it reads files from disk.

| Boundary | Classification | Status |
|----------|---------------|--------|
| D1-D10 markdown files from spec_dir | PRIVATE (orchestrator is the only consumer of raw D-docs) | RESOLVED — D3 E-001 defines the parsed representation. Parsing is heading-based per D5 RQ-001. |
| CLI arguments (spec_dir, output_dir, etc.) | PRIVATE | RESOLVED — D4 IN-001 through IN-005 define all CLI contracts. |

**Gaps found:** None.

### 2. Data Out

| Boundary | Classification | Status |
|----------|---------------|--------|
| Generated handoff markdown files | SHARED (builder agents consume these) | RESOLVED — Must follow BUILDER_HANDOFF_STANDARD.md format. D4 OUT-002. |
| Generated agent prompt files | SHARED (dispatched to builder agents) | RESOLVED — Must follow BUILDER_PROMPT_CONTRACT.md template. D4 OUT-003. |
| Validation reports (JSON) | SHARED (operator reads) | RESOLVED — D3 E-002, D4 OUT-001. |
| Holdout reports (JSON) | SHARED (operator reads) | RESOLVED — D3 E-006, D4 OUT-004. |
| Factory report (JSON) | SHARED (operator reads) | RESOLVED — D3 E-007, D4 OUT-005. |

**Gaps found:** None. All output shapes defined in D3/D4.

### 3. Persistence

| What | Where | Owned By | Status |
|------|-------|----------|--------|
| Dispatch ledger | JSONL file in output_dir | Orchestrator | RESOLVED — D4 SIDE-001 defines append-only writes. |
| Generated files (handoffs, prompts, reports) | output_dir filesystem | Orchestrator | RESOLVED — D4 OUT-002, OUT-003. |

**Gaps found:** None.

### 4. Auth / Authz

| Boundary | Status |
|----------|--------|
| Orchestrator → Claude Code subprocess | RESOLVED — Claude Code handles its own auth (API key from environment). Orchestrator passes `ANTHROPIC_API_KEY` through environment. |
| Orchestrator → filesystem | RESOLVED — Standard filesystem permissions. No special auth needed. |

**Gaps found:** None.

### 5. External Services

| Service | Interface | Status |
|---------|-----------|--------|
| Claude Code CLI | Subprocess with stdin/stdout | RESOLVED — D5 RQ-002 decided subprocess dispatch. Interface is: launch process, pass prompt, collect results file. |

#### GAP-001: Claude Code Invocation Contract (RESOLVED)

**Category:** External Services
**What Is Needed:** Exact CLI arguments and environment variables for invoking Claude Code as a builder agent.
**Existing Contract:** None — Claude Code's CLI interface is external documentation, not a D-document contract.
**Gap Description:** The orchestrator must know: (a) exact command to launch Claude Code, (b) how to pass the agent prompt, (c) how to specify allowed tools, (d) how to set the working directory, (e) how to detect completion, (f) how to collect results.
**Shared?:** NO (orchestrator-private — only the orchestrator calls Claude Code)

**Recommendation:**
- [x] Define inline — component-private, no shared concern

**Resolution:** The invocation contract is:
```bash
claude --print \
  --allowedTools "Read,Write,Edit,Bash,Glob,Grep" \
  --workdir <spec_staging_dir> \
  -p "<agent_prompt_text>"
```
Completion is detected by process exit. Results file existence is checked at the expected path from the handoff spec. If the results file is missing after process exit, the dispatch is marked FAILED.

**Impact If Unresolved:** Orchestrator cannot dispatch agents — the entire pipeline would be manual.

### 6. Configuration

| Config Item | Source | Status |
|-------------|--------|--------|
| Agent backend (claude-code vs future alternatives) | CLI argument, default "claude-code" | RESOLVED — D4 IN-005. |
| Claude Code binary path | Environment variable or PATH | RESOLVED — Use `which claude` or configurable via `FACTORY_CLAUDE_PATH`. |
| Adversarial question set (genesis vs infrastructure) | Config file or CLI flag | RESOLVED — Default to genesis. Config file can override. |
| Output directory | CLI argument | RESOLVED — D4 IN-002, IN-005. |

**Gaps found:** None.

### 7. Error Propagation

| Error Source | Propagation Path | Status |
|--------------|-----------------|--------|
| Spec validation failure | Orchestrator → FAIL report → operator | RESOLVED — D4 ERR-001. |
| Handoff generation failure | Orchestrator → FAIL report → operator | RESOLVED — D4 ERR-002. |
| Builder agent failure | Orchestrator → marks task FAILED → checks dependency graph → blocks dependent tasks → reports to operator | RESOLVED — D2 SC-008, D4 ERR-003/BUILDER_TASK_FAILED. |
| Holdout failure | Orchestrator → failure report with traceability → operator | RESOLVED — D2 SC-009, D4 ERR-004/HOLDOUT_SCENARIO_FAILED. |
| Claude Code process crash | Orchestrator → marks dispatch FAILED → reports to operator | RESOLVED — D4 ERR-003. |

**Gaps found:** None.

### 8. Observability

| What | How | Status |
|------|-----|--------|
| Spec validation results | JSON report to stdout and file | RESOLVED — D4 OUT-001. |
| Dispatch events | Dispatch ledger (JSONL) | RESOLVED — D4 SIDE-001. |
| Holdout results | JSON report | RESOLVED — D4 OUT-004. |
| Pipeline progress | Stdout logging during run | RESOLVED — orchestrator prints status per task: "Dispatching T-001...", "T-001 COMPLETED", etc. |

**Gaps found:** None.

### 9. Resource Accounting

| Resource | Accounting Method | Status |
|----------|-------------------|--------|
| Tokens consumed per dispatch | Extracted from builder results file or Claude Code output | RESOLVED — D3 E-005 DispatchRecord.tokens_used. |
| Wall-clock time | Timestamp diff between dispatch and completion | RESOLVED — D3 E-005 timestamp fields. |

#### GAP-002: Token Extraction from Claude Code Output (RESOLVED)

**Category:** Resource Accounting
**What Is Needed:** Method to extract total tokens consumed from a Claude Code subprocess run.
**Existing Contract:** None.
**Gap Description:** Claude Code's `--print` mode outputs the final response. Token usage may be available in stderr or a metrics file, but this is not guaranteed by Claude Code's interface.
**Shared?:** NO

**Recommendation:**
- [x] Stub with documented assumptions (interface may change)

**Resolution:** For MVP, token accounting is optional. The orchestrator records "tokens_used: null" if extraction is not available. When Claude Code exposes token metrics (via `--json` output or a metrics file), the orchestrator will extract them. This does not block the pipeline — token accounting is informational, not functional.

**Impact If Unresolved:** No token-level cost tracking. Acceptable for initial use.

---

## Clarification Log

#### CLR-001: Agent backend for dispatch

**Found During:** D2 (NEEDS CLARIFICATION marker)
**Question:** Should the orchestrator call Claude API directly, invoke Claude Code as subprocess, or both?
**Options:** See D5 RQ-002.
**Status:** RESOLVED(Claude Code subprocess as primary/only backend for MVP)
**Blocks:** D4 contracts (dispatch interface), D7 Plan (architecture)

#### CLR-002: Holdout execution method

**Found During:** D2 (NEEDS CLARIFICATION marker)
**Question:** Should holdout verify steps run as bash commands, Python functions, or both?
**Options:** See D5 RQ-003.
**Status:** RESOLVED(Bash-only with exit codes for MVP)
**Blocks:** D7 Plan (holdout runner architecture)

---

## Summary

| Category | Gaps Found | Shared | Resolved | Remaining |
|----------|-----------|--------|----------|-----------|
| Data In | 0 | 0 | 0 | 0 |
| Data Out | 0 | 0 | 0 | 0 |
| Persistence | 0 | 0 | 0 | 0 |
| Auth/Authz | 0 | 0 | 0 | 0 |
| External Services | 1 | 0 | 1 | 0 |
| Configuration | 0 | 0 | 0 | 0 |
| Error Propagation | 0 | 0 | 0 | 0 |
| Observability | 0 | 0 | 0 | 0 |
| Resource Accounting | 1 | 0 | 1 | 0 |
| **TOTAL** | **2** | **0** | **2** | **0** |

**Gate verdict: PASS — zero open items. D7 Plan may proceed.**
