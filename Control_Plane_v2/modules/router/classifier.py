"""Query Classification.

Pattern-based classification for tools-first routing.
Only falls back to LLM classification when explicitly enabled.

Example:
    from modules.router.classifier import classify_query

    result = classify_query("What packages are installed?")
    # Returns QueryClassification(type="list", confidence=1.0, pattern_matched=True)
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class QueryType(str, Enum):
    """Types of queries."""
    LIST = "list"
    EXPLAIN = "explain"
    STATUS = "status"
    INVENTORY = "inventory"
    VALIDATE = "validate"
    SUMMARIZE = "summarize"
    LEDGER = "ledger"
    PROMPTS = "prompts"  # Show governed prompts usage
    SESSION_LEDGER = "session_ledger"  # Show current session's ledger
    READ_FILE = "read_file"
    LIST_FRAMEWORKS = "list_frameworks"
    LIST_SPECS = "list_specs"
    LIST_FILES = "list_files"
    GENERAL = "general"


@dataclass
class QueryClassification:
    """Result of query classification."""

    type: QueryType
    confidence: float
    pattern_matched: bool
    matched_pattern: Optional[str] = None
    extracted_args: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "confidence": self.confidence,
            "pattern_matched": self.pattern_matched,
            "matched_pattern": self.matched_pattern,
            "extracted_args": self.extracted_args,
        }


# Pattern definitions for each query type
# Order matters - more specific patterns should come first
PATTERNS: Dict[QueryType, List[tuple]] = {
    QueryType.LIST: [
        (r"list\s+(all\s+)?packages", "list packages"),
        (r"what\s+(packages|pkgs)\s+(are\s+)?installed", "packages installed"),
        (r"show\s+(installed\s+)?packages", "show packages"),
        (r"installed\s+packages", "installed packages"),
        (r"^packages$", "packages"),
    ],
    QueryType.EXPLAIN: [
        (r"explain\s+(FMWK-[\w-]+|SPEC-[\w-]+|PKG-[\w-]+)", "explain artifact"),
        (r"what\s+is\s+(FMWK-[\w-]+|SPEC-[\w-]+|PKG-[\w-]+)", "what is artifact"),
        (r"describe\s+(FMWK-[\w-]+|SPEC-[\w-]+|PKG-[\w-]+)", "describe artifact"),
        (r"tell\s+me\s+about\s+(FMWK-[\w-]+|SPEC-[\w-]+|PKG-[\w-]+)", "tell about"),
        (r"^(FMWK-[\w-]+|SPEC-[\w-]+|PKG-[\w-]+)$", "direct artifact id"),
        (r"explain\s+(\S+\.py|\S+\.md)", "explain file"),
    ],
    QueryType.STATUS: [
        (r"(system\s+)?health(\s+check)?", "health check"),
        (r"(system\s+)?status", "system status"),
        (r"is\s+.*\s+ok\??", "is ok"),
        (r"verify(\s+system)?", "verify"),
        (r"check\s+(system\s+)?integrity", "check integrity"),
    ],
    QueryType.INVENTORY: [
        (r"(show\s+)?inventory", "inventory"),
        (r"file\s+count", "file count"),
        (r"orphan\s+files?", "orphan files"),
    ],
    QueryType.VALIDATE: [
        (r"validate\s+", "validate"),
        (r"check\s+compliance", "check compliance"),
        (r"verify\s+.*\s+against", "verify against"),
    ],
    QueryType.SUMMARIZE: [
        (r"summarize\s+", "summarize"),
        (r"what\s+frameworks\s+belong", "frameworks belong"),
        (r"how\s+.*\s+relate", "how relate"),
        (r"relationship\s+between", "relationship"),
        (r"overview\s+of", "overview"),
    ],
    QueryType.SESSION_LEDGER: [
        (r"this\s+sessions?\s+ledger", "this session ledger"),
        (r"(current|my)\s+sessions?\s+ledger", "current session ledger"),
        (r"sessions?\s+ledger", "session ledger"),
        (r"ledger\s+(for\s+)?(this|current|my)\s+session", "ledger for session"),
        (r"(read|show|view)\s+(me\s+)?(the\s+)?ledger\s+(for\s+)?(this|current|my)\s+session", "show session ledger"),
        (r"what\s+(queries|happened)\s+(in\s+)?(this|current|my)\s+session", "what happened session"),
        (r"(this|current|my)\s+session('?s?)?\s+(history|log|entries|ledger)", "session history"),
    ],
    QueryType.LEDGER: [
        (r"ledger", "ledger"),
        (r"audit\s*(log|trail)?", "audit"),
        (r"(show|list|view)\s+(the\s+)?log", "show log"),
        (r"recent\s+(events|entries|activity)", "recent events"),
        (r"what.*happened", "what happened"),
    ],
    QueryType.PROMPTS: [
        (r"prompts?\s*(used|usage|tracking)", "prompt usage"),
        (r"(show|list|view)\s+(governed\s+)?prompts?", "show prompts"),
        (r"llm\s*(calls?|usage|tracking)", "llm calls"),
        (r"(what|which)\s+prompts?\s+(were\s+)?(used|called)", "which prompts"),
        (r"prompt\s*(exchanges?|history)", "prompt exchanges"),
        (r"governed\s+prompt", "governed prompt"),
        (r"PRM-\w+-\d+", "prompt id reference"),
    ],
    QueryType.READ_FILE: [
        (r"(read|show|cat|view|display)\s+(file\s+)?[\w/]+\.(py|md|json|csv|yaml|txt)", "read file"),
        (r"(show|read)\s+me\s+[\w/]+\.(py|md|json|csv|yaml|txt)", "show me file"),
        (r"(what('s| is) in|contents? of)\s+[\w/]+\.(py|md|json|csv|yaml|txt)", "contents of"),
        (r"open\s+[\w/]+\.(py|md|json|csv|yaml|txt)", "open file"),
    ],
    QueryType.LIST_FRAMEWORKS: [
        (r"(list|show|what)\s+(all\s+)?frameworks", "list frameworks"),
        (r"frameworks\s*(list|\?)?$", "frameworks"),
    ],
    QueryType.LIST_SPECS: [
        (r"(list|show|what)\s+(all\s+)?specs", "list specs"),
        (r"specifications?\s*(list|\?)?$", "specs"),
    ],
    QueryType.LIST_FILES: [
        (r"(list|show)\s+(files\s+)?(in\s+)?[\w/]+/?", "list files in"),
        (r"(what('s| is) in|contents? of)\s+(the\s+)?[\w/]+\s*(directory|folder|dir)", "dir contents"),
        (r"ls\s+[\w/]+", "ls"),
        (r"browse\s+[\w/]+", "browse"),
    ],
}


def _extract_artifact_id(query: str, pattern: str) -> Optional[str]:
    """Extract artifact ID from query.

    Args:
        query: User query
        pattern: Matched pattern

    Returns:
        Extracted artifact ID or None
    """
    # Look for artifact IDs in the query
    artifact_patterns = [
        r"(FMWK-[\w-]+)",
        r"(SPEC-[\w-]+)",
        r"(PKG-[\w-]+)",
        r"([\w/]+\.py)",
        r"([\w/]+\.md)",
    ]

    for p in artifact_patterns:
        match = re.search(p, query, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def _extract_file_path(query: str) -> Optional[str]:
    """Extract file path from query.

    Args:
        query: User query

    Returns:
        Extracted file path or None
    """
    patterns = [
        r"([\w/.-]+\.(?:py|md|json|csv|yaml|yml|txt|jsonl))",
        r"(lib/[\w/.-]+)",
        r"(scripts/[\w/.-]+)",
        r"(modules/[\w/.-]+)",
    ]

    for p in patterns:
        match = re.search(p, query, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def _extract_dir_path(query: str) -> Optional[str]:
    """Extract directory path from query.

    Args:
        query: User query

    Returns:
        Extracted directory path or None
    """
    patterns = [
        r"(?:in|browse|ls|list files in)\s+([\w/.-]+)",
        r"(lib|scripts|modules|config|registries|frameworks|ledger|specs|schemas|tests|governed_prompts)/?",
    ]

    for p in patterns:
        match = re.search(p, query, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def classify_query(query: str) -> QueryClassification:
    """Classify a query using pattern matching.

    This is the tools-first classification. It uses deterministic
    pattern matching and never calls an LLM.

    Args:
        query: User query string

    Returns:
        QueryClassification with type and confidence
    """
    if not query:
        return QueryClassification(
            type=QueryType.GENERAL,
            confidence=0.0,
            pattern_matched=False,
        )

    query_lower = query.lower().strip()

    # Try each query type's patterns
    for query_type, patterns in PATTERNS.items():
        for pattern, pattern_name in patterns:
            if re.search(pattern, query_lower, re.IGNORECASE):
                # Extract any relevant arguments
                extracted_args = {}
                if query_type == QueryType.EXPLAIN:
                    artifact_id = _extract_artifact_id(query, pattern)
                    if artifact_id:
                        extracted_args["artifact_id"] = artifact_id
                elif query_type == QueryType.READ_FILE:
                    file_path = _extract_file_path(query)
                    if file_path:
                        extracted_args["file_path"] = file_path
                elif query_type == QueryType.LIST_FILES:
                    dir_path = _extract_dir_path(query)
                    if dir_path:
                        extracted_args["dir_path"] = dir_path

                return QueryClassification(
                    type=query_type,
                    confidence=1.0,
                    pattern_matched=True,
                    matched_pattern=pattern_name,
                    extracted_args=extracted_args,
                )

    # No pattern matched - return general with low confidence
    return QueryClassification(
        type=QueryType.GENERAL,
        confidence=0.5,
        pattern_matched=False,
    )


def needs_llm_classification(classification: QueryClassification) -> bool:
    """Check if query needs LLM classification.

    Args:
        classification: Result from classify_query

    Returns:
        True if LLM classification might help
    """
    # If pattern matched with high confidence, no LLM needed
    if classification.pattern_matched and classification.confidence >= 0.9:
        return False

    # General queries might benefit from LLM classification
    if classification.type == QueryType.GENERAL:
        return True

    # Low confidence queries might benefit
    if classification.confidence < 0.7:
        return True

    return False
