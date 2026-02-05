"""Query Classification with Fuzzy Matching.

Pattern-based classification with improved path extraction and fuzzy matching
for natural language variations.

Example:
    from modules.chat_interface.classifier import classify_query, QueryType

    result = classify_query("what is in the modules directory?")
    # Returns QueryClassification(type=BROWSE_DIR, dir_path="modules")
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class QueryType(str, Enum):
    """Types of queries."""

    # Browse operations
    BROWSE_DIR = "browse_dir"
    BROWSE_CODE = "browse_code"
    SEARCH_CODE = "search_code"

    # Package operations
    PACKAGE_LIST = "package_list"
    PACKAGE_INSPECT = "package_inspect"
    PACKAGE_PREFLIGHT = "package_preflight"
    PACKAGE_INSTALL = "package_install"
    PACKAGE_UNINSTALL = "package_uninstall"
    PACKAGE_STAGE = "package_stage"

    # Ledger operations
    LEDGER_QUERY = "ledger_query"
    PROMPTS_QUERY = "prompts_query"  # Show governed prompt usage

    # Help
    HELP = "help"

    # Fallback
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


# Known directory names in Control Plane
KNOWN_DIRS = {
    "modules", "lib", "scripts", "config", "registries",
    "frameworks", "ledger", "specs", "schemas", "tests",
    "governed_prompts", "packages_store", "installed",
    "planes", "handlers", "templates", "versions",
    "_staging", "_external_quarantine", "docs",
}

# Query patterns for each type
# Format: (regex_pattern, pattern_name)
# NOTE: Order in dict doesn't matter for dict iteration in Python 3.7+,
# but we explicitly check PACKAGE_LIST before BROWSE_DIR in classify_query()
PATTERNS: Dict[QueryType, List[Tuple[str, str]]] = {
    # Package patterns - these must be checked before BROWSE_DIR
    QueryType.PACKAGE_LIST: [
        (r"list\s+(?:all\s+)?packages", "list packages"),
        (r"(?:what|which)\s+packages\s+(?:are\s+)?installed", "packages installed"),
        (r"show\s+(?:installed\s+)?packages", "show packages"),
        (r"installed\s+packages", "installed packages"),
        (r"^packages$", "packages"),
    ],
    QueryType.BROWSE_DIR: [
        (r"what(?:'s| is) in (?:the )?(\w+)(?:\s+directory|\s+folder|\s+dir)?", "whats in dir"),
        (r"list\s+files\s+(?:in\s+)?(\w+)/?", "list files in"),  # Requires "files"
        (r"list\s+(?:in\s+)?(\w+)(?:\s+directory|\s+folder|\s+dir)", "list in dir"),  # Requires dir/folder
        (r"contents? of (?:the )?(\w+)", "contents of"),
        (r"browse (\w+)", "browse dir"),
        (r"^ls (\w+)", "ls dir"),
        (r"show (?:me )?(?:the )?(\w+)(?:\s+directory|\s+folder)$", "show dir"),
    ],
    QueryType.BROWSE_CODE: [
        (r"(?:read|show|cat|view|display)\s+(?:file\s+)?([\w/.+-]+\.(?:py|md|json|csv|yaml|yml|txt|jsonl))", "read file"),
        (r"(?:show|read)\s+me\s+([\w/.+-]+\.(?:py|md|json|csv|yaml|yml|txt|jsonl))", "show me file"),
        (r"(?:what'?s| is) in\s+([\w/.+-]+\.(?:py|md|json|csv|yaml|yml|txt|jsonl))", "whats in file"),
        (r"open\s+([\w/.+-]+\.(?:py|md|json|csv|yaml|yml|txt|jsonl))", "open file"),
    ],
    QueryType.SEARCH_CODE: [
        (r"search (?:for )?['\"]?(.+?)['\"]?(?:\s+in\s+\w+)?$", "search for"),
        (r"grep (?:for )?['\"]?(.+?)['\"]?", "grep for"),
        (r"find (?:all )?['\"]?(.+?)['\"]?\s+(?:in|across)", "find in"),
    ],
    QueryType.PACKAGE_INSPECT: [
        (r"inspect\s+(PKG-[\w-]+)", "inspect pkg"),
        (r"show\s+(PKG-[\w-]+)", "show pkg"),
        (r"describe\s+(PKG-[\w-]+)", "describe pkg"),
        (r"(?:what|tell me about)\s+(PKG-[\w-]+)", "about pkg"),
        (r"^(PKG-[\w-]+)$", "direct pkg id"),
    ],
    QueryType.PACKAGE_PREFLIGHT: [
        (r"preflight\s+(PKG-[\w-]+)", "preflight pkg"),
        (r"validate\s+(PKG-[\w-]+)", "validate pkg"),
        (r"check\s+(PKG-[\w-]+)", "check pkg"),
    ],
    QueryType.PACKAGE_INSTALL: [
        (r"install\s+(PKG-[\w-]+)", "install pkg"),
    ],
    QueryType.PACKAGE_UNINSTALL: [
        (r"uninstall\s+(PKG-[\w-]+)", "uninstall pkg"),
        (r"remove\s+(PKG-[\w-]+)", "remove pkg"),
    ],
    QueryType.PACKAGE_STAGE: [
        (r"stage\s+(PKG-[\w-]+)", "stage pkg"),
    ],
    QueryType.LEDGER_QUERY: [
        (r"(?:show|view|list)\s+(?:the\s+)?ledger", "show ledger"),
        (r"ledger\s+(?:entries|activity|events)", "ledger entries"),
        (r"recent\s+(?:ledger\s+)?(?:entries|activity|events)", "recent entries"),
        (r"what\s+happened", "what happened"),
        (r"audit\s*(?:log|trail)?", "audit"),
    ],
    QueryType.PROMPTS_QUERY: [
        (r"prompts?\s*(?:used|usage|tracking)", "prompt usage"),
        (r"(?:show|list|view)\s+(?:governed\s+)?prompts?", "show prompts"),
        (r"llm\s*(?:calls?|usage|tracking)", "llm calls"),
        (r"(?:what|which)\s+prompts?\s+(?:were\s+)?(?:used|called)", "which prompts"),
        (r"prompt\s*(?:exchanges?|history)", "prompt exchanges"),
        (r"governed\s+prompt", "governed prompt"),
        (r"PRM-\w+-\d+", "prompt id reference"),
    ],
    QueryType.HELP: [
        (r"^help$", "help"),
        (r"^commands$", "commands"),
        (r"what\s+can\s+(?:you|i)\s+do", "what can do"),
        (r"(?:show|list)\s+(?:available\s+)?commands", "show commands"),
        (r"^usage$", "usage"),
        (r"^\\?$", "question mark"),
    ],
}


def extract_dir_path(query: str) -> Optional[str]:
    """Extract directory path from query.

    Uses multiple strategies:
    1. Pattern matching for explicit directory references
    2. Known directory name detection
    3. Path-like string extraction

    Args:
        query: User query string

    Returns:
        Extracted directory path or None
    """
    query_lower = query.lower().strip()

    # Strategy 1: Pattern matching
    patterns = [
        r"what(?:'s| is) in (?:the )?(\w+)",
        r"list (?:files )?(?:in )?(\w+)",
        r"contents? of (?:the )?(\w+)",
        r"browse (\w+)",
        r"^ls (\w+)",
        r"show (?:me )?(?:the )?(\w+)\s*(?:directory|folder)?$",
    ]

    for pattern in patterns:
        match = re.search(pattern, query_lower)
        if match:
            candidate = match.group(1)
            # Verify it's a known directory or a path-like string
            if candidate in KNOWN_DIRS or "/" in candidate:
                return candidate
            # Check if any known dir is in the candidate
            if candidate in {"the", "a", "all", "some"}:
                continue
            return candidate

    # Strategy 2: Find known directory names in query
    for dir_name in KNOWN_DIRS:
        if dir_name in query_lower:
            # Make sure it's a word boundary match
            if re.search(rf"\b{dir_name}\b", query_lower):
                return dir_name

    # Strategy 3: Path-like string
    path_match = re.search(r"([\w/.-]+/[\w/.-]*)", query)
    if path_match:
        return path_match.group(1).rstrip("/")

    return None


def extract_file_path(query: str) -> Optional[str]:
    """Extract file path from query.

    Args:
        query: User query string

    Returns:
        Extracted file path or None
    """
    # Look for file paths with extensions
    patterns = [
        r"([\w/.-]+\.(?:py|md|json|csv|yaml|yml|txt|jsonl))",
        r"(lib/[\w/.-]+)",
        r"(scripts/[\w/.-]+)",
        r"(modules/[\w/.-]+)",
        r"(config/[\w/.-]+)",
        r"(registries/[\w/.-]+)",
        r"(frameworks/[\w/.-]+)",
        r"(ledger/[\w/.-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def extract_package_id(query: str) -> Optional[str]:
    """Extract package ID from query.

    Args:
        query: User query string

    Returns:
        Package ID (PKG-...) or None
    """
    match = re.search(r"(PKG-[\w-]+)", query, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def extract_search_pattern(query: str) -> Optional[str]:
    """Extract search pattern from query.

    Args:
        query: User query string

    Returns:
        Search pattern or None
    """
    # Remove common prefix words
    query = re.sub(r"^(?:search|grep|find)\s+(?:for\s+)?", "", query.lower())
    # Remove quotes
    query = query.strip("'\"")
    # Remove trailing context
    query = re.sub(r"\s+(?:in|across|within)\s+.*$", "", query)
    return query if query else None


def fuzzy_match(query: str, patterns: List[str], threshold: float = 0.6) -> Optional[str]:
    """Find best matching pattern above threshold.

    Args:
        query: Query string
        patterns: List of pattern strings to match against
        threshold: Minimum similarity score (0.0 to 1.0)

    Returns:
        Best matching pattern or None
    """
    best_match = None
    best_score = 0.0

    for pattern in patterns:
        score = SequenceMatcher(None, query.lower(), pattern.lower()).ratio()
        if score > best_score and score >= threshold:
            best_score = score
            best_match = pattern

    return best_match


# Priority order for pattern checking
# Package operations come first to avoid "list packages" matching browse_dir
PATTERN_CHECK_ORDER = [
    QueryType.HELP,
    QueryType.PACKAGE_LIST,
    QueryType.PACKAGE_INSPECT,
    QueryType.PACKAGE_PREFLIGHT,
    QueryType.PACKAGE_INSTALL,
    QueryType.PACKAGE_UNINSTALL,
    QueryType.PACKAGE_STAGE,
    QueryType.PROMPTS_QUERY,  # Check before ledger_query
    QueryType.LEDGER_QUERY,
    QueryType.BROWSE_CODE,
    QueryType.BROWSE_DIR,
    QueryType.SEARCH_CODE,
]


def classify_query(query: str) -> QueryClassification:
    """Classify a query using pattern matching with fuzzy fallback.

    Args:
        query: User query string

    Returns:
        QueryClassification with type and extracted arguments
    """
    if not query:
        return QueryClassification(
            type=QueryType.GENERAL,
            confidence=0.0,
            pattern_matched=False,
        )

    query_stripped = query.strip()

    # Try pattern matching in priority order
    for query_type in PATTERN_CHECK_ORDER:
        patterns = PATTERNS.get(query_type, [])
        for pattern, pattern_name in patterns:
            match = re.search(pattern, query_stripped, re.IGNORECASE)
            if match:
                # Build extracted args based on query type
                extracted_args = _extract_args(query_type, query_stripped, match)

                return QueryClassification(
                    type=query_type,
                    confidence=1.0,
                    pattern_matched=True,
                    matched_pattern=pattern_name,
                    extracted_args=extracted_args,
                )

    # No pattern matched - return general
    return QueryClassification(
        type=QueryType.GENERAL,
        confidence=0.5,
        pattern_matched=False,
    )


def _extract_args(
    query_type: QueryType,
    query: str,
    match: re.Match,
) -> Dict[str, Any]:
    """Extract arguments based on query type.

    Args:
        query_type: The classified query type
        query: Original query string
        match: Regex match object

    Returns:
        Dictionary of extracted arguments
    """
    args: Dict[str, Any] = {}

    if query_type == QueryType.BROWSE_DIR:
        dir_path = extract_dir_path(query)
        if dir_path:
            args["dir_path"] = dir_path

    elif query_type == QueryType.BROWSE_CODE:
        file_path = extract_file_path(query)
        if file_path:
            args["file_path"] = file_path

    elif query_type == QueryType.SEARCH_CODE:
        pattern = extract_search_pattern(query)
        if pattern:
            args["search_pattern"] = pattern

    elif query_type in (
        QueryType.PACKAGE_INSPECT,
        QueryType.PACKAGE_PREFLIGHT,
        QueryType.PACKAGE_INSTALL,
        QueryType.PACKAGE_UNINSTALL,
        QueryType.PACKAGE_STAGE,
    ):
        package_id = extract_package_id(query)
        if package_id:
            args["package_id"] = package_id

    return args


def get_handler_name(query_type: QueryType) -> str:
    """Map query type to handler name.

    Args:
        query_type: The query type

    Returns:
        Handler name string
    """
    mapping = {
        QueryType.BROWSE_DIR: "browse_dir",
        QueryType.BROWSE_CODE: "browse_code",
        QueryType.SEARCH_CODE: "search_code",
        QueryType.PACKAGE_LIST: "package_list",
        QueryType.PACKAGE_INSPECT: "package_inspect",
        QueryType.PACKAGE_PREFLIGHT: "package_preflight",
        QueryType.PACKAGE_INSTALL: "package_install",
        QueryType.PACKAGE_UNINSTALL: "package_uninstall",
        QueryType.PACKAGE_STAGE: "package_stage",
        QueryType.LEDGER_QUERY: "ledger_query",
        QueryType.PROMPTS_QUERY: "prompts_query",  # Show governed prompt usage
        QueryType.HELP: "help",
        QueryType.GENERAL: "help",  # Fallback to help
    }
    return mapping.get(query_type, "help")
