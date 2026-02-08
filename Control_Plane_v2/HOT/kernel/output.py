#!/usr/bin/env python3
"""
Formatted output utilities.
"""
from typing import List, Tuple


class ResultReporter:
    """Track and report operation results with consistent formatting."""

    def __init__(self, title: str = ""):
        self.title = title
        self.checks: List[Tuple[str, str, str]] = []  # (status, category, message)
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def ok(self, category: str, message: str):
        self.checks.append(("OK", category, message))
        self.passed += 1

    def fail(self, category: str, message: str):
        self.checks.append(("FAIL", category, message))
        self.failed += 1

    def warn(self, category: str, message: str):
        self.checks.append(("WARN", category, message))
        self.warnings += 1

    def report(self, width: int = 60) -> str:
        """Generate formatted report string."""
        lines = ["=" * width]
        if self.title:
            lines.append(self.title)
            lines.append("=" * width)
        lines.append("")

        current_category = None
        for status, category, msg in self.checks:
            if category != current_category:
                if current_category is not None:
                    lines.append("")
                lines.append(f"[{category}]")
                current_category = category

            symbol = {"OK": "\u2713", "FAIL": "\u2717", "WARN": "\u26a0"}[status]
            lines.append(f"  [{symbol}] {msg}")

        lines.append("")
        lines.append("-" * width)

        if self.failed == 0:
            status = "PASSED"
            if self.warnings > 0:
                status += f" ({self.warnings} warnings)"
            lines.append(f"{status}: {self.passed} checks passed")
        else:
            lines.append(f"FAILED: {self.failed} errors, {self.warnings} warnings")

        lines.append("=" * width)
        return "\n".join(lines)

    @property
    def success(self) -> bool:
        return self.failed == 0
