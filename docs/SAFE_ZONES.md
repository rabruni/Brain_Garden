# Safe Work Zones (Outside Control Plane Governance)

These directories are **OUTSIDE** the Control Plane governance system.
Agents can freely write here without creating orphans or violating governance.

---

## Safe Zones (WRITE FREELY)

```
playground/
├── docs/                          # ← SAFE: Notes, plans, documentation drafts
│   ├── plans/                     #    Implementation plans, architecture docs
│   ├── notes/                     #    Working notes, research, ideas
│   ├── sprints/                   #    Sprint logs, task tracking
│   └── SAFE_ZONES.md              #    This file
│
├── _external_quarantine/          # ← SAFE: Imported files, external code
│   └── YYYYMMDD-HHMMSS/           #    Timestamped imports
│
├── Control_Plane_v2/
│   ├── _staging/                  # ← SAFE: Package development area
│   │   └── PKG-XXX/               #    Build packages here before install
│   │
│   └── tmp/                       # ← SAFE: Temporary files
│
├── AGENTS.md                      # ← SAFE: Agent instructions
├── CLAUDE.md                      # ← SAFE: Claude Code instructions
└── GEMINI.md                      # ← SAFE: Gemini instructions
```

---

## What Goes Where

| Content Type | Location | Notes |
|--------------|----------|-------|
| Implementation plans | `docs/plans/` | Before coding starts |
| Working notes | `docs/notes/` | Research, ideas, scratchpad |
| Sprint logs | `docs/sprints/` | Task lists, progress tracking |
| External imports | `_external_quarantine/` | Code from outside the repo |
| Package development | `Control_Plane_v2/_staging/` | Building packages before install |
| Temporary files | `Control_Plane_v2/tmp/` | Auto-cleaned |

---

## DANGER ZONES (Do NOT Write Directly)

These are **INSIDE** Control Plane governance. Direct writes create orphans.

```
Control_Plane_v2/
├── lib/           # ← GOVERNED: Only via package install
├── modules/       # ← GOVERNED: Only via package install
├── scripts/       # ← GOVERNED: Only via package install
├── frameworks/    # ← GOVERNED: Only via package install
├── specs/         # ← GOVERNED: Only via package install
├── registries/    # ← DERIVED: Only via rebuild script
├── schemas/       # ← GOVERNED: Only via package install
├── tests/         # ← GOVERNED: Only via package install
├── docs/          # ← GOVERNED: Only via package install (NOTE: different from playground/docs/)
├── gates/         # ← GOVERNED: Only via package install
├── installed/     # ← FORBIDDEN: Package manager only
├── config/        # ← FORBIDDEN: System only
└── ledger/        # ← APPEND-ONLY: Via ledger scripts only
```

---

## Current Sprint Notes

When working on a sprint, create a file in `docs/sprints/`:

```
docs/sprints/
└── 2026-02-04_shell_implementation.md
```

---

## After Sprint Completes

When ready to enforce governance:

1. Run orphan check:
   ```bash
   cd Control_Plane_v2
   python3 scripts/agent_check.py --orphans
   ```

2. Review remediation plan:
   ```bash
   python3 scripts/remediate_orphans.py --plan
   ```

3. Package and install orphans
4. Update AGENTS.md with strict enforcement rules

---

## Saved Enforcement Rules

The strict AGENTS.md rules are saved and ready to apply after current sprints complete.
They enforce the "Build Outside, Install Inside" principle.

Location of enforcement tools:
- `Control_Plane_v2/scripts/agent_check.py` - Pre-write validation
- `Control_Plane_v2/scripts/remediate_orphans.py` - Orphan cleanup
