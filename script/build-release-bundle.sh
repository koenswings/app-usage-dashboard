#!/usr/bin/env bash
# build-release-bundle.sh — build the usage-dashboard App bundle WITH
# collector/build-info.json (idea#443).
#
# agent-app-dev's build-app-bundle.sh copies only `git ls-files` of --app-dir
# and has no per-app hook, so a build-info.json written into the checkout
# (gitignored) never reaches the bundle, and GET /api/v1/health reports no
# commit. This wrapper keeps build-app-bundle.sh unchanged:
#   1. clone the checkout's HEAD commit (and its tags) into a throwaway dir;
#   2. write collector/build-info.json there with script/write-build-info.sh:
#      {"version": <x-app.version>, "commit": <full HEAD sha>};
#   3. `git add -f` it in the throwaway clone's INDEX only (no commit, HEAD is
#      still the tag commit, so build-app-bundle.sh's tag==HEAD check holds and
#      its `git ls-files` copy includes the file);
#   4. run build-app-bundle.sh, which writes SHA256SUMS over the file;
#   5. check the bundle: build-info.json present, listed in SHA256SUMS, holds
#      the commit and version, `sha256sum -c` passes, and check-bundle-safe.py
#      finds no data/, .env or exclude/hookExclude path (copyBundle overwrites
#      every top-level bundle name in instances/<id>).
# The same commit always gives the same build-info.json bytes.
#
# Usage:
#   script/build-release-bundle.sh --build-app-bundle <agent-app-dev/script/build-app-bundle.sh> \
#       --disk-root <dir> --ref <release tag> [--app-dir <checkout>]
#
# --ref must equal compose.yaml x-app.version (e.g. 1.1) unless ALLOW_UNTAGGED=1
# (dev bundle 0.0-dev+<sha12>; build-info.json still carries x-app.version).
# Builds from the COMMITTED HEAD; uncommitted changes are not bundled.
# Env passed through to build-app-bundle.sh: DOCKER, ALLOW_UNTAGGED.
set -euo pipefail
die() { echo "ERROR: $*" >&2; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)
APP_DIR=$(cd "$HERE/.." && pwd)
BAB="" ROOT="" REF=""
while [ $# -gt 0 ]; do
  case "$1" in
    --build-app-bundle) BAB="${2:-}"; shift 2 ;;
    --disk-root) ROOT="${2:-}"; shift 2 ;;
    --ref) REF="${2:-}"; shift 2 ;;
    --app-dir) APP_DIR="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done
[ -n "$BAB" ] && [ -f "$BAB" ] || die "--build-app-bundle must point at agent-app-dev script/build-app-bundle.sh"
[ -n "$ROOT" ] && [ -d "$ROOT" ] || die "--disk-root must be an existing directory"
[ -n "$REF" ] || die "--ref required (the release tag, e.g. 1.1)"
git -C "$APP_DIR" rev-parse --git-dir >/dev/null 2>&1 || die "--app-dir is not a git checkout: $APP_DIR"
ROOT=$(cd "$ROOT" && pwd)
BAB=$(cd "$(dirname "$BAB")" && pwd)/$(basename "$BAB")

SHA=$(git -C "$APP_DIR" rev-parse HEAD)
if [ -n "$(git -C "$APP_DIR" status --porcelain --untracked-files=no)" ]; then
  echo "WARNING: $APP_DIR has uncommitted changes; they are NOT bundled (building $SHA)" >&2
fi

WORK=$(mktemp -d "${TMPDIR:-/tmp}/usage-dashboard-bundle.XXXXXX")
cleanup() { case "$WORK" in "${TMPDIR:-/tmp}"/usage-dashboard-bundle.*) rm -r -- "$WORK" ;; esac; }
trap cleanup EXIT
SRC="$WORK/src"
git init -q "$SRC"
git -C "$SRC" fetch -q --no-tags "$APP_DIR" HEAD
git -C "$SRC" fetch -q "$APP_DIR" 'refs/tags/*:refs/tags/*' 2>/dev/null || true
git -C "$SRC" -c advice.detachedHead=false checkout -q --detach FETCH_HEAD 2>/dev/null \
  || git -C "$SRC" -c advice.detachedHead=false checkout -q --detach "$SHA"
[ "$(git -C "$SRC" rev-parse HEAD)" = "$SHA" ] || die "throwaway clone is not at $SHA"

VERSION=$(awk '/^x-app:/{x=1;next} x&&/^[^ #]/{x=0} x&&/^  version:/{v=$2; gsub(/"/,"",v); print v; exit}' "$SRC/compose.yaml")
[ -n "$VERSION" ] || die "compose.yaml has no x-app.version"
if [ "${ALLOW_UNTAGGED:-}" != 1 ] && [ "$REF" != "$VERSION" ]; then
  die "--ref '$REF' does not equal compose.yaml x-app.version '$VERSION'"
fi

"$SRC/script/write-build-info.sh" --dest "$SRC" --commit "$SHA" --version "$VERSION" >/dev/null
git -C "$SRC" add -f collector/build-info.json
git -C "$SRC" ls-files --error-unmatch collector/build-info.json >/dev/null

OUT=$("$BAB" --app-dir "$SRC" --disk-root "$ROOT" --ref "$REF") || die "build-app-bundle.sh failed"
printf '%s\n' "$OUT"
BUNDLE_ABS=$(printf '%s\n' "$OUT" | sed -n 's/^ok: \(.*\) ([0-9]* files in SHA256SUMS)$/\1/p' | tail -1)
[ -n "$BUNDLE_ABS" ] && [ -d "$BUNDLE_ABS" ] || die "could not find the bundle build-app-bundle.sh wrote"
BUNDLE_REL=${BUNDLE_ABS#"$ROOT"/}
BI="$BUNDLE_REL/collector/build-info.json"

[ -f "$ROOT/$BI" ] || die "$BI missing from the bundle"
grep -qE "^[0-9a-f]{64}  $(printf '%s' "$BI" | sed 's/[.+]/\\&/g')\$" "$ROOT/$BUNDLE_REL/SHA256SUMS" || die "$BI is not listed in SHA256SUMS"
python3 - "$ROOT/$BI" "$SHA" "$VERSION" <<'PY' || die "build-info.json content check failed"
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d == {"version": sys.argv[3], "commit": sys.argv[2]}, d
PY
(cd "$ROOT" && sha256sum --quiet --strict -c "$BUNDLE_REL/SHA256SUMS") || die "SHA256SUMS check failed"
# copyBundle overwrites instances/<id> with every top-level bundle name: no data/,
# no .env, nothing in x-app.backup exclude/hookExclude; SHA256SUMS lists compose.yaml.
python3 "$HERE/check-bundle-safe.py" "$ROOT/$BUNDLE_REL" || die "bundle would clobber live instance state"
echo "build-info: $BI version=$VERSION commit=$SHA sha256=$(sha256sum "$ROOT/$BI" | cut -d' ' -f1)"
