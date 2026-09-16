#!/usr/bin/env bash
# Microscope Viewer Launcher
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Launch Python application
python3 "$DIR/main.py" "$@"
