# Solution Design

## Architecture

The chat interface uses a layered architecture:

```
┌─────────────────────────────────────────────┐
│              Chat Interface                  │
│  ┌─────────┐  ┌─────────┐  ┌─────────────┐  │
│  │ Session │  │Classifier│  │   Registry  │  │
│  │ Manager │  │         │  │  (Handlers) │  │
│  └────┬────┘  └────┬────┘  └──────┬──────┘  │
│       │            │              │          │
│       ▼            ▼              ▼          │
│  ┌─────────────────────────────────────┐    │
│  │         Handler Execution           │    │
│  └─────────────────────────────────────┘    │
│                    │                         │
│                    ▼                         │
│  ┌─────────────────────────────────────┐    │
│  │         Session Ledger              │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

## Key Components

### 1. Handler Registry

Decorator-based registration:

```python
@register("browse_dir",
          description="List directory contents",
          category="browse")
def handle_browse_dir(context, query, session):
    ...
```

### 2. Improved Classifier

Fuzzy matching + better path extraction:

```python
def extract_dir_path(query: str) -> str:
    # "what is in the modules directory?" -> "modules"
    # "list files in lib/" -> "lib"
    # "ls config" -> "config"
```

### 3. Session Manager

Per-session ledger and evidence:

```python
class ChatSession:
    def __init__(self, tier="ho1"):
        self.session_id = generate_session_id()
        self._ledger = None  # Lazy init

    def log_turn(self, query, result, handler, duration_ms):
        # Write to session ledger
```

### 4. Package Handlers

Full lifecycle support:

- `list_packages`: Show installed and available
- `inspect_package`: Show manifest and files
- `preflight_package`: Run validation
- `install_package`: Install from staging
- `uninstall_package`: Remove package
- `stage_package`: Prepare for install

## Data Flow

1. **Input**: JSON with `query` field
2. **Classification**: Determine query type and extract arguments
3. **Handler Lookup**: Find registered handler for query type
4. **Execution**: Run handler with context and session
5. **Evidence**: Record file reads and hashes
6. **Ledger**: Write turn entry with evidence
7. **Output**: JSON with `response` and `evidence` fields
