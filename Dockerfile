# Whole-repo china-abs image (pipeline components).
#
# Build context is the repository root:
#   docker build -t china-abs:latest .
#
# The image is an idle "toolbox": it stays alive so `just` actions can be run in
# any component folder via `docker exec`:
#   docker run -d --name china-abs --env-file .env \
#       -v "$PWD/docToCloud/docs:/app/docToCloud/docs" china-abs:latest
#   docker exec -it -w /app/docToCloud china-abs just scan 2026-09-01
#
# Included: china_model, docToCloud, toMarkdown, assembler, scheduler, dashboard.
# Excluded: absbox.cloud (heavy web stack) and the Nix/devenv components
# flow/ digester/ reader/ maker/.

FROM python:3.13-slim

ARG JUST_VERSION=1.51.0
ARG TARGETARCH=amd64

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# `curl` + `ca-certificates` fetch the `just` release binary; `just` is what the
# `docker exec` workflow drives.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && case "$TARGETARCH" in \
      amd64) JUST_ARCH=x86_64 ;; \
      arm64) JUST_ARCH=aarch64 ;; \
      *) echo "unsupported TARGETARCH: $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && curl -fsSL "https://github.com/casey/just/releases/download/${JUST_VERSION}/just-${JUST_VERSION}-${JUST_ARCH}-unknown-linux-musl.tar.gz" \
      | tar -xz -C /usr/local/bin just \
 && rm -rf /var/lib/apt/lists/* \
 && just --version

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

RUN uv sync --frozen --no-dev \
      --package china-model \
      --package doctocloud \
      --package tomarkdown \
      --package assembler \
      --package scheduler \
      --package dashboard

# Idle toolbox: keep PID 1 alive so `docker exec` can run `just` in any
# component.  For a one-off command use `docker run --rm china-abs <cmd>`.
CMD ["sleep", "infinity"]
