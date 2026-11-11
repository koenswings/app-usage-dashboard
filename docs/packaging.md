# Packaging the web image

The Engine's `installApp` / `buildInstance` runs `docker image pull` on every
compose `image:` (see `serviceImageTarPath` in Engine `Instance.ts`). It skips
the pull only when a matching tar already exists under the disk's `services/`
directory.

`usage-dashboard-web:1.0` is a build-only image (`web/Dockerfile`,
`pull_policy: never`). A GitHub `installApp` of this branch therefore fails
unless the image is already present locally or a tar is waiting on the disk.
The idea03 re-walk worked by building the image on the Pi and saving
`/services/usage-dashboard-web:1.0.tar` so Engine's existing-tar path accepted
it. Publishing to `ghcr.io` was approved on 11 Nov 2026 (idea#375 U-10).

This document covers the ghcr publish path, the tar-in-bundle fallback
kept for offline installs, and how `GET /api/v1/health` reports the git
commit without an instance `.env` hack.

## How `/health` gets `commit`

`GET /api/v1/health` is served by the **collector**, not the web container.
The collector runs the stock `python:3.12-slim-bookworm` image with
`./collector` bind-mounted at `/app`. Baking `COMMIT` into the web image
(or into `collector/Dockerfile`, which compose does not use) does not change
what `/health` returns.

Resolution order (`collector/src/buildinfo.py`):

1. `USAGE_DASHBOARD_COMMIT` — optional override. An empty value is ignored,
   so compose may pass `${USAGE_DASHBOARD_COMMIT:-}` without shadowing the
   file. There is no need to set this in the instance `.env`.
2. `collector/build-info.json` mounted at `/app/build-info.json`, or
   `/etc/idea-usage/build-info.json` (used only if a custom collector image
   is built). `USAGE_DASHBOARD_BUILD_INFO` can point at another path.
3. The Engine bundle directory `usage-dashboard-<sha>` parsed from
   `/proc/self/mountinfo`. This does not fire when the bind mount is the
   instance path (`usage-dashboard-<instanceId>/collector`), which is what
   GitHub `installApp` actually mounts.

The clean option is (2) written at **App Disk bundle time**:
`script/write-build-info.sh` writes `collector/build-info.json` with
`{"version":"<x-app.version>","commit":"<full sha>"}`.

`build-app-bundle.sh` (agent-app-dev) copies only `git ls-files`, then writes
`SHA256SUMS`. An untracked checkout copy of `collector/build-info.json` is
**not** included (the path is gitignored so a stale SHA is never committed).
After the script copies the tree into `apps/<appId>/` and before it writes
`SHA256SUMS`:

```sh
script/write-build-info.sh --dest "$ROOT/apps/usage-dashboard-1.0" \
  --commit "$(git -C "$APP_DIR" rev-parse HEAD)"
```

Then let the bundle script checksum the new file. If you run
`write-build-info.sh` only in the git checkout, remember to inject the file
into the staged bundle as above.

The web image also accepts `--build-arg COMMIT=<full sha>` and writes
`/etc/idea-usage/build-info.json` inside the nginx image. That identifies
the published web image; the collector does not read it.

## Publish to ghcr (U-10 approved)

Koen approved publishing on 11 Nov 2026 (Europe/Brussels). The image
is `ghcr.io/koenswings/usage-dashboard-web`. The package must be
**public** so idea can `docker pull` it without credentials.

`script/publish-web-image.sh` builds `linux/arm64` with buildx and
tags both:

```
ghcr.io/koenswings/usage-dashboard-web:<x-app.version>
ghcr.io/koenswings/usage-dashboard-web:<x-app.version>-<shortsha>
```

`<shortsha>` is `git rev-parse --short=12 HEAD`. Compose pins the
stable `:1.0` tag by digest. The `:1.0-<shortsha>` tag is a
per-commit alias so two builds of App version 1.0 stay
distinguishable. The tag shape follows
[app-kolibri-channel-builder](https://github.com/koenswings/app-kolibri-channel-builder)
(`ghcr.io/koenswings/<image>:<version>`).

The script passes `--build-arg COMMIT=<full sha>` and prints `digest:`
plus a ready-to-paste `pin:` line. It pushes **only** when invoked
with an explicit `--push`.

Pushing requires a GitHub token with `write:packages` and
`read:packages`, and a `docker login ghcr.io` on the host that runs
`--push`. Refresh an existing `gh` login with:

```sh
gh auth refresh -s write:packages,read:packages
```

Then log docker into ghcr.io with that token (do not scrape a token
from an agent session). After a successful publish:

1. Make the package public (the first push creates it private):

   ```sh
   gh api --method PATCH -H "Accept: application/vnd.github+json" \
     /user/packages/container/usage-dashboard-web \
     -f visibility=public
   ```

   If that 404s, use
   `/users/koenswings/packages/container/usage-dashboard-web`
   instead.

2. Confirm an anonymous inspect sees `linux` / `arm64`:

   ```sh
   docker manifest inspect \
     ghcr.io/koenswings/usage-dashboard-web:1.0
   ```

   Run this from a host (or a `DOCKER_CONFIG` directory) that has no
   ghcr credentials, so the check is actually anonymous. The digest
   must match the script's `digest:` line.

3. Pin `compose.yaml` with `script/pin-web-digest.sh`. That inspects
   the published `:1.0` tag (`docker buildx imagetools inspect`,
   falling back to `docker manifest inspect`), verifies `linux/arm64`,
   and sets

   ```yaml
   image: ghcr.io/koenswings/usage-dashboard-web:1.0@sha256:<digest>
   ```

   dropping `build:` and `pull_policy: never` from `web`. Use
   `repo:tag@sha256:digest`, not `repo@sha256:digest`. Engine idea#322
   `saveName()` rejects a digest-only pin so `docker image load` keeps
   a named tag.

4. `script/check-compose.mjs --release compose.yaml` must pass. It fails
   while `DIGEST_PLACEHOLDER`, `SHORTSHA`, or `<DIGEST>` remains, if `web`
   still has a `build:` block, or if the image is not the digest-pinned
   ghcr form `ghcr.io/koenswings/usage-dashboard-web:1.0@sha256:<64 hex>`
   (a `:1.0-<shortsha>@sha256:…` pin is also accepted).

Until the digest is filled in, `compose.yaml` keeps the local `build:`
path so a developer (or the tar-in-bundle fallback) can still produce
`usage-dashboard-web:1.0`.

## Fallback: ship a docker-save tar on the App Disk

For an offline App Disk, or if ghcr is unreachable, ship the image as a tar next to the App bundle.
Engine's existing-tar path looks for

```
<diskRoot>/services/<image with every / replaced by _>.tar
```

For `image: usage-dashboard-web:1.0` that is:

```
<diskRoot>/services/usage-dashboard-web:1.0.tar
```

`<diskRoot>` is the App Disk root (`/apps`, `/instances`, `/services`), not
a folder inside `apps/usage-dashboard-1.0/`. `build-app-bundle.sh` already
writes service tars there (`save="${img%%@*}"`, then every `/` → `_`).
On a GitHub `installApp` onto the system disk the same path is
`/services/usage-dashboard-web:1.0.tar`.

Build (on an arm64 host, or with buildx `--platform linux/arm64`) and save:

```sh
COMMIT=$(git rev-parse HEAD)
docker build --platform linux/arm64 \
  --build-arg "COMMIT=$COMMIT" \
  -f web/Dockerfile -t usage-dashboard-web:1.0 .
docker save usage-dashboard-web:1.0 > services/usage-dashboard-web:1.0.tar
```

Put that file at `<diskRoot>/services/usage-dashboard-web:1.0.tar` before
`installApp`. Engine then prints that the image already exists and does not
`docker pull`.

### Size

docker/buildx was not available on the development box that prepared this
note, so the arm64 image was not rebuilt there. Two measurements instead:

| Source | Size |
|---|---|
| idea03 re-walk `docker save` tar, `stat` of `/services/usage-dashboard-web:1.0.tar` on 11 Nov 2026 (Europe/Brussels) | **25,836,544 bytes** (24.6 MiB) |
| `nginx:1.28-alpine@sha256:a8b39bd9…` linux/arm64 compressed layer sum (`crane manifest --platform linux/arm64`) | 25,776,585 bytes (config blob 12,312 bytes) |
| node-built `web/dist` (same assets as the re-walk: `index-DVXJ_KSc.js` / `index-CY24lz_s.css`) | 74,355 bytes |
| `web/nginx.conf` + `web/entrypoint.sh` | 821 bytes |

The idea03 tar is 59,959 bytes above the nginx arm64 compressed layers,
which matches a gzipped extra layer for `web/dist` plus compose files and
`docker save` metadata. Plan on about **25–26 MiB** per App Disk for this
tar.

### Tradeoffs versus ghcr

- **Works offline** and needs no registry permission (U-10). The idea03
  re-walk already proved Engine accepts this exact filename.
- **Adds ~25 MiB** to every App Disk that carries the dashboard.
- The local tag `usage-dashboard-web:1.0` is reused for the whole 1.0
  line. `build-app-bundle.sh` never overwrites an existing tar (image+tag
  names are treated as immutable releases). A later rebuild of the same
  tag will be ignored unless the old tar is removed first. The ghcr tag
  `1.0-<shortsha>` does not have that collision.
- The tar is a single-platform arm64 image. That is what the kits need;
  it will not run on an amd64 developer laptop.
- GitHub `installApp` without the tar still hits `docker pull
  usage-dashboard-web:1.0` and fails.

Prefer the ghcr digest-pin once the image is published and compose.yaml is pinned. Keep this fallback for offline App Disks
and for a GitHub `installApp` that cannot reach ghcr.

## Tar-fallback e2e test (pool Pi)

`script/e2e-tar-fallback.sh` is the end-to-end `installApp` proof of this
fallback. It is meant to run as `pi` on a claimed ARM64 pool Pi (idea03, or
idea04). It refuses to start unless `hostname` is one of those two and the
fleet-state claim is Kid.

It stages `apps/usage-dashboard-1.0/` from `git ls-files`, injects
`collector/build-info.json` with `script/write-build-info.sh`, builds the
arm64 web image (`docker build --platform linux/arm64`), saves

```
<diskRoot>/services/usage-dashboard-web:1.0.tar
```

plus the other compose service tars Engine will load (`python:3.12-slim-bookworm`,
`tailscale_tailscale:v1.88.3`). `nginx:1.28-alpine` is only the web image
build base, not a compose service, so it is not saved as a service tar.
The local `usage-dashboard-web:1.0` image is then removed so the only way it
can reappear is `docker image load` of the tar. The script queues

```
installApp usage-dashboard-1.0 <systemDiskId> --source <systemDiskId> --fresh --name usage-dashboard-tar-e2e
```

through the Engine Automerge command queue (`script/send-engine-command.mjs`),
the same Console path the earlier re-walk used, but on the **local-disk**
route so the staged `build-info.json` is what `/api/v1/health` reports.
(A GitHub `installApp usage-dashboard@<sha>` clone would not include that
gitignored file.) Engine 8241221 `stopInstance` needs `<instanceId> <diskId>`.

After health, `/`, and `/assets/x.js` assertions, the default path is
`stopInstance`, `removeInstance`, then `docker rm` (no `-v`) of any Exited
leftovers (idea#424; this is still required on Engine 8241221 even though
agent-engine-dev#311 changes compose-down behaviour — that change is not
deployed on idea03). Written tars and the staged bundle are moved to
`/home/pi/kid-quarantine/<run>/`, never deleted. Before/after snapshots
(`docker ps -a`, `docker images`, `pm2 ls`, `lsblk`, `losetup -a`) are
diffed.

`--keep` skips teardown and leaves the instance running. `--ingest-history
[<dir>]` (default `/home/pi/kid-quarantine/20261111T001400/usage`) copies
that tree to a scratch dir under the run folder, flattens `.archive/` day
directories into the scratch root, exports `since 2026-10-01` with
`IDEA_USAGE_ROOT` pointing at the scratch, and ingests the NDJSON into the
new instance with `script/ingest-usage-export.py` (the same host-side
`interpret_export` + `store_export` path as the earlier proofs). It then
ingests a live `since 2026-10-01` of `/var/lib/idea/usage` the same way
(read-only). It never writes `/var/lib/idea/usage` and never runs
`archive-and-clear`.

Dry-run, on any host, with no Docker and no Engine:

```sh
script/e2e-tar-fallback.sh --dry-run [--dest /tmp/tar-fallback-dry]
```

On idea03, after the System Disk is registered (`IDEA_CONFIG_FILE` pointing
at `/home/pi/kid-i416-installapp/engine-config-8241221.yaml`, `systemDiskSkip:
false`; do not edit the deployed Engine tree):

```sh
# as pi, from a checkout of this branch, with FLEET_STATE set at a file
# whose idea03.claim is Kid:
script/e2e-tar-fallback.sh --keep --ingest-history
```

Pause above 75 °C and resume below 65 °C. Never touch `/disks/sdb1`, Disk B,
the WD SSD, or the protected disk serials. Do not print credentials.
