#!/usr/bin/env python3
"""Serve the collector API with the tests/test_api.py fixture.

Pixel can point the dashboard UI at this process (proxy /api to this origin;
the API is same-origin and does not send CORS headers).

    python3 tests/serve_fixture.py
    FIXTURE_BIND=127.0.0.1:8080 python3 tests/serve_fixture.py

Login: admin / admin911!
Four-state presence weekStart: 2026-11-02 (Nharira / dep-nharira)
  GET /api/v1/weeks/2026-11-02/schools/dep-nharira
  GET /api/v1/weeks/2026-11-02/schools/dep-nharira/presence

The original fixture week 2026-11-09 is also loaded.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import db  # noqa: E402
from src.api import serve  # noqa: E402
from test_api import FOUR_STATE_WEEK, WEEK, install_fixture  # noqa: E402


def main() -> None:
    bind = os.environ.get("FIXTURE_BIND") or "127.0.0.1:18080"
    os.environ.setdefault("IDEA_USAGE_ADMIN_PASSWORD", "admin911!")
    os.environ.setdefault("IDEA_USAGE_SESSION_SECRET", "test-secret")
    tmp = tempfile.mkdtemp(prefix="idea-usage-fixture-")
    conn = db.connect(os.path.join(tmp, "usage.sqlite"))
    install_fixture(conn, os.path.join(tmp, "registry.json"))
    server = serve(conn, bind)
    print("Fixture API listening on http://%s" % bind, flush=True)
    print("Login: admin / admin911!", flush=True)
    print("Four-state presence weekStart: %s" % FOUR_STATE_WEEK, flush=True)
    print("  GET /api/v1/weeks/%s/schools/dep-nharira" % FOUR_STATE_WEEK, flush=True)
    print("  GET /api/v1/weeks/%s/schools/dep-nharira/presence" % FOUR_STATE_WEEK, flush=True)
    print("Original fixture weekStart: %s" % WEEK, flush=True)
    print("SQLite: %s" % os.path.join(tmp, "usage.sqlite"), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    finally:
        server.server_close()
        conn.close()


if __name__ == "__main__":
    main()
