#!/usr/bin/env python3
"""
Pre-tool hook: blocks Edit/Write on Control Plane governed files.

Governed files are those tracked in registries/file_ownership.csv.
Direct edits break the SHA256 hash chain and fail G0B gate checks.

User override: when blocked, Claude Code prompts the user with "ask"
so they can approve the edit if they know what they're doing.

Reads JSON from stdin (Claude Code hook protocol), writes JSON to stdout.
Exit 0 = processed (decision in JSON), Exit 2 = hard block.
"""
import csv
import json
import os
import sys

def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)  # Can't parse — allow

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)  # No file path — allow (not an Edit/Write)

    # Find Control_Plane_v2 root relative to the file being edited
    cp_marker = "Control_Plane_v2/"
    idx = file_path.find(cp_marker)
    if idx == -1:
        sys.exit(0)  # Not in Control_Plane_v2 — allow

    cp_root = file_path[:idx + len(cp_marker)]
    rel_path = file_path[idx + len(cp_marker):]

    # Load governed file list from file_ownership.csv
    ownership_csv = os.path.join(cp_root, "registries", "file_ownership.csv")
    if not os.path.exists(ownership_csv):
        sys.exit(0)  # No ownership registry — allow

    governed_paths = set()
    try:
        with open(ownership_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                fp = row.get("file_path", "").strip()
                if fp:
                    governed_paths.add(fp)
    except Exception:
        sys.exit(0)  # Can't read registry — fail open

    if rel_path not in governed_paths:
        sys.exit(0)  # Not governed — allow

    # Governed file — ask user for override
    owner = ""
    try:
        with open(ownership_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("file_path", "").strip() == rel_path:
                    owner = row.get("owner_package_id", "unknown")
                    break
    except Exception:
        owner = "unknown"

    reason = (
        f"GOVERNED FILE: '{rel_path}' is owned by {owner}. "
        f"Direct edits break the hash chain and fail G0B. "
        f"Use the package workflow (pkgutil + package_install.py) instead. "
        f"Approve to override this protection."
    )

    result = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
