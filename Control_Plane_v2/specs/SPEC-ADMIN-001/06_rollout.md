# Rollout Plan

## Approach

Direct commit to repository after all gates pass. This is a T3 (agent tier) package that demonstrates governed agent operation.

## Pre-Deployment Checklist

1. [ ] All spec files complete (00-08)
2. [ ] All code files created in `modules/admin_agent/`
3. [ ] Test files created and passing
4. [ ] PKG-T0-EVIDENCE-001 installed (dependency)
5. [ ] PKG-T1-RUNTIME-001 installed (dependency)
6. [ ] Code reviewed by human

## Deployment Steps

### Step 1: Verify Dependencies

```bash
# Ensure dependencies are installed
python3 scripts/trace.py --explain PKG-T0-EVIDENCE-001
python3 scripts/trace.py --explain PKG-T1-RUNTIME-001
```

### Step 2: Create Package

```bash
python3 scripts/package_pack.py \
  --src modules/admin_agent \
  --id PKG-T3-ADMIN-001 \
  --token <admin_token>
```

### Step 3: Install Package (HO1 only)

The Admin Agent operates in HO1 tier only:

```bash
python3 scripts/package_install.py \
  --archive packages_store/PKG-T3-ADMIN-001.tar.gz \
  --id PKG-T3-ADMIN-001 \
  --token <admin_token>
```

### Step 4: Register in Control Plane

Update `registries/packages_registry.csv` with:
- Package ID: PKG-T3-ADMIN-001
- Spec: SPEC-ADMIN-001
- Tier: T3
- Status: active

### Step 5: Verify Installation

```bash
python3 scripts/trace.py --explain PKG-T3-ADMIN-001
python3 scripts/integrity_check.py --json
```

### Step 6: Test Admin Agent

```bash
# Test basic functionality
python3 -c "
from modules.admin_agent import AdminAgent
agent = AdminAgent()
print(agent.explain('FMWK-000'))
print(agent.list_installed())
print(agent.check_health())
"
```

## Rollback Plan

If issues are discovered:

1. **Immediate:** Uninstall package
   ```bash
   python3 scripts/package_uninstall.py --id PKG-T3-ADMIN-001 --token <admin_token>
   ```

2. **Code revert:** `git revert <commit_hash>`

3. **Registry cleanup:** Remove entry from `packages_registry.csv`

## Post-Deployment Verification

1. Run full test suite
2. Verify no orphan files created
3. Verify integrity check passes
4. Test with various artifact types
5. Verify ledger entries are correctly formatted
6. Confirm read-only behavior (no PRISTINE writes)
