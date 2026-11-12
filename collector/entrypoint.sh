#!/bin/sh
set -eu
# Packages are baked into the collector image (idea#461). Never install
# anything at start: a fresh container may have no outbound DNS
# (network_mode: service:tailscale, TS_ACCEPT_DNS=false).
missing=0
command -v ssh >/dev/null 2>&1 || { echo "ERROR: ssh is not in this image; rebuild the collector image with openssh-client" >&2; missing=1; }
command -v nc >/dev/null 2>&1 || { echo "ERROR: nc is not in this image; rebuild the collector image with netcat-openbsd" >&2; missing=1; }
[ -f /usr/share/zoneinfo/Europe/Brussels ] || { echo "ERROR: /usr/share/zoneinfo/Europe/Brussels is missing; rebuild the collector image with tzdata" >&2; missing=1; }
[ "$missing" = 0 ] || exit 1
mkdir -p /data/keys /data/backup /var/run/tailscale
chmod 700 /data/keys || true
if [ -f /data/keys/pull_key ]; then
  chmod 600 /data/keys/pull_key || true
fi
export PYTHONPATH=/app
exec python3 -m src.main
