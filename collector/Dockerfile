# Collector runtime image (idea#461). Official python:3.12-slim-bookworm
# (the same digest compose used in 1.3) plus openssh-client, netcat-openbsd
# and tzdata. Compose bind-mounts ./collector at /app, so this image does
# not COPY the app tree. GET /api/v1/health still reads
# collector/build-info.json from the bundle (script/write-build-info.sh).
# entrypoint.sh never installs packages at start.
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-client netcat-openbsd tzdata \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
