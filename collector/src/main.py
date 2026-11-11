"""Collector process: HTTP API + uplink poll + E1 pull + sidecar watchdog."""
from __future__ import annotations

import http.client
import json
import os
import socket
import sys
import threading
import time
from datetime import date, timedelta, timezone
from typing import Any

from . import auth
from . import db
from . import identity as identitymod
from . import presence as presence_mod
from .api import serve
from .pull import handle_pull, record_uplink


# Shared with the sidecar via ./data/tailscale-run — not the state dir (node key).
DEFAULT_TS_SOCKET = "/var/run/tailscale/tailscaled.sock"
# Only request a sidecar restart after this long continuously un-Running / unreachable.
DEFAULT_RESTART_AFTER_S = 600
DEFAULT_RESTART_MIN_INTERVAL_S = 600
# How often the collector itself writes uplink_samples (loop, record_uplink).
# Presence samples are pulled from kits (PULL_ONLINE_INTERVAL_S); there is no
# collector-side presence sampling interval. The startup-gap threshold is
# 2 * this uplink interval (idea#414 / #445).
DEFAULT_UPLINK_INTERVAL_S = 300
GAP_COLLECTOR_OFFLINE = "collector-offline"
LOCALAPI_HOST = "local-tailscaled.sock"


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def uplink_interval_s() -> int:
    """Configured uplink sample interval, seconds (env UPLINK_INTERVAL_S)."""
    value = env_int("UPLINK_INTERVAL_S", DEFAULT_UPLINK_INTERVAL_S)
    return value if value > 0 else DEFAULT_UPLINK_INTERVAL_S


def startup_gap_threshold_s() -> int:
    """Two uplink sample intervals. A missed pair of samples is an outage."""
    return 2 * uplink_interval_s()


def socket_path() -> str:
    return os.environ.get("TS_SOCKET") or DEFAULT_TS_SOCKET


def restart_flag_path(sock: str | None = None) -> str:
    override = os.environ.get("TS_RESTART_FLAG")
    if override:
        return override
    return os.path.join(os.path.dirname(sock or socket_path()), "restart-requested")


class UnixHTTPConnection(http.client.HTTPConnection):
    """HTTP/1.1 over a unix socket, with Host: local-tailscaled.sock like the Tailscale CLI."""

    def __init__(self, path: str, timeout: float = 5):
        super().__init__(LOCALAPI_HOST, timeout=timeout)
        self._unix_path = path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(self.timeout)
            sock.connect(self._unix_path)
        except OSError:
            sock.close()
            raise
        self.sock = sock


def localapi_status(sock: str) -> tuple[dict[str, Any] | None, str | None]:
    """GET /localapi/v0/status over the sidecar unix socket.

    Returns (status, error). error is set when the socket is unreachable or
    the response is not usable JSON.
    """
    conn = None
    try:
        conn = UnixHTTPConnection(sock, timeout=5)
        conn.request(
            "GET",
            "/localapi/v0/status",
            headers={
                "Host": LOCALAPI_HOST,
                "Sec-Tailscale": "localapi",
            },
        )
        resp = conn.getresponse()
        body = resp.read()
        if resp.status != 200:
            return None, "localapi HTTP %s" % resp.status
        return json.loads(body.decode("utf-8")), None
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)
    finally:
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass


def request_sidecar_restart(flag_path: str) -> None:
    directory = os.path.dirname(flag_path) or "."
    os.makedirs(directory, exist_ok=True)
    with open(flag_path, "w", encoding="utf-8") as fh:
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


def latest_sample_time(conn):
    """Latest timestamp across the sample tables used for presence and uplink.

    Returns a timezone-aware datetime, or None when the store has no samples
    (a fresh or empty DB).
    """
    times = []
    for sql in (
        "SELECT MAX(ts) FROM presence_samples",
        "SELECT MAX(timestamp) FROM uplink_samples",
    ):
        row = conn.execute(sql).fetchone()
        if row and row[0]:
            times.append(presence_mod.parse_ts(row[0]))
    return max(times) if times else None


def record_startup_outage_gap(conn, now=None, threshold_s: int | None = None) -> str | None:
    """If the last sample is older than the gap threshold, record a closed gap.

    The gap threshold is two uplink sample intervals
    (``2 * UPLINK_INTERVAL_S``, default 2 * 300 = 600 s). Presence is
    pulled from kits and has no collector-side sampling interval, so the
    uplink interval is the one used. Idempotent: does nothing on a fresh
    empty DB, when the last sample is still recent, when a gap is already
    open (the open start is backdated if it is later than the last sample),
    or when an existing row already overlaps the interval (a quick second
    restart). Returns the reason when a new row is inserted, else None.
    """
    if threshold_s is None:
        threshold_s = startup_gap_threshold_s()
    if now is None:
        now_dt = presence_mod.parse_ts(db.now_rfc3339())
    elif isinstance(now, str):
        now_dt = presence_mod.parse_ts(now)
    else:
        now_dt = now
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
    last = latest_sample_time(conn)
    if last is None:
        return None
    if (now_dt - last).total_seconds() < threshold_s:
        return None
    start_s = presence_mod.rfc3339(last)
    end_s = presence_mod.rfc3339(now_dt)

    open_row = conn.execute(
        "SELECT id, start FROM collector_gaps WHERE end IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if open_row:
        open_start = presence_mod.parse_ts(open_row["start"])
        if open_start > last:
            conn.execute(
                "UPDATE collector_gaps SET start = ? WHERE id = ?",
                (start_s, open_row["id"]),
            )
            conn.commit()
        return None

    for row in conn.execute("SELECT start, end FROM collector_gaps"):
        g0 = presence_mod.parse_ts(row["start"])
        g1 = presence_mod.parse_ts(row["end"]) if row["end"] else now_dt
        if g0 < now_dt and g1 > last:
            return None

    conn.execute(
        "INSERT INTO collector_gaps(start, end, reason) VALUES (?, ?, ?)",
        (start_s, end_s, GAP_COLLECTOR_OFFLINE),
    )
    conn.commit()
    print(
        "collector: recorded startup outage gap from %s to %s (%s)"
        % (start_s, end_s, GAP_COLLECTOR_OFFLINE),
        file=sys.stderr,
        flush=True,
    )
    return GAP_COLLECTOR_OFFLINE


def backend_state(status: dict[str, Any] | None) -> str:
    if not status:
        return ""
    return str(status.get("BackendState") or status.get("backendState") or "")


def is_logged_out(status: dict[str, Any] | None) -> bool:
    """NeedsLogin or an explicit logged-out status. Never treat this as a restart/join trigger."""
    if not status:
        return False
    if backend_state(status) == "NeedsLogin":
        return True
    if status.get("LoggedOut") is True:
        return True
    return False


def decide_sidecar_action(
    status: dict[str, Any] | None,
    error: str | None,
    now: float,
    bad_since: float | None,
    last_restart_at: float,
    restart_after_s: int = DEFAULT_RESTART_AFTER_S,
    restart_min_interval_s: int = DEFAULT_RESTART_MIN_INTERVAL_S,
) -> dict[str, Any]:
    """Pure watchdog policy for one loop tick.

    Never request a restart while BackendState is Running. Never request a
    restart or a join when the node is NeedsLogin / logged out. On a status
    error or a non-Running state, only request a restart after restart_after_s
    of continuous failure, rate-limited by restart_min_interval_s.
    """
    logged_out = is_logged_out(status)
    state = backend_state(status)
    running = bool(status) and state == "Running" and not logged_out

    if logged_out:
        return {
            "running": False,
            "logged_out": True,
            "open_gap_reason": "sidecar-logged-out",
            "close_gap": False,
            "request_restart": False,
            "record_uplink": False,
            "bad_since": None,
            "log": (
                "sidecar LocalAPI reports BackendState=%s (logged out); "
                "not restarting and not joining — a rejoin needs a new single-use key"
                % (state or "logged-out")
            ),
        }

    if running:
        return {
            "running": True,
            "logged_out": False,
            "open_gap_reason": None,
            "close_gap": True,
            "request_restart": False,
            "record_uplink": True,
            "bad_since": None,
            "log": None,
        }

    new_bad_since = bad_since if bad_since is not None else now
    elapsed = now - new_bad_since
    since_restart = (now - last_restart_at) if last_restart_at else restart_min_interval_s
    request = elapsed >= restart_after_s and since_restart >= restart_min_interval_s
    # After a restart request, reset the window so the next one waits another interval.
    next_bad_since = now if request else new_bad_since
    detail = error or ("BackendState=" + (state or "unknown"))
    if request:
        log = "sidecar %s for %ss; requesting restart (rate-limited)" % (detail, int(elapsed))
    else:
        log = "sidecar %s; backing off (restart only after %ss unreachable or non-Running)" % (
            detail, restart_after_s,
        )
    return {
        "running": False,
        "logged_out": False,
        "open_gap_reason": "sidecar-offline",
        "close_gap": False,
        "request_restart": request,
        "record_uplink": False,
        "bad_since": next_bad_since,
        "log": log,
    }


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


def backup_dir_from_env() -> str:
    return os.path.join(os.environ.get("DATA_DIR") or "/data", "backup")


def loop(conn, stop_event: threading.Event | None = None, pull_fn=None,
         backup_dir: str | None = None, snapshot_fn=None) -> None:
    poll_s = env_int("POLL_INTERVAL_S", 60)
    uplink_s = uplink_interval_s()
    pull_s = env_int("PULL_ONLINE_INTERVAL_S", 21600)
    restart_after_s = env_int("SIDECAR_RESTART_AFTER_S", DEFAULT_RESTART_AFTER_S)
    restart_min_interval_s = env_int("SIDECAR_RESTART_MIN_INTERVAL_S", DEFAULT_RESTART_MIN_INTERVAL_S)
    blip_s = env_int("IDENTITY_BLIP_S", identitymod.DEFAULT_IDENTITY_BLIP_S)
    blip_polls = identitymod.env_blip_polls()
    blip_poll_s = env_int("IDENTITY_BLIP_POLL_S", identitymod.DEFAULT_IDENTITY_BLIP_POLL_S)
    sock = socket_path()
    flag_path = restart_flag_path(sock)
    state_file = identitymod.env_state_file()
    ident = identitymod.IdentityState()
    key = os.environ.get("PULL_KEY") or "/data/keys/pull_key"
    socks = os.environ.get("TS_SOCKS5")
    pull = pull_fn or handle_pull
    last_uplink = 0.0
    last_pull: dict[str, float] = {}
    retries: dict[str, list[float]] = {}
    bad_since: float | None = None
    last_restart_at = 0.0
    fail_streak = 0
    snap_dir = backup_dir if backup_dir is not None else backup_dir_from_env()
    take_snap = snapshot_fn or (lambda c: db.maybe_daily_snapshot(c, snap_dir))

    while True:
        if stop_event is not None and stop_event.is_set():
            return
        try:
            take_snap(conn)
        except Exception as exc:
            print("collector: daily snapshot failed: %s" % exc, file=sys.stderr, flush=True)
        status, error = localapi_status(sock)
        now = time.time()
        ident_decision = identitymod.decide_identity(
            status, error, now, ident,
            blip_s=blip_s,
            blip_polls=blip_polls,
            stamp=identitymod.state_stamp(state_file),
        )
        if ident_decision.log:
            print("collector: %s" % ident_decision.log, file=sys.stderr, flush=True)
        if ident_decision.fail_closed:
            if ident_decision.gap_reason:
                open_collector_gap(conn, ident_decision.gap_reason)
            # Fail closed: never request a restart or a join. Keep serving
            # last-good API data. Do not close an identity / logged-out gap.
            fail_streak += 1
            sleep_s = poll_s
            if stop_event is not None and stop_event.wait(sleep_s):
                return
            if stop_event is None:
                time.sleep(sleep_s)
            continue
        decision = decide_sidecar_action(
            status, error, now, bad_since, last_restart_at,
            restart_after_s=restart_after_s,
            restart_min_interval_s=restart_min_interval_s,
        )
        bad_since = decision["bad_since"]
        if decision["log"]:
            print("collector: %s" % decision["log"], file=sys.stderr, flush=True)
        if decision["open_gap_reason"]:
            open_collector_gap(conn, decision["open_gap_reason"])
        if decision["close_gap"]:
            close_collector_gap(conn)
        if decision["request_restart"]:
            request_sidecar_restart(flag_path)
            last_restart_at = now
        if not decision["running"]:
            fail_streak += 1
            if ident_decision.in_blip:
                sleep_s = max(1, blip_poll_s)
            else:
                sleep_s = poll_s if not error else min(60, poll_s * (2 ** min(fail_streak - 1, 5)))
            if stop_event is not None and stop_event.wait(sleep_s):
                return
            if stop_event is None:
                time.sleep(sleep_s)
            continue
        fail_streak = 0
        if decision["record_uplink"] and now - last_uplink >= uplink_s:
            last_uplink = now
            ts = db.now_rfc3339()
            for kit in conn.execute("SELECT * FROM kits"):
                online, last_seen, via = peer_online(status or {}, kit["tailscale_name"])
                flip = record_uplink(conn, kit["engine"], ts, online, last_seen, via, None)
                conn.commit()
                if flip == "online":
                    retries[kit["engine"]] = [now + 60, now + 300, now + 900]
                    if os.path.isfile(key):
                        since = (date.today() - timedelta(days=14)).isoformat()
                        pull(conn, kit["engine"], kit["tailscale_name"], key, since, socks=socks)
                        last_pull[kit["engine"]] = now
            if os.path.isfile(key):
                for kit in conn.execute("SELECT * FROM kits"):
                    online, _, _ = peer_online(status or {}, kit["tailscale_name"])
                    if not online:
                        continue
                    due_retry = any(now >= t for t in retries.get(kit["engine"], []))
                    due_slow = now - last_pull.get(kit["engine"], 0) >= pull_s
                    if due_retry or due_slow:
                        retries[kit["engine"]] = [t for t in retries.get(kit["engine"], []) if now < t]
                        since = (date.today() - timedelta(days=14)).isoformat()
                        result = pull(conn, kit["engine"], kit["tailscale_name"], key, since, socks=socks)
                        if result == "success" or result == "disabled":
                            last_pull[kit["engine"]] = now
                            retries.pop(kit["engine"], None)
        if stop_event is not None and stop_event.wait(poll_s):
            return
        if stop_event is None:
            time.sleep(poll_s)


def main() -> int:
    data_dir = os.environ.get("DATA_DIR") or "/data"
    os.makedirs(data_dir, exist_ok=True)
    if not os.environ.get("IDEA_USAGE_OPERATORS_FILE"):
        os.environ["IDEA_USAGE_OPERATORS_FILE"] = os.path.join(data_dir, "operators.json")
    auth.ensure_operators()
    db_path = os.path.join(data_dir, "usage.sqlite")
    conn = db.connect(db_path)
    db.load_registry(conn, os.environ.get("REGISTRY_PATH") or os.path.join(data_dir, "registry.json"))
    # Whole-hub outages (collector was down) must show as a collectorGap.
    # The watchdog can only open a gap while the process is running.
    record_startup_outage_gap(conn)
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
