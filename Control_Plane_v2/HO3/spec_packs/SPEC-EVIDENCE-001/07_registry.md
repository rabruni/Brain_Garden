# Registry Entry

## Package Registry Entry

| Field | Value |
|-------|-------|
| id | PKG-T0-EVIDENCE-001 |
| name | Evidence Emission Standard Library |
| entity_type | package |
| spec_id | SPEC-EVIDENCE-001 |
| framework_id | FMWK-100 |
| tier | T0 |
| status | draft |
| version | 0.1.0 |
| plane_id | ho3 |

## Artifacts

| Artifact ID | Path | Type | Purpose |
|-------------|------|------|---------|
| ART-EV-001 | modules/stdlib_evidence/__init__.py | code | Public API exports |
| ART-EV-002 | modules/stdlib_evidence/hasher.py | code | SHA256 hashing utilities |
| ART-EV-003 | modules/stdlib_evidence/envelope.py | code | Evidence envelope builder |
| ART-EV-004 | modules/stdlib_evidence/reference.py | code | Artifact reference builder |
| ART-EV-005 | modules/stdlib_evidence/__main__.py | code | CLI entrypoint |
| ART-EV-006 | schemas/stdlib_evidence_request.json | schema | Input schema |
| ART-EV-007 | schemas/stdlib_evidence_response.json | schema | Output schema |
| ART-EV-008 | tests/test_stdlib_evidence.py | test | Unit tests |
| ART-EV-009 | tests/test_stdlib_evidence_pipe.py | test | Pipe-first tests |

## Dependencies

### Internal Dependencies
- None (T0 tier has no dependencies on higher tiers)

### External Dependencies
- Python 3.9+ standard library

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2026-02-03 | Initial implementation |
