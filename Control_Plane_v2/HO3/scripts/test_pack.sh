#!/bin/bash
# test_pack.sh - Create a package archive
#
# Usage:
#   ./scripts/test_pack.sh <src> <output>
#
# Arguments:
#   src    - Source file or directory to pack
#   output - Output archive path (e.g., packages_store/PKG-FOO.tar.gz)
#
# Example:
#   ./scripts/test_pack.sh modules/hello_module packages_store/PKG-TEST-001.tar.gz

set -e

# Set passthrough auth for testing
export CONTROL_PLANE_AUTH_PROVIDER=passthrough
export CONTROL_PLANE_ALLOW_PASSTHROUGH=1

cd "$(dirname "$0")/.."

if [ $# -lt 2 ]; then
    echo "Usage: $0 <src> <output>"
    echo ""
    echo "Arguments:"
    echo "  src    - Source file or directory to pack"
    echo "  output - Output archive path"
    exit 1
fi

SRC="$1"
OUT="$2"

if [ ! -e "$SRC" ]; then
    echo "ERROR: Source not found: $SRC"
    exit 1
fi

echo "Packing $SRC -> $OUT..."
python3 scripts/package_pack.py \
    --src "$SRC" \
    --out "$OUT"

echo ""
echo "Package created: $OUT"
echo "SHA256: $(cat ${OUT}.sha256)"
