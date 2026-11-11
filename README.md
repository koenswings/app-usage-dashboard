# app-usage-dashboard

IDEA App for the programme field-usage dashboard (proposal merged in idea#410).

**Install only on idea**, onto the system disk, with `installApp`. Never install this App on a school kit: the usage-pull private key is provisioned only on idea.

- `tailscale` — userspace sidecar tagged `tag:idea-hub`. State in `./data/tailscale`. Auth key from the instance `.env` (`TS_AUTHKEY`).
- `collector` — deterministic Python service (no LLM). Watches the sidecar LocalAPI, records uplink history, pulls `idea-usage-export` over SOCKS5 + restricted SSH, stores SQLite at `./data/usage.sqlite`.
- `web` — nginx on `${port}:8080`, proxies `/api/` to the collector. The UI itself is Pixel's (idea#415). A placeholder is served until that UI is wired in. Never binds 80, 3333, 3334 or 8081, and never touches MilkWise.

The usage-pull key lives at `./data/keys/pull_key` (mode 0600). Sidecar state lives under `./data/tailscale`. Both are listed in `x-app.backup.exclude` (`keys`, `tailscale`) so a normal Engine backup does not copy them; they go only to idea's encrypted Borg repository. See `docs/runbook.md`.

Only Koen and Marco may open the dashboard (`koen` and `marco`; see `docs/accounts.md`). HTTP responses follow `idea-usage-api/1` (Pixel, `web/API.md`). The collector-side data model is in `docs/API.md`.
