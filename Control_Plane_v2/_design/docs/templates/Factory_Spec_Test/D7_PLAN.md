# D7: Plan — Dark Factory Orchestrator

**Component:** Dark Factory Orchestrator
**Spec Version:** 0.1.0 (matches D2)
**Status:** Draft
**Constitution:** D1 v1.0.0
**Gap Analysis:** D6 — PASS (0 open items)

---

## Summary

The Dark Factory Orchestrator is a Python CLI tool that reads D1-D10 product spec documents, validates spec completeness, generates builder handoff documents and agent prompts, dispatches Claude Code builder agents, runs holdout scenarios, and produces traceability reports. First use case: HO1 Cognitive Process from the test/ directory.

## Technical Context

```
Language/Version:    Python 3.10+
Key Dependencies:   None beyond stdlib for MVP (argparse, json, re, subprocess, pathlib)
Storage:            Filesystem (markdown files, JSON reports, JSONL dispatch ledger)
Testing Framework:  pytest
Platform:           macOS / Linux
Performance Goals:  Validation < 5 seconds. Generation < 10 seconds. Holdout execution depends on test complexity.
Scale/Scope:        Single operator, single spec at a time. No concurrency for MVP.
```

## Constitution Check

| Article | Principle | Compliant | Notes |
|---------|-----------|-----------|-------|
| Art 1 | Specs Are Source of Truth | YES | Orchestrator reads D-docs as-is, does not modify or reinterpret |
| Art 2 | Holdout Isolation | YES | D9 content never included in handoff or prompt output |
| Art 3 | Orchestrator Does Not Build | YES | Outputs are markdown, JSON, and reports only — no .py source files |
| Art 4 | Every Handoff Is Traceable | YES | Handoff index maps task IDs to scenario IDs to contract IDs |
| Art 5 | Validate Before Dispatch | YES | Validation is the first pipeline step; generation refuses on FAIL |
| Art 6 | Holdout Failures Trace | YES | HoldoutResult includes validates_scenarios, validates_contracts, responsible_task |
| Art 7 | No Silent Failures | YES | Every operation returns explicit PASS/FAIL/BLOCKED |
| Art 8 | Deterministic Output | YES | No randomness in generation — same input → same output |

---

## Architecture Overview

```
                    ┌─────────────────┐
                    │   CLI (main.py) │
                    │   argparse      │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
     ┌──────────────┐ ┌───────────┐ ┌────────────┐
     │ SpecParser   │ │ Generator │ │ PipeRunner │
     │ + Validator  │ │           │ │            │
     └──────┬───────┘ └─────┬─────┘ └─────┬──────┘
            │               │              │
            ▼               ▼              ▼
     ┌──────────────┐ ┌───────────┐ ┌────────────┐
     │ ProductSpec  │ │ Handoff   │ │ Dispatcher │
     │ (D3 E-001)  │ │ Writer    │ │ + Holdout  │
     └──────────────┘ └───────────┘ └────────────┘
```

### Component Responsibilities

#### SpecParser (`spec_parser.py`)

**Responsibility:** Reads D1-D10 markdown files from a directory. Splits by headings. Extracts structured fields (scenario IDs, task dependencies, clarification statuses, holdout definitions).
**Implements:** Foundation for SC-001, SC-002, SC-003, SC-004, SC-005
**Depends On:** Python stdlib (pathlib, re)
**Exposes:** `parse(spec_dir: str) -> ProductSpec`

#### SpecValidator (`spec_validator.py`)

**Responsibility:** Checks a parsed ProductSpec for completeness and consistency. Runs all validation checks from D4 OUT-001.
**Implements:** SC-001, SC-006, SC-007, SC-010
**Depends On:** SpecParser (provides ProductSpec)
**Exposes:** `validate(spec: ProductSpec) -> ValidationResult`

#### HandoffGenerator (`handoff_generator.py`)

**Responsibility:** Generates handoff markdown files from a validated ProductSpec. One handoff per D8 task. Follows BUILDER_HANDOFF_STANDARD.md format.
**Implements:** SC-002
**Depends On:** SpecValidator (must pass), BUILDER_HANDOFF_STANDARD.md (format definition)
**Exposes:** `generate(spec: ProductSpec, output_dir: str) -> list[Handoff]`

#### PromptGenerator (`prompt_generator.py`)

**Responsibility:** Generates agent prompts from handoffs. Follows BUILDER_PROMPT_CONTRACT.md template. Generates 10 verification questions from D2/D4 content. Selects adversarial set.
**Implements:** SC-003
**Depends On:** HandoffGenerator (provides handoffs), D2/D4 content from ProductSpec
**Exposes:** `generate_prompts(handoffs: list[Handoff], spec: ProductSpec, output_dir: str) -> list[AgentPrompt]`

#### AgentDispatcher (`agent_dispatcher.py`)

**Responsibility:** Launches Claude Code subprocess with agent prompt. Waits for completion. Collects results file. Records dispatch events to ledger.
**Implements:** SC-005, SC-008
**Depends On:** PromptGenerator (provides prompts), Claude Code CLI
**Exposes:** `dispatch(prompt: AgentPrompt, workdir: str) -> DispatchRecord`

#### HoldoutRunner (`holdout_runner.py`)

**Responsibility:** Executes D9 holdout scenarios against installed code. Runs Setup/Execute/Verify bash commands. Reports per-scenario PASS/FAIL with traceability.
**Implements:** SC-004, SC-009
**Depends On:** SpecParser (provides D9 holdouts), installed code at install_root
**Exposes:** `run_holdouts(spec: ProductSpec, install_root: str) -> list[HoldoutResult]`

#### ReportGenerator (`report_generator.py`)

**Responsibility:** Assembles FactoryReport from validation, dispatch, and holdout results. Computes verdict. Writes JSON and human-readable summary.
**Implements:** SC-005
**Depends On:** All other components (collects their outputs)
**Exposes:** `generate_report(validation, dispatches, holdouts) -> FactoryReport`

### File Creation Order

```
PKG-DARK-FACTORY-001/
├── factory/
│   ├── __init__.py
│   ├── main.py                  ← CLI entrypoint (argparse)
│   ├── spec_parser.py           ← D-document parsing
│   ├── spec_validator.py        ← Completeness/consistency checks
│   ├── handoff_generator.py     ← Handoff markdown generation
│   ├── prompt_generator.py      ← Agent prompt generation
│   ├── agent_dispatcher.py      ← Claude Code subprocess dispatch
│   ├── holdout_runner.py        ← D9 scenario execution
│   └── report_generator.py      ← Final report assembly
├── tests/
│   ├── test_spec_parser.py      ← Parse each D-doc format
│   ├── test_spec_validator.py   ← Validation checks
│   ├── test_handoff_generator.py ← Handoff format compliance
│   ├── test_prompt_generator.py  ← Prompt template compliance
│   ├── test_agent_dispatcher.py  ← Subprocess dispatch (mocked)
│   ├── test_holdout_runner.py    ← Holdout execution (mocked)
│   ├── test_report_generator.py  ← Report assembly
│   └── test_e2e.py              ← Full pipeline with test/ spec
└── templates/
    ├── handoff_template.md      ← Handoff markdown template
    └── prompt_template.md       ← Prompt markdown template
```

### Testing Strategy

#### Unit Tests
- SpecParser: parse each D-doc format individually (D1 articles, D2 scenarios, D6 clarifications, D8 tasks/deps, D9 holdouts). Mock filesystem with temp directories containing known markdown files.
- SpecValidator: each check independently (missing doc, OPEN D6, orphan scenario, D8 cycle). Mock ProductSpec objects.
- HandoffGenerator: section generation, traceability inclusion, D9 exclusion. Mock ProductSpec.
- PromptGenerator: template rendering, question generation, adversarial set selection. Mock Handoff.
- HoldoutRunner: command execution, exit code interpretation, result assembly. Mock subprocess.

#### Integration Tests
- Parse the actual test/ directory and validate it. Verify PASS.
- Generate handoffs from test/ and verify all 10 sections present per handoff.
- Full pipeline with mocked Claude Code (returns pre-canned results files).

#### Smoke Test
- `factory validate --spec-dir test/` returns PASS. Maps to D2 SC-001.

### Complexity Tracking

| Component | Estimated Lines | Risk | Notes |
|-----------|----------------|------|-------|
| spec_parser.py | 200-300 | Medium | Must handle 10 different document formats |
| spec_validator.py | 100-150 | Low | Straightforward checks against ProductSpec |
| handoff_generator.py | 150-200 | Medium | Template rendering with D-doc extraction |
| prompt_generator.py | 100-150 | Low | Template + question generation |
| agent_dispatcher.py | 80-120 | Medium | Subprocess management, timeout handling |
| holdout_runner.py | 100-150 | Medium | Subprocess execution, result parsing |
| report_generator.py | 80-100 | Low | Data assembly and formatting |
| main.py | 60-80 | Low | CLI argument parsing and command routing |
| **Total source** | **870-1250** | | |
| **Total tests** | **600-900** | | 40+ test methods |

### Migration Notes

Greenfield — no migration. The orchestrator is a new tool that reads existing D-document formats.
