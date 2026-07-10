@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 goto use_py

where python >nul 2>&1
if not errorlevel 1 goto use_python

echo Python 3.11 or later is required for the Task57 launcher MVP.
echo Install Python, then run this file again.
pause
exit /b 1

:use_py
py -3 -m launcher
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%

:use_python
python -m launcher
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
