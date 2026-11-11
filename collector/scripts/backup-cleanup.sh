#!/bin/sh
# idea#444 postHook: remove only $DATA_DIR/backup/usage.sqlite and this hook's
# temp files. A missing dump is not an error. Dated daily snapshots are kept.
# Invoked by the Engine as: docker compose exec -T -- collector /app/scripts/backup-cleanup.sh
set -eu
DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
export PYTHONPATH="${DIR}${PYTHONPATH:+:$PYTHONPATH}"
export DATA_DIR="${DATA_DIR:-/data}"
exec python3 -m src.backup_hook cleanup
