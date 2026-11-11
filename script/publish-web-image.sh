#!/usr/bin/env bash
# publish-web-image.sh — build (and only with --push, publish) the arm64 web image.
#
# Tag convention follows app-kolibri-channel-builder
# (ghcr.io/koenswings/<image>:<version>) with a per-commit suffix:
#   ghcr.io/koenswings/usage-dashboard-web:<x-app.version>-<shortsha>
# shortsha is `git rev-parse --short=12 HEAD`.
#
# Usage:
#   script/publish-web-image.sh           # build linux/arm64, do not push, print digest
#   script/publish-web-image.sh --push    # build and push, then print digest
#
# Never pushes unless --push is given explicitly. Does not create git tags.
# Requires docker buildx. Passes --build-arg COMMIT=<full sha> so the image
# records /etc/idea-usage/build-info.json (the collector does not read this
# file; see script/write-build-info.sh).
set -euo pipefail

PUSH=0
die() { echo "ERROR: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --push) PUSH=1; shift ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
cd "$REPO"

VERSION=$(awk '/^x-app:/{x=1;next} x&&/^[^ #]/{x=0} x&&/^  version:/{
  v=$2; gsub(/"/,"",v); print v; exit
}' compose.yaml)
[ -n "$VERSION" ] || die "could not read x-app.version from compose.yaml"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not a git checkout"
COMMIT=$(git rev-parse HEAD)
SHORT=$(git rev-parse --short=12 HEAD)
IMAGE="ghcr.io/koenswings/usage-dashboard-web:${VERSION}-${SHORT}"

echo "image:  $IMAGE"
echo "COMMIT: $COMMIT"
echo "push:   $PUSH"

command -v docker >/dev/null 2>&1 || die "docker is not on PATH"
if ! docker buildx version >/dev/null 2>&1; then
  die "docker buildx is required (not available on this host)"
fi

META=$(mktemp)
trap 'rm -f "$META"' EXIT

BUILD_ARGS=(
  buildx build
  --platform linux/arm64
  --file web/Dockerfile
  --build-arg "COMMIT=$COMMIT"
  --build-arg "PNPM_VERSION=9.15.9"
  --build-arg "USAGE_DASHBOARD_VERSION=$VERSION"
  --tag "$IMAGE"
  --metadata-file "$META"
)
if [ "$PUSH" = 1 ]; then
  echo "pushing $IMAGE to ghcr.io (explicit --push)"
  BUILD_ARGS+=(--push)
else
  echo "building without --push (image stays local / in buildx cache)"
  # --load only works for the native platform; arm64 on a foreign host stays
  # in the buildx cache. Metadata still records the digest when the build works.
  BUILD_ARGS+=(--output "type=image,push=false")
fi
BUILD_ARGS+=(.)

docker "${BUILD_ARGS[@]}"

python3 -c '
import json, sys
meta = json.load(open(sys.argv[1], encoding="utf-8"))
image = sys.argv[2]
digest = meta.get("containerimage.digest") or meta.get("containerimage.config.digest") or ""
if not digest:
    sys.stderr.write("ERROR: buildx metadata did not include a digest\n")
    sys.exit(1)
print("digest: " + digest)
print("pin:    " + image + "@" + digest)
' "$META" "$IMAGE"
