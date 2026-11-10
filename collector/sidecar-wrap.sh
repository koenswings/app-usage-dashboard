#!/bin/sh
# Watchdog-friendly wrapper around Tailscale containerboot.
# The collector writes $TS_STATE_DIR/restart-requested when Self.Online is false.
set -eu
STATE=${TS_STATE_DIR:-/var/lib/tailscale}
mkdir -p "$STATE"
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
