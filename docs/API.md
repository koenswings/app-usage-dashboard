# Collector data model (idea#414)

The HTTP contract the UI calls is Pixel's `idea-usage-api/1` (`web/API.md` on `pixel/dashboard-ui-415`). This file is the collector-side model: how export records land in SQLite and how they are shaped for those endpoints.

Day-file schema: `idea-usage-day/1` (Axle, [agent-engine-dev#308](https://github.com/koenswings/agent-engine-dev/pull/308)). Export stream: NDJSON envelopes `{type: presence|day|sample, payload}` ending with `{type: end, counts, errors}`. Exit 10, empty stdout and stderr `disabled` means monitoring is off; that is stored as a kit state, not as a pull error.

## SQLite (`./data/usage.sqlite`, WAL)

| Table | Purpose |
|---|---|
| `kits` | engine, tailscale_name, school, deployment_id, optional IANA timezone, monitoring_enabled, last_pulled, note |
| `uplink_samples` | timestamp, engine, online, last_seen, via (`direct` \| `DERP` \| null), latency_ms |
| `uplink_transitions` | timestamp, engine, from_state, to_state (`online` \| `offline`) |
| `presence_samples` | raw pulled `idea-usage-presence/1` objects |
| `presence_segments` | `state` (`on` \| `off` \| `gapUnknown` \| `collectorGap`), start, end, length_known |
| `presence_days` | on_minutes, school_hours_on_minutes, boots, longest_gap_minutes, length_known |
| `daily_summaries` | engine, deployment_id, day, **instance**, app, name, demo, listed, hook_status, skip_reason, payload (full stored day file), pulled_at |
| `samples` | pulled `idea-usage-sample/1` rows (Nextcloud Office snapshots, including opaque `documentIds`) |
| `help_events` | id, deployment_id, offered_on, tutorial_chapters, note, created_by, created_at |
| `pull_log` | success, error, rejected, or **disabled** |
| `collector_gaps` | idea-side sidecar outages |

The kit files do not carry a deployment id. idea maps `(engine, day)` to `deployment_id` when a pull is stored (registry: `./data/registry.json`).

## Aggregation rules

- The day-file identity field is `instance` (not `instanceId`).
- Census (`setup` on Kolibri / Nextcloud) comes from the last `hookStatus: ok` day in the week and is not summed.
- Activity counters (sessions, minutes, page views, workflow events) are summed across ok days. `distinctArticles` is the max of daily counts (the export does not include the full article set, so a true weekly union is not available).
- Any day whose `clock.synced` is false marks that instance's week `clock.synced` false (`clockTrustworthy` on the school-week response).
- Stub / failed day files keep `hookStatus` (`ok` \| `timeout` \| `failed` \| `invalid` \| `skipped` \| `unlisted-no-hook` \| `no-hook`) and optional `skipReason`. App payloads on those days are treated as null; they do not overwrite an earlier ok summary.
- Nextcloud `office`, `setup`, `logins`, `appsOpened` and `workflows` are stored and served in the Engine shapes. Role keys are singular (`admin`, `teacher`, `learner`) on `office.byGroup` and `logins`. `setup` census fields stay `teachers` / `learners`. `appsOpened` is an object (`{ "files": n }`). `workflows` uses `fileDropLinks` and `fileDropUploads`.
- Scorecard `fileDrops` is `fileDropUploads` for the week (files received, not links created). `documentsCreatedOrEdited*` is null: the stored office object has `read` / `edit` / `distinctDocuments`, not created-vs-edited by role.
- `port` on the instance breakdown is always null: it is not in the export.
- `KitTimezone.utcOffset` comes from the latest presence sample's RFC 3339 offset. `timeZone` is the optional IANA name from the registry; without it the label is `kit local time (UTC±n)`.

## Endpoints (served by this collector)

See Pixel's `web/API.md`. Additions that are not in that draft:

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/health` | Unauthenticated. `{"ok": true, "schema": "idea-usage-api/1"}` so the Engine healthCheck can probe `${port}`. |

`GET /api/v1/session` without a cookie returns `{authenticated: false}` so the login page can ask. Every other `/api/v1` path requires the `idea_usage_session` cookie.

Consistent snapshots use `VACUUM INTO` under `./data/backup/`, keeping 14 copies.
