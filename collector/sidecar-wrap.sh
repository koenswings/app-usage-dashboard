#!/bin/sh
# Watchdog-friendly wrapper around Tailscale containerboot.
# The collector writes $TS_STATE_DIR/restart-requested when Self.Online is false.
#
# A keyed join (TS_AUTHKEY set, no persisted node key) runs exactly once.
# If that attempt fails or does not reach Running (authorized) before
# TS_JOIN_TIMEOUT seconds (default 90), the wrapper writes
# $TS_STATE_DIR/authkey-join-blocked and exits non-zero without looping.
# Docker may restart the container (restart: unless-stopped); the marker
# then blocks any further keyed attempt until an operator deletes it.
# Never print TS_AUTHKEY, private keys, or AuthURL.
set -eu
STATE=${TS_STATE_DIR:-/var/lib/tailscale}
BOOT=${TS_CONTAINERBOOT:-/usr/local/bin/containerboot}
JOIN_TIMEOUT=${TS_JOIN_TIMEOUT:-90}
MARKER_NAME=authkey-join-blocked

case "$JOIN_TIMEOUT" in
  ''|*[!0-9]*) JOIN_TIMEOUT=90 ;;
esac
if [ "$JOIN_TIMEOUT" -lt 1 ]; then
  JOIN_TIMEOUT=90
fi

state_has_nodekey() {
  dir=$1
  [ -f "$dir/tailscaled.state" ] || return 1
  # Match the field name only; do not print file contents (they include private keys).
  grep -q 'PrivateNodeKey' "$dir/tailscaled.state"
}

join_blocked() {
  [ -f "$STATE/$MARKER_NAME" ]
}

write_join_blocked() {
  reason=$1
  # Reason text is wrapper-controlled. Never write env values or key material.
  {
    echo "authkey-join-blocked"
    echo "reason: $reason"
    echo "Delete this file before another keyed start."
    echo "Do not reuse a key that already failed (including a tags rejection); mint a new single-use key."
  } > "$STATE/$MARKER_NAME"
}

allow_start() {
  if state_has_nodekey "$STATE"; then
    return 0
  fi
  if join_blocked; then
    return 1
  fi
  if [ -n "${TS_AUTHKEY:-}" ]; then
    return 0
  fi
  return 1
}

refuse_message() {
  if join_blocked && ! state_has_nodekey "$STATE"; then
    echo "sidecar-wrap: refusing to start: a previous keyed join wrote $STATE/$MARKER_NAME" >&2
    echo "sidecar-wrap: delete that marker before trying another key, or move existing idea-hub state into place" >&2
    return
  fi
  echo "sidecar-wrap: refusing to start: no persisted node key in $STATE and TS_AUTHKEY is empty" >&2
}

is_running_authorized() {
  # Never print status (it can include AuthURL). Require BackendState
  # Running and a sign the node is authorized (Online or a 100.x address).
  # Cap the CLI at 2s so a stuck `tailscale status` cannot disable the
  # join timeout. Tests may set TS_TAILSCALE to a fake binary.
  ts=${TS_TAILSCALE:-tailscale}
  if command -v timeout >/dev/null 2>&1; then
    status=$(timeout 2 "$ts" --socket=/tmp/tailscaled.sock status --json 2>/dev/null) || return 1
  else
    status=$("$ts" --socket=/tmp/tailscaled.sock status --json 2>/dev/null) || return 1
  fi
  printf '%s' "$status" | grep -Eq '"BackendState":[[:space:]]*"Running"' || return 1
  if printf '%s' "$status" | grep -Eq '"Online":[[:space:]]*true'; then
    return 0
  fi
  printf '%s' "$status" | grep -Eq '"TailscaleIPs":[^]]*100\.' || return 1
  return 0
}

watch_boot() {
  pid=$1
  while kill -0 "$pid" 2>/dev/null; do
    if [ -f "$STATE/restart-requested" ]; then
      echo "sidecar-wrap: restart requested by collector watchdog" >&2
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      return 0
    fi
    sleep 2
  done
  wait "$pid" 2>/dev/null || true
}

keyed_join_once() {
  echo "sidecar-wrap: starting one keyed join attempt (will not retry this key)" >&2
  "$BOOT" &
  JOIN_PID=$!
  i=0
  while kill -0 "$JOIN_PID" 2>/dev/null; do
    if is_running_authorized; then
      echo "sidecar-wrap: keyed join reached Running" >&2
      return 0
    fi
    i=$((i + 1))
    if [ "$i" -ge "$JOIN_TIMEOUT" ]; then
      echo "sidecar-wrap: keyed join timed out after ${JOIN_TIMEOUT}s" >&2
      write_join_blocked "timed out after ${JOIN_TIMEOUT}s waiting for Running"
      kill "$JOIN_PID" 2>/dev/null || true
      wait "$JOIN_PID" 2>/dev/null || true
      return 1
    fi
    sleep 1
  done
  wait "$JOIN_PID" 2>/dev/null || true
  if is_running_authorized; then
    echo "sidecar-wrap: keyed join reached Running" >&2
    return 0
  fi
  echo "sidecar-wrap: keyed join exited before the node was Running" >&2
  write_join_blocked "join attempt exited before the node was Running"
  return 1
}

if [ "${1:-}" = "--check-state" ]; then
  if [ -n "${2:-}" ]; then
    STATE=$2
  fi
  if allow_start; then
    exit 0
  fi
  refuse_message
  exit 1
fi

mkdir -p "$STATE"
if ! allow_start; then
  refuse_message
  if ! join_blocked; then
    echo "sidecar-wrap: move existing idea-hub state into place, or set TS_AUTHKEY for a one-time join" >&2
  fi
  # Stay up briefly so compose does not tight-loop; exit non-zero after.
  sleep 3600
  exit 1
fi

if [ ! -x "$BOOT" ]; then
  echo "sidecar-wrap: containerboot not found at $BOOT" >&2
  # Keep the container up so compose does not flap while the image is inspected.
  sleep 3600
  exit 1
fi

JOIN_PID=""
if [ -n "${TS_AUTHKEY:-}" ] && ! state_has_nodekey "$STATE"; then
  if ! keyed_join_once; then
    exit 1
  fi
  if [ -n "$JOIN_PID" ] && kill -0 "$JOIN_PID" 2>/dev/null; then
    watch_boot "$JOIN_PID"
  fi
fi

while true; do
  rm -f "$STATE/restart-requested"
  "$BOOT" &
  pid=$!
  watch_boot "$pid"
  sleep 2
done
