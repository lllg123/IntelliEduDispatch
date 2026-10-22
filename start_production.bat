@echo off
echo --- Starting Teaching Resource Scheduler in HTTPS mode ---
cd /d "%~dp0"

set "PROJECT_PYTHON="
for %%P in (".venv\Scripts\python.exe" "venv313\Scripts\python.exe" "venv\Scripts\python.exe") do if not defined PROJECT_PYTHON if exist "%%~P" set "PROJECT_PYTHON=%%~P"
if not defined PROJECT_PYTHON (
    echo No project Python environment found. Create .venv or venv313 first.
    exit /b 1
)

set "CADDY_EXE="
if exist "%~dp0caddy.exe" set "CADDY_EXE=%~dp0caddy.exe"
if not defined CADDY_EXE (
    where caddy.exe >nul 2>&1
    if not errorlevel 1 set "CADDY_EXE=caddy.exe"
)
if not defined CADDY_EXE (
    echo Caddy executable not found. Install Caddy or place caddy.exe in this folder.
    echo For local HTTP testing, use start_development.bat.
    exit /b 1
)

set "SHERLOCK_ALLOWED_IP="
for /f "delims=" %%A in ('powershell -NoProfile -Command "$ips=Get-NetIPAddress -AddressFamily IPv4 -AddressState Preferred; foreach($ip in $ips){if($ip.IPAddress -notlike '127.*'){Write-Output $ip.IPAddress;break}}"') do set "SHERLOCK_ALLOWED_IP=%%A"
if defined SHERLOCK_ALLOWED_IP echo --- Network IP: %SHERLOCK_ALLOWED_IP% ---

"%CADDY_EXE%" validate --config Caddyfile
if errorlevel 1 exit /b 1


echo --- Running database migrations... ---
"%PROJECT_PYTHON%" manage.py migrate --noinput
if errorlevel 1 exit /b 1
echo --- Collecting static files... ---
"%PROJECT_PYTHON%" manage.py collectstatic --noinput
if errorlevel 1 exit /b 1


echo --- Starting Caddy in the background... ---
start /b "" "%CADDY_EXE%" run --config Caddyfile

echo.
echo =====================================================================
echo   Teaching Resource Scheduler is starting!
if defined SHERLOCK_ALLOWED_IP echo   LAN: https://%SHERLOCK_ALLOWED_IP%:8443
echo   Or on this machine at:         https://localhost:8443
echo =====================================================================
echo.
echo Waitress is running in the foreground. Press Ctrl+C to stop the server.
echo When you are done, run the 'stop_production.bat' script to shut down Caddy.


"%PROJECT_PYTHON%" run.py
