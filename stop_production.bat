@echo off
echo --- Stopping the background Caddy server... ---
if exist "%~dp0caddy.exe" (
    "%~dp0caddy.exe" stop
) else (
    caddy stop
)
echo --- Caddy server has been shut down. ---
pause
