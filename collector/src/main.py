"""Collector process: HTTP API + uplink poll + E1 pull + sidecar watchdog."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

from . import db
from .api import serve
from .pull import handle_pull, record_uplink


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def localapi_status(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url.rstrip("/") + "/localapi/v0/status")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def request_sidecar_restart(state_dir: str) -> None:
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, "restart-requested")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("1\n")


def open_collector_gap(conn, reason: str) -> None:
    open_row = conn.execute("SELECT id FROM collector_gaps WHERE end IS NULL ORDER BY id DESC LIMIT 1").fetchone()
    if open_row:
        return
    conn.execute(
        "INSERT INTO collector_gaps(start, end, reason) VALUES (?, NULL, ?)",
        (db.now_rfc3339(), reason),
    )
    conn.commit()


def close_collector_gap(conn) -> None:
    conn.execute(
        "UPDATE collector_gaps SET end = ? WHERE end IS NULL",
        (db.now_rfc3339(),),
    )
    conn.commit()


def peer_online(status: dict, tailscale_name: str) -> tuple[bool, str | None, str | None]:
    peers = status.get("Peer") or status.get("peer") or {}
    if isinstance(peers, dict):
        iterable = peers.values()
    else:
        iterable = peers
    for peer in iterable:
        dns = (peer.get("DNSName") or peer.get("HostName") or peer.get("Name") or "").split(".")[0]
        host = peer.get("HostName") or ""
        if tailscale_name in (dns, host, peer.get("DNSName")):
            online = bool(peer.get("Online"))
            last_seen = peer.get("LastSeen")
            via = "DERP" if peer.get("Relay") and not peer.get("CurAddr") else ("direct" if peer.get("CurAddr") else None)
            if peer.get("Relay") and not online:
                via = "DERP"
            return online, last_seen, via
    return False, None, None


def loop(conn) -> None:
    poll_s = env_int("POLL_INTERVAL_S", 60)
    uplink_s = env_int("UPLINK_INTERVAL_S", 300)
    pull_s = env_int("PULL_ONLINE_INTERVAL_S", 21600)
    localapi = os.environ.get("TS_LOCALAPI") or "http://127.0.0.1:8384"
    socks = os.environ.get("TS_SOCKS5")
    key = os.environ.get("PULL_KEY") or "/data/keys/pull_key"
    state_dir = os.environ.get("TS_STATE_DIR") or "/data/tailscale"
    last_uplink = 0.0
    last_pull: dict[str, float] = {}
    retries: dict[str, list[float]] = {}

    while True:
        status = localapi_status(localapi)
        self = (status or {}).get("Self") or {}
        self_online = bool(self.get("Online")) if status else False
        if not status or not self_online:
            open_collector_gap(conn, "sidecar-offline")
            request_sidecar_restart(state_dir)
            time.sleep(poll_s)
            continue
        close_collector_gap(conn)
        now = time.time()
        if now - last_uplink >= uplink_s:
            last_uplink = now
            ts = db.now_rfc3339()
            for kit in conn.execute("SELECT * FROM kits"):
                online, last_seen, via = peer_online(status, kit["tailscale_name"])
                flip = record_uplink(conn, kit["engine"], ts, online, last_seen, via, None)
                conn.commit()
                if flip == "online":
                    retries[kit["engine"]] = [now + 60, now + 300, now + 900]
                    if os.path.isfile(key):
                        since = (date.today() - timedelta(days=14)).isoformat()
                        handle_pull(conn, kit["engine"], kit["tailscale_name"], key, since, socks=socks)
                        last_pull[kit["engine"]] = now
            # periodic pull while online
            if os.path.isfile(key):
                for kit in conn.execute("SELECT * FROM kits"):
                    online, _, _ = peer_online(status, kit["tailscale_name"])
                    if not online:
                        continue
                    due_retry = any(now >= t for t in retries.get(kit["engine"], []))
                    due_slow = now - last_pull.get(kit["engine"], 0) >= pull_s
                    if due_retry or due_slow:
                        retries[kit["engine"]] = [t for t in retries.get(kit["engine"], []) if now < t]
                        since = (date.today() - timedelta(days=14)).isoformat()
                        result = handle_pull(conn, kit["engine"], kit["tailscale_name"], key, since, socks=socks)
                        if result == "success" or result == "disabled":
                            last_pull[kit["engine"]] = now
                            retries.pop(kit["engine"], None)
        time.sleep(poll_s)


def main() -> int:
    data_dir = os.environ.get("DATA_DIR") or "/data"
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "usage.sqlite")
    conn = db.connect(db_path)
    db.load_registry(conn, os.environ.get("REGISTRY_PATH") or os.path.join(data_dir, "registry.json"))
    bind = os.environ.get("COLLECTOR_BIND") or "0.0.0.0:8080"
    server = serve(conn, bind)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print("collector listening on %s" % bind, file=sys.stderr)
    if os.environ.get("IDEA_USAGE_ONCE") == "1":
        thread.join()
        return 0
    try:
        loop(conn)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
