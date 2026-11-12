#!/usr/bin/env bash
# i443-update-checks.sh — READ-ONLY pre/post checks for the idea#443 updateApp of the
# idea-hub instance on idea03 (usage-dashboard-8fhwrslsrq78xtswed4 -> usage-dashboard-1.1).
#
# Run on idea03 as pi, INSIDE A CLAIM SOMEONE ELSE MADE (this script never claims,
# starts, stops, loads, pulls or writes anything outside its own --out dir under
# /home/pi/kid-evidence/). It never prints or stores secrets: .env, data/keys and the
# tailscale state are only tested for presence (and .env hashed); `docker inspect` is
# read through a --format with no Env; `tailscale status --json` is reduced in-pipe to
# BackendState and a Self.PublicKey prefix.
#
# Usage:
#   i443-update-checks.sh pre  --stick <stick disk root> [options]
#   i443-update-checks.sh post --pre <pre out dir> --expect-commit <sha> \
#                              --tag-compose-sha256 <hex> --stick <stick disk root> [options]
# Options:
#   --instance ID            default usage-dashboard-8fhwrslsrq78xtswed4
#   --app-id ID              default usage-dashboard-1.1
#   --out DIR                default /home/pi/kid-evidence/i443-<mode>-<UTC stamp> (must not exist)
#   --engine-dir DIR         default /home/pi/idea/agents/agent-engine-dev
#   --require-engine-commit SHA   (pre, repeatable) FAIL unless SHA is an ancestor of Engine HEAD
#   --min-helper N           default 9 (#448 updateApp needs idea-app-data v9)
#   --tag-compose-sha256 HEX pre: optional, stick compose must equal it; post: required
#   --expect-commit SHA      post: GET /api/v1/health commit must equal it (full or prefix)
#   --snapshot-dir DIR       post: the updateApp snapshot, default /.pre-update/<instance>
#                            (<instance disk appDataRoot>/.pre-update/<id>, UpdateApp.ts)
#   --max-backup-age-s N     pre: FAIL if the newest backup is older (default: report only)
#   --dry-run                print the check plan and exit 0; runs nothing, writes nothing
#   --fixture DIR            tests only: prefix every absolute path (also --out, --stick)
#                            with DIR; docker, curl and sudo stubs come from PATH
# Output: one "PASS|FAIL|INFO|WARN <id> <name>: <detail>" line per check on stdout and in
# <out>/report.txt; key=value baseline in <out>/baseline.env (post reads the pre one).
# Exit 0 = every check passed; 1 = at least one FAIL; 2 = usage error.
set -uo pipefail
export LC_ALL=C

MODE="${1:-}"
case "$MODE" in pre|post) shift ;; -h|--help|"") sed -n '2,33p' "$0" | sed 's/^# \{0,1\}//'; [ -n "$MODE" ]; exit $? ;; *) echo "usage: $0 pre|post ..." >&2; exit 2 ;; esac

INSTANCE=usage-dashboard-8fhwrslsrq78xtswed4
APP_ID=usage-dashboard-1.1
OUT="" STICK="" PRE="" SNAP_ARG="" EXPECT_COMMIT="" TAG_SHA="" MAX_BACKUP_AGE="" FX="" DRY=0
ENGINE_DIR=/home/pi/idea/agents/agent-engine-dev
MIN_HELPER=9
REQ_COMMITS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --instance) INSTANCE="${2:-}"; shift 2 ;;
    --app-id) APP_ID="${2:-}"; shift 2 ;;
    --out) OUT="${2:-}"; shift 2 ;;
    --stick) STICK="${2:-}"; shift 2 ;;
    --pre) PRE="${2:-}"; shift 2 ;;
    --engine-dir) ENGINE_DIR="${2:-}"; shift 2 ;;
    --require-engine-commit) REQ_COMMITS+=("${2:-}"); shift 2 ;;
    --min-helper) MIN_HELPER="${2:-}"; shift 2 ;;
    --tag-compose-sha256) TAG_SHA="${2:-}"; shift 2 ;;
    --expect-commit) EXPECT_COMMIT="${2:-}"; shift 2 ;;
    --max-backup-age-s) MAX_BACKUP_AGE="${2:-}"; shift 2 ;;
    --snapshot-dir) SNAP_ARG="${2:-}"; shift 2 ;;
    --fixture) FX="${2:-}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
usage_err() { echo "ERROR: $*" >&2; exit 2; }
[[ "$INSTANCE" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || usage_err "bad --instance"
[[ "$APP_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || usage_err "bad --app-id"
[[ "$MIN_HELPER" =~ ^[0-9]+$ ]] || usage_err "bad --min-helper"
[ -z "$TAG_SHA" ] || [[ "$TAG_SHA" =~ ^[0-9a-f]{64}$ ]] || usage_err "--tag-compose-sha256 must be 64 hex"
[ -z "$MAX_BACKUP_AGE" ] || [[ "$MAX_BACKUP_AGE" =~ ^[0-9]+$ ]] || usage_err "bad --max-backup-age-s"
if [ "$MODE" = pre ]; then
  [ -n "$STICK" ] || usage_err "pre needs --stick <stick disk root>"
else
  [ -n "$PRE" ] || usage_err "post needs --pre <pre out dir>"
  [ -n "$EXPECT_COMMIT" ] || usage_err "post needs --expect-commit <sha>"
  [[ "$EXPECT_COMMIT" =~ ^[0-9a-f]{7,40}$ ]] || usage_err "--expect-commit must be hex"
  [ -n "$TAG_SHA" ] || usage_err "post needs --tag-compose-sha256 (sha256 of git show 1.1:compose.yaml)"
  [ -n "$STICK" ] || usage_err "post needs --stick <stick disk root> for the drift check"
fi
if [ -n "$FX" ]; then FX=$(cd "$FX" && pwd) || usage_err "--fixture dir missing"; fi

# All host paths, prefixed in fixture mode.
P() { printf '%s%s' "$FX" "$1"; }
INST_DIR=$(P "/instances/$INSTANCE")
APPS_DIR=$(P /apps)
SERVICES_DIR=$(P /services)
SETTINGS=$(P /var/lib/idea/usage/settings.json)
DISKS=$(P /disks)
SNAP_DIR=$(P "${SNAP_ARG:-/.pre-update/$INSTANCE}")
HELPER=/usr/local/sbin/idea-app-data
EVIDENCE_ROOT=$(P /home/pi/kid-evidence)
[ -z "$FX" ] || ENGINE_DIR="$FX$ENGINE_DIR"
case "$STICK" in "") ;; /*) [ -z "$FX" ] || STICK="$FX$STICK" ;; *) usage_err "--stick must be absolute" ;; esac
STICK_BUNDLE="$STICK/apps/$APP_ID"
HERE=$(cd "$(dirname "$0")" && pwd)
VST="$HERE/../verify-service-tar.sh"
SAFE="$HERE/../check-bundle-safe.py"
TS_SOCK=/var/run/tailscale/tailscaled.sock
DOCKER=${DOCKER:-docker}
CURL=${CURL:-curl}
SUDO=${SUDO:-sudo}

if [ "$DRY" = 1 ]; then
  cat <<PLAN
DRY RUN ($MODE): nothing is run or written. instance=$INSTANCE app=$APP_ID
reads: $INST_DIR (compose.yaml x-app, stat data/tailscale, presence of .env data/keys tailscaled.state)
       $APPS_DIR $SERVICES_DIR $SETTINGS $DISKS/*/BACKUP.yaml $SNAP_DIR ${STICK:-<no stick>}
runs:  git -C $ENGINE_DIR rev-parse HEAD; $SUDO -n $HELPER version
       $DOCKER ps -aq --filter label=com.docker.compose.project=$INSTANCE
       $DOCKER inspect --format <id|name|image|status|health|service, no Env> <ids>
       $DOCKER exec <tailscale> tailscale --socket=$TS_SOCK status --json  (BackendState + PublicKey prefix only)
       $DOCKER port <web> 8080/tcp; $CURL -fsS http://127.0.0.1:<port>/api/v1/health
       $DOCKER image inspect <repo@digest> per 1.1 image; $VST <compose> $SERVICES_DIR
       sha256sum; df; find (names only)
PLAN
  if [ "$MODE" = pre ]; then
    echo "checks: P01 engine P02 helper P03 instanceOf P04 containers P05 tailscale P06 state-inode P07 secrets-presence P08 usageMonitoring P09 health P10 live-tars P11 bundle-tars P12 images-available P13 stick-bundle P14 stick-compose P15 free-space P16 backup-age P17 apps-listing P99 no-secrets-in-evidence"
  else
    echo "checks: Q01 instanceOf Q02 health Q03 nodekey Q04 state-inode Q05 backendstate Q06 usageMonitoring Q07 containers Q08 drift-tag Q09 drift-stick Q10 apps-files Q11 snapshot-no-secrets Q12 no-join-marker P99 no-secrets-in-evidence"
  fi
  exit 0
fi

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
if [ -z "$OUT" ]; then OUT="$EVIDENCE_ROOT/i443-$MODE-$STAMP"
else case "$OUT" in /*) OUT="$FX$OUT" ;; *) usage_err "--out must be absolute" ;; esac; fi
case "$(realpath -m "$OUT")/" in "$(realpath -m "$EVIDENCE_ROOT")"/?*) ;; *) usage_err "--out must be under $EVIDENCE_ROOT" ;; esac
[ ! -e "$OUT" ] || usage_err "$OUT exists; evidence dirs are written once"
mkdir -p "$OUT" || usage_err "cannot create $OUT"
chmod 0700 "$OUT"
REPORT="$OUT/report.txt"
BASE="$OUT/baseline.env"
: > "$REPORT"; : > "$BASE"
FAILS=0

say() { printf '%s\n' "$*" | tee -a "$REPORT"; }
res() { # res STATUS ID NAME DETAIL
  say "$1 $2 $3: $4"
  [ "$1" != FAIL ] || FAILS=$((FAILS + 1))
}
rec() { printf '%s=%s\n' "$1" "$2" >> "$BASE"; }
sha() { sha256sum -- "$1" 2>/dev/null | cut -d' ' -f1; }
xapp() { # xapp <compose> <key>  (x-app top-level scalar, quotes stripped)
  awk -v k="$2" '/^x-app:/{x=1;next} x&&/^[^ #]/{x=0} x&&$1==k":"{v=$2; gsub(/"/,"",v); print v; exit}' "$1" 2>/dev/null
}
instance_of() { local c="$INST_DIR/compose.yaml" n v; n=$(xapp "$c" name); v=$(xapp "$c" version); [ -n "$n" ] && printf '%s-%s' "$n" "$v"; }
pre_val() { sed -n "s/^$1=//p" "$PRE/baseline.env" 2>/dev/null | tail -1; }
in_pipe_status() { # tailscale status --json on stdin -> "BackendState PublicKeyPrefix"
  python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("unparsable none"); sys.exit(0)
pk = str((d.get("Self") or {}).get("PublicKey") or "")
print("%s %s" % (d.get("BackendState") or "none", pk[:16] if pk else "none"))'
}

say "== i443-update-checks $MODE $STAMP instance=$INSTANCE app=$APP_ID host=$(hostname)${FX:+ FIXTURE=$FX}"
rec mode "$MODE"; rec stamp "$STAMP"; rec instance "$INSTANCE"

# ---- containers (shared) ----
declare -A CID=()
containers_check() { # id
  local ids line bad=0 n=0 detail=""
  ids=$("$DOCKER" ps -aq --filter "label=com.docker.compose.project=$INSTANCE" 2>/dev/null)
  if [ -z "$ids" ]; then res FAIL "$1" containers "no containers for project $INSTANCE"; return; fi
  for id in $ids; do
    line=$("$DOCKER" inspect --format '{{.Id}}|{{.Name}}|{{.Config.Image}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{index .Config.Labels "com.docker.compose.service"}}' "$id" 2>/dev/null) || { bad=1; continue; }
    IFS='|' read -r fid _name image status health svc <<<"$line"
    n=$((n + 1))
    CID[$svc]=$fid
    rec "container_$svc" "${fid:0:12} $image $status $health"
    detail+=" $svc=${fid:0:12}/$status/$health"
    { [ "$status" = running ] && { [ "$health" = healthy ] || [ "$health" = none ]; }; } || bad=1
  done
  for s in tailscale collector web; do [ -n "${CID[$s]:-}" ] || { bad=1; detail+=" $s=absent"; }; done
  if [ "$bad" = 0 ]; then res PASS "$1" containers "$n running/healthy:$detail"; else res FAIL "$1" containers "not all running+healthy:$detail"; fi
}
TS_STATE="none none"
tailscale_check() { # id
  local out bs pk
  if [ -z "${CID[tailscale]:-}" ]; then res FAIL "$1" tailscale "no tailscale container"; return; fi
  out=$("$DOCKER" exec "${CID[tailscale]}" tailscale "--socket=$TS_SOCK" status --json 2>/dev/null | in_pipe_status)
  TS_STATE=${out:-"none none"}
  read -r bs pk <<<"$TS_STATE"
  rec backend_state "$bs"; rec nodekey_prefix "$pk"
  if [ "$bs" = Running ] && [ "$pk" != none ]; then res PASS "$1" tailscale "BackendState=$bs Self.PublicKey=$pk…"
  else res FAIL "$1" tailscale "BackendState=$bs Self.PublicKey=$pk"; fi
}
INODE=""
inode_check() { # id
  INODE=$(stat -c %i -- "$INST_DIR/data/tailscale" 2>/dev/null)
  rec tailscale_inode "${INODE:-none}"
  if [ -n "$INODE" ]; then res PASS "$1" state-inode "data/tailscale inode=$INODE"; else res FAIL "$1" state-inode "data/tailscale missing or unreadable"; fi
}
usage_check() { # id
  local v
  v=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("usageMonitoring","missing"))' "$SETTINGS" 2>/dev/null)
  rec usage_monitoring "${v:-unreadable}"
  if [ "$v" = on ]; then res PASS "$1" usageMonitoring "on ($SETTINGS)"; else res FAIL "$1" usageMonitoring "${v:-unreadable} ($SETTINGS)"; fi
}
HEALTH_V="" HEALTH_C=""
health_read() {
  local port body
  [ -n "${CID[web]:-}" ] || return 1
  port=$("$DOCKER" port "${CID[web]}" 8080/tcp 2>/dev/null | head -1 | sed 's/.*://')
  [[ "$port" =~ ^[0-9]+$ ]] || return 1
  body=$("$CURL" -fsS -m 10 "http://127.0.0.1:$port/api/v1/health" 2>/dev/null) || return 1
  read -r ok HEALTH_V HEALTH_C < <(printf '%s' "$body" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("bad - -"); sys.exit(0)
print("%s %s %s" % ("ok" if d.get("ok") is True else "notok", d.get("version") or "-", d.get("commit") or "-"))')
  [ "$ok" = ok ]
}
tars_check() { # id label compose
  local out rc
  if [ ! -f "$3" ]; then res FAIL "$1" "$2" "compose missing: $3"; return 1; fi
  out=$(python3 "$HERE/../verify_service_tar.py" "$3" "$SERVICES_DIR" 2>&1); rc=$?
  printf '%s\n' "$out" > "$OUT/$2.verify-service-tar.log"
  VST_OUT=$out
  local summary; summary=$(printf '%s\n' "$out" | sed -n 's/^summary: //p' | tail -1)
  rec "${2//-/_}_vst" "rc=$rc $summary"
  if [ "$rc" = 0 ]; then res PASS "$1" "$2" "verify-service-tar vs $SERVICES_DIR: $summary"
  else res FAIL "$1" "$2" "verify-service-tar rc=$rc: ${summary:-see $2.verify-service-tar.log}"; fi
}
sums_check() { # dir prefix -> 0 if sha256sum -c strict passes and every file listed
  local root=$1 b=$2 extra
  [ -f "$root/$b/SHA256SUMS" ] || { echo "no SHA256SUMS"; return 1; }
  (cd "$root" && sha256sum --quiet --strict -c "$b/SHA256SUMS" >/dev/null 2>&1) || { echo "sha256sum -c failed"; return 1; }
  extra=$(comm -23 <(cd "$root" && find "$b" \( -type f -o -type l \) ! -path "$b/SHA256SUMS" ! -path "$b/.idea-*" | sort) \
                   <(sed -E 's/^[0-9a-f]{64} [ *]//' "$root/$b/SHA256SUMS" | sort))
  [ -z "$extra" ] || { echo "unlisted: $(echo "$extra" | head -3 | tr '\n' ' ')"; return 1; }
  grep -Eq "^[0-9a-f]{64} [ *]$b/compose.yaml$" "$root/$b/SHA256SUMS" || { echo "compose.yaml not listed"; return 1; }
  echo "$(wc -l < "$root/$b/SHA256SUMS") files OK"
}
evidence_scan() {
  local hits
  hits=$(grep -rlE 'tskey-|privkey|PRIVATE KEY|"PrivateKey"|_PASSWORD=|SESSION_SECRET=|TS_AUTHKEY=[^ ]' "$OUT" 2>/dev/null | grep -v '/report.txt$')
  if [ -z "$hits" ]; then res PASS P99 no-secrets-in-evidence "no key/password patterns in $OUT"
  else res FAIL P99 no-secrets-in-evidence "secret-like pattern in: $hits"; fi
}

if [ "$MODE" = pre ]; then
  # P01 Engine
  head=$(git -C "$ENGINE_DIR" rev-parse HEAD 2>/dev/null)
  ever=$(sed -n 's/^  "version": "\(.*\)",$/\1/p' "$ENGINE_DIR/package.json" 2>/dev/null | head -1)
  rec engine_commit "${head:-none}"; rec engine_version "${ever:-none}"
  if [ -z "$head" ]; then res FAIL P01 engine "cannot read Engine HEAD in $ENGINE_DIR"
  else
    miss=""
    for c in "${REQ_COMMITS[@]}"; do git -C "$ENGINE_DIR" merge-base --is-ancestor "$c" HEAD 2>/dev/null || miss+=" $c"; done
    if [ -n "$miss" ]; then res FAIL P01 engine "HEAD ${head:0:12} (v$ever) lacks required:$miss"
    else res PASS P01 engine "HEAD ${head:0:12} v$ever${REQ_COMMITS[*]:+ contains ${REQ_COMMITS[*]}}"; fi
  fi
  # P02 helper
  hv=$("$SUDO" -n "$HELPER" version 2>/dev/null | head -1)
  rec helper_version "${hv:-none}"
  n=${hv#idea-app-data }
  if [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -ge "$MIN_HELPER" ]; then res PASS P02 helper "$hv (>= $MIN_HELPER)"
  else res FAIL P02 helper "'${hv:-none}', need idea-app-data >= $MIN_HELPER"; fi
  # P03 instanceOf
  io=$(instance_of); rec instance_of "${io:-none}"
  if [ -n "$io" ]; then res INFO P03 instanceOf "$io (from instances/$INSTANCE/compose.yaml x-app, as Instance.ts createAppId)"
  else res FAIL P03 instanceOf "cannot read $INST_DIR/compose.yaml x-app"; fi
  containers_check P04
  tailscale_check P05
  inode_check P06
  # P07 secrets: presence only (and .env hash); never read into the evidence
  envh=none; [ -r "$INST_DIR/.env" ] && envh="sha256:$(sha "$INST_DIR/.env" | cut -c1-16)"
  [ -e "$INST_DIR/.env" ] && [ "$envh" = none ] && envh=present-unreadable
  keys=absent; [ -e "$INST_DIR/data/keys" ] && keys=present
  st=unknown; if [ -x "$INST_DIR/data/tailscale" ]; then st=absent; [ -e "$INST_DIR/data/tailscale/tailscaled.state" ] && st=present; fi
  jb=unknown; if [ -x "$INST_DIR/data/tailscale" ]; then jb=absent; [ -e "$INST_DIR/data/tailscale/authkey-join-blocked" ] && jb=present; fi
  rec env_hash "$envh"; rec keys "$keys"; rec state_file "$st"; rec join_blocked "$jb"
  if [ "$envh" != none ] && [ "$st" != absent ] && [ "$jb" != present ]; then res PASS P07 secrets-presence ".env=$envh data/keys=$keys tailscaled.state=$st authkey-join-blocked=$jb"
  else res FAIL P07 secrets-presence ".env=$envh data/keys=$keys tailscaled.state=$st authkey-join-blocked=$jb"; fi
  usage_check P08
  if health_read; then rec health "ok $HEALTH_V $HEALTH_C"; res PASS P09 health "ok version=$HEALTH_V commit=$HEALTH_C"
  else rec health "fail"; res FAIL P09 health "GET /api/v1/health via web port failed"; fi
  # P10/P11 tars; P12 every 1.1 image local or MATCH (the stick's services/ are NOT used, Instance.ts:1402-1426)
  tars_check P10 live-tars "$INST_DIR/compose.yaml"
  VST_OUT=""
  tars_check P11 bundle-tars "$STICK_BUNDLE/compose.yaml"
  bundle_vst=$VST_OUT
  imgs=$(awk '/^services:/{s=1;next} s&&/^[^ #]/{s=0} s&&/^    image:/{print $2}' "$STICK_BUNDLE/compose.yaml" 2>/dev/null | tr -d "\"'" | sort -u)
  if [ -z "$imgs" ]; then res FAIL P12 images-available "no images read from $STICK_BUNDLE/compose.yaml"
  else
    bad="" ok=""
    for img in $imgs; do
      if [[ "$img" != *@sha256:* ]]; then bad+=" $img(unpinned)"; continue; fi
      repo=${img%%@*}; dig=${img#*@}; repo_nt=${repo%:*}; [[ "${repo##*/}" == *:* ]] || repo_nt=$repo
      local_=no; "$DOCKER" image inspect --format '{{.Id}}' "$repo_nt@$dig" >/dev/null 2>&1 && local_=yes
      tar=no; printf '%s\n' "$bundle_vst" | awk -v r="$img" '$1=="MATCH" && $3==r {f=1} END {exit !f}' && tar=MATCH
      rec "image_${repo_nt##*/}" "local=$local_ tar=$tar"
      if [ "$local_" = yes ] || [ "$tar" = MATCH ]; then ok+=" ${repo##*/}(local=$local_,tar=$tar)"; else bad+=" ${repo##*/}(local=no,tar=$tar)"; fi
    done
    if [ -z "$bad" ]; then res PASS P12 images-available "every 1.1 pin local or MATCH in $SERVICES_DIR:$ok"
    else res FAIL P12 images-available "not local and no MATCH tar in $SERVICES_DIR:$bad"; fi
  fi
  # P13 stick: META.yaml, bundle sums (verify-app-bundle rules), copyBundle safety
  meta="$STICK/META.yaml"; mfail=""
  if [ -f "$meta" ]; then
    for k in diskId diskName created lastDocked; do grep -Eq "^$k:[[:space:]]*[^[:space:]]" "$meta" || mfail+=" no-$k"; done
  else mfail=" META.yaml-missing"; fi
  sres=$(sums_check "$STICK" "apps/$APP_ID"); srcode=$?
  safe=$(python3 "$SAFE" "$STICK_BUNDLE" 2>&1); safecode=$?
  printf '%s\n' "$safe" > "$OUT/check-bundle-safe.log"
  rec stick_sums "$sres"; rec stick_compose_sha256 "$(sha "$STICK_BUNDLE/compose.yaml")"
  if [ -z "$mfail" ] && [ "$srcode" = 0 ] && [ "$safecode" = 0 ]; then res PASS P13 stick-bundle "META.yaml ok; apps/$APP_ID SHA256SUMS $sres; copyBundle-safe"
  else res FAIL P13 stick-bundle "META:${mfail:- ok} sums:$sres safe:$(printf '%s' "$safe" | head -2 | tr '\n' ' ')"; fi
  # P14 stick compose vs tag
  sc=$(sha "$STICK_BUNDLE/compose.yaml")
  if [ -z "$TAG_SHA" ]; then res INFO P14 stick-compose "sha256 ${sc:-missing} (no --tag-compose-sha256 given)"
  elif [ "$sc" = "$TAG_SHA" ]; then res PASS P14 stick-compose "equals tag compose $TAG_SHA"
  else res FAIL P14 stick-compose "stick ${sc:-missing} != tag $TAG_SHA"; fi
  # P15 free space on / vs the snapshot (instance size + max(10%, 1 GiB))
  avail=$(df -B1 --output=avail "$(P /)" 2>/dev/null | tail -1 | tr -d ' ')
  size=$(du -sb "$INST_DIR" 2>/dev/null | cut -f1)
  [[ "$size" =~ ^[0-9]+$ ]] || size=0
  margin=$(( size / 10 > 1073741824 ? size / 10 : 1073741824 ))
  need=$(( size + margin ))
  rec free_root "${avail:-none}"; rec instance_bytes "$size"
  if [[ "$avail" =~ ^[0-9]+$ ]] && [ "$avail" -ge "$need" ]; then res PASS P15 free-space "/ avail=$avail need>=$need (instance~$size, du may undercount root-only files)"
  else res FAIL P15 free-space "/ avail=${avail:-?} need>=$need"; fi
  # P16 newest backup age (BACKUP.yaml links, read only)
  now=$(date +%s%3N); newest=""; where=""
  for y in "$DISKS"/*/BACKUP.yaml; do
    [ -r "$y" ] || continue
    t=$(awk -v id="$INSTANCE" '/instanceId:/{m=($NF==id)} m&&/lastBackup:/{print $NF; m=0}' "$y" | tr -d "\"'" | sort -n | tail -1)
    if [[ "$t" =~ ^[0-9]+$ ]] && { [ -z "$newest" ] || [ "$t" -gt "$newest" ]; }; then newest=$t; where=$y; fi
  done
  if [ -z "$newest" ]; then
    rec backup_age_s none
    if [ -n "$MAX_BACKUP_AGE" ]; then res FAIL P16 backup-age "no backup of $INSTANCE in $DISKS/*/BACKUP.yaml"
    else res INFO P16 backup-age "no backup of $INSTANCE found in $DISKS/*/BACKUP.yaml"; fi
  else
    age=$(( (now - newest) / 1000 )); rec backup_age_s "$age"
    if [ -n "$MAX_BACKUP_AGE" ] && [ "$age" -gt "$MAX_BACKUP_AGE" ]; then res FAIL P16 backup-age "${age}s old > $MAX_BACKUP_AGE ($where)"
    else res INFO P16 backup-age "${age}s old ($where)"; fi
  fi
  # P17 /apps listing
  apps=$(find "$APPS_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' 2>/dev/null | sort | tr '\n' ' ')
  rec apps "$apps"
  ls -la "$APPS_DIR" > "$OUT/apps-listing.txt" 2>&1
  if [ -e "$APPS_DIR/$APP_ID" ]; then res WARN P17 apps-listing "$APP_ID already in $APPS_DIR: $apps"
  else res INFO P17 apps-listing "$apps"; fi
else
  [ -f "$PRE/baseline.env" ] || usage_err "$PRE/baseline.env missing"
  [ "$(pre_val mode)" = pre ] || usage_err "$PRE is not a pre run"
  [ "$(pre_val instance)" = "$INSTANCE" ] || usage_err "$PRE is for $(pre_val instance), not $INSTANCE"
  rec pre_dir "$PRE"
  io=$(instance_of); rec instance_of "${io:-none}"
  if [ "$io" = "$APP_ID" ]; then res PASS Q01 instanceOf "$io"; else res FAIL Q01 instanceOf "'${io:-none}' != $APP_ID"; fi
  CID=()
  ids=$("$DOCKER" ps -aq --filter "label=com.docker.compose.project=$INSTANCE" 2>/dev/null)
  for id in $ids; do
    line=$("$DOCKER" inspect --format '{{.Id}}|{{index .Config.Labels "com.docker.compose.service"}}' "$id" 2>/dev/null) || continue
    CID[${line#*|}]=${line%%|*}
  done
  want_v=${APP_ID##*-}
  if health_read; then
    rec health "ok $HEALTH_V $HEALTH_C"
    if [ "$HEALTH_V" = "$want_v" ] && [ "$HEALTH_C" != - ] && [[ "$EXPECT_COMMIT" == "$HEALTH_C"* || "$HEALTH_C" == "$EXPECT_COMMIT"* ]]; then
      res PASS Q02 health "version=$HEALTH_V commit=$HEALTH_C"
    else res FAIL Q02 health "version=$HEALTH_V (want $want_v) commit=$HEALTH_C (want $EXPECT_COMMIT)"; fi
  else rec health fail; res FAIL Q02 health "GET /api/v1/health via web port failed"; fi
  if [ -n "${CID[tailscale]:-}" ]; then
    out=$("$DOCKER" exec "${CID[tailscale]}" tailscale "--socket=$TS_SOCK" status --json 2>/dev/null | in_pipe_status)
  else out="none none"; fi
  read -r bs pk <<<"${out:-none none}"
  rec backend_state "$bs"; rec nodekey_prefix "$pk"
  pk0=$(pre_val nodekey_prefix); bs0=$(pre_val backend_state); in0=$(pre_val tailscale_inode)
  if [ "$pk" != none ] && [ "$pk" = "$pk0" ]; then res PASS Q03 nodekey "unchanged $pk…"; else res FAIL Q03 nodekey "pre=$pk0 now=$pk"; fi
  inode=$(stat -c %i -- "$INST_DIR/data/tailscale" 2>/dev/null); rec tailscale_inode "${inode:-none}"
  if [ -n "$inode" ] && [ "$inode" = "$in0" ]; then res PASS Q04 state-inode "unchanged $inode"; else res FAIL Q04 state-inode "pre=$in0 now=${inode:-none}"; fi
  if [ "$bs" = Running ] && [ "$bs" = "$bs0" ]; then res PASS Q05 backendstate "unchanged $bs"; else res FAIL Q05 backendstate "pre=$bs0 now=$bs"; fi
  usage_check Q06
  CID=(); containers_check Q07
  # Q08/Q09/Q10 drift: /apps/<appId> master vs tag compose and the stick copy
  ac=$(sha "$APPS_DIR/$APP_ID/compose.yaml"); stc=$(sha "$STICK_BUNDLE/compose.yaml")
  rec apps_compose_sha256 "${ac:-none}"
  if [ -n "$ac" ] && [ "$ac" = "$TAG_SHA" ]; then res PASS Q08 drift-tag "/apps/$APP_ID/compose.yaml = tag $TAG_SHA"
  else res FAIL Q08 drift-tag "/apps/$APP_ID/compose.yaml ${ac:-missing} != tag $TAG_SHA"; fi
  if [ -n "$ac" ] && [ "$ac" = "$stc" ]; then res PASS Q09 drift-stick "= stick copy"
  else res FAIL Q09 drift-stick "/apps ${ac:-missing} != stick ${stc:-missing}"; fi
  # copyBundle skips SHA256SUMS, so check /apps/<appId> files against the stick's sums
  if [ -f "$STICK_BUNDLE/SHA256SUMS" ] && [ -d "$APPS_DIR/$APP_ID" ]; then
    pref="apps/$APP_ID/"
    bad=$(grep -E "^[0-9a-f]{64} [ *]$pref" "$STICK_BUNDLE/SHA256SUMS" | while read -r h f; do
      f=${f#\*}; rel=${f#"$pref"}
      [ "$(sha "$APPS_DIR/$APP_ID/$rel")" = "$h" ] || echo "$rel"
    done | head -5 | tr '\n' ' ')
    if [ -z "$bad" ]; then res PASS Q10 apps-files "/apps/$APP_ID matches stick SHA256SUMS"
    else res FAIL Q10 apps-files "differ from stick SHA256SUMS: $bad"; fi
  else res FAIL Q10 apps-files "missing $STICK_BUNDLE/SHA256SUMS or $APPS_DIR/$APP_ID"; fi
  # Q11 snapshot: names only, never contents
  if [ ! -d "$SNAP_DIR" ]; then res FAIL Q11 snapshot-no-secrets "no $SNAP_DIR"
  elif ! find "$SNAP_DIR" -maxdepth 4 -print >/dev/null 2>&1; then res FAIL Q11 snapshot-no-secrets "cannot list $SNAP_DIR (permission); check with Atlas"
  else
    find "$SNAP_DIR" -maxdepth 3 -printf '%y %P\n' 2>/dev/null | sort > "$OUT/pre-update-listing.txt"
    hits=$(find "$SNAP_DIR" -maxdepth 5 \( -path '*/data/tailscale' -o -path '*/data/keys' -o -path '*/data/tailscale-run' -o -name tailscaled.state -o -name pull_key \) -printf '%P ' 2>/dev/null)
    complete=no; [ -e "$SNAP_DIR/COMPLETE" ] && complete=yes
    if [ -z "$hits" ]; then res PASS Q11 snapshot-no-secrets "no data/tailscale, data/keys, data/tailscale-run (COMPLETE=$complete)"
    else res FAIL Q11 snapshot-no-secrets "snapshot holds: $hits"; fi
  fi
  if [ -x "$INST_DIR/data/tailscale" ]; then
    if [ -e "$INST_DIR/data/tailscale/authkey-join-blocked" ]; then res FAIL Q12 no-join-marker "authkey-join-blocked present"
    else res PASS Q12 no-join-marker "no authkey-join-blocked"; fi
  else res WARN Q12 no-join-marker "data/tailscale not listable as $(id -un); not checked"; fi
fi

evidence_scan
say "== $MODE: $FAILS FAIL; evidence $OUT"
[ "$FAILS" = 0 ]
