# Testing Plan

## Unit Tests

### test_chat_interface.py

```python
class TestHandlerRegistry:
    """Test handler registration and invocation."""

    def test_register_handler(self):
        """Test handler registration via decorator."""

    def test_invoke_handler(self):
        """Test handler invocation by name."""

    def test_unknown_handler(self):
        """Test graceful handling of unknown handler."""

    def test_capability_check(self):
        """Test capability requirement enforcement."""


class TestClassifier:
    """Test query classification."""

    def test_browse_dir_classification(self):
        """Test directory browsing queries."""
        queries = [
            "what is in the modules directory?",
            "what's in modules",
            "list files in lib",
            "ls config",
            "browse handlers",
        ]
        for query in queries:
            result = classify_query(query)
            assert result.type == QueryType.BROWSE_DIR

    def test_browse_code_classification(self):
        """Test file reading queries."""

    def test_package_operations(self):
        """Test package query classification."""

    def test_fuzzy_matching(self):
        """Test fuzzy pattern matching."""


class TestDirPathExtraction:
    """Test directory path extraction."""

    def test_extract_from_natural_language(self):
        """Test extraction from various phrasings."""
        cases = [
            ("what is in the modules directory?", "modules"),
            ("what's in modules", "modules"),
            ("list files in lib/", "lib"),
            ("contents of config", "config"),
            ("show me what is in registries", "registries"),
        ]
        for query, expected in cases:
            result = extract_dir_path(query)
            assert result == expected, f"Query: {query}"
```

### test_chat_session.py

```python
class TestChatSession:
    """Test session management."""

    def test_session_id_format(self):
        """Test session ID follows pattern."""
        session = ChatSession()
        assert session.session_id.startswith("SES-CHAT-")
        assert len(session.session_id) == 25

    def test_session_start(self):
        """Test session initialization creates ledger."""

    def test_turn_logging(self):
        """Test turn logging to session ledger."""

    def test_evidence_recording(self):
        """Test file read evidence recording."""


class TestLedgerIntegration:
    """Test ledger integration."""

    def test_turn_entry_schema(self):
        """Test turn entries have required fields."""

    def test_evidence_hashes(self):
        """Test evidence includes file hashes."""
```

## Integration Tests

### Pipe Interface Tests

```bash
# Test directory browsing
echo '{"query": "what is in the modules directory?"}' \
  | python3 -m modules.chat_interface \
  | jq '.response | test("modules")'

# Test package listing
echo '{"query": "list packages"}' \
  | python3 -m modules.chat_interface \
  | jq '.response | test("PKG-")'

# Test file reading
echo '{"query": "read lib/auth.py"}' \
  | python3 -m modules.chat_interface \
  | jq '.response | test("def ")'

# Test help
echo '{"query": "help"}' \
  | python3 -m modules.chat_interface \
  | jq '.response | test("Available commands")'
```

### Session Ledger Tests

```bash
# Start session and make queries
SESSION_ID=$(echo '{"query": "help"}' | python3 -m modules.chat_interface | jq -r '.session_id')

# Verify ledger created
ls planes/ho1/sessions/$SESSION_ID/ledger/chat.jsonl

# Verify entries
cat planes/ho1/sessions/$SESSION_ID/ledger/chat.jsonl \
  | jq 'select(.event_type == "CHAT_TURN")'
```

### Package Operation Tests

```bash
# Test package listing
echo '{"query": "list packages"}' | python3 -m modules.chat_interface

# Test package inspection
echo '{"query": "inspect PKG-KERNEL-001"}' | python3 -m modules.chat_interface

# Test preflight (requires admin)
echo '{"query": "preflight PKG-TEST-001", "capability": "admin"}' \
  | python3 -m modules.chat_interface
```

## Verification Commands

```bash
# Run all unit tests
pytest tests/test_chat_interface.py tests/test_chat_session.py -v

# Run with coverage
pytest tests/test_chat_interface.py --cov=modules/chat_interface

# Run integration tests
./tests/integration/test_chat_pipe.sh
```
