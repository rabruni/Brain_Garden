# Commit Information

## Spec ID
SPEC-PROMPT-001

## Title
Prompt Governance Specification

## Summary
Defines the governance system for LLM prompts including registry, loader, and verification.

## Files Changed

### Created
- frameworks/FMWK-PROMPT-001_prompt_governance.md
- specs/SPEC-PROMPT-001/*.md (8 files)
- governed_prompts/PRM-CLASSIFY-001.md
- governed_prompts/PRM-ADMIN-EXPLAIN-001.md
- governed_prompts/PRM-ADMIN-VALIDATE-001.md
- lib/prompt_loader.py
- registries/prompts_registry.csv
- tests/test_prompt_loader.py

### Modified
- registries/frameworks_registry.csv
- registries/specs_registry.csv
- config/governed_roots.json

## Dependencies
- FMWK-000: Control Plane Governance
- stdlib_llm: LLM client

## Testing
```bash
pytest tests/test_prompt_loader.py -v
```

## Approval
- [ ] Framework reviewed
- [ ] Spec reviewed
- [ ] Tests pass
- [ ] Integration verified
