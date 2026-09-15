# china-abs

A monorepo for Chinese securitization (ABS) analytics. It covers the full lifecycle of a credit ABS deal — from reading raw prospectus/trustee documents, to extracting structured data with LLMs, to browsing deals and projecting issuance rates in a web dashboard.

The repo is organized around four components:

| Component | Purpose |
|---|---|
| [`absbox.cloud/`](#absboxcloud) | FastAPI web app for browsing deals/series, per-deal analytics, bond screening, and issuance-rate projection |
| [`china_model/`](#china_model) | Standalone Peewee data-model / DB-access library shared by the ABS workflow |
| [`maker/`](#maker) | LLM report-extraction service: routes ABS documents to typed schemas and stores results in MongoDB |
| [`reader/`](#reader) | Generic async ETL that summaries markdown documents via an LLM into MongoDB |

All components orbit a PostgreSQL database (`deal-library`) holding parsed deals, documents (including markdown extractions), and reference data such as the China government bond yield curve. The `main.py`/`pyproject.toml` files at the repo root are placeholder stubs.

## absbox.cloud

The browser and analytics front end for Chinese credit ABS deals (NPL 不良资产, AUTO 汽车贷款, consumer, RMBS, etc.).

**Features**
- **Deal pages** — stage-dependent tabs: 发行信息 (financing structure, rating-agency pool stats), 相关发行 (historical comparable issue spreads), 评级观点 (rating views), 分配规则 (waterfall), 存续信息 (current pool performance & bond paydowns), 清算信息 (liquidation: recovery rates, bond XIRR / WAL / static returns), 文档速览 (transaction-document viewer).
- **Pre-closing pipeline** — list pending ("待成立") and newly closed ("新成立") deals with status badges.
- **Issuance-rate projection** — `/projectIssuanceRate` interpolates the China government bond yield curve and adds a historical spread from comparable same-series / same-asset-class deals.
- **Bond screening** — `/bondScreen` filters bonds by face value, coupon, rating, asset class, and seniority.
- **Trading prices** — aggregated by seniority / pool type / series.
- **Document search** — keyword search over LLM-parsed markdown documents and rendered file preview.
- **JSON API** — `webApi.py` exposes `/deals/`, `/deal/{id}/data`, `/deal/{id}/analytics`, and `/trading/{date}/`.

**Stack** — FastAPI (HTML rendered server-side with htpy; Bulma, htmx, Alpine.js, ECharts), Peewee ORM + psycopg over PostgreSQL, pyxirr for IRR/XIRR, pandas/scipy for curve interpolation. Two apps: `index.py` (site) and `webApi.py` (JSON API), served with gunicorn/uvicorn on port 8001.

## china_model

A minimal standalone package exposing the same Peewee data model as `absbox.cloud/model.py` as an importable library, decoupled from the web app. It self-loads a `.env` for PostgreSQL connectivity (and includes MongoDB support among its dependencies). Also reference the future `updater.py` placeholder.

**Stack** — peewee + psycopg, bcrypt, fire, lenses, toolz, pymongo, rich; Python >= 3.13 managed with `uv`.

## maker

An LLM-based report-extraction service for ABS/NPL transactions. It reads markdown-converted transaction documents (from the `mineru` Postgres table), routes each document type to a typed extraction schema (~15 pydantic models for prospectus, issuance-plan, pricing-announcement, trustee, rating, and clearing reports), calls an OpenAI-compatible LLM via `instructor`, and upserts the structured results into MongoDB.

It also ships a minimal FastAPI service with JWT authentication, a backfill script for unprocessed pricing reports, and a `seed_user.py` seeding script.

**Stack** — FastAPI + uvicorn, instructor + openai, pydantic, psycopg / pymongo / motor, JWT (python-jose + passlib). Dev environments are defined via Nix `devenv` (Python 3.13 + uv, with a bundled MongoDB storing data under `./db`). Entrypoints: `seed <user> <pass>` and `uv run uvicorn app.main:app`.

## reader

A small async ETL pipeline that batch-processes markdown documents from a (remote) PostgreSQL table, LLM-extracts structured metadata (title, summary, key points, tags) via `instructor`, and idempotently upserts each result into MongoDB keyed by the source record id. Config is driven by env vars (see `.env.example`).

**Stack** — asyncpg, motor, instructor + openai (AsyncOpenAI), pydantic-settings; any OpenAI-compatible endpoint works (e.g. OpenAI or Ollama). Entrypoint: `python main.py`.

## Requirements

- Python >= 3.13 (each component pins its own version via `uv` / `devenv` / `requirements.txt`)
- PostgreSQL instance (named `deal-library`) with parsed deal and document data
- MongoDB instance for LLM-extraction results
- LLM API keys (e.g. `QWEN_API_KEY`, `DEEPSEEK_API_KEY`, `LLM_API_KEY`)