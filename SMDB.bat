@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem SMDB launcher for cmd.exe
rem Activates the .venv and runs the app as a module (python -m src)

set "ROOT=%~dp0"
set "VENV_DIR=%ROOT%.venv"
set "ACTIVATE_BAT=%VENV_DIR%\Scripts\activate.bat"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "APP_MOD=src"

if not exist "%ACTIVATE_BAT%" (
  echo [SMDB] ERROR: Virtual environment not found at "%VENV_DIR%".
  echo [SMDB] Run setup.bat first to create it.
  exit /b 1
)

echo [SMDB] Activating virtual environment
call "%ACTIVATE_BAT%"

rem Prefer venv python explicitly to avoid PATH issues
if exist "%VENV_PY%" (
  set "PYEXE=%VENV_PY%"
) else (
  rem Fallback to python on PATH (should be venv after activation)
  set "PYEXE=python"
)

echo [SMDB] Running: %PYEXE% -m %APP_MOD% %*
"%PYEXE%" -m %APP_MOD% %*
set "CODE=%ERRORLEVEL%"

exit /b %CODE%