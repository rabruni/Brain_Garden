# Admin Agent Script Quick Reference
Token-efficient index of scripts and key flags so an agent can pick the right command fast.

Format: `script — purpose | key flags | example`

## Package lifecycle
- `scripts/pkgutil.py` — Package authoring (init, preflight, stage, compliance) | `init[-agent] PKG --spec/--framework --output`, `preflight PKG --src`, `stage PKG --src`, `compliance summary|gates|troubleshoot --error G1` | `python3 scripts/pkgutil.py preflight PKG-XXX --src _staging/PKG-XXX`
- `scripts/package_install.py` — Install archive into plane (enforces G0A/G1/G5) | `--archive`, `--id`, `--dry-run`, `--force`, `--root`, `--work-order`, `--actor`, `--token`, `--json` | `python3 scripts/package_install.py --archive packages_store/PKG-XXX.tar.gz --id PKG-XXX`
- `scripts/package_uninstall.py` — Remove package files (use rollback preferred) | `--id`, `--root`, `--force`, `--json` | `python3 scripts/package_uninstall.py --id PKG-OLD --force`
- `scripts/package_sync.py` — Sync compiled registry after installs | `--root`, `--dry-run`, `--json` | `python3 scripts/package_sync.py`
- `scripts/package_pack.py` — Build package archive | `--src`, `--id`, `--token` | `python3 scripts/package_pack.py --src _staging/PKG-XXX --id PKG-XXX`
- `scripts/package_factory.py` — Library of gate steps used by pack/install (rarely invoked directly).

## Governance gates & integrity
- `scripts/gate_check.py` — Run gates | `--gate G0A G0B G1-G6|--all`, `--plane ho3|ho2|ho1`, `--manifest/--archive`, `--wo`, `--enforce`, `--json` | `python3 scripts/gate_check.py --gate G0B G1 G6 --plane ho3 --enforce`
- `scripts/g0k_gate.py, g2_gate.py, g3_gate.py, g4_gate.py, g5_gate.py, g6_gate.py` — Individual gate runners (internal; prefer `gate_check.py`).
- `scripts/integrity_check.py` — Verify hashes/merkle/orphans | `--json`, `--root` | `python3 scripts/integrity_check.py --json`
- `scripts/verify_installed_state.py` — Check installed vs registry | `--root`, `--json`.
- `scripts/verify_integrity.sh` — Shell wrapper for integrity sweep.
- `scripts/seal_guard.py` — Pristine/immutability enforcement drill.

## Ledger & work orders
- `scripts/trace.py` — Provenance/inventory explainer | `--inventory`, `--file <path>`, `--json` | `python3 scripts/trace.py --inventory`
- `scripts/ledger_repair.py` — Fix ledger chain gaps (use carefully) | `--ledger`, `--dry-run`.
- `scripts/ledger_tier.py` — Show tier ledger info | `--plane`.
- `scripts/apply_work_order.py` — Apply a work order | `--file`, `--wo`, `--root`.
- `scripts/wo_keygen.py` — Generate WO signing keypair.
- `scripts/wo_verify.py` — Verify signed work order | `--file`, `--sig`, `--pubkey`.
- `scripts/wo_approve.py` — Approve work order | `--wo`, `--actor`, `--token`.
- `scripts/compute_wo_hash.py` — Deterministic WO hash | `--file`.
- `scripts/validate_work_order.py` — Schema/chain checks | `--file`, `--json`.

## Plane/version control
- `scripts/cp_version_checkpoint.py` — Create checkpoint | `--label`, `--dry-run`, `--root`.
- `scripts/cp_version_list.py` — List checkpoints | `--root`.
- `scripts/cp_version_rollback.py` — Roll back to checkpoint | `--version-id`, `--force`, `--root`.
- `scripts/cp_plane.py` — Inspect plane metadata | `--plane`, `--json`.
- `scripts/validate_tier_deps.py` — Check tier dependency configs.

## Kernel/base assets
- `scripts/kernel_build.py` — Build kernel package | `--output`, `--root`.
- `scripts/kernel_install.py` — Install kernel (enforces G0K) | `--archive`, `--root`.
- `scripts/test_pack.sh`, `scripts/test_install.sh`, `scripts/test_uninstall.sh` — Smoke scripts for kernel/package flow.

## Auth & bootstrap
- `scripts/cp_init_auth.py` — Initialize auth secrets.
- `scripts/genesis_bootstrap.py` — First-time bootstrap of plane (HO3).
- `scripts/install_baseline.py` — Install baseline packages.
- `scripts/generate_baseline_manifest.py` — Baseline manifest helper.

## Registry & rebuild helpers
- `scripts/rebuild_derived.py`, `rebuild_derived_registries.py` — Recompute derived registries.
- `scripts/quarantine_orphans.py` — Move orphaned files out of registry control | `--dry-run`, `--restore QRN-ID`, `--list`, `--json` | `python3 scripts/quarantine_orphans.py --dry-run`
- `scripts/remediate_orphans.py` — Full governance chain orphan remediation (creates specs, registers, packages) | `--plan`, `--execute`, `--dry-run`, `--install`, `--config`, `--json` | `python3 scripts/remediate_orphans.py --execute --install`
- `scripts/validate_packages.py` — Validate registries/packages.
- `scripts/validate_package_manifest.py` — Manifest schema check.
- `scripts/validate_install_policy.py`, `validate_attention_policy.py` — Policy validators.

## Shell/interactive
- `scripts/shell.py` — Controlled shell inside plane (obeys pristine guard).
- `scripts/chat.py` — Simple chat/LLM helper for local testing.

## Misc
- `scripts/package_trace.sh` — Shell helper to trace package ownership.
- `scripts/ledger_tier.py` — Tier ledger info (duplicate note for quick find).
- `scripts/pristine_rebuild_drill.sh` — Rebuild pristine state (ops drill).
- Package-embedded scripts (read-only): e.g., `packages_store/PKG-KERNEL-001/files/scripts/trace.py`—use via installed package if needed.

Usage tip: prefer `gate_check.py`, `pkgutil.py`, `package_install.py`, `trace.py`, `integrity_check.py`, `cp_version_checkpoint.py`, and work-order helpers for most admin-agent tasks; others are support/ops scripts.
