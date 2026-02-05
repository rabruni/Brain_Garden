# Solution Design

## Architecture

```
┌─────────────────────────────────────────────────┐
│                 Agent Runtime                    │
├─────────────────────────────────────────────────┤
│ modules/stdlib_llm                              │
│   complete(prompt, prompt_pack_id="PRM-...")    │
├─────────────────────────────────────────────────┤
│ lib/prompt_loader.py                            │
│   load_prompt("PRM-...")                        │
│   verify_prompt_hash()                          │
├─────────────────────────────────────────────────┤
│ governed_prompts/                               │
│   PRM-CLASSIFY-001.md                          │
│   PRM-ADMIN-EXPLAIN-001.md                     │
├─────────────────────────────────────────────────┤
│ registries/prompts_registry.csv                 │
│   prompt_id, hash, status, version              │
└─────────────────────────────────────────────────┘
```

## Key Components

### 1. Prompts Registry

CSV file tracking all governed prompts:
- prompt_id: Unique identifier
- hash: SHA256 of content
- status: active/deprecated/draft
- version: Semantic version

### 2. Prompt Loader

Python module providing:
- `load_prompt(prompt_pack_id)`: Load and verify prompt
- `verify_prompt_hash(prompt_pack_id, content)`: Check hash
- `list_prompts()`: List available prompts

### 3. Governed Prompts Directory

Markdown files in `governed_prompts/`:
- Named by prompt_pack_id
- Contains template with placeholders
- Includes metadata and documentation

## Integration Points

- **stdlib_llm**: Requires prompt_pack_id for completions
- **Evidence System**: Logs prompt_pack_id and prompt_hash
- **Admin Agent**: Uses governed prompts for LLM-assisted queries
