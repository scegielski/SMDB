#!/usr/bin/env bash

set -euo pipefail

PYTHON_BIN=${PYTHON_BIN:-python3}
VENV_DIR=${VENV_DIR:-.venv}
REQUIREMENTS_FILE=${REQUIREMENTS_FILE:-requirements.txt}
APT_PACKAGES=(
  libxkbcommon-x11-0
  libxcb-xinerama0
  libxcb-cursor0
  libxcb-keysyms1
  libxcb-icccm4
  libxcb-shape0
  libglu1-mesa
)

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Error: ${PYTHON_BIN} not found. Set PYTHON_BIN to your Python 3 interpreter." >&2
  exit 1
fi

if [[ "${OS:-}" == "Windows_NT" ]]; then
  VENV_PY="${VENV_DIR}/Scripts/python.exe"
  VENV_PIP="${VENV_DIR}/Scripts/pip.exe"
else
  VENV_PY="${VENV_DIR}/bin/python"
  VENV_PIP="${VENV_DIR}/bin/pip"
fi

echo "Using Python interpreter: ${PYTHON_BIN}"
echo "Virtual environment directory: ${VENV_DIR}"

if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
  echo "Error: requirements file not found at ${REQUIREMENTS_FILE}." >&2
  exit 1
fi

if [[ "${SKIP_APT:-0}" != "1" ]] && command -v apt-get >/dev/null 2>&1; then
  missing_pkgs=()
  for pkg in "${APT_PACKAGES[@]}"; do
    if ! dpkg -s "${pkg}" >/dev/null 2>&1; then
      missing_pkgs+=("${pkg}")
    fi
  done
  if (( ${#missing_pkgs[@]} > 0 )); then
    echo "Installing missing system packages: ${missing_pkgs[*]}"
    if [[ $EUID -ne 0 ]] && command -v sudo >/dev/null 2>&1; then
      sudo apt-get update
      sudo apt-get install -y "${missing_pkgs[@]}"
    else
      apt-get update
      apt-get install -y "${missing_pkgs[@]}"
    fi
  else
    echo "All required system packages already installed."
  fi
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "Creating virtual environment..."
  if ! "${PYTHON_BIN}" -m venv "${VENV_DIR}"; then
    echo "Error: failed to create virtual environment. Ensure the venv module is installed (e.g., python3-venv)." >&2
    exit 1
  fi
fi

if [[ ! -x "${VENV_PY}" ]]; then
  echo "Error: virtual environment Python not found at ${VENV_PY}." >&2
  exit 1
fi

if ! "${VENV_PY}" -m pip --version >/dev/null 2>&1; then
  echo "pip not found in virtual environment; attempting to bootstrap with ensurepip..."
  if ! "${VENV_PY}" -m ensurepip --upgrade >/dev/null 2>&1; then
    echo "Error: unable to bootstrap pip in the virtual environment. Install the ensurepip module or update your Python distribution." >&2
    exit 1
  fi
fi

"${VENV_PY}" -m pip install --upgrade pip
"${VENV_PY}" -m pip install -r "${REQUIREMENTS_FILE}"

echo "Dependencies installed successfully inside ${VENV_DIR}."

MAKE_EXE="$PWD/MakeExe.sh"

if [[ "${OS:-}" == "Windows_NT" ]]; then
  ACTIVATE_SCRIPT="${VENV_DIR}/Scripts/activate"
  ACTIVATE_HINT="To activate run: ${VENV_DIR}\\\\Scripts\\\\activate.bat (cmd) or ${VENV_DIR}\\\\Scripts\\\\Activate.ps1 (PowerShell)"
  MAKE_EXE="$PWD/MakeExe.bat"
else
  ACTIVATE_SCRIPT="${VENV_DIR}/bin/activate"
  ACTIVATE_HINT="To activate run: source ${VENV_DIR}/bin/activate"
fi

if [[ -f "${ACTIVATE_SCRIPT}" ]]; then
  if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    # shellcheck disable=SC1090
    source "${ACTIVATE_SCRIPT}"
    echo "Virtual environment activated."
  else
    echo "${ACTIVATE_HINT}"
  fi
else
  echo "Warning: activation script not found at ${ACTIVATE_SCRIPT}." >&2
fi

if [[ -f "${MAKE_EXE}" ]]; then
  echo
  read -r -p "Run $(basename "${MAKE_EXE}") now to build executables? [y/N]: " run_make
  case "${run_make}" in
    [yY][eE][sS]|[yY])
      if [[ "${MAKE_EXE}" == *.bat ]]; then
        cmd.exe /c "\"${MAKE_EXE}\""
      else
        bash "${MAKE_EXE}"
      fi
      ;;
    *)
      echo "Skipping executable build."
      ;;
  esac
fi
