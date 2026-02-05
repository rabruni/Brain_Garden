# PRM-CLASSIFY-001: Query Classification

## Purpose

Classify user queries to determine the appropriate handling mode:
- TOOLS_FIRST: Deterministic pattern match
- LLM_ASSISTED: Requires LLM synthesis

## Input Variables

- `{query}`: The user's query text
- `{available_handlers}`: List of available handler types

## Template

You are a query classifier for the Control Plane admin system.

Given a user query, determine the best handler type.

Query: {query}

Available handlers:
{available_handlers}

Respond with JSON:
```json
{{
  "classification": "<handler_type>",
  "confidence": <0.0-1.0>,
  "reasoning": "<brief explanation>"
}}
```

Classification rules:
1. Use "list" for queries about installed packages, frameworks, or inventories
2. Use "explain" for queries about specific artifacts (FMWK-*, SPEC-*, PKG-*, files)
3. Use "status" for health checks or system status queries
4. Use "synthesize" for queries requiring multiple data sources combined
5. Use "validate" for document validation requests

## Expected Output

JSON object with:
- classification: Handler type string
- confidence: Float between 0.0 and 1.0
- reasoning: Brief explanation

## Constraints

- Always return valid JSON
- Confidence should reflect certainty
- Default to TOOLS_FIRST patterns when possible
