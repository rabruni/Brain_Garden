# Control Plane v2 Developer Guide (Packages + Auth + Integrity)

## Scope
- Minimal nucleus: package build/install, registry + ledger integrity, basic AuthN/AuthZ.
- No agents/modules shipped in v2.

## Key Paths
- Package store (staging): `packages_store/`
- Registries: `registries/` (`control_plane_registry.csv`, `packages_registry.csv`)
- Scripts: `scripts/` (`package_pack.py`, `package_install.py`, `package_sync.py`, `validate_packages.py`, `integrity_check.py`)
- Libraries: `lib/` (`packages.py`, `auth.py`, `authz.py`, `gate_operations.py`, etc.)

## Authentication & Authorization

### Authentication Setup (External Secrets)

Control Plane uses HMAC authentication by default (fail-closed). Secrets are stored
OUTSIDE the plane root to preserve the invariant: "nothing unaccounted-for inside governed roots".

**First-Time Setup:**

1. Initialize external secrets:
   ```bash
   python3 scripts/cp_init_auth.py
   ```

   This creates `~/.control_plane_v2/secrets.env` with:
   - Randomly generated shared secret
   - Pre-computed admin and maintainer tokens

2. Configure your environment:
   ```bash
   # Option A: Point to secrets file (auth.py loads it automatically)
   export CONTROL_PLANE_SECRETS_FILE=~/.control_plane_v2/secrets.env

   # Option B: Source secrets directly (exports are built-in)
   source ~/.control_plane_v2/secrets.env
   # Now CONTROL_PLANE_TOKEN is set to admin token
   ```

3. Verify:
   ```bash
   python3 scripts/cp_version_checkpoint.py --dry-run --label "test"
   ```

**Security Notes:**
- Secrets file is OUTSIDE plane root (preserves pristine boundary)
- File permissions are 600 (owner only)
- Secret is NEVER logged to ledger (only the action + path)
- Tokens are user-specific HMAC signatures

**Rotating Secrets:**
```bash
python3 scripts/cp_init_auth.py --force
```

### Providers and Roles

- Providers (`lib/auth.py`):
  - `hmac` (default, production): uses external secrets file or `CONTROL_PLANE_SHARED_SECRET` env
  - `passthrough` (dev only): requires `CONTROL_PLANE_ALLOW_PASSTHROUGH=1`
- Roles → actions (`lib/authz.py`):
  - `admin`: create/install/update/remove/pack/verify/hash_update/checkpoint
  - `maintainer`: install/update/remove/pack/verify
  - `auditor`, `reader`: verify
- Pass token via CLI `--token` or env `CONTROL_PLANE_TOKEN`. Missing/invalid token → denied.

## Package management

- Scripts: `package_pack.py`, `package_install.py`, `package_sync.py`, `validate_packages.py`.
- Archives live in `packages_store/` (tar.gz + .sha256).
- Registries: `packages_registry.csv` tracks source/digest and routing fields.
- Output routing:
  - `output_type`: `extension` (into Control_Plane root), `module` (into `modules/`), `external` (outside CP, ledger-only).
  - `output_path`: required for `external` (absolute/env-expanded); optional for module/extension (defaults to standard locations).
  - External deliveries are NOT in registry or integrity scope; they are logged to the ledger with path + hash.

## Build a Package (tar.gz, path-preserving)
1) Artifact under Control_Plane_v2 (e.g., `frameworks/FMWK-100_agent_development_standard.md`).
2) `python3 scripts/package_pack.py --src frameworks/FMWK-100_agent_development_standard.md --id PKG-FMWK-100 --token <token>`
   - Outputs `packages_store/FMWK-100_agent_development_standard.tar.gz` + `.sha256`.
   - Updates `packages_registry.csv` (source=archive, source_type=tar, digest set).
3) External archives can be dropped into `packages_store/` for later install.

## Install a Package
- `python3 scripts/package_install.py --archive packages_store/FMWK-100_agent_development_standard.tar.gz --id PKG-FMWK-100 --token <token>`
- Uses registry digest when `--id` given; refuses overwrite unless `--force`.
- Routing follows `output_type`; external installs skip registry and integrity but are fully audited in the ledger.

## Registry Utilities
- Compile view: `python3 scripts/package_sync.py`
- Validate schema/deps: `python3 scripts/validate_packages.py`

## Integrity & Compliance
- Full check: `python3 scripts/integrity_check.py --json`
  - Verifies registry ↔ filesystem hashes, computes Merkle root, detects orphans.
  - `REG-CP` intentionally hashless (self-reference avoidance).
- After any pack/install/remove, rerun integrity_check.
- Regenerate `MANIFEST.json` when files change (maintained during upkeep).

## Gate Operations (programmatic)
- `GateOperations` enforces AuthZ on create/install/update/remove.
- Example: `GateOperations(control_plane_root=Path('.'), token=<token>)`.

## Best Practices
- Always build via `package_pack.py` to preserve paths for replayable installs.
- Don’t bypass registries; installs should reference a registry row.
- Keep secrets out of repo; only public keys/config are committed.
- Run `validate_packages.py` + `integrity_check.py` in CI on every change.
- Treat `packages_store/` as the sole ingress point for external artifacts.

## Pluggable Auth Roadmap
- To add OAuth/OIDC: implement a new provider in `lib/auth.py` that validates ID tokens and maps claims → roles; select via `CONTROL_PLANE_AUTH_PROVIDER=oidc`.
