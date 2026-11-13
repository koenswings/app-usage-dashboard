"""idea#461: concurrent GET /overview must not 500 (SQLITE_MISUSE).

On production idea at 15:41:22 CET on 2026-11-12, login fired overlapping
GET /api/v1/weeks/2026-11-09/overview requests on the collector's one
shared sqlite3.Connection. One returned 500; stderr was
'api error: bad parameter or other API misuse'. The next request, 8ms
later, was 200. 1.5 gives each HTTP request its own connection.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from collector.src import api, db
from test_api import WEEK, install_fixture


class OverviewConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "usage.sqlite")
        self.conn = db.connect(self.db_path)
        install_fixture(self.conn, os.path.join(self.tmp, "registry.json"))
        os.environ.pop("IDEA_USAGE_ADMIN_PASSWORD", None)
        os.environ.pop("IDEA_USAGE_OPERATORS", None)
        os.environ["IDEA_USAGE_KOEN_PASSWORD"] = "koen911!"
        os.environ["IDEA_USAGE_MARCO_PASSWORD"] = "marco911!"
        os.environ["IDEA_USAGE_PBKDF2_ITERATIONS"] = "1000"
        os.environ["IDEA_USAGE_OPERATORS_FILE"] = os.path.join(self.tmp, "operators.json")
        os.environ["IDEA_USAGE_SESSION_SECRET"] = "test-secret"

    def tearDown(self):
        self.conn.close()

    def test_shared_connection_concurrent_overview_is_misuse(self):
        """Reproduces the production 500: two threads, one connection."""
        errors: list[BaseException] = []
        n = 8
        barrier = threading.Barrier(n)

        def worker():
            barrier.wait()
            try:
                for _ in range(20):
                    api.handle(
                        self.conn,
                        "GET",
                        "/api/v1/weeks/%s/overview" % WEEK,
                        None,
                        "koen",
                        False,
                    )
            except Exception as exc:  # noqa: BLE001 — the bug surfaces as several types
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertTrue(
            any(
                isinstance(exc, sqlite3.Error)
                or "misuse" in str(exc).lower()
                or "locked" in str(exc).lower()
                for exc in errors
            ),
            "expected SQLITE_MISUSE (or a torn read) on a shared connection; got %r"
            % [repr(e) for e in errors],
        )

    def test_serve_concurrent_overview_returns_200(self):
        """The 1.5 server opens a connection per request, so overlaps are 200."""
        server = api.serve(self.conn, "127.0.0.1:0")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            base = "http://%s:%s" % (host, port)
            opener = build_opener(HTTPCookieProcessor(CookieJar()))
            req = Request(
                base + "/api/v1/session",
                data=b'{"username":"koen","password":"koen911!"}',
                method="POST",
            )
            req.add_header("Content-Type", "application/json")
            with opener.open(req) as resp:
                self.assertEqual(resp.status, 200)

            results: list[tuple[int, dict]] = []

            def worker():
                r = Request(base + "/api/v1/weeks/%s/overview" % WEEK, method="GET")
                try:
                    with opener.open(r) as resp:
                        import json
                        results.append((resp.status, json.loads(resp.read().decode())))
                except HTTPError as exc:
                    import json
                    results.append((exc.code, json.loads(exc.read().decode())))

            n = 12
            barrier = threading.Barrier(n)

            def gated():
                barrier.wait()
                worker()

            threads = [threading.Thread(target=gated) for _ in range(n)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)
            self.assertEqual(len(results), n, results)
            self.assertTrue(all(status == 200 for status, _ in results), results)
            self.assertFalse(any(status == 500 for status, _ in results))
        finally:
            server.shutdown()
            server.server_close()

    def test_sqlite_misuse_is_503_with_retry_after(self):
        import json

        server = api.serve(self.conn, "127.0.0.1:0")
        threading.Thread(target=server.serve_forever, daemon=True).start()
        host, port = server.server_address
        base = "http://%s:%s" % (host, port)
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        req = Request(
            base + "/api/v1/session",
            data=b'{"username":"koen","password":"koen911!"}',
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        with opener.open(req) as resp:
            self.assertEqual(resp.status, 200)

        real = api.handle

        def boom(*_a, **_k):
            raise sqlite3.ProgrammingError("bad parameter or other API misuse")

        api.handle = boom
        try:
            r = Request(base + "/api/v1/weeks/%s/overview" % WEEK, method="GET")
            try:
                with opener.open(r) as resp:
                    status, payload, headers = resp.status, json.loads(resp.read().decode()), resp.headers
            except HTTPError as exc:
                status, payload, headers = exc.code, json.loads(exc.read().decode()), exc.headers
            self.assertEqual(status, 503, payload)
            self.assertEqual(payload["error"]["code"], "unavailable")
            self.assertEqual(payload["error"]["message"], "Temporarily busy")
            self.assertEqual(headers.get("Retry-After"), "1")
        finally:
            api.handle = real
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
