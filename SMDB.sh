#!/usr/bin/env bash
set -Eeuo pipefail

# SMDB launcher for POSIX shells (Linux/macOS)
# Activates the .venv and runs the app as a module (python -m src)

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
ROOT="$SCRIPT_DIR"
VENV_DIR="$ROOT/.venv"
ACTIVATE_SH="$VENV_DIR/bin/activate"
VENV_PY="$VENV_DIR/bin/python"
APP_MOD="src"

if [[ ! -f "$ACTIVATE_SH" ]]; then
  echo "[SMDB] ERROR: Virtual environment not found at '$VENV_DIR'." >&2
  echo "[SMDB] Run setup.sh or setup.bat/setup.ps1 first to create it." >&2
  exit 1
fi

echo "[SMDB] Activating virtual environment"
# shellcheck source=/dev/null
source "$ACTIVATE_SH"

if [[ -x "$VENV_PY" ]]; then
  PYEXE="$VENV_PY"
else
  PYEXE="python"
fi

echo "[SMDB] Running: $PYEXE -m $APP_MOD $*"
exec "$PYEXE" -m "$APP_MOD" "$@"