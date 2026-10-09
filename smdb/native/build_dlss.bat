@echo off
setlocal
cd /d "%~dp0"
for /f "usebackq delims=" %%I in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "SMTV_VCVARS=%%I\VC\Auxiliary\Build\vcvars64.bat"
call "%SMTV_VCVARS%"
if errorlevel 1 exit /b 1
cl /nologo /EHsc /O2 /MT dlss_worker.cpp /link /OUT:dlss_worker.exe d3d12.lib dxgi.lib d3dcompiler.lib
if errorlevel 1 exit /b 1
cl /nologo /EHsc /O2 /MT /LD dlss_interop.cpp /link /OUT:dlss_interop.dll d3d11.lib dxgi.lib opengl32.lib
exit /b %errorlevel%
