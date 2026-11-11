#!/usr/bin/env bash
# verify-service-tar.sh — check that saved service image tars match their compose pins (idea#445).
#
# Usage:
#   script/verify-service-tar.sh <compose.yaml> <services-dir> [--service NAME]...
#   script/verify-service-tar.sh --tar <file.tar> --image <repo:tag@sha256:...>
#   script/verify-service-tar.sh --print-tar-name <ref>  /  --print-save-name <ref>
#
# For every digest-pinned compose image it opens
#   <services-dir>/<serviceImageTarName(ref)>   (e.g. ghcr.io_koenswings_usage-dashboard-web:1.0.tar)
# and gives the same verdict as the Engine's pre-load check (agent-engine-dev
# #327 ImageRef.ts checkServiceTarPin): MATCH, MISMATCH (the Engine quarantines
# it), UNREADABLE (not quarantined) or MISSING. Tag-only images are SKIPped.
# A platform-manifest-only tar is always a MISMATCH (Steve, idea#445).
#
# Read-only: no Docker, no extraction, no writes. Exit codes, worst first:
# 1 = a MISMATCH, 3 = an UNREADABLE tar, 4 = a MISSING tar, 0 = all MATCH,
# 2 = usage/compose error. Rules: docs/packaging.md "Verify a service tar".
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
case "${1:-}" in
  -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
esac
exec python3 "$HERE/verify_service_tar.py" "$@"
