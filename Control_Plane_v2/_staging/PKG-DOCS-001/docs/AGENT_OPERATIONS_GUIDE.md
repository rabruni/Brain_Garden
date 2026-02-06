# Agent Operations Guide (Control Plane v2)

Operational playbook for LLM agents using the Control Plane. Follow these steps to build, install, upgrade, and operate packages; work with ledgers and tiers; and use prompt packs and modules under the governance rules.

---

## 1) Prerequisites & Environment
- Python 3.11+, repo root: `Control_Plane_v2/`.
- Auth (if enabled): `CONTROL_PLANE_TOKEN` (see `scripts/cp_init_auth.py`), optional `CONTROL_PLANE_SIGNING_KEY/VERIFY_KEY` for signed installs.
- Plan roots: default `CONTROL_PLANE` points to HO3 plane; other planes live under `planes/ho2`, `planes/ho1`.
- Keep INSTALLED immutable: only packaging/rollback scripts may write there.

## 2) Governance & Tiers (HO3/HO2/HO1)
- **HO3 (Governance / BUILDER)**: Owns frameworks, gates, package manager, governance ledger `ledger/governance.jsonl`. Writes L-INTENT, L-PACKAGE. Packages install here.
- **HO2 (Work Orders / META)**: Coordinates work; ledger at `planes/ho2/ledger/workorder.jsonl`; tracks sessions/work orders. Reads HO3; cannot change governance.
- **HO1 (Workers / FIRST)**: Executes tasks; ledgers per worker under `planes/ho1/ledger`. Reads HO2+HO3; cannot modify higher tiers.
- **Builder vs Built firewall**: BUILT artifacts cannot modify governance, install/uninstall, or write HO3 ledgers.
- **Spaces**: INSTALLED (authoritative, immutable) vs RUNTIME (mutable, non-authoritative). Promotion path: RUNTIME → package → work order → approval → install → INSTALLED.

## 3) Ledgers (Memory Model)
- All state is externalized; no hidden context.
- Paths: `ledger/governance.jsonl` (HO3), `planes/ho2/ledger/workorder.jsonl` (HO2), HO1 ledgers under `planes/ho1/ledger/`.
- Write/read via `lib/ledger_client.py`; entries include `prompts_used`, hashes; hash-chained + Merkle.
- Turn headers must declare inputs (artifact IDs, ledger refs, versions, work_order_id, turn_number).
- For session/LLM evidence, record `prompts_used` when routing via router module.

## 4) Frameworks & Spec Packs
- Registries: `registries/frameworks_registry.csv`, `registries/specs_registry.csv`, `registries/file_ownership.csv`.
- List frameworks/specs:
  ```bash
  python3 scripts/pkgutil.py compliance frameworks --json
  python3 scripts/pkgutil.py compliance specs --json
  ```
- Register (HO3 only):
  ```bash
  python3 scripts/pkgutil.py register-framework FMWK-NEW --src frameworks/FMWK-NEW_name.md
  python3 scripts/pkgutil.py register-spec SPEC-NEW --src specs/SPEC-NEW
  ```
- Specs define owned files + invariants; packages must reference a registered spec (gate G1).

## 5) Package Lifecycle (Build → Install → Upgrade → Rollback)
### Build / Validate (HO3)
```bash
# Scaffold (standard or agent)
python3 scripts/pkgutil.py init PKG-XXX --spec SPEC-XXX --output _staging/PKG-XXX
python3 scripts/pkgutil.py init-agent PKG-XXX --framework FMWK-100 --output _staging/PKG-XXX

# Validate (runs gates G0A/B, G1, G5 etc. without install)
python3 scripts/pkgutil.py preflight PKG-XXX --src _staging/PKG-XXX

# Stage archive (tar.gz into packages_store/)
python3 scripts/pkgutil.py stage PKG-XXX --src _staging/PKG-XXX
```

### Install (HO3, immutable install)
```bash
# Validate + install; receipts in installed/<pkg>/receipt.json
python3 scripts/package_install.py --archive packages_store/PKG-XXX.tar.gz --id PKG-XXX

# Dev unsigned installs
CONTROL_PLANE_ALLOW_UNSIGNED=1 python3 scripts/package_install.py --archive _staging/PKG-XXX.tar.gz --id PKG-XXX

# Dry-run / force
python3 scripts/package_install.py --archive ... --id ... --dry-run
python3 scripts/package_install.py --archive ... --id ... --force
```
Gate enforcement during install: G0A (manifest declaration), G1 (framework/spec chain), G5 (signature). Fail-closed if any gate fails.

### Upgrade
- Build a new version (bump manifest version), re-run `preflight` + `stage`, then `package_install.py` with the new archive. Old installs remain immutable.

### Remove / Rollback
- No direct uninstall (immutability). Use checkpoint/rollback:
```bash
python3 scripts/cp_version_checkpoint.py --label "pre-upgrade"
python3 scripts/cp_version_rollback.py --version-id VER-XXXX   # restores previous checkpoint
```

## 6) Gates & Integrity
- Run gates explicitly:
  ```bash
  python3 scripts/gate_check.py --all
  python3 scripts/gate_check.py --gate G0B G1 G6 --plane ho3 --enforce
  ```
- Integrity sweep:
  ```bash
  python3 scripts/integrity_check.py --json
  ```
- G0A: manifest/files declared; G0B: plane ownership; G1: framework/spec chain; G5: signature; G6: kernel parity; G2: work order (when applicable).

## 7) Prompt Packs
- Prompt pack IDs carried in routing: see `modules/router/decision.py` mapping (e.g., `PRM-ADMIN-EXPLAIN-001`, `PRM-ADMIN-GENERAL-001`).
- When invoking LLM-assisted flows, include `prompt_pack_id` in ledger entries (the router already records via `prompts_used`).
- Use `modules/router` (pipe-first) to route and log prompt usage.

## 8) Modules & Pipe-First Contract
- Modules are installed via packages; capability described in `capabilities.json` and `README` inside each module.
- Pipe-first: modules like `modules.router` and `modules.stdlib_llm` read JSON from stdin, emit JSON to stdout:
  ```bash
  echo '{"operation":"route","query":"What packages are installed?"}' | python3 -m modules.router
  ```
- Keep module IO portable by sticking to JSON pipes; avoid file side effects unless declared in spec/manifest.

## 9) Work Orders & Sessions (HO2)
- Work orders authorize cross-tier actions; HO2 ledger: `planes/ho2/ledger/workorder.jsonl`.
- When running gates with work-order context:
  ```bash
  python3 scripts/gate_check.py --gate G2 --wo WO-20260202-001 --plane ho2
  ```
- Prompt headers for every turn should declare:
  - `ledger_ids`, `artifact_ids`, `versions`, `work_order_id`, `turn_number`, `declared_inputs` (files + hashes).

## 10) Operational Cookbook (common commands)
- Inventory / provenance:
  ```bash
  python3 scripts/trace.py --inventory
  python3 scripts/trace.py --file lib/merkle.py
  ```
- List installed packages:
  ```bash
  python3 scripts/trace.py --inventory
  ```
- Compliance queries (for agents):
  ```bash
  python3 scripts/pkgutil.py compliance summary --json
  python3 scripts/pkgutil.py compliance gates
  python3 scripts/pkgutil.py compliance troubleshoot --error G1
  ```
- Plane integrity:
  ```bash
  python3 scripts/integrity_check.py --json
  ```

## 11) Safety Rails & Forbidden Actions
- HO1/HO2 must not modify frameworks, gates, registries, or install/uninstall packages.
- BUILT artifacts must not write to HO3 ledgers or mutate INSTALLED content.
- Any gate failure must halt (fail-closed); do not bypass without explicit governance approval.

## 12) Checklists
- **Before build**: Framework registered? Spec registered? Manifest has spec_id/plane_id? Tests planned?
- **Before install**: `preflight` clean; hashes up to date; signature present or unsigned flag set; checkpoint created.
- **Before executing a turn**: Declare inputs in header; read required ledger entries; ensure prompt pack ID recorded; write output to ledger.

## 13) Troubleshooting (fast paths)
- G0A/G1 failures: rerun `preflight` after updating manifest/assets; ensure spec_id exists in registries.
- Signature failures (G5): set `CONTROL_PLANE_ALLOW_UNSIGNED=1` in dev or supply verify key.
- OWN conflicts: check `registries/file_ownership.csv` for collisions.
- Router/prompt issues: verify prompt pack IDs in `modules/router/decision.py`; ensure `capabilities.json` exposes needed handlers.

---

Authoritative behavior lives in code and gates; this guide reflects current commands and paths in the Control Plane v2 repository. Always trust gate results and registry state over prose.
