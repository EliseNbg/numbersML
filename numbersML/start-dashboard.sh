#!/bin/bash
# Start Dashboard - Wrapper Script
# This script ensures the .venv is used

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Activate virtual environment
if [ -d "$PROJECT_ROOT/.venv" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Add project root to PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Start dashboard
cd "$PROJECT_ROOT"
python3 -m src.cli.start_dashboard "$@"
