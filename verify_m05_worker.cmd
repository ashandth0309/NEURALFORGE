@echo off
setlocal
cd /d "%~dp0"
python -m py_compile tools\m05_isolated_worker.py services\validator\tests\test_m05_isolated_worker.py
if errorlevel 1 exit /b 1
python -m unittest services.validator.tests.test_m05_isolated_worker -v
if errorlevel 1 exit /b 1
python -m unittest discover -s services/validator/tests -q
if errorlevel 1 exit /b 1
git diff --check
if errorlevel 1 exit /b 1
git status --short --untracked-files=all
endlocal
