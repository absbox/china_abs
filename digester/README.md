# digester

An LLM-based report-extraction service for ABS/NPL transactions. It reads
markdown-converted transaction documents (from the `mineru` Postgres table),
routes each document type to a typed extraction schema (~15 pydantic models for
prospectus, issuance-plan, pricing-announcement, trustee, rating, and clearing
reports), calls an OpenAI-compatible LLM via `instructor`, and upserts the
structured results into MongoDB.

It also ships a minimal FastAPI service with JWT authentication, a backfill
script for unprocessed pricing reports, and a `seed_user.py` seeding script.

> Renamed from `maker`; the API title is now "Digester Service".

## Setup

Dev environments are defined via Nix [`devenv`](https://devenv.sh) (Python 3.13
+ `uv`, with a bundled MongoDB storing data under `./db`).

```bash
devenv shell     # enter dev environment (installs deps via `uv sync`)
devenv up        # run MongoDB + API with hot reload (http://127.0.0.1:8000)
devenv test      # validate the environment
```

Credentials come from `.env` (git-ignored; see `.env.example`):

| Variable | Description |
|---|---|
| `DATABASE_HOST` / `DATABASE_PORT` / `DATABASE_NAME` / `DATABASE_USER` / `DATABASE_PASSWORD` | Postgres `deal-library` (source of parsed report markdown) |
| `MONGODB_URI` | MongoDB connection string (databases: raw/test/prod) |
| `QWEN_API_KEY` / `DEEPSEEK_API_KEY` / `LLM_API_KEY` / `LLM_MODEL_NAME` | LLM provider credentials |
| `JWT_SECRET_KEY` / `JWT_ALGORITHM` / `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Auth / JWT settings |

## Entrypoints

```bash
seed <user> <pass>                     # pre-seed a login user into MongoDB
uv run uvicorn app.main:app --reload   # run the API on :8000
```

## Task runner (`justfile`)

Run `just` from this folder:

```bash
just                                    # list recipes
just digest PRICING_ANN "a.pdf" "b.pdf" # extract one question over reports
just serve                              # run the API on :8000 (hot reload)
just shell                              # enter the devenv shell
```

`NAME` in `just digest` is a mineru key (markdown fetched from Postgres) or a
local markdown path; `QUESTION` is a registered key such as `PRICING_ANN`.

## Project structure

```
digester/
├── app/
│   ├── main.py          # FastAPI app (+ /health)
│   ├── routes.py        # extraction routes
│   ├── auth.py          # JWT auth
│   ├── auth_routes.py   # login routes
│   ├── backfill.py      # backfill unprocessed pricing reports
│   ├── database.py      # MongoDB (motor) connection
│   ├── extracter.py     # document-type routing + schemas
│   ├── handler.py       # extraction handlers
│   ├── llm.py           # LLM client (instructor/openai)
│   ├── models.py        # pydantic / odmantic models
│   └── enums.py
├── main.py              # placeholder entrypoint
├── seed_user.py         # user seeding script
├── justfile             # task runner (`just digest` / `serve`)
├── devenv.nix/.yaml     # dev environment (Python 3.13 + uv + MongoDB)
├── shell.nix            # minimal Nix shell (nodejs)
├── pyproject.toml       # uv project (name = "digester")
└── requirements.txt
```
