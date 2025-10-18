@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Windows cmd setup script
rem Creates a Python virtual environment in .venv and installs dependencies
rem from requirements.txt using pip.
rem
rem Usage:
rem   setup.bat
rem   setup.bat -VenvDir .customvenv -Requirements alt-requirements.txt -NoPipUpgrade

set "VENV_DIR=.venv"
set "REQUIREMENTS=requirements.txt"
set "NO_PIP_UPGRADE="

:parse
if "%~1"=="" goto after_parse
if /I "%~1"=="-VenvDir" (
  if "%~2"=="" (echo Missing value for -VenvDir & exit /b 2)
  set "VENV_DIR=%~2"
  shift
  shift
  goto parse
)
if /I "%~1"=="-Requirements" (
  if "%~2"=="" (echo Missing value for -Requirements & exit /b 2)
  set "REQUIREMENTS=%~2"
  shift
  shift
  goto parse
)
if /I "%~1"=="-NoPipUpgrade" (
  set "NO_PIP_UPGRADE=1"
  shift
  goto parse
)
if /I "%~1"=="-h" (
  echo Usage: setup.bat [-VenvDir path] [-Requirements file] [-NoPipUpgrade]
  exit /b 0
)
echo Unknown option: %~1
exit /b 2

:after_parse

echo [setup] Starting Windows (cmd) setup

rem Resolve Python launcher/executable
set "PYTHON="
where py >nul 2>&1 && set "PYTHON=py -3"
if not defined PYTHON (
  where python >nul 2>&1 && set "PYTHON=python"
)
if not defined PYTHON (
  echo [setup] ERROR: Python 3 not found. Install Python 3.x and ensure 'py' or 'python' is on PATH.
  exit /b 1
)

rem Create venv if missing
if not exist "%VENV_DIR%" (
  echo [setup] Creating virtual environment at "%VENV_DIR%"
  %PYTHON% -m venv "%VENV_DIR%"
) else (
  echo [setup] Virtual environment already exists at "%VENV_DIR%"
)

set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [setup] ERROR: Failed to locate venv Python at "%VENV_PY%".
  exit /b 1
)

rem Upgrade pip unless disabled
if not defined NO_PIP_UPGRADE (
  echo [setup] Upgrading pip
  "%VENV_PY%" -m pip install --upgrade pip
)

rem Install dependencies
if exist "%REQUIREMENTS%" (
  echo [setup] Installing dependencies from "%REQUIREMENTS%"
  "%VENV_PY%" -m pip install -r "%REQUIREMENTS%"
) else (
  echo [setup] WARNING: No "%REQUIREMENTS%" found; skipping dependency install.
)

echo.
echo [setup] Done. To activate the venv in cmd:
echo   call "%VENV_DIR%\Scripts\activate.bat"

exit /b 0

