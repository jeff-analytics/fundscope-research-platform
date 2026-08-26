@echo off
setlocal
cd /d "%~dp0"
echo [FundScope] Backend tests...
python -m pytest
if errorlevel 1 goto :fail

echo [FundScope] Frontend tests...
pushd frontend
call npm test
if errorlevel 1 (popd & goto :fail)
echo [FundScope] Frontend production build...
call npm run build
if errorlevel 1 (popd & goto :fail)
popd

echo.
echo All FundScope checks passed.
pause
exit /b 0

:fail
echo.
echo FundScope checks failed. Review the output above.
pause
exit /b 1
