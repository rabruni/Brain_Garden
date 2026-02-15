# FMWK-011: Prompt Contracts

## Purpose

Define the governance standard for prompt contracts -- the versioned, schema-validated specifications for every LLM exchange in the system. Prompt contracts are the IPC protocol between HO2 (caller) and HO1 (executor). Without contracts, HO1 receives unstructured strings and returns unstructured strings. With contracts, every LLM exchange is versioned, schema-validated, and auditable.

This framework formalizes Invariant #4 from v2 Section 10 (Architectural Invariants): "Communication is contractual. Versioned prompt contracts with JSON schemas. Every exchange recorded."

## Scope

### What FMWK-011 Governs

- Contract identity (ID format, versioning rules)
- Contract schema (required fields, boundary constraints)
- Input/output schema conventions (what goes in, what comes out)
- Required context specification (what HO2's attention function must assemble before the contract fires)
- Dual validation protocol (syntactic first, semantic second, both must pass)
- Contract loading and resolution rules (how HO1 finds and loads the right contract)
- Contract lifecycle (versioning, deprecation, migration)

### What FMWK-011 Does NOT Govern

- **Work order schema or lifecycle** -- FMWK-008 (Work Order Protocol). Work orders are the dispatch unit; contracts are the execution specification.
- **Tier boundary enforcement** -- FMWK-009 (Tier Boundary). If FMWK-011 discovers a gap in tier rules, it flags the gap and defers to FMWK-009.
- **Cognitive stack instantiation** -- FMWK-010 (Cognitive Stack). How per-agent-class stacks are created with shared code and isolated state.
- **Specific contract instances** -- Individual contract JSON files (e.g., `classify.json`, `synthesize.json`) ship with their consuming packages (e.g., PKG-HO1-EXECUTOR-001 via HANDOFF-14). FMWK-011 defines the rules; packages provide the instances.
- **The runtime contract loader** -- The code that loads and resolves contracts at runtime belongs to the HO1 Executor (PKG-HO1-EXECUTOR-001, HANDOFF-14). FMWK-011 defines the loading rules; the package implements them.

### Design Authority

Every claim in this framework traces to a specific section of `_staging/architecture/KERNEL_PHASE_2_v2.md` (Feb 14). Section references use the format `v2 Section N (Title)`.

---

## 1. Contract Identity

### ID Format

Every prompt contract has a unique `contract_id` that conforms to the pattern defined in `prompt_contract.schema.json`:

```
Pattern: ^PRC-[A-Z]+-[0-9]+$
```

Examples:
- `PRC-CLASSIFY-001` -- classification contract
- `PRC-SYNTHESIZE-001` -- synthesis/response generation contract
- `PRC-RETRIEVE-001` -- retrieval compression contract
- `PRC-AUDIT-001` -- admin audit formatting contract

The prefix `PRC` distinguishes prompt contracts from other governed artifacts (WO- for work orders, PRM- for prompt packs, FMWK- for frameworks).

The middle segment is an uppercase alphabetic descriptor of the contract's function. The trailing segment is a zero-padded numeric sequence within that descriptor namespace.

### Version Format

Every contract carries a semantic version:

```
Pattern: ^\d+\.\d+\.\d+$
```

Examples: `1.0.0`, `1.1.0`, `2.0.0`

Version semantics follow standard semver. See Section 9 (Versioning and Lifecycle) for rules on what constitutes major, minor, and patch changes.

### Relationship to Prompt Packs

Each contract references a `prompt_pack_id` (pattern: `^PRM-[A-Z]+-[0-9]+$`). The prompt pack contains the actual prompt template text. The contract binds to the pack and adds schema, boundary, and validation constraints around it. One prompt pack may be referenced by multiple contract versions.

**Source**: v2 Section 12 (Design Principles From CS Kernel Theory) -- "All tier-to-tier communication uses versioned prompt contracts with JSON schemas."

---

## 2. Contract Schema

The authoritative contract schema is defined in:

```
_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/prompt_contract.schema.json
```

This framework references that schema. It does NOT redefine it. The schema is the single source of truth for structural validation. This section explains each field's role in the system.

### Required Fields

The schema declares four required fields:

| Field | Type | Pattern | Role |
|-------|------|---------|------|
| `contract_id` | string | `^PRC-[A-Z]+-[0-9]+$` | Unique identifier. Used by HO1 to locate and load the contract. Referenced in work orders via `constraints.prompt_contract_id` (FMWK-008). |
| `version` | string | `^\d+\.\d+\.\d+$` | Semantic version. Enables multiple versions of a contract to coexist. HO1 loads the version specified in the work order or resolves to latest. |
| `prompt_pack_id` | string | `^PRM-[A-Z]+-[0-9]+$` | Governed prompt pack this contract binds to. The pack contains the prompt template; the contract wraps it with schemas and constraints. |
| `boundary` | object | -- | Execution boundary. Contains the LLM call parameters (max_tokens, temperature, optional provider_id, optional structured_output). See Section 3. |

### Optional Fields

| Field | Type | Role |
|-------|------|------|
| `agent_class` | string, enum | Which agent class this contract is designed for: `KERNEL.syntactic`, `KERNEL.semantic`, `ADMIN`, or `RESIDENT`. Scopes the contract to a cognitive stack. **Source**: v2 Section 4 (Agent Classes). |
| `tier` | string, enum | Which tier this contract executes at: `hot`, `ho2`, or `ho1`. In the current architecture, contracts execute at `ho1` (Kitchener Step 3). **Source**: v2 Section 2 (The Three-Tier Cognitive Hierarchy). |
| `required_context` | object | Context that HO2's attention function must assemble before dispatching the work order that uses this contract. See Section 6. |
| `input_schema` | object | JSON Schema for template variables injected into the prompt. See Section 4. |
| `output_schema` | object | JSON Schema for expected response structure. See Section 5. |
| `metadata` | object | Additional contract metadata. Open-ended (`additionalProperties: true`). Used for tagging, categorization, or package-specific annotations. |

### Top-Level Schema Policy

The schema itself has `"additionalProperties": true` at the top level. This allows contract instances to carry additional fields beyond what the schema defines, without breaking validation. This is intentional -- it permits forward-compatible extensions.

**Source**: v2 Section 10 (Architectural Invariants), Invariant #4 -- "Communication is contractual. Versioned prompt contracts with JSON schemas."

---

## 3. Boundary Constraints

The `boundary` object defines the execution envelope for the LLM call. It is the only required non-identity field in the contract.

### Required Boundary Fields

| Field | Type | Constraints | Role |
|-------|------|-------------|------|
| `max_tokens` | integer | min: 1, max: 100000 | Token limit for this prompt's response. The LLM Gateway enforces this limit. The Token Budgeter (KERNEL.syntactic) tracks consumption against the work order's budget. |
| `temperature` | number | min: 0, max: 2 | Sampling temperature. Deterministic contracts (classification, validation) use 0. Creative contracts may use higher values. |

### Optional Boundary Fields

| Field | Type | Role |
|-------|------|------|
| `provider_id` | string | Required LLM provider, if the contract is provider-specific. When absent, the LLM Gateway uses its configured default provider. When present, the Gateway routes to this specific provider. |
| `structured_output` | object | JSON Schema the LLM response must conform to. Passed to the provider as a structured output constraint (provider-dependent). This is distinct from `output_schema` -- `structured_output` is a provider-level instruction to the LLM, while `output_schema` is a post-hoc validation schema applied by the system. |

### Boundary and Budget Interaction

The contract's `boundary.max_tokens` defines the maximum for a single LLM call. The work order's `constraints.token_budget` (FMWK-008) defines the budget for the entire work order, which may include multiple LLM calls in a multi-round tool loop. The relationship:

```
boundary.max_tokens <= constraints.token_budget (per WO)
constraints.token_budget <= session budget remaining
```

Budget enforcement is not FMWK-011's responsibility. The Token Budgeter (KERNEL.syntactic) and HO2 cognitive process enforce budgets. FMWK-011 defines the boundary that feeds into that enforcement.

**Source**: v2 Section 10 (Architectural Invariants), Invariant #5 -- "Budgets are enforced, not advisory."
**Source**: v2 Section 8 (Infrastructure Components) -- Token Budgeter as KERNEL.syntactic component.

---

## 4. Input Schema

The `input_schema` field is an optional JSON Schema that defines the template variables injected into the prompt at execution time.

### Purpose

When HO1 loads a contract and its associated prompt pack, the prompt template contains variable placeholders. The `input_schema` declares what those variables are, their types, and which are required. HO2's attention function assembles the context; the `input_schema` validates that the assembled context contains everything the prompt needs.

### Example

For a classification contract:

```json
{
  "input_schema": {
    "type": "object",
    "required": ["user_input"],
    "properties": {
      "user_input": {
        "type": "string",
        "description": "Raw user utterance to classify"
      },
      "session_history": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Recent conversation turns for context"
      }
    }
  }
}
```

### Validation

Input schema validation is syntactic (KERNEL.syntactic). Before the LLM call fires, the assembled template variables are validated against `input_schema`. If validation fails, the work order fails with a schema error -- no LLM call is made.

This is the first half of the dual validation protocol applied to inputs: cheap, deterministic, pre-flight.

### Relationship to PromptRequest

The `PromptRequest` dataclass (in `prompt_router.py`) carries:
- `template_variables: Optional[dict[str, Any]]` -- the actual values injected
- `input_schema: Optional[dict[str, Any]]` -- the schema to validate them against

Both fields link the runtime request to the contract's input specification.

**Source**: v2 Section 1 (Grounding Model: The Kitchener Orchestration Stack) -- Step 3: "HO1 loads a prompt contract, makes the LLM call through a deterministic gateway, and returns the result."

---

## 5. Output Schema

The `output_schema` field is an optional JSON Schema that defines the expected structure of the LLM's response.

### Purpose

After the LLM responds, the system validates the response against `output_schema`. This is the syntactic half of the dual validation protocol (Section 7). It checks structure, not content. Content quality is HO2's responsibility at Kitchener Step 4 (Verification).

### additionalProperties Policy

**Default: `additionalProperties: true`.** Contracts are permissive by default. The output schema validates that required keys exist and have correct types. Auxiliary information the LLM returns passes through unblocked.

**Strict mode: `additionalProperties: false`.** Contracts that need exact output structure (e.g., classification with a fixed set of fields) opt in to strict mode by setting `additionalProperties: false` in their `output_schema`. This is a per-contract decision, not a framework-level default.

**Rationale**: Over-specifying blocks useful exploratory results. Under-specifying means no validation is possible. The default permissive policy balances structure with flexibility. Strict mode is available when the contract author knows the exact output shape.

### Example (Permissive)

```json
{
  "output_schema": {
    "type": "object",
    "required": ["speech_act", "ambiguity"],
    "properties": {
      "speech_act": {
        "type": "string",
        "enum": ["greeting", "question", "command", "reentry_greeting", "farewell"]
      },
      "ambiguity": {
        "type": "string",
        "enum": ["low", "medium", "high"]
      }
    },
    "additionalProperties": true
  }
}
```

The LLM must return `speech_act` and `ambiguity` with correct types. If it also returns `confidence: 0.92` or `search: "enable"`, those pass through.

### Example (Strict)

```json
{
  "output_schema": {
    "type": "object",
    "required": ["speech_act", "ambiguity"],
    "properties": {
      "speech_act": { "type": "string" },
      "ambiguity": { "type": "string" }
    },
    "additionalProperties": false
  }
}
```

Only `speech_act` and `ambiguity` are allowed. Any extra fields cause validation failure.

### Relationship to structured_output

`output_schema` and `boundary.structured_output` serve different purposes:

| Field | When Applied | What It Does | Who Enforces |
|-------|-------------|-------------|--------------|
| `boundary.structured_output` | Before the LLM call | Instructs the LLM provider to constrain its output format | LLM provider (provider-dependent) |
| `output_schema` | After the LLM call | Validates the response structure | KERNEL.syntactic (deterministic) |

When both are present, `structured_output` helps the LLM produce conformant output, and `output_schema` verifies it did. They are complementary, not redundant.

**Source**: v2 Section 10 (Architectural Invariants), Invariant #6 -- "Validation is structural. KERNEL.syntactic validates schemas. Prompt contracts validate input/output."
**Source**: v2 Section 13 (Prior Art Patterns) -- "Dual validation (syntactic -> semantic)."

---

## 6. Required Context

The `required_context` field declares what HO2's attention function must assemble before the work order that uses this contract is dispatched.

### Design Principle

Contracts don't own context. Contracts declare what they need; HO2 assembles it. The contract's `required_context` is a specification for attention, not an instruction to HO1. By the time HO1 receives the work order, the context has already been assembled and placed in `input_context.assembled_context` (FMWK-008).

**Source**: v2 Section 7 (Attention -- HO2's Retrieval Function) -- "Attention is NOT a standalone service. It is what the HO2 cognitive process does to prepare HO1's context."

### Sub-Fields

#### `ledger_queries` (array of objects)

Each entry specifies a ledger query that must be executed before the contract fires:

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | Ledger event type to query (e.g., `LLM_CALL`, `WO_COMPLETED`, `GATE_FAILED`) |
| `tier` | string, enum: `hot`, `ho2`, `ho1` | Which tier's ledger to query |
| `max_entries` | integer, min: 1 | Maximum number of entries to retrieve |
| `recency` | string | Duration window: `"1h"`, `"24h"`, `"session"` |

These map to HO2's retrieval operations: horizontal scan (HO2m) and priority probe (HO3m). The contract declares what it needs; HO2 decides how to retrieve it.

#### `framework_refs` (array of strings)

Pattern: `^FMWK-[A-Z0-9-]+$`

Framework definitions that must be in context when the prompt fires. For example, a governance audit contract might require FMWK-002 (Ledger Protocol) definitions to be loaded.

#### `file_refs` (array of strings)

File paths that must be read into context. Used for contracts that need specific configuration files, schema definitions, or reference documents.

### Context Budget and Truncation

If assembled context exceeds the token budget for the work order, HO2 applies truncation per v2 Section 7 (Attention):

- **Truncation priority**: frameworks > conversation history > metadata
- **Fail-closed default**: when in doubt, include rather than exclude. Missing context causes worse failures than excess context.

Context budget enforcement is HO2's responsibility, not the contract's. The contract declares needs; HO2 manages the budget.

**Source**: v2 Section 7 (Attention -- HO2's Retrieval Function) -- context budget and truncation rules.

---

## 7. Dual Validation Protocol

Every contract-bound LLM exchange undergoes two validation stages. Both must pass.

### The Sequence

```
Step 1: Syntactic Validation (KERNEL.syntactic)
  - Deterministic, zero-cost
  - Validates response against output_schema using JSON Schema
  - Checks: Is it valid JSON? Are required keys present? Are types correct?
  - Result: pass or fail with specific schema errors

      |
      | (only if syntactic passes)
      v

Step 2: Semantic Validation (HO2 cognitive process)
  - Expensive, requires cognitive judgment
  - HO2's Step 4 (Verification) in the Kitchener loop
  - Checks: Does the content meet the acceptance criteria from Step 2 (Scoping)?
  - Result: accept, retry (new WO with tighter constraints), or escalate
```

### Why This Order

1. **Syntactic check is free.** It runs deterministic code -- no LLM call, no token cost, sub-millisecond. Running it first prevents wasting tokens on semantic evaluation of structurally broken output.

2. **Semantic check is expensive.** It requires HO2 cognitive processing, potentially an LLM call. Only worth doing if the structure is already valid.

3. **Both must pass.** A structurally valid but semantically wrong answer fails at Step 2. A semantically good answer in the wrong format fails at Step 1. Neither alone is sufficient.

### Syntactic Validation Details

Syntactic validation is performed by KERNEL.syntactic (the Schema Validator component from v2 Section 8, Infrastructure Components). The current implementation in `prompt_router.py` (`_validate_output` method) performs basic required-field checking. The full implementation validates against the complete `output_schema` JSON Schema.

Validation occurs:
- **Input side**: `input_schema` validated against `template_variables` before the LLM call
- **Output side**: `output_schema` validated against the LLM response after the call

Both are syntactic (KERNEL.syntactic). Both are pre-conditions for semantic evaluation.

### Semantic Validation Details

Semantic validation is HO2's Step 4 (Verification) in the Kitchener loop. It is NOT part of FMWK-011's implementation -- it is part of the HO2 cognitive process (FMWK-010, PKG-HO2-SUPERVISOR-001). FMWK-011 defines the protocol; HO2 executes the semantic half.

HO2's verification checks:
- Does the output address the original intent from Step 2 (Scoping)?
- Are the acceptance criteria met?
- Is the content factually consistent with the assembled context?

If semantic validation fails, HO2 may retry (create a new work order with tighter constraints) or escalate (log a governance event).

### Applicability Beyond Prompt Contracts

The dual validation pattern is reusable across the system. v2 Section 13 (Prior Art Patterns) states: "Reusable pattern: cheap/deterministic check first, expensive/LLM check second, both must pass. Applies to gate checks, signal detection, content validation." FMWK-011 is the canonical instance of this pattern for prompt I/O.

**Source**: v2 Section 13 (Prior Art Patterns) -- "Dual validation (syntactic -> semantic)."
**Source**: v2 Section 10 (Architectural Invariants), Invariant #6 -- "Validation is structural."
**Source**: v2 Section 1 (Grounding Model) -- Step 4: Verification.

---

## 8. Contract Loading and Resolution

This section defines how HO1 finds, loads, and validates a contract at execution time.

### Resolution Flow

```
1. HO2 creates work order with constraints.prompt_contract_id = "PRC-CLASSIFY-001"
   (FMWK-008, Section 4: Work Order Schema)

2. HO2 dispatches WO to HO1 cognitive process

3. HO1 receives WO, reads constraints.prompt_contract_id

4. HO1 resolves contract_id to a file path:
   - Look up contract_id in the contract registry (governed file)
   - Registry maps contract_id + version -> file path

5. HO1 loads the contract JSON file

6. HO1 validates the loaded contract against prompt_contract.schema.json
   (KERNEL.syntactic: Schema Validator)
   - If validation fails: WO fails with "contract_schema_invalid"

7. HO1 loads the referenced prompt_pack_id
   - Resolves prompt pack to template file
   - If prompt pack not found: WO fails with "prompt_pack_not_found"

8. HO1 validates input_context against contract's input_schema (if defined)
   - If validation fails: WO fails with "input_schema_invalid"

9. HO1 injects template_variables into prompt template

10. HO1 constructs PromptRequest with contract fields:
    - contract_id, prompt_pack_id from contract identity
    - max_tokens, temperature, provider_id, structured_output from boundary
    - input_schema, output_schema from contract
    - work_order_id, session_id, agent_id, agent_class, tier from WO context

11. HO1 sends PromptRequest through LLM Gateway
    (v2 Section 10, Invariant #1: No direct LLM calls)

12. HO1 receives response, validates against output_schema (syntactic)

13. HO1 returns result to HO2 for semantic validation (Step 4)
```

### Contract Registry

Contracts are stored as governed JSON files. A contract registry (governed file, append-only updates) maps `contract_id` to file locations. The registry format is defined by the consuming package (PKG-HO1-EXECUTOR-001), not by this framework. FMWK-011 requires only that:

1. The registry exists as a governed file
2. Lookups are by `contract_id` (and optionally `version`)
3. The loaded JSON is validated against `prompt_contract.schema.json` before use

### Version Resolution

When a work order specifies only `contract_id` without a version:
- HO1 resolves to the **latest non-deprecated version** of that contract
- This is the default behavior for forward compatibility

When a work order specifies `contract_id` with a pinned version (via contract registry or WO metadata):
- HO1 loads that exact version
- If the version is deprecated, HO1 logs a warning but proceeds
- If the version does not exist, the WO fails with "contract_version_not_found"

### Failure Modes

| Failure | Error Code | Terminal? |
|---------|-----------|-----------|
| contract_id not in registry | `contract_not_found` | YES -- WO fails |
| Contract JSON invalid against schema | `contract_schema_invalid` | YES -- WO fails |
| Prompt pack not found | `prompt_pack_not_found` | YES -- WO fails |
| Input validation fails | `input_schema_invalid` | YES -- WO fails |
| Output validation fails (syntactic) | `output_schema_invalid` | NO -- reported to HO2 for retry decision |

All failures are logged to HO1m. Output validation failure is non-terminal because HO2 may choose to accept a partially valid response or retry.

**Source**: v2 Section 1 (Grounding Model) -- Step 3: "HO1 loads a prompt contract, makes the LLM call through a deterministic gateway, and returns the result."
**Source**: v2 Section 10 (Architectural Invariants), Invariant #1 -- "No direct LLM calls. Every LLM call flows through the LLM Gateway."
**Source**: v2 Section 5 (The Visibility / Syscall Model) -- HO1 calls HOT infrastructure as syscalls.

---

## 9. Versioning and Lifecycle

### Semantic Versioning Rules

Contracts follow semver (`MAJOR.MINOR.PATCH`):

| Change Type | Version Bump | Examples |
|-------------|-------------|----------|
| **MAJOR** | Breaking change to input_schema or output_schema required fields. Removing a required field. Changing a field's type. | `1.0.0` -> `2.0.0` |
| **MINOR** | Adding optional fields to input_schema or output_schema. Adding new enum values. Relaxing constraints (e.g., increasing max_tokens). | `1.0.0` -> `1.1.0` |
| **PATCH** | Documentation fixes. Metadata changes. prompt_pack_id update (same interface, improved prompt text). | `1.0.0` -> `1.0.1` |

### Compatibility Rules

- **Minor versions MUST NOT break consumers.** A work order built for contract `PRC-CLASSIFY-001` v1.0.0 must work with v1.1.0. New optional fields are added; existing fields are unchanged.
- **Major versions MAY break consumers.** A major version bump signals that work orders referencing the old version must be updated. Both versions coexist during migration.
- **Patch versions are transparent.** No consumer-visible change.

### Deprecation Protocol

1. A contract version is marked deprecated in the contract registry with a `deprecated_at` timestamp and a `successor_version` reference.
2. HO1 logs a warning when loading a deprecated contract but proceeds with execution.
3. Deprecated contracts remain loadable for a migration period (defined per contract, default: 30 days or until the next major release).
4. After the migration period, deprecated contracts are removed from the registry. Attempts to load them fail with `contract_version_not_found`.

### Lifecycle States

```
draft -> active -> deprecated -> removed
```

| State | Meaning |
|-------|---------|
| `draft` | Under development. Not yet available for production work orders. |
| `active` | Available for use. The current version. |
| `deprecated` | Superseded by a newer version. Still loadable. Warning logged on use. |
| `removed` | No longer loadable. Registry entry removed. |

### Immutability Rule

Once a contract version is `active`, its schema fields (contract_id, version, boundary, input_schema, output_schema, required_context) are immutable. To change any of these fields, create a new version. This preserves auditability -- every LLM exchange can be traced to the exact contract version that governed it.

**Source**: v2 Section 6 (Memory Architecture) -- "Append-only. No mutation. No deletion. History preserved."
**Source**: v2 Section 12 (Design Principles From CS Kernel Theory) -- IPC = schema-enforced message passing. Versioned contracts enable controlled evolution.

---

## 10. Implementation Mapping

### Consuming Packages

| Package | What It Implements | Relationship to FMWK-011 |
|---------|--------------------|--------------------------|
| **PKG-PHASE2-SCHEMAS-001** | `prompt_contract.schema.json` | Provides the authoritative contract schema. FMWK-011 references this schema. |
| **PKG-PROMPT-ROUTER-001** | `prompt_router.py` (LLM Gateway) | Routes contract-bound LLM calls. `PromptRequest` carries contract fields (`contract_id`, `prompt_pack_id`, `input_schema`, `output_schema`, boundary fields). |
| **PKG-WORK-ORDER-001** (HANDOFF-13) | `work_order.py` | Work orders reference contracts via `constraints.prompt_contract_id`. FMWK-008 governs the WO; FMWK-011 governs the contract it points to. |
| **PKG-HO1-EXECUTOR-001** (HANDOFF-14) | `ho1_executor.py` | The HO1 cognitive process that loads contracts, resolves prompt packs, validates I/O, and dispatches through the LLM Gateway. Primary consumer of FMWK-011. |
| **PKG-HO2-SUPERVISOR-001** (HANDOFF-15) | `ho2_supervisor.py` | The HO2 cognitive process that creates work orders referencing contracts, assembles context per `required_context`, and performs semantic validation (Step 4). |

### PromptRequest Field Mapping

The `PromptRequest` dataclass in `prompt_router.py` maps to contract fields as follows:

| PromptRequest Field | Contract Source | Notes |
|---------------------|----------------|-------|
| `contract_id` | `contract_id` | Direct mapping |
| `prompt_pack_id` | `prompt_pack_id` | Direct mapping |
| `agent_class` | `agent_class` | From contract or WO context |
| `tier` | `tier` | From contract or WO context |
| `max_tokens` | `boundary.max_tokens` | Direct mapping |
| `temperature` | `boundary.temperature` | Direct mapping |
| `provider_id` | `boundary.provider_id` | Optional; Gateway default if absent |
| `structured_output` | `boundary.structured_output` | Optional; passed to provider |
| `input_schema` | `input_schema` | For pre-flight validation |
| `output_schema` | `output_schema` | For post-response validation |
| `template_variables` | -- | Assembled by HO2 attention, validated against `input_schema` |
| `work_order_id` | -- | From the dispatching work order (FMWK-008) |
| `session_id` | -- | From session context |
| `agent_id` | -- | From the cognitive stack identity (FMWK-010) |
| `framework_id` | -- | FMWK-011 |

### Implementation Sequence

```
FMWK-011 (this document -- governance rules)
  |
  v
PKG-WORK-ORDER-001 (HANDOFF-13) -- WOs reference contracts via prompt_contract_id
  |
  v
PKG-HO1-EXECUTOR-001 (HANDOFF-14) -- HO1 loads and executes contracts
PKG-HO2-SUPERVISOR-001 (HANDOFF-15) -- HO2 creates WOs, assembles context, verifies
  |
  v
Session Host v2 (HANDOFF-16) -- Kitchener loop replaces flat loop
```

**Source**: v2 Section 18 (Critical Path -- What's Next) -- build sequence from frameworks through packages.
**Source**: v2 Section 1 (Grounding Model) -- the canonical dispatch loop that contracts enable.

---

## Conformance

- **Schema authority**: `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/prompt_contract.schema.json`
- **Reference implementation**: `HOT/kernel/prompt_router.py` (PKG-PROMPT-ROUTER-001) -- current LLM Gateway with contract field support
- **Governing invariants**: v2 Section 10 (Architectural Invariants), #1 (no direct LLM calls), #4 (contractual communication), #6 (structural validation)
- **Related frameworks**:
  - FMWK-008 (Work Order Protocol) -- WOs reference contracts via `constraints.prompt_contract_id`
  - FMWK-009 (Tier Boundary) -- tier enforcement rules that contracts respect
  - FMWK-010 (Cognitive Stack) -- per-agent-class instantiation that scopes contract usage

## Status

- **Version**: 1.0.0
- **State**: draft
- **Owner**: ray
- **Created**: 2026-02-14
