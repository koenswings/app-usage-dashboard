#!/usr/bin/env bash
# verify-service-tar.sh — check that saved service image tars match their compose pins (idea#445).
#
# Usage:
#   script/verify-service-tar.sh <compose.yaml> <services-dir> [--service NAME]... [--platform-digest sha256:<hex>]
#   script/verify-service-tar.sh --tar <file.tar> --image <repo:tag@sha256:...> [--platform-digest sha256:<hex>]
#   script/verify-service-tar.sh --print-tar-name <ref>  /  --print-save-name <ref>
#
# For every digest-pinned compose image it opens
#   <services-dir>/<serviceImageTarName(ref)>   (e.g. ghcr.io_koenswings_usage-dashboard-web:1.0.tar)
# and reads index.json and manifest.json. It passes only if the entry named
# repo:tag has the pinned top-level digest (an index: digest == pin; a single
# manifest: digest == pin), the blobs needed for an offline linux/arm64 load are
# present, and manifest.json RepoTags names repo:tag. Tag-only images are skipped.
#
# Read-only: no Docker, no extraction, no writes. Exit 0 = all pass, 1 = a check
# failed (missing tar included), 2 = usage/compose error. Rules: docs/packaging.md.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
case "${1:-}" in
  -h|--help) sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
esac
exec python3 "$HERE/verify_service_tar.py" "$@"
