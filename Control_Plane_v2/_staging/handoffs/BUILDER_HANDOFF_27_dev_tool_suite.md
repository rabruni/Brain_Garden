# BUILDER_HANDOFF_27: Dev Tool Suite — Write, Edit, Grep, Shell

## 1. Mission

Give the admin agent the ability to directly modify files, search codebases, and run shell commands within the governed plane root. Four new tools (write_file, edit_file, grep, run_shell) behind a dual gate: `tool_profile: "development"` in admin_config.json AND `CP_ADMIN_ENABLE_RISKY_TOOLS=1` environment variable. Either gate missing = tools not registered. Production deployments remove these tools by changing one config field.

One package modified: PKG-ADMIN-001.

**Independent of HANDOFF-26A and HANDOFF-26B** -- can run in parallel.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design -> Test -> Then implement.** Write/update tests FIRST.
3. **Package everything.** Modified package gets updated `manifest.json` SHA256 hashes. Use `hashing.py:compute_sha256()` and `packages.py:pack()`. NEVER raw hashlib or shell tar.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` -> `install.sh` -> all gates pass.
5. **No hardcoding.** Timeouts, size limits, path restrictions -- all from config or tool parameters.
6. **No file replacement.** In-package modifications only.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` -- never with `./` prefix.
8. **Results file.** Write `_staging/handoffs/RESULTS_HANDOFF_27.md`.
9. **Full regression test.** Run ALL staged package tests. Report pass/fail.
10. **Baseline snapshot.** Include in results file.
11. **Dual gate is non-negotiable.** Both `tool_profile: "development"` AND `CP_ADMIN_ENABLE_RISKY_TOOLS=1` env var must be true for dev tools to register. Missing either = tools not available. This is the safety mechanism.
12. **All writes must stay within plane root.** Path traversal (`../`) must be blocked. `write_file` and `edit_file` resolve paths and check `startswith(root.resolve())`.
13. **run_shell must have a timeout.** Default 30 seconds, configurable via parameter, hard cap at 120 seconds.
14. **Existing tools unchanged.** The five current tools (gate_check, read_file, query_ledger, list_files, list_packages) are untouched.

## 3. Architecture / Design

### Dual Gate Mechanism

```
build_session_host_v2() checks:
  1. admin_config.json -> "tool_profile": "development"
  2. os.environ.get("CP_ADMIN_ENABLE_RISKY_TOOLS") == "1"

  Both true  -> call _register_dev_tools(dispatcher, root)
  Either false -> skip registration, tools don't exist
```

**Why dual gate?**
- Config alone is not enough: a committed config file with `tool_profile: development` could accidentally ship to production. The env var is the runtime guard.
- Env var alone is not enough: the config should explicitly declare the deployment profile. An env var without config intent is a mistake.
- Removing from production: change `tool_profile` to `"production"` in config. Done. No code changes needed.

### Tool Contracts

#### 1. write_file

**Purpose:** Create or overwrite a file within the plane root.

**Input:**
```json
{
  "path": "HO2/scratch/notes.txt",
  "content": "file content here",
  "create_dirs": true
}
```

**Output:**
```json
{
  "status": "ok",
  "path": "HO2/scratch/notes.txt",
  "bytes_written": 17,
  "created_dirs": true
}
```

**Security:**
- Path resolved against root. `../` traversal blocked.
- Forbidden paths from `admin_config.json` permissions.forbidden are enforced: writing to `HOT/kernel/*` or `HOT/scripts/*` is rejected.
- Binary content not supported (text-only). Files > 1MB rejected.

#### 2. edit_file

**Purpose:** Find-and-replace within a file. Exact string match, not regex.

**Input:**
```json
{
  "path": "HO2/kernel/some_file.py",
  "old_string": "def old_name(",
  "new_string": "def new_name(",
  "replace_all": false
}
```

**Output:**
```json
{
  "status": "ok",
  "path": "HO2/kernel/some_file.py",
  "replacements": 1,
  "bytes_before": 2400,
  "bytes_after": 2400
}
```

**Security:**
- Same path restrictions as write_file.
- `old_string` must exist in the file (error if not found).
- When `replace_all` is false, `old_string` must be unique (error if multiple matches). This prevents ambiguous edits.

#### 3. grep

**Purpose:** Server-side regex search across files in the plane root. Returns matching lines without stuffing file content into LLM context.

**Input:**
```json
{
  "pattern": "def handle_turn",
  "path": "HO2/kernel",
  "glob": "*.py",
  "max_results": 50,
  "context_lines": 2
}
```

**Output:**
```json
{
  "status": "ok",
  "pattern": "def handle_turn",
  "match_count": 2,
  "files_searched": 8,
  "results": [
    {
      "file": "HO2/kernel/ho2_supervisor.py",
      "line_number": 128,
      "line": "    def handle_turn(self, session_id: str, user_message: str) -> TurnResult:",
      "context_before": ["", ""],
      "context_after": ["        ...", "        ..."]
    }
  ]
}
```

**Logic:**
- Walk `root / path` recursively, filtering by glob pattern (default `*`).
- Apply regex to each line.
- Return matches with file path, line number, matching line, and optional context lines.
- Skip binary files, `.git/`, `__pycache__/`, and files > 1MB.
- Path must stay within root (same traversal check).

#### 4. run_shell

**Purpose:** Execute a shell command with timeout. Captures stdout, stderr, exit code.

**Input:**
```json
{
  "command": "python3 -m pytest HO2/tests/ -v --tb=short",
  "timeout": 60,
  "cwd": "."
}
```

**Output:**
```json
{
  "status": "ok",
  "exit_code": 0,
  "stdout": "...",
  "stderr": "...",
  "timed_out": false,
  "duration_seconds": 4.2
}
```

**Security:**
- `cwd` resolved against root. Traversal blocked.
- Timeout default: 30 seconds. Max: 120 seconds. Commands that exceed timeout are killed.
- stdout + stderr capped at 50000 chars each. Truncated with `[TRUNCATED at 50000 chars]` marker.
- No restrictions on which commands can be run -- the dual gate IS the restriction. If you have the gate, you have full access within the root. This is intentional: dev tools that can't run arbitrary commands aren't useful.

### Adversarial Analysis: Unrestricted run_shell

**Hurdles**: run_shell with no command restrictions is powerful. A misconfigured agent could `rm -rf` the plane root. Mitigation: the dual gate ensures only intentional dev deployments have this tool. The 120-second timeout prevents runaway processes.
**Not Enough**: If we restrict run_shell to a whitelist of commands (only pytest, only git), we lose the value. The whole point is that the admin agent can do what Claude Code does -- run tests, check git status, inspect processes, install dependencies. A restricted shell is barely better than no shell.
**Too Much**: We could add command parsing, sandbox execution, or container isolation. All of these are production-grade hardening that belongs in a future security handoff, not in a dev tool MVP.
**Synthesis**: Ship unrestricted run_shell behind the dual gate. The gate is the safety boundary. Document the removal path (change one config field). Future hardening is a separate handoff.

### Config Changes

Add `tool_profile` field to admin_config.json (top-level):

```json
{
  "agent_id": "admin-001",
  "agent_class": "ADMIN",
  "tool_profile": "development",
  ...
}
```

**CRITICAL: Dev tool entries do NOT go in the static `tools` array.** They are defined in code inside `_register_dev_tools()` and injected dynamically only when the dual gate passes. This prevents tools_allowed leakage: if dev tool configs were in the static `tools` array, line 293 of main.py (`tools_allowed=[t["tool_id"] for t in cfg_dict.get("tools", [])]`) would expose them to HO2 and the LLM even when the gate fails. The LLM would see `write_file_dev` in its tool list, try to call it, and fail because no handler is registered.

**The fix:** `_register_dev_tools()` returns a list of dev tool config dicts. `build_session_host_v2()` appends them to the tools list AFTER the gate check and BEFORE constructing HO2Config.tools_allowed. When the gate fails, dev tools don't exist anywhere -- not in the dispatcher, not in tools_allowed, not in tool schemas sent to the LLM.

Similarly, the ToolDispatcher at line 253 (`ToolDispatcher(tool_configs=cfg_dict.get("tools", []))`) is constructed BEFORE the gate check, so it only receives core tool configs. Dev tool configs are injected into the dispatcher by `_register_dev_tools()` via `dispatcher.register_tool()`.

### Tool ID Naming

Dev tools use `_dev` suffix: `write_file_dev`, `edit_file_dev`, `grep_dev`, `run_shell_dev`. This:
- Prevents collision with any future production tools named `write_file`, `edit_file`, etc.
- Makes it immediately obvious in logs which tools are development-only.
- When production tools are built later, they can use the unsuffixed names with different security models.

## 4. Implementation Steps

### Step 1: Add dual gate check to main.py

In `_staging/PKG-ADMIN-001/HOT/admin/main.py`, in `build_session_host_v2()`, after `_register_admin_tools(dispatcher, root=root)` (line 256) and BEFORE HO2Config construction (line 288), add:

```python
# Dev tools: dual gate check
import os
tool_profile = cfg_dict.get("tool_profile", "production")
env_flag = os.environ.get("CP_ADMIN_ENABLE_RISKY_TOOLS", "0")
dev_tool_configs = []
if tool_profile == "development" and env_flag == "1":
    dev_tool_configs = _register_dev_tools(dispatcher, root=root, permissions=cfg_dict.get("permissions", {}))

# Merge dev tool configs into the tools list for tools_allowed construction
all_tools = cfg_dict.get("tools", []) + dev_tool_configs
```

Then update HO2Config construction (line 293) to use `all_tools` instead of `cfg_dict.get("tools", [])`:

```python
ho2_config = HO2Config(
    ...
    tools_allowed=[t["tool_id"] for t in all_tools],
    ...
)
```

**Why this ordering matters:** ToolDispatcher is constructed at line 251 with only core tool configs. Dev tool handlers are registered by `_register_dev_tools()`. HO2Config.tools_allowed is built from `all_tools` which includes dev tools only if the gate passed. Result: when the gate fails, dev tools exist nowhere in the system.

### Step 2: Implement _register_dev_tools function

Add function in main.py (after `_register_admin_tools`):

```python
def _register_dev_tools(dispatcher, root: Path, permissions: dict) -> list[dict]:
    """Register development-only tools. Only called when dual gate passes.

    Returns list of tool config dicts for tools_allowed construction.
    """

    forbidden_patterns = permissions.get("forbidden", [])

    def _is_forbidden(rel_path: str) -> bool:
        import fnmatch
        for pattern in forbidden_patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
        return False

    def _resolve_safe(rel: str) -> tuple[Path | None, str | None]:
        """Resolve path relative to root, block traversal."""
        resolved_root = root.resolve()
        target = (root / rel).resolve()
        if not str(target).startswith(str(resolved_root)):
            return None, "path escapes root"
        return target, None
```

**2a. write_file_dev handler:**
```python
    def _write_file_dev(args):
        rel = str(args.get("path", ""))
        content = str(args.get("content", ""))
        create_dirs = bool(args.get("create_dirs", False))

        if not rel:
            return {"status": "error", "error": "path is required"}
        if len(content) > 1_000_000:
            return {"status": "error", "error": "content exceeds 1MB limit"}
        if _is_forbidden(rel):
            return {"status": "error", "error": f"path matches forbidden pattern: {rel}"}

        target, err = _resolve_safe(rel)
        if err:
            return {"status": "error", "error": err}

        created_dirs = False
        if create_dirs and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            created_dirs = True

        target.write_text(content)
        return {
            "status": "ok",
            "path": rel,
            "bytes_written": len(content.encode("utf-8")),
            "created_dirs": created_dirs,
        }
```

**2b. edit_file_dev handler:**
```python
    def _edit_file_dev(args):
        rel = str(args.get("path", ""))
        old_string = str(args.get("old_string", ""))
        new_string = str(args.get("new_string", ""))
        replace_all = bool(args.get("replace_all", False))

        if not rel or not old_string:
            return {"status": "error", "error": "path and old_string are required"}
        if _is_forbidden(rel):
            return {"status": "error", "error": f"path matches forbidden pattern: {rel}"}

        target, err = _resolve_safe(rel)
        if err:
            return {"status": "error", "error": err}
        if not target.exists() or not target.is_file():
            return {"status": "error", "error": "file not found"}

        original = target.read_text()
        count = original.count(old_string)
        if count == 0:
            return {"status": "error", "error": "old_string not found in file"}
        if not replace_all and count > 1:
            return {"status": "error", "error": f"old_string found {count} times; use replace_all=true or provide more context"}

        if replace_all:
            result = original.replace(old_string, new_string)
        else:
            result = original.replace(old_string, new_string, 1)

        target.write_text(result)
        return {
            "status": "ok",
            "path": rel,
            "replacements": count if replace_all else 1,
            "bytes_before": len(original.encode("utf-8")),
            "bytes_after": len(result.encode("utf-8")),
        }
```

**2c. grep_dev handler:**
```python
    def _grep_dev(args):
        import re
        pattern_str = str(args.get("pattern", ""))
        rel = str(args.get("path", "."))
        file_glob = str(args.get("glob", "*"))
        max_results = min(int(args.get("max_results", 50)), 200)
        context_lines = min(int(args.get("context_lines", 0)), 5)

        if not pattern_str:
            return {"status": "error", "error": "pattern is required"}

        try:
            regex = re.compile(pattern_str)
        except re.error as e:
            return {"status": "error", "error": f"invalid regex: {e}"}

        target, err = _resolve_safe(rel)
        if err:
            return {"status": "error", "error": err}
        if not target.exists():
            return {"status": "error", "error": "path not found"}

        import fnmatch
        results = []
        files_searched = 0
        skip_dirs = {".git", "__pycache__", ".DS_Store", "node_modules"}

        def search_file(fpath: Path):
            nonlocal files_searched
            try:
                if fpath.stat().st_size > 1_000_000:
                    return
                text = fpath.read_text(errors="replace")
            except (PermissionError, OSError):
                return
            files_searched += 1
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if len(results) >= max_results:
                    return
                if regex.search(line):
                    resolved_root = root.resolve()
                    rel_file = str(fpath.resolve().relative_to(resolved_root))
                    ctx_before = lines[max(0, i - context_lines):i] if context_lines else []
                    ctx_after = lines[i + 1:i + 1 + context_lines] if context_lines else []
                    results.append({
                        "file": rel_file,
                        "line_number": i + 1,
                        "line": line,
                        "context_before": ctx_before,
                        "context_after": ctx_after,
                    })

        if target.is_file():
            search_file(target)
        else:
            for fpath in sorted(target.rglob("*")):
                if len(results) >= max_results:
                    break
                if any(skip in fpath.parts for skip in skip_dirs):
                    continue
                if fpath.is_file() and fnmatch.fnmatch(fpath.name, file_glob):
                    search_file(fpath)

        return {
            "status": "ok",
            "pattern": pattern_str,
            "match_count": len(results),
            "files_searched": files_searched,
            "results": results,
        }
```

**2d. run_shell_dev handler:**
```python
    def _run_shell_dev(args):
        import subprocess
        import time

        command = str(args.get("command", ""))
        timeout_sec = min(int(args.get("timeout", 30)), 120)
        cwd_rel = str(args.get("cwd", "."))
        max_output = 50000

        if not command:
            return {"status": "error", "error": "command is required"}

        cwd_target, err = _resolve_safe(cwd_rel)
        if err:
            return {"status": "error", "error": f"cwd: {err}"}
        if not cwd_target.is_dir():
            return {"status": "error", "error": "cwd is not a directory"}

        start = time.time()
        timed_out = False
        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout_sec, cwd=str(cwd_target),
            )
            stdout = proc.stdout
            stderr = proc.stderr
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            stdout = ""
            stderr = f"Command timed out after {timeout_sec} seconds"
            exit_code = -1
        duration = round(time.time() - start, 2)

        if len(stdout) > max_output:
            stdout = stdout[:max_output] + f"\n[TRUNCATED at {max_output} chars]"
        if len(stderr) > max_output:
            stderr = stderr[:max_output] + f"\n[TRUNCATED at {max_output} chars]"

        return {
            "status": "ok",
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "duration_seconds": duration,
        }
```

**2e. Register all four and return configs:**
```python
    dispatcher.register_tool("write_file_dev", _write_file_dev)
    dispatcher.register_tool("edit_file_dev", _edit_file_dev)
    dispatcher.register_tool("grep_dev", _grep_dev)
    dispatcher.register_tool("run_shell_dev", _run_shell_dev)

    # Return tool configs for tools_allowed construction
    return [
        {"tool_id": "write_file_dev", "description": "Write or create a file within the plane root (dev only)",
         "handler": "tools.write_file_dev", "profile": "development",
         "parameters": {"type": "object", "properties": {
             "path": {"type": "string", "description": "Relative path from plane root"},
             "content": {"type": "string", "description": "File content to write"},
             "create_dirs": {"type": "boolean", "default": False, "description": "Create parent directories if needed"}},
             "required": ["path", "content"]}},
        {"tool_id": "edit_file_dev", "description": "Find-and-replace in a file (dev only)",
         "handler": "tools.edit_file_dev", "profile": "development",
         "parameters": {"type": "object", "properties": {
             "path": {"type": "string", "description": "Relative path from plane root"},
             "old_string": {"type": "string", "description": "Exact string to find"},
             "new_string": {"type": "string", "description": "Replacement string"},
             "replace_all": {"type": "boolean", "default": False, "description": "Replace all occurrences"}},
             "required": ["path", "old_string", "new_string"]}},
        {"tool_id": "grep_dev", "description": "Search file contents with regex (dev only)",
         "handler": "tools.grep_dev", "profile": "development",
         "parameters": {"type": "object", "properties": {
             "pattern": {"type": "string", "description": "Regex pattern to search for"},
             "path": {"type": "string", "default": ".", "description": "Relative path to search in"},
             "glob": {"type": "string", "default": "*", "description": "Filename glob filter"},
             "max_results": {"type": "integer", "default": 50, "description": "Max matching lines (cap 200)"},
             "context_lines": {"type": "integer", "default": 0, "description": "Lines of context (0-5)"}},
             "required": ["pattern"]}},
        {"tool_id": "run_shell_dev", "description": "Run a shell command with timeout (dev only)",
         "handler": "tools.run_shell_dev", "profile": "development",
         "parameters": {"type": "object", "properties": {
             "command": {"type": "string", "description": "Shell command to execute"},
             "timeout": {"type": "integer", "default": 30, "description": "Timeout in seconds (max 120)"},
             "cwd": {"type": "string", "default": ".", "description": "Working directory (relative to plane root)"}},
             "required": ["command"]}},
    ]
```

### Step 3: Add tool_profile field to admin_config.json

Add `"tool_profile": "development"` as a top-level field in admin_config.json. That is the ONLY config change.

**Do NOT add dev tool entries to the static `tools` array.** Dev tool configs are defined in code inside `_register_dev_tools()` and returned for dynamic injection. This is the fix for the tools_allowed leakage bug: if they were in the static array, HO2 would expose them to the LLM even when the gate fails.

### Step 4: Update tests

Add test classes in `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py`.
See Section 6 for full test list.

### Step 5: Governance cycle

1. Update `manifest.json` hashes for PKG-ADMIN-001
2. Delete `.DS_Store` and `__pycache__`, rebuild archive with `pack()`
3. Rebuild `CP_BOOTSTRAP.tar.gz`
4. Clean-room install to temp dir
5. `pytest` -- all tests pass
6. Run 8/8 governance gates

## 5. Package Plan

**No new packages.** One existing package modified:

### PKG-ADMIN-001 (modified)
| Field | Value |
|-------|-------|
| Package ID | PKG-ADMIN-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HOT/admin/main.py` -- dual gate + 4 dev tool handlers + _register_dev_tools (returns tool configs)
- `HOT/config/admin_config.json` -- tool_profile field only (dev tools NOT in static tools array)
- `HOT/tests/test_admin.py` -- new tests

Dependencies: unchanged

## 6. Test Plan

### PKG-ADMIN-001 new tests (28)

**TestDualGate (6):**

| Test | Description | Expected |
|------|-------------|----------|
| `test_dev_tools_registered_when_both_gates_pass` | tool_profile=development + env=1 -> 4 dev tools available | dispatcher has write_file_dev, edit_file_dev, grep_dev, run_shell_dev |
| `test_dev_tools_not_registered_without_env_var` | tool_profile=development + env unset -> no dev tools | dispatcher does NOT have dev tools AND tools_allowed excludes them |
| `test_dev_tools_not_registered_without_config` | tool_profile=production + env=1 -> no dev tools | dispatcher does NOT have dev tools AND tools_allowed excludes them |
| `test_dev_tools_not_registered_default_profile` | no tool_profile field + env=1 -> no dev tools | Defaults to "production", no dev tools, no tools_allowed leakage |
| `test_existing_tools_always_registered` | Any gate state -> 5 core tools present | gate_check, read_file, etc. always available |
| `test_dev_tools_coexist_with_core_tools` | Both gates pass -> 9 total tools | 5 core + 4 dev all registered |

**TestWriteFileDev (6):**

| Test | Description | Expected |
|------|-------------|----------|
| `test_write_file_creates_new` | Write to non-existent file -> created | File exists, content matches |
| `test_write_file_overwrites` | Write to existing file -> replaced | New content, bytes_written correct |
| `test_write_file_creates_dirs` | create_dirs=true with nested path -> dirs created | Parent dirs exist, created_dirs=true |
| `test_write_file_blocks_traversal` | path=../../etc/passwd -> error | status=error, "path escapes root" |
| `test_write_file_blocks_forbidden` | path=HOT/kernel/test.py -> error | status=error, "forbidden pattern" |
| `test_write_file_rejects_oversized` | content > 1MB -> error | status=error, "exceeds 1MB limit" |

**TestEditFileDev (5):**

| Test | Description | Expected |
|------|-------------|----------|
| `test_edit_file_replaces_unique` | Single match, replace_all=false -> 1 replacement | replacements=1, content updated |
| `test_edit_file_replaces_all` | 3 matches, replace_all=true -> 3 replacements | replacements=3 |
| `test_edit_file_not_found` | Non-existent file -> error | status=error, "file not found" |
| `test_edit_file_old_string_missing` | old_string not in file -> error | status=error, "not found in file" |
| `test_edit_file_ambiguous_without_replace_all` | 2 matches, replace_all=false -> error | status=error, "found 2 times" |

**TestGrepDev (5):**

| Test | Description | Expected |
|------|-------------|----------|
| `test_grep_finds_matches` | Pattern in 2 files -> 2+ results | match_count >= 2, results have file + line_number |
| `test_grep_with_context` | context_lines=2 -> before/after populated | context_before and context_after non-empty |
| `test_grep_respects_glob` | glob=*.py only searches .py files | No .txt matches returned |
| `test_grep_invalid_regex` | pattern=[invalid -> error | status=error, "invalid regex" |
| `test_grep_blocks_traversal` | path=../../ -> error | status=error, "path escapes root" |

**TestRunShellDev (6):**

| Test | Description | Expected |
|------|-------------|----------|
| `test_run_shell_success` | echo hello -> exit 0, stdout=hello | exit_code=0, stdout contains "hello" |
| `test_run_shell_captures_stderr` | command that writes stderr -> captured | stderr non-empty |
| `test_run_shell_timeout` | sleep 999 with timeout=1 -> timed_out | timed_out=true, exit_code=-1 |
| `test_run_shell_cwd` | cwd set to subdir -> runs there | Output reflects correct working directory |
| `test_run_shell_cwd_traversal` | cwd=../../ -> error | status=error, "path escapes root" |
| `test_run_shell_truncates_output` | Command producing > 50000 chars -> truncated | stdout contains "TRUNCATED" marker |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Admin main.py | `_staging/PKG-ADMIN-001/HOT/admin/main.py` | _register_admin_tools pattern at :77, build_session_host_v2 at :208 |
| Admin config | `_staging/PKG-ADMIN-001/HOT/config/admin_config.json` | Existing tool config structure |
| Admin tests | `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py` | Test patterns for tool handlers |
| read_file handler | `_staging/PKG-ADMIN-001/HOT/admin/main.py:98` | Path resolution + traversal check pattern |
| list_files handler | `_staging/PKG-ADMIN-001/HOT/admin/main.py:148` | Recursive walk pattern, skip .DS_Store/__pycache__ |
| Kernel hashing | `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py` | compute_sha256() |
| Kernel packages | `_staging/PKG-KERNEL-001/HOT/kernel/packages.py` | pack() |

## 8. End-to-End Verification

```bash
# 1. Clean-room install
TMPDIR=$(mktemp -d)
cd Control_Plane_v2/_staging
tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
cd "$TMPDIR" && bash install.sh --root "$TMPDIR" --dev

# 2. Run all tests
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 -m pytest "$TMPDIR/HOT/tests/" "$TMPDIR/HO1/tests/" "$TMPDIR/HO2/tests/" -v

# 3. Run gates
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 "$TMPDIR/HOT/scripts/gate_check.py" --all --enforce --root "$TMPDIR"

# 4. Verify tool_profile in config + dual gate via unit tests
python3 -c "
import json
d = json.load(open('$TMPDIR/HOT/config/admin_config.json'))
assert d.get('tool_profile') == 'development', 'tool_profile not set'
# Dev tools are NOT in the static tools array (that's the fix for tools_allowed leakage).
# They are injected dynamically by _register_dev_tools() only when both gates pass.
# The dual gate is verified by unit tests (TestDualGate class), not by config inspection.
static_tools = [t['tool_id'] for t in d['tools']]
for dev_tool in ['write_file_dev', 'edit_file_dev', 'grep_dev', 'run_shell_dev']:
    assert dev_tool not in static_tools, f'{dev_tool} should NOT be in static tools array'
print(f'tool_profile=development, {len(static_tools)} static tools, dev tools correctly absent from static config')
"

# 6. E2E with real API (requires ANTHROPIC_API_KEY + CP_ADMIN_ENABLE_RISKY_TOOLS=1)
CP_ADMIN_ENABLE_RISKY_TOOLS=1 python3 -m admin.main --root "$TMPDIR" --dev
# Verification:
#   admin> write a file at HO2/scratch/test.txt with the content "hello from admin"
#     -> Expected tool call: write_file_dev({"path": "HO2/scratch/test.txt", "content": "hello from admin", "create_dirs": true})
#     -> Verify: bytes_written in response
#   admin> search for "def handle_turn" in the HO2 directory
#     -> Expected tool call: grep_dev({"pattern": "def handle_turn", "path": "HO2/kernel", "glob": "*.py"})
#     -> Verify: match in ho2_supervisor.py
#   admin> run the gate check
#     -> Expected tool call: gate_check({"gate": "all"})
#     -> Verify: existing core tool still works alongside dev tools
#   admin> /exit
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `main.py` | `_staging/PKG-ADMIN-001/HOT/admin/` | MODIFY |
| `admin_config.json` | `_staging/PKG-ADMIN-001/HOT/config/` | MODIFY |
| `test_admin.py` | `_staging/PKG-ADMIN-001/HOT/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-ADMIN-001/` | MODIFY (hashes) |
| `PKG-ADMIN-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_27.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Dual gate = defense in depth.** Neither config alone nor env var alone enables dev tools. Both must agree. This prevents accidental exposure.
2. **Easy removal path.** Change `tool_profile` to `"production"` and the four dev tools vanish from tools_allowed, the dispatcher, and the LLM's tool list. No code changes, no package rebuild, just config. This works because dev tool configs are injected dynamically, not stored in the static config array.
3. **Root-bounded.** Every file operation resolves against the plane root. Path traversal is blocked at the handler level, not by caller discipline.
4. **Permissions respected.** write_file_dev and edit_file_dev enforce the same forbidden patterns as read_file. HOT/kernel/* is protected.
5. **Timeout everything.** run_shell has a hard 120-second cap. No unbounded execution.
6. **_dev suffix.** Dev tools are visually distinct in logs and config. No confusion about which tools are dev-only.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-27** -- Dev tool suite: write, edit, grep, shell

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_27_dev_tool_suite.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design -> Test -> Then implement. Write tests FIRST.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` -- NEVER `tar czf ... -C dir .`
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir -> run install.sh -> install YOUR changes on top -> ALL gates must pass. This is NOT optional.
6. Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail, and whether you introduced new failures.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_27.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md.
8. CP_BOOTSTRAP rebuild: Rebuild CP_BOOTSTRAP.tar.gz and report the new SHA256.
9. Built-in tools: Use `hashing.py:compute_sha256()` for all SHA256 hashes and `packages.py:pack()` for all archives.
10. The dual gate (tool_profile + env var) is non-negotiable. Both must be checked. Test both-present, config-missing, and env-missing cases explicitly.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What are the FOUR dev tools this handoff adds? What suffix do their tool_ids use and why?
2. What is the dual gate? What TWO conditions must BOTH be true for dev tools to register?
3. If a production deployment has CP_ADMIN_ENABLE_RISKY_TOOLS=1 set but tool_profile is "production", are dev tools available? Why or why not?
4. How does write_file_dev prevent path traversal? How does it enforce the forbidden list from permissions?
5. What happens when edit_file_dev finds old_string 3 times and replace_all is false?
6. What does grep_dev skip when walking directories? What is the file size limit?
7. What is run_shell_dev's default timeout? Maximum timeout? What happens when a command exceeds it?
8. How many new tests are you adding? List the test class names and their counts.
9. How would a production deployment disable dev tools? What single config change is needed?
10. After this handoff, how many total tools will ADMIN have in admin_config.json? List all tool_ids.

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers

1. write_file_dev, edit_file_dev, grep_dev, run_shell_dev. The `_dev` suffix prevents collision with future production tools and makes dev-only tools immediately obvious in logs and config.
2. The dual gate requires: (1) `tool_profile: "development"` in admin_config.json, AND (2) `CP_ADMIN_ENABLE_RISKY_TOOLS=1` environment variable. Both must be true.
3. No. The dual gate requires BOTH conditions. tool_profile="production" fails the config check, so dev tools are not registered regardless of the env var.
4. Path is resolved via `(root / rel).resolve()` and checked with `startswith(str(root.resolve()))`. If the resolved path is outside root, it returns an error. The forbidden list from `permissions.forbidden` (e.g., `HOT/kernel/*`) is checked with fnmatch before any write.
5. Returns an error: "old_string found 3 times; use replace_all=true or provide more context". When replace_all is false, the match must be unique to prevent ambiguous edits.
6. Skips `.git/`, `__pycache__/`, `.DS_Store`, `node_modules/`. File size limit is 1MB -- files larger than that are skipped silently.
7. Default timeout: 30 seconds. Maximum: 120 seconds (hard cap). When exceeded, the process is killed, timed_out=true, exit_code=-1, stderr contains the timeout message.
8. 28 tests across 5 test classes: TestDualGate (6), TestWriteFileDev (6), TestEditFileDev (5), TestGrepDev (5), TestRunShellDev (6).
9. Change `tool_profile` from `"development"` to `"production"` in admin_config.json. No code changes needed. Dev tools vanish from tools_allowed because `_register_dev_tools()` never runs, so no tool configs are returned for injection.
10. Static admin_config.json `tools` array has 5 entries (unchanged core tools): gate_check, read_file, query_ledger, list_files, list_packages. At runtime when both gates pass, `_register_dev_tools()` injects 4 more into tools_allowed: write_file_dev, edit_file_dev, grep_dev, run_shell_dev = 9 total. When gate fails, only the 5 core tools exist anywhere in the system.
