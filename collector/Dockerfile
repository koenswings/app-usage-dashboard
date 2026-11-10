# Optional baked image. The compose file uses official python:3.12-slim-bookworm
# plus collector/entrypoint.sh (no image is published for 1.0).
FROM python:3.12-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-client netcat-openbsd \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY src /app/src
COPY entrypoint.sh /app/entrypoint.sh
ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
