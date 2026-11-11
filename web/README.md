# web

Dashboard UI for the idea-hosted `app-usage-dashboard` App (Solid + Vite, static build, no CDN). Owner: Pixel, idea#415.

The UI talks only to Kid's HTTP API (`/api/v1/...`). It never opens SQLite and never writes kit data. Writes are `POST /api/v1/schools/:deploymentId/help-events` (an operator records that help was offered) and the proposed `PUT /api/v1/settings/thresholds` (operator session; pending collector).

The HTTP contract is in [API.md](./API.md) and `src/api/types.ts`. `GET /api/v1/health` is public. `GET /api/v1/session` without a cookie returns `{authenticated:false}` (not a 401) so the login page can ask.

## Commands

Run these from `web/`:

```bash
pnpm install
pnpm dev                      # real API via the Vite proxy (see USAGE_API_PROXY)
pnpm dev:mock                 # labelled sample data (VITE_MOCK=1)
pnpm build                    # production build — calls the real same-origin API
VITE_MOCK=1 pnpm build        # embed the mock adapter (opt-in, for screenshots / offline preview)
pnpm preview                  # serve dist/
pnpm typecheck
pnpm test
```

Build output: `web/dist/`.

## Environment

| Variable | Meaning |
|---|---|
| `VITE_MOCK=1` | Opt-in in-app fetch adapter and labelled sample data (3 schools). Compile-time. Use `pnpm dev:mock` or set it for a screenshot/offline `build`. The default build talks to the real API. |
| `VITE_API_BASE` | Optional prefix for real API calls. Default is empty (same origin). |
| `USAGE_API_PROXY` | Where Vite proxies `/api` during `pnpm dev` / `pnpm preview`. Default `http://127.0.0.1:18080`. |

## Mock login

The mock adapter accepts username `admin` and password `mock-operator`. That password is mock-only. The production default-password convention lives in server configuration and is never baked into UI source.

Sample fixtures (Nharira / healthy-looking counts, Chigonda / offer-help banner plus stale data and a tiny Wikipedia week, kind-panda / No data) are clearly labelled “Sample data” in the UI.

## Display defaults

`GET /api/v1/meta` wins when it sends a number. If it omits a field, `src/config/display.ts` supplies:

| Setting | Default | Used for |
|---|---|---|
| `staleAfterHours` | `48` | A card whose `lastPulled` is older than this is marked “data from &lt;date&gt;” |
| `hourlyChartMinWeeklyViews` | `20` | Hide Wikipedia views-by-hour when that copy’s weekly page views are below this |

Scorecard grade cut-offs are the U-7 starting thresholds Koen approved on idea#375 (11 Nov 09:42 Europe/Brussels). They live in `src/config/thresholds.ts` as defaults an operator can change on the Settings page (`#/settings`). Effective values come from `/meta.thresholds` or `GET /api/v1/settings/thresholds` when the collector serves them; otherwise the built-in defaults are used. If the settings endpoint is missing (`404`), Settings is read-only. Grey (no data / not measured) never counts as amber.

| Key | Default |
|---|---|
| `availableMinSchoolDays` | `3` |
| `teachingCycleMinItems` | `1` |
| `learnerSessionShareMin` | `0.5` (shown as 50%) |
| `nextcloudMinActions` | `1` |
| `wikipediaMinViews` | `10` |
| `helpAfterAmberWeeks` | `3` |
| `unusedAfterHelpWeeks` | `4` |

Set up is a yes/no check (own Kolibri has ≥1 coach, ≥1 class and enrolled learners; own Nextcloud has teacher and learner accounts beyond the seeds) and has no number.

## Pages against proposal §2

| Page | Nav label | §2 question | What it answers |
|---|---|---|---|
| Fleet overview | Fleet | Q1–Q8 at a glance | Six scorecard lines (Available, Set up, Teaching cycle, Learners operate, Nextcloud, Wikipedia) graded against the U-7 defaults, plus last-pulled freshness |
| School week | Week | Q1, Q3 | Kit on/off/gap pattern and who is on the books (census) |
| Kolibri | Kolibri | Q2, Q3, Q4, Q6 | Anyone using the app while the kit is on; who operates (role census and sign-ins); lessons, quizzes, assigned vs free content; school’s own vs Demo vs extra copies |
| Nextcloud | Nextcloud | Q5, Q6 | Roles, apps opened, Office, sharing workflows; school’s own vs Demo vs extra copies |
| Wikipedia | Wikipedia | Q6, Q8 | Views, articles, sessions, top articles, views by hour (hidden on a tiny week); school’s own vs Demo |
| Help offered | Help | Q7 | Whether use changes after help was offered (record + weekly raw counts) |
| Reachability | Reachability | Q1 | Whether idea could reach the kit, next to the power sampler, so “not reachable to us” is not read as “powered off” |
| Apps | Apps | Q6 | Every copy on its own line (own / Demo / extra) so two Kolibris are never added together |
| Settings | Settings | U-7 (idea#375) | Operator-only editable defaults for the scorecard cut-offs, with Save and Reset to defaults |

Pages 6–8 no longer carry a “needs sketch sign-off” banner. They stay because each one answers a §2 question.

### Dropped or reworded (did not map to §2, or was jargon)

- “Needs sketch sign-off” banners
- Raw instance ids and “listed / unlisted” tags (now “School’s own”, “Demo”, “Extra copy”)
- Tailscale `via` (DERP / direct) and `latencyMs` on the reachability page
- Instance port column
- “Beyond seeds” as a number derived on idea (the hook now emits `beyondSeed`; the UI reads it directly)
- Collabora CODE and raw Nextcloud app ids (shown as Files / Office / Photos)
- Empty scorecard bars (grades are words, not bars)
- Nextcloud “documents created / edited” by role (replaced by the Engine `office` object)

## Constraints

- TypeScript strict, one CSS file (`src/main.css`), no CSS framework, no CDN, no web fonts from the network
- Every `<For>` is keyed by a stable ID, never by array index
- Scorecard thresholds live in `src/config/thresholds.ts` only, as editable defaults (idea#375 U-7). Grey never counts as amber
