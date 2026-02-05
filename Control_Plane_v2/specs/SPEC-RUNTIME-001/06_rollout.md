# Rollout Plan

## Approach

Direct commit to repository after all gates pass. This is a T1 (runtime tier) module that provides the execution framework for all agents.

## Pre-Deployment Checklist

1. [ ] All spec files complete (00-08)
2. [ ] All code files created in `modules/agent_runtime/`
3. [ ] Test files created and passing
4. [ ] PKG-T0-EVIDENCE-001 installed (dependency)
5. [ ] Code reviewed by human

## Deployment Steps

### Step 1: Verify Dependency

```bash
# Ensure evidence stdlib is installed
python3 scripts/trace.py --explain PKG-T0-EVIDENCE-001
```

### Step 2: Create Package

```bash
python3 scripts/package_pack.py \
  --src modules/agent_runtime \
  --id PKG-T1-RUNTIME-001 \
  --token <admin_token>
```

### Step 3: Install Package (HO3 first)

```bash
python3 scripts/package_install.py \
  --archive packages_store/PKG-T1-RUNTIME-001.tar.gz \
  --id PKG-T1-RUNTIME-001 \
  --token <admin_token>
```

### Step 4: Register in Control Plane

Update `registries/packages_registry.csv` with:
- Package ID: PKG-T1-RUNTIME-001
- Spec: SPEC-RUNTIME-001
- Tier: T1
- Status: active

### Step 5: Verify Installation

```bash
python3 scripts/trace.py --explain PKG-T1-RUNTIME-001
python3 scripts/integrity_check.py --json
```

### Step 6: Run Integration Test

```bash
# Test basic runtime functionality
python3 -c "
from modules.agent_runtime import AgentRunner, Session
from modules.agent_runtime.capability import CapabilityEnforcer

# Test capability enforcement
caps = {'read': ['ledger/*.jsonl'], 'write': [], 'execute': [], 'forbidden': []}
enforcer = CapabilityEnforcer(caps)
print('Capability check:', enforcer.check('read', 'ledger/governance.jsonl'))
"
```

## Rollback Plan

If issues are discovered:

1. **Immediate:** Uninstall package
   ```bash
   python3 scripts/package_uninstall.py --id PKG-T1-RUNTIME-001 --token <admin_token>
   ```

2. **Code revert:** `git revert <commit_hash>`

3. **Registry cleanup:** Remove entry from `packages_registry.csv`

## Post-Deployment Verification

1. Run full test suite
2. Verify no orphan files created
3. Verify integrity check passes
4. Test with a simple agent package
5. Verify ledger entries are correctly formatted
