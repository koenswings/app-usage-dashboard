#!/usr/bin/env python3
"""Compare the on-disk idea-hub nodekey with tailscale status --json Self.PublicKey.

Never prints private keys. Prints public prefixes and match only.

Usage:
  script/check-idea-hub-nodekey.py --state-dir DIR --status-json FILE
  script/check-idea-hub-nodekey.py --state-dir DIR --socket /var/run/tailscale/tailscaled.sock
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "collector"))

from src.nodekey import compare, disk_nodekeys, status_self_public  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare persisted idea-hub nodekey to Self.PublicKey")
    parser.add_argument("--state-dir", required=True, help="Directory that holds tailscaled.state")
    parser.add_argument("--status-json", help="Path to a saved tailscale status --json file")
    parser.add_argument("--socket", help="tailscaled socket; used if --status-json is omitted")
    args = parser.parse_args(argv)

    state_path = Path(args.state_dir) / "tailscaled.state"
    if not state_path.is_file():
        print("disk_state=missing", file=sys.stderr)
        print("match=false")
        return 1

    pubs = disk_nodekeys(state_path)
    if not pubs:
        print("disk_nodekey=none", file=sys.stderr)
        print("match=false")
        return 1

    if args.status_json:
        status = json.loads(Path(args.status_json).read_text())
    elif args.socket:
        raw = subprocess.check_output(
            ["tailscale", "--socket", args.socket, "status", "--json"],
            stderr=subprocess.STDOUT,
        )
        status = json.loads(raw)
    else:
        print("error: provide --status-json or --socket", file=sys.stderr)
        return 2

    result = compare(pubs, status_self_public(status))
    print("disk_count=%d" % result["disk_count"])
    for path, prefix in result["disk_prefixes"]:
        print("disk_prefix=%s path=%s" % (prefix, path))
    print("status_prefix=%s" % result["status_prefix"])
    print("match=%s" % str(result["match"]).lower())
    return 0 if result["match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
