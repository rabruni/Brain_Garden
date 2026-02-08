# SPEC-EVIDENCE-001: Evidence Emission Standard Library

## Summary

The Evidence Emission Standard Library (PKG-T0-EVIDENCE-001) provides foundational utilities for generating cryptographic evidence, computing hashes, and building evidence envelopes that link agent execution to the Control Plane's audit trail. This is a Tier 0 (T0) trust baseline library that all higher-tier modules depend upon for evidence generation.

## Scope

### In Scope
- SHA256 hashing of JSON objects and files
- Evidence envelope construction with required linkage fields (session_id, turn_number, work_order_id)
- Artifact reference building for ledger entries
- Pipe-first CLI interface for standalone invocation
- Deterministic serialization for reproducible hashes

### Out of Scope
- Ledger writing (handled by runtime)
- Network operations
- LLM integration
- Capability enforcement (handled by runtime)

## Success Criteria

1. Hash of identical JSON input produces identical output across invocations
2. Evidence envelope contains all required fields: session_id, turn_number, input_hash, output_hash
3. CLI reads from stdin, writes to stdout, no filesystem side effects
4. All functions are importable and documented
5. Tests achieve 100% coverage of public API

## Frameworks

This module complies with:
- FMWK-100: Agent Development Standard (Section 7: Reusable Module Standard)
- FMWK-000: Control Plane Governance Framework
