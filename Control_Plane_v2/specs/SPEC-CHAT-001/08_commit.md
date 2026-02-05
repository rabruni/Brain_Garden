# Commit Specification

## Commit Message

```
Implement extensible chat interface with session ledger (SPEC-CHAT-001)

Phase 3 of Control Plane transparency interface:
- Extensible handler registry with plugin pattern
- Session ledger integration for full audit trail
- Improved classifier with fuzzy matching
- Package management handlers (list, inspect, preflight, install, uninstall)
- Browse handlers for full code/directory transparency
- Search and ledger query handlers

Implements FMWK-CHAT-001 invariants:
- I-CHAT-1: Unique session IDs
- I-CHAT-2: Turn logging with evidence
- I-CHAT-3: Read transparency
- I-CHAT-4: Write capability requirements
- I-CHAT-5: Extensible handler registry
- I-CHAT-6: Fail-safe fallback
- I-CHAT-7/8/9: Package operation governance

New files:
- frameworks/FMWK-CHAT-001_chat_interface_governance.md
- specs/SPEC-CHAT-001/ (8 files + manifest)
- modules/chat_interface/ (11 files)
- schemas/chat_request.json, chat_response.json
- tests/test_chat_interface.py, test_chat_session.py
```

## Files Changed

### New Files

```
frameworks/FMWK-CHAT-001_chat_interface_governance.md
specs/SPEC-CHAT-001/00_overview.md
specs/SPEC-CHAT-001/01_problem.md
specs/SPEC-CHAT-001/02_solution.md
specs/SPEC-CHAT-001/03_requirements.md
specs/SPEC-CHAT-001/04_design.md
specs/SPEC-CHAT-001/05_testing.md
specs/SPEC-CHAT-001/06_rollout.md
specs/SPEC-CHAT-001/07_registry.md
specs/SPEC-CHAT-001/08_commit.md
specs/SPEC-CHAT-001/manifest.yaml
modules/chat_interface/__init__.py
modules/chat_interface/__main__.py
modules/chat_interface/session.py
modules/chat_interface/registry.py
modules/chat_interface/classifier.py
modules/chat_interface/handlers/__init__.py
modules/chat_interface/handlers/browse.py
modules/chat_interface/handlers/packages.py
modules/chat_interface/handlers/search.py
modules/chat_interface/handlers/ledger.py
modules/chat_interface/handlers/help.py
schemas/chat_request.json
schemas/chat_response.json
tests/test_chat_interface.py
tests/test_chat_session.py
```

### Modified Files

```
registries/frameworks_registry.csv  # Add FMWK-CHAT-001
registries/specs_registry.csv       # Add SPEC-CHAT-001
```

## Pre-Commit Checks

```bash
# Syntax check
python3 -m py_compile modules/chat_interface/*.py
python3 -m py_compile modules/chat_interface/handlers/*.py

# Schema validation
python3 -c "import json; json.load(open('schemas/chat_request.json'))"
python3 -c "import json; json.load(open('schemas/chat_response.json'))"

# Import check
python3 -c "from modules.chat_interface import ChatInterface, chat_turn"

# Unit tests
pytest tests/test_chat_interface.py tests/test_chat_session.py -v

# Integration test
echo '{"query": "what is in modules?"}' | python3 -m modules.chat_interface | jq .
```

## Post-Commit Verification

```bash
# Verify framework registered
grep FMWK-CHAT-001 registries/frameworks_registry.csv

# Verify spec registered
grep SPEC-CHAT-001 registries/specs_registry.csv

# Verify module loads
python3 -c "from modules.chat_interface import ChatInterface; print('OK')"

# Full integration test
echo '{"query": "help"}' | python3 -m modules.chat_interface | jq '.response | test("Available")'
```
