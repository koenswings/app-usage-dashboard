#!/usr/bin/env bash
# publish-web-image.sh — build, publish (only with --push) and export the arm64 web image.
#
# Published tags (only with --push):
#   ghcr.io/koenswings/usage-dashboard-web:<x-app.version>
#   ghcr.io/koenswings/usage-dashboard-web:<x-app.version>-<shortsha>
# Compose pins the :<version> tag by its digest (repo:tag@sha256:<index>).
# shortsha = `git rev-parse --short=12 HEAD`.
#
# Usage:
#   script/publish-web-image.sh                      # local test build only, tagged usage-dashboard-web:local-<shortsha>
#   script/publish-web-image.sh --push               # build and push, print digest + pin
#   script/publish-web-image.sh --push --export-tar <dir>
#                                                    # push, then export the tar of the new pin
#   script/publish-web-image.sh --export-tar <dir> [--pin <repo:tag@sha256:...>]
#                                                    # export only: the pin from --pin, else compose.yaml web
#
# --export-tar does exactly what the Engine's install path does (agent-engine-dev
# src/data/ImageRef.ts buildImageSteps): `docker image pull --platform linux/arm64
# <pin>`, `docker image tag <pin> <repo:tag>`, `docker save <repo:tag>` into
# <dir>/<serviceImageTarName>.partial, then script/verify-service-tar.sh on the
# .partial and only then an atomic `mv` to the real name. A local build is never
# saved. An existing tar is left alone if it already matches the pin; a stale one
# stops the export (quarantine it first, see docs/packaging.md "Pin-change runbook").
#
# Local test builds are tagged only usage-dashboard-web:local-<shortsha>: never a
# ghcr name and never a published tag, so they cannot shadow or be shipped as a
# release. Never pushes unless --push is given. Does not create git tags.
# DOCKER=<path> overrides the docker binary (tests use a stub).
set -euo pipefail

PUSH=0
EXPORT_DIR=""
PIN_ARG=""
DOCKER=${DOCKER:-docker}
die() { echo "ERROR: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --push) PUSH=1; shift ;;
    --export-tar) EXPORT_DIR="${2:-}"; [ -n "$EXPORT_DIR" ] || die "--export-tar needs a directory"; shift 2 ;;
    --pin) PIN_ARG="${2:-}"; [ -n "$PIN_ARG" ] || die "--pin needs a value"; shift 2 ;;
    -h|--help) sed -n '2,31p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done
[ "$PUSH" = 0 ] || [ -z "$PIN_ARG" ] || die "--pin is for export-only runs; --push makes its own pin"
[ -z "$PIN_ARG" ] || [ -n "$EXPORT_DIR" ] || die "--pin needs --export-tar"

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
VERIFY="$HERE/verify-service-tar.sh"
cd "$REPO"

VERSION=$(awk '/^x-app:/{x=1;next} x&&/^[^ #]/{x=0} x&&/^  version:/{
  v=$2; gsub(/"/,"",v); print v; exit
}' compose.yaml)
[ -n "$VERSION" ] || die "could not read x-app.version from compose.yaml"

REPO_NAME="ghcr.io/koenswings/usage-dashboard-web"
IMAGE="${REPO_NAME}:${VERSION}"
LOCAL_REPO="usage-dashboard-web"

command -v "$DOCKER" >/dev/null 2>&1 || die "docker is not on PATH"

# --- build ------------------------------------------------------------------

build_image() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not a git checkout"
  local commit short meta
  commit=$(git rev-parse HEAD)
  short=$(git rev-parse --short=12 HEAD)
  "$DOCKER" buildx version >/dev/null 2>&1 || die "docker buildx is required (not available on this host)"
  meta=$(mktemp)
  local args=(
    buildx build
    --platform linux/arm64
    --file web/Dockerfile
    --build-arg "COMMIT=$commit"
    --build-arg "PNPM_VERSION=9.15.9"
    --build-arg "USAGE_DASHBOARD_VERSION=$VERSION"
    --metadata-file "$meta"
  )
  echo "COMMIT: $commit"
  if [ "$PUSH" = 1 ]; then
    echo "image:  $IMAGE"
    echo "sha:    ${IMAGE}-${short}"
    echo "pushing $IMAGE and ${IMAGE}-${short} to ghcr.io (explicit --push)"
    args+=(--tag "$IMAGE" --tag "${IMAGE}-${short}" --push)
  else
    # Local test build: never a published tag (idea#445). --load works only on
    # an arm64 host; elsewhere the image stays in the buildx cache.
    echo "image:  ${LOCAL_REPO}:local-${short} (local test build; not a pin, never shipped as a tar)"
    args+=(--tag "${LOCAL_REPO}:local-${short}" --output "type=image,push=false")
  fi
  args+=(.)
  "$DOCKER" "${args[@]}"
  BUILT_DIGEST=$(python3 -c '
import json, sys
meta = json.load(open(sys.argv[1], encoding="utf-8"))
d = meta.get("containerimage.digest") or meta.get("containerimage.config.digest") or ""
if not d:
    sys.stderr.write("ERROR: buildx metadata did not include a digest\n"); sys.exit(1)
print(d)
' "$meta")
  rm -f "$meta"
}

# --- export -----------------------------------------------------------------

compose_web_pin() {
  awk '/^services:/{s=1;next} s&&/^[^ #]/{s=0} s&&/^  web:/{w=1;next} w&&/^  [A-Za-z0-9_-]+:/{w=0} w&&/^    image:/{print $2; exit}' compose.yaml | tr -d "\"'"
}

export_tar() {
  local pin="$1" dir="$2"
  case "$pin" in
    *@sha256:*) ;;
    *) die "export needs a digest pin (repo:tag@sha256:...), got: $pin" ;;
  esac
  local name tarname dest partial
  name=$(python3 "$HERE/verify_service_tar.py" --print-save-name "$pin")
  tarname=$(python3 "$HERE/verify_service_tar.py" --print-tar-name "$pin")
  [ -d "$dir" ] || die "export dir does not exist: $dir"
  dest="$dir/$tarname"
  partial="$dest.partial"
  echo "export: $pin -> $dest"
  if [ -e "$dest" ]; then
    if "$VERIFY" --tar "$dest" --image "$pin"; then
      echo "export: $dest already matches the pin; left as is"
      return 0
    fi
    die "$dest exists and does not match $pin. Quarantine it first (move, never delete), then re-run (docs/packaging.md, Pin-change runbook)"
  fi
  # Exactly the Engine's buildImageSteps: pull by full ref, tag repo:tag, plain save.
  "$DOCKER" image pull --platform linux/arm64 "$pin"
  "$DOCKER" image tag "$pin" "$name"
  "$DOCKER" save "$name" > "$partial"
  if ! "$VERIFY" --tar "$partial" --image "$pin"; then
    die "exported tar does not match $pin; left at $partial (not renamed)"
  fi
  mv -f "$partial" "$dest"
  echo "export: ok $dest"
  echo "sha256: $(sha256sum "$dest" | awk '{print $1}')"
}

# --- main -------------------------------------------------------------------

PIN=""
if [ "$PUSH" = 1 ]; then
  build_image
  PIN="${IMAGE}@${BUILT_DIGEST}"
  echo "digest: $BUILT_DIGEST"
  echo "pin:    $PIN"
elif [ -z "$EXPORT_DIR" ]; then
  build_image
  echo "local digest: $BUILT_DIGEST (local test build; not a pin)"
  exit 0
else
  PIN=${PIN_ARG:-$(compose_web_pin)}
  [ -n "$PIN" ] || die "could not read the web image from compose.yaml; pass --pin"
  echo "pin:    $PIN (export only; no build)"
fi

if [ -n "$EXPORT_DIR" ]; then
  export_tar "$PIN" "$EXPORT_DIR"
fi
