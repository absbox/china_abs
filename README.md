# china-abs

A monorepo for Chinese securitization (ABS) analytics. It covers the document half of the lifecycle of a credit ABS deal — from scanning raw prospectus/trustee disclosures, through PDF-to-markdown conversion and LLM extraction, to filling the structured deal/bond database. (The browser/analytics front end lives in a separate repository.)

The repo is organized around several components:

| Component | Purpose |
|---|---|
| [`china_model/`](#china_model) | Standalone Peewee data-model / DB-access library shared by the ABS workflow |
| [`docToCloud/`](#doctocloud) | Scan chinabond.com.cn and sync new disclosure documents to Qiniu |
| [`toMarkdown/`](#tomarkdown) | Download outstanding PDFs from Qiniu and convert them to markdown |
| [`scheduler/`](#scheduler) | APScheduler orchestration of the document pipeline |
| [`dashboard/`](#dashboard) | Read-only status / health checks for the project |
| [`assembler/`](#assembler) | Fill deal data: reads the `os_fill_*` reporting views and writes deals, bonds, payments and prices |
| [`digester/`](#digester) | LLM report-extraction service: routes ABS documents to typed schemas and stores results in MongoDB |
| [`reader/`](#reader) | Generic async ETL that summaries markdown documents via an LLM into MongoDB |

All components orbit a PostgreSQL database (`deal-library`) holding parsed deals, documents (including markdown extractions), and reference data such as the China government bond yield curve.

The repo also contains a few shared root files: `util.py` (helpers loaded by path from `assembler`), `Dockerfile` + `.dockerignore` (the whole-repo image, see [Docker](#docker)), and `main.py`/`shell.nix`/`.python-version` as workspace-level stubs. The web front end (`absbox.cloud`) and the legacy Airflow pipeline (`flow`) live outside this repository and are intentionally untracked.

## Task runners (`justfile`)

Each component owns its `justfile`; run `just` from the component folder. The
[`dashboard/`](#dashboard) is read-only and only exposes `just health`.

Setup (from the repo root): `nix-shell` then `uv sync --all-packages`
(`digester` and `reader` are separate — see their sections).

| Component | Recipe | What it does |
|---|---|---|
| `dashboard/` | `just health` | Health-check the whole project (DB, outstanding work, config). |
| `docToCloud/` | `just scan BEGIN [END]` | Scan chinabond from `BEGIN` to `END` (default today) and list files missing from Qiniu. |
| `docToCloud/` | `just download PATH BEGIN [END]` | Download the missing files into `PATH`. |
| `scheduler/` | `just deal-init [SINCE]` | Run deal init for documents that arrived since `SINCE` (default today) (`scheduler.jobs.digest.allocate_to_location_by_date`). |
| `scheduler/` | `just allocate [SINCE]` | Allocate newly uploaded files to existing deals (`scheduler.jobs.digest.process_new`). |
| `toMarkdown/` | `just process NAME...` | Convert named PDFs with the fallback chain: pdf-inspector → paddle → mineru. |
| `toMarkdown/` | `just process-all` | Run that fallback chain over **all** outstanding PDFs. |
| `toMarkdown/` | `just list` | List PDFs still missing markdown (`convert-list` alias). |
| `toMarkdown/` | `just pdfinspect NAME...` | Download and convert with pdf-inspector only (`convert` alias). |
| `toMarkdown/` | `just paddle NAME...` | Convert with PaddleOCR-VL only. |
| `toMarkdown/` | `just mineru NAME...` | Convert with the MinerU service only. |
| `digester/` | `just digest QUESTION NAME...` | Run one extraction question over a list of reports (`digester/digest.py`). |
| `digester/` | `just serve` | Run the digester API (`uvicorn`, hot reload, `:8000`). |
| `reader/` | `just run` | Run the `reader` ETL pipeline. |

`NAME` in `just digest` is either a `mineru` key (markdown fetched from
Postgres) or a path to a local markdown file; `QUESTION` is a registered key
such as `PRICING_ANN`. `BEGIN`/`END`/`SINCE` accept `YYYY-MM-DD`.

The `shell` recipe in each component enters that component's dev environment
(`nix-shell` or `devenv`) and does not work inside the Docker image.

### Examples

```bash
# 1. list what's missing since 1 Sep, then download it to a folder
cd docToCloud && just scan 2026-09-01
cd docToCloud && just download /tmp/pdfs 2026-09-01

# 2. initialise deals for the newly arrived documents
cd scheduler && just deal-init 2026-09-16

# 3. attach the new files to existing deals
cd scheduler && just allocate 2026-09-16

# 4. pdf -> markdown: one specific file, or every outstanding file
cd toMarkdown && just process "农盈利信远弘2025年第二期不良资产支持证券发行说明书.pdf"
cd toMarkdown && just process-all
cd toMarkdown && just list
cd toMarkdown && just pdfinspect-all    # pdf-inspector only
cd toMarkdown && just mineru-all        # mineru only
cd toMarkdown && just paddle-all        # paddle only

# 5. ask one question across a batch of reports
cd digester && just digest PRICING_ANN "report-a.pdf" "report-b.pdf"
```

> Note: `just deal-init` and `just allocate` call `scheduler/jobs/digest.py`.
> The document classifier and the per-type allocation handlers there are still
> being ported from `flow/dags/datasource/digestByNewFiles.py` and currently log
> `not migrated` without modifying data.

## Docker

The whole repository can be built into one image and driven with `docker exec`.
It is an idle **toolbox** image (PID 1 is `sleep infinity`) containing the shared
`.venv` and the pipeline components — `china_model`, `docToCloud`, `toMarkdown`,
`assembler`, `scheduler` and `dashboard` — plus `just`, so any component's
recipes can be run inside the container. The entrypoint also starts `cron`,
which runs the scheduled deal-docs downloads from `/etc/cron.d/doctocloud`
(generated from `flow/dags/scheduler.py`; see
[docToCloud](docToCloud/README.md#scheduled-downloads-docker)).

### Build

```bash
# context = repository root
docker build -t china-abs:latest .
```

### Credentials (environment)

All components share a single, git-ignored `.env` at the repository root.
`--env-file` supplies it to the container; `.env` files are never baked into
the image (`.dockerignore`). Start from the root template:

```bash
cp .env.example .env
$EDITOR .env   # DATABASE_* + QINIU_ACCESS_KEY/SECRET_KEY (see the comments)
```

- `QINIU_BUCKET` / `QINIU_BUCKET_DOMAIN` are optional (they default to
  `deal-docs` / `deal-doc.doclink.site`).
- A full `DATABASE_URI=postgresql://...` DSN may be used instead of the
  individual `DATABASE_*` variables; when set it takes precedence over them.
- The same file also carries the optional `scheduler` (MinerU queue,
  allocation, …), `digester` (LLM / JWT / MongoDB) and `reader` (`APP_*`)
  settings — see [`.env.example`](.env.example).
- Keep values unquoted: the `--env-file` format is plain `KEY=value` lines (no
  `export`, no quotes), which python-dotenv and the dev-shell loaders also
  accept.

### Run

```bash
mkdir -p docToCloud/docs docToCloud/logs
docker run -d --name china-abs --restart unless-stopped \
    --env-file .env \
    -v "$PWD/docToCloud/docs:/app/docToCloud/docs" \
    -v "$PWD/docToCloud/logs:/app/docToCloud/logs" \
    china-abs:latest
```

The container runs until stopped (`docker stop china-abs`). The entrypoint
starts `cron`, so the scheduled downloads fire at the times in
[docToCloud](docToCloud/README.md#scheduled-downloads-docker). Mounts:

- `/app/docToCloud/docs` — DocToCloud's default download folder (its `--dir`
  default). Mount it so downloaded PDFs survive container recreation. The CLI
  creates it if missing.
- `/app/docToCloud/logs` — the daily `YYYY-MM-DD.log` files. Optional, but
  useful for auditing the scheduled runs.
- Cron's own run output is appended to `/var/log/doctocloud-cron.log` inside the
  container (no mount needed).

Then drive `just` in any component folder:

```bash
docker exec -it -w /app/docToCloud china-abs just scan 2026-09-01
docker exec -it -w /app/docToCloud china-abs just download-issuance 2026-09-19
docker exec -it -w /app/toMarkdown china-abs just list
docker exec -it -w /app/scheduler  china-abs bash -lc 'python main.py --list'
docker exec -it -w /app/dashboard  china-abs just health

# run the scheduled jobs immediately instead of waiting for the next cron tick
docker exec china-abs /usr/sbin/cron -N
# follow the scheduled-job output
docker exec china-abs tail -f /var/log/doctocloud-cron.log
```

For a one-off command without keeping a container:

```bash
docker run --rm --env-file .env \
    -v "$PWD/docToCloud/docs:/app/docToCloud/docs" \
    -w /app/docToCloud china-abs just scan 2026-09-01
```

Notes:
- The image includes the `uv` workspace members only; `digester`/`reader`
  (separate `devenv` / `requirements.txt` environments) are **not** in it.
- The container needs outbound access to `chinabond.com.cn`, Qiniu and
  PostgreSQL, and publishes no ports.
- The `shell` recipes (`nix-shell` / `devenv`) do not work inside the container.

## china_model

A standalone package that is the **single source of truth** for the Peewee data model shared across the monorepo. The schema lives in `src/china_model/models.py`; importing the package has no side effects — a host application calls `china_model.configure()` once at startup (reading `DATABASE_*` env vars or an explicit DSN) and the models bind to a `DatabaseProxy`.

Besides the deal/bond tables it also models the pipeline tables `QiniuStorage` (`qiniu_storage`) and `Mineru` (`mineru`) used by `docToCloud` and `toMarkdown`. A `model.py` shim is kept for legacy `from model import ...` imports. It is a member of the root `uv` workspace, so the other projects depend on it via `china-model = { workspace = true }`.

**Stack** — peewee 4 (psycopg3) + bcrypt, fire, lenses, toolz, pymongo, rich; Python >= 3.13 managed with `uv`.

## digester

An LLM-based report-extraction service for ABS/NPL transactions. It reads markdown-converted transaction documents (from the `mineru` Postgres table), routes each document type to a typed extraction schema (~15 pydantic models for prospectus, issuance-plan, pricing-announcement, trustee, rating, and clearing reports), calls an OpenAI-compatible LLM via `instructor`, and upserts the structured results into MongoDB.

It also ships a minimal FastAPI service with JWT authentication, a backfill script for unprocessed pricing reports, and a `seed_user.py` seeding script.

**Stack** — FastAPI + uvicorn, instructor + openai, pydantic, psycopg / pymongo / motor, JWT (python-jose + passlib). Dev environments are defined via Nix `devenv` (Python 3.13 + uv, with a bundled MongoDB storing data under `./db`). Entrypoints: `just digest QUESTION NAME...`, `just serve`, or `uv run uvicorn app.main:app`.

## dashboard

Read-only status / health checks for the whole project. `dashboard/api.py`
connects to PostgreSQL and MongoDB, counts the shared tables, asks `scheduler`
for the outstanding-work views, and lists the required configuration; the
result is rendered as Markdown by `dashboard/main.py`. Entry point:
`cd dashboard && just health`.

Actions are owned by the component that implements them — see each component's
`justfile` and the [Task runners](#task-runners-justfile) section above, or
[`dashboard/README.md`](dashboard/README.md).

**Stack** — rich, psycopg, china-model; it loads `scheduler` through
`bridge.py`.

## assembler

The fill layer between the parsed reports and the deal objects. `assembler/fill.py`
is the port of the legacy Airflow `flow/dags/datasource/fill_data_fun.py`: each
step reads one `os_fill_*` reporting view (or `os_llm_deal_waterfall`) and
performs the corresponding writes into the shared `china_model` tables — pricing/Bond
creation, issue plans, pre-closing rating data, clear reports, trustee periods
and bond payments, pool performance, waterfall, sequence views, end dates,
balance tie-outs and trading prices.

It contains no LLM extraction and no orchestration; the scheduled job body lives
in `scheduler/jobs/fill.py`, which imports these functions. Entry point:
`python -m assembler.main {list,run}`.

**Stack** — `china_model` (Peewee 4 + psycopg3), toolz, lenses, dateparser; an
optional `llm` extra wires `fillWaterfall`/`calibrateTheName` to an
OpenAI-compatible endpoint.

## docToCloud

Scans chinabond.com.cn and pulls new ABS/MBS disclosure documents into Qiniu:
scan → diff against `qiniu_storage` → download → upload. After a successful
upload it records the object in `qiniu_storage` and registers the document in
the unified `report` catalogue (creating its `location` row and inferring its
`reporttype` from the file name). Downloaded files default to
`docToCloud/docs/`. Entry point: `python main.py {list,fetch,upload,sync}`.

## toMarkdown

Downloads outstanding PDFs from Qiniu and converts them to markdown, upserting
into the `mineru` table. Three backends live in subfolders: `pdfinspect/`
(local `pdf-inspector`), `mineru/` (the MinerU batch service) and `paddle/`
(local `PaddleOCR-VL`). `pipeline.py` chains them local-first (pdf-inspector →
paddle → mineru) via `just process NAME...`. Entry point: `python
main.py {list,process,download,download-all,inspect,mineru,paddle}`.

## scheduler

The APScheduler orchestration (exact port of the legacy Airflow `flow` scheduler,
same 14 jobs/crons) with job bodies built on the other subprojects. It reuses
`docToCloud`'s flat modules by adding them to `sys.path` (`pathsetup.py`).
Entry point: `python main.py [--list]`.

## reader

A small async ETL pipeline that batch-processes markdown documents from a (remote) PostgreSQL table, LLM-extracts structured metadata (title, summary, key points, tags) via `instructor`, and idempotently upserts each result into MongoDB keyed by the source record id. Config is driven by env vars (see the root [`.env.example`](.env.example)).

**Stack** — asyncpg, motor, instructor + openai (AsyncOpenAI), pydantic-settings; any OpenAI-compatible endpoint works (e.g. OpenAI or Ollama). Entrypoint: `python main.py` (or `just run`).

## Repository layout

```text
china-abs/
├── china_model/   # shared Peewee schema (installed as `china-model`)
├── docToCloud/    # chinabond scan → download → Qiniu upload
├── toMarkdown/    # Qiniu PDF → markdown (`mineru` table)
├── scheduler/     # APScheduler orchestration
├── assembler/     # os_fill_* views → deal/bond tables
├── dashboard/     # read-only health checks
├── digester/      # LLM extraction service (devenv)
├── reader/        # async LLM summarisation ETL
├── .env.example   # unified env template (copy to .env)
├── util.py        # shared helpers, loaded by path
├── Dockerfile     # whole-repo pipeline image
├── docker-entrypoint.sh  # starts cron, then the container command
└── pyproject.toml # uv workspace root
```

The `uv` workspace members are `china_model`, `toMarkdown`, `docToCloud`,
`scheduler`, `dashboard` and `assembler`; `digester` and `reader` manage their
own environments (`devenv` / `requirements.txt`). `absbox.cloud`, `flow` and
`maker` are not part of this repository and are git-ignored.

## Requirements

- Python >= 3.13 (each component pins its own version via `uv` / `devenv` / `requirements.txt`)
- PostgreSQL instance (named `deal-library`) with parsed deal and document data
- MongoDB instance for LLM-extraction results
- LLM API keys (e.g. `QWEN_API_KEY`, `DEEPSEEK_API_KEY`, `LLM_API_KEY`)
- Qiniu credentials (`QINIU_ACCESS_KEY`, `QINIU_SECRET_KEY`, `QINIU_BUCKET`) for `docToCloud`/`toMarkdown`
