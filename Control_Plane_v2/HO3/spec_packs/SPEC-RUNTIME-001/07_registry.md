# Registry Entry

## Package Registry Entry

| Field | Value |
|-------|-------|
| id | PKG-T1-RUNTIME-001 |
| name | Agent Runtime Module |
| entity_type | package |
| spec_id | SPEC-RUNTIME-001 |
| framework_id | FMWK-100 |
| tier | T1 |
| status | draft |
| version | 0.1.0 |
| plane_id | ho3 |

## Artifacts

| Artifact ID | Path | Type | Purpose |
|-------------|------|------|---------|
| ART-RT-001 | modules/agent_runtime/__init__.py | code | Public API exports |
| ART-RT-002 | modules/agent_runtime/runner.py | code | AgentRunner class |
| ART-RT-003 | modules/agent_runtime/capability.py | code | CapabilityEnforcer class |
| ART-RT-004 | modules/agent_runtime/session.py | code | Session management |
| ART-RT-005 | modules/agent_runtime/sandbox.py | code | TurnSandbox context manager |
| ART-RT-006 | modules/agent_runtime/prompt_builder.py | code | Prompt header construction |
| ART-RT-007 | modules/agent_runtime/memory.py | code | Ledger replay utilities |
| ART-RT-008 | modules/agent_runtime/ledger_writer.py | code | Dual ledger writer |
| ART-RT-009 | modules/agent_runtime/exceptions.py | code | Custom exceptions |
| ART-RT-010 | modules/agent_runtime/README.md | doc | Module documentation |
| ART-RT-011 | tests/test_agent_runtime.py | test | Unit tests |
| ART-RT-012 | tests/test_sandbox_failclosed.py | test | Sandbox enforcement tests |

## Dependencies

### Internal Dependencies
- PKG-T0-EVIDENCE-001 (evidence emission)
- PKG-KERNEL-001 (ledger_client, merkle)

### External Dependencies
- Python 3.9+ standard library

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2026-02-03 | Initial implementation |
