# Whole-repo china-abs image (pipeline components).
#
# Build context is the repository root:
#   docker build -t china-abs:latest .
#
# The image is an idle "toolbox": it stays alive so `just` actions can be run in
# any component folder via `docker exec`.  The entrypoint also starts cron, which
# runs the scheduled deal-docs downloads from /etc/cron.d/doctocloud (generated
# from flow/dags/scheduler.py):
#   docker run -d --name china-abs --env-file .env \
#       -v "$PWD/docToCloud/docs:/app/docToCloud/docs" china-abs:latest
#   docker exec -it -w /app/docToCloud china-abs just scan 2026-09-01
#
# Included: china_model, docToCloud, toMarkdown, assembler, scheduler, dashboard.
# Excluded: absbox.cloud (heavy web stack) and the Nix/devenv components
# flow/ digester/ reader/ maker/.
#
# Multi-stage: the `builder` stage installs `uv`, resolves the workspace into
# /app/.venv, then drops uv's cache.  The final stage copies only the finished
# virtualenv and the sources, so the uv toolchain and its ~290 MB cache never
# reach the shipped image.

FROM python:3.13-slim AS builder

ARG TARGETARCH=amd64

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

RUN pip install --no-cache-dir "uv==0.11.21"

WORKDIR /app

# Workspace manifests + the components in this image.  uv tolerates the other
# members listed in pyproject.toml being absent.
COPY pyproject.toml uv.lock util.py ./
COPY china_model ./china_model
COPY docToCloud ./docToCloud
COPY toMarkdown ./toMarkdown
COPY assembler ./assembler
COPY scheduler ./scheduler
COPY dashboard ./dashboard

# UV_LINK_MODE=copy makes /app/.venv self-contained, so the cache is pure
# duplication and is safe to remove before the venv is copied forward.
RUN uv sync --frozen --no-dev \
      --package china-model \
      --package doctocloud \
      --package tomarkdown \
      --package assembler \
      --package scheduler \
      --package dashboard \
 && rm -rf /root/.cache/uv

FROM python:3.13-slim

ARG JUST_VERSION=1.51.0
ARG TARGETARCH=amd64

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# `curl` + `ca-certificates` fetch the `just` release binary; `just` is what the
# `docker exec` workflow drives.  `cron` runs the scheduled deal-docs downloads
# from /etc/cron.d/doctocloud.
#
# Point apt at the Tencent Cloud mirror for faster installs in mainland China.
# Debian bookworm+ ships /etc/apt/sources.list.d/debian.sources; older variants
# use /etc/apt/sources.list.
RUN for f in /etc/apt/sources.list.d/debian.sources /etc/apt/sources.list; do \
      [ -f "$f" ] || continue; \
      sed -i 's|deb.debian.org|mirrors.cloud.tencent.com|g; s|security.debian.org|mirrors.cloud.tencent.com|g' "$f"; \
    done \
 && apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends curl ca-certificates cron \
 && case "$TARGETARCH" in \
      amd64) JUST_ARCH=x86_64 ;; \
      arm64) JUST_ARCH=aarch64 ;; \
      *) echo "unsupported TARGETARCH: $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && curl -fsSL "https://github.com/casey/just/releases/download/${JUST_VERSION}/just-${JUST_VERSION}-${JUST_ARCH}-unknown-linux-musl.tar.gz" \
      | tar -xz -C /usr/local/bin just \
 && rm -rf /var/lib/apt/lists/* \
 && just --version

WORKDIR /app

# The resolved virtualenv from the builder, plus the sources it runs from.
COPY --from=builder /app/.venv /app/.venv
COPY util.py ./
COPY china_model ./china_model
COPY docToCloud ./docToCloud
COPY toMarkdown ./toMarkdown
COPY assembler ./assembler
COPY scheduler ./scheduler
COPY dashboard ./dashboard

# Scheduled deal-docs downloads: install the cron file and the entrypoint that
# starts the cron daemon.  The cron file is generated from the job frequencies
# in flow/dags/scheduler.py and drives `just` recipes in /app/docToCloud.
COPY docToCloud/doctocloud.cron /etc/cron.d/doctocloud
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0644 /etc/cron.d/doctocloud \
 && chmod 0755 /usr/local/bin/docker-entrypoint.sh

# Idle toolbox: the entrypoint starts cron and then keeps PID 1 alive so
# `docker exec` can run `just` in any component.  For a one-off command use
# `docker run --rm china-abs <cmd>`.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["sleep", "infinity"]
