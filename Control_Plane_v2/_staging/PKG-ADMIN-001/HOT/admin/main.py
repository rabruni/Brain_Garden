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
        staging / "PKG-ANTHROPIC-PROVIDER-001" / "HOT" / "kernel",
        staging / "PKG-BOOT-MATERIALIZE-001" / "HOT" / "scripts",
        staging / "PKG-LAYOUT-002" / "HOT" / "scripts",
        staging / "PKG-KERNEL-001" / "HOT",
        # V2 Kitchener loop packages
        staging / "PKG-WORK-ORDER-001" / "HOT" / "kernel",
        staging / "PKG-LLM-GATEWAY-001" / "HOT" / "kernel",
        staging / "PKG-HO1-EXECUTOR-001" / "HO1" / "kernel",
        staging / "PKG-HO2-SUPERVISOR-001" / "HO2" / "kernel",
        staging / "PKG-SESSION-HOST-V2-001" / "HOT" / "kernel",
        staging / "PKG-SHELL-001" / "HOT" / "kernel",
        staging / "PKG-TOKEN-BUDGETER-001" / "HOT" / "kernel",
    ]
    if root is not None:
        add = [
            Path(root) / "HOT", Path(root) / "HOT" / "kernel", Path(root) / "HOT" / "scripts",
            Path(root) / "HO1" / "kernel", Path(root) / "HO2" / "kernel",
        ] + add
    for path in add:
        p = str(path)
        if p not in sys.path:
            sys.path.insert(0, p)


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


def build_session_host_v2(
    root: Path,
    config_path: Path,
    dev_mode: bool = False,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
):
    """Compose the V2 Kitchener loop and return a Shell instance."""
    _ensure_import_paths(root=Path(root))

    from anthropic_provider import AnthropicProvider
    from contract_loader import ContractLoader
    from ho1_executor import HO1Executor
    from ho2_supervisor import HO2Config, HO2Supervisor
    from ledger_client import LedgerClient
    from llm_gateway import LLMGateway, RouterConfig
    from session_host_v2 import AgentConfig as V2AgentConfig, SessionHostV2
    from shell import Shell
    from token_budgeter import BudgetConfig, TokenBudgeter
    from tool_dispatch import ToolDispatcher
    from work_order import WorkOrder  # verify import works

    root = Path(root)
    cfg_dict = load_admin_config(config_path)

    # 1. Ledger clients — three separate paths
    (root / "HO2" / "ledger").mkdir(parents=True, exist_ok=True)
    (root / "HO1" / "ledger").mkdir(parents=True, exist_ok=True)
    ledger_gov = LedgerClient(ledger_path=root / "HOT" / "ledger" / "governance.jsonl")
    ledger_ho2m = LedgerClient(ledger_path=root / "HO2" / "ledger" / "ho2m.jsonl")
    ledger_ho1m = LedgerClient(ledger_path=root / "HO1" / "ledger" / "ho1m.jsonl")

    # 2. Token budgeter
    budget_cfg = cfg_dict.get("budget", {})
    budgeter = TokenBudgeter(
        ledger_client=ledger_gov,
        config=BudgetConfig(
            session_token_limit=budget_cfg.get("session_token_limit", 200000),
        ),
    )

    # 3. Contract loader + Tool dispatcher
    contract_loader = ContractLoader(contracts_dir=root / "HO1" / "contracts")
    dispatcher = ToolDispatcher(
        plane_root=root,
        tool_configs=cfg_dict.get("tools", []),
        permissions=cfg_dict.get("permissions", {}),
    )
    _register_admin_tools(dispatcher, root=root)

    # 4. LLM Gateway
    gateway = LLMGateway(
        ledger_client=ledger_gov,
        budgeter=budgeter,
        config=RouterConfig(
            default_provider="anthropic",
            default_model="claude-sonnet-4-5-20250929",
        ),
        dev_mode=dev_mode,
    )
    gateway.register_provider("anthropic", AnthropicProvider())

    # 5. HO1 Executor
    ho1_config = {
        "agent_id": cfg_dict.get("agent_id", "admin-001") + ".ho1",
        "agent_class": cfg_dict.get("agent_class", "ADMIN"),
        "tier": "ho1",
        "framework_id": cfg_dict.get("framework_id", "FMWK-000"),
        "package_id": "PKG-HO1-EXECUTOR-001",
    }
    ho1 = HO1Executor(
        gateway=gateway,
        ledger=ledger_ho1m,
        budgeter=budgeter,
        tool_dispatcher=dispatcher,
        contract_loader=contract_loader,
        config=ho1_config,
    )

    # 6. HO2 Supervisor
    ho2_config = HO2Config(
        attention_templates=["ATT-ADMIN-001"],
        ho2m_path=root / "HO2" / "ledger" / "ho2m.jsonl",
        ho1m_path=root / "HO1" / "ledger" / "ho1m.jsonl",
        budget_ceiling=budget_cfg.get("session_token_limit", 200000),
        tools_allowed=[t["tool_id"] for t in cfg_dict.get("tools", [])],
    )
    ho2 = HO2Supervisor(
        plane_root=root,
        agent_class=cfg_dict.get("agent_class", "ADMIN"),
        ho1_executor=ho1,
        ledger_client=ledger_ho2m,
        token_budgeter=budgeter,
        config=ho2_config,
    )

    # 7. V2 Agent Config
    v2_agent_config = V2AgentConfig(
        agent_id=cfg_dict["agent_id"],
        agent_class=cfg_dict["agent_class"],
        framework_id=cfg_dict["framework_id"],
        tier=cfg_dict["tier"],
        system_prompt=cfg_dict["system_prompt"],
        attention=cfg_dict["attention"],
        tools=cfg_dict["tools"],
        budget=cfg_dict["budget"],
        permissions=cfg_dict["permissions"],
    )

    # 8. Session Host V2
    sh_v2 = SessionHostV2(
        ho2_supervisor=ho2,
        gateway=gateway,
        agent_config=v2_agent_config,
        ledger_client=ledger_gov,
    )

    # 9. Shell
    return Shell(sh_v2, v2_agent_config, input_fn, output_fn)


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

    shell = build_session_host_v2(root, config_path, dev_mode, input_fn, output_fn)
    shell.run()
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
