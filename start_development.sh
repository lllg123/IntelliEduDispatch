#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "--- Starting Teaching Resource Scheduler in DEVELOPMENT mode (HTTP) ---"
echo "Access at: http://127.0.0.1:8000"
export DEBUG=True

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

"$PYTHON_BIN" manage.py migrate --noinput
"$PYTHON_BIN" manage.py runserver
