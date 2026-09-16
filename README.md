# china-abs

A monorepo for Chinese securitization (ABS) analytics. It covers the full lifecycle of a credit ABS deal — from reading raw prospectus/trustee documents, to extracting structured data with LLMs, to browsing deals and projecting issuance rates in a web dashboard.

The repo is organized around several components:

| Component | Purpose |
|---|---|
| [`absbox.cloud/`](#absboxcloud) | FastAPI web app for browsing deals/series, per-deal analytics, bond screening, and issuance-rate projection |
| [`china_model/`](#china_model) | Standalone Peewee data-model / DB-access library shared by the ABS workflow |
| [`digester/`](#digester) | LLM report-extraction service: routes ABS documents to typed schemas and stores results in MongoDB |
| [`reader/`](#reader) | Generic async ETL that summaries markdown documents via an LLM into MongoDB |

All components orbit a PostgreSQL database (`deal-library`) holding parsed deals, documents (including markdown extractions), and reference data such as the China government bond yield curve. The `main.py`/`pyproject.toml` files at the repo root are placeholder stubs.

## Workflows (`justfile`)

The root `justfile` wires the day-to-day document pipeline to the subprojects
(`docToCloud` → scan/download/upload, `scheduler` → deal init + allocation,
`toMarkdown` → pdf→markdown, `digester` → LLM extraction).

```bash
just                 # list every recipe
nix-shell            # NixOS: shell with just + the native libs
uv sync --all-packages
```

### Requested workflows

| Recipe | What it does |
|---|---|
| `just scan-download BEGIN [END]` | Scan chinabond from `BEGIN` to `END` (default today), download files missing from Qiniu and upload them (`docToCloud`). |
| `just scan-list BEGIN [END]` | Preview only — list scanned files still missing from Qiniu. |
| `just deal-init [SINCE]` | Run deal init for documents that arrived since `SINCE` (default today) (`scheduler.jobs.digest.allocate_to_location_by_date`). |
| `just allocate [SINCE]` | Allocate newly uploaded files to existing deals (`scheduler.jobs.digest.process_new`). |
| `just convert NAME...` | Download the given Qiniu key(s) then convert the folder PDFs to markdown (`toMarkdown`). |
| `just convert-all` | Download and convert **all** outstanding PDFs that have no markdown yet. |
| `just convert-list` | List PDFs still missing markdown. |
| `just digest QUESTION NAME...` | Run one extraction question over a list of reports (`digester/digest.py`). |

`NAME` in `just digest` is either a `mineru` key (markdown fetched from
Postgres) or a path to a local markdown file; `QUESTION` is a registered key
such as `PRICING_ANN`. `BEGIN`/`END`/`SINCE` accept `YYYY-MM-DD`.

### Examples

```bash
# 1. pull everything published since 1 Sep, upload to Qiniu
just scan-download 2026-09-01

# 2. initialise deals for the newly arrived documents
just deal-init 2026-09-16

# 3. attach the new files to existing deals
just allocate 2026-09-16

# 4. pdf -> markdown: one specific file, or every outstanding file
just convert "农盈利信远弘2025年第二期不良资产支持证券发行说明书.pdf"
just convert-all
just convert-list

# 5. ask one question across a batch of reports
just digest PRICING_ANN "report-a.pdf" "report-b.pdf"
```

### Component helpers

| Recipe | What it does |
|---|---|
| `just shell` / `just shell-in <component>` | Enter the root / a component Nix dev shell. |
| `just check` | `py_compile` every Python component. |
| `just reader` / `just digester` | Run the `reader` ETL / the `digester` API (`:8000`). |
| `just web` / `just api` | Run the `absbox.cloud` site / JSON API (`:8001`). |
| `just upload-web-dev` / `just upload-web` | `scp` `absbox.cloud` to the dev / production folder. |

> Note: `just deal-init` and `just allocate` call `scheduler/jobs/digest.py`.
> The document classifier and the per-type allocation handlers there are still
> being ported from `flow/dags/datasource/digestByNewFiles.py` and currently log
> `not migrated` without modifying data.

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

A standalone package that is the **single source of truth** for the Peewee data model shared across the monorepo. The schema lives in `src/china_model/models.py`; importing the package has no side effects — a host application calls `china_model.configure()` once at startup (reading `DATABASE_*` env vars or an explicit DSN) and the models bind to a `DatabaseProxy`.

Besides the deal/bond tables it also models the pipeline tables `QiniuStorage` (`qiniu_storage`) and `Mineru` (`mineru`) used by `docToCloud` and `toMarkdown`. A `model.py` shim is kept for legacy `from model import ...` imports. It is a member of the root `uv` workspace, so the other projects depend on it via `china-model = { workspace = true }`.

**Stack** — peewee 4 (psycopg3) + bcrypt, fire, lenses, toolz, pymongo, rich; Python >= 3.13 managed with `uv`.

## digester

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