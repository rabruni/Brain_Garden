"""DRY_RUN Confirmation Helpers for TOOLS_FIRST handlers.

All tools_first handlers default to dry-run: they describe what they
would do and return a confirmation token.  Execution requires either:

(A) **Two-turn**: user re-sends the query with ``RUN:<confirmation_id>``
(B) **Same-turn**: user includes both an A0 signal AND the keyword EXECUTE

confirmation_id = first 16 hex chars of sha256(canonical_json(proposed_actions)).
Since proposed_actions is deterministic (same query -> same hash), no
server-side state is needed.  The confirmation_id is always computed and
recorded for audit, regardless of which authorization path is used.
"""

import hashlib
import json
import re
from typing import Any, Dict, Optional, Tuple

CONFIRM_RE = re.compile(r"\bRUN:([a-f0-9]{16})\b")

# A0 signal: literal "A0" as a word boundary, or the phrase "Execution Mode"
_A0_RE = re.compile(r"\bA0\b|Execution Mode", re.IGNORECASE)

# Execution keyword: standalone "EXECUTE"
_EXECUTE_RE = re.compile(r"\bEXECUTE\b", re.IGNORECASE)


def extract_confirmation(query: str) -> Tuple[str, Optional[str]]:
    """Strip ``RUN:<hex16>`` from query, return (clean_query, confirmation_id | None)."""
    m = CONFIRM_RE.search(query)
    if not m:
        return query, None
    confirmation_id = m.group(1)
    clean = query[: m.start()].rstrip() + query[m.end() :]
    clean = clean.strip()
    return clean, confirmation_id


def extract_a0_execute(query: str) -> Tuple[str, bool]:
    """Detect A0 + EXECUTE signals and strip them from the query.

    Returns:
        (clean_query, a0_execute) where *a0_execute* is True only when
        BOTH an A0 signal AND the EXECUTE keyword are present.
    """
    has_a0 = bool(_A0_RE.search(query))
    has_execute = bool(_EXECUTE_RE.search(query))

    if not (has_a0 and has_execute):
        return query, False

    # Strip both signals so they don't pollute routing / classification
    clean = _A0_RE.sub("", query)
    clean = _EXECUTE_RE.sub("", clean)
    # Collapse whitespace
    clean = re.sub(r"\s{2,}", " ", clean).strip()
    return clean, True


def compute_confirmation_id(proposed_actions: dict) -> str:
    """Return first 16 hex chars of sha256(canonical JSON of *proposed_actions*)."""
    canonical = json.dumps(proposed_actions, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _build_proposed(handler_name: str, context: Dict[str, Any]) -> dict:
    """Build the deterministic proposed-actions dict for hashing."""
    return {"handler": handler_name, "query": context.get("query", "")}


def check_confirmation(
    handler_name: str,
    context: Dict[str, Any],
    description: str,
) -> Optional[str]:
    """Gate execution behind a confirmation token or A0+EXECUTE authorization.

    Authorization paths (checked in order):
    1. ``confirmation_id`` in context matches expected hash  -> execute (two-turn)
    2. ``a0_execute`` is True in context                     -> execute (same-turn)
    3. Neither present                                       -> dry-run

    The confirmation_id is always computed.  When executing via A0+EXECUTE,
    the id is embedded in the response header so it appears in the ledger.

    Returns:
        A dry-run (or error) response string if execution should NOT proceed,
        or ``None`` if authorization is valid and execution should continue.
    """
    proposed = _build_proposed(handler_name, context)
    expected_id = compute_confirmation_id(proposed)

    confirmation_id = context.get("confirmation_id")
    a0_execute = context.get("a0_execute", False)

    # Path A — two-turn RUN:<token>
    if confirmation_id is not None:
        if confirmation_id != expected_id:
            return (
                f"Confirmation mismatch. Expected RUN:{expected_id} "
                f"but received RUN:{confirmation_id}. "
                f"Re-send the original query to get a fresh token."
            )
        return None  # valid token -> proceed

    # Path B — same-turn A0 + EXECUTE
    if a0_execute:
        # Store confirmation_id in context so handlers / ledger can record it
        context["confirmation_id"] = expected_id
        return None  # authorized -> proceed

    # Default: dry-run
    return (
        f"## Proposed Action: {handler_name}\n"
        f"{description}\n"
        f"To execute, re-send with: RUN:{expected_id}"
    )
