#!/bin/bash
# =============================================================================
# VERIFY INTEGRITY
# =============================================================================
# Single command to run all Control Plane integrity checks.
#
# Usage:
#   ./scripts/verify_integrity.sh          # Run all checks
#   ./scripts/verify_integrity.sh --quick  # Skip slow checks (orphans)
#   ./scripts/verify_integrity.sh --json   # JSON output
#
# =============================================================================

set -uo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CP_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$CP_ROOT"

# Parse args
QUICK_MODE=0
JSON_MODE=0
for arg in "$@"; do
    case $arg in
        --quick|-q) QUICK_MODE=1 ;;
        --json|-j) JSON_MODE=1 ;;
        --help|-h)
            echo "Usage: $0 [--quick] [--json]"
            echo ""
            echo "Options:"
            echo "  --quick, -q   Skip slow checks (orphan detection)"
            echo "  --json, -j    Output results as JSON"
            echo ""
            exit 0
            ;;
    esac
done

# Track results
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_SKIPPED=0
RESULTS=()

log_header() {
    [[ $JSON_MODE -eq 0 ]] && echo -e "\n${BLUE}=== $1 ===${NC}"
}

log_pass() {
    [[ $JSON_MODE -eq 0 ]] && echo -e "${GREEN}PASS${NC}: $1"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
    RESULTS+=("{\"check\": \"$1\", \"status\": \"PASS\"}")
}

log_fail() {
    [[ $JSON_MODE -eq 0 ]] && echo -e "${RED}FAIL${NC}: $1"
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    RESULTS+=("{\"check\": \"$1\", \"status\": \"FAIL\", \"detail\": \"$2\"}")
}

log_skip() {
    [[ $JSON_MODE -eq 0 ]] && echo -e "${YELLOW}SKIP${NC}: $1"
    CHECKS_SKIPPED=$((CHECKS_SKIPPED + 1))
    RESULTS+=("{\"check\": \"$1\", \"status\": \"SKIP\"}")
}

# =============================================================================
log_header "P1: Registry Hash Verification"
# =============================================================================
if [[ -f scripts/integrity_check.py ]]; then
    verify_output=$(python3 scripts/integrity_check.py --verify --quiet 2>&1)
    if echo "$verify_output" | grep -qE "OK|ISSUES"; then
        # Check if there are actual hash failures vs just info
        if echo "$verify_output" | grep -q "FAIL"; then
            log_fail "Registry hashes" "Hash mismatch detected"
        else
            log_pass "Registry hashes verified"
        fi
    else
        log_fail "Registry hashes" "Verification error"
    fi
else
    log_skip "Registry hashes (script not found)"
fi

# =============================================================================
log_header "P2: Orphan Detection"
# =============================================================================
if [[ $QUICK_MODE -eq 1 ]]; then
    log_skip "Orphan detection (--quick mode)"
elif [[ -f scripts/integrity_check.py ]]; then
    orphan_output=$(python3 scripts/integrity_check.py --orphans --quiet 2>&1)
    if echo "$orphan_output" | grep -qE "OK|ISSUES|Orphans: [0-9]+"; then
        log_pass "Orphan check completed"
    else
        log_fail "Orphan detection" "Check failed"
    fi
else
    log_skip "Orphan detection (script not found)"
fi

# =============================================================================
log_header "P3: Chain Links (artifact->spec->framework)"
# =============================================================================
if [[ -f scripts/integrity_check.py ]]; then
    chain_output=$(python3 scripts/integrity_check.py --chain --quiet 2>&1)
    if echo "$chain_output" | grep -qE "OK|Chain: 0 errors"; then
        log_pass "Chain links valid"
    else
        log_fail "Chain links" "Broken links detected"
    fi
else
    log_skip "Chain links (script not found)"
fi

# =============================================================================
log_header "P5: Ledger Chain Integrity"
# =============================================================================
if [[ -f scripts/ledger_repair.py ]]; then
    if python3 scripts/ledger_repair.py --verify-only 2>/dev/null | grep -q "VALID"; then
        log_pass "Ledger chain valid"
    else
        log_fail "Ledger chain" "Chain broken - run: python3 scripts/ledger_repair.py --verify-only"
    fi
else
    log_skip "Ledger chain (script not found)"
fi

# =============================================================================
log_header "P7: Package Determinism"
# =============================================================================
if python3 -c "
from lib.packages import pack
import tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as t:
    src = Path(t) / 'src'
    src.mkdir()
    (src / 'test.txt').write_text('test')
    h1 = pack(src, Path(t)/'a.tar.gz')
    h2 = pack(src, Path(t)/'b.tar.gz')
    assert h1 == h2, 'Not deterministic'
" 2>/dev/null; then
    log_pass "Package packing is deterministic"
else
    log_fail "Package determinism" "pack() produces different hashes"
fi

# =============================================================================
log_header "Package Validation"
# =============================================================================
if [[ -f scripts/validate_packages.py ]]; then
    pkg_output=$(python3 scripts/validate_packages.py 2>&1)
    if echo "$pkg_output" | grep -qE "^OK:|valid"; then
        log_pass "Package manifests valid"
    else
        log_fail "Package manifests" "Validation errors found"
    fi
else
    log_skip "Package validation (script not found)"
fi

# =============================================================================
# Summary
# =============================================================================
if [[ $JSON_MODE -eq 1 ]]; then
    echo "{"
    echo "  \"passed\": $CHECKS_PASSED,"
    echo "  \"failed\": $CHECKS_FAILED,"
    echo "  \"skipped\": $CHECKS_SKIPPED,"
    echo "  \"results\": ["
    for i in "${!RESULTS[@]}"; do
        if [[ $i -lt $((${#RESULTS[@]} - 1)) ]]; then
            echo "    ${RESULTS[$i]},"
        else
            echo "    ${RESULTS[$i]}"
        fi
    done
    echo "  ]"
    echo "}"
else
    echo ""
    echo "============================================="
    if [[ $CHECKS_FAILED -eq 0 ]]; then
        echo -e "${GREEN}INTEGRITY CHECK: ALL PASSED${NC}"
    else
        echo -e "${RED}INTEGRITY CHECK: FAILURES DETECTED${NC}"
    fi
    echo "============================================="
    echo "Passed:  $CHECKS_PASSED"
    echo "Failed:  $CHECKS_FAILED"
    echo "Skipped: $CHECKS_SKIPPED"
    echo ""
fi

[[ $CHECKS_FAILED -eq 0 ]] && exit 0 || exit 1
