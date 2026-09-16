#!/usr/bin/env bash
# elite-hud launcher for macOS/Linux (development and CrossOver/Whisky bottles).
#
#   ./run.sh
#   ./run.sh --headless --replay tests/fixtures/Journal.2026-03-14T200000.01.log --replay-live
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON:-python3}"

if [ ! -x ".venv/bin/python" ]; then
    echo "[elite-hud] Creating virtual environment..."
    "$PYTHON_BIN" -m venv .venv
    echo "[elite-hud] Installing PySide6 (one time)..."
    .venv/bin/python -m pip install --upgrade pip >/dev/null
    .venv/bin/python -m pip install -r requirements.txt
fi

# Qt enumerates its plugin directory with QDir, which skips files carrying the
# macOS "hidden" flag -- and some setups (archive tools, sync daemons, MDM
# policies) set that flag on everything pip installs, leaving Qt unable to find
# any platform plugin. Clearing it is harmless and only affects this venv.
if [ "$(uname -s)" = "Darwin" ] && [ -d ".venv/lib" ]; then
    chflags -R nohidden .venv 2>/dev/null || true
fi

export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
exec .venv/bin/python -m elite_hud "$@"
