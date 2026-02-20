# BUILDER_HANDOFF_31A1: Wire HO3Memory Into ADMIN Runtime

## 1. Mission

Connect the already-built HO3Memory (PKG-HO3-MEMORY-001) to the ADMIN runtime. H-29 built everything — HO3Memory class, HO2 supervisor hooks, consolidation plumbing — but none of it is active because `build_session_host_v2()` in `main.py` never instantiates HO3Memory or passes it to HO2Supervisor. This handoff is **instrumentation**: signals start flowing, HO3 biases get injected at Step 2b+, consolidation can fire. Modifies **PKG-ADMIN-001** only.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write/update tests FIRST. Every change gets test coverage.
3. **Package everything.** Modified package gets updated `manifest.json` SHA256 hashes. Use `hashing.py:compute_sha256()` and `packages.py:pack()`. NEVER raw hashlib or shell tar.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → `install.sh` → all gates pass.
5. **No hardcoding.** Budget values come from `admin_config.json`, not code defaults. If a test passes with the config key removed, the budget isn't properly centralized.
6. **No file replacement.** These are in-package modifications to PKG-ADMIN-001 only. Do not touch other packages.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never with `./` prefix.
8. **Results file.** Write `_staging/handoffs/RESULTS_HANDOFF_31A1.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md.
9. **Full regression test.** Run ALL staged package tests. Report pass/fail. New failures are blockers.
10. **Baseline snapshot.** Include in results file. Baseline input: 22 packages, 693 installed tests, 8/8 gates.
11. **Scope boundary.** This handoff modifies PKG-ADMIN-001 ONLY. Do NOT modify PKG-SESSION-HOST-V2-001 (that is H-31A-2). Do NOT modify PKG-HO2-SUPERVISOR-001 or PKG-HO3-MEMORY-001.
12. **Backward compatible.** If the `ho3` section is absent from admin_config.json, behavior is identical to before this handoff. HO3Memory is not instantiated. No errors.

## 3. Architecture / Design

### What Exists (already built by H-29A/B/C)

```
PKG-HO3-MEMORY-001 (HOT/kernel/ho3_memory.py)
├─ HO3MemoryConfig(memory_dir, gate_count_threshold, gate_session_threshold, ...)
├─ HO3Memory(plane_root, config)
│   ├─ log_signal(signal_id, session_id, event_id)
│   ├─ read_signals(signal_id?) → [SignalAccumulator]
│   ├─ read_active_biases() → [dict]
│   ├─ check_gate(signal_id) → GateResult
│   └─ log_overlay(overlay_dict)
└─ Uses: HOT/memory/signals.jsonl, HOT/memory/overlays.jsonl
```

```
PKG-HO2-SUPERVISOR-001 (HO2/kernel/ho2_supervisor.py)
├─ HO2Supervisor.__init__(..., ho3_memory=None)  ← accepts it, currently None
├─ HO2Config.ho3_enabled: bool = False           ← controls all HO3 code paths
├─ HO2Config.ho3_memory_dir: Optional[Path]      ← unused (HO3Memory owns its path)
├─ HO2Config.ho3_gate_count_threshold: int = 5   ← passed but never from config
├─ HO2Config.ho3_gate_session_threshold: int = 3
├─ HO2Config.ho3_gate_window_hours: int = 168
├─ HO2Config.consolidation_budget: int = 4000    ← used but never from config
├─ Step 2b+ (line 191-201): if ho3_memory → read_active_biases → inject
├─ Post-turn (line 307-347): if ho3_memory → log_signal → check_gate → candidates
└─ run_consolidation(signal_ids) (line 537-603): full WO dispatch → overlay write
```

### What's Missing (this handoff fills these gaps)

```
PKG-ADMIN-001 (HOT/admin/main.py)
├─ _ensure_import_paths(): MISSING PKG-HO3-MEMORY-001 path
├─ build_session_host_v2(): DOES NOT instantiate HO3Memory
├─ build_session_host_v2(): DOES NOT pass ho3_memory to HO2Supervisor
├─ build_session_host_v2(): DOES NOT map ho3 config to HO2Config fields
├─ build_session_host_v2(): DOES NOT pass consolidation_budget from config
└─ HO2Config construction: 5 fields use defaults instead of config values
```

```
admin_config.json
├─ MISSING: "ho3" section (enabled, memory_dir, gate thresholds)
├─ MISSING: budget.consolidation_budget
└─ MISSING: budget.ho3_bias_budget (forward placeholder for H-29.1)
```

### Budget Audit: HO2Config Fields vs admin_config.json

| HO2Config Field | Default | Config Source | Currently Wired? |
|-----------------|---------|---------------|------------------|
| budget_ceiling | 100000 | budget.session_token_limit | YES (line 1263) |
| classify_budget | 2000 | budget.classify_budget | YES (line 1264) |
| synthesize_budget | 16000 | budget.synthesize_budget | YES (line 1265) |
| followup_min_remaining | 500 | budget.followup_min_remaining | YES (line 1266) |
| budget_mode | "enforce" | budget.budget_mode | YES (line 1267) |
| consolidation_budget | 4000 | budget.consolidation_budget | **NO — uses default** |
| ho3_enabled | False | ho3.enabled | **NO — uses default** |
| ho3_memory_dir | None | ho3.memory_dir | **NO — uses default** |
| ho3_gate_count_threshold | 5 | ho3.gate_count_threshold | **NO — uses default** |
| ho3_gate_session_threshold | 3 | ho3.gate_session_threshold | **NO — uses default** |
| ho3_gate_window_hours | 168 | ho3.gate_window_hours | **NO — uses default** |

After this handoff, ALL fields will be wired from config. No silent divergence.

### Adversarial Analysis: Adding HO3 Dependency to ADMIN

**Hurdles**: PKG-HO3-MEMORY-001 must be importable from main.py. Staging import paths need updating. HO3Memory does `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` internally — when imported from a different package context, this resolves to the HO3 package's HOT/ dir, which is correct for `from kernel.ledger_client import ...`.

**Not Enough**: If we add the config and import path but don't wire all HO2Config fields, we get silent budget divergence — config says one thing, code uses a different default. The audit-and-wire step is essential.

**Too Much**: We could restructure the entire budget loading into a centralized function. Overkill — that's a future refactor. For now, just wire the missing fields explicitly in the HO2Config constructor call.

**Synthesis**: Add import path, instantiate HO3Memory, wire all HO2Config fields from config, add config entries. Keep it mechanical. The HO2 code already has all the guards (`if self._ho3_memory and self._config.ho3_enabled`).

## 4. Implementation Steps

### Step 1: Add ho3 config section to admin_config.json

In `_staging/PKG-ADMIN-001/HOT/config/admin_config.json`, add after the `"budget"` section and before `"permissions"`:

```json
  "ho3": {
    "enabled": true,
    "memory_dir": "HOT/memory",
    "gate_count_threshold": 5,
    "gate_session_threshold": 3,
    "gate_window_hours": 168
  },
```

Also add two keys to the existing `"budget"` section:

```json
    "consolidation_budget": 4000,
    "ho3_bias_budget": 2000,
```

The `budget` section after this change:
```json
  "budget": {
    "session_token_limit": 200000,
    "classify_budget": 2000,
    "synthesize_budget": 100000,
    "consolidation_budget": 4000,
    "ho3_bias_budget": 2000,
    "followup_min_remaining": 500,
    "budget_mode": "warn",
    "turn_limit": 50,
    "timeout_seconds": 7200
  },
```

### Step 2: Update admin_config.schema.json

In `_staging/PKG-ADMIN-001/HOT/schemas/admin_config.schema.json`, add `"ho3"` to the `properties` object:

```json
    "ho3": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean"},
        "memory_dir": {"type": "string"},
        "gate_count_threshold": {"type": "integer", "minimum": 1},
        "gate_session_threshold": {"type": "integer", "minimum": 1},
        "gate_window_hours": {"type": "integer", "minimum": 1}
      }
    }
```

Note: `ho3` is NOT added to the `required` array — it's optional for backward compatibility.

### Step 3: Add HO3 import path to _ensure_import_paths

In `_staging/PKG-ADMIN-001/HOT/admin/main.py`, in the `_ensure_import_paths` function, add this line to the staging `add` list (after the PKG-TOKEN-BUDGETER-001 line, around line 51):

```python
        staging / "PKG-HO3-MEMORY-001" / "HOT" / "kernel",
        staging / "PKG-HO3-MEMORY-001" / "HOT",
```

The installed root paths already include `Path(root) / "HOT" / "kernel"` and `Path(root) / "HOT"`, so no change needed for installed mode.

### Step 4: Instantiate HO3Memory in build_session_host_v2

In `build_session_host_v2()`, after step 7 (HO2 Supervisor construction, line 1277) and before step 8 (V2 Agent Config, line 1279), add:

```python
    # 7b. HO3 Memory (optional — enabled via ho3.enabled in config)
    ho3_memory = None
    ho3_cfg = cfg_dict.get("ho3", {})
    if ho3_cfg.get("enabled", False):
        try:
            from ho3_memory import HO3Memory, HO3MemoryConfig
            memory_dir = root / ho3_cfg.get("memory_dir", "HOT/memory")
            memory_dir.mkdir(parents=True, exist_ok=True)
            ho3_config = HO3MemoryConfig(
                memory_dir=memory_dir,
                gate_count_threshold=ho3_cfg.get("gate_count_threshold", 5),
                gate_session_threshold=ho3_cfg.get("gate_session_threshold", 3),
                gate_window_hours=ho3_cfg.get("gate_window_hours", 168),
                enabled=True,
            )
            ho3_memory = HO3Memory(plane_root=root, config=ho3_config)
        except ImportError:
            pass  # PKG-HO3-MEMORY-001 not installed — ho3_memory stays None
```

### Step 5: Wire all HO2Config fields from config

Replace the HO2Config construction (lines 1259-1269) with:

```python
    ho2_config = HO2Config(
        attention_templates=["ATT-ADMIN-001"],
        ho2m_path=root / "HO2" / "ledger" / "ho2m.jsonl",
        ho1m_path=root / "HO1" / "ledger" / "ho1m.jsonl",
        budget_ceiling=budget_cfg.get("session_token_limit", 200000),
        classify_budget=budget_cfg.get("classify_budget", 2000),
        synthesize_budget=budget_cfg.get("synthesize_budget", 16000),
        followup_min_remaining=budget_cfg.get("followup_min_remaining", 500),
        budget_mode=budget_mode,
        tools_allowed=[t["tool_id"] for t in all_tools],
        # HO3 fields — all from config, no silent defaults
        ho3_enabled=ho3_cfg.get("enabled", False),
        ho3_memory_dir=Path(ho3_cfg.get("memory_dir", "HOT/memory")) if ho3_cfg.get("memory_dir") else None,
        ho3_gate_count_threshold=ho3_cfg.get("gate_count_threshold", 5),
        ho3_gate_session_threshold=ho3_cfg.get("gate_session_threshold", 3),
        ho3_gate_window_hours=ho3_cfg.get("gate_window_hours", 168),
        consolidation_budget=budget_cfg.get("consolidation_budget", 4000),
    )
```

### Step 6: Pass ho3_memory to HO2Supervisor

Replace the HO2Supervisor construction (lines 1270-1277) with:

```python
    ho2 = HO2Supervisor(
        plane_root=root,
        agent_class=cfg_dict.get("agent_class", "ADMIN"),
        ho1_executor=ho1,
        ledger_client=ledger_ho2m,
        token_budgeter=budgeter,
        config=ho2_config,
        ho3_memory=ho3_memory,
    )
```

### Step 7: Update manifest.json

Add `PKG-HO3-MEMORY-001` to the `dependencies` array:

```json
  "dependencies": [
    "PKG-KERNEL-001",
    "PKG-ANTHROPIC-PROVIDER-001",
    "PKG-WORK-ORDER-001",
    "PKG-LLM-GATEWAY-001",
    "PKG-HO1-EXECUTOR-001",
    "PKG-HO2-SUPERVISOR-001",
    "PKG-HO3-MEMORY-001",
    "PKG-SESSION-HOST-V2-001",
    "PKG-SHELL-001"
  ],
```

Update SHA256 hashes for all modified assets using `compute_sha256()`.

### Step 8: Write tests (DTT — these come FIRST in actual execution)

Add new test functions to `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py`. See Test Plan section below.

### Step 9: Governance cycle

1. Delete `.DS_Store` and `__pycache__` from `_staging/PKG-ADMIN-001/`
2. Update `manifest.json` SHA256 hashes for all changed files using `compute_sha256()`
3. Rebuild `PKG-ADMIN-001.tar.gz` using `pack()`
4. Rebuild `CP_BOOTSTRAP.tar.gz`
5. Clean-room install → all gates pass
6. Full regression test → no new failures

## 5. Package Plan

### PKG-ADMIN-001 (modified)

| Field | Value |
|-------|-------|
| Package ID | PKG-ADMIN-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HOT/admin/main.py` — import path, HO3Memory instantiation, HO2Config wiring
- `HOT/config/admin_config.json` — ho3 section, budget entries
- `HOT/schemas/admin_config.schema.json` — ho3 schema
- `HOT/tests/test_admin.py` — new tests
- `manifest.json` — dependency + hash updates

Dependencies (updated):
- PKG-KERNEL-001
- PKG-ANTHROPIC-PROVIDER-001
- PKG-WORK-ORDER-001
- PKG-LLM-GATEWAY-001
- PKG-HO1-EXECUTOR-001
- PKG-HO2-SUPERVISOR-001
- **PKG-HO3-MEMORY-001** (NEW)
- PKG-SESSION-HOST-V2-001
- PKG-SHELL-001

## 6. Test Plan

### New tests for PKG-ADMIN-001 (10 new tests)

| Test | Description | Expected |
|------|-------------|----------|
| `test_ho3_memory_created_when_enabled` | Config has ho3.enabled=true → build_session_host_v2 creates HO3Memory | HO2Supervisor receives non-None ho3_memory |
| `test_ho3_memory_none_when_disabled` | Config has ho3.enabled=false → ho3_memory=None | HO2Supervisor receives ho3_memory=None |
| `test_ho3_memory_none_when_section_missing` | Config has no "ho3" key → backward compatible | HO2Supervisor receives ho3_memory=None, no errors |
| `test_ho3_config_values_mapped_to_ho2config` | Config ho3 section → HO2Config fields match | ho2_config.ho3_enabled, ho3_gate_count_threshold, etc. all match config values |
| `test_consolidation_budget_from_config` | budget.consolidation_budget=4000 in config → HO2Config reads it | ho2_config.consolidation_budget == 4000 |
| `test_consolidation_budget_not_default_when_config_differs` | Set consolidation_budget=8000 in config → HO2Config reads 8000 not 4000 | ho2_config.consolidation_budget == 8000 |
| `test_ho3_bias_budget_in_config` | admin_config.json contains budget.ho3_bias_budget | Key exists with value 2000 |
| `test_ho3_memory_dir_resolved_against_root` | ho3.memory_dir="HOT/memory" → resolved as root/"HOT"/"memory" | Memory dir path is root / "HOT" / "memory" |
| `test_ho3_memory_dir_created` | ho3.enabled=true, dir doesn't exist → dir created | root/"HOT"/"memory" directory exists after build |
| `test_ho3_import_path_in_staging_mode` | _ensure_import_paths includes PKG-HO3-MEMORY-001 path | Path string contains "PKG-HO3-MEMORY-001" |

### Test implementation notes

To test `build_session_host_v2` with HO3, the test config fixture (`_write_admin_files`) needs a variant that includes the `ho3` section. Create a helper:

```python
def _write_admin_files_with_ho3(tmp_path: Path, ho3_enabled=True):
    """Like _write_admin_files but with ho3 config section."""
    cfg_path, tpl_path = _write_admin_files(tmp_path)
    cfg = json.loads(cfg_path.read_text())
    cfg["ho3"] = {
        "enabled": ho3_enabled,
        "memory_dir": "HOT/memory",
        "gate_count_threshold": 5,
        "gate_session_threshold": 3,
        "gate_window_hours": 168,
    }
    cfg["budget"]["consolidation_budget"] = 4000
    cfg["budget"]["ho3_bias_budget"] = 2000
    cfg_path.write_text(json.dumps(cfg))
    return cfg_path, tpl_path
```

Tests that verify HO2Supervisor received ho3_memory should mock the HO2Supervisor constructor to capture its arguments, or inspect the constructed ho2 object's `_ho3_memory` attribute. Follow existing test patterns in `test_admin.py`.

### Existing tests (128) must continue passing

No existing test behavior should change. The ho3 wiring is purely additive — it only activates when `ho3.enabled=true` in config. Existing test fixtures don't have the ho3 section, so HO3Memory is never instantiated in existing tests.

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| main.py (current) | `_staging/PKG-ADMIN-001/HOT/admin/main.py` | Lines to modify (import path, build_session_host_v2) |
| admin_config.json | `_staging/PKG-ADMIN-001/HOT/config/admin_config.json` | Config to extend |
| admin_config.schema.json | `_staging/PKG-ADMIN-001/HOT/schemas/admin_config.schema.json` | Schema to extend |
| test_admin.py | `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py` | Test patterns (_write_admin_files, dual-context) |
| manifest.json | `_staging/PKG-ADMIN-001/manifest.json` | Dependencies and hashes |
| HO3Memory interface | `_staging/PKG-HO3-MEMORY-001/HOT/kernel/ho3_memory.py:1-80` | HO3MemoryConfig, HO3Memory constructor |
| HO2Config fields | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py:57-85` | Fields to wire from config |
| HO2Supervisor constructor | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py:109-118` | ho3_memory parameter |
| Kernel hashing | `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py` | compute_sha256() for manifest updates |
| Kernel packages | `_staging/PKG-KERNEL-001/HOT/kernel/packages.py` | pack() for archive rebuilds |

## 8. End-to-End Verification

```bash
# 1. Clean-room install
TMPDIR=$(mktemp -d)
cd Control_Plane_v2/_staging
tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
cd "$TMPDIR" && bash install.sh --root "$TMPDIR" --dev

# 2. Run all tests
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 -m pytest "$TMPDIR/HOT/tests" "$TMPDIR/HO1/tests" "$TMPDIR/HO2/tests" -v

# 3. Run gates
python3 "$TMPDIR/HOT/scripts/gate_check.py" --root "$TMPDIR" --all --enforce

# 4. Verify HO3 config present in installed config
python3 -c "import json; cfg=json.load(open('$TMPDIR/HOT/config/admin_config.json')); assert cfg.get('ho3',{}).get('enabled')==True; assert cfg['budget']['consolidation_budget']==4000; assert cfg['budget']['ho3_bias_budget']==2000; print('HO3 config: OK')"

# 5. Verify HO3Memory is importable from installed root
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT" python3 -c "from ho3_memory import HO3Memory, HO3MemoryConfig; print('HO3Memory import: OK')"
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `main.py` | `_staging/PKG-ADMIN-001/HOT/admin/` | MODIFY |
| `admin_config.json` | `_staging/PKG-ADMIN-001/HOT/config/` | MODIFY |
| `admin_config.schema.json` | `_staging/PKG-ADMIN-001/HOT/schemas/` | MODIFY |
| `test_admin.py` | `_staging/PKG-ADMIN-001/HOT/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-ADMIN-001/` | MODIFY |
| `PKG-ADMIN-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_31A1.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Config is truth.** Every budget value, threshold, and feature flag comes from `admin_config.json`. Code defaults exist only as fallbacks when the config key is absent — and tests verify the config path, not the fallback path.
2. **Backward compatible.** Missing `ho3` section = no HO3Memory. No errors, no behavioral change. Existing tests don't break.
3. **Guard pattern preserved.** HO2Supervisor already checks `if self._ho3_memory and self._config.ho3_enabled` before all HO3 code paths. This handoff activates those paths by providing a non-None ho3_memory and ho3_enabled=true.
4. **Import failure is safe.** If PKG-HO3-MEMORY-001 is not installed, the `try/except ImportError` catches it and ho3_memory stays None. The system runs without HO3.
5. **Audit, don't assume.** The budget divergence audit is explicit — every HO2Config field is mapped to a config key. No "probably fine" defaults.
6. **One package.** This handoff modifies PKG-ADMIN-001 only. The consolidation caller in SessionHostV2 is H-31A-2.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-31A1** — Wire HO3Memory into ADMIN runtime (PKG-ADMIN-001)

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_31A1_wire_ho3_into_admin.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` — NEVER `tar czf ... -C dir .`
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir → run install.sh → install YOUR changes on top → ALL gates must pass. This is NOT optional.
6. Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail, and whether you introduced new failures.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_31A1.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md. MUST include: Clean-Room Verification section, Baseline Snapshot section, Full Regression section.
8. CP_BOOTSTRAP rebuild: Rebuild CP_BOOTSTRAP.tar.gz and report the new SHA256.
9. Built-in tools: Use `hashing.py:compute_sha256()` for all SHA256 hashes and `packages.py:pack()` for all archives. NEVER use raw hashlib or shell tar.
10. This handoff modifies PKG-ADMIN-001 ONLY. Do NOT touch PKG-SESSION-HOST-V2-001, PKG-HO2-SUPERVISOR-001, or PKG-HO3-MEMORY-001.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What SINGLE package does this handoff modify? What package does it NOT touch (the consolidation caller)?
2. What function in main.py creates the runtime stack? At what step number do you insert HO3Memory instantiation?
3. What are the TWO classes you import from ho3_memory, and what try/except pattern do you use?
4. Name all SIX HO2Config fields that are currently NOT wired from admin_config.json. Where do they currently get their values?
5. What is the new `ho3` section in admin_config.json? List all 5 keys and their values.
6. What TWO new keys are added to the `budget` section? What are their values?
7. What happens if the `ho3` section is missing from admin_config.json entirely? What happens if PKG-HO3-MEMORY-001 is not installed?
8. How many NEW tests are you adding? Name them all.
9. What tar format command do you use for archive rebuilds? What format do SHA256 hashes use in manifests?
10. After this handoff, what does HO2Supervisor's Step 2b+ (line 191-201) do differently than before? What enables the change?

**Adversarial questions:**

11. If this build fails at Gate G0A, which specific file is the most likely culprit and why?
12. Is there a kernel tool you're tempted to skip in favor of a shell command? Why will you NOT do that?
13. The word "enabled" appears in both HO3MemoryConfig.enabled and HO2Config.ho3_enabled. Are these the same thing? If not, what's the difference and which controls what?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers

1. PKG-ADMIN-001 only. Does NOT touch PKG-SESSION-HOST-V2-001 (consolidation caller is H-31A-2).
2. `build_session_host_v2()`. Insert at step 7b, after HO2 Supervisor construction (line 1277) and before V2 Agent Config (line 1279).
3. `HO3Memory` and `HO3MemoryConfig` from `ho3_memory`. Wrapped in `try/except ImportError: pass` so if PKG-HO3-MEMORY-001 isn't installed, ho3_memory stays None.
4. Six fields: (a) ho3_enabled (default False), (b) ho3_memory_dir (default None), (c) ho3_gate_count_threshold (default 5), (d) ho3_gate_session_threshold (default 3), (e) ho3_gate_window_hours (default 168), (f) consolidation_budget (default 4000). All use dataclass defaults instead of reading from admin_config.json.
5. `ho3.enabled: true`, `ho3.memory_dir: "HOT/memory"`, `ho3.gate_count_threshold: 5`, `ho3.gate_session_threshold: 3`, `ho3.gate_window_hours: 168`.
6. `consolidation_budget: 4000` and `ho3_bias_budget: 2000`. ho3_bias_budget is a forward placeholder — no code reads it yet (that's H-29.1).
7. Missing ho3 section: `cfg_dict.get("ho3", {})` returns empty dict, `ho3_cfg.get("enabled", False)` returns False, HO3Memory not instantiated, ho3_memory=None. Missing PKG-HO3-MEMORY-001: ImportError caught, ho3_memory stays None. Both cases: system runs identically to before.
8. 10 new tests: test_ho3_memory_created_when_enabled, test_ho3_memory_none_when_disabled, test_ho3_memory_none_when_section_missing, test_ho3_config_values_mapped_to_ho2config, test_consolidation_budget_from_config, test_consolidation_budget_not_default_when_config_differs, test_ho3_bias_budget_in_config, test_ho3_memory_dir_resolved_against_root, test_ho3_memory_dir_created, test_ho3_import_path_in_staging_mode.
9. `tar czf ... -C dir $(ls dir)`. SHA256 format: `sha256:<64hex>` (71 chars).
10. Before: `self._ho3_memory` is None (passed as None from main.py), so the `if self._ho3_memory and self._config.ho3_enabled:` guard at line 193 is False → `read_active_biases()` never called. After: ho3_memory is a real HO3Memory instance and ho3_enabled=True → guard is True → biases are read and injected into assembled_context. The change is enabled by this handoff instantiating HO3Memory and passing it.
11. `manifest.json` — if any SHA256 hash is bare hex (missing `sha256:` prefix) or stale (file modified after hash computed), G0A fails. Most likely culprit: `admin_config.json` hash after adding the ho3/budget keys.
12. Tempted to use `shell tar` for archive rebuild. Will NOT because shell tar produces non-deterministic metadata (mtime, uid) → different hash each build. Must use `packages.py:pack()` which produces I4-DETERMINISTIC archives (mtime=0, uid=0, sorted entries, PAX format).
13. They are NOT the same. `HO3MemoryConfig.enabled` is internal to the HO3Memory class — it controls whether the memory store considers itself active. `HO2Config.ho3_enabled` controls whether the HO2 Supervisor checks `self._ho3_memory` at all. Both must be True for HO3 to function. In practice, if ho3.enabled=true in config, both get set to True via the mapping in build_session_host_v2.
