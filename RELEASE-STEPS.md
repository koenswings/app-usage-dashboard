# Release steps for usage-dashboard 1.6

Do **not** run these commands as part of the `kid/justice-operator` PR work.
They are for after the PR is merged to `main` and Koen has OK'd a release.
This file does not create or push a tag, and it does not build or publish
an image.

## Proposed tag

`1.6` (lightweight `<major>.<minor>` tag, same convention as `1.1`–`1.5`).
Tag the merge commit on `main`, not this feature-branch head.

## Image rebuild: not needed

The 1.6 change lives in:

- bind-mounted collector Python (`./collector` → `/app`), including
  `ALLOWED_OPERATORS` and the seed from `IDEA_USAGE_JUSTICE_PASSWORD`
- `compose.yaml` env passthrough and `x-app.version` / labels
- docs and tests

It does **not** live in the web or collector images. Keep the existing pins:

- `ghcr.io/koenswings/usage-dashboard-web:1.3@sha256:6ec777fb89b84cae93cc592b5cb96b9dea070c71cb25e892a8294af3f10f5dfc`
- `ghcr.io/koenswings/usage-dashboard-collector:1.4@sha256:dd2ff032e15ba54da53f16ee54c43cad11a61b55ef8580e117142fe01fbee241`

Do not run `script/publish-web-image.sh` or `script/publish-collector-image.sh`.
Do not `docker push` to ghcr. Do not retag or rebuild those images.

## After merge: tag only

On a full clone with tags (not a shallow clone), after the PR is merged:

```sh
git fetch origin --tags
git checkout main
git pull --ff-only origin main
# Confirm HEAD is the merge (or squash) commit of the justice-operator PR
# and that compose x-app.version is 1.6:
git log -1 --oneline
python3 - <<'PY'
from pathlib import Path
import re, sys
text = Path("compose.yaml").read_text()
v = re.search(r'(?m)^  version: "([^"]+)"$', text).group(1)
sys.exit(0 if v == "1.6" else 1)
PY

# Optional: compare compose against the previous release tag (1.5)
# AAD_CHECK_COMPOSE=<agent-app-dev>/script/check-compose.mjs script/check-base-ref.sh

# Lightweight tag, same as 1.1–1.5. Do not use -f. Do not tag until review says so.
git tag 1.6
git push origin 1.6
```

Then build the App bundle from that tag (still not a deploy):

```sh
git checkout 1.6
script/build-release-bundle.sh \
  --build-app-bundle <agent-app-dev>/script/build-app-bundle.sh \
  --disk-root <root> --ref 1.6
```

Do not deploy to production idea (instance `vsd0acgun2mmeg573zw`) until Koen
has OK'd it. Do not touch live `registry.json`.

## If a later change does need an arm64 image (not for 1.6)

Only if a future release actually changes the web or collector image, build
on a **claimed ARM64 pool Pi** with a **throwaway** `docker-container` buildx
builder. Never use the shared default builder. Do not `buildx prune`. Pause
the buildkit container if the Pi goes above 75 °C. Remove the throwaway
builder afterwards.

Example (collector). Pick a unique name; do not reuse a shared builder:

```sh
B=kid-collector-1.x-$(date +%Y%m%dT%H%M%S)
docker buildx create --name "$B" --driver docker-container
docker buildx use "$B"

# Preferred: the repo script (it already reads x-app.version). Add --push
# only when a publish is actually approved. Without --push it only makes a
# local test tag usage-dashboard-collector:local-<shortsha>.
# script/publish-collector-image.sh
# script/publish-collector-image.sh --push
# script/publish-collector-image.sh --push --export-tar <services-dir>

# Tar-only arm64 load (no ghcr push), matching script/publish-collector-image.sh:
docker buildx build --builder "$B" --platform linux/arm64 \
  --provenance=false --sbom=false --load \
  -f collector/Dockerfile \
  -t ghcr.io/koenswings/usage-dashboard-collector:<x-app.version> \
  --metadata-file /tmp/collector-buildx-meta.json \
  --progress=plain collector

docker buildx rm "$B"

# Then export + verify a service tar, and pin compose with
# script/pin-collector-digest.sh --digest sha256:<64-hex>
# from the buildx metadata containerimage.digest (or image Id on a
# single-platform --load). See docs/packaging.md.

# Web, if that image actually changed:
# B=kid-web-1.x-$(date +%Y%m%dT%H%M%S)
# docker buildx create --name "$B" --driver docker-container
# script/publish-web-image.sh          # local test only
# script/publish-web-image.sh --push   # only when approved
# docker buildx rm "$B"
```

None of the image commands above are part of the 1.6 justice-operator release.
