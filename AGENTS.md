# Repository Guidelines

## Project Structure & Module Organization
- Control Plane v2 lives in `Control_Plane_v2/` with core dirs: `frameworks/` (governance docs), `lib/` (shared libraries), `scripts/` (CLI tools), `registries/` (CSV sources of truth), `ledger/` (append-only logs), `modules/` (installable extensions), `packages_store/` (built archives), `versions/` (checkpoints), `tests/` (Python tests), `docs/` (developer guide).
- Work inside `Control_Plane_v2` unless explicitly modifying sibling projects (`HRM_Test`, `docs`).

## Build, Test, and Development Commands
- Package build: `python3 scripts/package_pack.py --src <path> --id <PKG-ID> --token <TOKEN>` (creates tar.gz in `packages_store/`, updates registry).
- Package install: `python3 scripts/package_install.py --archive packages_store/<pkg>.tar.gz --id <PKG-ID> --token <TOKEN>` (verifies digest/signature, routes output).
- Sync compiled registry: `python3 scripts/package_sync.py`.
- Validate registries: `python3 scripts/validate_packages.py`.
- Integrity check: `python3 scripts/integrity_check.py --json` (hash/merkle/orphans).
- Checkpoint/rollback: `python3 scripts/cp_version_checkpoint.py --label "<note>"` and `python3 scripts/cp_version_rollback.py --version-id <VER-ID>`.

## Coding Style & Naming Conventions
- Python 3.11+; prefer type hints and dataclasses for data shapes.
- Use 4-space indentation; keep functions small and side-effect aware.
- Package IDs: `PKG-XXX`, frameworks: `FMWK-###`, libs: `LIB-###`, scripts: `SCRIPT-###`. Registry `artifact_path` should be relative to `Control_Plane_v2`.

## Testing Guidelines
- Tests reside in `Control_Plane_v2/tests/`; run with `python3 -m pytest` (or targeted via `pytest tests/test_<area>.py`).
- Aim to cover new logic (boundary guards, auth, hashing) with unit tests; prefer deterministic fixtures over network calls.

## Commit & Pull Request Guidelines
- Write concise commits: `<area>: <change>` (e.g., `scripts: tighten signature check`).
- PRs should include: summary, testing commands run, related issue/trace, and screenshots/logs if UI/CLI output changed.
- Do not commit generated archives or checkpoint outputs; keep `packages_store/` and `versions/` clean or ignored as configured.

## Security & Configuration Tips
- Default auth provider is HMAC; `CONTROL_PLANE_ALLOW_PASSTHROUGH=1` is dev-only—avoid in sealed environments.
- Boundary writes: core dirs (frameworks/lib/scripts/registries/modules) should be modified only via `package_install` or checkpoint/rollback; honor `lib/pristine.py` guards.
- Keep signing keys outside the repo; set `CONTROL_PLANE_SIGNING_KEY`/`CONTROL_PLANE_VERIFY_KEY` when producing/verifying signed packages.
