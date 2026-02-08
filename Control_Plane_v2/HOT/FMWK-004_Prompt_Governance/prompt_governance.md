# FMWK-PROMPT-001: Prompt Governance Framework

## Purpose

Govern prompt templates used by LLM-assisted agents in the Control Plane.
This framework ensures all LLM interactions use approved, auditable prompts.

## Scope

- All prompt templates used for LLM completions
- Prompt versioning and change tracking
- Hash verification for prompt integrity

## Core Principles

1. **Governed by Default**: All prompts MUST be registered before use
2. **Immutable Once Registered**: Prompt changes create new versions
3. **Auditable**: All prompt usage is logged with prompt_pack_id
4. **Fail-Closed**: Ungoverned prompts result in HARD FAIL

## Invariants

| ID | Invariant |
|----|-----------|
| I-PRM-1 | All prompts MUST be registered in prompts_registry.csv |
| I-PRM-2 | Prompt files MUST have SHA256 hash recorded on registration |
| I-PRM-3 | Prompts MUST be reviewed and approved before use |
| I-PRM-4 | Prompt changes MUST update hash and version |
| I-PRM-5 | Prompt content MUST NOT contain raw secrets |

## Prompt ID Format

```
PRM-<DOMAIN>-<SEQ>
```

Examples:
- `PRM-ADMIN-001` - Admin agent prompt
- `PRM-CLASSIFY-001` - Query classification prompt
- `PRM-VALIDATE-001` - Validation prompt

## Registry Schema

The prompts registry (`registries/prompts_registry.csv`) has these columns:

| Column | Type | Description |
|--------|------|-------------|
| prompt_id | string | Unique prompt identifier |
| title | string | Human-readable title |
| framework_id | string | Governing framework |
| status | enum | active, deprecated, draft |
| version | semver | Prompt version |
| plane_id | string | Owning plane |
| hash | string | SHA256 of prompt content |
| created_at | ISO8601 | Creation timestamp |

## Prompt File Format

Prompts are stored as Markdown files in `governed_prompts/`:

```
governed_prompts/
├── PRM-CLASSIFY-001.md
├── PRM-ADMIN-EXPLAIN-001.md
└── PRM-ADMIN-VALIDATE-001.md
```

### Template Variables

Prompts use Python `.format()` style placeholders:

```markdown
# Task

Explain the artifact: {artifact_id}

## Context

{context}
```

### Sections

Each prompt file SHOULD include:

1. **Purpose** - What the prompt is for
2. **Input Variables** - Expected template variables
3. **Expected Output** - What the LLM should produce
4. **Constraints** - Behavioral constraints

## Lifecycle

1. **Draft**: New prompt under development
2. **Active**: Approved for production use
3. **Deprecated**: Superseded, migration required

## Change Process

1. Create new prompt file with incremented version
2. Update prompts_registry.csv with new hash
3. Submit for review
4. Upon approval, set status to active
5. Mark old version as deprecated

## Security Considerations

- Never include raw secrets in prompts
- Use placeholders for dynamic content
- Validate template variable sources
- Log prompt_pack_id, never raw prompt content

## Related Artifacts

- SPEC-PROMPT-001: Prompt Governance Specification
- lib/prompt_loader.py: Prompt loading and verification
- modules/stdlib_llm: LLM client requiring governed prompts

## Governance

- **Owner**: Control Plane Maintainers
- **Approvers**: Admin role required
- **Review Frequency**: Per-change
