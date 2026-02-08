# Rollout Plan

## Approach

Direct commit to repository after all gates pass. This is a T0 (trust baseline) library with no external dependencies, so the rollout is straightforward.

## Pre-Deployment Checklist

1. [ ] All spec files complete (00-08)
2. [ ] All code files created in `modules/stdlib_evidence/`
3. [ ] Schema files created in `schemas/`
4. [ ] Test files created and passing
5. [ ] Code reviewed by human

## Deployment Steps

### Step 1: Create Package

```bash
python3 scripts/package_pack.py \
  --src modules/stdlib_evidence \
  --id PKG-T0-EVIDENCE-001 \
  --token <admin_token>
```

### Step 2: Install Package (HO3 first)

```bash
python3 scripts/package_install.py \
  --archive packages_store/PKG-T0-EVIDENCE-001.tar.gz \
  --id PKG-T0-EVIDENCE-001 \
  --token <admin_token>
```

### Step 3: Register in Control Plane

Update `registries/packages_registry.csv` with:
- Package ID: PKG-T0-EVIDENCE-001
- Spec: SPEC-EVIDENCE-001
- Tier: T0
- Status: active

### Step 4: Verify Installation

```bash
python3 scripts/trace.py --explain PKG-T0-EVIDENCE-001
python3 scripts/integrity_check.py --json
```

## Rollback Plan

If issues are discovered:

1. **Immediate:** Uninstall package
   ```bash
   python3 scripts/package_uninstall.py --id PKG-T0-EVIDENCE-001 --token <admin_token>
   ```

2. **Code revert:** `git revert <commit_hash>`

3. **Registry cleanup:** Remove entry from `packages_registry.csv`

## Post-Deployment Verification

1. Run test suite to confirm installation works
2. Verify no orphan files created
3. Verify integrity check passes
4. Confirm package appears in `trace.py --installed`
