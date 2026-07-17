@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 (
  py -3.11 -c "import sys" >nul 2>&1
  if not errorlevel 1 goto use_py
)

where python >nul 2>&1
if not errorlevel 1 (
  python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
  if not errorlevel 1 goto use_python
)

echo AutoClipper LauncherにはPython 3.11以降が必要です。
echo Python 3.11以降をインストールしてから、もう一度実行してください。
pause
exit /b 1

:use_py
py -3.11 -m launcher
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%

:use_python
python -m launcher
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
