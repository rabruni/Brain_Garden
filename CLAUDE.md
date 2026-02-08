# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
5. **End with two tables:** a "journey" table showing how data transforms stage-by-stage, and a "effects" table listing all writes/calls.

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

**Symbol key:**
- `│ ├─ └─ ▼` — tree/flow structure
- `[file.py:LINE]` — real source location
- `📝` — file/ledger write
- `→` — subprocess, API call, or I/O
- `← LLM CALL #N` — LLM invocation (numbered)
- `┌─ ─┐ └─ ─┘` — content box showing actual data at that stage
- `✓ / ✗` — validation pass/fail

## Repository Overview

This is a dual-project monorepo containing:

1. **HRM_Test/** - Hierarchical Reasoning Model: A novel recurrent neural network for abstract reasoning tasks (ARC puzzles, Sudoku, Mazes) achieving strong results with only 27M parameters and 1000 training examples
2. **Control_Plane_v2/** - Package management and multi-tier governance infrastructure for auditable agent coordination

## HRM_Test Commands

### Dataset Building
```bash
# Build ARC dataset (requires git submodules)
git submodule update --init --recursive
python dataset/build_arc_dataset.py

# Build Sudoku dataset with augmentation
python dataset/build_sudoku_dataset.py --output-dir data/sudoku-extreme-1k-aug-1000 --subsample-size 1000 --num-aug 1000
```

### Training
```bash
# Single GPU (e.g., RTX 4070)
OMP_NUM_THREADS=8 python pretrain.py data_path=data/sudoku-extreme-1k-aug-1000 epochs=20000 global_batch_size=384

# Multi-GPU distributed training
OMP_NUM_THREADS=8 torchrun --nproc-per-node 8 pretrain.py data_path=data/arc-aug-1000
```

### Evaluation
```bash
OMP_NUM_THREADS=8 torchrun --nproc-per-node 8 evaluate.py checkpoint=<path>
```

### Visualization
Open `puzzle_visualizer.html` in browser and upload the data/ folder.

## CRITICAL: Control_Plane_v2 Governed File Rules

**NEVER directly edit files inside Control_Plane_v2/ that are governed (tracked in `registries/file_ownership.csv`).**
**NEVER write inline Python to create tar.gz files, compute hashes, or manipulate manifests.**
**NEVER run `generate_baseline_manifest.py` to fix hash mismatches from direct edits.**
Direct edits break the SHA256 hash chain, fail G0B gate checks, and require expensive manual repair.

All changes to governed files MUST go through `pkgutil` + `package_install.py`. The scripts handle
hashing, manifests, tar creation, ledger writes, and ownership — you do NOT do any of that manually.

### Complete Package Workflow (use this EVERY TIME)

All commands run from `Control_Plane_v2/` directory.

**Step 1: Register spec (if new — skip if spec already exists)**
```bash
# Create spec dir with manifest.yaml first
mkdir -p specs/SPEC-MY-001
# Write specs/SPEC-MY-001/manifest.yaml (spec_id, title, framework_id, version, status, plane_id, created_at, assets)
python3 scripts/pkgutil.py register-spec SPEC-MY-001 --src specs/SPEC-MY-001 --force
```

**Step 2: Create package skeleton**
```bash
python3 scripts/pkgutil.py init PKG-MY-001 --spec SPEC-MY-001 --output _staging/
```
This creates `_staging/PKG-MY-001/` with a manifest.json template.

**Step 3: Add/modify source files in the staging directory**
Place your changed files under `_staging/PKG-MY-001/` mirroring the target path structure.
Example: `_staging/PKG-MY-001/modules/router/prompt_router.py`

Edit the manifest.json to list assets, dependencies, etc. The `sha256` fields will be
computed automatically by `pkgutil stage`.

**Step 4: Preflight validation**
```bash
python3 scripts/pkgutil.py preflight PKG-MY-001 --src _staging/PKG-MY-001
```

**Step 5: Stage (creates tar.gz + sha256 + delta.csv)**
```bash
python3 scripts/pkgutil.py stage PKG-MY-001 --src _staging/PKG-MY-001
```
Produces `_staging/PKG-MY-001.tar.gz`.

**Step 6: Install**
```bash
python3 scripts/package_install.py --archive _staging/PKG-MY-001.tar.gz --id PKG-MY-001 --dev --force
```
`--dev` bypasses auth/signatures. `--force` allows overwriting existing files.

**Step 7: Rebuild derived registries**
```bash
python3 scripts/rebuild_derived_registries.py --plane ho3
```

**Step 8: Verify**
```bash
python3 scripts/gate_check.py --gate G0B --enforce
```

### Ownership transfers
If your package modifies files owned by another package (e.g., PKG-BASELINE-HO3-000),
declare that package as a **direct dependency** in your manifest.json `"dependencies"` array.
The rebuild script allows ownership transfer when the new owner declares the old owner as a dependency.

### Ledger consolidation
If `rebuild_derived_registries.py` doesn't see your new package (says "Found 1 packages" when
you expect 2), the install events may be in timestamped split files (`ledger/packages-YYYYMMDD-HHMMSS.jsonl`)
instead of the main `ledger/packages.jsonl`. Append them:
```bash
cat ledger/packages-<timestamp>.jsonl >> ledger/packages.jsonl
```

### Baseline regeneration (only after all packages are installed)
```bash
python3 scripts/generate_baseline_manifest.py --plane ho3 --output packages_store/PKG-BASELINE-HO3-000/ --show-hash
cp packages_store/PKG-BASELINE-HO3-000/manifest.json installed/PKG-BASELINE-HO3-000/manifest.json
python3 scripts/rebuild_derived_registries.py --plane ho3
```

## Control_Plane_v2 Commands

### Package Operations (quick reference)
```bash
python3 scripts/pkgutil.py compliance workflow    # Show full workflow
python3 scripts/pkgutil.py compliance troubleshoot --error G1  # Troubleshoot gate failures
python3 scripts/pkgutil.py register-spec SPEC-XXX --src specs/SPEC-XXX --force
python3 scripts/pkgutil.py init PKG-XXX --spec SPEC-XXX --output _staging/
python3 scripts/pkgutil.py preflight PKG-XXX --src _staging/PKG-XXX
python3 scripts/pkgutil.py stage PKG-XXX --src _staging/PKG-XXX
python3 scripts/package_install.py --archive _staging/PKG-XXX.tar.gz --id PKG-XXX --dev --force
python3 scripts/rebuild_derived_registries.py --plane ho3
python3 scripts/gate_check.py --gate G0B --enforce
python3 scripts/integrity_check.py --json
```

### Version Control
```bash
python3 scripts/cp_version_checkpoint.py --label "Production release" --token <token>
python3 scripts/cp_version_list.py
python3 scripts/cp_version_rollback.py --version-id VER-... --token <token>
```

### Testing
```bash
pytest tests/test_provenance.py
pytest tests/test_pristine.py
pytest tests/test_factory_canary.py
```

## HRM_Test Architecture

The Hierarchical Reasoning Model uses two interdependent recurrent modules:
- **H (High-level)**: Slow, abstract planning module (H_cycles iterations)
- **L (Low-level)**: Fast, detailed computation module (L_cycles iterations)

Key components in `models/`:
- `hrm/hrm_act_v1.py`: Main model with adaptive computation time (ACT) and halting Q-learning
- `layers.py`: FlashAttention, RoPE embeddings, SwiGLU, RMS normalization
- `losses.py`: Stablemax cross-entropy, ACT loss head combining LM loss with Q-halt learning
- `sparse_embedding.py`: Distributed sparse embeddings

Configuration uses Hydra/OmegaConf (`config/`). Training integrates with Weights & Biases for logging.

## Control_Plane_v2 Architecture

A minimal governance system with:
- **Tier separation**: HOT, Second Order, First Order tiers with separate codebases
- **Immutable ledger**: All operations logged for audit trail
- **Merkle verification**: Integrity checking via `lib/integrity.py` and `lib/merkle.py`
- **Role-based access**: admin, maintainer, auditor, reader roles in `lib/authz.py`
- **Pluggable auth**: passthrough (dev) or HMAC (production) via `lib/auth.py`

Key libraries in `lib/`:
- `gate_operations.py`: CRUD with authorization enforcement
- `packages.py`: Tar.gz packing with SHA256 digests
- `ledger_client.py`: Append-only event logging
- `provenance.py`: Source tracking and dependency resolution

Environment variables:
- `CONTROL_PLANE_AUTH_PROVIDER`: `passthrough` or `HMAC`
- `CONTROL_PLANE_SHARED_SECRET`: Required for HMAC auth