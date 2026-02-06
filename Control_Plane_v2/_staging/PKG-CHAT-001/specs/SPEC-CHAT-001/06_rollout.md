# Rollout Plan

## Phase 1: Core Module (WO-7.1 - WO-7.3)

### Deliverables

1. `modules/chat_interface/registry.py` - Handler registry
2. `modules/chat_interface/session.py` - Session management
3. `modules/chat_interface/classifier.py` - Improved classifier

### Validation

```bash
# Test registry
python3 -c "from modules.chat_interface.registry import HandlerRegistry; print('OK')"

# Test session
python3 -c "from modules.chat_interface.session import ChatSession; s = ChatSession(); print(s.session_id)"

# Test classifier
python3 -c "from modules.chat_interface.classifier import classify_query; print(classify_query('what is in modules?'))"
```

## Phase 2: Handlers (WO-7.4)

### Deliverables

1. `modules/chat_interface/handlers/__init__.py`
2. `modules/chat_interface/handlers/browse.py`
3. `modules/chat_interface/handlers/packages.py`
4. `modules/chat_interface/handlers/search.py`
5. `modules/chat_interface/handlers/ledger.py`
6. `modules/chat_interface/handlers/help.py`

### Validation

```bash
# Test handler imports
python3 -c "from modules.chat_interface.handlers import browse, packages, search, ledger, help; print('OK')"

# Test handler registration
python3 -c "
from modules.chat_interface.registry import HandlerRegistry
from modules.chat_interface import handlers
print(f'Registered: {len(HandlerRegistry._handlers)} handlers')
"
```

## Phase 3: Public API (WO-7.5)

### Deliverables

1. `modules/chat_interface/__init__.py` - Public API
2. `modules/chat_interface/__main__.py` - CLI

### Validation

```bash
# Test public API
python3 -c "from modules.chat_interface import ChatInterface, chat_turn; print('OK')"

# Test pipe mode
echo '{"query": "help"}' | python3 -m modules.chat_interface | jq .

# Test interactive mode (manual)
python3 -m modules.chat_interface --interactive
```

## Phase 4: Schemas and Tests (WO-7.6)

### Deliverables

1. `schemas/chat_request.json`
2. `schemas/chat_response.json`
3. `tests/test_chat_interface.py`
4. `tests/test_chat_session.py`

### Validation

```bash
# Run tests
pytest tests/test_chat_interface.py tests/test_chat_session.py -v

# Validate schemas
python3 -c "import json; json.load(open('schemas/chat_request.json')); print('OK')"
```

## Rollback Procedure

If issues are found:

1. **Revert commits**:
   ```bash
   git log --oneline -5  # Find commit before chat_interface
   git revert <commit>
   ```

2. **Disable module**:
   ```bash
   mv modules/chat_interface modules/chat_interface.disabled
   ```

3. **Update registries**:
   - Remove FMWK-CHAT-001 from frameworks_registry.csv
   - Remove SPEC-CHAT-001 from specs_registry.csv

## Success Criteria

1. All unit tests pass
2. Pipe interface works for all query types
3. Session ledgers created correctly
4. Package operations function with proper authorization
5. No regressions in existing router functionality
