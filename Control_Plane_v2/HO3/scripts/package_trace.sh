#!/bin/bash
#
# Reconcile file hashes and rebuild kernel after modifications.
#
# This script ensures:
# 1. All file hashes in file_ownership.csv match actual files
# 2. All content_hash values in control_plane_registry.csv are current
# 3. Kernel is rebuilt and installed with parity to all tiers
# 4. All gates pass (G0B, G0K, G1-G6)
#
# Usage:
#   ./scripts/package_trace.sh           # Run full reconciliation
#   ./scripts/package_trace.sh --verify  # Just verify, no changes
#
set -e

cd "$(dirname "$0")/.."
CP_ROOT="$(pwd)"

# Handle arguments
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    echo "Usage: package_trace.sh [OPTIONS]"
    echo ""
    echo "Reconcile file hashes and rebuild kernel after modifications."
    echo ""
    echo "Options:"
    echo "  --verify    Just verify, no changes (runs gates + trace --verify)"
    echo "  --help, -h  Show this help message"
    echo ""
    echo "What it does:"
    echo "  1. Updates all file hashes in file_ownership.csv"
    echo "  2. Updates content_hash values in control_plane_registry.csv"
    echo "  3. Rebuilds and installs kernel to all tiers"
    echo "  4. Runs all gates (G0K, G0B, G1-G6)"
    echo "  5. Verifies with trace.py --verify"
    echo ""
    echo "Examples:"
    echo "  ./scripts/package_trace.sh           # Full reconciliation"
    echo "  ./scripts/package_trace.sh --verify  # Verify only"
    exit 0
fi

VERIFY_ONLY=false
if [[ "$1" == "--verify" ]]; then
    VERIFY_ONLY=true
fi

echo "========================================"
echo "Control Plane Hash Reconciliation"
echo "========================================"
echo ""

if $VERIFY_ONLY; then
    echo "Mode: VERIFY ONLY (no changes)"
    echo ""
    python3 scripts/gate_check.py --all
    echo ""
    python3 scripts/trace.py --verify
    exit $?
fi

# Step 1: Update all file hashes in registries
echo "Step 1: Reconciling file hashes..."
python3 << 'PYEOF'
import csv
from pathlib import Path
from kernel.merkle import hash_file
from datetime import datetime, timezone

# Update file_ownership.csv with current hashes
fo_path = Path("registries/file_ownership.csv")
with open(fo_path, "r") as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames
    rows = list(reader)

updated = 0
for row in rows:
    fpath = row.get("file_path", "")
    full_path = Path(fpath)
    if full_path.exists():
        current_hash = f"sha256:{hash_file(full_path)}"
        if row.get("sha256") != current_hash:
            row["sha256"] = current_hash
            row["installed_at"] = datetime.now(timezone.utc).isoformat()
            updated += 1

with open(fo_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)

print(f"  Updated {updated} hashes in file_ownership.csv")

# Update control_plane_registry.csv content_hash values
cp_path = Path("registries/control_plane_registry.csv")
with open(cp_path, "r") as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames
    rows = list(reader)

updated = 0
for row in rows:
    artifact_path = row.get("artifact_path", "").lstrip("/")
    if artifact_path:
        full_path = Path(artifact_path)
        if full_path.exists():
            current_hash = hash_file(full_path)
            if row.get("content_hash") != current_hash:
                row["content_hash"] = current_hash
                updated += 1

with open(cp_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)

print(f"  Updated {updated} content_hash values in control_plane_registry.csv")
PYEOF

echo ""

# Step 2: Rebuild kernel package
echo "Step 2: Rebuilding kernel package..."
python3 scripts/kernel_build.py
echo ""

# Step 3: Install kernel to all tiers
echo "Step 3: Installing kernel to all tiers..."
python3 scripts/kernel_install.py
echo ""

# Step 4: Final hash reconciliation (registries changed during updates)
echo "Step 4: Final hash reconciliation..."
python3 << 'PYEOF'
import csv
from pathlib import Path
from kernel.merkle import hash_file
from datetime import datetime, timezone

fo_path = Path("registries/file_ownership.csv")
cp_path = Path("registries/control_plane_registry.csv")

# Update control_plane_registry.csv hash first
with open(fo_path, "r") as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames
    rows = list(reader)

cp_hash = f"sha256:{hash_file(cp_path)}"
for row in rows:
    if row.get("file_path") == "registries/control_plane_registry.csv":
        row["sha256"] = cp_hash
        row["installed_at"] = datetime.now(timezone.utc).isoformat()

with open(fo_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)

# Self-update file_ownership.csv hash
with open(fo_path, "r") as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames
    rows = list(reader)

fo_hash = f"sha256:{hash_file(fo_path)}"
for row in rows:
    if row.get("file_path") == "registries/file_ownership.csv":
        row["sha256"] = fo_hash
        row["installed_at"] = datetime.now(timezone.utc).isoformat()

with open(fo_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)

print("  Registry hashes reconciled")
PYEOF

echo ""

# Step 5: Run all gates
echo "Step 5: Running all gates..."
echo ""
python3 scripts/gate_check.py --all

GATE_RESULT=$?
echo ""

# Step 6: Final verification with trace tool
echo "Step 6: Final verification with trace.py..."
python3 scripts/trace.py --verify

TRACE_RESULT=$?
echo ""

echo "========================================"
if [[ $GATE_RESULT -eq 0 && $TRACE_RESULT -eq 0 ]]; then
    echo "SUCCESS: All gates pass, system verified"
    exit 0
else
    echo "FAILED: Some checks did not pass"
    exit 1
fi
