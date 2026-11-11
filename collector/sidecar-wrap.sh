#!/bin/sh
# Watchdog-friendly wrapper around Tailscale containerboot.
# The collector writes $TS_STATE_DIR/restart-requested when Self.Online is false.
set -eu
STATE=${TS_STATE_DIR:-/var/lib/tailscale}

state_has_nodekey() {
  dir=$1
  [ -f "$dir/tailscaled.state" ] || return 1
  # Match the field name only; do not print file contents (they include private keys).
  grep -q 'PrivateNodeKey' "$dir/tailscaled.state"
}

allow_start() {
  if state_has_nodekey "$STATE"; then
    return 0
  fi
  if [ -n "${TS_AUTHKEY:-}" ]; then
    return 0
  fi
  return 1
}

if [ "${1:-}" = "--check-state" ]; then
  if [ -n "${2:-}" ]; then
    STATE=$2
  fi
  if allow_start; then
    exit 0
  fi
  echo "sidecar-wrap: refusing to start: no persisted node key in $STATE and TS_AUTHKEY is empty" >&2
  exit 1
fi

mkdir -p "$STATE"
if ! allow_start; then
  echo "sidecar-wrap: refusing to start: no persisted node key in $STATE and TS_AUTHKEY is empty" >&2
  echo "sidecar-wrap: move existing idea-hub state into place, or set TS_AUTHKEY for a one-time join" >&2
  sleep 3600
  exit 1
fi

BOOT=/usr/local/bin/containerboot
if [ ! -x "$BOOT" ]; then
  echo "sidecar-wrap: containerboot not found at $BOOT" >&2
  # Keep the container up so compose does not flap while the image is inspected.
  sleep 3600
  exit 1
fi
while true; do
  rm -f "$STATE/restart-requested"
  "$BOOT" &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    if [ -f "$STATE/restart-requested" ]; then
      echo "sidecar-wrap: restart requested by collector watchdog" >&2
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      break
    fi
    sleep 2
  done
  wait "$pid" 2>/dev/null || true
  sleep 2
done
