# TODO: Admin Plane OS-Level Separation

**Created**: 2026-02-04
**Context**: Discussion on ADMIN role and crosscutting agents
**Related**: CP-FIREWALL-001 v1.1.0 (Section 11)

---

## Summary

ADMIN agents (Managers) should be fully isolated at the OS level, not just application level. This includes separating both data and code.

## Proposed Structure

```
/opt/control_plane/              # Owner: cp_service:cp_group (750)
├── ledger/                      # HO3 governance
├── installed/                   # Packages
└── planes/
    ├── ho1/                     # Residents
    └── ho2/                     # Work orders

/opt/control_plane_admin/        # Owner: cp_admin:cp_admin (700)
├── ho1/                         # Admin execution ledger
│   └── ledger/
├── ho2/                         # Admin session ledger
│   └── ledger/
├── ho3/                         # Admin learning ledger
│   └── ledger/
├── scripts/                     # Admin scripts (chat.py, etc.)
├── lib/                         # Admin libraries
└── modules/
    └── admin_agent/             # Admin agent module

/opt/control_plane_observe/      # Owner: cp_observe:cp_observe (750)
├── ho1_observe.jsonl            # L-OBSERVE from HO1
├── ho2_observe.jsonl            # L-OBSERVE from HO2
└── ho3_observe.jsonl            # L-OBSERVE from HO3
```

## Tasks

- [ ] Create CP-DEPLOY-001 document with OS-level separation guidelines
- [ ] Define environment variables for configurable paths
  - `CONTROL_PLANE_ROOT`
  - `ADMIN_PLANE_ROOT`
  - `OBSERVE_PLANE_ROOT`
- [ ] Update admin_agent module to use configurable root
- [ ] Update chat.py to respect ADMIN_PLANE_ROOT
- [ ] Create deployment scripts for OS-level setup
- [ ] Document user/group requirements (cp_service, cp_admin, cp_observe)

## Security Benefits

| Protection Layer | Without Separation | With Separation |
|-----------------|-------------------|-----------------|
| Application (G-FIREWALL) | Enforced | Enforced |
| OS file permissions | Same user | Different user |
| Container isolation | Same container | Can be different |
| Backup/audit | Mixed | Separate |
| Compromise blast radius | Full access | Limited |

## Notes

- Admin scripts and libraries should be in the admin directory for full isolation
- This is defense-in-depth: even if application layer is bypassed, OS layer protects
- Future: could be separate containers or even separate machines
