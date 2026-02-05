# SPEC-PROMPT-001: Prompt Governance Specification

## Overview

This specification defines the governance system for LLM prompts in the Control Plane.
It ensures all prompts are registered, versioned, and auditable.

## Key Artifacts

| Artifact | Purpose |
|----------|---------|
| prompts_registry.csv | Registry of all governed prompts |
| governed_prompts/*.md | Prompt template files |
| lib/prompt_loader.py | Prompt loading with hash verification |

## Dependencies

- FMWK-PROMPT-001: Governing framework
- FMWK-000: Control Plane Governance

## Status

- **Version**: 1.0.0
- **Status**: Active
- **Created**: 2026-02-04
