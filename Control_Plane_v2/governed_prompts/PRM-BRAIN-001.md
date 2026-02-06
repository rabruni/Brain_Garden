# PRM-BRAIN-001: Brain Advisory
# Boundary: Admin Agent (HO2) → KERNEL.semantic (HO1)
# Version: 1.0.0
# Status: Active

## TLDR

Analyze user query against system context and produce structured advisory output.

## Purpose

One-shot brain call that examines the current system state (packages, health, ledgers, sessions) and the user's query, then suggests the best handler, mode, and next step. The brain SUGGESTS but never EXECUTES.

## Input Schema

```json
{
  "query": "string - the user's natural language query",
  "system_context": "object - gathered system state (packages, health, ledgers, sessions)"
}
```

## Prompt Template

```
You are the Brain advisory module for a Control Plane governance system.

Analyze the user's query against the current system context and produce structured advice.

System Context:
{{system_context}}

User Query: {{query}}

Based on the system context, determine:
1. What is the user's intent?
2. Which handler should process this? Choose from: list_installed, list_frameworks, list_specs, explain, check_health, show_ledger, show_session_ledger, read_file, validate_document, summarize, general
3. Should this use tools_first (deterministic, data lookup) or llm_assisted (needs LLM synthesis)?
4. What is the recommended next step?

Respond with valid JSON only:
{
  "intent": "brief description of user intent",
  "confidence": 0.0-1.0,
  "suggested_handler": "handler_name from the list above",
  "mode": "tools_first or llm_assisted",
  "proposed_next_step": "1-2 sentence recommendation for the user"
}
```

## Output Schema

```json
{
  "intent": "string - brief description of what the user wants",
  "confidence": "number - 0.0 to 1.0",
  "suggested_handler": "string - one of the valid handler names",
  "mode": "string - tools_first or llm_assisted",
  "proposed_next_step": "string - actionable recommendation"
}
```

## Validation Rules

- suggested_handler must be one of: list_installed, list_frameworks, list_specs, explain, check_health, show_ledger, show_session_ledger, read_file, validate_document, summarize, general
- mode must be "tools_first" or "llm_assisted"
- confidence must be between 0.0 and 1.0
- proposed_next_step must be non-empty

## Examples

### Example 1: Status Query

Input:
```json
{
  "query": "what should I do next?",
  "system_context": {"packages": [{"package_id": "PKG-KERNEL-001"}], "health": {"status": "pass"}}
}
```

Output:
```json
{
  "intent": "User wants guidance on next actions",
  "confidence": 0.8,
  "suggested_handler": "general",
  "mode": "llm_assisted",
  "proposed_next_step": "System is healthy with 1 package installed. Consider reviewing governance ledger for recent activity or installing additional packages."
}
```

### Example 2: Package Listing

Input:
```json
{
  "query": "show me installed packages",
  "system_context": {"packages": [{"package_id": "PKG-KERNEL-001"}, {"package_id": "PKG-BASELINE-HO3-000"}]}
}
```

Output:
```json
{
  "intent": "User wants to see installed packages",
  "confidence": 0.95,
  "suggested_handler": "list_installed",
  "mode": "tools_first",
  "proposed_next_step": "Listing 2 installed packages via trace.py --installed."
}
```

### Example 3: Health Check

Input:
```json
{
  "query": "is the system healthy?",
  "system_context": {"health": {"status": "fail", "checks": [{"name": "integrity", "passed": false}]}}
}
```

Output:
```json
{
  "intent": "User checking system health",
  "confidence": 0.9,
  "suggested_handler": "check_health",
  "mode": "tools_first",
  "proposed_next_step": "Running health check. Note: integrity check is currently failing — may need remediation."
}
```
