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

- The day-file identity field is `instance`. HTTP responses also send `instanceId` as an alias of the same value.
- Census and Nextcloud `setup` come from the last `hookStatus: ok` day in the week and are not summed. Nextcloud `setup` and `logins` use singular `admin` / `teacher` / `learner` keys, each `{total, beyondSeed}`. `beyondSeed` is read from the hook; it is `null` when the hook omitted it. The collector does not invent it (no `teachers - 1` heuristic). `otherGroups` stays on Nextcloud `setup`. Kolibri HTTP `setup` is Pixel's flat `Census` (the hook's RoleCount totals are mapped into `learnersRegistered` / `teachers` / `admins`).
- Activity counters (sessions, minutes, page views, workflow events, office opens/read/edit) are summed across ok days. On a Nextcloud *instance*, weekly `office.distinctDocuments` is the last ok day's value (not a sum or max of days). Scorecard `officeDistinctDocuments` is the **sum across the school's own Nextcloud instances** (document ids are salted per instance, so two own Nextclouds hold different documents and the sum is correct). Kiwix `distinctArticles` is the max of daily counts (the export does not include the article set, so a true weekly union is not available).
- Any instance whose `clock` is present and `synced` is false marks that week untrusted (`clockTrusted` on the school-week and per-app week responses). A null clock does not taint the week.
- Stub / failed day files keep `hookStatus` (`ok` \| `timeout` \| `failed` \| `invalid` \| `skipped` \| `unlisted-no-hook` \| `no-hook`) and optional `skipReason`. App payloads on those days are treated as null; they do not overwrite an earlier ok summary.
- Nextcloud `office.byGroup` stays numeric (`{admin, teacher, learner}`), not RoleCount. `appsOpened` is an object (`{ "files": n }`). `workflows` uses `fileDropLinks` and `fileDropUploads`.
- The scorecard Nextcloud block matches Pixel's `ScorecardNextcloudInputs` (`worksheetShares`, `editShares`, `fileDropLinks`, `fileDropUploads`, `schoolFilesShares`, `officeOpens`, `officeDistinctDocuments`, `officeRead`, `officeEdit`, `officeEstimatedMinutes`). `officeDistinctDocuments` is the sum across the school's own Nextcloud instances (see above). Setup extras are `nextcloudTeacherBeyondSeed` and `nextcloudLearnerBeyondSeed` (null when the hook did not emit `beyondSeed`).
- Presence segments for a school week cover Monday 00:00 through Saturday 00:00 (the end of `weekEnd`, Friday) in kit-local offset — the same window Pixel's strip draws. They are contiguous, non-overlapping, and sum to that 5-day length. Unmeasured stretches are filled explicitly: `off` where the export shows the kit was off; `collectorGap` where a watchdog `collector_gaps` interval (sidecar down) covers the hole; `gapUnknown` otherwise. `lengthKnown` is true for measured `on`/`off` and for collector gaps that have both a start and an end; it is false for `gapUnknown` and for an open-ended collector outage.
- `presence.summary` is a short plain sentence such as `On 4 of 5 school days, 31 h in school hours`, built from `presence_days` school-hour totals. It is `null` when those roll-ups are missing. It is never an empty string.
- Uplink samples and transitions use the same offset-aware week bounds as presence. Timestamps are compared as parsed instants, not as naive `T00:00:00` strings, so `Z` and `+02:00` values near a Monday/Saturday boundary fall on the correct side.
- `GET /api/v1/weeks`.`currentWeekStart` is the latest Monday with stored data (daily summaries or presence days). `GET /api/v1/meta` adds `todayWeekStart` (today's Monday) and `currentWeekHasData` (true when at least one stored week exists). The weeks list also repeats `todayWeekStart` and `currentWeekHasData` next to `currentWeekStart`. If the store is empty, `currentWeekStart` falls back to `todayWeekStart` and `currentWeekHasData` is false.
- `port` on the instance breakdown is always null: it is not in the export.
- `KitTimezone.utcOffset` comes from the latest presence sample's RFC 3339 offset. `timeZone` is the optional IANA name from the registry; without it the label is `kit local time (UTC±n)`.
- The HTTP API is same-origin (no CORS headers). The UI is served from the same host.

## Endpoints (served by this collector)

See Pixel's `web/API.md`. Additions that are not in that draft:

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/health` | Unauthenticated. `{"ok": true, "schema": "idea-usage-api/1"}` so the Engine healthCheck can probe `${port}`. |

`GET /api/v1/session` without a cookie returns `{authenticated: false}` so the login page can ask. Every other `/api/v1` path requires the `idea_usage_session` cookie.

`GET /api/v1/meta` also returns `todayWeekStart` (Monday of today) and `currentWeekHasData`. `GET /api/v1/weeks` returns `currentWeekStart` as the latest Monday that has stored data, plus the same two fields.

Consistent snapshots use `VACUUM INTO` under `./data/backup/`, keeping 14 copies.
