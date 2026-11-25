@echo off
setlocal
cd /d "%~dp0"
python -m unittest discover -s services/validator/tests -q
if errorlevel 1 exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\plan_m05_service_isolation.ps1" -Json
if errorlevel 1 exit /b 1
git diff --check
if errorlevel 1 exit /b 1
git status --short --untracked-files=all
endlocal
