# collector

Owner: Kid, idea#414.

Python service. Modules live in `src/`:

- `db.py` — SQLite WAL schema (§7.5)
- `parse.py` — `idea-usage-export` NDJSON (`since`); exit 10 is `disabled`, not an error
- `presence.py` — `on` / `off` / `gapUnknown` from kit samples; `collectorGap` from the sidecar watchdog
- `pull.py` — restricted SSH `since` / `archive-and-clear --before`
- `aggregate.py` — week views and scorecard inputs
- `api.py` — `/api/v1` (`idea-usage-api/1`)
- `main.py` — process loop

`sidecar-wrap.sh` restarts `containerboot` when the collector writes `restart-requested`.
