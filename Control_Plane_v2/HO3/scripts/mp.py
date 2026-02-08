#!/usr/bin/env python3
"""
mp (Markdown Path) — quick visual outline for .md files.

Usage:
    python3 scripts/mp.py <path/to/file.md>

Behavior:
    - Emits a bullet outline of headings and list items.
    - Preserves heading hierarchy (indent = 2 spaces per heading level-1).
    - Indents list items relative to current heading plus their own list indent.
    - Supports unordered (- * +) and ordered (1. 1) lists.

This intentionally avoids external deps; it does light parsing to stay robust.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Tuple


Heading = Tuple[int, str]


def parse_markdown(lines: List[str]) -> List[str]:
    """Convert markdown lines into an indented outline.

    Headings set the base depth. Lists indent relative to current heading plus
    their own leading-space depth (measured in 2-space units).
    """

    outline: List[str] = []
    heading_stack: List[Heading] = []

    for raw in lines:
        line = raw.rstrip("\n")

        # Headings: #{1,6} Title
        m_head = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m_head:
            level = len(m_head.group(1))
            title = m_head.group(2).strip()

            # Maintain stack of headings
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))

            indent = " " * ((level - 1) * 2)
            outline.append(f"{indent}- {title}")
            continue

        # Lists: unordered or ordered
        m_list = re.match(r"^(\s*)([-*+]\s+|\d+[.)]\s+)(.+)$", line)
        if m_list:
            leading_spaces, _, body = m_list.groups()
            # Treat every 2 leading spaces as one indent unit
            list_units = max(0, len(leading_spaces) // 2)
            heading_depth = heading_stack[-1][0] if heading_stack else 1
            base_units = heading_depth - 1
            total_units = base_units + list_units
            indent = " " * (total_units * 2)
            outline.append(f"{indent}- {body.strip()}")

    return outline


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a markdown outline (headings + lists).")
    parser.add_argument("path", type=Path, help="Markdown file to outline")
    args = parser.parse_args()

    if not args.path.is_file():
        print(f"error: file not found: {args.path}")
        return 1

    lines = args.path.read_text(encoding="utf-8").splitlines()
    outline = parse_markdown(lines)

    for line in outline:
        print(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
