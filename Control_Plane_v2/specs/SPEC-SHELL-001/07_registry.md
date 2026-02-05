# Registry Entries

## Framework Entry

**File**: `registries/frameworks_registry.csv`

```csv
framework_id,title,status,version,plane_id,created_at
FMWK-SHELL-001,Shell/CLI Development Standard,active,1.0.0,ho3,2026-02-03T00:00:00Z
```

## Spec Entry

**File**: `registries/specs_registry.csv`

```csv
spec_id,title,framework_id,status,version,plane_id,created_at
SPEC-SHELL-001,Universal Shell,FMWK-SHELL-001,active,1.0.0,ho3,2026-02-03T00:00:00Z
```

## Package Assets

**Module Files**:
- `modules/shell/__init__.py`
- `modules/shell/shell.py`
- `modules/shell/chat_ui.py`
- `modules/shell/interfaces.py`
- `modules/shell/commands/__init__.py`
- `modules/shell/commands/core.py`
- `modules/shell/commands/memory.py`
- `modules/shell/commands/signals.py`
- `modules/shell/commands/governance.py`
- `modules/shell/commands/notes.py`
- `modules/shell/capabilities.json`
- `modules/shell/README.md`

**Script Files**:
- `scripts/shell.py`

**Test Files**:
- `tests/test_shell.py`
- `tests/test_shell_commands.py`

## Dependencies

| Dependency | Version | Required |
|------------|---------|----------|
| prompt_toolkit | >=3.0.0 | Yes |
| pyyaml | >=6.0 | No |

## Version

```yaml
spec_id: SPEC-SHELL-001
version: 1.0.0
created: 2026-02-03
updated: 2026-02-03
```
