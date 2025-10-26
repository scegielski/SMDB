#!/usr/bin/env bash
set -Eeuo pipefail

# PyInstaller build helper for POSIX shells (Linux/macOS)
# Mirrors the workflow of MakeExe.bat

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
ROOT="$SCRIPT_DIR"
VENV_PY="$ROOT/.venv/bin/python"
PYINSTALLER_CMD=()

cd "$ROOT"

run_build() {
  local spec="$1"
  local out="${2:-}"
  local exename="${3:-}"
  local -a dist_args=()

  if [[ -n "$out" && -z "$exename" ]]; then
    dist_args=(--distpath "$out")
  fi

  echo
  echo "Building with $spec ..."

  local -a cmd
  if [[ ${#PYINSTALLER_CMD[@]} -eq 0 ]]; then
    if [[ -x "$VENV_PY" ]]; then
      if "$VENV_PY" -m PyInstaller --version >/dev/null 2>&1; then
        PYINSTALLER_CMD=("$VENV_PY" -m PyInstaller)
      fi
    fi
    if [[ ${#PYINSTALLER_CMD[@]} -eq 0 ]]; then
      if command -v pyinstaller >/dev/null 2>&1; then
        PYINSTALLER_CMD=("pyinstaller")
      fi
    fi
  fi

  if [[ ${#PYINSTALLER_CMD[@]} -eq 0 ]]; then
    echo "PyInstaller not found. Install it in .venv or add to PATH."
    echo "  python -m pip install pyinstaller"
    return 1
  fi
  cmd=("${PYINSTALLER_CMD[@]}")

  if ! "${cmd[@]}" --noconfirm --clean "${dist_args[@]}" "$spec" >/dev/null 2>&1; then
    echo "Build failed for $spec."
    return 1
  fi

  echo "Build succeeded for $spec."

  if [[ -n "$exename" ]]; then
    rm -f "dist/${exename}.exe" "dist/${exename}"
  fi
}

choice=""
echo
echo "Select build type:"
echo "  [1] One file (single EXE)"
echo "  [2] One folder (onedir)"
echo "  [3] Both (default)"
if ! read -r -p "Enter 1, 2, or 3 [3]: " choice; then
  choice=""
fi
choice="${choice//[[:space:]]/}"
if [[ "$choice" != "1" && "$choice" != "2" && "$choice" != "3" ]]; then
  choice="3"
fi
if [[ -z "$choice" ]]; then
  choice="3"
fi

OUT_DIR=""

case "$choice" in
  "1")
    rm -rf "dist/SMDB-onefile"
    if ! run_build "smdb/SMDB-onefile.spec" "dist/SMDB-onefile"; then
      echo "One or more builds failed."
      exit 1
    fi
    OUT_DIR="dist/SMDB-onefile"
    ;;
  "2")
    rm -rf "dist/SMDB-onedir"
    rm -f "dist/SMDB.exe"
    if ! run_build "smdb/SMDB-onefolder.spec" "dist/SMDB-onedir" "SMDB"; then
      echo "One or more builds failed."
      exit 1
    fi
    OUT_DIR="dist/SMDB-onedir"
    ;;
  *)
    rm -rf "dist/SMDB-onefile"
    if ! run_build "smdb/SMDB-onefile.spec" "dist/SMDB-onefile"; then
      echo "One or more builds failed."
      exit 1
    fi
    rm -rf "dist/SMDB-onedir"
    rm -f "dist/SMDB.exe"
    if ! run_build "smdb/SMDB-onefolder.spec" "dist/SMDB-onedir" "SMDB"; then
      echo "One or more builds failed."
      exit 1
    fi
    OUT_DIR="dist"
    ;;
esac

echo
echo "Opening $OUT_DIR ..."
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$OUT_DIR" >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then
  open "$OUT_DIR" >/dev/null 2>&1 &
else
  echo "Unable to automatically open $OUT_DIR; please open it manually."
fi
