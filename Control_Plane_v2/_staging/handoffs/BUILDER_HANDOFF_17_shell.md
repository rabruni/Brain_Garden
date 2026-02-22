# BUILDER_HANDOFF_17: PKG-SHELL-001 — Human-Facing Command Shell

## 1. Mission

Create `PKG-SHELL-001` — a human-facing command shell that replaces the direct REPL loop in PKG-ADMIN-001's `main.py` with a proper command parser. The Shell receives dependencies via constructor injection (SessionHostV2, AgentConfig, I/O functions), parses user input into cognitive turns or admin commands, and formats output for display. ADMIN agent class only for MVP. Under 200 lines of implementation code.

After this handoff, the presentation layer is cleanly separated from config loading and cognitive dispatch.

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design -> Test -> Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** New code ships as packages in `_staging/PKG-SHELL-001/` with manifest.json, SHA256 hashes, proper dependencies. Follow existing package patterns.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` -> install all layers -> install PKG-SHELL-001. All gates must pass.
5. **No hardcoding.** Prompt strings, command prefixes, help text — all derivable from config or constants at the top of the module. No magic strings buried in logic.
6. **No file replacement.** Packages must NEVER overwrite another package's files. Use state-gating instead.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`).
8. **Results file.** When finished, write `_staging/RESULTS_HANDOFF_17.md` (see `BUILDER_HANDOFF_STANDARD.md`).
9. **Full regression test.** Run ALL staged package tests (not just yours) and report results.
10. **Baseline snapshot.** Your results file must include a baseline snapshot.

**Task-specific constraints:**

11. **Shell does NOT load config.** Shell receives SessionHostV2, AgentConfig, and I/O functions via constructor injection. Config loading stays in main.py. This is the entire point of the separation.
12. **Shell does NOT modify main.py.** The spec notes that main.py will need rewiring to use Shell, but that is a separate followup task. This package creates the Shell class only.
13. **Under 200 lines.** Shell is a presentation concern. If the implementation exceeds 200 lines, scope is too large.
14. **ADMIN only.** No RESIDENT support, no multi-agent switching, no rich TUI. All deferred.

---

## 3. Architecture / Design

### Shell Responsibilities

The Shell is a **presentation layer**. It owns:

- REPL loop (read input, dispatch, print output)
- Command parsing (`/` prefix = admin command, everything else = cognitive turn)
- Output formatting (extract response text from TurnResult, optionally show cost)
- Session lifecycle calls (delegates to SessionHostV2)

The Shell does NOT own:

- Config loading (main.py)
- Cognitive dispatch (HO2 Supervisor via SessionHostV2)
- LLM calls (HO1 via LLM Gateway)
- Session state (HO2 Supervisor)

### Data Flow

```
User types "hello"
  -> Shell.run() reads input
  -> Not a `/` command -> cognitive turn
  -> Shell calls session_host_v2.process_turn("hello")
  -> SessionHostV2 delegates to HO2 -> HO1 -> LLM -> back up
  -> SessionHostV2 returns TurnResult
  -> Shell formats TurnResult.response for display
  -> Shell prints to output_fn
  -> Loop back to read next input

User types "/help"
  -> Shell.run() reads input
  -> Starts with `/` -> admin command
  -> Shell parses command name "help"
  -> Shell dispatches to _handle_help()
  -> Shell prints help text via output_fn
  -> Loop back
```

### REPL Loop Structure

```
Shell.__init__(session_host_v2, agent_config, input_fn=input, output_fn=print)

Shell.run():
  1. session_id = session_host_v2.start_session(agent_config)
  2. output_fn(f"Session started: {session_id}")
  3. Loop:
     a. raw = input_fn("admin> ")
     b. text = raw.strip()
     c. if text == "": continue
     d. if text starts with "/": _dispatch_command(text)
     e. else: _dispatch_turn(text)
  4. On exit (/exit, EOFError, KeyboardInterrupt):
     session_host_v2.end_session()
     output_fn("Session ended.")
```

### Command Table

| Command | Handler | Behavior |
|---------|---------|----------|
| `/exit` | `_handle_exit()` | Sets running flag to False, breaks REPL loop |
| `/help` | `_handle_help()` | Prints available commands and usage |
| `/show frameworks` | `_handle_show_frameworks()` | Placeholder — prints "Not yet implemented" |
| Unknown `/cmd` | `_handle_unknown(cmd)` | Prints "Unknown command: {cmd}. Type /help for available commands." |

Admin commands are intentionally minimal for MVP. The command table is a dict mapping command strings to handler methods — extensible without changing the parser.

### Adversarial Analysis: Separation from main.py

**Hurdles**: Current main.py couples config loading, import path setup, and the REPL loop. Shell must be usable without any of that — it receives fully constructed dependencies. The risk is that Shell silently re-couples by importing config helpers or path setup.

**Not Enough**: If Shell doesn't cleanly separate I/O from logic, testing remains painful. Every REPL test would need to mock stdin/stdout at the OS level. DI for input_fn/output_fn is the minimum viable testability.

**Too Much**: Building a full command framework (argparse per command, plugin system, command history) is premature. One dict mapping strings to handlers is sufficient.

**Synthesis**: Shell receives all dependencies via `__init__`. I/O is injected. Command parsing is a single dict lookup. Under 200 lines. Extensible later without rewrite.

---

## 4. Implementation Steps

### Step 1: Write tests (DTT)

Create `_staging/PKG-SHELL-001/HOT/tests/test_shell.py` with all tests from Section 6. Tests inject mock `input_fn` and `output_fn` callables and a mock `session_host_v2` object. No real terminal input, no real LLM calls.

### Step 2: Implement shell.py

Create `_staging/PKG-SHELL-001/HOT/kernel/shell.py`:

```python
"""Human-facing command shell for the Control Plane.

Parses user input into cognitive turns or admin commands.
Delegates all cognitive processing to SessionHostV2.
Presentation layer only — no cognitive logic.

Usage:
    shell = Shell(session_host_v2, agent_config)
    shell.run()
"""
```

Class signature:

```python
class Shell:
    def __init__(
        self,
        session_host_v2,
        agent_config,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ) -> None:
        self._host = session_host_v2
        self._agent_config = agent_config
        self._input_fn = input_fn
        self._output_fn = output_fn
        self._running = False
        self._session_id: str | None = None
        self._commands: dict[str, Callable] = {
            "/exit": self._handle_exit,
            "/help": self._handle_help,
            "/show frameworks": self._handle_show_frameworks,
        }

    def run(self) -> None:
        """Start the REPL loop."""
        self._session_id = self._host.start_session(self._agent_config)
        self._output_fn(f"Session started: {self._session_id}")
        self._running = True
        try:
            while self._running:
                try:
                    raw = self._input_fn("admin> ")
                except (EOFError, KeyboardInterrupt):
                    break
                text = raw.strip()
                if not text:
                    continue
                if text.startswith("/"):
                    self._dispatch_command(text)
                else:
                    self._dispatch_turn(text)
        finally:
            self._host.end_session()
            self._output_fn("Session ended.")

    def _dispatch_command(self, text: str) -> None:
        """Route a /command to its handler."""
        # Check for exact match first, then prefix match for multi-word commands
        handler = self._commands.get(text.lower())
        if handler is None:
            # Try matching the longest registered command that is a prefix
            for cmd, h in sorted(self._commands.items(), key=lambda x: -len(x[0])):
                if text.lower().startswith(cmd):
                    handler = h
                    break
        if handler is not None:
            handler()
        else:
            self._handle_unknown(text)

    def _dispatch_turn(self, text: str) -> None:
        """Send cognitive input to SessionHostV2."""
        result = self._host.process_turn(text)
        self._format_result(result)

    def _format_result(self, result) -> None:
        """Format a TurnResult for display."""
        self._output_fn(f"assistant: {result.response}")

    def _handle_exit(self) -> None:
        self._running = False

    def _handle_help(self) -> None:
        lines = [
            "Available commands:",
            "  /help              — Show this help text",
            "  /show frameworks   — List active frameworks",
            "  /exit              — End session and exit",
            "",
            "All other input is sent as a cognitive turn.",
        ]
        self._output_fn("\n".join(lines))

    def _handle_show_frameworks(self) -> None:
        self._output_fn("Not yet implemented.")

    def _handle_unknown(self, text: str) -> None:
        self._output_fn(f"Unknown command: {text}. Type /help for available commands.")
```

### Step 3: Create manifest.json

Create `_staging/PKG-SHELL-001/manifest.json`:

```json
{
  "package_id": "PKG-SHELL-001",
  "version": "1.0.0",
  "schema_version": "1.2",
  "title": "Human-Facing Command Shell",
  "description": "REPL command parser that routes cognitive turns to SessionHostV2 and handles admin commands",
  "spec_id": "SPEC-GATE-001",
  "framework_id": "FMWK-000",
  "plane_id": "hot",
  "layer": 4,
  "dependencies": [
    "PKG-SESSION-HOST-V2-001",
    "PKG-KERNEL-001"
  ],
  "assets": [
    {
      "path": "HOT/kernel/shell.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "module"
    },
    {
      "path": "HOT/tests/test_shell.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "test"
    }
  ]
}
```

### Step 4: Build package archive

```bash
cd Control_Plane_v2/_staging
# Use Python tarfile with explicit arcname — no ./  prefix
python3 -c "
import tarfile
from pathlib import Path
pkg = Path('PKG-SHELL-001')
with tarfile.open('PKG-SHELL-001.tar.gz', 'w:gz') as tf:
    for f in sorted(pkg.rglob('*')):
        if f.is_file() and '__pycache__' not in str(f):
            tf.add(str(f), arcname=str(f.relative_to(pkg)))
"
```

### Step 5: Run tests

```bash
CONTROL_PLANE_ROOT="/tmp/test" python3 -m pytest _staging/PKG-SHELL-001/HOT/tests/test_shell.py -v
# Expected: 10+ tests pass
```

### Step 6: Clean-room verification

```bash
TESTDIR=$(mktemp -d)
INSTALLDIR=$(mktemp -d)
export CONTROL_PLANE_ROOT="$INSTALLDIR"
tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TESTDIR"
cd "$TESTDIR" && bash install.sh --root "$INSTALLDIR" --dev
# Then install PKG-SHELL-001 on top
python3 scripts/package_install.py --archive PKG-SHELL-001.tar.gz \
  --id PKG-SHELL-001 --frameworks-active FMWK-000 \
  --session S1 --work-order WO1 --actor builder --token dev
```

### Step 7: Full regression test

```bash
cd Control_Plane_v2/_staging
CONTROL_PLANE_ROOT="$TMPDIR" python3 -m pytest . -v --ignore=PKG-FLOW-RUNNER-001
# Expected: all pass, no new failures
```

### Step 8: Write results file

Write `_staging/RESULTS_HANDOFF_17.md` following the standard format.

---

## 5. Package Plan

### New Package

| Field | Value |
|-------|-------|
| Package ID | `PKG-SHELL-001` |
| Layer | 4 |
| spec_id | `SPEC-GATE-001` |
| framework_id | `FMWK-000` |
| plane_id | `hot` |
| Dependencies | `PKG-SESSION-HOST-V2-001`, `PKG-KERNEL-001` |
| Assets | `HOT/kernel/shell.py` (module), `HOT/tests/test_shell.py` (test) |

### Modified Packages

None. This package creates new files only. The main.py rewiring to use Shell is a separate followup task (not part of this handoff).

---

## 6. Test Plan

**File:** `_staging/PKG-SHELL-001/HOT/tests/test_shell.py`

All tests inject mock `input_fn`, `output_fn`, and a mock `session_host_v2`. No real terminal input. No real LLM calls.

### Mock Setup

```python
class MockSessionHostV2:
    def __init__(self):
        self.started = False
        self.ended = False
        self.turns = []

    def start_session(self, agent_config):
        self.started = True
        return "SES-MOCK-001"

    def end_session(self):
        self.ended = True

    def process_turn(self, message):
        self.turns.append(message)
        return MockTurnResult(response=f"Echo: {message}")

class MockTurnResult:
    def __init__(self, response):
        self.response = response
```

### Tests

| # | Test | Validates |
|---|------|-----------|
| 1 | `test_cognitive_turn_dispatched` | Non-command input ("hello") sent to `session_host_v2.process_turn()` |
| 2 | `test_admin_command_parsed` | `/help` recognized as admin command, not sent to process_turn |
| 3 | `test_exit_command` | `/exit` ends REPL loop cleanly |
| 4 | `test_help_command` | `/help` displays help text listing available commands |
| 5 | `test_output_formatting` | TurnResult.response formatted as "assistant: {response}" |
| 6 | `test_session_starts_on_run` | `session_host_v2.start_session()` called when Shell.run() begins |
| 7 | `test_session_ends_on_exit` | `session_host_v2.end_session()` called when REPL exits |
| 8 | `test_empty_input_handled` | Empty string and whitespace-only input skipped without error |
| 9 | `test_config_not_loaded` | Shell has no config-loading code; receives dependencies only via __init__ |
| 10 | `test_io_injection` | Custom input_fn and output_fn work correctly (testability proof) |
| 11 | `test_unknown_command` | `/foo` prints "Unknown command" message |
| 12 | `test_eof_ends_loop` | EOFError from input_fn ends REPL gracefully |
| 13 | `test_keyboard_interrupt_ends_loop` | KeyboardInterrupt ends REPL gracefully |

**13 tests total.** Covers: cognitive turn dispatch, command parsing, exit/help commands, output formatting, session lifecycle, empty input, I/O injection, unknown commands, graceful termination.

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Current REPL pattern | `_staging/PKG-ADMIN-001/HOT/admin/main.py` | `run_cli()` is the existing REPL loop. Shell replaces this pattern. Study the input/output flow. |
| SessionHost interface | `_staging/PKG-SESSION-HOST-001/HOT/kernel/session_host.py` | `process_turn()`, `start_session()`, `end_session()` method signatures. SessionHostV2 will follow the same interface pattern. |
| AgentConfig | `_staging/PKG-SESSION-HOST-001/HOT/kernel/session_host.py` | `AgentConfig` dataclass passed to Shell at construction. |
| TurnResult | `_staging/PKG-SESSION-HOST-001/HOT/kernel/session_host.py` | `TurnResult` dataclass returned from `process_turn()`. Shell formats this for display. |
| Builder standard | `_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` | Results file format, baseline snapshot format |
| HANDOFF-12 exemplar | `_staging/handoffs/BUILDER_HANDOFF_12_boot_materialize.md` | Reference handoff format |

---

## 8. End-to-End Verification

```bash
# 1. Run package tests
cd Control_Plane_v2/_staging
CONTROL_PLANE_ROOT="/tmp/test" python3 -m pytest PKG-SHELL-001/HOT/tests/test_shell.py -v
# Expected: 13 tests pass

# 2. Verify package archive contents
tar tzf _staging/PKG-SHELL-001.tar.gz
# Expected:
#   manifest.json
#   HOT/kernel/shell.py
#   HOT/tests/test_shell.py

# 3. Verify Shell class interface
python3 -c "
import sys
sys.path.insert(0, 'PKG-SHELL-001/HOT/kernel')
from shell import Shell
# Verify constructor signature
import inspect
sig = inspect.signature(Shell.__init__)
params = list(sig.parameters.keys())
assert 'session_host_v2' in params, f'Missing session_host_v2 in {params}'
assert 'agent_config' in params, f'Missing agent_config in {params}'
assert 'input_fn' in params, f'Missing input_fn in {params}'
assert 'output_fn' in params, f'Missing output_fn in {params}'
print('Shell interface: PASS')
"

# 4. Verify Shell does NOT import config loading
python3 -c "
import ast
with open('PKG-SHELL-001/HOT/kernel/shell.py') as f:
    tree = ast.parse(f.read())
imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
for imp in imports:
    if isinstance(imp, ast.ImportFrom) and imp.module:
        assert 'main' not in imp.module, 'Shell must not import from main.py'
        assert 'load_config' not in imp.module, 'Shell must not load config'
print('No config coupling: PASS')
"

# 5. Verify line count
wc -l PKG-SHELL-001/HOT/kernel/shell.py
# Expected: under 200 lines

# 6. Full regression
CONTROL_PLANE_ROOT="$TMPDIR" python3 -m pytest . -v --ignore=PKG-FLOW-RUNNER-001
# Expected: all pass, no new failures
```

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `shell.py` | `_staging/PKG-SHELL-001/HOT/kernel/` | CREATE |
| `test_shell.py` | `_staging/PKG-SHELL-001/HOT/tests/` | CREATE |
| `manifest.json` | `_staging/PKG-SHELL-001/` | CREATE |
| `PKG-SHELL-001.tar.gz` | `_staging/` | CREATE |
| `RESULTS_HANDOFF_17.md` | `_staging/` | CREATE |

**Not modified:** main.py, session_host.py, session_host_v2.py, or any other existing package. The main.py rewiring to use Shell is a separate followup task.

---

## 10. Design Principles

1. **Presentation only.** Shell handles input parsing and output formatting. Zero cognitive logic. If you're writing an LLM call, attention assembly, or WO creation inside Shell, you've crossed the boundary.
2. **Dependency injection.** Shell receives SessionHostV2, AgentConfig, input_fn, and output_fn via constructor. It never loads config from disk, never constructs its own session host, never reads environment variables.
3. **Testable by design.** Injected I/O functions mean every test is a pure function call with mock inputs and captured outputs. No terminal mocking, no subprocess spawning.
4. **Command prefix convention.** Lines starting with `/` are admin commands. Everything else is a cognitive turn. This is the only parsing rule. Simple, unambiguous, extensible.
5. **Graceful termination.** EOFError, KeyboardInterrupt, and `/exit` all end the session cleanly. `end_session()` is always called via `finally` block.
6. **Under 200 lines.** If the shell grows beyond 200 lines, scope has crept. Admin commands beyond `/help`, `/exit`, and `/show frameworks` are deferred.
