# Remaining differences from Pixel `b4fa49b`

The collector on `kid/i414-collector` serves `web/API.md` and `web/src/api/types.ts` as merged to `main` at [`9bdf867`](https://github.com/koenswings/app-usage-dashboard/commit/9bdf867) (Pixel #1). This note lists only what still differs from that head, plus collector-side additions. Mapped already (not listed below): singular `admin` / `teacher` / `learner` as `{total, beyondSeed}` on Nextcloud `setup` and `logins`; `otherGroups` on `setup`; `instance` plus `instanceId` as an alias; `clockTrusted`; census and Nextcloud `setup` from the last ok day; null app payloads on stub days; scorecard `nextcloudTeacherBeyondSeed` / `nextcloudLearnerBeyondSeed` read from the hook (null when absent); scorecard Nextcloud office and workflow fields as in `ScorecardNextcloudInputs`.

## `port` is always null

`DiscoveredInstance.port` is not in the Engine export. Every instance on `GET /api/v1/weeks/{weekStart}/schools/{deploymentId}/instances` sends `"port": null`.

## Scorecard document-edit fields

`b4fa49b` dropped `documentsCreatedOrEditedTeachers` / `documentsCreatedOrEditedLearners`. The collector still does not invent a created-versus-edited-by-role reduction. It serves the `office*` counters on `ScorecardNextcloudInputs` (`officeOpens`, `officeDistinctDocuments`, `officeRead`, `officeEdit`, `officeEstimatedMinutes`) from the stored office object.

Steve's U-7 line 5 decision: Nextcloud actions that count are by a teacher or learner, not an admin. The scorecard sends these collector-side splits, keeping the flat totals:

- `officeOpensTeacherLearner` / `officeOpensAdmin` from `office.byGroup`
- `worksheetSharesTeacherLearner` / `worksheetSharesAdmin` from `workflows.byGroup.worksheetShares`
- `editSharesTeacherLearner` / `editSharesAdmin` from `workflows.byGroup.editShares`
- `fileDropUploadsTeacherLearner` / `fileDropUploadsAdmin` from `workflows.byGroup.fileDropUploads`
- `schoolFilesSharesTeacherLearner` / `schoolFilesSharesAdmin` from `workflows.byGroup.schoolFilesShares`

Old day files with no matching `byGroup` (while the flat total is > 0) send `null` for both split fields, not `0`. `nextcloudMinActions` uses only the `*TeacherLearner` fields (plus `officeOpensTeacherLearner`); a null split contributes 0, so unattributed or admin-only actions do not meet the threshold. `fileDropLinks` stays an unsplit total and is not part of the sum.

Please add the eight workflow split fields and the two office split fields to `ScorecardNextcloudInputs` on the Console PR (`web/API.md` and `web/src/api/types.ts` are yours). Grade line 5 on the `*TeacherLearner` values only.

## `GET /api/v1/health` is public

Unauthenticated and cheap (no database). The Engine healthCheck probes `${port}` and still matches `expect: '"ok"'`.

`HealthResponse` on `main` (`9bdf867`) is `{ ok, schema }`. The collector also sends:

- `version` (string): the App `x-app.version`, currently `"1.0"`.
- `commit` (string or `null`): the dashboard git SHA, from `USAGE_DASHBOARD_COMMIT`, or `/etc/idea-usage/build-info.json` baked at image build, or the Engine bundle directory `usage-dashboard-<sha>`. `null` when none of those are available.

Pixel can add both as optional fields on `HealthResponse` in `web/API.md` and `web/src/api/types.ts`.

## `GET /api/v1/session` works without a cookie

Without `idea_usage_session` the handler returns `200` and `{schema, authenticated: false, user: null}` so the login page can ask. It is not a 401. `POST /api/v1/session` and `DELETE /api/v1/session` stay public too (login / logout). Every other `/api/v1` path still requires the cookie.

## U-9: only `koen` and `marco` may sign in

The programme dashboard has exactly two operator accounts: `koen` and `marco`. There is no `admin` operator any more (`IDEA_USAGE_ADMIN_PASSWORD` is gone). Login is still `POST /api/v1/session` with `{username, password}` — `web/src/pages/LoginPage.tsx` already has both fields, so no single-user rewrite is required.

`PUT /api/v1/session/password` (operator session) accepts `{currentPassword, newPassword}` (new password at least 8 characters). Success returns the same session payload as login. Wrong current password is `401` `{error:{code:"unauthorized",...}}`. A short new password is `400` `{error:{code:"validation",...}}`. The session cookie stays valid.

The UI login mock (`web/src/mock/fetch.ts`) and `web/test/api-client.test.ts` still use `admin` / `mock-operator`. Those never hit the collector. Please retarget the mock at `koen` (or keep a mock-only username — just do not document `admin` as a real operator). A change-password form is not required for this drop; the API is there when you want one.

## `fileDrops` naming

There is no combined `fileDrops` field. Workflows and the scorecard use `fileDropLinks` (links created) and `fileDropUploads` (files received), matching `b4fa49b`.

## `learnerSessionsOnAssigned` is visits

`scorecard.teachingCycle.learnerSessionsOnAssigned` is the week's assigned learner *content visits* (sum of Kolibri `content[].visits` where `role` is `learner` and `assigned` is true). It is not a session count. `assignedShareOfLearnerVisits` is that number divided by all learner content visits.

## `KitTimezone.timeZone` source

`utcOffset` is the kit's offset at Monday 00:00 of the requested week, derived from the registry IANA `timeZone` via zoneinfo, whether or not the kit has stored samples. If the registry has no IANA name, `utcOffset` falls back to the latest presence sample's RFC 3339 offset, then to `+00:00`; `timeZone` is `""` and the label is `kit local time (UTC±n)`. The IANA name itself is from idea's `registry.json` for that kit, not a value the kit reports. If a week spans a DST change, bounds are still local midnights; the single `utcOffset` is the week-start offset and segment timestamps carry their own RFC 3339 offsets.

## `SchoolCard.monitoringEnabled`

Pixel's `b4fa49b` `SchoolCard` did not include `monitoringEnabled` (only `KitListItem` and `SchoolWeekResponse` did). The collector now sends `monitoringEnabled: boolean` on each overview card, matching that kit's current flag. Each card is one kit (`engine` + `deploymentId`), so a school with several kits is several cards; there is no any-of aggregation.

## Presence when monitoring is off

`collectorGap` is only applied for idea-side sidecar outages while a kit's monitoring was known to be on. A never-enabled kit's week is all `gapUnknown`, with no `collectorGap`. Periods covered by `disabled` polls, and time before the first successful pull, stay `gapUnknown` too.

## Weekly `distinctArticles` is a max over days

Kiwix day files give a daily `distinctArticles` count, not the article set. The week value is the maximum of those daily counts (a union is not possible). Nextcloud `office.distinctDocuments` is different: the week passes through the last ok day's value, as `NextcloudOffice` comments require.

## `clockTrusted` comes from ok day-files only

Pixel's types.ts (`SchoolWeekResponse`) and the drift review on #2: `clockTrusted` is `false` only if a contributing `hookStatus: ok` day-file for that week had `clock.synced === false`. `no-hook`, `unlisted-no-hook` and `skipped` stubs (and `timeout` / `failed` / `invalid`) do not contribute. Each row is attributed only to its own `day`. If an instance has no ok day that week, its `clock` is `null`. A week with no contributing ok-rows has `clockTrusted: true` (boolean, not null).

## `uplink.measured`

`GET /api/v1/weeks/{weekStart}/schools/{deploymentId}/uplink` adds `measured: boolean`. It is `true` when at least one idea-side Tailscale sample was stored for that week, and `false` when `samples` and `transitions` are empty.

Uplink is not missing from a filter and is not a field on the kit `idea-usage-export` stream (that stream is `presence`, `day`, and `sample` only). The collector records uplink by polling the sidecar Tailscale LocalAPI (`/localapi/v0/status`) in `main.loop` via `record_uplink`. Presence `on` comes from kit-side `idea-usage-presence/1` samples — a different source. Until the sidecar has joined the tailnet and stored samples, `measured` is `false` and the arrays are empty. That is expected, not a bounds bug.

## Help banner when the only `on` time is outside school hours

The rule lives in the collector (`help_suggestions_for` in `collector/src/aggregate.py`), not in `web/`. The UI (`web/src/pages/FleetOverview.tsx`) prefixes a non-empty `helpSuggestions` list with “Offer help first.” and renders each `message` verbatim.

`offer help` now depends on school-hours on-time (07:00–16:00 kit-local). A kit whose only `on` time is outside school hours is not added to `helpSuggestions`. Help is still offered when monitoring is on and the kit was not on at all this week, or when it was on during school hours but had no learner sessions, or when there is no pulled usage data yet.

The live message `idea03 (idea03 (proof))` is because `school` is already `idea03 (proof)` and the template is `engine (school)`. That interpolation is unchanged.

## U-7 threshold settings (collector, this PR)

Koen approved the U-7 scorecard defaults. The collector now stores them in SQLite (`meta` keys on `./data/usage.sqlite`) and serves Pixel's proposed contract:

- `GET /api/v1/settings/thresholds` → `{thresholds, defaults, updatedAt|null, updatedBy|null}` (operator session, same as `/meta`).
- `PUT /api/v1/settings/thresholds` (operator session) accepts a partial `thresholds` object or `{reset:true}`. Validation failures use Pixel's `{error, field}` shape, not the usual `{error:{code,message}}` envelope used by every other collector endpoint.
- `GET /api/v1/meta` now includes `thresholds` (effective values) and sets `thresholdsConfigured: true`.

Please add this to `web/API.md` and `web/src/api/types.ts` on the Console PR rather than editing `web/API.md` here (that file is yours). The collector-side description is in `docs/API.md`. Extra fields the UI can ignore: `SchoolCard.unused` and `SchoolWeekResponse.unused` (true after help + `unusedAfterHelpWeeks` amber weeks with no improvement). Unused kits are not added to `helpSuggestions`, because that banner is phrased “offer help”.

Scorecard colours are still not sent by the collector (responses stay raw inputs). Tones are computed server-side only so `help_suggestions_for` and the unused flag can read `helpAfterAmberWeeks` and `unusedAfterHelpWeeks`. Grey never counts toward those streaks.

Names taken as proposed. Pushback/notes live in the Kid report to you: `learnerSessionShareMin` is scored from session counts (the scorecard still also exposes `learnerShareOfMinutes`); `helpAfterAmberWeeks` / `unusedAfterHelpWeeks` reject 0; `availableMinSchoolDays` is capped at 5; `updatedBy` is the operator username.

