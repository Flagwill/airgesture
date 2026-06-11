#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON=${PYTHON:-python3}

if [ -x "$ROOT_DIR/.mpenv/bin/python" ]; then
  PYTHON="$ROOT_DIR/.mpenv/bin/python"
elif [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  PYTHON="$ROOT_DIR/.venv/bin/python"
fi

exec "$PYTHON" "$ROOT_DIR/scripts/check_env.py"
