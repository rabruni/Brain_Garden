# BUILDER_HANDOFF_25: Fix Classify + Admin Tool Improvements

## 1. Mission

Fix the classify WO failure that breaks every conversation start, restore a lost regression filter, and give the admin agent the ability to browse files and query all ledgers.

Four fixes across two packages:

1. **PKG-HO1-EXECUTOR-001** — Intercept Anthropic's `output_json` pseudo-tool as structured output (not a dispatchable tool) AND restore the `tools_allowed` filter that H-23/H-24 accidentally dropped.
2. **PKG-ADMIN-001** — Add `ledger` parameter to `query_ledger` tool (governance/ho2m/ho1m) AND add `list_files` tool for filesystem discovery.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design -> Test -> Then implement.** Write/update tests FIRST. Every change gets test coverage.
3. **Package everything.** Modified packages get updated `manifest.json` SHA256 hashes. Use `hashing.py:compute_sha256()` and `packages.py:pack()`. NEVER raw hashlib or shell tar.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` -> `install.sh` -> all gates pass.
5. **No hardcoding.** `list_files` depth limit comes from tool parameters, not a magic constant.
6. **No file replacement.** These are in-package modifications, no cross-package file changes.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never with `./` prefix.
8. **Results file.** Write `_staging/handoffs/RESULTS_HANDOFF_25.md`.
9. **Full regression test.** Run ALL staged package tests. Report pass/fail.
10. **Baseline snapshot.** Include in results file.
11. **When adding `list_files`, also add it to `admin_config.json` tools array** — otherwise HO2 won't include it in `tools_allowed` for synthesize WOs and the LLM will never see it.

## 3. Architecture / Design

### Root Cause: Classify Failure

```
Classify WO (no tools_allowed, has structured_output in contract)
    |
    v
HO1 sends structured_output to Anthropic
    |
    v
Anthropic returns tool_use block: name="output_json", input={"speech_act":"greeting",...}
    |
    v
_extract_tool_uses() returns [{"tool_id": "output_json", ...}]
    |
    v
H-22 had a filter here: tools_allowed is empty -> tool_uses = []
BUT H-23/H-24 CLOBBERED THIS FILTER (regression at line 168-170)
    |
    v
tool_dispatcher.execute("output_json", ...) -> error (no handler)
    |
    v
Builds follow-up request, but turn_limit=1 -> turn_limit_exceeded
    |
    v
Classify WO fails. Every. Single. Time.
```

### What Happened to H-22's Filter

H-22 added `tools_allowed` filtering between `_extract_tool_uses()` and the dispatch loop (original lines ~172-179):

```python
tools_allowed = wo.get("constraints", {}).get("tools_allowed", [])
raw_tool_uses = self._extract_tool_uses(content, response)
if tools_allowed:
    allowed_set = set(tools_allowed)
    tool_uses = [tu for tu in raw_tool_uses if tu["tool_id"] in allowed_set]
else:
    tool_uses = []
```

H-23 or H-24 modified `ho1_executor.py` and dropped this filtering block. The current code at line 168-170 goes straight from extract to dispatch:

```python
tool_uses = self._extract_tool_uses(content, response)
if tool_uses and self.tool_dispatcher:
```

### Fix Design

| Fix | Package | File | What | Why |
|-----|---------|------|------|-----|
| 1a | PKG-HO1-EXECUTOR-001 | `ho1_executor.py` | Intercept `output_json` in extracted tool_uses: extract `.input` as parsed structured output | Anthropic's structured_output is not a real tool |
| 1b | PKG-HO1-EXECUTOR-001 | `ho1_executor.py` | Restore `tools_allowed` filter between extract and dispatch | Regression fix — H-22's filter was lost |
| 2 | PKG-ADMIN-001 | `main.py` + `admin_config.json` | Add `ledger` parameter to `query_ledger`: governance (default), ho2m, ho1m | TURN_RECORDED events are in ho2m, not governance |
| 3 | PKG-ADMIN-001 | `main.py` + `admin_config.json` | Add `list_files` tool with depth/glob parameters | Agent can't discover file paths without browsing |

### Adversarial Analysis: output_json Interception

**Hurdles**: output_json is an Anthropic implementation detail, not documented as stable API. If they change the name or mechanism, the interception breaks. Need to handle it defensively.
**Not Enough**: Restoring the filter alone (1b) likely fixes classify in most cases — the provider already serializes tool input into `content`, so discarding output_json still leaves usable data. But this relies on provider-specific serialization behavior that isn't contractually guaranteed. Without explicit interception, a provider change that stops serializing tool input into content would silently break classify again.
**Too Much**: We could redesign structured output handling end-to-end — intercept at Gateway level, normalize across providers. Overkill for a hotfix.
**Synthesis**: The tools_allowed filter is the primary fix — it blocks output_json from dispatch and lets the provider's serialized content flow through. The output_json interception is defense-in-depth: it explicitly extracts the structured payload so we don't depend on provider serialization behavior. Both fixes together: filter as the gate, interception as the safety net.

## 4. Implementation Steps

### Step 1: Intercept output_json + restore tools_allowed filter in HO1

In `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py`, replace lines 168-170:

**Before (current broken code):**
```python
                # Check for tool_use blocks
                tool_uses = self._extract_tool_uses(content, response)
                if tool_uses and self.tool_dispatcher:
```

**After:**
```python
                # Check for tool_use blocks (filtered to tools_allowed)
                tools_allowed = wo.get("constraints", {}).get("tools_allowed", [])
                raw_tool_uses = self._extract_tool_uses(content, response)

                # Intercept Anthropic output_json pseudo-tool:
                # When structured_output is active, Anthropic returns the result
                # as a tool_use with name="output_json". This is NOT a real tool.
                # Extract its payload as final structured output and remove from list.
                output_json_blocks = [tu for tu in raw_tool_uses if tu["tool_id"] == "output_json"]
                if output_json_blocks and "output_json" not in (tools_allowed or []):
                    final_content = json.dumps(output_json_blocks[0].get("arguments", {}))
                    raw_tool_uses = [tu for tu in raw_tool_uses if tu["tool_id"] != "output_json"]

                # Filter to tools_allowed (restored from H-22, dropped by H-23/H-24)
                if tools_allowed:
                    allowed_set = set(tools_allowed)
                    tool_uses = [tu for tu in raw_tool_uses if tu["tool_id"] in allowed_set]
                else:
                    tool_uses = []

                # If no dispatchable tools remain, break with whatever final_content we have
                if not tool_uses or not self.tool_dispatcher:
                    break

                if tool_uses and self.tool_dispatcher:
```

This does four things:
1. Extracts raw tool_uses as before
2. Checks for `output_json` pseudo-tool — if found and not in tools_allowed, extracts its payload as final_content and removes it from raw_tool_uses (does NOT break — real tools may remain)
3. Filters remaining tool_uses to only those in tools_allowed (H-22's fix restored)
4. If no dispatchable tools remain after filtering, breaks the loop with whatever final_content we have (classify completes here; mixed responses dispatch real tools)

### Step 2: Add ledger selection to query_ledger

In `_staging/PKG-ADMIN-001/HOT/admin/main.py`, modify `_query_ledger()` (line 107):

**Before:**
```python
    def _query_ledger(args):
        from ledger_client import LedgerClient

        ledger = LedgerClient(ledger_path=root / "HOT" / "ledger" / "governance.jsonl")
        event_type = args.get("event_type")
        max_entries = int(args.get("max_entries", 10))
        if event_type:
            entries = ledger.read_by_event_type(str(event_type))[-max_entries:]
        else:
            entries = ledger.read_all()[-max_entries:]
        return {
            "status": "ok",
            "count": len(entries),
            "entries": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "submission_id": e.submission_id,
                    "decision": e.decision,
                    "reason": e.reason[:200] if e.reason else "",
                    "timestamp": e.timestamp,
                    "metadata_keys": sorted(e.metadata.keys()) if e.metadata else [],
                }
                for e in entries
            ],
        }
```

**After:**
```python
    def _query_ledger(args):
        from ledger_client import LedgerClient

        ledger_map = {
            "governance": root / "HOT" / "ledger" / "governance.jsonl",
            "ho2m": root / "HO2" / "ledger" / "ho2m.jsonl",
            "ho1m": root / "HO1" / "ledger" / "ho1m.jsonl",
        }
        source = args.get("ledger", "governance")
        ledger_path = ledger_map.get(source)
        if not ledger_path:
            return {"status": "error", "error": f"Unknown ledger: {source}. Valid: governance, ho2m, ho1m"}

        ledger = LedgerClient(ledger_path=ledger_path)
        event_type = args.get("event_type")
        max_entries = int(args.get("max_entries", 10))
        if event_type:
            entries = ledger.read_by_event_type(str(event_type))[-max_entries:]
        else:
            entries = ledger.read_all()[-max_entries:]
        return {
            "status": "ok",
            "source": source,
            "count": len(entries),
            "entries": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "submission_id": e.submission_id,
                    "decision": e.decision,
                    "reason": e.reason[:200] if e.reason else "",
                    "timestamp": e.timestamp,
                    "metadata_keys": sorted(e.metadata.keys()) if e.metadata else [],
                }
                for e in entries
            ],
        }
```

Also update the tool schema in `admin_config.json` for `query_ledger` to include the `ledger` parameter:

```json
{
    "tool_id": "query_ledger",
    "description": "Query ledger entries from governance, ho2m, or ho1m ledgers",
    "handler": "tools.query_ledger",
    "parameters": {
        "type": "object",
        "properties": {
            "event_type": {"type": "string"},
            "max_entries": {"type": "integer", "default": 10},
            "ledger": {
                "type": "string",
                "enum": ["governance", "ho2m", "ho1m"],
                "default": "governance",
                "description": "Which ledger to query: governance (system events), ho2m (session/turns), ho1m (execution traces)"
            }
        }
    }
}
```

### Step 3: Add list_files tool

In `_staging/PKG-ADMIN-001/HOT/admin/main.py`, add a `_list_files` handler inside `_register_admin_tools()`:

```python
    def _list_files(args):
        import fnmatch

        rel_path = args.get("path", ".")
        target = (root / rel_path).resolve()
        if not str(target).startswith(str(root.resolve())):
            return {"status": "error", "error": "path escapes root"}
        if not target.exists() or not target.is_dir():
            return {"status": "error", "error": "directory not found"}

        max_depth = min(int(args.get("max_depth", 3)), 5)
        pattern = args.get("glob", "*")
        files = []

        def _walk(dir_path, depth):
            if depth > max_depth:
                return
            try:
                for entry in sorted(dir_path.iterdir()):
                    rel = str(entry.relative_to(root))
                    if entry.is_dir():
                        if not entry.name.startswith(".") and entry.name != "__pycache__":
                            files.append({"path": rel + "/", "type": "dir"})
                            _walk(entry, depth + 1)
                    elif fnmatch.fnmatch(entry.name, pattern):
                        files.append({"path": rel, "type": "file", "size": entry.stat().st_size})
            except PermissionError:
                pass

        _walk(target, 1)
        return {"status": "ok", "root": rel_path, "count": len(files), "files": files[:500]}
```

Register it:
```python
    dispatcher.register_tool("list_files", _list_files)
```

Add to `admin_config.json` tools array:
```json
{
    "tool_id": "list_files",
    "description": "List files and directories under a path (bounded, root-relative)",
    "handler": "tools.list_files",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "default": ".",
                "description": "Relative path from plane root"
            },
            "max_depth": {
                "type": "integer",
                "default": 3,
                "description": "Maximum directory depth (1-5)"
            },
            "glob": {
                "type": "string",
                "default": "*",
                "description": "Filename pattern (e.g. *.py, *.json)"
            }
        }
    }
}
```

**IMPORTANT**: Because `admin_config.json` drives `tools_allowed` via:
```python
ho2_config = HO2Config(
    ...
    tools_allowed=[t["tool_id"] for t in cfg_dict.get("tools", [])],
)
```
Adding `list_files` to the config automatically exposes it to synthesize WOs through HO2. No additional wiring needed.

### Step 4: Update tests

**PKG-HO1-EXECUTOR-001** — update `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py`:

Add to a new class `TestOutputJsonNormalization`:
- `test_output_json_intercepted_as_structured_output` — output_json tool_use with no tools_allowed -> extracted as final_content, WO completes
- `test_output_json_payload_becomes_output_result` — output_result matches output_json input payload
- `test_output_json_ignored_when_in_tools_allowed` — if somehow output_json IS in tools_allowed, treat as normal tool (don't intercept)
- `test_output_json_with_real_tools_coexist` — response has both output_json and real tool_use blocks, only real tools dispatched

Add to `TestToolUseWiring` (restore regression tests):
- `test_tools_allowed_filter_restored` — tool_uses filtered to tools_allowed before dispatch
- `test_empty_tools_allowed_blocks_all_dispatch` — no tools_allowed -> no tools dispatched (even if tool_uses extracted)

**PKG-ADMIN-001** — update `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py`:

Add new class `TestQueryLedgerSelection`:
- `test_query_ledger_default_governance` — no ledger param -> reads governance
- `test_query_ledger_ho2m` — ledger=ho2m -> reads HO2 ledger
- `test_query_ledger_ho1m` — ledger=ho1m -> reads HO1 ledger
- `test_query_ledger_invalid_source` — unknown ledger -> error response
- `test_query_ledger_returns_source_field` — response includes "source" field

Add new class `TestListFilesTool`:
- `test_list_files_returns_directory_contents` — lists files in root
- `test_list_files_respects_max_depth` — depth=1 -> no subdirectory contents
- `test_list_files_glob_filter` — glob=*.py -> only .py files
- `test_list_files_escapes_root_blocked` — path=../../ -> error
- `test_list_files_nonexistent_dir` — missing dir -> error
- `test_list_files_in_admin_config` — tool_id "list_files" present in config tools array

### Step 5: Governance cycle

1. Update `manifest.json` hashes for PKG-HO1-EXECUTOR-001 and PKG-ADMIN-001
2. Delete `.DS_Store` and `__pycache__`, rebuild archives with `pack()`
3. Rebuild `CP_BOOTSTRAP.tar.gz`
4. Clean-room install to temp dir
5. `pytest` -- all tests pass
6. Run 8/8 governance gates

## 5. Package Plan

**No new packages.** Two existing packages modified:

### PKG-HO1-EXECUTOR-001 (modified)

| Field | Value |
|-------|-------|
| Package ID | PKG-HO1-EXECUTOR-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | ho1 |

Modified assets:
- `HO1/kernel/ho1_executor.py` -- output_json interception + tools_allowed filter restored
- `HO1/tests/test_ho1_executor.py` -- new tests

Dependencies: unchanged (PKG-KERNEL-001, PKG-TOKEN-BUDGETER-001, PKG-LLM-GATEWAY-001)

### PKG-ADMIN-001 (modified)

| Field | Value |
|-------|-------|
| Package ID | PKG-ADMIN-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HOT/admin/main.py` -- query_ledger ledger selection + list_files tool
- `HOT/config/admin_config.json` -- add list_files tool entry + update query_ledger schema
- `HOT/tests/test_admin.py` -- new tests

Dependencies: unchanged

## 6. Test Plan

### PKG-HO1-EXECUTOR-001 new tests (6)

| Test | Description | Expected |
|------|-------------|----------|
| `test_output_json_intercepted_as_structured_output` | output_json block, no tools_allowed -> WO completes | state=completed, output_result has classify fields |
| `test_output_json_payload_becomes_output_result` | output_json input payload matches output_result | output_result == {"speech_act":"greeting","ambiguity":"low"} |
| `test_output_json_ignored_when_in_tools_allowed` | output_json in tools_allowed -> dispatched normally | tool_dispatcher.execute called with "output_json" |
| `test_output_json_with_real_tools_coexist` | Both output_json and list_packages in response, tools_allowed=["list_packages"] | output_json intercepted, list_packages dispatched |
| `test_tools_allowed_filter_restored` | tool_uses with mixed IDs, tools_allowed=["t1"] -> only t1 dispatched | tool_dispatcher.execute called once with "t1" |
| `test_empty_tools_allowed_blocks_all_dispatch` | tool_uses extracted but tools_allowed=[] -> none dispatched | tool_dispatcher.execute not called |

### PKG-ADMIN-001 new tests (11)

| Test | Description | Expected |
|------|-------------|----------|
| `test_query_ledger_default_governance` | No ledger param -> governance path | Reads from HOT/ledger/governance.jsonl |
| `test_query_ledger_ho2m` | ledger=ho2m -> HO2 path | Reads from HO2/ledger/ho2m.jsonl |
| `test_query_ledger_ho1m` | ledger=ho1m -> HO1 path | Reads from HO1/ledger/ho1m.jsonl |
| `test_query_ledger_invalid_source` | ledger=bogus -> error | status=error with message |
| `test_query_ledger_returns_source_field` | Response includes source | result["source"] == "governance" |
| `test_list_files_returns_directory_contents` | list_files on populated dir | Returns file list with paths |
| `test_list_files_respects_max_depth` | max_depth=1 -> shallow | No nested subdirectory contents |
| `test_list_files_glob_filter` | glob=*.py -> filtered | Only .py files returned |
| `test_list_files_escapes_root_blocked` | path=../../etc -> error | status=error, "escapes root" |
| `test_list_files_nonexistent_dir` | missing path -> error | status=error, "not found" |
| `test_list_files_in_admin_config` | admin_config.json has list_files entry | tool_id "list_files" in tools array |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| HO1 executor (current) | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` | Lines 168-170 to fix |
| HO1 _extract_tool_uses | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py:356` | How tool_uses are extracted |
| HO1 tests (current) | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py` | Test patterns, TestGatewayHO1Integration for output_json test |
| Admin main.py (current) | `_staging/PKG-ADMIN-001/HOT/admin/main.py` | query_ledger at line 107, _register_admin_tools |
| Admin config (current) | `_staging/PKG-ADMIN-001/HOT/config/admin_config.json` | 4 tools currently registered |
| Admin config schema | `_staging/PKG-ADMIN-001/HOT/schemas/admin_config.schema.json` | Schema for validation |
| Admin tests (current) | `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py` | Test patterns |
| Tool dispatcher | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/tool_dispatch.py` | How tools register + execute |
| HO2 config wiring | `_staging/PKG-ADMIN-001/HOT/admin/main.py:221` | `tools_allowed=[t["tool_id"] for t in cfg_dict.get("tools", [])]` |
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
  python3 -m pytest "$TMPDIR" -v

# 3. Run gates
python3 "$TMPDIR/HOT/scripts/gate_check.py" --all --enforce --root "$TMPDIR"

# 4. E2E with real API (requires ANTHROPIC_API_KEY)
cd "$TMPDIR" && python3 -m admin.main --root "$TMPDIR" --dev
# Test sequence:
#   admin> hello
#     -> Verify: NO classify failure in logs, natural language response
#     -> Expected tool call: none (classify WO completes via output_json interception)
#   admin> what frameworks are installed?
#     -> Verify: list_packages tool executes, natural language response
#     -> Expected tool call: list_packages({})
#   admin> show me turn events from the session ledger
#     -> Verify: returns entries from HO2 ledger, NOT governance
#     -> Expected tool call: query_ledger({"ledger": "ho2m", "event_type": "TURN_RECORDED"})
#   admin> what files are in the kernel directory?
#     -> Verify: returns file listing with paths, types, sizes
#     -> Expected tool call: list_files({"path": "HOT/kernel"})
#   admin> /exit
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/` | MODIFY |
| `test_ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO1-EXECUTOR-001/` | MODIFY (hashes) |
| `main.py` | `_staging/PKG-ADMIN-001/HOT/admin/` | MODIFY |
| `admin_config.json` | `_staging/PKG-ADMIN-001/HOT/config/` | MODIFY |
| `test_admin.py` | `_staging/PKG-ADMIN-001/HOT/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-ADMIN-001/` | MODIFY (hashes) |
| `PKG-HO1-EXECUTOR-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-ADMIN-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_25.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **output_json is not a tool.** It's Anthropic's implementation detail for structured output. Intercept it before the tool dispatch path. Extract its payload as the structured result.
2. **Defense in depth.** Both the output_json interception AND the tools_allowed filter are needed. The interception handles the classify case correctly. The filter prevents any undeclared tool from reaching dispatch.
3. **Regressions are real.** H-22's tools_allowed filter was correct and necessary. H-23/H-24 dropped it. This handoff restores it and adds tests that will catch future regressions.
4. **Tools need discoverability.** `read_file` without `list_files` is like `cat` without `ls`. The agent needs both.
5. **Ledgers are per-tier by design.** The query tool must let the agent specify which tier's ledger to read. Default to governance for backward compatibility.
6. **Config drives tools_allowed.** Adding `list_files` to `admin_config.json` automatically wires it through HO2Config.tools_allowed -> synthesize WO constraints. No additional plumbing needed.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-25** -- Fix classify structured output + admin tool improvements

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_25_classify_fix_and_admin_tools.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design -> Test -> Then implement. Write tests FIRST.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` -- NEVER `tar czf ... -C dir .`
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir -> run install.sh -> install YOUR changes on top -> ALL gates must pass. This is NOT optional.
6. Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail, and whether you introduced new failures.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_25.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md. MUST include: Clean-Room Verification section, Baseline Snapshot section, Full Regression section.
8. CP_BOOTSTRAP rebuild: Rebuild CP_BOOTSTRAP.tar.gz and report the new SHA256.
9. Built-in tools: Use `hashing.py:compute_sha256()` for all SHA256 hashes and `packages.py:pack()` for all archives. NEVER use raw hashlib or shell tar.
10. When adding list_files tool, you MUST also add it to admin_config.json tools array. Otherwise HO2 will not include it in tools_allowed and the LLM will never see it.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What are the FOUR fixes in this handoff? Name each with its package and the specific code location.
2. Why do classify WOs currently fail? Trace the exact failure path from Anthropic response to turn_limit_exceeded.
3. What is output_json? Why is it NOT a real tool? What should HO1 do with it instead of dispatching it?
4. What happened to H-22's tools_allowed filter? Where was it, and what replaced it?
5. The query_ledger tool currently reads which ledger? Where are TURN_RECORDED events? Why can't the agent see them?
6. When you add list_files to admin_config.json, what downstream effect does that have on HO2Config.tools_allowed? Why is this necessary?
7. How many new tests are you adding to HO1? To ADMIN? List them by name.
8. What does the list_files tool return? What are its safety bounds (depth, root escape, output limit)?
9. Which TWO manifest.json files need updated hashes? Which TWO .tar.gz archives need rebuilding (plus CP_BOOTSTRAP)?
10. After all changes, what E2E admin shell sequence would verify all four fixes work?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers

1. (a) output_json interception — PKG-HO1-EXECUTOR-001, ho1_executor.py ~line 168. (b) Restore tools_allowed filter — same file, same location. (c) Ledger selection — PKG-ADMIN-001, main.py _query_ledger(). (d) list_files tool — PKG-ADMIN-001, main.py + admin_config.json.
2. Classify WO has structured_output in contract, no tools_allowed -> Anthropic returns tool_use name="output_json" -> _extract_tool_uses returns it -> no filter (H-22 filter lost) -> tool_dispatcher.execute("output_json") -> error (no handler) -> builds follow-up -> turn_limit=1 -> turn_limit_exceeded.
3. output_json is Anthropic's internal mechanism for structured output via tool_use. Not a real tool — has no handler, not in any config. HO1 should extract its `.input` (the JSON payload) as `final_content` and complete the WO.
4. H-22 added filtering at ~lines 172-179: `if tools_allowed: filter; else: tool_uses = []`. H-23 or H-24 modified ho1_executor.py and dropped this block. Current code at line 168-170 goes straight from extract to dispatch.
5. query_ledger reads `HOT/ledger/governance.jsonl`. TURN_RECORDED events are in `HO2/ledger/ho2m.jsonl`. Different ledgers — agent can't see its own conversation history.
6. main.py line 221: `tools_allowed=[t["tool_id"] for t in cfg_dict.get("tools", [])]`. Adding list_files to the config array automatically includes it in HO2Config.tools_allowed, which means synthesize WOs will include it in constraints.tools_allowed, which means the LLM will see it as an available tool.
7. HO1: 6 tests (output_json_intercepted, payload_becomes_result, ignored_when_allowed, coexist_with_real_tools, filter_restored, empty_blocks_all). ADMIN: 11 tests (5 query_ledger + 6 list_files).
8. Returns `{status, root, count, files: [{path, type, size?}]}`. Safety: max_depth capped at 5, root escape blocked via resolve() check, hidden dirs and __pycache__ skipped, output capped at 500 entries.
9. Manifests: PKG-HO1-EXECUTOR-001 and PKG-ADMIN-001. Archives: same two .tar.gz plus CP_BOOTSTRAP.tar.gz.
10. `admin> hello` (no classify failure — output_json intercepted), `admin> what frameworks are installed?` (list_packages tool dispatched), `admin> show me turn events from the session ledger` (query_ledger with ledger=ho2m — returns HO2 entries), `admin> what files are in the kernel directory?` (list_files with path=HOT/kernel — returns listing), `admin> /exit`. Key: verify expected tool calls match the arg shapes, not just natural language responses.
