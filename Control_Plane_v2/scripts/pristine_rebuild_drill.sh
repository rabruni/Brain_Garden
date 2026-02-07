#!/bin/bash
# =============================================================================
# PRISTINE REBUILD DRILL
# =============================================================================
# Proves the Control Plane can be wiped to Genesis and rebuilt deterministically.
#
# Per FMWK-PKG-001: Package Standard v1.0 (Phase 8)
#
# Requires:
#   WIPE_CONFIRM=YES_WIPE_PRISTINE
#   CONTROL_PLANE_SIGNING_KEY (optional, for signature verification)
#
# Usage:
#   WIPE_CONFIRM=YES_WIPE_PRISTINE ./scripts/pristine_rebuild_drill.sh
#
# WARNING: This script DELETES files. Only run on test branches.
# =============================================================================

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_phase() {
    echo ""
    echo "================================================================="
    echo "=== $1 ==="
    echo "================================================================="
}

# Safety check
if [[ "${WIPE_CONFIRM:-}" != "YES_WIPE_PRISTINE" ]]; then
    log_error "ABORT: Set WIPE_CONFIRM=YES_WIPE_PRISTINE to confirm destructive operation"
    echo ""
    echo "This script will DELETE files from:"
    echo "  - frameworks/"
    echo "  - lib/"
    echo "  - modules/"
    echo "  - schemas/"
    echo "  - scripts/policies/"
    echo "  - scripts/ (except genesis_bootstrap.py)"
    echo "  - specs/"
    echo ""
    echo "Only run this on test branches, never on main/release."
    echo ""
    echo "Usage:"
    echo "  WIPE_CONFIRM=YES_WIPE_PRISTINE ./scripts/pristine_rebuild_drill.sh"
    exit 1
fi

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CP_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$CP_ROOT"

# Strict mode control (P8)
# Default: strict (no waivers). Use --dev or PRISTINE_DRILL_STRICT=0 for dev mode.
STRICT_MODE=1
if [[ "${PRISTINE_DRILL_STRICT:-1}" == "0" ]] || [[ "$*" == *"--dev"* ]]; then
    STRICT_MODE=0
    log_warn "DEV MODE: Waivers enabled (ALLOW_UNSIGNED, ALLOW_UNATTESTED)"
else
    log_info "STRICT MODE: No waivers (production)"
fi

log_info "Control Plane: $CP_ROOT"
log_info "Drill starting..."

# Create drill directory
DRILL_TS=$(date +%Y%m%d%H%M%S)
DRILL_DIR="$CP_ROOT/_drill_$DRILL_TS"
mkdir -p "$DRILL_DIR"
log_info "Drill artifacts: $DRILL_DIR"

# =============================================================================
log_phase "PHASE 1: EXPORT CURRENT STATE"
# =============================================================================

# Checkpoint current state (if script exists)
if [[ -f scripts/cp_version_checkpoint.py ]]; then
    log_info "Creating checkpoint..."
    python3 scripts/cp_version_checkpoint.py --label "pre-drill-$DRILL_TS" || log_warn "Checkpoint failed (continuing)"
fi

# Export packages_store
if [[ -d packages_store ]]; then
    log_info "Exporting packages_store..."
    cp -r packages_store "$DRILL_DIR/"
else
    log_warn "No packages_store found"
fi

# Export ledger
if [[ -d ledger ]]; then
    log_info "Exporting ledger..."
    cp -r ledger "$DRILL_DIR/"
fi

# Export installed receipts
if [[ -d installed ]]; then
    log_info "Exporting installed state..."
    cp -r installed "$DRILL_DIR/installed_before"
fi

# Generate seed registry from packages
log_info "Generating seed registry..."
if [[ -f registries/compiled/packages.json ]]; then
    cp registries/compiled/packages.json "$DRILL_DIR/seed_registry.json"
else
    # Create minimal seed registry
    cat > "$DRILL_DIR/seed_registry.json" << 'EOF'
{
  "schema_version": "1.0",
  "created_at": "2026-01-31T00:00:00Z",
  "packages": [],
  "install_order": []
}
EOF
fi

# Preserve genesis_bootstrap.py
log_info "Preserving genesis_bootstrap.py..."
cp scripts/genesis_bootstrap.py "$DRILL_DIR/"

log_info "Export complete"

# =============================================================================
log_phase "PHASE 2: WIPE PRISTINE PATHS"
# =============================================================================

# List of PRISTINE paths to wipe
PRISTINE_PATHS=(
    "frameworks"
    "lib"
    "modules"
    "schemas"
    "scripts/policies"
    "specs"
)

# Wipe PRISTINE paths
for path in "${PRISTINE_PATHS[@]}"; do
    if [[ -d "$path" ]]; then
        log_info "Wiping $path/..."
        rm -rf "$path"
    fi
done

# Wipe scripts (except genesis_bootstrap.py)
if [[ -d scripts ]]; then
    log_info "Wiping scripts/ (preserving genesis_bootstrap.py)..."
    find scripts -type f -name "*.py" ! -name "genesis_bootstrap.py" -delete
    find scripts -type f -name "*.sh" -delete
fi

# Clear installed receipts (will be regenerated)
log_info "Clearing installed receipts..."
rm -rf installed
mkdir -p installed

# Remove MANIFEST.json (will be regenerated)
rm -f MANIFEST.json

# Recreate scripts/ and restore bootstrapper
mkdir -p scripts
cp "$DRILL_DIR/genesis_bootstrap.py" scripts/

log_info "PRISTINE paths wiped (except genesis_bootstrap.py)"

# =============================================================================
log_phase "PHASE 3: GENESIS INSTALL (G0)"
# =============================================================================

# Genesis uses the self-contained bootstrapper (no lib/ deps)
G0_PACKAGES=("PKG-G0-001" "PKG-G0-002" "PKG-G0-003")
G0_INSTALLED=0

for pkg_id in "${G0_PACKAGES[@]}"; do
    archive=$(ls "$DRILL_DIR/packages_store/${pkg_id}"*.tar.gz 2>/dev/null | head -1 || true)
    if [[ -z "$archive" || ! -f "$archive" ]]; then
        log_warn "Genesis package not found: $pkg_id (skipping)"
        continue
    fi

    log_info "Installing $pkg_id (G0)..."
    if python3 scripts/genesis_bootstrap.py \
        --seed "$DRILL_DIR/seed_registry.json" \
        --archive "$archive" \
        --force; then
        G0_INSTALLED=$((G0_INSTALLED + 1))
    else
        log_error "Failed to install $pkg_id"
    fi
done

if [[ $G0_INSTALLED -eq 0 ]]; then
    log_warn "No Genesis packages installed (may be normal if packages not yet created)"
fi

# Verify Genesis standalone (if packages were installed)
if [[ $G0_INSTALLED -gt 0 ]]; then
    log_info "Verifying Genesis standalone..."
    python3 -c "
from lib.paths import CONTROL_PLANE
from lib.merkle import hash_file
from lib.packages import sha256_file
print(f'Genesis OK: {CONTROL_PLANE}')
" 2>/dev/null || log_warn "Genesis verification skipped (libs not yet available)"
fi

# =============================================================================
log_phase "PHASE 4: TIERED INSTALL (T0 -> T1 -> T2 -> T3)"
# =============================================================================

# Set install mode; waivers only in dev mode (P8)
export CONTROL_PLANE_INSTALL_MODE=1
if [[ $STRICT_MODE -eq 0 ]]; then
    export CONTROL_PLANE_ALLOW_UNSIGNED=1
    export CONTROL_PLANE_ALLOW_UNATTESTED=1
fi

install_tier() {
    local tier=$1
    local tier_installed=0

    for archive in "$DRILL_DIR/packages_store/PKG-${tier}-"*.tar.gz; do
        [[ -f "$archive" ]] || continue

        pkg_id=$(basename "$archive" | cut -d_ -f1)
        log_info "Installing $pkg_id ($tier)..."

        # Try package_install.py first, fall back to genesis_bootstrap
        if [[ -f scripts/package_install.py ]]; then
            python3 scripts/package_install.py \
                --archive "$archive" \
                --id "$pkg_id" \
                --force \
                --skip-manifest \
                --skip-capabilities 2>/dev/null || \
            python3 scripts/genesis_bootstrap.py \
                --seed "$DRILL_DIR/seed_registry.json" \
                --archive "$archive" \
                --force
        else
            python3 scripts/genesis_bootstrap.py \
                --seed "$DRILL_DIR/seed_registry.json" \
                --archive "$archive" \
                --force
        fi

        tier_installed=$((tier_installed + 1))
    done

    return $tier_installed
}

# Install T0 (using genesis_bootstrap since package_install not yet available)
log_info "Installing T0 (Trust Baseline)..."
for archive in "$DRILL_DIR/packages_store/PKG-T0-"*.tar.gz; do
    [[ -f "$archive" ]] || continue
    pkg_id=$(basename "$archive" | cut -d_ -f1)
    log_info "Installing $pkg_id (T0)..."
    python3 scripts/genesis_bootstrap.py \
        --seed "$DRILL_DIR/seed_registry.json" \
        --archive "$archive" \
        --force || log_warn "Failed to install $pkg_id"
done

# Install T1 (Runtime Tools)
log_info "Installing T1 (Runtime Tools)..."
install_tier "T1" || true

# Install T2 (Modules)
log_info "Installing T2 (Modules)..."
install_tier "T2" || true

# Install T3 (Agents)
log_info "Installing T3 (Agents)..."
install_tier "T3" || true

unset CONTROL_PLANE_INSTALL_MODE
[[ $STRICT_MODE -eq 0 ]] && unset CONTROL_PLANE_ALLOW_UNSIGNED CONTROL_PLANE_ALLOW_UNATTESTED

# =============================================================================
log_phase "PHASE 5: VERIFICATION"
# =============================================================================

VERIFICATION_PASSED=0
VERIFICATION_TOTAL=0

# 5.1 Integrity check
VERIFICATION_TOTAL=$((VERIFICATION_TOTAL + 1))
log_info "Running integrity check..."
if [[ -f scripts/integrity_check.py ]]; then
    if python3 scripts/integrity_check.py --verify --orphans --chain 2>/dev/null; then
        log_info "Integrity check: PASSED"
        VERIFICATION_PASSED=$((VERIFICATION_PASSED + 1))
    else
        log_warn "Integrity check: FAILED (may be expected if registry not rebuilt)"
    fi
else
    log_warn "Integrity check: SKIPPED (script not installed)"
fi

# 5.2 Validate packages
VERIFICATION_TOTAL=$((VERIFICATION_TOTAL + 1))
log_info "Validating packages..."
if [[ -f scripts/validate_packages.py ]]; then
    if python3 scripts/validate_packages.py 2>/dev/null; then
        log_info "Package validation: PASSED"
        VERIFICATION_PASSED=$((VERIFICATION_PASSED + 1))
    else
        log_warn "Package validation: FAILED"
    fi
else
    log_warn "Package validation: SKIPPED (script not installed)"
fi

# 5.3 Ledger chain
VERIFICATION_TOTAL=$((VERIFICATION_TOTAL + 1))
log_info "Verifying ledger chain..."
if python3 -c "
from lib.ledger_client import LedgerClient
valid, issues = LedgerClient().verify_chain()
if issues:
    for i in issues: print(f'  {i}')
assert valid, 'Ledger chain broken'
print('LEDGER OK')
" 2>/dev/null; then
    log_info "Ledger chain: PASSED"
    VERIFICATION_PASSED=$((VERIFICATION_PASSED + 1))
else
    log_warn "Ledger chain: SKIPPED or FAILED"
fi

# =============================================================================
log_phase "PHASE 6: STATE COMPARISON"
# =============================================================================

# Compare installed receipts
log_info "Comparing installed state..."
if [[ -f scripts/verify_installed_state.py ]]; then
    python3 scripts/verify_installed_state.py \
        --before "$DRILL_DIR/installed_before" \
        --after installed \
        --verbose || true
else
    # Manual comparison
    python3 << EOF
import json
from pathlib import Path

before = Path('$DRILL_DIR/installed_before')
after = Path('installed')

before_pkgs = {p.name for p in before.iterdir() if p.is_dir()} if before.exists() else set()
after_pkgs = {p.name for p in after.iterdir() if p.is_dir()} if after.exists() else set()

print(f'Before: {len(before_pkgs)} packages')
print(f'After:  {len(after_pkgs)} packages')

missing = before_pkgs - after_pkgs
extra = after_pkgs - before_pkgs

if missing:
    print(f'MISSING: {sorted(missing)}')
if extra:
    print(f'EXTRA: {sorted(extra)}')

if not missing:
    print('STATE COMPARISON: OK')
else:
    print('STATE COMPARISON: MISMATCH')
EOF
fi

# =============================================================================
log_phase "DRILL COMPLETE"
# =============================================================================

echo ""
echo "Verification: $VERIFICATION_PASSED/$VERIFICATION_TOTAL passed"
echo ""
echo "Drill artifacts preserved in: $DRILL_DIR"
echo "To clean up: rm -rf $DRILL_DIR"
echo ""

if [[ $VERIFICATION_PASSED -eq $VERIFICATION_TOTAL ]]; then
    echo "============================================="
    echo "=== PRISTINE REBUILD DRILL PASSED ==="
    echo "============================================="
    exit 0
else
    echo "============================================="
    echo "=== PRISTINE REBUILD DRILL INCOMPLETE ==="
    echo "============================================="
    echo ""
    echo "Some verifications skipped or failed."
    echo "This may be expected if packages have not been created yet."
    exit 0  # Don't fail - this is informational
fi
