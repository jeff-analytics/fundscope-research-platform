@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_LAUNCHER="
where py.exe >nul 2>nul
if not errorlevel 1 set "PYTHON_LAUNCHER=py -3"
if not defined PYTHON_LAUNCHER (
  where python.exe >nul 2>nul
  if not errorlevel 1 set "PYTHON_LAUNCHER=python"
)

if not defined PYTHON_LAUNCHER (
  echo Python was not found.
  echo.
  pause
  exit /b 1
)

%PYTHON_LAUNCHER% "%~dp0scripts\diagnose_windows.py"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
pause
exit /b %EXIT_CODE%
