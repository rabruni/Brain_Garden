#!/usr/bin/env python3
"""Interactive chat with the Admin Agent.

Usage:
    python3 scripts/chat.py
    python3 scripts/chat.py --token <auth_token>

Commands:
    /quit or /exit - Exit the chat
    /help - Show help
    /session - Show current session ID
"""

import os
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.admin_agent import admin_turn
from modules.agent_runtime.session import generate_session_id


def authenticate(token: str = None) -> tuple[str, list[str]]:
    """Authenticate user and return identity.

    Args:
        token: Optional auth token (user:signature for HMAC)

    Returns:
        Tuple of (username, roles)

    Raises:
        SystemExit if authentication fails
    """
    from lib.auth import get_provider, AuthConfigError

    try:
        provider = get_provider()
        identity = provider.authenticate(token)

        if identity is None:
            print("Authentication failed. Invalid or missing token.")
            print("Use: python3 scripts/chat.py --token <user:signature>")
            sys.exit(1)

        return identity.user, identity.roles

    except AuthConfigError as e:
        print(f"Auth configuration error: {e}")
        sys.exit(1)


def handle_query(query: str, session_id: str, turn: int) -> str:
    """Route all queries through admin_turn for proper session logging.

    All queries go through admin_turn which:
    - Uses the authenticated session for tracking
    - Logs to the session ledger
    - Routes to appropriate handlers (tools-first or LLM-assisted)
    """
    return admin_turn(query, session_id=session_id, turn_number=turn)


def print_help(session_id: str):
    print(f"""
Session: {session_id}

Commands:
  /quit, /exit  - Exit the chat
  /help         - Show this help
  /session      - Show session ID

Example queries:
  What packages are installed?
  Explain FMWK-000
  System health
  Show me this session's ledger
""")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Chat with the Admin Agent")
    parser.add_argument("--token", help="Auth token (user:signature for HMAC)")
    parser.add_argument("--dev", action="store_true", help="Dev mode (passthrough auth with system username)")
    args = parser.parse_args()

    # Dev mode: use passthrough auth with system username
    if args.dev:
        os.environ["CONTROL_PLANE_AUTH_PROVIDER"] = "passthrough"
        os.environ["CONTROL_PLANE_ALLOW_PASSTHROUGH"] = "1"

    # Get token from args or environment
    token = args.token or os.getenv("CONTROL_PLANE_TOKEN")

    # Authenticate
    user, roles = authenticate(token)

    # Generate session ID tied to authenticated user
    session_id = generate_session_id(user=user)

    print("=" * 50)
    print("  Control Plane Admin Agent")
    print(f"  User: {user} | Roles: {', '.join(roles)}")
    print(f"  Session: {session_id}")
    print("  Type /help for commands, /quit to exit")
    print("=" * 50)
    print()

    turn = 0

    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not query:
            continue

        # Handle commands
        if query.lower() in ["/quit", "/exit", "quit", "exit"]:
            print("Goodbye!")
            break

        if query.lower() == "/help":
            print_help(session_id)
            continue

        if query.lower() == "/session":
            print(f"\nSession ID: {session_id}\n")
            continue

        # Execute turn - all queries routed through admin_turn with session
        turn += 1
        try:
            result = handle_query(query, session_id, turn)
            print()
            print("Agent:", result)
            print()
        except Exception as e:
            print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
