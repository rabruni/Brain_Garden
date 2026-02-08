# PRM-ROUTER-001: Query Router
# Boundary: Admin Agent (HO2) → KERNEL.semantic (HO1)
# Version: 2.0.0
# Status: Active

## TLDR

Classify user query and extract parameters for routing.

## Purpose

First step in query handling. Determine what the user wants and extract any artifact IDs or file paths mentioned.

## Input Schema

```json
{
  "query": "string - the user's natural language query",
  "capabilities": "string (optional) - available intent list from capability gathering"
}
```

## Prompt Template

```
Classify this Control Plane admin query.

{{capabilities}}

Query: {{query}}

What kind of request is this?
Pick the intent that best matches from the list above.

If the query mentions an artifact (FMWK-XXX, SPEC-XXX, PKG-XXX), extract it.
If the query mentions a file path, extract it.

Respond with valid JSON only:
{
  "intent": "the_intent",
  "artifact_id": "FMWK-XXX | null",
  "file_path": "path/to/file | null",
  "confidence": 0.0-1.0,
  "reasoning": "1 sentence"
}
```

## Output Schema

```json
{
  "intent": "string - one of the intent types listed",
  "artifact_id": "string | null - extracted artifact ID if present",
  "file_path": "string | null - extracted file path if present",
  "confidence": "number - 0.0 to 1.0",
  "reasoning": "string - brief explanation"
}
```

## Validation Rules

- intent must be one of the allowed values
- If intent is "explain_artifact", artifact_id should be non-null
- If intent is "read_file", file_path should be non-null
- confidence must be between 0.0 and 1.0
- reasoning must be non-empty

## Default Capabilities

When no capabilities are injected, the following intent list is used:

- list_packages: Show installed packages
- list_frameworks: Show frameworks
- list_specs: Show specifications
- explain_artifact: Explain FMWK-XXX, SPEC-XXX, or PKG-XXX
- health_check: System status or verification
- show_ledger: Governance/audit logs
- show_session: Current session info
- read_file: Read a specific file
- validate: Check compliance
- summarize: Summary or comparison
- general: Doesn't fit other categories

## Examples

### Example 1: Explain Framework

Input:
```json
{"query": "what is FMWK-000"}
```

Output:
```json
{
  "intent": "explain_artifact",
  "artifact_id": "FMWK-000",
  "file_path": null,
  "confidence": 0.95,
  "reasoning": "User asking about a specific framework by ID"
}
```

### Example 2: List Packages

Input:
```json
{"query": "show me installed packages"}
```

Output:
```json
{
  "intent": "list_packages",
  "artifact_id": null,
  "file_path": null,
  "confidence": 0.9,
  "reasoning": "Requesting inventory of installed packages"
}
```

### Example 3: Vague Query

Input:
```json
{"query": "tell me about governance"}
```

Output:
```json
{
  "intent": "general",
  "artifact_id": null,
  "file_path": null,
  "confidence": 0.6,
  "reasoning": "General question without specific artifact or action"
}
```
