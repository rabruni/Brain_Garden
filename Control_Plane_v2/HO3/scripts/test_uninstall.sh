#!/bin/bash
# test_uninstall.sh - Uninstall a package by re-packing to packages_store/
#
# Usage:
#   ./scripts/test_uninstall.sh <pkg_id>
#
# Arguments:
#   pkg_id - Package ID (matches installed/<pkg_id>/ subdirectory)
#
# Example:
#   ./scripts/test_uninstall.sh PKG-TEST-001

set -e

# Set passthrough auth for testing
export CONTROL_PLANE_AUTH_PROVIDER=passthrough
export CONTROL_PLANE_ALLOW_PASSTHROUGH=1

cd "$(dirname "$0")/.."

if [ $# -lt 1 ]; then
    echo "Usage: $0 <pkg_id>"
    echo ""
    echo "Arguments:"
    echo "  pkg_id - Package ID to uninstall"
    exit 1
fi

PKG_ID="$1"

echo "Uninstalling $PKG_ID..."
python3 scripts/package_uninstall.py --id "$PKG_ID"

echo ""
echo "Uninstalled: installed/$PKG_ID -> packages_store/$PKG_ID.tar.gz"
