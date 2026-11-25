@echo off
setlocal
cd /d "%~dp0"
python -m py_compile services\validator\service_boundary.py services\validator\service_framing.py services\validator\tests\test_service_boundary.py services\validator\tests\test_service_framing.py
if errorlevel 1 exit /b 1
python -m unittest services.validator.tests.test_service_boundary services.validator.tests.test_service_framing -v
if errorlevel 1 exit /b 1
python -m unittest discover -s services/validator/tests -q
if errorlevel 1 exit /b 1
git diff --check
if errorlevel 1 exit /b 1
git status --short --untracked-files=all
endlocal
