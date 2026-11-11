# Optional baked image. The compose file uses official python:3.12-slim-bookworm
# plus collector/entrypoint.sh (no image is published for 1.0).
FROM python:3.12-slim-bookworm
ARG USAGE_DASHBOARD_VERSION=1.0
ARG COMMIT=
ARG USAGE_DASHBOARD_COMMIT=
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-client netcat-openbsd \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /etc/idea-usage \
 && COMMIT_VAL="${COMMIT:-$USAGE_DASHBOARD_COMMIT}" \
 && printf '{"version":"%s","commit":"%s"}\n' \
      "$USAGE_DASHBOARD_VERSION" "$COMMIT_VAL" \
      > /etc/idea-usage/build-info.json
WORKDIR /app
COPY src /app/src
COPY scripts /app/scripts
COPY entrypoint.sh /app/entrypoint.sh
ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
