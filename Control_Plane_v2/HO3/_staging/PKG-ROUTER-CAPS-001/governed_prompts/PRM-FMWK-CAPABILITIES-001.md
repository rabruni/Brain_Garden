# PRM-FMWK-CAPABILITIES-001: Framework Capability Extraction
# Boundary: Admin Agent (HO2) → KERNEL.semantic (HO1)
# Version: 1.0.0
# Status: Active

## TLDR

Extract queryable capabilities from framework registry metadata.

## Purpose

Pre-router step: read framework definitions and return a structured
capabilities manifest that the router prompt can use as intent labels.

## Input Schema

```json
{
  "frameworks_registry": "string - CSV content of frameworks_registry.csv"
}
```

## Prompt Template

```
You are analyzing a Control Plane's framework registry to extract queryable capabilities.

Framework Registry:
{{frameworks_registry}}

For each framework, identify what types of user queries it can handle.
Return a JSON array of intent objects. Each intent should map to one type
of user question the system can answer.

Required intents (these always exist):
- list_packages, list_frameworks, list_specs, explain_artifact,
  health_check, show_ledger, show_session, read_file, validate,
  summarize, general

You may add additional intents if frameworks suggest them.

Respond with valid JSON only:
{
  "intents": [
    {
      "id": "intent_name",
      "handler": "handler_function_name",
      "description": "1 sentence",
      "framework": "FMWK-XXX"
    }
  ]
}
```

## Output Schema

```json
{
  "intents": [
    {
      "id": "string",
      "handler": "string",
      "description": "string",
      "framework": "string"
    }
  ]
}
```

## Validation Rules

- intents array must be non-empty
- Each intent must have id, handler, description, framework
- Must include all required intents (listed above)
