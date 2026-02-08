# Technical Design

## Prompt Loader API

```python
# lib/prompt_loader.py

def load_prompt(prompt_pack_id: str, verify: bool = True) -> str:
    """Load governed prompt by ID.

    Args:
        prompt_pack_id: Prompt identifier (e.g., PRM-ADMIN-001)
        verify: Whether to verify hash (default: True)

    Returns:
        Prompt template content

    Raises:
        PromptNotFoundError: If prompt doesn't exist
        PromptHashMismatchError: If hash verification fails
    """

def verify_prompt_hash(prompt_pack_id: str, content: str) -> bool:
    """Verify prompt content matches registered hash.

    Args:
        prompt_pack_id: Prompt identifier
        content: Content to verify

    Returns:
        True if hash matches
    """

def get_prompt_hash(prompt_pack_id: str) -> str:
    """Get registered hash for prompt.

    Args:
        prompt_pack_id: Prompt identifier

    Returns:
        SHA256 hash from registry
    """

def list_prompts(status: str = "active") -> list[dict]:
    """List prompts by status.

    Args:
        status: Filter by status (active, deprecated, draft, all)

    Returns:
        List of prompt metadata dicts
    """
```

## Registry Format

```csv
prompt_id,title,framework_id,status,version,plane_id,hash,created_at
PRM-CLASSIFY-001,Query Classification,FMWK-004,active,1.0.0,ho3,sha256:...,2026-02-04T00:00:00Z
```

## Prompt File Format

```markdown
# PRM-EXAMPLE-001: Example Prompt

## Purpose
Brief description of what this prompt does.

## Input Variables
- `{variable_name}`: Description of variable

## Template

[Actual prompt template here]

## Expected Output
Description of expected LLM response.

## Constraints
- Constraint 1
- Constraint 2
```

## Error Handling

| Error | Code | Behavior |
|-------|------|----------|
| Prompt not found | PROMPT_NOT_FOUND | HARD FAIL |
| Hash mismatch | PROMPT_HASH_MISMATCH | HARD FAIL |
| Invalid ID format | INVALID_PROMPT_ID | HARD FAIL |
| Registry corrupt | REGISTRY_ERROR | HARD FAIL |
