# Detailed Design

## Handler Registry

### Registration

```python
from dataclasses import dataclass
from typing import Callable, Dict, Optional

@dataclass
class HandlerInfo:
    name: str
    handler: Callable
    description: str
    requires_capability: Optional[str] = None
    category: str = "general"

class HandlerRegistry:
    _handlers: Dict[str, HandlerInfo] = {}

    @classmethod
    def register(cls, name: str, **kwargs):
        def decorator(fn):
            cls._handlers[name] = HandlerInfo(
                name=name,
                handler=fn,
                **kwargs
            )
            return fn
        return decorator

    @classmethod
    def invoke(cls, name: str, context: dict, query: str, session) -> str:
        if name not in cls._handlers:
            return f"Unknown handler: {name}"

        info = cls._handlers[name]

        # Check capability if required
        if info.requires_capability:
            # Capability check here
            pass

        return info.handler(context, query, session)
```

### Handler Implementation Pattern

```python
@HandlerRegistry.register(
    "browse_dir",
    description="List directory contents",
    category="browse"
)
def handle_browse_dir(context: dict, query: str, session) -> str:
    dir_path = context.get("dir_path") or extract_dir_path(query)

    # Read directory
    full_path = session.root / dir_path
    if not full_path.is_dir():
        return f"Not a directory: {dir_path}"

    # Record evidence
    items = list(full_path.iterdir())

    # Format output
    lines = [f"# Contents of `{dir_path}/`", ""]
    # ... format items

    return "\n".join(lines)
```

## Session Management

### Session Lifecycle

```python
class ChatSession:
    def __init__(self, tier: str = "ho1"):
        self.session_id = self._generate_id()
        self.tier = tier
        self.turn_count = 0
        self.root = Path(__file__).resolve().parent.parent.parent
        self._ledger = None
        self._reads = []  # Files read this turn

    def _generate_id(self) -> str:
        date = datetime.now(timezone.utc).strftime("%Y%m%d")
        rand = uuid.uuid4().hex[:8]
        return f"SES-CHAT-{date}-{rand}"

    def start(self) -> "ChatSession":
        """Initialize session ledger."""
        ledger_path = get_session_ledger_path(
            self.tier,
            self.session_id,
            "chat",
            self.root
        )
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._ledger = LedgerClient(ledger_path=ledger_path)
        return self

    def record_read(self, path: str, file_hash: str):
        """Record file read for evidence."""
        self._reads.append({"path": path, "hash": file_hash})

    def log_turn(self, query: str, result: str, handler: str, duration_ms: int):
        """Log turn to session ledger."""
        self.turn_count += 1

        entry = LedgerEntry(
            event_type="CHAT_TURN",
            submission_id=f"{self.session_id}-T{self.turn_count:03d}",
            decision="EXECUTED",
            reason="Query processed successfully",
            metadata={
                "turn_number": self.turn_count,
                "query_hash": f"sha256:{hash_string(query)}",
                "result_hash": f"sha256:{hash_string(result)}",
                "handler": handler,
                "duration_ms": duration_ms,
                "declared_reads": self._reads.copy(),
            }
        )

        self._ledger.write(entry)
        self._reads.clear()
```

## Query Classification

### Improved Pattern Extraction

```python
def extract_dir_path(query: str) -> Optional[str]:
    """Extract directory path from natural language query."""

    # Known directory names
    KNOWN_DIRS = {
        "modules", "lib", "scripts", "config", "registries",
        "frameworks", "ledger", "specs", "schemas", "tests",
        "governed_prompts", "packages_store", "installed",
        "planes", "handlers"
    }

    query_lower = query.lower()

    # Pattern 1: "what is in X" or "what's in X"
    match = re.search(r"what(?:'s| is) in (?:the )?(\w+)", query_lower)
    if match:
        candidate = match.group(1)
        if candidate in KNOWN_DIRS:
            return candidate

    # Pattern 2: "list files in X"
    match = re.search(r"list (?:files )?in (\w+)", query_lower)
    if match:
        return match.group(1)

    # Pattern 3: "contents of X"
    match = re.search(r"contents? of (?:the )?(\w+)", query_lower)
    if match:
        return match.group(1)

    # Pattern 4: "browse X" or "ls X"
    match = re.search(r"(?:browse|ls) (\w+)", query_lower)
    if match:
        return match.group(1)

    # Pattern 5: Check if any known dir appears in query
    for dir_name in KNOWN_DIRS:
        if dir_name in query_lower:
            return dir_name

    return None
```

### Fuzzy Matching

```python
from difflib import SequenceMatcher

def fuzzy_match(query: str, patterns: List[str], threshold: float = 0.6) -> Optional[str]:
    """Find best matching pattern above threshold."""
    best_match = None
    best_score = 0.0

    for pattern in patterns:
        score = SequenceMatcher(None, query.lower(), pattern.lower()).ratio()
        if score > best_score and score >= threshold:
            best_score = score
            best_match = pattern

    return best_match
```

## Package Operations

### Install Handler

```python
@HandlerRegistry.register(
    "package_install",
    description="Install a package",
    category="packages",
    requires_capability="admin"
)
def handle_package_install(context: dict, query: str, session) -> str:
    package_id = extract_package_id(query)
    if not package_id:
        return "Please specify a package ID. Example: 'install PKG-TEST-001'"

    # Find archive
    archive = find_package_archive(package_id, session.root)
    if not archive:
        return f"Package archive not found: {package_id}"

    # Run install
    result = subprocess.run([
        sys.executable,
        str(session.root / "scripts" / "package_install.py"),
        "--archive", str(archive),
        "--id", package_id,
        "--json"
    ], capture_output=True, text=True)

    if result.returncode != 0:
        return f"Install failed:\n{result.stderr}"

    return f"Installed {package_id} successfully"
```

### Uninstall Handler

```python
@HandlerRegistry.register(
    "package_uninstall",
    description="Uninstall a package",
    category="packages",
    requires_capability="admin"
)
def handle_package_uninstall(context: dict, query: str, session) -> str:
    package_id = extract_package_id(query)

    installed_path = session.root / "installed" / package_id
    if not installed_path.exists():
        return f"Package not installed: {package_id}"

    # Load receipt
    receipt_path = installed_path / "receipt.json"
    receipt = json.loads(receipt_path.read_text())

    # Remove files
    removed = 0
    for file_info in receipt.get("files", []):
        file_path = session.root / file_info["path"]
        if file_path.exists():
            file_path.unlink()
            removed += 1

    # Remove installed directory
    shutil.rmtree(installed_path)

    # Log to ledger
    session.log_event("PACKAGE_UNINSTALLED", package_id, {
        "files_removed": removed
    })

    return f"Uninstalled {package_id}: {removed} files removed"
```
