# Builder Handoff #11: Session Host + ADMIN First Boot

## 1. Mission

Build the Session Host — the governed chat loop that hosts agents — and boot ADMIN as the first agent. Two packages: `PKG-SESSION-HOST-001` (the reusable engine) and `PKG-ADMIN-001` (ADMIN's configuration + entry point). When done, a human can type a message, ADMIN responds using Claude, tools execute, and every exchange is logged to the ledger.

**CRITICAL CONSTRAINTS — read before doing anything:**

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** New code ships as packages in `_staging/PKG-<NAME>/` with manifest.json, SHA256 hashes, proper dependencies. Follow existing package patterns.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → install all bootstrap packages → install PKG-ATTENTION-001 → install YOUR new packages. All gates must pass.
5. **No hardcoding.** Every threshold, timeout, retry count — all config-driven.
6. **No file replacement.** Packages must NEVER overwrite another package's files.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .`
8. **Results file.** When finished, write `_staging/RESULTS_HANDOFF_11.md` following the results file format in `BUILDER_HANDOFF_STANDARD.md`.
9. **Full regression test.** Run ALL staged package tests and report results.
10. **Baseline snapshot.** Your results file must include package count, file_ownership rows, total tests, all gate results.
11. **Use friendly names.** Session Host (not H5/Flow Runner), Attention Service (not H4), Exchange Recording (not H10), Prompt Router (not H3), Anthropic Provider (not H9).

---

## 2. Architecture

### What the Session Host IS

A Python module that runs a governed chat loop. It's the runtime that hosts any agent — ADMIN, RESIDENT, or future agent classes. It is kernel infrastructure, not agent-specific.

### What ADMIN IS

A configuration of the Session Host. ADMIN is not code — it's a config file that tells the Session Host: which tools, which permissions, which attention template, which system prompt, which budget. ADMIN is the first car. The Session Host is the engine.

### Full Query Turn (Single User Message → Response)

```
Human types: "Are all gates passing?"
    │
    ▼
SESSION HOST receives input
    │
    ▼
SESSION HOST calls ATTENTION SERVICE
    │  Input: AttentionRequest (agent_id, agent_class, tier, prompt_contract)
    │  Attention assembles context from ledger, registries, files
    │  Returns: AssembledContext (context_text, context_hash, fragments)
    │  (v1: deterministic pipeline. Future: semantic agent with its own LLM call)
    │
    ▼
SESSION HOST builds the prompt
    │  System: agent's system_prompt from config
    │  Context: attention's assembled context_text
    │  Conversation: prior turns in this session
    │  User: the human's message
    │  Tools: agent's tool definitions from config
    │
    ▼
SESSION HOST sends through PROMPT ROUTER
    │  Router validates → auth → budget → DISPATCH marker → send to Anthropic
    │  → EXCHANGE record (prompt + response text logged) → debit budget → return
    │
    ▼
SESSION HOST receives response
    │
    ├── If text only → display to human, loop
    │
    └── If tool_use → TOOL DISPATCH
            │  Check tool is in agent's allowed list
            │  Execute tool (governed script/function)
            │  Send tool result back to Claude (via router — another EXCHANGE)
            │  Get final response → display to human, loop
```

### Component Boundaries

| Component | Responsibility | Does NOT |
|-----------|---------------|----------|
| Session Host | Chat loop, prompt assembly, tool dispatch, session lifecycle | Assemble context, send to LLM, log to ledger |
| Attention Service | Gather context from ledger/registries/files | Send prompts, execute tools |
| Prompt Router | Validate, auth, budget, send to LLM, log EXCHANGE | Assemble context, decide what to send |
| Tool Dispatch | Register tools, validate permissions, execute | Choose which tools to call (that's Claude's job) |

### Agent Configuration

Each agent is defined by a JSON config file. The Session Host reads this at startup.

```json
{
  "agent_id": "admin-001",
  "agent_class": "ADMIN",
  "framework_id": "FMWK-005",
  "tier": "hot",
  "system_prompt": "You are ADMIN, the governance interface for the Control Plane...",
  "attention": {
    "template_id": "ATT-ADMIN-001",
    "prompt_contract": {
      "contract_id": "PRC-ADMIN-001",
      "version": "1.0.0",
      "prompt_pack_id": "PRM-ADMIN-001",
      "boundary": {
        "max_tokens": 4096,
        "temperature": 0.0
      }
    }
  },
  "tools": [
    {
      "tool_id": "gate_check",
      "description": "Run governance gate checks and report results",
      "handler": "tools.gate_check",
      "parameters": {
        "type": "object",
        "properties": {
          "gate": { "type": "string", "description": "Specific gate to check (e.g. 'G0B', 'G1') or 'all'" }
        }
      }
    },
    {
      "tool_id": "read_file",
      "description": "Read a governed file and return its contents",
      "handler": "tools.read_file",
      "parameters": {
        "type": "object",
        "properties": {
          "path": { "type": "string", "description": "Relative path from plane root" }
        },
        "required": ["path"]
      }
    },
    {
      "tool_id": "query_ledger",
      "description": "Query the ledger for entries by event type, agent, session, or work order",
      "handler": "tools.query_ledger",
      "parameters": {
        "type": "object",
        "properties": {
          "event_type": { "type": "string" },
          "max_entries": { "type": "integer", "default": 10 },
          "agent_id": { "type": "string" },
          "session_id": { "type": "string" }
        }
      }
    },
    {
      "tool_id": "list_packages",
      "description": "List all installed packages with their versions and status",
      "handler": "tools.list_packages",
      "parameters": { "type": "object", "properties": {} }
    }
  ],
  "budget": {
    "session_token_limit": 200000,
    "turn_limit": 50,
    "timeout_seconds": 7200
  },
  "permissions": {
    "read": ["HOT/*", "HO2/*", "HO1/*"],
    "write": ["HO2/*", "HO1/*"],
    "forbidden": ["HOT/kernel/*", "HOT/scripts/*"]
  }
}
```

---

## 3. Implementation Steps

### Step 1: Write tests for Session Host (DTT)

File: `_staging/PKG-SESSION-HOST-001/HOT/tests/test_session_host.py`

Tests use mocks for attention, router, and tools. No real LLM calls.

### Step 2: Implement Session Host

File: `_staging/PKG-SESSION-HOST-001/HOT/kernel/session_host.py`

```python
class SessionHost:
    def __init__(self, plane_root, agent_config, attention_service, router, dev_mode=False):
        ...

    def start_session(self) -> str:
        """Initialize session, return session_id. Log SESSION_START to ledger."""

    def process_turn(self, user_message: str) -> TurnResult:
        """One full turn: attention → prompt → router → tools → response."""

    def end_session(self):
        """Log SESSION_END to ledger. Report budget summary."""
```

Key methods inside `process_turn`:

1. `_call_attention(user_message)` → `AssembledContext`
2. `_build_prompt(user_message, context, conversation_history)` → prompt string or messages list
3. `_build_tools_for_api()` → list of tool definitions in Anthropic API format
4. `_route_prompt(prompt, tools)` → `PromptResponse`
5. `_handle_tool_calls(response)` → execute tools, send results back, get final response
6. `_append_to_history(user_message, assistant_response)` → update conversation history

### Step 3: Implement Tool Dispatch

File: `_staging/PKG-SESSION-HOST-001/HOT/kernel/tool_dispatch.py`

```python
class ToolDispatcher:
    def __init__(self, plane_root, tool_configs, permissions):
        ...

    def register_tool(self, tool_id, handler_fn, schema):
        """Register a tool handler."""

    def execute(self, tool_id, arguments) -> ToolResult:
        """Validate permissions, execute tool, return result."""

    def get_api_tools(self) -> list[dict]:
        """Return tool definitions in Anthropic API format."""
```

Built-in tool handlers (for ADMIN v1):

```python
# tools.gate_check — wraps HOT/scripts/gate_check.py
# tools.read_file — reads a file, checks permissions
# tools.query_ledger — queries ledger entries
# tools.list_packages — reads HOT/installed/ receipts
```

### Step 4: Write tests for Tool Dispatch

File: same test file or separate `test_tool_dispatch.py`

### Step 5: Create ADMIN config

File: `_staging/PKG-ADMIN-001/HOT/config/admin_config.json`

Use the config structure shown in Architecture section. System prompt should describe ADMIN's capabilities and boundaries.

### Step 6: Create ADMIN entry point

File: `_staging/PKG-ADMIN-001/HOT/admin/main.py`

```python
"""ADMIN agent entry point. Usage: python3 main.py --root /path/to/cp --dev"""

def main():
    # 1. Parse args (--root, --dev)
    # 2. Load admin_config.json
    # 3. Create AttentionService, PromptRouter, TokenBudgeter
    # 4. Create SessionHost with all components
    # 5. Start session
    # 6. Read-eval-print loop:
    #      user_input = input("admin> ")
    #      result = session_host.process_turn(user_input)
    #      print(result.response)
    # 7. End session on quit/exit/ctrl-c
```

### Step 7: Create ADMIN attention template

File: `_staging/PKG-ADMIN-001/HOT/attention_templates/ATT-ADMIN-001.json`

This tells the attention service what context to assemble for ADMIN:

```json
{
  "template_id": "ATT-ADMIN-001",
  "version": "1.0.0",
  "description": "Full visibility context for ADMIN agent",
  "applies_to": {
    "agent_class": ["ADMIN"],
    "framework_id": ["FMWK-005"]
  },
  "pipeline": [
    {"stage": "select_tiers", "type": "tier_select", "config": {"tiers": ["hot", "ho2", "ho1"]}},
    {"stage": "recent_exchanges", "type": "ledger_query", "config": {"event_type": "EXCHANGE", "max_entries": 10, "recency": "session"}},
    {"stage": "recent_installs", "type": "ledger_query", "config": {"event_type": "INSTALLED", "max_entries": 5}},
    {"stage": "structure", "type": "structuring", "config": {"strategy": "chronological", "max_tokens": 8000}},
    {"stage": "halt", "type": "halting", "config": {"min_fragments": 0}}
  ],
  "budget": {
    "max_context_tokens": 10000,
    "max_queries": 20,
    "timeout_ms": 5000
  },
  "fallback": {
    "on_timeout": "return_partial",
    "on_empty": "proceed_empty"
  }
}
```

### Step 8: Create ADMIN framework manifest

File: `_staging/PKG-ADMIN-001/HOT/FMWK-005_Admin/manifest.yaml`

### Step 9: Build package manifests

- `_staging/PKG-SESSION-HOST-001/manifest.json`
- `_staging/PKG-ADMIN-001/manifest.json`

### Step 10: Build archives and rebuild CP_BOOTSTRAP

```bash
# Build PKG-SESSION-HOST-001.tar.gz
cd _staging/PKG-SESSION-HOST-001 && tar czf ../PKG-SESSION-HOST-001.tar.gz $(ls) && cd ..

# Build PKG-ADMIN-001.tar.gz
cd _staging/PKG-ADMIN-001 && tar czf ../PKG-ADMIN-001.tar.gz $(ls) && cd ..

# Rebuild CP_BOOTSTRAP.tar.gz with both new packages added to packages/
# 1. Extract current bootstrap
mkdir -p /tmp/rebuild_bootstrap
tar xzf CP_BOOTSTRAP.tar.gz -C /tmp/rebuild_bootstrap

# 2. Copy new archives into packages/
cp PKG-SESSION-HOST-001.tar.gz /tmp/rebuild_bootstrap/packages/
cp PKG-ADMIN-001.tar.gz /tmp/rebuild_bootstrap/packages/
# Also copy PKG-ATTENTION-001.tar.gz if not already present
cp PKG-ATTENTION-001.tar.gz /tmp/rebuild_bootstrap/packages/

# 3. Rebuild
cd /tmp/rebuild_bootstrap && tar czf /path/to/_staging/CP_BOOTSTRAP.tar.gz $(ls) && cd -
```

### Step 11: Clean-room verification

Install full chain → all gates pass → run ADMIN in `--dev` mode → type a message → get a response.

---

## 4. Package Plan

### PKG-SESSION-HOST-001 (Layer 3)

| Field | Value |
|-------|-------|
| package_id | PKG-SESSION-HOST-001 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |
| version | 1.0.0 |
| layer | 3 |

**Assets:**
| Path | Classification |
|------|---------------|
| HOT/kernel/session_host.py | kernel |
| HOT/kernel/tool_dispatch.py | kernel |
| HOT/tests/test_session_host.py | test |

**Dependencies:** PKG-KERNEL-001, PKG-PROMPT-ROUTER-001, PKG-ATTENTION-001

### PKG-ADMIN-001 (Layer 3)

| Field | Value |
|-------|-------|
| package_id | PKG-ADMIN-001 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-005 |
| plane_id | hot |
| version | 1.0.0 |
| layer | 3 |

**Assets:**
| Path | Classification |
|------|---------------|
| HOT/admin/main.py | application |
| HOT/config/admin_config.json | config |
| HOT/attention_templates/ATT-ADMIN-001.json | config |
| HOT/FMWK-005_Admin/manifest.yaml | framework |
| HOT/tests/test_admin.py | test |

**Dependencies:** PKG-SESSION-HOST-001, PKG-ATTENTION-001, PKG-PROMPT-ROUTER-001, PKG-ANTHROPIC-PROVIDER-001

---

## 5. Test Plan

### Session Host Tests (25 tests)

**Session lifecycle (4):**
1. `test_start_session_returns_session_id` — session_id format matches SES-XXXXXXXX
2. `test_start_session_logs_to_ledger` — SESSION_START entry in ledger
3. `test_end_session_logs_to_ledger` — SESSION_END entry in ledger
4. `test_end_session_reports_budget` — budget summary in SESSION_END metadata

**Turn processing (8):**
5. `test_process_turn_calls_attention` — attention service called with correct request
6. `test_process_turn_builds_prompt_with_context` — assembled context appears in prompt
7. `test_process_turn_includes_system_prompt` — agent's system_prompt in the prompt
8. `test_process_turn_includes_conversation_history` — prior turns included
9. `test_process_turn_sends_through_router` — router.route() called
10. `test_process_turn_returns_response_text` — TurnResult contains Claude's response
11. `test_process_turn_updates_history` — conversation history grows after turn
12. `test_process_turn_with_empty_context` — works when attention returns nothing

**Tool dispatch (8):**
13. `test_tool_definitions_sent_to_api` — tools from config appear in API call
14. `test_tool_call_dispatched` — tool_use in response triggers tool execution
15. `test_tool_result_sent_back` — tool result sent to Claude as tool_result
16. `test_forbidden_tool_rejected` — tool not in allowed list returns error
17. `test_tool_permission_check` — write tool blocked when agent has read-only
18. `test_multiple_tool_calls` — multiple tools in one response all execute
19. `test_tool_error_handled` — tool execution error returned to Claude gracefully
20. `test_tool_result_logged` — tool execution logged to ledger

**Budget and boundaries (5):**
21. `test_budget_tracked_per_session` — total tokens across turns tracked
22. `test_turn_limit_enforced` — session ends when turn_limit reached
23. `test_timeout_enforced` — session ends when timeout reached
24. `test_dev_mode_bypasses_auth` — --dev skips auth checks
25. `test_config_loaded_from_file` — agent config JSON parsed correctly

### ADMIN Tests (10 tests)

26. `test_admin_config_valid_json` — admin_config.json parses without error
27. `test_admin_config_has_required_fields` — agent_id, agent_class, tools, system_prompt present
28. `test_admin_attention_template_valid` — ATT-ADMIN-001.json matches attention_template.schema.json
29. `test_admin_tools_have_schemas` — every tool has parameters schema
30. `test_admin_main_creates_session` — main.py creates SessionHost and starts session
31. `test_admin_gate_check_tool` — gate_check tool wrapper runs gate_check.py and returns results
32. `test_admin_read_file_tool` — read_file tool returns file contents
33. `test_admin_query_ledger_tool` — query_ledger tool returns ledger entries
34. `test_admin_list_packages_tool` — list_packages tool returns installed packages
35. `test_admin_forbidden_write` — ADMIN cannot write to kernel space

---

## 6. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Attention Service | `_staging/PKG-ATTENTION-001/HOT/kernel/attention_service.py` | You call `assemble()` — read its interface |
| Prompt Router | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/prompt_router.py` | You call `route()` — read PromptRequest/PromptResponse |
| Anthropic Provider | `_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/kernel/anthropic_provider.py` | Returns `content_blocks` with tool_use support |
| Provider Protocol | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/provider.py` | ProviderResponse, MockProvider for testing |
| Token Budgeter | `_staging/PKG-TOKEN-BUDGETER-001/HOT/kernel/token_budgeter.py` | Budget allocation and tracking |
| Ledger Client | `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` | LedgerEntry, LedgerClient — you write SESSION_START/END |
| ADMIN Design Doc | `_staging/ADMIN_DESIGN.md` | What ADMIN is, what it can see/do, firewall boundaries |
| Locked System Shell | `~/AI_ARCH/_locked_system_flattened/shell/main.py` | Reference UX — interactive shell with tool use |
| Locked System CLI | `~/AI_ARCH/_locked_system_flattened/cli/main.py` | CLI entry point reference |
| Attention Template Schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/attention_template.schema.json` | ATT-ADMIN-001 must conform |
| Prompt Contract Schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/prompt_contract.schema.json` | ADMIN's prompt contract must conform |
| Firewall Spec | `docs/CP-FIREWALL-001_builder_vs_built.md` | ADMIN's capabilities and boundaries |
| Script Toolbox | `docs/ADMIN_AGENT_SCRIPT_REF.md` | Scripts that become ADMIN's tools |

---

## 7. End-to-End Verification

```bash
STAGING="Control_Plane_v2/_staging"
TMPDIR=$(mktemp -d)

# 1. Extract and install bootstrap (13 packages)
mkdir -p "$TMPDIR/bootstrap"
tar xzf "$STAGING/CP_BOOTSTRAP.tar.gz" -C "$TMPDIR/bootstrap"
export CONTROL_PLANE_ROOT="$TMPDIR/cp"
bash "$TMPDIR/bootstrap/install.sh" --root "$CONTROL_PLANE_ROOT" --dev
# Expected: 13 packages, 8/8 gates

# 2. Install Attention Service
python3 "$CONTROL_PLANE_ROOT/HOT/scripts/package_install.py" \
    --archive "$STAGING/PKG-ATTENTION-001.tar.gz" \
    --id PKG-ATTENTION-001 --root "$CONTROL_PLANE_ROOT" --dev
# Expected: 14 packages

# 3. Install Session Host
python3 "$CONTROL_PLANE_ROOT/HOT/scripts/package_install.py" \
    --archive "$STAGING/PKG-SESSION-HOST-001.tar.gz" \
    --id PKG-SESSION-HOST-001 --root "$CONTROL_PLANE_ROOT" --dev
# Expected: 15 packages

# 4. Install ADMIN
python3 "$CONTROL_PLANE_ROOT/HOT/scripts/package_install.py" \
    --archive "$STAGING/PKG-ADMIN-001.tar.gz" \
    --id PKG-ADMIN-001 --root "$CONTROL_PLANE_ROOT" --dev
# Expected: 16 packages

# 5. Gate check
CONTROL_PLANE_ROOT="$CONTROL_PLANE_ROOT" python3 \
    "$CONTROL_PLANE_ROOT/HOT/scripts/gate_check.py" --root "$CONTROL_PLANE_ROOT" --all
# Expected: 8/8 gates PASS

# 6. Run all tests
CONTROL_PLANE_ROOT="$CONTROL_PLANE_ROOT" \
PYTHONPATH="$CONTROL_PLANE_ROOT/HOT:$CONTROL_PLANE_ROOT/HOT/kernel" \
python3 -m pytest "$CONTROL_PLANE_ROOT/HOT/tests/" -v

# 7. ADMIN smoke test (requires ANTHROPIC_API_KEY for real LLM calls)
ANTHROPIC_API_KEY="..." \
CONTROL_PLANE_ROOT="$CONTROL_PLANE_ROOT" \
python3 "$CONTROL_PLANE_ROOT/HOT/admin/main.py" --root "$CONTROL_PLANE_ROOT" --dev
# Type: "What packages are installed?"
# Expected: ADMIN lists 16 packages
# Type: "exit"
# Expected: clean shutdown, SESSION_END logged
```

---

## 8. Files Summary

| File | Location | Action |
|------|----------|--------|
| session_host.py | `_staging/PKG-SESSION-HOST-001/HOT/kernel/` | CREATE |
| tool_dispatch.py | `_staging/PKG-SESSION-HOST-001/HOT/kernel/` | CREATE |
| test_session_host.py | `_staging/PKG-SESSION-HOST-001/HOT/tests/` | CREATE |
| manifest.json | `_staging/PKG-SESSION-HOST-001/` | CREATE |
| PKG-SESSION-HOST-001.tar.gz | `_staging/` | CREATE |
| main.py | `_staging/PKG-ADMIN-001/HOT/admin/` | CREATE |
| admin_config.json | `_staging/PKG-ADMIN-001/HOT/config/` | CREATE |
| ATT-ADMIN-001.json | `_staging/PKG-ADMIN-001/HOT/attention_templates/` | CREATE |
| manifest.yaml | `_staging/PKG-ADMIN-001/HOT/FMWK-005_Admin/` | CREATE |
| test_admin.py | `_staging/PKG-ADMIN-001/HOT/tests/` | CREATE |
| manifest.json | `_staging/PKG-ADMIN-001/` | CREATE |
| PKG-ADMIN-001.tar.gz | `_staging/` | CREATE |
| CP_BOOTSTRAP.tar.gz | `_staging/` | REBUILD (add 3 new packages) |

---

## 9. Design Principles (Non-Negotiable)

1. **Session Host is agent-agnostic.** It hosts ANY agent class. ADMIN is just the first configuration. No ADMIN-specific code in session_host.py.
2. **Config is king.** Tools, permissions, system prompt, budget — all from the agent's config JSON. The Session Host reads config, not code.
3. **Every turn goes through the router.** No direct LLM calls. The router logs every EXCHANGE. If attention gets a semantic upgrade (its own LLM call), that goes through the router too.
4. **Tool dispatch is governed.** Every tool call is validated against the agent's allowed list and permissions. Forbidden tools return an error to Claude, not to the human.
5. **The ledger IS the session memory.** No separate session state. Conversation history is reconstructed from EXCHANGE entries in the current session. The ledger is the source of truth.
6. **Fail gracefully.** If attention returns empty, proceed with just the user message. If a tool fails, return the error to Claude and let it try another approach. Never crash the session.
7. **v1 scope: make it work.** Don't build aperture model, semantic attention, OS-level separation, or multi-agent orchestration. Those are future upgrades. Build the loop, boot ADMIN, type a message, get a response.

---

## 10. Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**YOUR IDENTITY — print this FIRST before doing anything else:**
> **Agent: HANDOFF-11** — Session Host + ADMIN first boot

**Read this file FIRST — it is your complete specification:**
`Control_Plane_v2/_staging/BUILDER_HANDOFF_11_session_host.md`

**Also read these files for context:**
- `Control_Plane_v2/_staging/ADMIN_DESIGN.md` — what ADMIN is
- `Control_Plane_v2/_staging/PKG-ATTENTION-001/HOT/kernel/attention_service.py` — attention interface
- `Control_Plane_v2/_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/prompt_router.py` — router interface
- `Control_Plane_v2/_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/provider.py` — MockProvider for testing

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` — NEVER `tar czf ... -C dir .`
4. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_HANDOFF_11.md`

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What are the two packages you're building? What layer are they?
2. What does `SessionHost.process_turn()` do, step by step?
3. What happens when Claude's response contains a `tool_use` block?
4. Where does ADMIN's system prompt come from? Where do its tools come from?
5. How does conversation history work? Where is it stored?
6. What goes through the Prompt Router — just ADMIN's response, or attention too?
7. What is the relationship between session_host.py and tool_dispatch.py?
8. How do you test the Session Host without making real LLM calls?
9. What tar command format do you use for building archives?
10. After installation, what does the human type to start ADMIN, and what should happen?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

**Expected Answers:**

1. PKG-SESSION-HOST-001 (engine, Layer 3) and PKG-ADMIN-001 (ADMIN config + entry point, Layer 3).
2. Call attention → build prompt (system + context + history + user message + tools) → send through router → if tool_use, execute tools and send results back → return response.
3. Session Host checks tool is in agent's allowed list, executes it via ToolDispatcher, sends the result back to Claude as a tool_result message, gets the final text response.
4. Both come from admin_config.json. The Session Host reads the config file at startup. No hardcoded prompts or tools.
5. Conversation history is the list of (user, assistant) turns in the current session. Stored in memory during the session. The ledger has EXCHANGE records for persistence — history can be reconstructed from ledger on session resume.
6. In v1, only ADMIN's response goes through the router. Attention is deterministic (no LLM call). In a future semantic attention upgrade, attention's LLM call would also go through the router.
7. session_host.py is the chat loop. tool_dispatch.py handles tool registration, permission checking, and execution. The Session Host calls the ToolDispatcher when Claude wants to use a tool.
8. Use MockProvider from provider.py. Mock the attention service to return canned AssembledContext. Mock tool handlers to return canned results. No real API calls needed.
9. `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .`
10. `python3 HOT/admin/main.py --root /path/to/cp --dev` — a prompt appears, human types a message, ADMIN responds, tools execute if needed, everything logged to ledger.
