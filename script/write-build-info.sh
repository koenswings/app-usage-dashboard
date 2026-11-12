#!/usr/bin/env bash
# write-build-info.sh — write collector/build-info.json for GET /api/v1/health.
#
# The collector image bakes packages only (idea#461); compose still
# bind-mounts ./collector at /app, so a COMMIT baked into the web or
# collector image never reaches /health. This file is the bundle-time
# equivalent: Engine copies the App tree into the instance, compose mounts
# ./collector at /app, and collector/src/buildinfo.py reads
# /app/build-info.json.
#
# Usage:
#   script/write-build-info.sh [--dest <dir>] [--commit <sha>] [--version <ver>]
#
# --dest defaults to the App repo root (this file's ../..). The JSON is written
# to <dest>/collector/build-info.json (gitignored in the checkout).
# --commit defaults to `git rev-parse HEAD` in --dest (or the repo root).
# --version defaults to compose.yaml x-app.version.
#
# Call this on the staged App Disk bundle AFTER `git ls-files` copy and BEFORE
# SHA256SUMS (see docs/packaging.md). `git ls-files` will not copy an
# untracked checkout copy, so writing only in the working tree is not enough.
set -euo pipefail

DEST=""
COMMIT=""
VERSION=""
die() { echo "ERROR: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dest) DEST="${2:-}"; shift 2 ;;
    --commit) COMMIT="${2:-}"; shift 2 ;;
    --version) VERSION="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
if [ -z "$DEST" ]; then
  DEST="$REPO"
fi
DEST=$(cd "$DEST" && pwd)
COMPOSE="$DEST/compose.yaml"
if [ ! -f "$COMPOSE" ]; then
  COMPOSE="$REPO/compose.yaml"
fi
[ -f "$COMPOSE" ] || die "compose.yaml not found in $DEST or $REPO"

if [ -z "$VERSION" ]; then
  VERSION=$(awk '/^x-app:/{x=1;next} x&&/^[^ #]/{x=0} x&&/^  version:/{
    v=$2; gsub(/"/,"",v); print v; exit
  }' "$COMPOSE")
fi
[ -n "$VERSION" ] || die "could not read x-app.version (pass --version)"

if [ -z "$COMMIT" ]; then
  if git -C "$DEST" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    COMMIT=$(git -C "$DEST" rev-parse HEAD)
  elif git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    COMMIT=$(git -C "$REPO" rev-parse HEAD)
  else
    die "could not determine commit (pass --commit)"
  fi
fi
[ -n "$COMMIT" ] || die "empty commit"

mkdir -p "$DEST/collector"
OUT="$DEST/collector/build-info.json"
python3 -c 'import json,sys; json.dump({"version": sys.argv[1], "commit": sys.argv[2]}, sys.stdout); sys.stdout.write("\n")' \
  "$VERSION" "$COMMIT" > "$OUT"
echo "ok: $OUT (version=$VERSION commit=$COMMIT)"
