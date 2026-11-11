#!/bin/sh
set -eu
case "${IDEA_WEB_PORT:-}" in
  80|3333|3334|8081)
    echo "usage-dashboard: refusing to bind forbidden port ${IDEA_WEB_PORT}" >&2
    exit 1
    ;;
esac
exec nginx -g 'daemon off;'
