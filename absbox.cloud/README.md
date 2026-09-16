# absbox.cloud

The browser and analytics front end for Chinese credit ABS deals (NPL 不良资产,
AUTO 汽车贷款, consumer, RMBS, etc.).

**Features**
- **Deal pages** — stage-dependent tabs: 发行信息, 相关发行, 评级观点, 分配规则, 存续信息, 清算信息, 文档速览.
- **Pre-closing pipeline** — pending ("待成立") and newly closed ("新成立") deals with status badges.
- **Issuance-rate projection** — `/projectIssuanceRate` interpolates the China government bond yield curve and adds a historical spread from comparable deals.
- **Bond screening** — `/bondScreen` filters by face value, coupon, rating, asset class and seniority.
- **Trading prices**, **document search**, and a **JSON API** (`webApi.py`).

**Stack** — FastAPI (server-rendered HTML with htpy; Bulma, htmx, Alpine.js,
ECharts), Peewee + psycopg over PostgreSQL, pyxirr, pandas/scipy. Two apps:
`index.py` (site) and `webApi.py` (JSON API), served with gunicorn/uvicorn on
port 8001.

## Shared data model

The Peewee schema is **not** defined here. This project depends on the shared
[`china-model`](../china_model) package. `model.py` is a thin compatibility
shim so existing `from model import ...` imports keep working; it binds the
database on import.

## Setup

Requires Python 3.13+.

```bash
nix-shell          # NixOS: provides python/uv + native libs
uv sync            # from the repo root (workspace member)
```

Configuration is read from `.env` (git-ignored) or the environment:

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8001` | HTTP port |
| `DATABASE_HOST` | `localhost` | PostgreSQL host (`DATABASE_URL` is accepted as a legacy fallback) |
| `DATABASE_PORT` | `5432` | PostgreSQL port |
| `DATABASE_NAME` | `deal-library` | Database name |
| `DATABASE_USER` | `doadmin` | Database user |
| `DATABASE_PASSWORD` | – | Database password |

## Run

```bash
PYTHONPATH=. python index.py            # site, port 8001
PYTHONPATH=. python webApi.py           # JSON API, port 8001
gunicorn -c gunicorn_conf.py index:app  # production
```

Or via the monorepo tasks: `just web`, `just api`.

## Optional dependency

Chinese numeral parsing in `parser_base.py` uses the private `cnc` package. It
is imported defensively; without it the rest of the app works and only
`tryParseNumberIntCNEN` raises when it would need the conversion.

## Project structure

```
absbox.cloud/
├── pyproject.toml     # dependencies (incl. china-model) — workspace member
├── shell.nix          # NixOS dev shell
├── model.py           # compatibility shim -> china_model
├── db.py              # raw psycopg helpers (pool, markdown/file lookups)
├── index.py           # site app
├── webApi.py          # JSON API
├── parser_base.py     # document parsers
├── pages/             # htpy page components
└── gunicorn_conf.py
```
