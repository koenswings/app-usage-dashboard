# Packaging the web image

The web image is published as `ghcr.io/koenswings/usage-dashboard-web` and
pinned in `compose.yaml` as `repo:tag@sha256:<digest>`
(`ghcr.io/koenswings/usage-dashboard-web:1.0@sha256:…`). The Engine's
`installApp` / `buildInstance` pulls every compose `image:` by that full ref,
tags it `repo:tag` and saves it to the disk's `services/` directory (see
`buildImageSteps` and `serviceImageTarPath` in Engine `ImageRef.ts` /
`Instance.ts`). Every start loads those tars again.

This document covers the ghcr publish path, the exact-pin tar export and its
verification (idea#445), the pin-change runbook, the tar-in-bundle fallback
kept for offline installs, and how `GET /api/v1/health` reports the git
commit without an instance `.env` hack.

## How `/health` gets `commit`

`GET /api/v1/health` is served by the **collector**, not the web container.
The collector runs a baked image (`ghcr.io/koenswings/usage-dashboard-collector`,
python:3.12-slim-bookworm plus openssh-client, netcat-openbsd and tzdata)
with `./collector` bind-mounted at `/app`. Baking `COMMIT` into the web
image or into the collector image does not change what `/health` returns.

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
`SHA256SUMS`, and has no per-app hook. An untracked checkout copy of
`collector/build-info.json` is **not** included (the path is gitignored so a
stale SHA is never committed). So build the bundle through the per-app wrapper
`script/build-release-bundle.sh` (idea#443), which leaves agent-app-dev
unchanged:

1. clones the checkout's HEAD commit and its tags into a throwaway dir;
2. writes `collector/build-info.json` there with `write-build-info.sh`
   (`{"version": <x-app.version>, "commit": <full HEAD sha>}`);
3. `git add -f`s it in the throwaway clone's **index only** (HEAD is still the
   tag commit, so the tag==HEAD check holds and `git ls-files` now lists it);
4. runs `build-app-bundle.sh`, whose `SHA256SUMS` then covers the file;
5. checks the bundle: the file is there, listed in `SHA256SUMS`, holds the
   commit and version, `sha256sum -c` passes, and `check-bundle-safe.py`
   passes (below).

```sh
git checkout 1.1
script/build-release-bundle.sh \
  --build-app-bundle <agent-app-dev>/script/build-app-bundle.sh \
  --disk-root <root> --ref 1.1
```

`--ref` must equal `x-app.version`. The same commit always gives the same
`build-info.json` bytes. With `ALLOW_UNTAGGED=1` the dev bundle
(`0.0-dev+<sha12>`) still carries `"version": "<x-app.version>"`.

### No live state in the bundle (`check-bundle-safe.py`)

updateApp's Swap (`copyBundle`, agent-engine-dev `UpdateApp.ts:133-137` on
main, `:152-156` on #448) copies every top-level name of the bundle over
`instances/<id>/` with overwrite, except `.env`, `SHA256SUMS` and `.idea-*`.
It is not exclude-aware. A bundle that shipped `data/` (even an empty
`data/tailscale`) would overwrite the hub's live state after the snapshot.
`script/check-bundle-safe.py <apps/<appId>>` (and `--tree <checkout>`) fails
on a top-level `data/`, a `.env`, or any path in `x-app.backup.exclude` /
`hookExclude` (normalised like the Engine), and on a `SHA256SUMS` that is
empty, does not list `compose.yaml`, or misses a file.

The web image also accepts `--build-arg COMMIT=<full sha>` and writes
`/etc/idea-usage/build-info.json` inside the nginx image. That identifies
the published web image; the collector does not read it.

## Release 1.1 (idea#443)

1.1 is the first release with `x-app.backup.method: hook` and the idea#446
`x-app.backup.verify` lists. The web image did not change, so 1.1 keeps the
published pin `ghcr.io/koenswings/usage-dashboard-web:1.0@sha256:9b5501f0…`
(no republish). Its tar name stays `ghcr.io_koenswings_usage-dashboard-web:1.0.tar`,
so a disk that already holds a `MATCH` tar for that pin needs no new web tar.
A later web change would publish `:<x-app.version>` and follow the pin-change
runbook below.

`verify.present` / `verify.absent` must hold for a hook archive **and** a
`HOOK_FALLBACK` short-stop archive, because an archive does not record which
one it was (Steve, idea#446). A fallback archive packs the live
`data/usage.sqlite` and has no dump; a hook archive has the dump
`data/backup/usage.sqlite` and no live db. So neither is listed.
`check-compose.mjs` refuses either in `present` or `absent`, a bare name in
`present` (a bare name means `data/<name>`, so `compose.yaml` would check
`data/compose.yaml`), and with `--release` requires the block when the
method is `hook`.

Bundle: `script/build-release-bundle.sh --ref 1.1` (wrapping agent-app-dev
`build-app-bundle.sh`) from a checkout of the `1.1` tag. It only bundles from
a `<major>.<minor>` tag at HEAD.

Bundle stick (Steve, idea#443): the Engine docks a disk only with a valid
`META.yaml` at the partition root (a non-empty mapping;
`src/monitors/mounts.ts isValidIdeaMetaFile`, `usbDeviceMonitor.ts:283-285`),
and agent-app-dev `check-app-disk-tree.sh` also wants `diskId`, `diskName`,
`created` and `lastDocked` (epoch ms; `src/data/Meta.ts DiskMeta`). It is an
App Disk because `apps/` exists (`Disk.ts:609-617`). The offer needs
`apps/usage-dashboard-1.1/SHA256SUMS` non-empty and listing a bare
`compose.yaml` (bundle-relative; `UpdateApp.ts sumsLookUsable`); updateApp
runs `cd apps/<appId> && sha256sum --check --strict SHA256SUMS`. The stick's `services/*.tar` are not used:
the start loads images only from idea03's own `/services` or skips the load
when the pin is local (`Instance.ts:1402-1426`, `674-700`).

Checks on idea03: `script/release/i443-update-checks.sh pre|post` (read-only,
inside someone else's claim, evidence only under `/home/pi/kid-evidence/`).
See `--help` for the check list.

## Publish to ghcr (U-10 approved)

Koen approved publishing on 11 Nov 2026 (Europe/Brussels). The image
is `ghcr.io/koenswings/usage-dashboard-web`. The package must be
**public** so idea can `docker pull` it without credentials.

`script/publish-web-image.sh --push` builds `linux/arm64` with buildx and
pushes two tags:

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
with an explicit `--push`. Add `--export-tar <dir>` to also write the
tar of the new pin (see "Exact-pin tar export" below).

Without `--push` the script makes a **local test build** tagged only
`usage-dashboard-web:local-<shortsha>`. Local builds never get a
`ghcr.io/…` name or a published tag (`:1.0`, `:1.0-<shortsha>`), so they
can't shadow the pinned image, be mistaken for it, or end up in a
`services/` tar (idea#445). Their digest is not a pin.

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

5. Follow the **pin-change runbook** below on every disk that already
   holds the App. `pin-web-digest.sh` prints it at the end of every run.

## Exact-pin tar export (idea#445)

```sh
script/publish-web-image.sh --export-tar <dir>                  # pin from compose.yaml web
script/publish-web-image.sh --export-tar <dir> --pin <repo:tag@sha256:…>
script/publish-web-image.sh --push --export-tar <dir>           # the pin just pushed
```

This does exactly what the Engine's install path does, and nothing else:

1. `docker image pull --platform linux/arm64 <pin>`
2. `docker image tag <pin> <repo:tag>`
3. `docker save <repo:tag> > <dir>/<tar name>.partial` (a plain save, never `--platform`)
4. `script/verify-service-tar.sh --tar <…>.partial --image <pin>`
5. `mv` of the `.partial` file to its real name (same directory, so the rename is atomic)

A local build is never saved. If the verify step fails, the `.partial` file
stays where it is and nothing gets the real name. If the real tar already
exists and matches the pin, it is left alone. If it exists but doesn't match,
the export stops: quarantine the old tar first (runbook step 1).

The tar name is the Engine's `serviceImageTarName(ref)`: `saveName(ref)`
(`repo:tag`, digest stripped) with every `/` replaced by `_`, plus `.tar`. For
the web pin that is `ghcr.io_koenswings_usage-dashboard-web:1.0.tar`.
`script/verify-service-tar.sh --print-tar-name <ref>` prints it.

## Verify a service tar

```sh
script/verify-service-tar.sh <compose.yaml> <services-dir> [--service web]
script/verify-service-tar.sh --tar <file.tar> --image <repo:tag@sha256:…>
```

It is read-only and needs no Docker: it opens the tar with Python's `tarfile`
and reads `index.json`, `manifest.json` and the top-level blob, without
extracting anything. For every digest-pinned compose image it checks
`<services-dir>/<serviceImageTarName>`. Images pinned by tag only are skipped
(`SKIP`).

The verdict is a line-for-line port of the Engine's pre-load check,
`checkServiceTarPin` in agent-engine-dev `src/data/ImageRef.ts` (#327), so
the script and the Engine always agree. The **named entry** is the
`index.json` descriptor whose `io.containerd.image.name` (or a repo-like
`org.opencontainers.image.ref.name`, one containing `/` or `:`) equals
`repo:tag`, with `docker.io/library/` normalised. A single unnamed entry
counts as named. `manifest.json` `RepoTags` must also name `repo:tag`.

| State | When | Engine on start |
|---|---|---|
| `MATCH` `layout=index` | the named entry is an image index and its digest == the pin; **or** a bare `index.json` that is itself an image index, with no name annotation, whose bytes hash to the pin | loads it (if the pin isn't already local) |
| `MATCH` `layout=manifest` | the named entry is a single manifest whose digest == the pin (a one-platform image with no index, such as the old `ef48f1fa`) | loads it |
| `MISMATCH` `layout=index` | the named image index has another digest (a stale tar) | **quarantines** it, never loads it |
| `MISMATCH` `layout=manifest` | the tar holds only a platform manifest while the pin is something else (usually the index); e.g. `docker save --platform` or a classic-store save. **Always refused** (Steve's idea#445 decision): after `docker load`, `repo:tag@<index>` doesn't resolve offline | **quarantines** it |
| `UNREADABLE` | no `index.json` or `manifest.json`, or not JSON; no entries; no entry named `repo:tag`; `RepoTags` without `repo:tag`; the same name on two different digests; no sha256 digest; a top-level blob that's missing or doesn't hash to its digest; an unknown media type; not a tar | doesn't quarantine it; fails the start only if the pin isn't local |
| `MISSING` | no tar under that name (a pre-#322 digest-named tar is called out) | warns, continues |

There's no override for `MISMATCH`.

Exit codes, worst state first: `1` = a `MISMATCH`, `3` = an `UNREADABLE`
tar, `4` = a `MISSING` tar, `0` = all `MATCH`, `2` = usage or compose error.
Each image prints one `STATE …` line (with `layout=` and `digest=` when
known), then a `summary:` line with the counts. For operators: `1` means the
Engine will quarantine that tar, so re-export it. `3` means look at the tar
by hand, because the Engine leaves it in place.

**Docker 29, containerd image store.** Plain `docker save repo:tag` on idea03
(Docker 29.4.0, `io.containerd.snapshotter.v1`) writes an OCI layout. Its
`index.json` has one entry: the image's top-level descriptor as pulled, with
`io.containerd.image.name=<repo:tag>`. The 11 Nov 10:51 tar of `ef48f1fa` is
an example: one `application/vnd.docker.distribution.manifest.v2+json` entry
with digest `ef48f1fa…` and its blob present. For an image pulled by its
index digest, the Engine's idea#322 notes (PR #296) record that a plain save
keeps the index (`.Id` = index digest). The first real save of `9b5501f0`
(Atlas's idea03 refresh) checks that with step 3 of the runbook below.

## Release 1.4 (idea#461)

1.4 fixes a first-boot crash: 1.3's collector ran `apt-get` in
`entrypoint.sh` to install `openssh-client`, `netcat-openbsd` and `tzdata`.
On a fresh install the collector shares the userspace Tailscale netns
(`network_mode: service:tailscale`, `TS_ACCEPT_DNS=false`) and cannot
resolve `deb.debian.org`, so the container exits 100 and health stays 502
(W2 hub move, 2026-11-12). 1.4 bakes those packages into a collector image
and the entrypoint never installs anything.

The image is `ghcr.io/koenswings/usage-dashboard-collector:1.4`, built on
a claimed arm64 pool Pi with a throwaway buildx builder (same tar-only
path as the 1.3 web image; see `script/publish-collector-image.sh`).
Compose pins `repo:tag@sha256:<digest>`. The service tar name is
`ghcr.io_koenswings_usage-dashboard-collector:1.4.tar` and goes in
`<diskRoot>/services/` or the System Disk `/services`, next to the
unchanged web tar (`ghcr.io_koenswings_usage-dashboard-web:1.3.tar` —
the 1.3 web pin is kept, as 1.1 kept the 1.0 web pin).

`updateApp` to 1.4 recreates the collector container and loads the new
tar. `./data` and `./data/tailscale` stay in place; do not copy, re-auth
or restart the Tailscale state or service. After the pin is filled,
`script/check-compose.mjs --release` requires every service (including
collector) to be digest-pinned with no `build:` block.

There is no data migration (`1.3→1.4`).

## Pin-change runbook

The tar name only depends on `repo:tag`, so when the pin moves, the old tar
keeps the same file name on every disk that already holds the App. Nothing
replaces it. An Engine start then loads the old tar, which moves `repo:tag`
back to the old image (idea#445). Whenever the web pin changes, on every Pi or
App Disk that already has this App, inside a fleet claim, with `<services>`
= `/services` on a System Disk or `<diskRoot>/services` on an App Disk:

1. **Quarantine the old tar** (move, never delete):
   `mv <services>/ghcr.io_koenswings_usage-dashboard-web:1.0.tar /home/pi/kid-quarantine/<run>/`
2. **Export a fresh tar of the pin**:
   `script/publish-web-image.sh --export-tar <services> --pin <pin>`
3. **Verify it**: `script/verify-service-tar.sh compose.yaml <services>`.
   Every pinned image must say `MATCH` (exit 0). Exit 1 (`MISMATCH`) means
   it's still stale: go back to step 1. Exit 3 (`UNREADABLE`) means inspect
   the tar.
4. **Point the local tag at the pin**:
   `docker tag <repo>@sha256:<digest> <repo>:<tag>`
5. **Do one Engine-driven start** (Console start or `startInstance`, not
   `docker compose up`, which resolves by digest and hides a stale tar).
   Then confirm that `docker image inspect <repo>:<tag> --format '{{.Id}}'`
   is the pinned digest (containerd store).

`script/pin-web-digest.sh` prints these steps, filled in with the new pin, at
the end of every run. With `--services-dir <dir>` it also runs step 3 for the
web service against that directory.

## Engine contract this relies on (idea#445, Axle)

The App-side tools make sure a disk only ever gets a tar that matches the pin.
The Engine side (agent-engine-dev, Axle) makes a stale tar harmless:

- `verifyServiceImageDigest` checks `repo@<digest>` (RepoDigests), not `repo:tag`.
- A start skips the tar load when the pinned digest is already local, and points `repo:tag` back at it.
- Before loading a tar, the Engine checks that its digest equals the pin. A mismatched tar is quarantined, not loaded.
- `installApp` compares an existing tar with the pin instead of skipping it with "already exists".
- copyApp, moveApp and restoreApp name tars with `serviceImageTarName`, the same as install. Until then, they silently skip pinned `@sha256` refs.

`verify-service-tar.sh` mirrors that pre-load check (`checkServiceTarPin`,
agent-engine-dev #327). If the Engine rule changes, change the script with it.

## Fallback: ship a docker-save tar on the App Disk

For an offline App Disk, or if ghcr is unreachable, ship the image as a tar
next to the App bundle. The Engine's existing-tar path looks for

```
<diskRoot>/services/<serviceImageTarName(ref)>
```

For the compose pin `ghcr.io/koenswings/usage-dashboard-web:1.0@sha256:…` that is:

```
<diskRoot>/services/ghcr.io_koenswings_usage-dashboard-web:1.0.tar
```

(`saveName()` strips the digest, then every `/` becomes `_`). `<diskRoot>` is
the App Disk root (`/apps`, `/instances`, `/services`), not a folder inside
`apps/usage-dashboard-1.0/`. On a GitHub `installApp` onto the system disk the
same path is `/services/ghcr.io_koenswings_usage-dashboard-web:1.0.tar`.

Produce it **only** with the exact-pin export, on any host with Docker that
can reach ghcr:

```sh
script/publish-web-image.sh --export-tar <diskRoot>/services
script/verify-service-tar.sh compose.yaml <diskRoot>/services
```

Never `docker build` + `docker save` a local build under the pinned name. Its
digest is never the ghcr pin, so the Engine's digest check refuses it, and a
stale or local tar under that name would move `repo:tag` off the pin on the
next Engine start.

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
  re-walk already proved the Engine accepts this exact file name.
- **Adds ~25 MiB** to every App Disk that carries the dashboard.
- The tar name is `repo:tag` only, so it is reused for the whole 1.0
  line. `build-app-bundle.sh` and the Engine's install path don't overwrite
  an existing tar. After a pin change, the old tar has to be quarantined
  and re-exported (pin-change runbook). `verify-service-tar.sh` catches a
  stale one.
- The tar only carries linux/arm64 content (the index plus its arm64
  manifest). That is what the kits need; it won't run on an amd64
  developer laptop.
- A GitHub `installApp` without the tar pulls the pin from ghcr (public).

Prefer the ghcr digest-pin once the image is published and compose.yaml is pinned. Keep this fallback for offline App Disks
and for a GitHub `installApp` that cannot reach ghcr.

## Tar-fallback e2e test (pool Pi)

`script/e2e-tar-fallback.sh` is the end-to-end `installApp` proof of this
fallback. It is meant to run as `pi` on a claimed ARM64 pool Pi (idea03, or
idea04). It refuses to start unless `hostname` is one of those two and the
fleet-state claim is Kid.

It stages `apps/usage-dashboard-1.0/` from `git ls-files` and injects
`collector/build-info.json` with `script/write-build-info.sh`. It then moves any
existing web tar aside and exports

```
/services/ghcr.io_koenswings_usage-dashboard-web:1.0.tar
```

with `script/publish-web-image.sh --export-tar /services --pin <compose pin>`
(never a local build; the script refuses an unpinned web image). It also saves
the other compose service tars the Engine will load
(`ghcr.io_koenswings_usage-dashboard-collector:<version>`,
`tailscale_tailscale:v1.88.3`) and runs
`script/verify-service-tar.sh compose.yaml /services` on all of them. `nginx:1.28-alpine` is only the web image
build base, not a compose service, so it is not saved as a service tar.
The names `repo:tag` and `repo@<pin>` are then removed (names only, no
`-f`), so `docker image load` of the tar is the only way they come back. If a
container (such as the live hub) uses the pinned image, nothing is removed and
the run notes that the load was not forced. After the Engine install it
asserts that `repo@<pin>` exists and that `repo:tag` resolves to the same image
with `repo@<pin>` in its RepoDigests. Teardown never untags the web image. The script queues

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
