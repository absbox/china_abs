# dashboard

Status / health checks for the whole **china-abs** project. The dashboard is
read-only: it inspects the shared database, the outstanding-work views and the
required configuration, and renders the result as **Markdown** (via `rich`).

Actions are **not** run from here. Each action lives with the component that
owns the underlying function and is exposed by that component's own `justfile`
(see [*Where the actions live*](#where-the-actions-live)).

## How it works

`dashboard/api.py` exposes the health checks. `health()` connects to PostgreSQL
and MongoDB, counts the shared tables, asks the `scheduler` project's
`jobs.health.run_check()` for the outstanding-work views, and lists which
environment variables are set.

`bridge.py` adds the `scheduler` project to `sys.path` so `jobs.health` can be
imported.

```
dashboard/
├── main.py      # CLI: render the health report as markdown
├── api.py       # health / connection checks
├── bridge.py    # imports scheduler.jobs.health
├── justfile     # `just health`
├── pyproject.toml
└── shell.nix
```

## Setup

Requires Python 3.13+.

```bash
nix-shell          # NixOS: python/uv + native libs
uv sync --all-packages   # from the repo root (workspace member)
```

Configuration is read from the repo-root `.env` (git-ignored; see
[`.env.example`](../.env.example)).

## Usage

Run from this folder (`cd dashboard`):

```bash
just              # list recipes
just health       # health-check DB, outstanding work, config
```

The same check is available directly through the CLI:

```bash
python main.py health
```

## Where the actions live

Run `just` from the component folder that owns the function:

| Action | Component | Recipe |
|---|---|---|
| scan / download chinabond docs | `docToCloud` | `just scan BEGIN [END]`, `just download PATH BEGIN [END]` |
| deal init / allocate | `scheduler` | `just deal-init [SINCE]`, `just allocate [SINCE]` |
| pdf → markdown | `toMarkdown` | `just process NAME...`, `just process-all`, `just list` |
| LLM extraction | `digester` | `just digest QUESTION NAME...` |
| reader ETL | `reader` | `just run` |
| absbox.cloud site / API / deploy | `absbox.cloud` | `just web`, `just api`, `just upload-web-dev`, `just upload-web` |

See each component's README and `justfile` for details.
