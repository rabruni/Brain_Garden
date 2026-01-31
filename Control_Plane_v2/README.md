Minimal Control Plane v2 – package management + integrity only.

## What’s here
- Package manager (pack/install/sync/validate) with audit logging
- Integrity check (registry ↔ filesystem hashes, Merkle root)
- AuthN/Z (passthrough or HMAC token)
- Lightweight version checkpoints/rollbacks

## Build a package
1) Place the artifact under Control_Plane_v2 (e.g., `frameworks/FMWK-100_agent_development_standard.md`).
2) Run  
   `python3 scripts/package_pack.py --src frameworks/FMWK-100_agent_development_standard.md --id PKG-FMWK-100 --frameworks-active FMWK-107 --session S1 --work-order WO1 --actor you --token <token>`
   - Produces `packages_store/<name>.tar.gz` (+ .sha256)
   - Updates `packages_registry.csv` (source, source_type=tar, digest, output_type/path)
   - Logs a `package_pack` event to the ledger with hashes and context.

## Install a package
`python3 scripts/package_install.py --archive packages_store/<name>.tar.gz --id PKG-... --frameworks-active FMWK-107 --session S1 --work-order WO1 --actor you --token <token>`
- Verifies digest (from packages_registry when --id is provided).
- Routing via `output_type`:
  - `extension` → Control_Plane root (default)
  - `module` → `modules/`
  - `external` → absolute `output_path`; not added to the registry/integrity, but fully logged to ledger (path + hash).
- Logs `package_install` to ledger with before/after hashes and context.

## Output routing fields (packages_registry.csv)
- `output_type`: extension | module | external
- `output_path`: required for external (absolute/env-expanded); optional for others.
- External deliveries are ledger-only; internal installs remain governed by the Control Plane (tracked in registries, verified by integrity checks).

## Auth
- Token via `--token` or `CONTROL_PLANE_TOKEN`.
- Providers: `CONTROL_PLANE_AUTH_PROVIDER=passthrough|hmac` (set `CONTROL_PLANE_SHARED_SECRET` for hmac).

## Integrity & checkpoints
- Check: `python3 scripts/integrity_check.py --json`
- Version checkpoint: `python3 scripts/cp_version_checkpoint.py --label "<note>" --token <token>`
- Rollback: `python3 scripts/cp_version_rollback.py --version-id VER-... --token <token>`
- List checkpoints: `python3 scripts/cp_version_list.py`

## Changing configs / new packages
- Update `packages_registry.csv` with new rows (id, source, digest, output_type/output_path, deps, status).
- For internal artifacts, ensure paths stay under the Control Plane root so integrity covers them.
- Rebuild manifest and rerun integrity after registry changes.

## Informing another agent (short checklist)
- To build: run `package_pack.py` with --id and context; ensure registry row exists; note output_type/path.
- To install: run `package_install.py` with --id (for digest check), routing applied automatically; external installs are ledger-only.
- Always rerun `integrity_check.py --json`; keep token/auth settings configured.
