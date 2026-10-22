@echo off
echo --- Starting Teaching Resource Scheduler in DEVELOPMENT mode (HTTP) ---
cd /d "%~dp0"
echo --- Access at: http://127.0.0.1:8000
echo --- Press Ctrl+C to stop the server.

set "PROJECT_PYTHON="
for %%P in (".venv\Scripts\python.exe" "venv313\Scripts\python.exe" "venv\Scripts\python.exe") do if not defined PROJECT_PYTHON if exist "%%~P" set "PROJECT_PYTHON=%%~P"
if not defined PROJECT_PYTHON (
    echo No project Python environment found. Create .venv or venv313 first.
    exit /b 1
)

"%PROJECT_PYTHON%" manage.py migrate --noinput
if errorlevel 1 exit /b 1
"%PROJECT_PYTHON%" manage.py runserver
