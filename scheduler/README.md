# scheduler

The APScheduler orchestration for the china-abs document pipeline — an exact
port of `flow/dags/scheduler.py` (same 14 jobs, same cron triggers, same job
ids, same APScheduler configuration), with the job bodies rebuilt on the new
subprojects:

- **docToCloud** — chinabond scanning, download and Qiniu upload
  (`jobs/docs.py`, via `chinabond`/`cloud`/`db`);
- **china_model** — shared Peewee models and DB access
  (`jobs/db.py`, `jobs/health.py`, `jobs/digest.py`);
- **docToCloud / toMarkdown / digester** — markdown + extraction flow stays the
  same shape (see *Migration status*).

## Setup

Requires Python 3.13+.

```bash
nix-shell          # NixOS: provides python/uv + native libs
uv sync            # from the repo root (workspace member)
```

Credentials come from `.env` (git-ignored; see `.env.example`): `DATABASE_*`,
`QINIU_*`, `MINERU_TOKEN`, `MINERU_CALLBACK`, `PGMQ_*`, `DOCS_DIR`,
`SCHEDULER_LOG_DIR`.

## Run

```bash
python main.py --list   # list registered jobs
python main.py          # start the blocking scheduler
```

Set `SCHEDULER_PERSIST=1` to enable the sqlalchemy jobstore from
`scheduler_params` (`jobs.sqlite`); by default the in-memory scheduler used by
`flow` is kept.

## Task runner (`justfile`)

Run `just` from this folder:

```bash
just                       # list recipes
just deal-init 2026-09-16  # allocate new documents (allocate_to_location_by_date)
just allocate 2026-09-16   # attach new uploads to existing deals (process_new)
just shell                 # enter the Nix dev shell
```

`SINCE` accepts `YYYY-MM-DD` and defaults to today.

## Jobs (identical to `flow/dags/scheduler.py`)

| id | cron | job |
|---|---|---|
| `catchUpPdf` | `05:00` | submit 498 outstanding PDFs from `os_mineru` to MinerU |
| `deleteUnusedFiles` | `*/2h` | delete local pdf/zip/doc that already have markdown |
| `pullInterestRate` | `23:00` | append new China govt bond yield curve rows |
| `eager_download_issue_file` | `:30 9-21 mon-sat` | `download_issuance_pricing(cutDaysNum=1, ['发行文件'])` |
| `eager_download_pricing_file` | `:00 9-21 mon-sat` | `download_pricing_outstanding_deal(cutDaysNum=10)` |
| `safenet_eager_download` | `:00 22 mon-sat` | `download_issuance_pricing()` |
| `eager_parse` | `*/15 mon-sat` | `parse_issuance_pricing()` |
| `pullIncomeDocs` | `19:00` | download + convert + attach + status |
| `pullChinaBondData` | `15:00` | issuance list + trading prices |
| `llm_extract_deal_data` | `20:30` | 6 LLM extractors |
| `fill_deal_data_obj` | `*/15` | 16 deal-fill functions |
| `writeHealthReport` | `*/15` | upsert `HealthCheck` snapshot |
| `submitMineruQueue` | `*/5` | drain pgmq `mineru` queue to mineru.net |
| `archieveFiles` | day 26 `03:00` | move 90-day-old Qiniu objects to type 4 |

## Migration status

Ported **exactly**:

- `jobs/db.py`, `jobs/mineru.py`, `jobs/cleanup.py`, `jobs/health.py`,
  `jobs/cloud.py`, `jobs/ex_data.py`;
- `jobs/digest.py` thin DB steps (`process_new`, `digitalized`,
  `allocate_to_location_by_date`, `change_deals_status`) and
  `jobs/docs.py` download/upload jobs (on docToCloud).

Ported as **orchestration + stubs** (function lists and control flow identical;
internals marked `not migrated`):

- `jobs/fill.py` — the LLM extractors and 16 `fill_data_fun` functions;
- `jobs/digest.py` — `classify_files` and the 15 `update*` allocation handlers.

These correspond to `flow/dags/datasource/LLM_filling_preClosing.py`,
`fill_data_fun.py` and `digestByNewFiles.py` (thousands of lines of LLM /
classification logic). They log a warning and no-op until ported.

`jobs/mineru.py` uses the `docToCloud` Qiniu signing helper and reads the MinerU
token from `MINERU_TOKEN` (no longer hard-coded).

## Project structure

```
scheduler/
├── main.py            # APScheduler entry point (exact port)
├── pathsetup.py       # puts docToCloud on sys.path
├── justfile           # task runner (`just deal-init` / `allocate`)
├── jobs/
│   ├── db.py          # Postgres helpers (china_model + psycopg)
│   ├── mineru.py      # pgmq + MinerU batch API
│   ├── cleanup.py     # catchUpPdf / deleteUnusedFiles
│   ├── docs.py        # download jobs (docToCloud-backed)
│   ├── ex_data.py     # interest rate + chinabond reference data
│   ├── digest.py      # allocation / stage changes
│   ├── health.py      # writeHealthReport
│   ├── cloud.py       # archieveFiles
│   └── fill.py        # LLM extract / fill orchestration
├── pyproject.toml
├── shell.nix
└── .env.example
```
