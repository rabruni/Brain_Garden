# Problem Statement

## Challenge

LLM-assisted agents need prompts to guide their behavior. Without governance:

1. **No Audit Trail**: Cannot track which prompts produced which outputs
2. **Version Drift**: Prompt changes are untracked
3. **Security Risk**: Ungoverned prompts may contain or leak secrets
4. **No Review**: Prompts bypass approval workflows

## Requirements

1. All prompts must be registered before use
2. Prompt content must be hash-verified
3. Prompt usage must be logged by ID (not raw content)
4. Changes must create new versions

## Impact

Without prompt governance:
- Cannot reproduce agent behavior
- Cannot audit LLM interactions
- Risk of prompt injection via unverified templates
- No change management for agent behavior
