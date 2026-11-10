# web

Dashboard UI for the idea-hosted `app-usage-dashboard` App (Solid + Vite, static build, no CDN). Owner: Pixel, idea#415.

The UI talks only to Kid's read-only HTTP API (`/api/v1/...`). It never opens SQLite and never writes kit data. The only write is `POST /api/v1/schools/:deploymentId/help-events`, used when an operator records that help was offered.

The HTTP contract is in [API.md](./API.md) and `src/api/types.ts`.

## Commands

Run these from `web/`:

```bash
pnpm install
VITE_MOCK=1 pnpm dev          # mock API, labelled sample data
VITE_MOCK=1 pnpm build        # embed the mock adapter (for local preview)
pnpm build                    # production build — calls the real same-origin API
pnpm preview                  # serve dist/ (use after a VITE_MOCK=1 build to review sample data)
pnpm typecheck
pnpm test
```

Build output: `web/dist/`.

## Environment

| Variable | Meaning |
|---|---|
| `VITE_MOCK=1` | Use the in-app fetch adapter and labelled sample data (3 schools). Compile-time; set it for `dev` and for any `build` you want to preview offline. |
| `VITE_API_BASE` | Optional prefix for real API calls. Default is empty (same origin). |

## Mock login

The mock adapter accepts username `admin` and password `mock-operator`. That password is mock-only. The production default-password convention lives in server configuration and is never baked into UI source.

Sample fixtures (Nharira / healthy-looking counts, Chigonda / offer-help banner plus stale data and a tiny Wikipedia week, kind-panda / No data) are clearly labelled “Sample data” in the UI.

## Constraints

- TypeScript strict, one CSS file (`src/main.css`), no CSS framework, no CDN, no web fonts from the network
- Every `<For>` is keyed by a stable ID, never by array index
- Scorecard thresholds live in `src/config/thresholds.ts` only; until Koen sets them the UI shows “Thresholds not set”
- Pages 6–8 (help timeline, uplink history, instance breakdown) are first functional versions and need a sketch sign-off
