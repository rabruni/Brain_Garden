# Registry Entry

## Package Registry Entry

| Field | Value |
|-------|-------|
| id | PKG-T3-ADMIN-001 |
| name | Admin Agent |
| entity_type | package |
| spec_id | SPEC-ADMIN-001 |
| framework_id | FMWK-100 |
| tier | T3 |
| status | draft |
| version | 0.1.0 |
| plane_id | ho1 |

## Artifacts

| Artifact ID | Path | Type | Purpose |
|-------------|------|------|---------|
| ART-ADM-001 | modules/admin_agent/__init__.py | code | Public API exports |
| ART-ADM-002 | modules/admin_agent/agent.py | code | AdminAgent class |
| ART-ADM-003 | modules/admin_agent/capabilities.json | config | Capability declarations |
| ART-ADM-004 | modules/admin_agent/README.md | doc | Module documentation |
| ART-ADM-005 | tests/test_admin_agent.py | test | Unit tests |

## Dependencies

### Internal Dependencies
- PKG-T1-RUNTIME-001 (agent runtime)
- PKG-T0-EVIDENCE-001 (evidence emission)
- PKG-KERNEL-001 (trace.py, ledger_client)

### External Dependencies
- Python 3.9+ standard library

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2026-02-03 | Initial implementation (read-only) |
