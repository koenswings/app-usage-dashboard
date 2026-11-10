# Remaining differences from Pixel `b4fa49b`

The collector on `kid/i414-collector` serves `web/API.md` and `web/src/api/types.ts` at `pixel/dashboard-ui-415` head [`b4fa49b`](https://github.com/koenswings/app-usage-dashboard/commit/b4fa49baa5c2fc97fc6d79e40215b519c6c67bca). This note lists only what still differs from that head. Mapped already (not listed below): singular `admin` / `teacher` / `learner` as `{total, beyondSeed}` on Nextcloud `setup` and `logins`; `otherGroups` on `setup`; `instance` plus `instanceId` as an alias; `clockTrusted`; census and Nextcloud `setup` from the last ok day; null app payloads on stub days; scorecard `nextcloudTeacherBeyondSeed` / `nextcloudLearnerBeyondSeed` read from the hook (null when absent); scorecard Nextcloud office and workflow fields as in `ScorecardNextcloudInputs`.

## `port` is always null

`DiscoveredInstance.port` is not in the Engine export. Every instance on `GET /api/v1/weeks/{weekStart}/schools/{deploymentId}/instances` sends `"port": null`.

## Scorecard document-edit fields

`b4fa49b` dropped `documentsCreatedOrEditedTeachers` / `documentsCreatedOrEditedLearners` and the teacher/learner office-open split. The collector does not invent those fields. It serves the `office*` counters on `ScorecardNextcloudInputs` (`officeOpens`, `officeDistinctDocuments`, `officeRead`, `officeEdit`, `officeEstimatedMinutes`) from the stored office object. There is no created-versus-edited-by-role reduction.

## `GET /api/v1/health` is public

Unauthenticated `{"ok": true, "schema": "idea-usage-api/1"}` so the Engine healthCheck can probe `${port}`.

## `GET /api/v1/session` works without a cookie

Without `idea_usage_session` the handler returns `200` and `{schema, authenticated: false, user: null}` so the login page can ask. It is not a 401. Every other `/api/v1` path still requires the cookie.

## `fileDrops` naming

There is no combined `fileDrops` field. Workflows and the scorecard use `fileDropLinks` (links created) and `fileDropUploads` (files received), matching `b4fa49b`.

## `learnerSessionsOnAssigned` is visits

`scorecard.teachingCycle.learnerSessionsOnAssigned` is the week's assigned learner *content visits* (sum of Kolibri `content[].visits` where `role` is `learner` and `assigned` is true). It is not a session count. `assignedShareOfLearnerVisits` is that number divided by all learner content visits.

## `KitTimezone.timeZone` source

`utcOffset` comes from the latest presence sample's RFC 3339 offset. `timeZone` is the optional IANA name from idea's `registry.json` for that kit, not a value the kit itself reports. When the registry has no IANA name, `timeZone` is `""` and the label is `kit local time (UTC±n)`.

## Weekly `distinctArticles` is a max over days

Kiwix day files give a daily `distinctArticles` count, not the article set. The week value is the maximum of those daily counts (a union is not possible). Nextcloud `office.distinctDocuments` is different: the week passes through the last ok day's value, as `NextcloudOffice` comments require.
