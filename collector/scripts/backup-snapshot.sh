#!/bin/sh
# idea#444 preHook: write a fresh consistent dump at $DATA_DIR/backup/usage.sqlite
# (VACUUM INTO via python3; never cp the live db). Exits non-zero on failure.
# Invoked by the Engine as: docker compose exec -T -- collector /app/scripts/backup-snapshot.sh
set -eu
DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
export PYTHONPATH="${DIR}${PYTHONPATH:+:$PYTHONPATH}"
export DATA_DIR="${DATA_DIR:-/data}"
exec python3 -m src.backup_hook snapshot
