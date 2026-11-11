#!/usr/bin/env bash
# pin-web-digest.sh — fill compose.yaml with the published ghcr digest.
#
# After ghcr.io/koenswings/usage-dashboard-web:1.0 has been pushed:
#   script/pin-web-digest.sh
#   script/pin-web-digest.sh --image ghcr.io/koenswings/usage-dashboard-web:1.0
#   script/pin-web-digest.sh --check-only
#   script/pin-web-digest.sh --digest sha256:<64-hex> --compose compose.yaml
#
# Reads the digest with `docker buildx imagetools inspect`, falling back to
# `docker manifest inspect` / `docker manifest inspect --verbose`. Verifies
# that the image includes linux/arm64. Rewrites the web service to
#   image: ghcr.io/koenswings/usage-dashboard-web:<x-app.version>@sha256:<digest>
# and drops `build:` and `pull_policy: never` from that service.
#
# --digest skips the registry inspect (used by tests, or when the digest is
# already known). Does not push an image, change package visibility, or
# commit. Does not create git tags.
#
# Every run ends by printing the pin-change runbook (idea#445): each disk that
# already holds this App keeps the OLD tar under the same repo:tag file name, so
# it must be quarantined, re-exported, verified and re-tagged.
# --services-dir <dir> also runs script/verify-service-tar.sh on that dir for the
# new pin (read-only; it fails until the runbook has been done there).
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
IMAGE=""
COMPOSE="$REPO/compose.yaml"
DIGEST=""
CHECK_ONLY=0
SERVICES_DIR=""

die() { echo "ERROR: $*" >&2; exit 1; }

usage() { sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --image) IMAGE="${2:-}"; [ -n "$IMAGE" ] || die "--image needs a value"; shift 2 ;;
    --compose) COMPOSE="${2:-}"; [ -n "$COMPOSE" ] || die "--compose needs a value"; shift 2 ;;
    --digest) DIGEST="${2:-}"; [ -n "$DIGEST" ] || die "--digest needs a value"; shift 2 ;;
    --check-only) CHECK_ONLY=1; shift ;;
    --services-dir) SERVICES_DIR="${2:-}"; [ -n "$SERVICES_DIR" ] || die "--services-dir needs a value"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done

[ -f "$COMPOSE" ] || die "compose file not found: $COMPOSE"

VERSION=$(awk '/^x-app:/{x=1;next} x&&/^[^ #]/{x=0} x&&/^  version:/{
  v=$2; gsub(/"/,"",v); print v; exit
}' "$COMPOSE")
[ -n "$VERSION" ] || die "could not read x-app.version from $COMPOSE"

if [ -z "$IMAGE" ]; then
  IMAGE="ghcr.io/koenswings/usage-dashboard-web:${VERSION}"
fi

if [ -n "$DIGEST" ]; then
  case "$DIGEST" in
    sha256:[0-9a-f]*) ;;
    [0-9a-f]*) DIGEST="sha256:$DIGEST" ;;
    *) die "digest must be sha256:<64 hex>, got: $DIGEST" ;;
  esac
  HEX="${DIGEST#sha256:}"
  echo "$HEX" | grep -Eq '^[0-9a-f]{64}$' || die "digest must be sha256:<64 hex>, got: $DIGEST"
  echo "digest: $DIGEST (supplied; registry inspect skipped)"
  echo "note:   linux/arm64 was not verified because --digest was given"
else
  command -v docker >/dev/null 2>&1 || die "docker is not on PATH (needed to inspect $IMAGE)"
  INSPECT_OUT=$(mktemp)
  trap 'rm -f "$INSPECT_OUT"' EXIT
  METHOD=""
  if docker buildx imagetools inspect "$IMAGE" >"$INSPECT_OUT" 2>/dev/null; then
    METHOD="docker buildx imagetools inspect"
  elif docker manifest inspect "$IMAGE" >"$INSPECT_OUT" 2>/dev/null; then
    METHOD="docker manifest inspect"
  else
    die "could not inspect $IMAGE with buildx imagetools or docker manifest inspect"
  fi
  echo "inspect: $METHOD"

  EVAL=$(python3 - "$IMAGE" "$INSPECT_OUT" <<'PY'
import json, re, subprocess, sys

image, path = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
digest = None
platforms = []

def add_plat(os_name, arch, variant=None):
    if not os_name or not arch:
        return
    plat = f"{os_name}/{arch}"
    if variant:
        plat = f"{plat}/{variant}"
    if plat not in platforms:
        platforms.append(plat)

for line in text.splitlines():
    if line.startswith("Digest:") and digest is None:
        digest = line.split()[1].strip()
    m = re.match(r"\s*Platform:\s+(\S+)", line)
    if m:
        plat = m.group(1).strip()
        if plat not in platforms:
            platforms.append(plat)

if digest is None or not platforms:
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        data = json.loads(stripped)
        items = data if isinstance(data, list) else [data]
        for item in items:
            desc = item.get("Descriptor") if isinstance(item, dict) else None
            if isinstance(desc, dict):
                if digest is None:
                    digest = desc.get("digest")
                plat = desc.get("platform") or {}
                add_plat(plat.get("os"), plat.get("architecture"), plat.get("variant"))
            manifests = item.get("manifests") if isinstance(item, dict) else None
            if isinstance(manifests, list):
                for man in manifests:
                    plat = (man or {}).get("platform") or {}
                    add_plat(plat.get("os"), plat.get("architecture"), plat.get("variant"))

if digest is None:
    try:
        raw = subprocess.run(
            ["docker", "manifest", "inspect", "--verbose", image],
            check=False, capture_output=True, text=True,
        )
        if raw.returncode == 0 and raw.stdout.strip():
            data = json.loads(raw.stdout)
            items = data if isinstance(data, list) else [data]
            for item in items:
                desc = item.get("Descriptor") or {}
                if digest is None:
                    digest = desc.get("digest")
                plat = desc.get("platform") or {}
                add_plat(plat.get("os"), plat.get("architecture"), plat.get("variant"))
    except Exception:
        pass

if not digest:
    sys.stderr.write("ERROR: inspect output did not include a digest\n")
    sys.exit(1)
if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
    sys.stderr.write("ERROR: unexpected digest form: %s\n" % digest)
    sys.exit(1)

arm64 = any(p == "linux/arm64" or p.startswith("linux/arm64/") for p in platforms)
print(digest)
print("platforms:" + ",".join(platforms))
if not arm64:
    sys.stderr.write(
        "ERROR: inspected image does not list linux/arm64 (saw: %s)\n"
        % (", ".join(platforms) or "<none>")
    )
    sys.exit(1)
PY
)
  DIGEST=$(printf '%s\n' "$EVAL" | awk 'NR==1{print; exit}')
  PLATS=$(printf '%s\n' "$EVAL" | awk 'NR==2{print; exit}')
  echo "digest: $DIGEST"
  echo "$PLATS"
  echo "ok:     linux/arm64 present"
fi

PIN="ghcr.io/koenswings/usage-dashboard-web:${VERSION}@${DIGEST}"
echo "pin:    $PIN"

print_runbook() {
  local digest="${PIN##*@}" name tarname repo
  name=$(python3 "$HERE/verify_service_tar.py" --print-save-name "$PIN")
  tarname=$(python3 "$HERE/verify_service_tar.py" --print-tar-name "$PIN")
  repo="${name%:*}"
  cat <<EOF

Pin-change runbook (idea#445; docs/packaging.md). On every Pi or App Disk that
already has this App, inside a fleet claim, with <services> = /services on a
System Disk or <diskRoot>/services on an App Disk:
  1. Quarantine the old tar (move, never delete):
       mv <services>/$tarname /home/pi/kid-quarantine/<run>/
  2. Export a fresh tar of the pin (never a local build):
       script/publish-web-image.sh --export-tar <services> --pin $PIN
  3. Verify it:
       script/verify-service-tar.sh compose.yaml <services>
  4. Point the local tag at the pin:
       docker tag $repo@$digest $name
  5. Do one Engine-driven start (Console start or startInstance, not
     docker compose up), then check
       docker image inspect $name --format '{{.Id}}'   ==  $digest  (containerd image store)
EOF
}

if [ "$CHECK_ONLY" = 1 ]; then
  print_runbook
  exit 0
fi

python3 - "$COMPOSE" "$PIN" <<'PY'
import re, sys
from pathlib import Path

path = Path(sys.argv[1])
pin = sys.argv[2]
text = path.read_text(encoding="utf-8")
lines = text.split("\n")

in_services = False
web_start = None
web_end = None
for i, line in enumerate(lines):
    if line == "services:":
        in_services = True
        continue
    if in_services and line and not line.startswith("#") and line[0] not in " \t":
        in_services = False
    if in_services and re.match(r"^  web:\s*$", line):
        web_start = i
        continue
    if web_start is not None and web_end is None:
        if re.match(r"^  [A-Za-z0-9_-]+:\s*$", line):
            web_end = i
            break
if web_start is None:
    sys.stderr.write("ERROR: no web: service in %s\n" % path)
    sys.exit(1)
if web_end is None:
    web_end = len(lines)

block = lines[web_start:web_end]
new_block = [block[0]]
skipping_build = False
image_done = False
for line in block[1:]:
    if skipping_build:
        if re.match(r"^      ", line) or line.strip() == "":
            continue
        if re.match(r"^    \S", line):
            skipping_build = False
        else:
            continue
    if re.match(r"^    build:\s*$", line) or re.match(r"^    build:\s+\S", line):
        skipping_build = True
        continue
    if re.match(r"^    pull_policy:\s*never\s*$", line):
        continue
    if re.match(r"^    image:\s*", line):
        new_block.append("    image: " + pin)
        image_done = True
        continue
    new_block.append(line)
if not image_done:
    new_block.insert(1, "    image: " + pin)

out = lines[:web_start] + new_block + lines[web_end:]
new_text = "\n".join(out)
if not new_text.endswith("\n"):
    new_text += "\n"
path.write_text(new_text, encoding="utf-8")
print("wrote:  %s" % path)
PY

echo "updated $COMPOSE"

print_runbook
if [ -n "$SERVICES_DIR" ]; then
  echo
  echo "verify: $SERVICES_DIR against the new pin"
  "$HERE/verify-service-tar.sh" "$COMPOSE" "$SERVICES_DIR" --service web
fi
