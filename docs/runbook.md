# Runbook — field usage dashboard (idea only)

## Install

Install onto idea's **system disk** with `installApp`. Do not install on a school kit. Proof installs go on idea03 or idea04 first, never on golden idea01 and never on idea until Koen says so.

The Engine assigns `${port}` in the instance `.env`. The web entrypoint refuses 80, 3333, 3334 and 8081.

The web image is a multi-stage build (`web/Dockerfile`): a digest-pinned `node:22-bookworm-slim` stage runs `corepack`-pinned `pnpm install --frozen-lockfile && pnpm build` when `web/package.json` exists and copies `web/dist` into the nginx html root. If `web/package.json` is absent, the existing placeholder is served instead. nginx still proxies `/api/` to the collector and serves `index.html` at `/`.

`location /` keeps the SPA fallback (`try_files $uri /index.html`). Missing files under `/assets/` return 404 (`location /assets/ { try_files $uri =404; }`) so a stale hashed bundle URL is not served as the app shell. There is no nginx-config test harness that runs nginx; `tests/test_packaging.py` checks these directives in `web/nginx.conf`.

## Packaging (U-10 approved)

The web image is published to `ghcr.io/koenswings/usage-dashboard-web` as
a public package, pinned in compose as
`ghcr.io/koenswings/usage-dashboard-web:1.0@sha256:<digest>`. Engine
`installApp` runs `docker pull` on every compose image; the public
digest-pin is what lets idea pull without credentials. The tar-in-bundle
fallback (measured 25,836,544 bytes / 24.6 MiB) is kept for offline App
Disks. How `/health` gets `commit` without an instance `.env` hack is in
`docs/packaging.md`.

Build (and only with `--push`, publish) with `script/publish-web-image.sh`.
That tags both `:1.0` and `:1.0-<shortsha>`. After a push, make the
package public, confirm an anonymous `docker manifest inspect` of
`ghcr.io/koenswings/usage-dashboard-web:1.0` lists `linux` / `arm64`,
then run `script/pin-web-digest.sh` and
`script/check-compose.mjs --release compose.yaml`.
`compose.web-ghcr.example.yaml` shows the intended `web:` service
(`repo:tag@sha256:digest`, no `build:` block).

The tar-fallback e2e test (`script/e2e-tar-fallback.sh`) and the host-side
export ingest (`script/ingest-usage-export.py`) are documented in
`docs/packaging.md`. On a claimed idea03, after the System Disk is
registered with the outside `IDEA_CONFIG_FILE`:

```sh
script/e2e-tar-fallback.sh --keep --ingest-history
```

`--keep` leaves the instance running. `--ingest-history` re-ingests the
quarantined usage tree (read-only of the original) plus a live
`since 2026-10-01` export, without writing `/var/lib/idea/usage`.

## Secrets

| Path | What | Backup |
|---|---|---|
| `./data/keys/pull_key` | usage-pull private key, mode 0600 | idea's encrypted Borg only (`x-app.backup.exclude: keys`) |
| `./data/tailscale/` | sidecar Tailscale state | idea's encrypted Borg only (`exclude: tailscale`) |
| instance `.env` `TS_AUTHKEY` | tagged, non-ephemeral auth key for `tag:idea-hub` | Engine instance env (not this repo) |
| `./data/operators.json` | salted PBKDF2 hashes for `koen` and `marco` (mode 0640) | instance data (hashes only) |
| `IDEA_USAGE_KOEN_PASSWORD` | first-run seed for Koen's login (compose default `koen911!`) | instance env |
| `IDEA_USAGE_MARCO_PASSWORD` | first-run seed for Marco's login (compose default `marco911!`) | instance env |

Operator login is documented in `docs/accounts.md`. Atlas installs the matching public key on each kit as helper v7 (`/etc/ssh/idea_usage_keys/pi`), pinned `from=` the sidecar's own Tailscale IPv4, forced command `/usr/local/sbin/idea-usage-export`. Never paste a key into chat or git.

If sidecar state is lost, Koen re-registers the node and sets its previous 100.x IPv4 in the Tailscale admin console so the kits' `from=` lines keep working (idea#375).

## Registry

`./data/registry.json`:

```json
{
  "kits": [
    {
      "engine": "happy-zebra",
      "tailscaleName": "happy-zebra",
      "school": "Nharira",
      "deploymentId": "dep-nharira",
      "timezone": "Africa/Harare",
      "note": "own apps + Demo"
    }
  ]
}
```

`timezone` is optional IANA. Without it the API labels ticks as `kit local time (UTC±offset)` from the latest presence sample.

## Restore

1. Restore `./data/usage.sqlite` from a `VACUUM INTO` snapshot under `./data/backup/` or from idea's Borg copy of App data.
2. Restore `./data/keys/pull_key` and `./data/tailscale/` only from idea's encrypted Borg.
3. Restart the App. The collector opens SQLite in WAL mode and keeps serving the last stored data if Tailscale is down.

## Known limits

When a monitored kit Engine is used as the test host (as on idea03 for idea#416), the collector cannot pull from its own host. The helper v7 key has the restriction `from=100.64.0.0/10`, and the container's source address is on the Docker bridge (`172.x`), so for the proof the host's data was loaded with a host-side plain-SSH pull.

This is deliberately not fixed. In production the dashboard runs on idea, which is not a monitored kit: it isn't tagged `tag:idea` and has no idea-usage export. Widening `from=` would weaken the key restriction for no production gain. The real path is the Tailscale sidecar with the `tag:idea-hub` key (pending).

The dashboard must not be installed on a monitored kit Engine.
