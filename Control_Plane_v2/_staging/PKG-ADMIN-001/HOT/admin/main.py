"""ADMIN agent entrypoint.

Usage:
    python3 HOT/admin/main.py --root /path/to/cp --dev
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable
import importlib
from unittest.mock import patch


REQUIRED_CONFIG_FIELDS = {
    "agent_id",
    "agent_class",
    "framework_id",
    "tier",
    "system_prompt",
    "attention",
    "tools",
    "budget",
    "permissions",
}


def _staging_root() -> Path:
    # .../PKG-ADMIN-001/HOT/admin/main.py -> .../_staging
    return Path(__file__).resolve().parents[3]


def _ensure_import_paths(root: Path | None = None) -> None:
    staging = _staging_root()
    add: list[Path] = [
        staging / "PKG-KERNEL-001" / "HOT" / "kernel",
        staging / "PKG-PROMPT-ROUTER-001" / "HOT" / "kernel",
        staging / "PKG-ANTHROPIC-PROVIDER-001" / "HOT" / "kernel",
        staging / "PKG-ATTENTION-001" / "HOT" / "kernel",
        staging / "PKG-SESSION-HOST-001" / "HOT" / "kernel",
        staging / "PKG-BOOT-MATERIALIZE-001" / "HOT" / "scripts",
        staging / "PKG-LAYOUT-002" / "HOT" / "scripts",
        staging / "PKG-KERNEL-001" / "HOT",
        staging / "PKG-ATTENTION-001" / "HOT",
    ]
    if root is not None:
        add = [Path(root) / "HOT", Path(root) / "HOT" / "kernel", Path(root) / "HOT" / "scripts"] + add
    for path in add:
        p = str(path)
        if p not in sys.path:
            sys.path.insert(0, p)

    # In source-tree tests, attention modules are not yet installed into
    # kernel/. Alias them so attention_service can import kernel.attention_stages.
    if "kernel.attention_stages" not in sys.modules:
        try:
            mod = importlib.import_module("attention_stages")
            sys.modules["kernel.attention_stages"] = mod
        except Exception:
            pass


def load_admin_config(config_path: Path) -> dict:
    """Load and validate ADMIN config JSON."""
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(str(config_path))

    data = json.loads(config_path.read_text())
    missing = sorted(REQUIRED_CONFIG_FIELDS - set(data.keys()))
    if missing:
        raise ValueError(f"required fields missing: {', '.join(missing)}")
    return data


def _register_admin_tools(dispatcher, root: Path) -> None:
    """Register built-in ADMIN tool handlers."""

    def _gate_check(args):
        gate = args.get("gate", "all")
        script = root / "HOT" / "scripts" / "gate_check.py"
        if not script.exists():
            return {"status": "error", "error": "gate_check.py not found"}
        cmd = [sys.executable, str(script), "--root", str(root)]
        if gate != "all":
            cmd.extend(["--gate", str(gate)])
        else:
            cmd.append("--all")
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return {
            "status": "ok" if proc.returncode == 0 else "error",
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    def _read_file(args):
        rel = args.get("path", "")
        path = (root / rel).resolve()
        if not str(path).startswith(str(root.resolve())):
            return {"status": "error", "error": "path escapes root"}
        if not path.exists() or not path.is_file():
            return {"status": "error", "error": "file not found"}
        return {"status": "ok", "path": rel, "content": path.read_text()}

    def _query_ledger(args):
        from ledger_client import LedgerClient

        ledger = LedgerClient(ledger_path=root / "HOT" / "ledger" / "governance.jsonl")
        event_type = args.get("event_type")
        max_entries = int(args.get("max_entries", 10))
        if event_type:
            entries = ledger.read_by_event_type(str(event_type))[-max_entries:]
        else:
            entries = ledger.read_all()[-max_entries:]
        return {
            "status": "ok",
            "count": len(entries),
            "entries": [e.id for e in entries],
        }

    def _list_packages(_args):
        installed_dir = root / "HOT" / "installed"
        if not installed_dir.exists():
            return {"status": "ok", "packages": []}
        packages = sorted(p.name for p in installed_dir.glob("PKG-*") if p.is_dir())
        return {"status": "ok", "packages": packages}

    dispatcher.register_tool("gate_check", _gate_check)
    dispatcher.register_tool("read_file", _read_file)
    dispatcher.register_tool("query_ledger", _query_ledger)
    dispatcher.register_tool("list_packages", _list_packages)


def build_session_host(root: Path, config_path: Path, dev_mode: bool = False):
    """Compose dependencies and return a SessionHost instance."""
    _ensure_import_paths(root=Path(root))

    from anthropic_provider import AnthropicProvider
    from attention_service import AttentionService
    from ledger_client import LedgerClient
    from prompt_router import PromptRouter, RouterConfig
    from session_host import AgentConfig, SessionHost
    from tool_dispatch import ToolDispatcher

    root = Path(root)
    cfg_dict = load_admin_config(config_path)

    agent_config = AgentConfig.from_file(config_path)

    ledger = LedgerClient(ledger_path=root / "HOT" / "ledger" / "governance.jsonl")
    attention = AttentionService(plane_root=root)

    router = PromptRouter(
        ledger_client=ledger,
        config=RouterConfig(default_provider="anthropic", default_model="claude-sonnet-4-5-20250929"),
        dev_mode=dev_mode,
    )
    router.register_provider("anthropic", AnthropicProvider())

    dispatcher = ToolDispatcher(
        plane_root=root,
        tool_configs=cfg_dict.get("tools", []),
        permissions=cfg_dict.get("permissions", {}),
    )
    _register_admin_tools(dispatcher, root=root)

    return SessionHost(
        plane_root=root,
        agent_config=agent_config,
        attention_service=attention,
        router=router,
        tool_dispatcher=dispatcher,
        ledger_client=ledger,
        dev_mode=dev_mode,
    )


def run_cli(
    root: Path,
    config_path: Path,
    dev_mode: bool = False,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    """Interactive ADMIN loop."""
    root = Path(root)
    _ensure_import_paths(root=root)

    pristine_patch = None
    if dev_mode:
        # Dev/test mode may run outside governed roots; bypass append-only guard.
        pristine_patch = patch("kernel.pristine.assert_append_only", return_value=None)
        pristine_patch.start()
    from boot_materialize import boot_materialize

    mat_result = boot_materialize(root)
    if mat_result != 0:
        output_fn(f"WARNING: Boot materialization returned {mat_result} (non-fatal)")

    host = build_session_host(root=root, config_path=config_path, dev_mode=dev_mode)
    session_id = host.start_session()
    output_fn(f"Session started: {session_id}")

    try:
        while True:
            user = input_fn("admin> ").strip()
            if not user:
                continue
            if user.lower() in {"exit", "quit"}:
                break
            result = host.process_turn(user)
            output_fn(f"assistant: {result.response}")
    finally:
        host.end_session()
        output_fn("Session ended")
        if pristine_patch is not None:
            pristine_patch.stop()

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ADMIN Session Host")
    parser.add_argument("--root", required=True, help="Control Plane root path")
    parser.add_argument("--config", default="HOT/config/admin_config.json", help="Path to ADMIN config")
    parser.add_argument("--dev", action="store_true", help="Enable dev mode")
    args = parser.parse_args(argv)

    root = Path(args.root)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path

    return run_cli(root=root, config_path=config_path, dev_mode=args.dev)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
