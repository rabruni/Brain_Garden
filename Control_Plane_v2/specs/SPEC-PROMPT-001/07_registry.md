# Registry Entries

## Files Created

| Path | Purpose |
|------|---------|
| governed_prompts/PRM-CLASSIFY-001.md | Query classification prompt |
| governed_prompts/PRM-ADMIN-EXPLAIN-001.md | Explain artifact prompt |
| governed_prompts/PRM-ADMIN-VALIDATE-001.md | Validate document prompt |
| lib/prompt_loader.py | Prompt loading library |
| registries/prompts_registry.csv | Prompt registry |

## Registry Entries Required

### frameworks_registry.csv

```csv
FMWK-PROMPT-001,Prompt Governance,active,1.0.0,ho3,2026-02-04T00:00:00Z
```

### specs_registry.csv

```csv
SPEC-PROMPT-001,Prompt Governance Specification,FMWK-PROMPT-001,active,1.0.0,ho3,2026-02-04T00:00:00Z
```

### prompts_registry.csv

```csv
PRM-CLASSIFY-001,Query Classification,FMWK-PROMPT-001,active,1.0.0,ho3,<hash>,2026-02-04T00:00:00Z
PRM-ADMIN-EXPLAIN-001,Explain Artifact,FMWK-PROMPT-001,active,1.0.0,ho3,<hash>,2026-02-04T00:00:00Z
PRM-ADMIN-VALIDATE-001,Validate Document,FMWK-PROMPT-001,active,1.0.0,ho3,<hash>,2026-02-04T00:00:00Z
```

## governed_roots.json Update

Add `governed_prompts/` to governed roots:

```json
{
  "governed_roots": [
    ...existing...,
    "governed_prompts/"
  ]
}
```
