#!/bin/sh
set -eu
need_pkgs=0
command -v ssh >/dev/null 2>&1 || need_pkgs=1
[ -f /usr/share/zoneinfo/Europe/Brussels ] || need_pkgs=1
if [ "$need_pkgs" = 1 ]; then
  apt-get update
  apt-get install -y --no-install-recommends openssh-client netcat-openbsd tzdata
  rm -rf /var/lib/apt/lists/*
fi
mkdir -p /data/keys /data/backup /data/tailscale
chmod 700 /data/keys || true
if [ -f /data/keys/pull_key ]; then
  chmod 600 /data/keys/pull_key || true
fi
export PYTHONPATH=/app
exec python3 -m src.main
