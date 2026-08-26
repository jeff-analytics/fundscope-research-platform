@echo off
setlocal EnableExtensions
set "FUNDSCOPE_ROLE=analyst"
call "%~dp0START_WINDOWS.bat"
exit /b %ERRORLEVEL%
