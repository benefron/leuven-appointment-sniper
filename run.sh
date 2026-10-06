#!/bin/zsh
# One polling pass; launchd calls this every 5 minutes.
cd "$(dirname "$0")" || exit 1
set -a; source ./.env; set +a
exec ./.venv/bin/python snipe.py
