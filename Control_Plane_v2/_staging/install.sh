#!/usr/bin/env bash
#
# install.sh — Control Plane v2 Bootstrap Installer
#
# Installs all packages from the packages/ directory in dependency order.
# Layer 0 (genesis + kernel) uses the genesis bootstrap path.
# All other packages are auto-discovered and topologically sorted.
#
# Usage:
#   ./install.sh --root <dir> [--dev] [--force]
#
# Arguments:
#   --root <dir>     Install target directory (required, created if absent)
#   --dev            Bypass auth/signature checks (for testing)
#   --force          Overwrite existing files (for re-install/recovery)
#
# Prerequisites:
#   - python3 (3.10+, stdlib only — no pip packages needed)
#
# Exit codes:
#   0  Success
#   1  Missing prerequisites or argument error
#   2  Package install failure
#   3  Gate check failure

set -euo pipefail

# ── Layer 0 (always first, special bootstrap path) ───────────────────
LAYER0_GENESIS="PKG-GENESIS-000"
LAYER0_KERNEL="PKG-KERNEL-001"

# ── Helpers ──────────────────────────────────────────────────────────
info()  { echo "==> $*"; }
step()  { echo ""; echo "── Step $1: $2 ──"; }
err()   { echo "ERROR: $*" >&2; }
die()   { err "$*"; exit 1; }

# ── Argument parsing ────────────────────────────────────────────────
ROOT=""
DEV_FLAG=""
FORCE_FLAG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --root)
            [[ $# -lt 2 ]] && die "--root requires a directory argument"
            ROOT="$2"
            shift 2
            ;;
        --dev)
            DEV_FLAG="--dev"
            shift
            ;;
        --force)
            FORCE_FLAG="--force"
            shift
            ;;
        -h|--help)
            echo "Usage: ./install.sh --root <dir> [--dev] [--force]"
            echo ""
            echo "  --root <dir>     Install target directory (required)"
            echo "  --dev            Bypass auth/signature checks"
            echo "  --force          Overwrite existing files (re-install)"
            echo ""
            echo "All packages in packages/ are auto-discovered and installed"
            echo "in dependency order. No hardcoded package lists."
            exit 0
            ;;
        *)
            die "Unknown argument: $1 (use --help for usage)"
            ;;
    esac
done

[[ -z "$ROOT" ]] && die "--root is required. Usage: ./install.sh --root <dir> [--dev] [--force]"

# ── Prerequisites ───────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    die "python3 is required but not found. Install Python 3.10+ and try again."
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "Using python3 $PYTHON_VERSION"

# ── Resolve paths ───────────────────────────────────────────────────
BOOTSTRAP_DIR="$(cd "$(dirname "$0")" && pwd)"
PACKAGES_DIR="$BOOTSTRAP_DIR/packages"

mkdir -p "$ROOT"
ROOT="$(cd "$ROOT" && pwd)"

export CONTROL_PLANE_ROOT="$ROOT"

info "Bootstrap dir: $BOOTSTRAP_DIR"
info "Install root:  $ROOT"
[[ -n "$DEV_FLAG" ]] && info "Dev mode:      ON"
[[ -n "$FORCE_FLAG" ]] && info "Force mode:    ON"

# ── Verify bootstrap structure ──────────────────────────────────────
[[ -d "$PACKAGES_DIR" ]] || die "Missing packages/ directory in $BOOTSTRAP_DIR"
[[ -f "$PACKAGES_DIR/$LAYER0_GENESIS.tar.gz" ]] || die "Missing $LAYER0_GENESIS.tar.gz"
[[ -f "$PACKAGES_DIR/$LAYER0_KERNEL.tar.gz" ]] || die "Missing $LAYER0_KERNEL.tar.gz"
[[ -f "$BOOTSTRAP_DIR/resolve_install_order.py" ]] || die "Missing resolve_install_order.py"

ARCHIVE_COUNT=$(ls "$PACKAGES_DIR"/*.tar.gz 2>/dev/null | wc -l | tr -d ' ')
info "$ARCHIVE_COUNT package archives found"

# ── Step 1: Extract genesis seed ────────────────────────────────────
step 1 "Extract $LAYER0_GENESIS (bootstrap seed)"

tar xzf "$PACKAGES_DIR/$LAYER0_GENESIS.tar.gz" -C "$ROOT"

[[ -f "$ROOT/HOT/scripts/genesis_bootstrap.py" ]] || die "genesis_bootstrap.py not found"
[[ -f "$ROOT/HOT/config/seed_registry.json" ]]    || die "seed_registry.json not found"

rm -f "$ROOT/manifest.json"

info "$LAYER0_GENESIS extracted"

# ── Step 2: Install kernel via genesis bootstrap ────────────────────
step 2 "Install $LAYER0_KERNEL (genesis bootstrap)"

GENESIS_ARGS=(
    --seed "$ROOT/HOT/config/seed_registry.json"
    --archive "$PACKAGES_DIR/$LAYER0_KERNEL.tar.gz"
    --id "$LAYER0_KERNEL"
    --genesis-archive "$PACKAGES_DIR/$LAYER0_GENESIS.tar.gz"
)
[[ -n "$FORCE_FLAG" ]] && GENESIS_ARGS+=(--force)

python3 "$ROOT/HOT/scripts/genesis_bootstrap.py" "${GENESIS_ARGS[@]}"

[[ -f "$ROOT/HOT/scripts/package_install.py" ]] || die "package_install.py not found"

info "$LAYER0_KERNEL installed: package_install.py available"

# ── Helper: install a package ───────────────────────────────────────
install_package() {
    local archive="$1"
    local pkg_id="$2"

    local args=(
        --archive "$archive"
        --id "$pkg_id"
        --root "$ROOT"
    )
    [[ -n "$DEV_FLAG" ]] && args+=("$DEV_FLAG")
    [[ -n "$FORCE_FLAG" ]] && args+=("$FORCE_FLAG")

    python3 "$ROOT/HOT/scripts/package_install.py" "${args[@]}"
}

# ── Step 3: Auto-discover and install all remaining packages ────────
step 3 "Resolve install order (auto-discovery)"

INSTALL_ORDER=$(python3 "$BOOTSTRAP_DIR/resolve_install_order.py" "$PACKAGES_DIR")
PKG_COUNT=$(echo "$INSTALL_ORDER" | wc -l | tr -d ' ')

info "Install order ($PKG_COUNT packages):"
echo "$INSTALL_ORDER" | while read -r pkg; do
    echo "    $pkg"
done

step 4 "Install packages in dependency order"

INSTALLED=0
while IFS= read -r pkg; do
    INSTALLED=$((INSTALLED + 1))
    info "[$INSTALLED/$PKG_COUNT] Installing $pkg..."
    install_package "$PACKAGES_DIR/$pkg.tar.gz" "$pkg"
done <<< "$INSTALL_ORDER"

info "All $INSTALLED packages installed"

# ── Gate checks ─────────────────────────────────────────────────────
step 5 "Running gate checks"

GATE_OUTPUT=$(python3 "$ROOT/HOT/scripts/gate_check.py" --root "$ROOT" --all 2>&1) || true
echo "$GATE_OUTPUT"

PASS_COUNT=$(echo "$GATE_OUTPUT" | grep -cE '^G[0-9A-Z-]+: PASS' || true)
FAIL_COUNT=$(echo "$GATE_OUTPUT" | grep -cE '^G[0-9A-Z-]+: FAIL' || true)

# ── Summary ─────────────────────────────────────────────────────────
TOTAL_INSTALLED=$((INSTALLED + 2))  # +2 for Layer 0 (genesis + kernel)
RECEIPT_COUNT=$(ls -d "$ROOT/HOT/installed"/PKG-*/receipt.json 2>/dev/null | wc -l | tr -d ' ')

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Control Plane v2 Bootstrap Complete"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "  Root:          $ROOT"
echo "  Packages:      $TOTAL_INSTALLED total ($RECEIPT_COUNT receipts)"
echo "  Gates:         $PASS_COUNT passed, $FAIL_COUNT failed"
echo ""

if [[ "$FAIL_COUNT" -gt 0 ]]; then
    echo "  WARNING: $FAIL_COUNT gate failure(s). Review output above."
    exit 3
fi

echo "  Install successful."
echo ""
