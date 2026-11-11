#!/bin/sh
# One-join helper for a fresh single-use idea-hub auth key.
#
# The key must already be in the environment as TS_AUTHKEY. Never pass it as
# an argument, never echo it, never commit it.
#
# Commands:
#   write-env  --env-file INSTANCE.env   add/replace TS_AUTHKEY from the environment
#   remove-env --env-file INSTANCE.env   delete the TS_AUTHKEY line
#   verify     --state-dir DIR (--status-json FILE | --socket SOCK)
#   attempt    --env-file INSTANCE.env -- <command>
#              write-env, run <command> once, then always remove-env
#              (success or failure). Use this so the key does not stay in
#              the env file after a single join attempt.
#
# Prefer `attempt` over a bare write-env so TS_AUTHKEY is stripped even if
# the start fails. After BackendState is Running, run verify. Recreate or
# restart so the container env no longer holds the consumed key, then verify
# again so the on-disk nodekey still matches control.
set -eu

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
}

cmd=${1:-}
if [ -n "$cmd" ]; then
  shift
fi

ENV_FILE=""
STATE_DIR=""
STATUS_JSON=""
SOCKET=""
while [ $# -gt 0 ]; do
  case "$1" in
    --env-file) ENV_FILE=$2; shift 2 ;;
    --state-dir) STATE_DIR=$2; shift 2 ;;
    --status-json) STATUS_JSON=$2; shift 2 ;;
    --socket) SOCKET=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    *) break ;;
  esac
done

# Refuse a key passed on argv (remaining args are a command, not a key).
for arg in "$@"; do
  case "$arg" in
    tskey-*|TS_AUTHKEY=*)
      echo "join-idea-hub-once: refusing to accept a key on the command line" >&2
      exit 2
      ;;
  esac
done

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

write_env() {
  if [ -z "${ENV_FILE:-}" ]; then
    echo "join-idea-hub-once: --env-file is required" >&2
    exit 2
  fi
  if [ -z "${TS_AUTHKEY:-}" ]; then
    echo "join-idea-hub-once: TS_AUTHKEY is empty; export it in this shell first" >&2
    exit 2
  fi
  python3 - "$ENV_FILE" <<'PY'
import os, sys
from pathlib import Path
path = Path(sys.argv[1])
key = os.environ["TS_AUTHKEY"]
if not key:
    raise SystemExit("empty TS_AUTHKEY")
text = path.read_text() if path.exists() else ""
lines = text.splitlines()
out = [line for line in lines if not line.startswith("TS_AUTHKEY=")]
out.append("TS_AUTHKEY=" + key)
data = "\n".join(out) + "\n"
path.write_text(data)
os.chmod(path, 0o600)
print("wrote TS_AUTHKEY to env file (value not printed)")
PY
}

remove_env() {
  if [ -z "${ENV_FILE:-}" ]; then
    echo "join-idea-hub-once: --env-file is required" >&2
    exit 2
  fi
  python3 - "$ENV_FILE" <<'PY'
import os, sys
from pathlib import Path
path = Path(sys.argv[1])
if not path.exists():
    print("env file missing; nothing to remove")
    raise SystemExit(0)
lines = path.read_text().splitlines()
out = [line for line in lines if not line.startswith("TS_AUTHKEY=")]
path.write_text("\n".join(out) + ("\n" if out else ""))
print("removed TS_AUTHKEY from env file")
PY
}

verify() {
  if [ -z "${STATE_DIR:-}" ]; then
    echo "join-idea-hub-once: --state-dir is required" >&2
    exit 2
  fi
  if [ -n "${STATUS_JSON:-}" ]; then
    python3 "$ROOT/script/check-idea-hub-nodekey.py" --state-dir "$STATE_DIR" --status-json "$STATUS_JSON"
  elif [ -n "${SOCKET:-}" ]; then
    python3 "$ROOT/script/check-idea-hub-nodekey.py" --state-dir "$STATE_DIR" --socket "$SOCKET"
  else
    echo "join-idea-hub-once: provide --status-json or --socket" >&2
    exit 2
  fi
}

attempt() {
  if [ $# -eq 0 ]; then
    echo "join-idea-hub-once: attempt requires a command (after --)" >&2
    exit 2
  fi
  write_env
  trap remove_env EXIT INT TERM
  rc=0
  "$@" || rc=$?
  exit "$rc"
}

case "$cmd" in
  write-env) write_env ;;
  remove-env) remove_env ;;
  verify) verify ;;
  attempt) attempt "$@" ;;
  ""|-h|--help) usage ;;
  *) echo "unknown command: $cmd" >&2; usage >&2; exit 2 ;;
esac
