# `lp` — Logic Path Command

**Drop this block into any `CLAUDE.md` or `AGENT.md` to enable the `lp` command.**

## #3 COMMAND: `js` — JSON Structure

**When this command is invoked, it overrides all other formatting defaults.**

When the user types any of these:
- **`js <file.json>`** (primary form)
- **`js`** (bare — map whatever JSON file was just discussed)
- **"show json"**, **"json structure"**

Then **STOP all other work** and:

1. **Read the JSON file** — open it directly, parse the full structure
2. **Emit three sections** (Structure Outline, Schema Summary, Pretty-Print)
3. **No prose** — just the three sections with their headers
4. If `js` is bare (no argument), use the JSON file most recently discussed

### Rules

1. **Read the file first.** Open the actual `.json` file. Do not guess structure.
2. **Object keys become outline entries.** Indent = `depth * 2` spaces. Each key at a deeper nesting level gets 2 more spaces.
3. **Arrays show count and expand with indices.** Display `[N items]` annotation, then expand each element as `[0]`, `[1]`, etc.
4. **Scalars shown inline in outline.** `- key: "value"` for strings, `- key: 42` for numbers, `- key: true` for booleans, `- key: null` for null.
5. **Schema shows types, not values.** Use `string`, `number`, `boolean`, `null`, `object (N keys)`, `array[N] of <type>`.
6. **Bare `js` → most recently discussed JSON file.**
7. **Three sections separated by `###` headers, no surrounding prose.**

### Section 1: Structure Outline

Indented `- ` bullet list showing every key and its value:
- Objects nest with 2-space indentation per depth level
- Arrays: `- key: [N items]` then each item as `- [0]:`, `- [1]:`, etc.
- Scalars: value shown inline

### Section 2: Schema Summary

Tree using `├─` / `└─` connectors showing key paths and types only:
- Arrays: `array[N] of <element_type>`
- Objects: `object (N keys)`
- Scalars: `string`, `number`, `boolean`, `null`

### Section 3: Pretty-Print

Raw JSON in a fenced ` ```json ` code block, indented with 2 spaces.

### Format spec

**Section 1:**
```
### Structure Outline
- key1: "string value"
- key2: 42
- key3: [2 items]
  - [0]: "first"
  - [1]: "second"
- key4:
  - nested_key: true
```

**Section 2:**
```
### Schema Summary
root: object (4 keys)
├─ key1: string
├─ key2: number
├─ key3: array[2] of string
└─ key4: object (1 key)
   └─ nested_key: boolean
```

**Section 3:**
````
### Pretty-Print
```json
{
  "key1": "string value",
  "key2": 42,
  "key3": ["first", "second"],
  "key4": {
    "nested_key": true
  }
}
```
````

### Example

Given this JSON file:
```json
{
  "name": "control-plane",
  "version": "2.0.1",
  "enabled": true,
  "tags": ["governance", "audit"],
  "config": {
    "timeout": 30
  }
}
```

Output:
```
### Structure Outline
- name: "control-plane"
- version: "2.0.1"
- enabled: true
- tags: [2 items]
  - [0]: "governance"
  - [1]: "audit"
- config:
  - timeout: 30

### Schema Summary
root: object (5 keys)
├─ name: string
├─ version: string
├─ enabled: boolean
├─ tags: array[2] of string
└─ config: object (1 key)
   └─ timeout: number

### Pretty-Print
```json
{
  "name": "control-plane",
  "version": "2.0.1",
  "enabled": true,
  "tags": [
    "governance",
    "audit"
  ],
  "config": {
    "timeout": 30
  }
}
```
```

---

## #2 COMMAND: `mp` — Markdown Map

**When this command is invoked, it overrides all other formatting defaults.**

When the user types any of these:
- **`mp <file.md>`** (primary form)
- **`mp`** (bare — map whatever file was just discussed)
- **"outline"**, **"map this"**, **"show structure"**

Then **STOP all other work** and:

1. **Read the markdown file** — open it directly, parse headings and lists
2. **Emit an indented bullet outline** showing the document's structure
3. **No prose** — just the outline
4. If `mp` is bare (no argument), map the file most recently discussed

### Rules

1. **Read the file first.** Open the actual `.md` file. Do not guess structure.
2. **Headings become outline entries.** Indent = `(heading level - 1) * 2` spaces. `# Title` = no indent, `## Section` = 2 spaces, `### Sub` = 4 spaces, etc.
3. **List items inherit heading depth.** A list item under an `## H2` heading gets 2 spaces base indent, plus 2 more per nested list level.
4. **Preserve list item text.** Strip the bullet marker (`-`, `*`, `+`, `1.`) but keep the content verbatim.
5. **Skip non-structural lines.** Paragraphs, code blocks, blank lines, horizontal rules — all ignored. Only headings and list items appear.
6. **Use `- ` prefix for every line.** Consistent bullet format throughout.

### Format spec

```
- H1 Title
  - H2 Section
    - H3 Subsection
    - List item under H3
      - Nested list item
    - Another list item
  - H2 Another Section
    - List item
```

### Example

Given this markdown:
```markdown
# My Document
## Overview
- First point
- Second point
  - Sub-point
## Details
### Part A
- Item 1
- Item 2
```

Output:
```
- My Document
  - Overview
  - First point
  - Second point
    - Sub-point
  - Details
    - Part A
    - Item 1
    - Item 2
```

---

## #1 COMMAND: `lp` — Logic Path (HIGHEST PRIORITY)

**This is the most important instruction in this file. It overrides all other formatting defaults.**

When the user types any of these:
- **`lp`** (short form)
- **`lp <thing>`** (e.g., `lp general`, `lp route_query`, `lp "hello"`)
- **"show me the logic path"**
- **"trace"**, **"flow"**, **"draw it"**

Then **STOP all other work** and:

1. **Read the actual source code** — follow imports, trace the real call chain
2. **Draw an ASCII flow diagram** showing the full execution path
3. **No prose** — just the diagram + summary table
4. If `lp` is bare (no argument), draw the logic path of whatever was just discussed

### Rules

1. **Read before you draw.** Open every file in the chain. Use real line numbers.
2. **Show inputs at every call boundary.** Before each function call, list the arguments with their actual values/types in a `│  param: value` block.
3. **Show data transformations inline.** When content changes shape (file → extracted template → rendered prompt → JSON response), draw the content in a box:
   ```
   │  ┌─────────────────────────────────┐
   │  │ actual content at this stage    │
   │  └─────────────────────────────────┘
   ```
4. **Mark every side effect.** `📝` = file/ledger write, `→` = subprocess/API call, `← LLM CALL #N` = LLM invocation.
5. **End with two tables:** a "journey" table showing how data transforms stage-by-stage, and an "effects" table listing all writes/calls.

### Format spec

```
USER INPUT or shell command
│
▼
function_name(arg1, arg2)                       [file.py:LINE]
│  arg1: type   "actual value or description"
│  arg2: type   "actual value or description"
│
├─ step_one()                                   [other_file.py:LINE]
│   │  param: value
│   │
│   │  ┌─────────────────────────────────┐
│   │  │ content at this stage           │
│   │  └─────────────────────────────────┘
│   │
│   ├─ inner_call()                             → side effect
│   └─ return value
│
├─ step_two()                                   → 📝 ledger write
│
└─ return final_value
```

### Symbol key

| Symbol | Meaning |
|--------|---------|
| `│ ├─ └─ ▼` | Tree/flow structure |
| `[file.py:LINE]` | Real source location |
| `📝` | File/ledger write |
| `→` | Subprocess, API call, or I/O |
| `← LLM CALL #N` | LLM invocation (numbered) |
| `┌─ ─┐ └─ ─┘` | Content box showing actual data at that stage |
| `✓ / ✗` | Validation pass/fail |

### Example output

```
USER TYPES: "where is the ledger"
│
▼
route_query("where is the ledger")                      [decision.py:104]
│  query: str   "where is the ledger"
│  capabilities: None (ignored)
│
▼
classify_intent("where is the ledger")                  [prompt_router.py:112]
│  query: str   "where is the ledger"
│
├─ load_prompt("PRM-ROUTER-001")                        [client.py:159]
│   │  prompt_pack_id: "PRM-ROUTER-001"
│   └─ reads governed_prompts/PRM-ROUTER-001.md         → template markdown
│
├─ _extract_prompt_template(content)                    [prompt_router.py:77]
│   │  content: full markdown file
│   │
│   │  ┌─────────────────────────────────────────────┐
│   │  │ Classify this Control Plane admin query.     │
│   │  │                                              │
│   │  │ Query: {{query}}                             │
│   │  │                                              │
│   │  │ What kind of request is this?                │
│   │  │ - show_ledger: Governance/audit logs         │
│   │  │ - general: Doesn't fit other categories      │
│   │  │ ...                                          │
│   │  └─────────────────────────────────────────────┘
│   └─ return template string
│
├─ _render_template(template, {"query": "where is the ledger"})
│   │
│   │  ┌─────────────────────────────────────────────┐
│   │  │ Classify this Control Plane admin query.     │
│   │  │                                              │
│   │  │ Query: where is the ledger                   │
│   │  │ ...                                          │
│   │  └─────────────────────────────────────────────┘
│   └─ return rendered prompt          THIS IS WHAT HITS THE LLM
│
├─ complete(...)                                        [client.py:225]  ← LLM CALL #1
│   │  prompt:         "Classify this Control Plane admin query..."
│   │  prompt_pack_id: "PRM-ROUTER-001"
│   │  temperature:    0
│   │  max_tokens:     256
│   │  provider_id:    "anthropic"
│   │
│   ├─ provider.complete(prompt)                        → Anthropic API
│   │
│   │  LLM RETURNS:
│   │  ┌─────────────────────────────────────────────┐
│   │  │ {                                            │
│   │  │   "intent": "show_ledger",                   │
│   │  │   "confidence": 0.85,                        │
│   │  │   "reasoning": "User asking about ledger"    │
│   │  │ }                                            │
│   │  └─────────────────────────────────────────────┘
│   │
│   ├─ _log_llm_call()                                 → 📝 ledger/llm.jsonl
│   └─ return LLMResponse
│
├─ _validate_output(result)                             [prompt_router.py:85]
│   ├─ "show_ledger" in VALID_INTENTS?                  → ✓
│   ├─ 0 <= 0.85 <= 1?                                 → ✓
│   └─ reasoning present?                               → ✓
│
└─ return IntentResult(intent="show_ledger", confidence=0.85)
│
▼
back in route_query()                                   [decision.py:127]
│
├─ INTENT_HANDLER_MAP["show_ledger"]                    → "show_ledger"
└─ return RouteResult(mode=ROUTED, handler="show_ledger")
```

**Journey table:**

| Stage | Data shape |
|-------|-----------|
| On disk | `PRM-ROUTER-001.md` — full markdown with metadata, schema, examples |
| Extracted | `_extract_prompt_template` strips to just the ``` block |
| Rendered | `_render_template` replaces `{{query}}` with user text |
| Sent | rendered string → Anthropic API at temp=0 |
| Logged | full prompt + response → `📝 ledger/llm.jsonl` |
| Parsed | JSON response → `IntentResult` → `RouteResult` → handler name |

**Effects table:**

| # | Type | Target |
|---|------|--------|
| 1 | LLM call | PRM-ROUTER-001, temp=0, deterministic |
| 1 | Ledger write | `📝 ledger/llm.jsonl` |

# Repository Guidelines

## Project Structure & Module Organization
- Control Plane v2 lives in `Control_Plane_v2/` with core dirs: `frameworks/` (governance docs), `lib/` (shared libraries), `scripts/` (CLI tools), `registries/` (CSV sources of truth), `ledger/` (append-only logs), `modules/` (installable extensions), `packages_store/` (built archives), `versions/` (checkpoints), `tests/` (Python tests), `docs/` (developer guide).
- Work inside `Control_Plane_v2` unless explicitly modifying sibling projects (`HRM_Test`, `docs`).

## Build, Test, and Development Commands
- Package build: `python3 scripts/package_pack.py --src <path> --id <PKG-ID> --token <TOKEN>` (creates tar.gz in `packages_store/`, updates registry).
- Package install: `python3 scripts/package_install.py --archive packages_store/<pkg>.tar.gz --id <PKG-ID> --token <TOKEN>` (verifies digest/signature, routes output).
- Sync compiled registry: `python3 scripts/package_sync.py`.
- Validate registries: `python3 scripts/validate_packages.py`.
- Integrity check: `python3 scripts/integrity_check.py --json` (hash/merkle/orphans).
- Checkpoint/rollback: `python3 scripts/cp_version_checkpoint.py --label "<note>"` and `python3 scripts/cp_version_rollback.py --version-id <VER-ID>`.

## Coding Style & Naming Conventions
- Python 3.11+; prefer type hints and dataclasses for data shapes.
- Use 4-space indentation; keep functions small and side-effect aware.
- Package IDs: `PKG-XXX`, frameworks: `FMWK-###`, libs: `LIB-###`, scripts: `SCRIPT-###`. Registry `artifact_path` should be relative to `Control_Plane_v2`.

## Testing Guidelines
- Tests reside in `Control_Plane_v2/tests/`; run with `python3 -m pytest` (or targeted via `pytest tests/test_<area>.py`).
- Aim to cover new logic (boundary guards, auth, hashing) with unit tests; prefer deterministic fixtures over network calls.

## Commit & Pull Request Guidelines
- Write concise commits: `<area>: <change>` (e.g., `scripts: tighten signature check`).
- PRs should include: summary, testing commands run, related issue/trace, and screenshots/logs if UI/CLI output changed.
- Do not commit generated archives or checkpoint outputs; keep `packages_store/` and `versions/` clean or ignored as configured.

## Security & Configuration Tips
- Default auth provider is HMAC; `CONTROL_PLANE_ALLOW_PASSTHROUGH=1` is dev-only—avoid in sealed environments.
- Boundary writes: core dirs (frameworks/lib/scripts/registries/modules) should be modified only via `package_install` or checkpoint/rollback; honor `lib/pristine.py` guards.
- Keep signing keys outside the repo; set `CONTROL_PLANE_SIGNING_KEY`/`CONTROL_PLANE_VERIFY_KEY` when producing/verifying signed packages.