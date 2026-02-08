#!/bin/bash
# test_install.sh - Install a package to installed/<pkg_id>/
#
# Usage:
#   ./scripts/test_install.sh <archive> <pkg_id> [dest_dir]
#
# Arguments:
#   archive   - Path to .tar.gz archive (relative to Control_Plane_v2/)
#   pkg_id    - Package ID (used for installed/<pkg_id>/ subdirectory)
#   dest_dir  - Optional destination base (default: installed/)
#
# Examples:
#   ./scripts/test_install.sh packages_store/PKG-TEST-001.tar.gz PKG-TEST-001
#   ./scripts/test_install.sh packages_store/foo.tar.gz PKG-FOO modules/

set -e

cd "$(dirname "$0")/.."

if [ $# -lt 2 ]; then
    echo "Usage: $0 <archive> <pkg_id> [dest_dir]"
    echo ""
    echo "Arguments:"
    echo "  archive   - Path to .tar.gz archive"
    echo "  pkg_id    - Package ID for subdirectory name"
    echo "  dest_dir  - Destination base directory (default: installed/)"
    exit 1
fi

ARCHIVE="$1"
PKG_ID="$2"
DEST_BASE="${3:-installed}"
DEST="$DEST_BASE/$PKG_ID"

if [ ! -f "$ARCHIVE" ]; then
    echo "ERROR: Archive not found: $ARCHIVE"
    exit 1
fi

if [ -d "$DEST" ]; then
    echo "ERROR: Target exists: $DEST (use test_uninstall.sh first)"
    exit 1
fi

echo "Installing $PKG_ID..."
echo "  Archive: $ARCHIVE"
echo "  Destination: $DEST"

# Create destination and extract
mkdir -p "$DEST"
tar -xzf "$ARCHIVE" -C "$DEST"

echo ""
echo "SUCCESS: Installed packages_store/ -> installed/"
echo ""
echo "Contents of $DEST:"
find "$DEST" -type f | while read f; do echo "  - $f"; done
