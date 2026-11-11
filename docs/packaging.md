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
it. Publishing to `ghcr.io` needs Koen's yes ([idea#375](https://github.com/koenswings/idea/issues/375) U-10).

This document covers the two paths prepared while U-10 is pending, and how
`GET /api/v1/health` reports the git commit without an instance `.env` hack.

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

## Pending U-10: publish to ghcr

`script/publish-web-image.sh` builds `linux/arm64` with buildx:

```
ghcr.io/koenswings/usage-dashboard-web:<x-app.version>-<shortsha>
```

`<shortsha>` is `git rev-parse --short=12 HEAD`. The tag shape follows
[app-kolibri-channel-builder](https://github.com/koenswings/app-kolibri-channel-builder)
(`ghcr.io/koenswings/<image>:<version>`) with a per-commit suffix so two
builds of App version 1.0 do not collide.

The script passes `--build-arg COMMIT=<full sha>` and prints `digest:` plus
a ready-to-paste `pin:` line. It pushes **only** when invoked with an
explicit `--push`. Do not run `--push` until U-10 is approved.

After a successful publish (and not before):

1. Confirm the image is arm64:

   ```sh
   docker manifest inspect \
     "ghcr.io/koenswings/usage-dashboard-web:1.0-$(git rev-parse --short=12 HEAD)"
   ```

   The response must list `linux` / `arm64` (a single-platform arm64
   manifest or an index that includes that platform). The digest must match
   the script's `digest:` line.

2. Edit the `web:` service in `compose.yaml` as shown in
   `compose.web-ghcr.example.yaml`: set

   ```yaml
   image: ghcr.io/koenswings/usage-dashboard-web:1.0-<shortsha>@sha256:<digest>
   ```

   and drop `build:` and `pull_policy: never`. Use `repo:tag@sha256:digest`,
   not `repo@sha256:digest`. Engine idea#322 `saveName()` rejects a
   digest-only pin so `docker image load` keeps a named tag.

3. `script/check-compose.mjs --release compose.yaml` must pass. It fails
   while `DIGEST_PLACEHOLDER`, `SHORTSHA`, or `<DIGEST>` remains, if `web`
   still has a `build:` block, or if the image is not the digest-pinned
   ghcr form above.

Until that edit lands, `compose.yaml` keeps the local `build:` path so a
developer (or a tar-in-bundle fallback) can still produce
`usage-dashboard-web:1.0`.

## Fallback: ship a docker-save tar on the App Disk

If Koen says no to ghcr, ship the image as a tar next to the App bundle.
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

Prefer the ghcr digest-pin once U-10 is approved. Keep this fallback
documented in case Koen says no.
