# AGENTS.md — programme dashboard UI (`web/`)

You are building the IDEA Field Usage dashboard UI (Pixel, idea#415) inside `app-usage-dashboard`. Kid owns `collector/` and `docs/API.md`; do not rewrite those.

## Commands (from `web/`)

```bash
pnpm install
pnpm typecheck
pnpm test
pnpm build
VITE_MOCK=1 pnpm dev
```

QC before a PR: `pnpm install`, `pnpm typecheck`, `pnpm test`, `pnpm build`, and grep the UI source for `console.log` and index-keyed `<For>` (a second callback argument used as the key).

## Constraints

- Solid.js + Vite + TypeScript strict
- One CSS file: `src/main.css`. No CSS framework, no CDN, no runtime external deps, no web fonts from the network
- Fully offline on idea’s LAN and over Tailscale
- Every `<For>` keyed by a stable ID, never by index
- No broad store subscriptions (use derived values / resources)
- No `console.log`
- No `TODO` / `FIXME` without a linked issue
- No commented-out blocks over 5 lines
- No hardcoded credentials. The Console default-password convention is server config, never UI source
- Shared `ScorecardCard` and `PresenceStrip` live in `src/components/shared/` with no app-specific imports (D2 should be able to reuse them later)
- Threshold comparison lives only in `src/config/thresholds.ts`. Until Koen sets cut-offs (idea#375) show “Thresholds not set”; never invent grades. “No data” is never the word “Grey”
- Read-only `GET /api/v1/...` except `POST` help-events (and the session login/logout). No direct SQLite
- Banner and help wording always say “offer help”, never “retract”
- Presence states: `on`, `off`, `gapUnknown`, `collectorGap`. The last two are hatched grey with their own words, never drawn as the kit going dark
- Pages 6–8 are first functional versions and need a sketch sign-off

## Layout

- Contract: `API.md`, `src/api/types.ts`
- Client: `src/api/client.ts`
- Mock adapter: `src/mock/` (`VITE_MOCK=1`)
- Pages: `src/pages/`
- Tests: `test/` (vitest + @solidjs/testing-library)
