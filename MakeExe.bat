@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Change to the script's directory (repo root)
cd /d "%~dp0"

REM Prefer PyInstaller via local venv Python if present
set "VENV_PY=.\.venv\Scripts\python.exe"

echo.
echo Select build type:
echo   [1] One file (single EXE)
echo   [2] One folder (onedir)
echo   [3] Both (default)
set "CHOICE="
set /P CHOICE="Enter 1, 2, or 3 [3]: "
if not defined CHOICE set "CHOICE=3"
if "%CHOICE%" NEQ "1" if "%CHOICE%" NEQ "2" if "%CHOICE%" NEQ "3" set "CHOICE=3"

if "%CHOICE%"=="1" (
  call :run_build "src\SMDB-onefile.spec" "dist\SMDB-onefile"
  set "OUT_DIR=dist\SMDB-onefile"
  goto :open_out
)

if "%CHOICE%"=="2" (
  call :run_build "src\SMDB-onefolder.spec" "dist\SMDB-onedir" "SMDB"
  set "OUT_DIR=dist\SMDB-onedir"
  goto :open_out
)

REM Default: build both
call :run_build "src\SMDB-onefile.spec" "dist\SMDB-onefile" || goto :fail
call :run_build "src\SMDB-onefolder.spec" "dist\SMDB-onedir" "SMDB" || goto :fail
set "OUT_DIR=dist"
goto :open_out

:run_build
setlocal
set "SPEC=%~1"
set "OUT=%~2"
set "EXENAME=%~3"
set "DISTARG="
if defined OUT if not defined EXENAME set "DISTARG=--distpath"
echo.
echo Building with %SPEC% ...
if exist "%VENV_PY%" (
  if defined DISTARG (
    "%VENV_PY%" -m PyInstaller --noconfirm --clean %DISTARG% "%OUT%" "%SPEC%"
  ) else (
    "%VENV_PY%" -m PyInstaller --noconfirm --clean "%SPEC%"
  )
) else (
  where pyinstaller >nul 2>&1 || (
    echo PyInstaller not found. Install it in .venv or add to PATH.
    echo   python -m pip install pyinstaller
    endlocal & exit /b 1
  )
  if defined DISTARG (
    pyinstaller --noconfirm --clean %DISTARG% "%OUT%" "%SPEC%"
  ) else (
    pyinstaller --noconfirm --clean "%SPEC%"
  )
)
if errorlevel 1 (
  echo Build failed for %SPEC%.
  endlocal & exit /b 1
)
echo Build succeeded for %SPEC%.
REM Clean up duplicate top-level EXE left by onedir build
if defined EXENAME (
  if exist "dist\%EXENAME%.exe" del /q "dist\%EXENAME%.exe"
)
endlocal & exit /b 0

:open_out
echo.
echo Opening %OUT_DIR% ...
start "" explorer "%OUT_DIR%"
goto :eof

:fail
echo One or more builds failed.
endlocal
exit /b 1
