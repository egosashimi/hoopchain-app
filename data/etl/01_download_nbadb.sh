#!/bin/bash
# ============================================================
# HOOPCHAIN ETL — Step 1: Download nbadb from Kaggle
# ============================================================
# Prerequisites:
#   - KAGGLE_USERNAME and KAGGLE_KEY set in environment (or ~/.kaggle/kaggle.json)
#   - kaggle CLI installed: pip install kaggle
#
# Output: data/exports/basketball.sqlite
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPORT_DIR="$SCRIPT_DIR/../exports"
mkdir -p "$EXPORT_DIR"

echo "🏀 Downloading nbadb from Kaggle..."
echo "Dataset: wyattowalsh/basketball"
echo "Output: $EXPORT_DIR/basketball.sqlite"
echo ""

# Check for credentials
if [ -z "$KAGGLE_USERNAME" ] && [ ! -f "$HOME/.kaggle/kaggle.json" ]; then
    echo "ERROR: Kaggle credentials not found."
    echo "Set KAGGLE_USERNAME and KAGGLE_KEY environment variables, or"
    echo "place your kaggle.json at ~/.kaggle/kaggle.json"
    echo ""
    echo "Get credentials at: https://www.kaggle.com/settings/account"
    exit 1
fi

# Download dataset
echo "Downloading..."
cd "$EXPORT_DIR"
kaggle datasets download -d wyattowalsh/basketball --force

echo "Extracting..."
unzip -o basketball.zip -d .

# Find the sqlite file
SQLITE_FILE=$(find . -name "*.sqlite" | head -n 1)
if [ -z "$SQLITE_FILE" ]; then
    echo "ERROR: No .sqlite file found in the downloaded archive."
    echo "Contents of $EXPORT_DIR:"
    ls -la
    exit 1
fi

echo "✅ Downloaded: $SQLITE_FILE"
echo ""
echo "Next step: python 02_build_graph.py"
