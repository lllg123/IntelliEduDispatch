#!/bin/bash


set -e
cd "$(dirname "$0")"

echo "--- Starting Teaching Resource Scheduler in HTTPS mode ---"

PYTHON_BIN=""
for candidate in .venv/bin/python venv313/bin/python venv/bin/python; do
    if [ -x "$candidate" ]; then
        PYTHON_BIN="$candidate"
        break
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    echo "No project Python environment found. Create .venv or venv313 first."
    exit 1
fi


if ! command -v caddy >/dev/null 2>&1; then
    echo "Caddy executable not found. Install Caddy or use start_development.sh for local HTTP."
    exit 1
fi
IP_ADDRESS=$("$PYTHON_BIN" -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('192.0.2.1',80));print(s.getsockname()[0]);s.close()" 2>/dev/null || true)
if [ -n "$IP_ADDRESS" ]; then
    export SHERLOCK_ALLOWED_IP="$IP_ADDRESS"
    echo "--- Network IP: $IP_ADDRESS ---"
fi
caddy validate --config Caddyfile


echo "--- Running database migrations... ---"
"$PYTHON_BIN" manage.py migrate --noinput
echo "--- Collecting static files... ---"
"$PYTHON_BIN" manage.py collectstatic --noinput


cleanup() {
    echo -e "\n--- Shutting down Caddy server... ---"
    caddy stop
    exit
}
trap cleanup SIGINT SIGTERM

echo "--- Starting Caddy in the background... ---"
caddy start --config Caddyfile

echo "--- Starting Teaching Resource Scheduler application server (Waitress)... ---"
echo
if [ -x "$(command -v tput)" ]; then
    tput setaf 2
fi
echo "====================================================================="
echo "  Teaching Resource Scheduler is now running securely!"
if [ -n "$IP_ADDRESS" ]; then
    echo "  LAN: https://$IP_ADDRESS:8443"
fi
echo "  Or on this machine at:         https://localhost:8443"
echo "====================================================================="
if [ -x "$(command -v tput)" ]; then
    tput sgr0
fi
echo
echo "Waitress is running in the foreground. Press Ctrl+C to stop everything."


"$PYTHON_BIN" run.py
