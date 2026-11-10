# Programme dashboard HTTP API

Contract for Pixel's UI (idea#415) against Kid's `web` service in `app-usage-dashboard` (idea#414). Field names follow the merged proposal (idea PR #410) §7.5 tables and §7.6 day summary, plus the presence shape agreed with Kid:

`{ state: 'on' | 'off' | 'gapUnknown' | 'collectorGap', start, end, lengthKnown }`

`lastPulled` is returned on every kit and every school card. Help events are the only write, and only an operator (Koen or Marco) may create one.

TypeScript types live in `src/api/types.ts`.

## Versions

| Name | Value | Meaning |
|---|---|---|
| HTTP API schema | `idea-usage-api/1` | This document. Every JSON response includes `"schema": "idea-usage-api/1"`. |
| Day-file schema | `idea-usage-day/1` | §7.6 files pulled from the kit (`/var/lib/idea/usage/<day>/<instance>.json`). The day-file identity field is `instance`; `instanceId` is an accepted alias. |

A breaking change increments the HTTP API schema. Unknown fields must be ignored by the client.

## Base path, transport, privacy

- Base path: `/api/v1`
- JSON request and response bodies, UTF-8
- Public (no cookie): `GET /api/v1/health`, `GET /api/v1/session`, `POST /api/v1/session`, `DELETE /api/v1/session`. Every other `/api/v1` path requires the cookie
- Role-level counts only (§9). No usernames, no per-learner dossiers, no document contents, no network addresses
- Content titles, channel names and Wikipedia article titles are allowed (they describe curriculum, not people)
- The UI never talks to SQLite and never writes kit data

## Auth (Console operator pattern)

The Console stores operator accounts in the Engine `userDB` and keeps a client-side `operatorSession` after a username + password check (bcrypt). This dashboard is a separate HTTP app, so the same *operator* idea is exposed as a **cookie session**:

- Cookie name: `idea_usage_session`
- Attributes: `HttpOnly; SameSite=Lax; Path=/`; `Secure` when the request is HTTPS
- Default-password convention (`<account name>911!`, e.g. the first operator `admin`) lives in **server config**, never in UI source
- Who besides Koen may log in is a Koen item (idea#375); the login is required either way

| Method | Path | Body | Response |
|---|---|---|---|
| `GET` | `/api/v1/health` | — | `{ "ok": true, "schema": "idea-usage-api/1" }`. Public, no cookie. Used by the Engine healthCheck. |
| `GET` | `/api/v1/session` | — | `SessionResponse`. Without a cookie this is `200` and `{ authenticated: false, user: null }` — not a 401. The UI uses that to show the login page. |
| `POST` | `/api/v1/session` | `{ "username", "password" }` | `SessionResponse` + `Set-Cookie`. `401` with error `unauthorized` on bad credentials |
| `DELETE` | `/api/v1/session` | — | `SessionResponse` with `authenticated: false` + cleared cookie |

## Error shape

Every non-2xx response:

```json
{
  "error": {
    "code": "unauthorized | forbidden | not_found | validation | conflict | unavailable",
    "message": "Human-readable sentence",
    "details": {}
  }
}
```

`details` is optional. `401 unauthorized` when a protected path is called without a cookie (not on `GET /api/v1/session` or `GET /api/v1/health`). `403 forbidden` if a non-operator somehow authenticates and hits `POST .../help-events`.

## Endpoints

Week paths use `weekStart`: the Monday of the school week as `YYYY-MM-DD`. A non-Monday value is `400 validation`. School weeks displayed in the UI are Monday–Friday; Saturday and Sunday presence still appear in the segment list when present.

### Meta and lists

| Method | Path | Query | Response |
|---|---|---|---|
| `GET` | `/api/v1/health` | — | `HealthResponse` — public `{ ok, schema }` |
| `GET` | `/api/v1/meta` | — | `MetaResponse` |
| `GET` | `/api/v1/kits` | — | `KitsResponse` — registry of engines / deployments, each with `lastPulled` |
| `GET` | `/api/v1/weeks` | — | `WeeksResponse` — Mondays the picker can offer, plus `currentWeekStart` |

`MetaResponse` fields:

- `thresholdsConfigured` — `false` until Koen sets cut-offs (idea#375). The API still returns raw scorecard **inputs**, never a grade
- `staleAfterHours` — a card whose `lastPulled` is older than this has `stale: true` and `dataFrom: "<YYYY-MM-DD>"`. Server value wins. If meta omits it, the UI uses `48` from `src/config/display.ts`
- `hourlyChartMinWeeklyViews` — the UI hides Wikipedia views-by-hour when that instance's weekly `pageViews` is below this number. Server value wins. If meta omits it, the UI uses `20` from `src/config/display.ts`
- `headerTimeZone` — typically `Europe/Brussels`
- `sampleData` — `true` when serving labelled sample / mock data
- `daySchema` — `idea-usage-day/1`

`KitListItem` fields (from the §7.5 `kits` table, plus `lastPulled` from `pull_log`):

- `engine`, `tailscaleName`, `school`, `deploymentId`, `lastPulled`, `monitoringEnabled`

### Fleet overview (page 1)

| Method | Path | Response |
|---|---|---|
| `GET` | `/api/v1/weeks/{weekStart}/overview` | `OverviewResponse` |

Contains one `SchoolCard` per deployment: scorecard **inputs** (raw counts), headline census (`classes`, `learnersRegistered`, `teachers`, `kolibriMinutes`), per-card `lastPulled`, `stale`, `dataFrom`, and `hasUsageData`.

`helpSuggestions` is an optional, **server-owned** list of banner items (kits that look idle or dark). Each `message` is already phrased as "offer help". The UI renders these verbatim and does not invent cut-offs or retractions. Empty when the collector has nothing to flag.

When `thresholdsConfigured` is `false`, the UI shows the pill and every data-bearing scorecard line as **Thresholds not set**. A card with no pulled usage data shows **No data** (never the word "Grey").

### School week (page 2)

| Method | Path | Response |
|---|---|---|
| `GET` | `/api/v1/weeks/{weekStart}/schools/{deploymentId}` | `SchoolWeekResponse` |
| `GET` | `/api/v1/weeks/{weekStart}/schools/{deploymentId}/presence` | `PresenceResponse` |

`SchoolWeekResponse` is the scorecard inputs plus the Q3 census (`classes`, `classesDelta`, `learnersRegistered`, `learnersRegisteredDelta`, `learnersEnrolled`, `teachers`, `teachersDelta`, `admins`) and a `presence` block.

Presence segments (also the standalone presence endpoint):

```ts
{ state: 'on' | 'off' | 'gapUnknown' | 'collectorGap', start, end, lengthKnown }
```

The presence block also carries `timezone: { timeZone, utcOffset, label }` so ticks render in **kit local time**, labelled as such (the page header uses Brussels time). `timeZone` is the optional IANA name from idea's `registry.json` for that kit — not a value the kit itself reports. `utcOffset` comes from the latest presence sample's RFC 3339 offset. When the registry has no IANA name, `timeZone` is `""` and `label` is `kit local time (UTC±n)`.

`PresenceResponse.days` is the §7.5 `presence_days` roll-up: `onMinutes`, `schoolHoursOnMinutes`, `boots`, `longestGapMinutes`, `lengthKnown`.

### Uplink history (page 7)

| Method | Path | Response |
|---|---|---|
| `GET` | `/api/v1/weeks/{weekStart}/schools/{deploymentId}/uplink` | `UplinkResponse` |

From §7.5 `uplink_samples` and `uplink_transitions`:

- Sample: `timestamp`, `engine`, `online`, `lastSeen`, `via` (`direct` \| `DERP` \| `null`), `latencyMs`
- Transition: `timestamp`, `engine`, `fromState`, `toState` (`online` \| `offline`)

Shown next to the power sampler so "dark to us" (uplink down) and "powered off" (presence `off`) stay distinct.

### App week aggregates (pages 3–5)

| Method | Path | Response |
|---|---|---|
| `GET` | `/api/v1/weeks/{weekStart}/schools/{deploymentId}/kolibri` | `KolibriWeekResponse` |
| `GET` | `/api/v1/weeks/{weekStart}/schools/{deploymentId}/nextcloud` | `NextcloudWeekResponse` |
| `GET` | `/api/v1/weeks/{weekStart}/schools/{deploymentId}/kiwix` | `KiwixWeekResponse` |

One object per **instance**. Own, Demo and extra copies stay on their own lines and are never summed together.

Every instance (all three apps) carries the Engine envelope: `instance` (day-file identity; `instanceId` is an alias), `name`, `hookStatus`, `listed`, `demo`, `clock`, `collectedAt`, and `skipReason` when `hookStatus` is `skipped`. App payloads are optional and `null` on stubs and failed days so the UI can tell “the measurement failed” apart from “nothing has been collected yet” (`collectedAt` is null). `flags` is Kolibri-only.

`hookStatus` (agent-engine-dev#308): `ok | timeout | failed | invalid | skipped | unlisted-no-hook | no-hook`. A working borrowed hook on an extra copy is `ok` with `listed: false` — there is no `unlistedBorrowed`. `missing` was renamed to `no-hook`. When status is `skipped`, `skipReason` is `backup | update | move | temperature`. The UI shows each status in plain words.

Each app-week response also has `clockTrusted`. It is `false` when any day-file this week had `clock.synced === false`; the whole week is then untrustworthy for time-based reading.

**Kolibri** mirrors §7.6: `clock`, `setup` (census + deltas; snapshot from the last ok day), `signins` (`learner` / `coach` / `admin` each `{ users, sessions, minutes }`, summed across ok days), `guest` (`visits`, `seconds` — convert to minutes only for the scorecard), `teaching` (summed), `content[]` (`channel`, `title`, `kind`, `role`, `visits`, `seconds`, `completions`, `assigned`, summed). `flags` may include `demoSeedExcluded`.

**Nextcloud** follows the Engine usage contract (agent-engine-dev#308) as amended (singular role keys; hook-emitted `{total, beyondSeed}`). These fields are **not** taken as-is from the original §7.6 sketch:

- `setup`: `{ admin, teacher, learner, otherGroups? }` where each of `admin` / `teacher` / `learner` is `{ total, beyondSeed }` emitted by the hook. Do not derive beyond-seed on idea. `otherGroups` is kept (a map of extra group name → count) unless the Engine later drops it.
- `logins`: `{ admin, teacher, learner }`, each `{ total, beyondSeed }`
- `office`: `{ opens, distinctDocuments, read, edit, estimatedMinutes, byGroup: { admin, teacher, learner }, mime: { text, sheet, slides } }`. Single `estimatedMinutes` (no per-role split). No created/edited fields. Do not re-reduce this object. `distinctDocuments` is already the Engine’s union across that day’s samples. A week response must not sum daily `distinctDocuments` (that would over-count); it may pass through the last ok day’s value. If office is missing, it is `null`.
- `appsOpened`: a map of App id → open count. May be missing or empty. No role unless a later counter exists.
- `workflows`: `{ worksheetShares, editShares, fileDropLinks, fileDropUploads, schoolFilesShares }` (`fileDropLinks` and `fileDropUploads` are separate)

**Kiwix / Wikipedia** (sibling file in §7.6): `pageViews` and `sessions` are summed across ok days; `topArticles[]` (`title`, `views`) merge by title; `byHour` (24 kit-local hourly totals) is summed. `distinctArticles` is the **maximum of the daily counts**, not a week-wide distinct total — day files do not include the article set, so a union is not possible. The UI labels this “most different articles in one day” and never calls it the week’s distinct total. No identity. The UI hides `byHour` when `pageViews < hourlyChartMinWeeklyViews`.

### Instance breakdown (page 8)

| Method | Path | Response |
|---|---|---|
| `GET` | `/api/v1/weeks/{weekStart}/schools/{deploymentId}/instances` | `InstancesResponse` |

Every discovered container, including extra (Engine-unlisted) copies. Fields: the instance envelope (`instance`, `name`, `app`, `demo`, `listed`, `hookStatus`, `skipReason?`, `clock`, `collectedAt`) plus an optional `note`. The collector always sends `"port": null` (the field is not in the Engine export); the UI does not display it. Two Kolibris never collapse into one number.

### Help events (page 6, Q7) — only write

| Method | Path | Body | Response |
|---|---|---|---|
| `GET` | `/api/v1/schools/{deploymentId}/help-events` | — | `HelpEventsResponse` |
| `POST` | `/api/v1/schools/{deploymentId}/help-events` | `CreateHelpEventRequest` | `201` + the created `HelpEvent` |

`CreateHelpEventRequest`: `{ offeredOn, tutorialChapters, note }`.

The App never invents a help event. `HelpEventsResponse.weeklyTrend` is an array of `{ weekStart, scorecard }` so the timeline can show raw counts before and after an offered-help date. Wording on the dashboard is always "offer help", never "retract".

## Scorecard inputs

The six lines from §4. The API returns the measurements, not a colour or a pass/fail:

1. **Available** — `schoolDaysOn`, `schoolDaysExpected`, `schoolHoursOnMinutes`, `bootsPerSchoolDay`, `longestGapMinutes`
2. **Set up** — own-Kolibri `classes`, `learnersRegistered`, `learnersEnrolled`, `teachers`, `admins`; own-Nextcloud `nextcloudTeacherBeyondSeed`, `nextcloudLearnerBeyondSeed` (read from hook `setup.teacher.beyondSeed` / `setup.learner.beyondSeed` on the last ok day)
3. **Teaching cycle** — `lessonsCreated`, `lessonsVisible`, `quizzesCreated`, `quizzesStarted`, `learnerSessionsOnAssigned` (assigned learner *content visits*, not sessions; the collector keeps this field name), `assignedShareOfLearnerVisits` (`learnerSessionsOnAssigned` / all learner content visits)
4. **Learners operate** — sessions and minutes by role, plus `learnerShareOfMinutes`. Guest time stays as `seconds` on the instance payload and is converted to minutes only here
5. **Nextcloud** — `worksheetShares`, `editShares`, `fileDropLinks`, `fileDropUploads`, `schoolFilesShares`, `officeOpens`, `officeDistinctDocuments`, `officeRead`, `officeEdit`, `officeEstimatedMinutes`
6. **Wikipedia** — `pageViewsOwn`, `sessionsOwn`, `distinctArticlesOwn` on the school's own instance (Demo excluded). `distinctArticlesOwn` is the max of daily `distinctArticles`, not a week-wide distinct total.

`null` means no data for that input (kit not pulled, monitoring off, or that app produced no summary). Null is shown as **No data**, never as a failing grade.

Threshold comparison, if it is ever enabled, lives in one UI module (`src/config/thresholds.ts`) and reads `thresholdsConfigured` from `/api/v1/meta`. Until Koen sets values, that module does not invent cut-offs.

## Invented fields (not named in §7.6)

§7.6 is a kit-side day-file sketch. The HTTP API below had to name the idea-hosted wrappers and a few operator-facing extras. Kid and Axle should confirm or rename these:

| Field / type | Why it exists |
|---|---|
| `schema: "idea-usage-api/1"` | HTTP wrapper version, distinct from `idea-usage-day/1` |
| `deploymentId` on responses | Idea's mapping of `(engine, day)` → deployment; not stored on the kit |
| `lastPulled`, `stale`, `dataFrom`, `staleAfterHours` | Per-card freshness (accepted UI change 2) |
| `monitoringEnabled`, `hasUsageData` | Distinguish "monitoring off" / "never pulled" from a zero week |
| `KitTimezone` (`timeZone`, `utcOffset`, `label`) | `timeZone` from the idea registry (optional IANA); `utcOffset` from the latest presence sample |
| `headerTimeZone`, `hourlyChartMinWeeklyViews`, `sampleData` | Header clock, chart-hiding threshold, mock/sample banner |
| `note` on a school card | Subtitle ("own apps + Demo", "Not installed yet") |
| `headlines` | Fleet-card census strip (classes / learners / teachers / Kolibri minutes) |
| `helpSuggestions[]` | Server-owned fleet banner; UI does not invent idle/dark cut-offs |
| `weekStart` / `weekEnd` / `weekLabel` / `GET /weeks` | Week picker (accepted UI change 5) |
| Scorecard input object grouping (`available`, `setup`, …) | §4 lines packaged so the UI does not re-derive them from day files |
| `bootsPerSchoolDay`, `schoolDaysOn`, `schoolHoursOnMinutes` | Derived from `presence_days` for the Available line |
| `nextcloudTeacherBeyondSeed`, `nextcloudLearnerBeyondSeed` | Scorecard copies of hook `setup.*.beyondSeed` on the last ok day; not derived on idea |
| `assignedShareOfLearnerVisits`, `learnerShareOfMinutes`, `learnerSessionsOnAssigned` | `learnerSessionsOnAssigned` is assigned learner content visits (Kid keeps this name); the share is that number over all learner visits |
| `listed`, `hookStatus`, `skipReason`, `collectedAt` | Instance envelope from the Engine contract (agent-engine-dev#308) |
| `clockTrusted` | Week-level roll-up: any unsynced clock makes the week untrustworthy. The collector serves `clockTrusted`, not `clockTrustworthy`. |
| `HelpEvent` (`id`, `offeredOn`, `tutorialChapters`, `note`, `createdBy`, `createdAt`) | §7.5 `help_events` column names were not specified |
| `weeklyTrend` on help-events | Before/after comparison for page 6 |
| `SessionResponse`, cookie `idea_usage_session` | Cookie equivalent of the Console operator session |
| Error envelope (`error.code` / `message` / `details`) | Uniform client handling |

Fields taken as-is from §7.6 / §7.5 / the agreed presence shape are **not** listed above: `engine`, `day`, `app`, `instance`, `name`, `demo`, `clock`, Kolibri `setup` census fields, `signins`, `content`, `teaching`, `guest`, `flags`, Kiwix `pageViews` / `distinctArticles` / `sessions` / `topArticles` / `byHour`, presence `{state,start,end,lengthKnown}`, uplink sample/transition columns, `lastPulled`.

Reshaped Nextcloud fields (`setup`, `logins`, `office`, `appsOpened`, `workflows`) follow the Engine usage contract and the Kid/Axle amendment (singular `admin` / `teacher` / `learner` keys and `{total, beyondSeed}` role counts). They are documented in the Nextcloud section above, not treated as unchanged §7.6.

## Week roll-ups

The HTTP week objects are aggregates of ok day-files:

- Census / Nextcloud `setup` is a snapshot from the **last ok day**, never summed. Daily deltas may be summed.
- Sign-ins, teaching, content visits/seconds/completions, and Kiwix `pageViews` / `sessions` / `byHour` are summed across ok days. Kiwix `distinctArticles` is the max of daily counts (never described as the week’s distinct total). Nextcloud `office.distinctDocuments` is the last ok day’s Engine-union value, not a sum or max of days.
- Any day with `clock.synced === false` marks the whole week untrustworthy (`clockTrusted: false`). The UI shows a visible warning.
- A presence segment with `lengthKnown: false` is never displayed as a real duration.
- Guest time stays in `seconds` on the payload; convert to minutes only when building scorecard `guestMinutes`.

## What the UI will not call

- No direct SQLite
- No writes other than `POST /api/v1/schools/{deploymentId}/help-events`
- No kit export verbs (`since`, `archive-and-clear`) — those are collector / helper v8
- idea#417 (Console D2 Usage panel) is out of scope
