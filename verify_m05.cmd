@echo off
setlocal
cd /d "%~dp0"
python -m py_compile services\validator\service_auth.py services\validator\tests\test_service_auth.py services\validator\tests\test_service_adversarial.py
if errorlevel 1 exit /b 1
python -m unittest services.validator.tests.test_service_auth -v
if errorlevel 1 exit /b 1
python -m unittest services.validator.tests.test_service_adversarial -v
if errorlevel 1 exit /b 1
python -m unittest discover -s services/validator/tests -q
if errorlevel 1 exit /b 1
git diff --check
if errorlevel 1 exit /b 1
git status --short --untracked-files=all
endlocal
