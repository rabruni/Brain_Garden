# D10: Agent Context — Dark Factory Orchestrator

**Component:** Dark Factory Orchestrator
**Package:** PKG-DARK-FACTORY-001
**Updated:** 2026-02-22

---

## What This Project Does

The Dark Factory is an automated pipeline that reads D1-D10 product spec documents, validates them for completeness, generates builder handoff documents and agent prompts, dispatches Claude Code builder agents, runs holdout scenarios against delivered code, and produces traceability reports. It turns a complete spec into verified, delivered software — without human intervention in the build loop.

## Architecture Overview

```
CLI (main.py)
│
├── validate ──▶ SpecParser ──▶ SpecValidator ──▶ ValidationResult (JSON)
│
├── generate ──▶ SpecParser ──▶ HandoffGenerator ──▶ Handoff .md files + index
│
├── prompts  ──▶ HandoffGenerator output ──▶ PromptGenerator ──▶ Prompt + Expected Answers
│
├── holdout  ──▶ SpecParser ──▶ HoldoutRunner ──▶ HoldoutResults (JSON)
│
└── run      ──▶ All of the above ──▶ AgentDispatcher ──▶ ReportGenerator ──▶ FactoryReport
```

```
factory/                  — All source modules (spec_parser, validator, generators, dispatcher, runner, report)
tests/                    — pytest unit + integration tests
templates/                — Handoff and prompt markdown templates
_design/docs/templates/   — D1-D10 spec directories consumed as input
```

## Key Patterns

- **Validate Before Generate:** The pipeline refuses to generate handoffs or dispatch agents if spec validation fails. This is non-negotiable (D1 Article 5).
- **Holdout Isolation:** D9 holdout content NEVER appears in generated handoffs or prompts. The builder agent must not see holdout scenarios before completing work (D1 Article 2).
- **Deterministic Output:** Same spec input → same output files. No randomness, no LLM calls during generation. Only the dispatch phase involves LLM (via Claude Code subprocess).
- **Traceability Everywhere:** Every handoff traces to D2 scenarios + D4 contracts + D8 task ID. Every holdout result traces to the responsible D8 task. Every dispatch is logged to the ledger.
- **Heading-Based Parsing:** D-documents are parsed by splitting on markdown headings and extracting structured fields via regex. No full markdown AST library needed.

## Commands

```bash
# Validate a spec directory
python3 -m factory validate --spec-dir _design/docs/templates/test

# Generate handoff documents
python3 -m factory generate --spec-dir _design/docs/templates/test --output-dir /tmp/factory_out

# Generate agent prompts (requires handoffs already generated)
python3 -m factory prompts --handoffs-dir /tmp/factory_out --spec-dir _design/docs/templates/test

# Run holdout scenarios against installed code
python3 -m factory holdout --spec-dir _design/docs/templates/test --install-root /tmp/factory_out

# Full pipeline (validate + generate + prompts + dispatch + holdout + report)
python3 -m factory run --spec-dir _design/docs/templates/test --output-dir /tmp/factory_out

# Run unit tests
python3 -m pytest tests/ -v

# Run a single test file
python3 -m pytest tests/test_spec_parser.py -v

# Run full regression
python3 -m pytest tests/ -v --tb=short
```

## Tool Rules

| USE THIS | NOT THIS | WHY |
|----------|----------|-----|
| SpecParser.parse() | Manual file reads + regex | Centralized parsing with error handling |
| SpecValidator.validate() | Ad-hoc checks | All validation rules in one place |
| HandoffGenerator.generate() | Manual markdown assembly | Template-driven, traceable, D9-excluded |
| subprocess.run() for Claude Code | Anthropic SDK directly | D5 RQ-002 decision — subprocess dispatch |
| argparse (main.py) | sys.argv parsing | Standard CLI, subcommand support |
| json.dumps() for reports | Print statements | Machine-readable, parseable output |
| pathlib.Path | os.path string manipulation | Cleaner path handling, cross-platform |

## Coding Conventions

- Python 3.10+ with stdlib only (no external dependencies for MVP)
- Type hints on all public functions and dataclass fields
- Dataclasses for all entities (D3 E-001 through E-007) — no raw dicts
- Functions return explicit result objects, never raise to caller for expected failures
- Exit codes: 0 = success, 1 = validation/generation failure, 2 = usage error
- Tests use pytest with tmp_path fixtures for filesystem isolation

## Submission Protocol

1. Answer 13 questions (10 verification + 3 adversarial). STOP. Wait for approval.
2. Build via DTT: per-behavior red-green-refactor cycles.
3. Write RESULTS file with SHA256 hashes, test counts, baseline snapshot.
4. Run full regression. Report new failures.

```
Branch:  factory/T-NNN-component-name
Commit:  "T-NNN: <one-line summary>"
Results: PKG-DARK-FACTORY-001/RESULTS_T-NNN.md
```

## Active Components (what you'll interact with)

| Component | Where | Interface |
|-----------|-------|-----------|
| SpecParser | factory/spec_parser.py | parse(spec_dir) → ProductSpec |
| SpecValidator | factory/spec_validator.py | validate(spec) → ValidationResult |
| HandoffGenerator | factory/handoff_generator.py | generate(spec, output_dir) → list[Handoff] |
| PromptGenerator | factory/prompt_generator.py | generate_prompts(handoffs, spec, output_dir) → list[AgentPrompt] |
| AgentDispatcher | factory/agent_dispatcher.py | dispatch(prompt, workdir) → DispatchRecord |
| HoldoutRunner | factory/holdout_runner.py | run_holdouts(spec, install_root) → list[HoldoutResult] |
| ReportGenerator | factory/report_generator.py | generate_report(validation, dispatches, holdouts) → FactoryReport |

## Links to Deeper Docs

- D1 Constitution: Immutable rules — holdout isolation, validate-before-dispatch, no silent failures
- D2 Specification: All 10 scenarios (SC-001 through SC-010) with GIVEN/WHEN/THEN
- D3 Data Model: 7 entities (ProductSpec, ValidationResult, Handoff, AgentPrompt, DispatchRecord, HoldoutResult, FactoryReport)
- D4 Contracts: 5 inbound, 5 outbound, 2 side-effect, 4 error contracts
- D7 Plan: Full architecture, file structure, testing strategy, complexity estimates
- D8 Tasks: 7 tasks across 4 phases with dependency graph
- BUILDER_HANDOFF_STANDARD.md: 10-section format for generated handoffs
- BUILDER_PROMPT_CONTRACT.md: Agent prompt template with 13-question gate
