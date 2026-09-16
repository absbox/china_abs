# dashboard

Command dashboard and task runner for the whole **china-abs** project. It:

- calls Python functions in the sibling subprojects,
- renders every result as **Markdown** (via `rich`),
- manages / health-checks the project,
- exposes a single-function dispatcher and a `justfile` for the command line.

## How it works

`dashboard/api.py` is the API: one function per pipeline action. Each function
loads the relevant subproject through `bridge.py` and returns a Markdown
string.

`bridge.py` handles the fact that `docToCloud` and `toMarkdown` are flat-module
projects that both define a top-level `db`/`cloud`: each is imported under a
private module name with its internal `db` injected only for the duration of
the import, so the two never collide. `scheduler` is imported as a package, and
`digester` supplies the LLM extraction functions.

```
dashboard/
├── main.py      # CLI: dispatch a command, render markdown
├── api.py       # one function per action (+ REGISTRY)
├── bridge.py    # cross-project import shims
├── justfile     # `just <recipe>` -> python main.py <command>
├── pyproject.toml
├── shell.nix
└── .env.example
```

## Setup

Requires Python 3.13+.

```bash
nix-shell          # NixOS: python/uv + native libs
uv sync --all-packages   # from the repo root (workspace member)
```

Configuration is read from `.env` (git-ignored; see `.env.example`). The
dashboard loads the repo `.env`; for `digest` it also loads
`digester/.env` (LLM API keys).

## Usage

Run from this folder (`cd dashboard`):

```bash
just                      # list recipes
just health               # health-check DB, outstanding work, config

# the five pipeline workflows
just scan-download 2026-09-01
just scan-list 2026-09-01
just deal-init 2026-09-16
just allocate 2026-09-16
just convert "农盈利信远弘2025年第二期不良资产支持证券发行说明书.pdf"
just convert-all
just convert-list
just digest PRICING_ANN "a.pdf" "b.pdf"
```

The same actions are available directly through the CLI:

```bash
python main.py health
python main.py scan-download 2026-09-01
python main.py call convert-list          # call a single function by name
python main.py call allocate 2026-09-16
```

| Command | Function | Calls into |
|---|---|---|
| `scan-download BEGIN [END]` | `api.scan_download` | `docToCloud` (`chinabond` + `cloud` + `db`) |
| `scan-list BEGIN [END]` | `api.scan_list` | `docToCloud` |
| `deal-init [SINCE]` | `api.deal_init` | `scheduler.jobs.digest` |
| `allocate [SINCE]` | `api.allocate` | `scheduler.jobs.digest` |
| `convert NAME...` | `api.convert` | `toMarkdown` |
| `convert-all` | `api.convert_all` | `toMarkdown` |
| `convert-list` | `api.convert_list` | `toMarkdown` |
| `digest QUESTION NAME...` | `api.digest` | `digester.app.llm` |
| `health` | `api.health` | `china_model` + `scheduler.jobs.health` |
| `call NAME [ARGS...]` | `api.REGISTRY[NAME]` | — |

## Notes

- `deal-init` / `allocate` call `scheduler/jobs/digest.py`; its classifier and
  per-type handlers are still being ported from
  `flow/dags/datasource/digestByNewFiles.py` and currently log `not migrated`.
- `digest` names may be `mineru` keys or local markdown paths; `QUESTION` is a
  registered key such as `PRICING_ANN`.
