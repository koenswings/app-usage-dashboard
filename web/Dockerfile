# Multi-stage web image: build Pixel's UI when web/package.json exists,
# otherwise copy the placeholder into the nginx html root.
# Base images are digest-pinned multi-arch indexes (idea#322).
# linux/arm64 verified 2026-11-11 (crane manifest inspect).
ARG NODE_IMAGE=node:22-bookworm-slim@sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d
ARG NGINX_IMAGE=nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236

FROM ${NODE_IMAGE} AS ui
ARG PNPM_VERSION=9.15.9
WORKDIR /build
COPY web/ /build/web/
RUN set -eu \
 && if [ -f /build/web/package.json ]; then \
      corepack enable \
      && corepack prepare "pnpm@${PNPM_VERSION}" --activate \
      && cd /build/web \
      && pnpm install --frozen-lockfile \
      && pnpm build \
      && test -f /build/web/dist/index.html; \
    else \
      mkdir -p /build/web/dist \
      && if [ -d /build/web/placeholder ]; then \
           cp -a /build/web/placeholder/. /build/web/dist/; \
         else \
           printf '%s\n' '<!DOCTYPE html><title>Field usage dashboard</title>' \
             > /build/web/dist/index.html; \
         fi; \
    fi

FROM ${NGINX_IMAGE}
COPY web/nginx.conf /etc/nginx/nginx.conf
COPY web/entrypoint.sh /entrypoint.sh
COPY --from=ui /build/web/dist /usr/share/nginx/html
EXPOSE 8080
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
