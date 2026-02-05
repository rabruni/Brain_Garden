"""Control Plane governance commands.

Provides: :pkg, :ledger, :gate, :wo, :compliance, :trace
These are NEW commands specific to Control Plane integration.
"""

import json
from pathlib import Path
from typing import Dict, Callable

from modules.shell.chat_ui import Colors


def _get_inspector(shell):
    """Get CPInspector instance."""
    try:
        from lib.agent_helpers import CPInspector

        return CPInspector(shell.root)
    except ImportError:
        return None


def cmd_pkg(shell, args: str) -> bool:
    """List or show package details.

    Usage: :pkg            - List installed packages
           :pkg <id>       - Show package details
    """
    inspector = _get_inspector(shell)
    if not inspector:
        shell.ui.print_error("CPInspector not available")
        return True

    args = args.strip()

    if args:
        # Show specific package
        shell.ui.print_system_message(f"Package: {args}")

        # Try to find manifest
        installed_dir = shell.root / "installed" / args
        manifest_path = installed_dir / "manifest.json"

        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
                print(f"\n  Package ID: {manifest.get('package_id', 'unknown')}")
                print(f"  Version:    {manifest.get('version', 'unknown')}")
                print(f"  Spec:       {manifest.get('spec_id', 'none')}")
                print(f"  Plane:      {manifest.get('plane_id', 'unknown')}")
                print(f"  Type:       {manifest.get('package_type', 'standard')}")

                assets = manifest.get("assets", [])
                print(f"\n  Assets ({len(assets)} files):")
                for asset in assets[:10]:
                    path = asset.get("path", "?")
                    classification = asset.get("classification", "other")
                    print(f"    [{classification}] {path}")
                if len(assets) > 10:
                    print(f"    ... and {len(assets) - 10} more")

                # Add to reads for evidence
                shell._reads_this_turn.append(
                    {"path": str(manifest_path), "type": "manifest"}
                )

            except json.JSONDecodeError:
                shell.ui.print_error(f"Invalid manifest for {args}")
        else:
            shell.ui.print_error(f"Package not found: {args}")
    else:
        # List all packages
        packages, evidence = inspector.list_installed()

        shell.ui.print_system_message("Installed Packages")
        print()

        if not packages:
            print(f"  {Colors.DIM}No packages installed{Colors.RESET}")
        else:
            print(f"  {'Package ID':<30} {'Version':<10} {'Assets':<8} {'Type':<12}")
            print(f"  {'-'*30} {'-'*10} {'-'*8} {'-'*12}")
            for pkg in packages:
                print(
                    f"  {pkg.package_id:<30} {pkg.version:<10} {pkg.assets_count:<8} {pkg.package_type:<12}"
                )

        # Add to reads
        shell._reads_this_turn.append(
            {"path": evidence.path, "hash": evidence.hash, "type": "installed"}
        )

    return True


def cmd_ledger(shell, args: str) -> bool:
    """Show ledger entries.

    Usage: :ledger              - Show recent governance entries
           :ledger <type>       - Filter by event type
           :ledger session      - Show session ledger
    """
    args = args.strip().lower()

    shell.ui.print_system_message("Ledger Entries")

    if args == "session" and shell._session:
        # Show session ledger
        exec_path = shell._session.exec_ledger_path
        if exec_path.exists():
            print(f"\n  Session Ledger: {exec_path}")
            print()
            try:
                with open(exec_path, "r") as f:
                    lines = f.readlines()[-10:]  # Last 10 entries
                    for i, line in enumerate(lines):
                        entry = json.loads(line)
                        turn = entry.get("turn_number", "?")
                        status = entry.get("status", "?")
                        print(
                            f"  #{turn}: {status} - {entry.get('command', entry.get('event_type', '?'))[:50]}"
                        )
                shell._reads_this_turn.append(
                    {"path": str(exec_path), "type": "session_ledger"}
                )
            except Exception as e:
                shell.ui.print_error(f"Error reading ledger: {e}")
        else:
            print(f"  {Colors.DIM}No session ledger yet{Colors.RESET}")
        return True

    # Show governance ledger
    ledger_dir = shell.root / "ledger"
    if not ledger_dir.exists():
        print(f"  {Colors.DIM}No ledger directory{Colors.RESET}")
        return True

    # Find most recent governance ledger
    ledger_files = sorted(ledger_dir.glob("governance-*.jsonl"), reverse=True)
    if not ledger_files:
        print(f"  {Colors.DIM}No governance ledger files{Colors.RESET}")
        return True

    ledger_path = ledger_files[0]
    print(f"\n  Ledger: {ledger_path.name}")
    print()

    try:
        with open(ledger_path, "r") as f:
            lines = f.readlines()

        # Filter if type specified
        entries = []
        for line in lines:
            if line.strip():
                try:
                    entry = json.loads(line)
                    event_type = entry.get("event_type", "")
                    if not args or args in event_type.lower():
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue

        # Show last 10
        for entry in entries[-10:]:
            event_type = entry.get("event_type", "?")
            timestamp = entry.get("timestamp", "?")[:19]
            decision = entry.get("decision", entry.get("status", "?"))
            print(f"  [{timestamp}] {event_type}: {decision}")

        if not entries:
            print(f"  {Colors.DIM}No matching entries{Colors.RESET}")

        shell._reads_this_turn.append({"path": str(ledger_path), "type": "governance"})

    except Exception as e:
        shell.ui.print_error(f"Error reading ledger: {e}")

    return True


def cmd_gate(shell, args: str) -> bool:
    """Show gate status.

    Usage: :gate            - Show all gate status
           :gate <id>       - Show specific gate details
    """
    inspector = _get_inspector(shell)

    shell.ui.print_system_message("Gate Status")
    print()

    # Get recent failures
    if inspector:
        failures, evidence = inspector.last_gate_failures(count=5)

        if failures:
            print(f"  {Colors.BOLD}Recent Failures:{Colors.RESET}")
            for f in failures:
                print(
                    f"    {Colors.RED}✗{Colors.RESET} {f.gate}: {f.error_message[:50]}"
                )
            print()
            shell._reads_this_turn.append(
                {"path": evidence.path, "hash": evidence.hash, "type": "gate_failures"}
            )
        else:
            print(f"  {Colors.GREEN}✓{Colors.RESET} No recent gate failures")
            print()

    # Show gate descriptions
    gates = {
        "MANIFEST": "Basic manifest structure validation",
        "G0A": "Package declaration consistency",
        "G0B": "Entry point and dependency check",
        "G1": "Governance chain validation",
        "OWN": "File ownership validation",
        "G3": "Test execution",
        "G4": "Ledger replication",
        "G5": "Signature validation",
    }

    print(f"  {Colors.BOLD}Gates:{Colors.RESET}")
    for gate_id, desc in gates.items():
        print(f"    {gate_id:<10} {desc}")

    return True


def cmd_wo(shell, args: str) -> bool:
    """Show work orders.

    Usage: :wo              - List work orders
           :wo <id>         - Show work order details
    """
    shell.ui.print_system_message("Work Orders")
    print()

    # Look for work order ledger
    wo_path = shell.root / "planes" / "ho2" / "ledger" / "workorder.jsonl"

    if not wo_path.exists():
        print(f"  {Colors.DIM}No work order ledger{Colors.RESET}")
        return True

    try:
        with open(wo_path, "r") as f:
            lines = f.readlines()[-10:]

        for line in lines:
            if line.strip():
                entry = json.loads(line)
                wo_id = entry.get("metadata", {}).get("work_order_id", "?")
                status = entry.get("decision", entry.get("status", "?"))
                print(f"  {wo_id}: {status}")

        shell._reads_this_turn.append({"path": str(wo_path), "type": "workorder"})

    except Exception as e:
        shell.ui.print_error(f"Error reading work orders: {e}")

    return True


def cmd_compliance(shell, args: str) -> bool:
    """Show compliance information.

    Usage: :compliance      - Show compliance summary
    """
    inspector = _get_inspector(shell)
    if not inspector:
        shell.ui.print_error("CPInspector not available")
        return True

    shell.ui.print_system_message("Compliance Summary")

    # Get chain info
    chain, _ = inspector.get_governance_chain()
    print(f"\n  {Colors.BOLD}Governance Chain:{Colors.RESET}")
    for level in chain.get("chain", []):
        pattern = level.get("id_pattern", level.get("pattern", "?"))
        print(f"    {level.get('level', '?')}. {level.get('name', '?')}: {pattern}")

    # Get gate requirements
    gates, _ = inspector.get_gate_requirements()
    print(f"\n  {Colors.BOLD}Required Gates:{Colors.RESET}")
    for gate_id, gate_info in gates.get("gates", {}).items():
        phase = gate_info.get("phase", "?")
        desc = gate_info.get("description", "?")[:40]
        print(f"    {gate_id} ({phase}): {desc}")

    # Get stats
    stats, evidence = inspector.get_registry_stats()
    print(f"\n  {Colors.BOLD}Registry Stats:{Colors.RESET}")
    print(f"    Registries: {stats.get('registries', 0)}")
    print(f"    Total items: {stats.get('total_items', 0)}")

    shell._reads_this_turn.append(
        {"path": evidence.path, "hash": evidence.hash, "type": "registries"}
    )

    return True


def cmd_trace(shell, args: str) -> bool:
    """Trace artifact lineage.

    Usage: :trace <id>      - Trace artifact
    """
    if not args.strip():
        shell.ui.print_error("Usage: :trace <artifact_id>")
        return True

    artifact_id = args.strip()
    shell.ui.print_system_message(f"Tracing: {artifact_id}")

    # Try to use trace.py
    import subprocess

    trace_script = shell.root / "scripts" / "trace.py"
    if not trace_script.exists():
        shell.ui.print_error("trace.py not found")
        return True

    try:
        import sys

        result = subprocess.run(
            [sys.executable, str(trace_script), "--explain", artifact_id, "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(shell.root),
        )

        if result.stdout:
            data = json.loads(result.stdout)
            data_type = data.get("type", "unknown")
            info = data.get("data", {})

            print(f"\n  Type: {data_type}")
            if data_type == "file":
                ownership = info.get("ownership", {})
                print(f"  Framework: {ownership.get('framework_id', '?')}")
                print(f"  Spec: {ownership.get('spec_id', '?')}")
                print(f"  Package: {ownership.get('package', '?')}")
            elif data_type == "package":
                print(f"  Package ID: {info.get('package_id', '?')}")
                print(f"  Files: {len(info.get('files', []))}")
            elif data_type == "framework":
                print(f"  Framework ID: {info.get('framework_id', '?')}")
                print(f"  Title: {info.get('title', '?')}")
                print(f"  Specs: {len(info.get('specs', []))}")
            else:
                print(f"  {json.dumps(info, indent=2)[:500]}")

        if result.stderr:
            print(f"  {Colors.DIM}{result.stderr}{Colors.RESET}")

    except subprocess.TimeoutExpired:
        shell.ui.print_error("Trace timed out")
    except json.JSONDecodeError:
        print(result.stdout if result.stdout else "No output")
    except Exception as e:
        shell.ui.print_error(f"Trace error: {e}")

    return True


GOVERNANCE_COMMANDS: Dict[str, Callable] = {
    "pkg": cmd_pkg,
    "package": cmd_pkg,
    "packages": cmd_pkg,
    "ledger": cmd_ledger,
    "gate": cmd_gate,
    "gates": cmd_gate,
    "wo": cmd_wo,
    "workorder": cmd_wo,
    "compliance": cmd_compliance,
    "trace": cmd_trace,
}
