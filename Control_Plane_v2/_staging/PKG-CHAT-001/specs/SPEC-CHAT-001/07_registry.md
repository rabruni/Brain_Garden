# Registry Updates

## frameworks_registry.csv

Add row:

```csv
FMWK-CHAT-001,Chat Interface Governance,active,1.0.0,ho3,2026-02-04T00:00:00Z
```

## specs_registry.csv

Add row:

```csv
SPEC-CHAT-001,Chat Interface Implementation,FMWK-CHAT-001,active,1.0.0,ho3,2026-02-04T00:00:00Z
```

## file_ownership.json (compiled)

Files owned by this spec's package:

```json
{
  "modules/chat_interface/__init__.py": "PKG-CHAT-001",
  "modules/chat_interface/__main__.py": "PKG-CHAT-001",
  "modules/chat_interface/session.py": "PKG-CHAT-001",
  "modules/chat_interface/registry.py": "PKG-CHAT-001",
  "modules/chat_interface/classifier.py": "PKG-CHAT-001",
  "modules/chat_interface/handlers/__init__.py": "PKG-CHAT-001",
  "modules/chat_interface/handlers/browse.py": "PKG-CHAT-001",
  "modules/chat_interface/handlers/packages.py": "PKG-CHAT-001",
  "modules/chat_interface/handlers/search.py": "PKG-CHAT-001",
  "modules/chat_interface/handlers/ledger.py": "PKG-CHAT-001",
  "modules/chat_interface/handlers/help.py": "PKG-CHAT-001",
  "schemas/chat_request.json": "PKG-CHAT-001",
  "schemas/chat_response.json": "PKG-CHAT-001"
}
```

## Query Type Registry

New query types added to classifier:

| Type | Patterns | Handler |
|------|----------|---------|
| BROWSE_DIR | "what is in X", "list files in X", "ls X", "browse X" | browse.list_dir |
| BROWSE_CODE | "read X", "show X", "cat X" | browse.read_file |
| SEARCH_CODE | "search for X", "grep X", "find X" | search.grep |
| PACKAGE_LIST | "list packages", "installed packages" | packages.list_all |
| PACKAGE_INSPECT | "inspect PKG-X", "show PKG-X" | packages.inspect |
| PACKAGE_PREFLIGHT | "preflight PKG-X", "validate PKG-X" | packages.preflight |
| PACKAGE_INSTALL | "install PKG-X" | packages.install |
| PACKAGE_UNINSTALL | "uninstall PKG-X", "remove PKG-X" | packages.uninstall |
| PACKAGE_STAGE | "stage PKG-X" | packages.stage |
| LEDGER_QUERY | "show ledger", "recent activity" | ledger.query |
| HELP | "help", "commands", "what can you do" | help.show |
