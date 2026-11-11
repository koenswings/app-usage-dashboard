#!/usr/bin/env bash
# e2e-tar-fallback.sh — end-to-end installApp test of the services/ tar fallback.
#
# The Engine loads the web image from
# <diskRoot>/services/ghcr.io_koenswings_usage-dashboard-web:1.0.tar
# (a sibling of apps/, see docs/packaging.md) instead of running
# `docker pull` on ghcr. This script stages the App Disk bundle, builds and
# saves the arm64 web image plus the other compose service tars, then
# installApp through the Engine's local-disk path (--source, --fresh) so
# GET /api/v1/health reports the bundled commit (collector/build-info.json).
#
# Usage (on a claimed idea03 or idea04, as pi):
#   script/e2e-tar-fallback.sh [--keep] [--ingest-history <dir>]
#
# Dry-run (any host; no Docker, no Engine, no SSH, no hostname/claim check):
#   script/e2e-tar-fallback.sh --dry-run [--dest <dir>] [--keep] [--ingest-history <dir>]
#
# --keep  leave the instance running (skip teardown, keep tars and the web image).
# --ingest-history <dir>  after assertions, copy that usage tree to this run's
#   quarantine scratch (read-only of the original), flatten .archive day dirs,
#   export with idea-usage-export (IDEA_USAGE_ROOT=scratch), and ingest into
#   the instance store. Then also ingest a live `since 2026-10-01` export of
#   /var/lib/idea/usage (read-only; never archive-and-clear, never write usage).
#   Default dir: /home/pi/kid-quarantine/20261111T001400/usage
#
# Environment:
#   FLEET_STATE / STATE_FILE   path to fleet-state.json (claim must be Kid)
#   ENGINE_ROOT                default /home/pi/idea/agents/agent-engine-dev
#   ENGINE_API                 default http://127.0.0.1:8080
#   QUARANTINE_ROOT            default /home/pi/kid-quarantine
#   HISTORY_ROOT               default /home/pi/kid-quarantine/20261111T001400/usage
#
# Hard limits: no rm -rf, no pkill -f or pgrep -f, no dd, mkfs or wipe.
# Never touch /disks/sdb1 or the protected disks. Never print credentials.
# Never write /var/lib/idea/usage. Never run archive-and-clear.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
SEND="$HERE/send-engine-command.mjs"
WRITE_BUILD_INFO="$HERE/write-build-info.sh"
APP_NAME=usage-dashboard
APP_VERSION=1.0
APP_ID="${APP_NAME}-${APP_VERSION}"
WEB_IMAGE=ghcr.io/koenswings/usage-dashboard-web:1.0
INSTANCE_NAME=usage-dashboard-tar-e2e
ENGINE_ROOT=${ENGINE_ROOT:-/home/pi/idea/agents/agent-engine-dev}
QUARANTINE_ROOT=${QUARANTINE_ROOT:-/home/pi/kid-quarantine}
PROTECTED_SERIALS='AA202000000000004820 AA000000000000005638 3813430-532011020 20070Q450002'
PROTECTED_PATHS='/disks/sdb1'

DRY_RUN=0
DEST=""
DID_INSTALL=0
DID_TEARDOWN=0
INSTANCE_ID=""
INSTANCE_PORT=""
SYSTEM_DISK_ID=""
SYSTEM_DISK_DEV=""
COMMIT=""
RUN_ID=""
RUN_DIR=""
WROTE_FILES=()
LOG_MARK_OUT=0
LOG_MARK_ERR=0
KEEP=0
INGEST_HISTORY=0
HISTORY_ROOT=${HISTORY_ROOT:-/home/pi/kid-quarantine/20261111T001400/usage}
DEPLOYMENT_ID="dep-idea03-tar-e2e"
KIT_ENGINE=idea03


die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "==> $*" >&2; }

usage() {
  sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --dest) DEST="${2:-}"; shift 2 ;;
    --keep) KEEP=1; shift ;;
    --ingest-history)
      INGEST_HISTORY=1
      if [ -n "${2:-}" ] && [ "${2#--}" = "$2" ]; then
        HISTORY_ROOT="$2"
        shift 2
      else
        shift
      fi
      ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown arg: $1 (see --help)" ;;
  esac
done

[ -f "$REPO/compose.yaml" ] || die "compose.yaml not found in $REPO"
[ -x "$WRITE_BUILD_INFO" ] || die "write-build-info.sh is not executable"
[ -x "$SEND" ] || die "send-engine-command.mjs is not executable"

# --- temperature ----------------------------------------------------------

temp_c() {
  if [ -r /sys/class/thermal/thermal_zone0/temp ]; then
    awk '{ printf "%.1f", $1/1000 }' /sys/class/thermal/thermal_zone0/temp
    return
  fi
  if command -v vcgencmd >/dev/null 2>&1; then
    vcgencmd measure_temp 2>/dev/null | tr -dc '0-9.'
    return
  fi
  echo ""
}

pause_if_hot() {
  [ "$DRY_RUN" = 1 ] && return 0
  local t label="${1:-}"
  t=$(temp_c)
  [ -n "$t" ] || return 0
  log "SoC temp ${t} C${label:+ ($label)}"
  awk -v t="$t" 'BEGIN { exit !(t > 75) }' || return 0
  log "SoC ${t} C is above 75 C; pausing until it is below 65 C"
  while true; do
    sleep 15
    t=$(temp_c)
    [ -n "$t" ] || continue
    log "SoC temp ${t} C (waiting to drop below 65 C)"
    awk -v t="$t" 'BEGIN { exit !(t < 65) }' && break
  done
  log "SoC temp ${t} C; resuming"
}

# --- snapshots ------------------------------------------------------------

take_snapshot() {
  local dir="$1" label="$2"
  mkdir -p "$dir"
  {
    echo "# snapshot $label $(date '+%Y-%m-%d %H:%M:%S %z')"
    echo "# hostname=$(hostname 2>/dev/null || true)"
  } > "$dir/meta.txt"
  docker ps -a > "$dir/docker-ps.txt" 2>&1 || true
  docker images > "$dir/docker-images.txt" 2>&1 || true
  pm2 ls > "$dir/pm2-ls.txt" 2>&1 || true
  lsblk > "$dir/lsblk.txt" 2>&1 || true
  losetup -a > "$dir/losetup.txt" 2>&1 || true
  (temp_c; echo) > "$dir/tempC.txt" 2>&1 || true
  log "snapshot $label written under $dir"
}

diff_snapshots() {
  local before="$1" after="$2" out="$3"
  mkdir -p "$out"
  local f
  for f in docker-ps.txt docker-images.txt pm2-ls.txt lsblk.txt losetup.txt; do
    if [ -f "$before/$f" ] || [ -f "$after/$f" ]; then
      diff -u "$before/$f" "$after/$f" > "$out/$f.diff" || true
    fi
  done
  log "snapshot diffs written under $out"
  if [ -d "$out" ]; then
    echo "----- snapshot diffs -----"
    for f in "$out"/*.diff; do
      [ -f "$f" ] || continue
      if [ -s "$f" ]; then
        echo "### $(basename "$f")"
        cat "$f"
      else
        echo "### $(basename "$f"): no difference"
      fi
    done
  fi
}

# --- guards ---------------------------------------------------------------

find_fleet_state() {
  if [ -n "${FLEET_STATE:-}" ]; then
    [ -f "$FLEET_STATE" ] || die "FLEET_STATE is not a file: $FLEET_STATE"
    echo "$FLEET_STATE"
    return
  fi
  if [ -n "${STATE_FILE:-}" ]; then
    [ -f "$STATE_FILE" ] || die "STATE_FILE is not a file: $STATE_FILE"
    echo "$STATE_FILE"
    return
  fi
  local p
  for p in \
    /home/pi/idea/agents/idea/fleet-state.json \
    /home/pi/idea/fleet-state.json
  do
    if [ -f "$p" ]; then
      echo "$p"
      return
    fi
  done
  die "fleet-state.json not found (set FLEET_STATE)"
}

check_host_and_claim() {
  local host state claim
  host=$(hostname -s 2>/dev/null || hostname)
  case "$host" in
    idea03|idea04) ;;
    *) die "refusing to run on hostname '$host' (only idea03 or idea04)" ;;
  esac
  state=$(find_fleet_state)
  command -v jq >/dev/null 2>&1 || die "jq is required to read the fleet claim"
  claim=$(jq -r --arg h "$host" '.[$h].claim // empty' "$state")
  case "$claim" in
    Kid|Kid*) ;;
    *) die "refusing to run: fleet claim for $host is '${claim:-<null>}', not Kid (state $state)" ;;
  esac
  log "hostname $host, fleet claim '$claim' (Kid) from $state"
}

check_protected_disks() {
  local line serial path
  # Never operate on /disks/sdb1 or other /disks targets; this test uses the
  # system disk roots /apps /instances /services only.
  for path in $PROTECTED_PATHS /disks; do
    case "${DISK_ROOT:-}" in
      "$path"|"$path"/*) die "refusing to use disk root ${DISK_ROOT} (protected $path)" ;;
    esac
  done
  if command -v lsblk >/dev/null 2>&1; then
    while IFS= read -r line; do
      for serial in $PROTECTED_SERIALS; do
        case "$line" in
          *"$serial"*)
            # The root SSD serial is listed so dd/mkfs/wipe never target it.
            # installApp onto the already-mounted system partition is allowed.
            ;;
        esac
      done
      # Presence of the hardware test stick (UUID 3E50-902A) is not itself a
      # reason to abort: it is often docked on idea03. The chosen System Disk
      # is checked later and must not be that stick or Disk B.
      :
    done < <(lsblk -o NAME,SERIAL,UUID,LABEL,MOUNTPOINT 2>/dev/null || true)
  fi
}

assert_no_forbidden_target() {
  local target="$1"
  case "$target" in
    /disks|/disks/*)
      die "refusing to write $target (never touch /disks on this test)" ;;
    /var/lib/idea/usage|/var/lib/idea/usage/*)
      die "refusing to write $target (/var/lib/idea/usage is off limits)" ;;
  esac
}


disk_root() {
  # System disk is "/", never an empty string (cd "" fails; join bugs).
  local r="${1-}"
  if [ -z "$r" ] || [ "$r" = "." ]; then
    printf '%s\n' "/"
  else
    printf '%s\n' "$r"
  fi
}

# --- compose image / tar names (Engine serviceImageTarName / saveName) ----

compose_images() {
  awk '/^services:/{s=1;next} s&&/^[^ #]/{s=0} s&&/^    image:/{print $2}' "$REPO/compose.yaml" \
    | tr -d "\"'"
}

save_name() {
  local img="$1"
  printf '%s\n' "${img%%@*}"
}

tar_rel_of() {
  local name
  name=$(save_name "$1")
  printf 'services/%s.tar\n' "${name//\//_}"
}

# --- bundle staging -------------------------------------------------------

stage_bundle() {
  local root; root=$(disk_root "$1")
  local tmp bundle
  assert_no_forbidden_target "$root"
  mkdir -p "$root/apps" "$root/services"
  bundle="$root/apps/$APP_ID"
  if [ -e "$bundle" ]; then
    if [ "$DRY_RUN" = 1 ]; then
      die "$bundle already exists (dry-run dest must be empty of this app id)"
    fi
    local leftover="$RUN_DIR/pre-existing-$APP_ID"
    log "moving pre-existing $bundle to $leftover"
    mkdir -p "$RUN_DIR"
    mv "$bundle" "$leftover"
  fi
  tmp="$root/apps/.build-${APP_ID}.$$"
  mkdir "$tmp"
  # git-tracked files only (no .git), modes kept. Same approach as build-app-bundle.sh.
  (cd "$REPO" && git ls-files -z | tar --null -T - -cf -) | tar -xpf - -C "$tmp"
  [ ! -e "$tmp/SHA256SUMS" ] || die "App repo has its own SHA256SUMS at the root; that name is reserved"
  COMMIT=$(git -C "$REPO" rev-parse HEAD)
  "$WRITE_BUILD_INFO" --dest "$tmp" --commit "$COMMIT" --version "$APP_VERSION"
  [ -f "$tmp/collector/build-info.json" ] || die "write-build-info.sh did not write collector/build-info.json"
  mv "$tmp" "$bundle"
  WROTE_FILES+=("apps/$APP_ID")
  log "staged $bundle (commit $COMMIT)"
}

write_sums() {
  local root; root=$(disk_root "$1")
  shift
  local bundle="$root/apps/$APP_ID"
  local sums="$bundle/SHA256SUMS"
  local tars=("$@")
  (
    cd "$root"
    {
      find "apps/$APP_ID" \( -type f -o -type l \) ! -path "apps/$APP_ID/SHA256SUMS"
      if [ ${#tars[@]} -gt 0 ]; then
        printf '%s\n' "${tars[@]}"
      fi
    } | LC_ALL=C sort -u | while IFS= read -r f; do
      [ -e "$f" ] || die "SHA256SUMS: missing $f"
      sha256sum -- "$f"
    done
  ) > "$sums"
  log "SHA256SUMS: $(wc -l < "$sums") files"
}

# --- docker images / tars -------------------------------------------------

image_present() {
  docker image inspect "$1" >/dev/null 2>&1
}

ensure_official_image() {
  local ref="$1"
  local name
  name=$(save_name "$ref")
  if image_present "$name" || image_present "$ref"; then
    log "official image already present: $name"
    return
  fi
  log "pulling official image $ref (linux/arm64) so it can be saved as a service tar"
  docker image pull --platform linux/arm64 "$ref"
  if [ "$name" != "$ref" ]; then
    docker image tag "$ref" "$name"
  fi
}

save_tar() {
  local root; root=$(disk_root "$1")
  local ref="$2"
  local rel dest name
  rel=$(tar_rel_of "$ref")
  dest="$root/$rel"
  name=$(save_name "$ref")
  assert_no_forbidden_target "$dest"
  if [ -e "$dest" ]; then
    if [ "$name" = "$WEB_IMAGE" ]; then
      log "moving stale $dest aside so this run can write a fresh web tar"
      mkdir -p "$RUN_DIR/pre-existing-tars"
      mv "$dest" "$RUN_DIR/pre-existing-tars/$(basename "$dest")"
    else
      log "$rel exists, reused"
      echo "$rel"
      return
    fi
  fi
  log "docker save $name -> $rel"
  docker save "$name" > "$dest.partial"
  mv "$dest.partial" "$dest"
  WROTE_FILES+=("$rel")
  echo "$rel"
}

build_web_image() {
  pause_if_hot "before docker build"
  log "docker build $WEB_IMAGE (linux/arm64, COMMIT=$COMMIT)"
  docker build --platform linux/arm64 \
    --build-arg "COMMIT=$COMMIT" \
    --build-arg "PNPM_VERSION=9.15.9" \
    -f "$REPO/web/Dockerfile" \
    -t "$WEB_IMAGE" \
    "$REPO"
  pause_if_hot "after docker build"
}

# --- Engine helpers -------------------------------------------------------

engine_cmd() {
  node "$SEND" "$@"
}

inspect_store() {
  engine_cmd inspect
}

send_engine() {
  local cmd="$1"
  log "Engine command: $cmd"
  engine_cmd send "$cmd"
}

pick_system_disk() {
  local id
  inspect_store > "$RUN_DIR/store-inspect-before.json"
  python3 - "$RUN_DIR/store-inspect-before.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
local = data.get("localSystem") or []
if not local:
    sys.stderr.write(
        "ERROR: no System Disk is registered on the local engine.\n"
        "Restart Engine with IDEA_CONFIG_FILE pointing at the outside copy\n"
        "that has systemDiskSkip: false (do not edit the deployed tree).\n"
        "On idea03: /home/pi/kid-i416-installapp/engine-config-8241221.yaml\n"
    )
    sys.exit(1)
if len(local) != 1:
    # Prefer sda* / mmcblk0* style system devices; never sdb or /disks.
    prefer = [d for d in local if str(d.get("device") or "").startswith(("sda", "mmcblk"))]
    if len(prefer) == 1:
        local = prefer
    else:
        sys.stderr.write("ERROR: expected one local System Disk, got: %s\n" % json.dumps(local))
        sys.exit(1)
d = local[0]
dev = str(d.get("device") or "")
if dev == "sdb" or dev.startswith("sdb"):
    sys.stderr.write("ERROR: refusing System Disk device %s (Disk B / sdb is protected)\n" % dev)
    sys.exit(1)
print("%s\t%s" % (d["id"], dev))
PY
}

log_watermark() {
  local out="${HOME}/.pm2/logs/engine-out.log"
  local err="${HOME}/.pm2/logs/engine-error.log"
  LOG_MARK_OUT=0
  LOG_MARK_ERR=0
  [ -f "$out" ] && LOG_MARK_OUT=$(wc -l < "$out")
  [ -f "$err" ] && LOG_MARK_ERR=$(wc -l < "$err")
}

copy_new_logs() {
  local dest="$1"
  local out="${HOME}/.pm2/logs/engine-out.log"
  local err="${HOME}/.pm2/logs/engine-error.log"
  mkdir -p "$dest"
  if [ -f "$out" ]; then
    tail -n +"$((LOG_MARK_OUT + 1))" "$out" > "$dest/engine-out-new.log" || true
  fi
  if [ -f "$err" ]; then
    tail -n +"$((LOG_MARK_ERR + 1))" "$err" > "$dest/engine-error-new.log" || true
  fi
}

assert_no_web_pull() {
  local logs="$1"
  local combined="$logs/engine-combined.log"
  cat "$logs"/engine-out-new.log "$logs"/engine-error-new.log > "$combined" 2>/dev/null || true
  if grep -E 'Pulling service image[[:space:]]+usage-dashboard-web|docker image pull[^[:space:]]*[[:space:]]+usage-dashboard-web' "$combined" >/dev/null 2>&1; then
    die "Engine log shows a registry pull of usage-dashboard-web (see $combined)"
  fi
  if grep -F 'usage-dashboard-web:1.0' "$combined" | grep -E 'Pulling service image|docker image pull' >/dev/null 2>&1; then
    die "Engine log shows a registry pull of usage-dashboard-web:1.0 (see $combined)"
  fi
  if grep -F "Loading the service image" "$combined" | grep -F "usage-dashboard-web" >/dev/null 2>&1; then
    log "Engine log: loaded usage-dashboard-web from the service tar (no pull)"
    return 0
  fi
  if grep -F "Service image" "$combined" | grep -F "usage-dashboard-web" | grep -F "already exists" >/dev/null 2>&1; then
    log "Engine log: usage-dashboard-web tar already existed; pull skipped"
    return 0
  fi
  log "WARN: Engine log did not mention loading or skipping usage-dashboard-web; inspect $combined"
  # Still fail if inspect said the image was absent before install and we
  # cannot show a load. The caller also checks docker image inspect.
}

wait_for_instance() {
  local name="$1"
  local timeout="${2:-420}"
  local start now rc line
  start=$(date +%s)
  while true; do
    inspect_store > "$RUN_DIR/store-inspect-latest.json"
    rc=0
    line=$(python3 - "$RUN_DIR/store-inspect-latest.json" "$name" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
name = sys.argv[2]
found = [i for i in (data.get("localInstances") or []) if i.get("name") == name]
if not found:
    sys.exit(2)
# Prefer a Running instance with a port.
running = [i for i in found if i.get("status") == "Running" and i.get("port")]
pick = running[-1] if running else found[-1]
port = pick.get("port") or 0
status = pick.get("status") or ""
print("%s\t%s\t%s" % (pick.get("id") or "", port, status))
if status == "Running" and port:
    sys.exit(0)
sys.exit(3)
PY
) || rc=$?
    if [ "$rc" = 0 ]; then
      printf '%s\n' "$line"
      return 0
    fi
    now=$(date +%s)
    if [ $((now - start)) -ge "$timeout" ]; then
      die "timed out after ${timeout}s waiting for instance '$name' to become Running with a port"
    fi
    if [ "$rc" = 3 ]; then
      log "instance '$name' is present but not yet Running with a port; waiting"
    else
      log "waiting for Engine to register instance '$name'"
    fi
    pause_if_hot "waiting for install"
    sleep 5
  done
}

wait_for_health() {
  local port="$1"
  local timeout="${2:-240}"
  local start now url body
  start=$(date +%s)
  url="http://127.0.0.1:${port}/api/v1/health"
  while true; do
    if body=$(curl -fsS -m 5 "$url" 2>/dev/null); then
      printf '%s\n' "$body"
      return 0
    fi
    now=$(date +%s)
    if [ $((now - start)) -ge "$timeout" ]; then
      die "timed out after ${timeout}s waiting for $url"
    fi
    sleep 4
  done
}

assert_health() {
  local body="$1"
  local expect="$2"
  printf '%s\n' "$body" > "$RUN_DIR/health.json"
  python3 - "$body" "$expect" <<'PY'
import json, sys
body, expect = sys.argv[1], sys.argv[2]
try:
    data = json.loads(body)
except json.JSONDecodeError as e:
    sys.stderr.write("ERROR: /api/v1/health is not JSON: %s\n%s\n" % (e, body))
    sys.exit(1)
ok = True
def check(pred, msg):
    global ok
    if pred:
        print("PASS: " + msg)
    else:
        print("FAIL: " + msg)
        ok = False
check(data.get("ok") is True, "ok is true (got %r)" % (data.get("ok"),))
check(data.get("schema") == "idea-usage-api/1",
      "schema is idea-usage-api/1 (got %r)" % (data.get("schema"),))
check(data.get("commit") == expect,
      "commit equals bundled sha %s (got %r)" % (expect, data.get("commit")))
check(data.get("commit") not in (None, ""), "commit is not null")
if not ok:
    sys.exit(1)
PY
}

assert_web_pages() {
  local port="$1"
  local base="http://127.0.0.1:${port}"
  local tmp="$RUN_DIR/http"
  mkdir -p "$tmp"
  local code
  code=$(curl -sS -m 10 -o "$tmp/index.html" -w '%{http_code}' "$base/")
  if [ "$code" != "200" ]; then
    die "GET / returned $code, expected 200"
  fi
  if ! grep -qi '<html\|<!doctype html\|IDEA Field Usage\|id="root"' "$tmp/index.html"; then
    die "GET / body does not look like index.html (see $tmp/index.html)"
  fi
  if grep -qi 'Field usage dashboard' "$tmp/index.html" && ! grep -qi 'IDEA Field Usage' "$tmp/index.html"; then
    log "WARN: GET / still looks like the placeholder page"
  fi
  echo "PASS: GET / returns 200 and serves index.html"
  code=$(curl -sS -m 10 -o "$tmp/missing.js" -w '%{http_code}' "$base/assets/x.js")
  if [ "$code" != "404" ]; then
    die "GET /assets/x.js returned $code, expected 404 (SPA fallback must not apply under /assets/)"
  fi
  echo "PASS: GET /assets/x.js returns 404"
}

# --- teardown -------------------------------------------------------------

docker_rm_exited() {
  local id="$1"
  local line cid name
  [ -n "$id" ] || return 0
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    cid=${line%% *}
    name=${line#* }
    case "$name" in
      *"$id"*)
        log "docker rm (no -v) leftover $name ($cid)"
        docker rm "$cid"
        ;;
    esac
  done < <(docker ps -a --filter status=exited --format '{{.ID}} {{.Names}}' 2>/dev/null || true)
}

move_written() {
  local root; root=$(disk_root "$1")
  local dest="$2"
  mkdir -p "$dest/apps" "$dest/services"
  local rel
  for rel in "${WROTE_FILES[@]+"${WROTE_FILES[@]}"}"; do
    [ -n "$rel" ] || continue
    if [ -e "$root/$rel" ]; then
      assert_no_forbidden_target "$root/$rel"
      log "moving $root/$rel -> $dest/$rel"
      mkdir -p "$dest/$(dirname "$rel")"
      mv "$root/$rel" "$dest/$rel"
    fi
  done
}

remove_test_images() {
  if image_present "$WEB_IMAGE"; then
    log "docker image rm $WEB_IMAGE"
    docker image rm "$WEB_IMAGE" || log "WARN: could not remove $WEB_IMAGE"
  fi
}

teardown() {
  if [ "$DID_TEARDOWN" = 1 ]; then
    return 0
  fi
  DID_TEARDOWN=1
  pause_if_hot "before teardown"
  if [ -n "$INSTANCE_ID" ] && [ -n "$SYSTEM_DISK_ID" ]; then
    # Engine 8241221 needs stopInstance <instanceId> <diskId>.
    send_engine "stopInstance $INSTANCE_ID $SYSTEM_DISK_ID" || log "WARN: stopInstance failed"
    sleep 3
    send_engine "removeInstance $INSTANCE_ID" || log "WARN: removeInstance failed"
    sleep 3
    docker_rm_exited "$INSTANCE_ID"
  fi
  move_written "${DISK_ROOT:-}" "$RUN_DIR"
  remove_test_images
  log "teardown finished"
}

on_exit() {
  local rc=$?
  if [ "$DRY_RUN" = 1 ]; then
    exit "$rc"
  fi
  # --keep: leave the instance, tars and web image in place (Pixel re-check).
  if [ "$KEEP" = 1 ]; then
    log "exit rc=$rc keep=1 did_install=$DID_INSTALL (teardown skipped)"
    exit "$rc"
  fi
  if [ "$DID_TEARDOWN" != 1 ]; then
    teardown || true
  fi
  exit "$rc"
}


# --- history ingest (host-side, no pull key) ------------------------------

# The collector container writes ./data as root, so registry.json and
# usage.sqlite are often root-owned. Host-side ingest as pi has to copy or
# run via sudo (or matching ownership) rather than opening those paths
# directly. Never print credentials. sudo -n so a missing NOPASSWD fails
# immediately instead of hanging on a prompt.

install_into_instance_data() {
  local src="$1" dest="$2"
  local dir
  dir=$(dirname "$dest")
  if [ -e "$dest" ] && [ -w "$dest" ] && [ -w "$dir" ]; then
    cp "$src" "$dest"
  elif [ ! -e "$dest" ] && [ -w "$dir" ]; then
    cp "$src" "$dest"
  else
    sudo -n cp "$src" "$dest"
  fi
}

run_ingest_python() {
  local db_path="$1"
  shift
  local dir
  dir=$(dirname "$db_path")
  if { [ ! -e "$db_path" ] || [ -w "$db_path" ]; } && [ -w "$dir" ]; then
    python3 "$REPO/script/ingest-usage-export.py" --db "$db_path" "$@"
  else
    sudo -n python3 "$REPO/script/ingest-usage-export.py" --db "$db_path" "$@"
  fi
}

ensure_registry() {
  local data_dir="$1"
  local dest="$data_dir/registry.json"
  local scratch="$RUN_DIR/registry.json"
  # Seed the scratch copy from the live registry when we can read it.
  # The collector's root-owned file may be unreadable without sudo.
  if [ -f "$dest" ]; then
    if [ -r "$dest" ]; then
      cp "$dest" "$scratch"
    else
      # Read as root; the redirect targets the user-writable scratch copy.
      # shellcheck disable=SC2024
      sudo -n cat "$dest" > "$scratch"
    fi
  else
    printf '%s\n' '{"kits":[]}' > "$scratch"
  fi
  python3 - "$scratch" "$KIT_ENGINE" "$DEPLOYMENT_ID" <<'PY'
import json, sys
from pathlib import Path
path, engine, dep = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
data = {"kits": []}
if path.is_file():
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        data = {"kits": []}
    data.setdefault("kits", [])
kits = data["kits"]
found = False
for kit in kits:
    if kit.get("engine") == engine:
        kit.setdefault("tailscaleName", engine)
        kit.setdefault("school", "proof")
        kit["deploymentId"] = kit.get("deploymentId") or dep
        kit.setdefault("timezone", "Europe/Brussels")
        found = True
        break
if not found:
    kits.append({
        "engine": engine,
        "tailscaleName": engine,
        "school": "proof",
        "deploymentId": dep,
        "timezone": "Europe/Brussels",
        "note": "tar-fallback e2e re-ingest",
    })
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(str(path))
PY
  install_into_instance_data "$scratch" "$dest"
  # Ingest reads the installed path (sudo can read a root-owned copy).
  printf '%s\n' "$dest"
}

flatten_archive_days() {
  # Copy archive day dirs into the scratch root so idea-usage-export (which
  # only walks live YYYY-MM-DD folders, not .archive/) will include them.
  # Never overwrite a live day that is already at the scratch root.
  local scratch="$1"
  local list="$2"
  : > "$list"
  local stamp day dest
  [ -d "$scratch/.archive" ] || return 0
  for stamp in "$scratch/.archive"/*; do
    [ -d "$stamp" ] || continue
    for day in "$stamp"/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]; do
      [ -d "$day" ] || continue
      dest="$scratch/$(basename "$day")"
      echo "$(basename "$day")  source=$(basename "$stamp")" >> "$list"
      if [ -e "$dest" ]; then
        log "scratch already has $(basename "$day"); leaving the live copy, archive day noted"
      else
        cp -a "$day" "$dest"
      fi
    done
  done
}

export_usage_tree() {
  local root="$1"
  local since="$2"
  local out="$3"
  local bin
  bin=${IDEA_USAGE_EXPORT:-/usr/local/sbin/idea-usage-export}
  [ -x "$bin" ] || die "idea-usage-export not found at $bin"
  # settings.json in the scratch/live tree must say on, otherwise exit 10.
  local status
  status=$(python3 - "$root" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
path = root / "settings.json"
if not path.is_file():
    print("missing")
    sys.exit(0)
data = json.loads(path.read_text(encoding="utf-8"))
print((data or {}).get("usageMonitoring") or "off")
PY
)
  if [ "$status" != "on" ]; then
    if [ "$root" = "/var/lib/idea/usage" ]; then
      die "live usageMonitoring is '$status'; refusing to change /var/lib/idea/usage"
    fi
    log "scratch settings.json usageMonitoring=$status; writing on into the scratch copy only"
    python3 - "$root" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
path = root / "settings.json"
data = {}
if path.is_file():
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
if not isinstance(data, dict):
    data = {}
data["usageMonitoring"] = "on"
path.write_text(json.dumps(data) + "\n", encoding="utf-8")
PY
  fi
  log "export since $since from $root"
  # Read-only of the usage tree (scratch or live). Never archive-and-clear.
  set +e
  IDEA_USAGE_ROOT="$root" IDEA_USAGE_ENGINE="$KIT_ENGINE" "$bin" since "$since" > "$out" 2> "$out.stderr"
  local rc=$?
  set -e
  if [ "$rc" != 0 ]; then
    die "idea-usage-export since $since failed (rc $rc) stderr=$(tr '\n' ' ' < "$out.stderr")"
  fi
  echo "$rc"
}

ingest_stream() {
  local db_path="$1"
  local stream="$2"
  local registry="$3"
  local label="$4"
  run_ingest_python "$db_path" \
    --engine "$KIT_ENGINE" \
    --deployment-id "$DEPLOYMENT_ID" \
    --stream "$stream" \
    --registry "$registry" > "$RUN_DIR/ingest-$label.json"
  log "ingested $label: $(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["counts"])' "$RUN_DIR/ingest-$label.json")"
}

login_session() {
  # Writes a cookie jar. Does not print the password.
  local port="$1"
  local jar="$2"
  local pass_file="$3"
  python3 - "$port" "$jar" "$pass_file" <<'PY'
import json, sys, urllib.request, http.cookiejar
from pathlib import Path
port, jar_path, pass_file = sys.argv[1], sys.argv[2], sys.argv[3]
password = Path(pass_file).read_text(encoding="utf-8").splitlines()[0]
body = json.dumps({"username": "admin", "password": password}).encode()
cj = http.cookiejar.MozillaCookieJar(jar_path)
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
req = urllib.request.Request(
    "http://127.0.0.1:%s/api/v1/session" % port,
    data=body,
    method="POST",
    headers={"Content-Type": "application/json"},
)
with opener.open(req, timeout=10) as resp:
    data = json.loads(resp.read().decode())
if not data.get("authenticated"):
    sys.exit("login did not authenticate")
cj.save(ignore_discard=True, ignore_expires=True)
print("ok")
PY
}

api_get() {
  local port="$1" path="$2" jar="$3" dest="$4"
  python3 - "$port" "$path" "$jar" "$dest" <<'PY'
import json, sys, urllib.request, http.cookiejar
port, path, jar_path, dest = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
cj = http.cookiejar.MozillaCookieJar(jar_path)
cj.load(ignore_discard=True, ignore_expires=True)
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
with opener.open("http://127.0.0.1:%s%s" % (port, path), timeout=15) as resp:
    raw = resp.read()
open(dest, "wb").write(raw)
print(dest)
PY
}

assert_weeks_not_single_gap() {
  local port="$1" jar="$2"
  local week dep dest
  dep="$DEPLOYMENT_ID"
  for week in 2026-10-26 2026-11-02; do
    dest="$RUN_DIR/api-week-$week-presence.json"
    api_get "$port" "/api/v1/weeks/$week/schools/$dep/presence" "$jar" "$dest" >/dev/null
    python3 - "$dest" "$week" <<'PY'
import json, sys
path, week = sys.argv[1], sys.argv[2]
data = json.loads(open(path, encoding="utf-8").read())
segs = data.get("segments") or []
days = data.get("days") or []
states = [s.get("state") for s in segs]
on_days = [d for d in days if (d.get("onMinutes") or d.get("on_minutes") or 0)]
school = [d for d in days if (d.get("schoolHoursOnMinutes") or d.get("school_hours_on_minutes") or 0)]
only_gap = bool(segs) and all(s == "gapUnknown" for s in states)
has_presence = any(s in ("on", "off", "collectorGap") for s in states) or bool(days)
has_on = "on" in states or bool(on_days)
print("week %s segments=%s presenceDays=%s onMinutesDays=%s" % (week, states, len(days), len(on_days)))
if only_gap and not on_days:
    sys.stderr.write("FAIL: week %s is still one gapUnknown with no on-time\n" % week)
    sys.exit(1)
if not has_presence and not has_on:
    sys.stderr.write("FAIL: week %s has no presence or on-time\n" % week)
    sys.exit(1)
print("PASS: week %s has presence or on-time (not a single gapUnknown)" % week)
PY
  done
}

run_history_ingest() {
  local port="$1"
  local instance_dir="/instances/$INSTANCE_ID"
  local data_dir="$instance_dir/data"
  [ -d "$data_dir" ] || die "instance data dir not found: $data_dir"
  [ -d "$HISTORY_ROOT" ] || die "history root not found: $HISTORY_ROOT (set --ingest-history)"
  case "$HISTORY_ROOT" in
    /var/lib/idea/usage|/var/lib/idea/usage/*)
      die "refusing to use /var/lib/idea/usage as the history source for copying" ;;
  esac

  local scratch="$RUN_DIR/history-scratch"
  log "copying $HISTORY_ROOT -> $scratch (original left untouched)"
  mkdir -p "$scratch"
  # Copy contents, including hidden .archive, without touching the original.
  cp -a "$HISTORY_ROOT"/. "$scratch/"
  flatten_archive_days "$scratch" "$RUN_DIR/archive-dates.txt"
  log "archive dates (scratch flatten):"
  cat "$RUN_DIR/archive-dates.txt" >&2 || true

  local registry
  registry=$(ensure_registry "$data_dir")
  export_usage_tree "$scratch" "2026-10-01" "$RUN_DIR/export-archive.ndjson" >/dev/null
  ingest_stream "$data_dir/usage.sqlite" "$RUN_DIR/export-archive.ndjson" "$registry" "archive"

  # Live export is read-only. Do not write /var/lib/idea/usage.
  export_usage_tree "/var/lib/idea/usage" "2026-10-01" "$RUN_DIR/export-live.ndjson" >/dev/null
  ingest_stream "$data_dir/usage.sqlite" "$RUN_DIR/export-live.ndjson" "$registry" "live"

  # Login password: instance .env or the documented fixture default. Written
  # only to a 0600 file; never printed.
  local pass_file="$RUN_DIR/operator-password"
  python3 - "$instance_dir/.env" "$pass_file" <<'PY'
import os, sys
from pathlib import Path
env_path, dest = Path(sys.argv[1]), Path(sys.argv[2])
password = "admin911!"
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("IDEA_USAGE_ADMIN_PASSWORD="):
            value = line.split("=", 1)[1]
            if value:
                password = value
            break
dest.write_text(password + "\n", encoding="utf-8")
dest.chmod(0o600)
PY
  local jar="$RUN_DIR/session.cookies"
  login_session "$port" "$jar" "$pass_file" >/dev/null
  api_get "$port" "/api/v1/weeks" "$jar" "$RUN_DIR/api-weeks.json" >/dev/null
  api_get "$port" "/api/v1/weeks/2026-10-26/schools/$DEPLOYMENT_ID" "$jar" "$RUN_DIR/api-week-2026-10-26.json" >/dev/null
  api_get "$port" "/api/v1/weeks/2026-11-02/schools/$DEPLOYMENT_ID" "$jar" "$RUN_DIR/api-week-2026-11-02.json" >/dev/null
  assert_weeks_not_single_gap "$port" "$jar"
  log "history ingest verified. archive dates: $RUN_DIR/archive-dates.txt"
}

# --- dry-run --------------------------------------------------------------

run_dry() {
  local root
  if [ -n "$DEST" ]; then
    mkdir -p "$DEST"
    root=$(cd "$DEST" && pwd)
  else
    root=$(mktemp -d "${TMPDIR:-/tmp}/e2e-tar-fallback-dry.XXXXXX")
  fi
  RUN_DIR="$root/dry-run-meta"
  mkdir -p "$RUN_DIR"
  log "dry-run dest $root"
  stage_bundle "$root"
  local img rel planned=()
  while IFS= read -r img; do
    [ -n "$img" ] || continue
    rel=$(tar_rel_of "$img")
    planned+=("$rel")
    echo "$img -> $rel"
  done < <(compose_images)
  printf '%s\n' "${planned[@]}" > "$RUN_DIR/planned-tars.txt"
  # No docker daemon in dry-run: checksum the staged bundle only.
  write_sums "$root"
  python3 - "$root/apps/$APP_ID/collector/build-info.json" "$COMMIT" <<'PY'
import json, sys
path, expect = sys.argv[1], sys.argv[2]
data = json.load(open(path))
assert data["version"] == "1.0", data
assert data["commit"] == expect, data
print("PASS: staged collector/build-info.json version=1.0 commit=" + expect)
PY
  cat > "$RUN_DIR/planned-commands.txt" <<EOF
# Planned Engine / Docker steps (not executed in --dry-run)
docker build --platform linux/arm64 --build-arg COMMIT=$COMMIT -f web/Dockerfile -t $WEB_IMAGE .
docker save $WEB_IMAGE > services/ghcr.io_koenswings_usage-dashboard-web:1.0.tar
# plus official compose service tars:
#   services/python:3.12-slim-bookworm.tar
#   services/tailscale_tailscale:v1.88.3.tar
# nginx:1.28-alpine is the web image *build* base, not a compose service;
# Engine does not load a nginx tar once the web service tar exists.
docker image rm $WEB_IMAGE   # so installApp must load the tar, not reuse the build
installApp $APP_ID <systemDiskId> --source <systemDiskId> --fresh --name $INSTANCE_NAME
# wait for health, GET /, GET /assets/x.js
stopInstance <instanceId> <systemDiskId>
removeInstance <instanceId>
docker rm <exited leftovers>    # no -v; idea#424
# move written tars + bundle to $QUARANTINE_ROOT/<run>/  (never delete)
# --keep: skip teardown; leave the instance running
# --ingest-history: copy usage tree to scratch, flatten .archive days,
#   IDEA_USAGE_ROOT=scratch idea-usage-export since 2026-10-01,
#   ingest into the instance sqlite; then live since 2026-10-01 (read-only)
EOF
  log "dry-run ok"
  log "staged bundle: $root/apps/$APP_ID"
  log "planned tars:"
  cat "$RUN_DIR/planned-tars.txt"
  log "planned commands: $RUN_DIR/planned-commands.txt"
}

# --- main (live) ----------------------------------------------------------

run_live() {
  command -v docker >/dev/null 2>&1 || die "docker is required"
  command -v node >/dev/null 2>&1 || die "node is required"
  command -v python3 >/dev/null 2>&1 || die "python3 is required"
  command -v curl >/dev/null 2>&1 || die "curl is required"
  command -v jq >/dev/null 2>&1 || die "jq is required"
  command -v git >/dev/null 2>&1 || die "git is required"
  command -v sha256sum >/dev/null 2>&1 || die "sha256sum is required"
  [ -d "$ENGINE_ROOT" ] || die "ENGINE_ROOT not found: $ENGINE_ROOT"

  check_host_and_claim
  check_protected_disks
  pause_if_hot "start"

  COMMIT=$(git -C "$REPO" rev-parse HEAD)
  RUN_ID="tar-fallback-e2e-$(date '+%Y%m%dT%H%M%S%z')"
  RUN_DIR="$QUARANTINE_ROOT/$RUN_ID"
  mkdir -p "$RUN_DIR/before" "$RUN_DIR/after" "$RUN_DIR/diff" "$RUN_DIR/logs"
  echo "$COMMIT" > "$RUN_DIR/commit.txt"
  log "run id $RUN_ID (commit $COMMIT)"
  log "quarantine $RUN_DIR"

  take_snapshot "$RUN_DIR/before" "before"
  trap on_exit EXIT

  # System disk roots are /apps /services /instances (disk root /).
  DISK_ROOT="/"
  local pick
  pick=$(pick_system_disk)
  SYSTEM_DISK_ID=${pick%%$'\t'*}
  SYSTEM_DISK_DEV=${pick#*$'\t'}
  log "System Disk id=$SYSTEM_DISK_ID device=$SYSTEM_DISK_DEV (root /apps, not /disks)"
  case "$SYSTEM_DISK_DEV" in
    sdb|sdb*) die "refusing to install on $SYSTEM_DISK_DEV" ;;
  esac
  [ -d /apps ] && [ -d /services ] && [ -d /instances ] || \
    die "/apps /services /instances must exist on the system disk (is the Engine running with systemDiskSkip: false?)"

  # Stage onto the live system disk.
  stage_bundle ""

  local img tars=() rel
  while IFS= read -r img; do
    [ -n "$img" ] || continue
    case "$(save_name "$img")" in
      "$WEB_IMAGE")
        build_web_image
        save_tar "" "$img" >/dev/null
        rel=$(tar_rel_of "$img")
        tars+=("$rel")
        ;;
      *)
        ensure_official_image "$img"
        save_tar "" "$img" >/dev/null
        rel=$(tar_rel_of "$img")
        tars+=("$rel")
        ;;
    esac
  done < <(compose_images)
  write_sums "" "${tars[@]}"

  # The web image must not already be in the local docker store when
  # installApp starts, otherwise a passing inspect would not prove the tar load.
  if image_present "$WEB_IMAGE"; then
    log "removing local $WEB_IMAGE after docker save so Engine must load the tar"
    docker image rm "$WEB_IMAGE"
  fi
  if image_present "$WEB_IMAGE"; then
    die "$WEB_IMAGE is still present after docker image rm"
  fi
  echo "PASS: $WEB_IMAGE is absent before installApp"
  web_tar="/$(tar_rel_of "$WEB_IMAGE")"
  [ -f "$web_tar" ] || die "missing $web_tar"

  log_watermark
  DID_INSTALL=1
  send_engine "installApp $APP_ID $SYSTEM_DISK_ID --source $SYSTEM_DISK_ID --fresh --name $INSTANCE_NAME"

  local waited
  waited=$(wait_for_instance "$INSTANCE_NAME" 480)
  INSTANCE_ID=${waited%%$'\t'*}
  local rest=${waited#*$'\t'}
  INSTANCE_PORT=${rest%%$'\t'*}
  log "instance $INSTANCE_ID port $INSTANCE_PORT"
  echo "$INSTANCE_ID" > "$RUN_DIR/instance-id.txt"
  echo "$INSTANCE_PORT" > "$RUN_DIR/instance-port.txt"
  echo "$SYSTEM_DISK_ID" > "$RUN_DIR/system-disk-id.txt"

  copy_new_logs "$RUN_DIR/logs"
  assert_no_web_pull "$RUN_DIR/logs"
  if image_present "$WEB_IMAGE"; then
    echo "PASS: $WEB_IMAGE is present after installApp (loaded from tar, not pulled)"
  else
    die "$WEB_IMAGE is still absent after installApp; tar load did not happen"
  fi

  local health
  health=$(wait_for_health "$INSTANCE_PORT" 240)
  log "GET /api/v1/health -> $health"
  assert_health "$health" "$COMMIT"
  assert_web_pages "$INSTANCE_PORT"

  if [ "$INGEST_HISTORY" = 1 ]; then
    run_history_ingest "$INSTANCE_PORT"
  fi

  if [ "$KEEP" = 1 ]; then
    take_snapshot "$RUN_DIR/after" "after-kept-running"
    diff_snapshots "$RUN_DIR/before" "$RUN_DIR/after" "$RUN_DIR/diff"
    {
      echo "url=http://100.126.117.80:${INSTANCE_PORT}/"
      echo "instanceId=$INSTANCE_ID"
      echo "diskId=$SYSTEM_DISK_ID"
      echo "appId=$APP_ID"
      echo "commit=$COMMIT"
      echo "keep=1"
    } > "$RUN_DIR/keep.txt"
    echo "$RUN_ID" > "$RUN_DIR/ok.txt"
    log "PASS: tar-fallback e2e complete; instance left running (--keep). Artifacts: $RUN_DIR"
    log "URL http://100.126.117.80:${INSTANCE_PORT}/  instance $INSTANCE_ID  disk $SYSTEM_DISK_ID"
    return 0
  fi

  teardown
  take_snapshot "$RUN_DIR/after" "after"
  diff_snapshots "$RUN_DIR/before" "$RUN_DIR/after" "$RUN_DIR/diff"
  echo "$RUN_ID" > "$RUN_DIR/ok.txt"
  log "PASS: tar-fallback e2e complete. Artifacts: $RUN_DIR"
}

# --- entry ----------------------------------------------------------------

if [ "$DRY_RUN" = 1 ]; then
  run_dry
else
  run_live
fi
