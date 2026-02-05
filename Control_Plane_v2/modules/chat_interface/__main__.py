#!/usr/bin/env python3
"""Chat Interface CLI.

Supports three modes:
1. Pipe mode: Read JSON from stdin, write JSON to stdout
2. Interactive mode: REPL for conversational interaction
3. Single query mode: Execute one query and exit

Usage:
    # Pipe mode (default)
    echo '{"query": "list packages"}' | python3 -m modules.chat_interface

    # Interactive mode
    python3 -m modules.chat_interface --interactive

    # Single query
    python3 -m modules.chat_interface "what is in modules?"
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from modules.chat_interface import ChatInterface, chat_turn


def pipe_mode(tier: str = "ho1", capability: str = None) -> int:
    """Process JSON from stdin, write JSON to stdout.

    Input format:
        {"query": "...", "capability": "..."}

    Output format:
        {"response": "...", "session_id": "...", ...}

    Args:
        tier: Tier name
        capability: Default capability

    Returns:
        Exit code
    """
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        error = {"error": f"Invalid JSON input: {e}"}
        print(json.dumps(error))
        return 1

    query = input_data.get("query", "")
    cap = input_data.get("capability", capability)

    if not query:
        error = {"error": "Missing 'query' field in input"}
        print(json.dumps(error))
        return 1

    interface = ChatInterface(tier=tier, capability=cap)
    result = chat_turn(interface, query)

    print(json.dumps(result, indent=2))
    return 0


def interactive_mode(tier: str = "ho1", capability: str = None) -> int:
    """Run interactive REPL.

    Args:
        tier: Tier name
        capability: Default capability

    Returns:
        Exit code
    """
    interface = ChatInterface(tier=tier, capability=capability)

    print("=" * 60)
    print("Control Plane Chat Interface")
    print(f"Session: {interface.session_id}")
    print(f"Tier: {tier}")
    if capability:
        print(f"Capability: {capability}")
    print("=" * 60)
    print()
    print("Type 'help' for available commands, '/quit' to exit.")
    print()

    while True:
        try:
            query = input("> ").strip()
        except EOFError:
            print("\nGoodbye!")
            break
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break

        if not query:
            continue

        if query.lower() in ("/quit", "/exit", "/q"):
            print("Goodbye!")
            break

        if query.lower() == "/session":
            print(f"Session: {interface.session_id}")
            print(f"Turns: {interface.session.turn_count}")
            print(f"Ledger: {interface.session.get_ledger_path()}")
            continue

        result = chat_turn(interface, query)

        print()
        print(result["response"])
        print()
        print(f"[{result['handler']} | {result['duration_ms']}ms | Turn {result['turn_number']}]")
        print()

    # Flush session ledger
    interface.session.flush()
    return 0


def single_query_mode(query: str, tier: str = "ho1", capability: str = None) -> int:
    """Execute a single query.

    Args:
        query: Query string
        tier: Tier name
        capability: Capability level

    Returns:
        Exit code
    """
    interface = ChatInterface(tier=tier, capability=capability)
    result = chat_turn(interface, query)

    print(result["response"])
    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Control Plane Chat Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Pipe mode (read JSON from stdin)
    echo '{"query": "list packages"}' | python3 -m modules.chat_interface

    # Interactive mode
    python3 -m modules.chat_interface --interactive

    # Single query
    python3 -m modules.chat_interface "what is in modules?"

    # With admin capability
    python3 -m modules.chat_interface --capability admin --interactive
"""
    )

    parser.add_argument(
        "query",
        nargs="?",
        help="Query to execute (if not using pipe mode)"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode"
    )
    parser.add_argument(
        "--tier", "-t",
        default="ho1",
        choices=["ho1", "ho2", "ho3"],
        help="Tier name (default: ho1)"
    )
    parser.add_argument(
        "--capability", "-c",
        help="Capability level (e.g., admin)"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON (for single query mode)"
    )

    args = parser.parse_args()

    if args.interactive:
        return interactive_mode(args.tier, args.capability)

    if args.query:
        if args.json:
            interface = ChatInterface(tier=args.tier, capability=args.capability)
            result = chat_turn(interface, args.query)
            print(json.dumps(result, indent=2))
            return 0
        return single_query_mode(args.query, args.tier, args.capability)

    # Pipe mode (default if no query and not interactive)
    return pipe_mode(args.tier, args.capability)


if __name__ == "__main__":
    sys.exit(main())
