@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if "%FUNDSCOPE_ROLE%"=="" set "FUNDSCOPE_ROLE=maintainer"

set "PYTHON_LAUNCHER="
where py.exe >nul 2>nul
if not errorlevel 1 set "PYTHON_LAUNCHER=py -3"

if not defined PYTHON_LAUNCHER (
  where python.exe >nul 2>nul
  if not errorlevel 1 set "PYTHON_LAUNCHER=python"
)

if not defined PYTHON_LAUNCHER (
  echo Python 3.11 or newer is required.
  echo Install Python and enable Add Python to PATH, then run this file again.
  echo.
  pause
  exit /b 1
)

%PYTHON_LAUNCHER% "%~dp0scripts\launch_windows.py"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo FundScope did not start. See the detailed message above.
  echo.
  pause
  exit /b %EXIT_CODE%
)

echo.
echo FundScope launcher completed.
echo Keep the API and Web windows open while using FundScope.
echo.
pause
exit /b 0
