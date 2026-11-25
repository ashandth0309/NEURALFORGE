@echo off
setlocal
cd /d "%~dp0"
where powershell >nul 2>nul
if errorlevel 1 (
  echo PowerShell was not found.
  exit /b 1
)
python -m unittest discover -s services/validator/tests -q
if errorlevel 1 exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\audit_m05_windows_acl.ps1"
if errorlevel 1 exit /b 1
git diff --check
if errorlevel 1 exit /b 1
git status --short --untracked-files=all
endlocal
