# Rollout Plan

## Phase 1: Infrastructure

1. Create governed_prompts/ directory
2. Add to governed_roots.json
3. Create prompts_registry.csv
4. Implement lib/prompt_loader.py

## Phase 2: Initial Prompts

1. Create PRM-CLASSIFY-001 (query classification)
2. Create PRM-ADMIN-EXPLAIN-001 (explain artifacts)
3. Create PRM-ADMIN-VALIDATE-001 (validate documents)
4. Register all in prompts_registry.csv

## Phase 3: Integration

1. Update stdlib_llm to use prompt_loader
2. Update admin_agent to use governed prompts
3. Update router to reference governed prompts

## Phase 4: Enforcement

1. Enable hash verification by default
2. Reject ungoverned prompts
3. Monitor for violations

## Rollback Plan

1. Set PROMPT_VERIFY=false to disable verification
2. Fall back to inline prompts if registry corrupt
3. Keep previous prompt versions available

## Success Criteria

- All LLM calls use prompt_pack_id
- No raw prompts in evidence logs
- Hash verification catches modifications
- All prompts pass registry validation
