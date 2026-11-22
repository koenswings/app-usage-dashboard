# app-usage-dashboard

IDEA App for the programme field-usage dashboard (proposal merged in idea#410).

**Install only on idea**, onto the system disk, with `installApp`. Never install this App on a school kit: the usage-pull private key is provisioned only on idea.

- `tailscale` — userspace sidecar that **owns** the idea-hub Tailscale identity (`idea-hub`, `tag:idea-hub`). Hostname is `idea-hub`. Compose already passes `TS_EXTRA_ARGS=--advertise-tags=tag:idea-hub`. State lives only in the App's `./data/tailscale`. To move that identity, **move** the state (never copy it): whichever container runs last owns the live node key, and any leftover copy goes stale (`NeedsLogin` / `nodeKeyExpired`). Only one idea-hub container may ever exist, and an older copy of the state must never be started after the App has run (it re-registers a stale node key and the node ends up Expired). Removing or stopping the App only stops its containers and keeps `./data/tailscale`; never run `tailscale logout` or `down`. Compose sets `TS_STATE_DIR=/var/lib/tailscale` to the bind mount, `TS_AUTH_ONCE=true` (so containerboot does not force `tailscale up` on every start), and empty `TS_KUBE_SECRET`. The sidecar wrapper refuses to start with empty state unless `TS_AUTHKEY` is set, and a keyed join is attempted exactly once (a failure writes `./data/tailscale/authkey-join-blocked` and does not retry the key). Leave `TS_AUTHKEY` empty when reusing existing state; do not re-auth. After a join or restart, `script/check-idea-hub-nodekey.py` compares the derived on-disk nodekey with `tailscale status --json` `Self.PublicKey` (it never prints private keys).
- `collector` — deterministic Python service (no LLM). Watches the sidecar LocalAPI, records uplink history, pulls `idea-usage-export` over SOCKS5 + restricted SSH, stores SQLite at `./data/usage.sqlite`.
- `web` — nginx on `${port}:8080`, proxies `/api/` to the collector. The UI itself is Pixel's (idea#415). A placeholder is served until that UI is wired in. Never binds 80, 3333, 3334 or 8081, and never touches MilkWise.

The usage-pull key lives at `./data/keys/pull_key` (mode 0600). Sidecar state lives only under `./data/tailscale` (move it, never copy it). `x-app.backup` is hook-mode (idea#444): the preHook writes a consistent dump at `./data/backup/usage.sqlite` so a backup can run without stopping the idea-hub sidecar. `exclude` (always applied) is `keys`, `tailscale`, `tailscale-run`, and `data/backup/daily`. `hookExclude` (only after a successful preHook; dropped on fallback or stop) is the live `usage.sqlite` plus `-wal`/`-shm`. The hook dump stays in the archive. The key and node state go only to idea's encrypted Borg repository; `tailscale-run` is runtime-only. See `docs/runbook.md`.

Only Koen, Marco and Justice may open the dashboard (`koen`, `marco` and `justice`; see `docs/accounts.md`). HTTP responses follow `idea-usage-api/1` (Pixel, `web/API.md`). The collector-side data model is in `docs/API.md`.

## Release check against the previous release (idea#403)

- **Before tagging a release, run `script/check-base-ref.sh` in a full clone with tags, with `AAD_CHECK_COMPOSE` set:** `AAD_CHECK_COMPOSE=<agent-app-dev>/script/check-compose.mjs script/check-base-ref.sh`.
- It compares `compose.yaml` with the previous release tag (agent-app-dev `check-compose --base-ref`). A stateful image (MariaDB, MySQL, Postgres, Mongo, Redis) that moves to a new series needs an App major bump.
- **Previous release tag:** the highest `<major>.<minor>[-<upstream>]` tag that is an ancestor of HEAD and is not HEAD's own tag.
- **It fails** in a shallow clone (`git fetch --unshallow --tags`; CI: `fetch-depth: 0`) and in a clone with no release tags at all (`git fetch --tags`).
- **First release:** if the repo has release tags but none of them is an ancestor, it is skipped with a note. If there are no release tags at all, a real first release must set `CHECK_BASE_REF_FIRST_RELEASE=1`.
- `tests/test_release_base_ref.py` tests it. The compare runs only when `AAD_CHECK_COMPOSE` is set.
