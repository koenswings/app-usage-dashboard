# collector

Owner: Kid, idea#414.

Python service. Modules live in `src/`:

- `db.py` — SQLite WAL schema (§7.5) and dated daily VACUUM INTO copies under `./data/backup/daily/`
- `backup_hook.py` — idea#444 preHook / postHook dump and start-time restore from `./data/backup/usage.sqlite`
- `parse.py` — `idea-usage-export` NDJSON (`since`); exit 10 is `disabled`, not an error
- `presence.py` — `on` / `off` / `gapUnknown` from kit samples; `collectorGap` from the sidecar watchdog
- `pull.py` — restricted SSH `since` / `archive-and-clear --before`
- `aggregate.py` — week views and scorecard inputs
- `thresholds.py` — U-7 defaults, validation, SQLite settings, and amber/unused streaks
- `auth.py` — cookie sessions and the two U-9 operators (`koen`, `marco`), hashed in `./data/operators.json`
- `api.py` — `/api/v1` (`idea-usage-api/1`)
- `main.py` — process loop (LocalAPI over the shared unix socket; watchdog backs off and never restarts a Running or NeedsLogin sidecar)

`sidecar-wrap.sh` restarts `containerboot` when the collector writes `restart-requested` in the shared socket dir (`./data/tailscale-run`), never in the state dir (`./data/tailscale`). A restart is requested only after LocalAPI has been unreachable or BackendState non-Running for 10 minutes, and never when BackendState is Running, NeedsLogin, or the node is logged out. After SIGTERM the wrapper waits `TS_RESTART_TERM_S` seconds (default 15), then SIGCONTs and SIGKILLs the containerboot process group (and tailscaled if it left the group) so a SIGSTOPped tailscaled cannot pin `wait` forever. The state file is never copied, moved, or deleted.
The collector stays root because live `./data` (sqlite, keys) is root-owned; changing the user would require a chown of that volume.
