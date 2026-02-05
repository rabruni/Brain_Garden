#!/usr/bin/env python3
"""Control Plane Universal Shell entry point.

This script provides the main entry point for launching the Universal Shell,
a rich terminal interface for interacting with the Control Plane.

Usage:
    python scripts/shell.py                    # Default agent
    python scripts/shell.py --debug            # Enable debug mode
    python scripts/shell.py --tier ho2         # Run in HO2 tier

Example:
    $ cd Control_Plane_v2
    $ python scripts/shell.py --debug

    Control Plane Shell
    ──────────────────────────────────────────────────────────────
      cp_default v1.0.0 | DEBUG | SES-20260203-abc123
    ──────────────────────────────────────────────────────────────

    Commands (vim-style, prefix with :):
      :h  :help         Show help
      :pkg              List installed packages
      :ledger           Show recent ledger entries
      :q  :quit         Quit

    You: :pkg
    ── Installed Packages ──

    You: :q
    ── Goodbye! ──
"""

import argparse
import sys
from pathlib import Path

# Add Control_Plane_v2 to path
SCRIPT_DIR = Path(__file__).resolve().parent
CP_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(CP_ROOT))

from modules.shell import UniversalShell, create_default_agent


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Control Plane Universal Shell",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/shell.py                Launch shell with default agent
  python scripts/shell.py --debug        Enable debug mode
  python scripts/shell.py --tier ho2     Run in HO2 tier
        """,
    )
    parser.add_argument(
        "--agent",
        "-a",
        type=str,
        default="default",
        help="Agent to use (default: 'default')",
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Enable debug mode (shows state after each turn)",
    )
    parser.add_argument(
        "--tier",
        type=str,
        default="ho1",
        choices=["ho1", "ho2", "ho3"],
        help="Operating tier (default: ho1)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Control Plane root directory (default: auto-detect)",
    )

    args = parser.parse_args()

    # Determine root
    root = args.root or CP_ROOT

    # Create agent
    if args.agent == "default":
        agent = create_default_agent(tier=args.tier)
    else:
        # Future: support loading custom agents
        print(f"Unknown agent: {args.agent}", file=sys.stderr)
        print("Available agents: default", file=sys.stderr)
        sys.exit(1)

    # Run shell
    shell = UniversalShell(agent, debug=args.debug, root=root)

    try:
        shell.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\nShell error: {e}", file=sys.stderr)
        if args.debug:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
