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

## idea-hub identity

The App owns the idea-hub Tailscale identity (`idea-hub`, `tag:idea-hub`).
Hostname is `idea-hub`. Compose already sets
`TS_EXTRA_ARGS=--advertise-tags=tag:idea-hub`. The live node key lives only
in the App's `./data/tailscale`.

To hand the identity to this App (or later to another host), **move** that
state directory — never copy it. Whichever container last starts with a
given copy owns the live node key; any leftover copy then goes stale
(`NeedsLogin` / `nodeKeyExpired`). Only one idea-hub container may ever
exist. Do not run a standalone `idea-hub-sidecar` at the same time as this
App's sidecar: the standalone sidecar is retired.

Never start an older copy of the state after this App's sidecar has run:
it re-registers a stale node key and the tailnet then marks idea-hub
Expired (this happened on 2026-11-11). Removing or stopping the App only
stops its containers and keeps `./data/tailscale` in place; never run
`tailscale logout` or `tailscale down` on teardown. Install the App with
the moved state already in `./data/tailscale`, so the sidecar never starts
empty (an empty start asks for a new login).

Compose persists sidecar state by setting `TS_STATE_DIR` to the bind-mount
target `/var/lib/tailscale` (`./data/tailscale` on the host),
`TS_AUTH_ONCE=true` so containerboot does not force `tailscale up` on every
start, and `TS_KUBE_SECRET` empty. `collector/sidecar-wrap.sh` refuses to
start if `./data/tailscale` has no persisted node key unless `TS_AUTHKEY`
is set. Production `tailscaled.state` files base64-encode each persist
profile, so `PrivateNodeKey` is often not visible in plaintext; the wrapper
decodes those blobs when `python3` is available and otherwise treats a
state file of 200 bytes or more as persisted (a machinekey-only start is
typically under 200 bytes).

When moving existing state, leave `TS_AUTHKEY` empty and do not open a
login URL. After the sidecar is Running, confirm the on-disk nodekey still
matches control:

```sh
script/check-idea-hub-nodekey.py --state-dir ./data/tailscale --socket /var/run/tailscale/tailscaled.sock
```

(Use `docker exec` of the sidecar for the socket, or pass a saved
`status --json` file with `--status-json`. The script prints public
prefixes only; it never prints private keys.)

### One-join when Koen issues a fresh single-use key

If sidecar state is lost, Koen issues a **single-use** auth key and (if
needed) sets the previous 100.x IPv4 in the Tailscale admin console so the
kits' `from=` lines keep working (idea#375). The key must never be pasted
into chat, a ticket, or git.

The key must be created with **`tag:idea-hub` ticked** (the only tag) and
`tag:idea-hub` must be listed in Tailscale ACL **`tagOwners`** for the
identity that creates the key. Compose already passes
`--advertise-tags=tag:idea-hub`. A key that control rejects with
`requested tags [tag:idea-hub] are invalid or not permitted` is **burned**:
do not retry it, even if the wrapper stopped after one attempt. Mint a new
single-use key after fixing the tag tick and `tagOwners`.

`collector/sidecar-wrap.sh` makes **exactly one** keyed join attempt. If
`tailscale up` fails or the node is not Running and authorized within
`TS_JOIN_TIMEOUT` seconds (default 90), the wrapper writes
`./data/tailscale/authkey-join-blocked` and exits non-zero without looping
or starting containerboot again with the key. Compose `restart:
unless-stopped` may restart the container; the marker then blocks any
further keyed start until an operator deletes that file (or moves existing
idea-hub state into place). Delete the marker only when you are ready to
try a **new** key.

On the host that has the instance, in a shell that will not be logged:

1. Export the key in that shell only: `export TS_AUTHKEY=...` (do not put
   it on a command line that will be stored in history if you can avoid it).
2. Write it into the instance `.env`, run the one start, and strip the key
   from the env file afterwards — success or failure. `attempt` always
   runs `remove-env` (via an EXIT trap):

```sh
script/join-idea-hub-once.sh attempt --env-file /instances/<instance-id>/.env -- \
  node engine-ctl.mjs send startInstance <instance-id> <system-disk-id>
```

   (`write-env` / `remove-env` remain available if the start has to be
   issued from another shell; then call `remove-env` yourself immediately
   after that single attempt, whether it succeeded or failed.)
   `TS_AUTH_ONCE=true` and the wrapper allow this empty-state start
   because `TS_AUTHKEY` is set. Do not open a login URL.
3. When the sidecar `BackendState` is `Running` and there is no `AuthURL`,
   verify the on-disk nodekey matches `Self.PublicKey`:

```sh
script/join-idea-hub-once.sh verify --state-dir /instances/<instance-id>/data/tailscale --socket /var/run/tailscale/tailscaled.sock
```

   (`--socket` is the socket inside the sidecar; `docker exec` the
   `check-idea-hub-nodekey.py` equivalent, or write `status --json` out
   and pass `--status-json`.) Expect `match=true`.
4. Recreate or stop+start the instance so the container environment no
   longer holds `TS_AUTHKEY` (the env file was already stripped by
   `attempt` / `remove-env`). Existing state is present, so the wrapper
   starts without a key. Verify again with the same `verify` command so
   the on-disk nodekey still matches after the restart.
5. If the join fails, stop the instance, confirm `TS_AUTHKEY` is gone from
   the env file, shred any temp key file on the host, and leave the
   `authkey-join-blocked` marker in place until a new key is ready. Do not
   retry the burned key.

## Secrets

| Path | What | Backup |
|---|---|---|
| `./data/keys/pull_key` | usage-pull private key, mode 0600 | idea's encrypted Borg only (`x-app.backup.exclude: keys`) |
| `./data/tailscale/` | sidecar Tailscale state | idea's encrypted Borg only (`exclude: tailscale`) |
| `./data/tailscale-run/` | LocalAPI unix-socket dir (not the node key) | excluded from a normal Engine backup (`exclude: tailscale-run`); runtime only |
| instance `.env` `TS_AUTHKEY` | optional first-time auth key; leave empty when moving existing idea-hub state | Engine instance env (not this repo) |
| `./data/operators.json` | salted PBKDF2 hashes for `koen` and `marco` (mode 0640) | instance data (hashes only) |
| `IDEA_USAGE_KOEN_PASSWORD` | first-run seed for Koen's login (compose default `koen911!`) | instance env |
| `IDEA_USAGE_MARCO_PASSWORD` | first-run seed for Marco's login (compose default `marco911!`) | instance env |

Operator login is documented in `docs/accounts.md`. Atlas installs the matching public key on each kit as helper v7 (`/etc/ssh/idea_usage_keys/pi`), pinned `from=` the sidecar's own Tailscale IPv4, forced command `/usr/local/sbin/idea-usage-export`. Never paste a key into chat or git.

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

## Daily SQLite snapshots

The collector writes one consistent `VACUUM INTO` copy per **UTC** day to
`./data/backup/usage-YYYY-MM-DD.sqlite`. It decides whether today's copy is
due by looking at that filename, so a restart on the same UTC day does not
write a second file. The write is atomic: `VACUUM INTO` a temp file in the
same directory, then rename. A failure is logged on stderr and never stops
the collector loop.

Only files matching `usage-YYYY-MM-DD.sqlite` are pruned. The 14 newest UTC
dates are kept. Other files in `./data/backup` (for example
`i431-cleanup-*.sqlite`) are left alone. Leftover `*.tmp` files from a
crashed write are not treated as snapshots.

## Restore

1. Restore `./data/usage.sqlite` from a daily `VACUUM INTO` snapshot
   (`./data/backup/usage-YYYY-MM-DD.sqlite`) or from idea's Borg copy of App data.
2. Restore `./data/keys/pull_key` only from idea's encrypted Borg. **Move** (never copy) `./data/tailscale/` into place so only one live node-key copy exists.
3. Restart the App. The collector opens SQLite in WAL mode and keeps serving the last stored data if Tailscale is down.

## Known limits

When a monitored kit Engine is used as the test host (as on idea03 for idea#416), the collector cannot pull from its own host. The helper v7 key has the restriction `from=100.64.0.0/10`, and the container's source address is on the Docker bridge (`172.x`), so for the proof the host's data was loaded with a host-side plain-SSH pull.

This is deliberately not fixed. In production the dashboard runs on idea, which is not a monitored kit: it isn't tagged `tag:idea` and has no idea-usage export. Widening `from=` would weaken the key restriction for no production gain. The App owns the idea-hub sidecar (`tag:idea-hub`); kits pin `from=` to that node's Tailscale IPv4.

The dashboard must not be installed on a monitored kit Engine.
