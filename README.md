# app-usage-dashboard

IDEA App for the programme field-usage dashboard (proposal merged in idea#410).

**Install only on idea**, onto the system disk, with `installApp`. Never install this App on a school kit: the usage-pull private key is provisioned only on idea.

- `tailscale` — userspace sidecar that **owns** the idea-hub Tailscale identity (`idea-hub`, `tag:idea-hub`). Hostname is `idea-hub`. Compose already passes `TS_EXTRA_ARGS=--advertise-tags=tag:idea-hub`. State lives only in the App's `./data/tailscale`. To move that identity, **move** the state (never copy it): whichever container runs last owns the live node key, and any leftover copy goes stale (`NeedsLogin` / `nodeKeyExpired`). Only one idea-hub container may ever exist, and an older copy of the state must never be started after the App has run (it re-registers a stale node key and the node ends up Expired). Removing or stopping the App only stops its containers and keeps `./data/tailscale`; never run `tailscale logout` or `down`. Compose sets `TS_STATE_DIR=/var/lib/tailscale` to the bind mount, `TS_AUTH_ONCE=true` (so containerboot does not force `tailscale up` on every start), and empty `TS_KUBE_SECRET`. The sidecar wrapper refuses to start with empty state unless `TS_AUTHKEY` is set. Leave `TS_AUTHKEY` empty when reusing existing state; do not re-auth. After a join or restart, `script/check-idea-hub-nodekey.py` compares the derived on-disk nodekey with `tailscale status --json` `Self.PublicKey` (it never prints private keys).
- `collector` — deterministic Python service (no LLM). Watches the sidecar LocalAPI, records uplink history, pulls `idea-usage-export` over SOCKS5 + restricted SSH, stores SQLite at `./data/usage.sqlite`.
- `web` — nginx on `${port}:8080`, proxies `/api/` to the collector. The UI itself is Pixel's (idea#415). A placeholder is served until that UI is wired in. Never binds 80, 3333, 3334 or 8081, and never touches MilkWise.

The usage-pull key lives at `./data/keys/pull_key` (mode 0600). Sidecar state lives only under `./data/tailscale` (move it, never copy it). Both are listed in `x-app.backup.exclude` (`keys`, `tailscale`) so a normal Engine backup does not copy them; they go only to idea's encrypted Borg repository. See `docs/runbook.md`.

Only Koen and Marco may open the dashboard (`koen` and `marco`; see `docs/accounts.md`). HTTP responses follow `idea-usage-api/1` (Pixel, `web/API.md`). The collector-side data model is in `docs/API.md`.
