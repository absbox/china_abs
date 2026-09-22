# toMarkdown

Download outstanding PDF files from Qiniu cloud storage and convert them to
markdown. Three conversion backends are available:

| Subfolder | Backend | Notes |
|-----------|---------|-------|
| [`pdfinspect/`](pdfinspect) | `pdf-inspector` | Runs locally; no network service required. |
| [`mineru/`](mineru) | [MinerU](https://mineru.net) batch API | Signs Qiniu URLs and submits batches; results are polled and/or delivered to a callback server. |
| [`paddle/`](paddle) | [PaddleOCR-VL](https://aistudio.baidu.com) job API | Uploads local PDFs, polls each job, and joins the per-page markdown. |

All three write into the shared `mineru` Postgres table with a different
`model` (`inspector`, `mineru`, or `paddle`). Outstanding files are identified
by joining the `qiniu_storage` and `mineru` tables via the shared
[`china-model`](../china_model) package.

`pipeline.py` chains them local-first: pdf-inspector first, then PaddleOCR-VL
for files it could not read (e.g. image-based PDFs), then MinerU for anything
still outstanding. Use `main.py process NAME...` / `just process NAME...`.

## Setup

Requires Python 3.13+.

```bash
nix-shell          # NixOS: provides python/uv + native libs
uv sync            # from the repo root (workspace member)
```

Credentials come from the repo-root `.env` (git-ignored; see
[`.env.example`](../.env.example)):

| Variable | Description |
|----------|-------------|
| `DATABASE_HOST` | PostgreSQL host (default: `localhost`) |
| `DATABASE_PORT` | PostgreSQL port (default: `5432`) |
| `DATABASE_NAME` | Database name (default: `deal-library`) |
| `DATABASE_USER` | Database user (default: `doadmin`) |
| `DATABASE_PASSWORD` | Database password |
| `QINIU_ACCESS_KEY` | Qiniu access key |
| `QINIU_SECRET_KEY` | Qiniu secret key |
| `QINIU_BUCKET_DOMAIN` | Qiniu CDN domain (default: `deal-doc.doclink.site`) |
| `MINERU_TOKEN` | MinerU API token (required for `mineru/`) |
| `MINERU_CALLBACK` | Callback URL passed to MinerU |
| `MINERU_CALLBACK_CHECK` | Health URL used to probe the callback server |
| `MINERU_MAX_FILES_PER_BATCH` | Max files per MinerU batch (default: `50`) |
| `MINERU_SUBMIT_INTERVAL` | Seconds to wait between batch submissions (default: `65`) |
| `MINERU_POLL_INTERVAL` | Seconds between result polls (default: `30`) |
| `MINERU_POLL_TIMEOUT` | Max seconds to wait for a batch (default: `3600`) |
| `PADDLE_TOKEN` | PaddleOCR-VL API token (required for `paddle/`) |
| `PADDLE_JOB_URL` | PaddleOCR job endpoint (default: `https://paddleocr.aistudio-app.com/api/v2/ocr/jobs`) |
| `PADDLE_MODEL` | PaddleOCR model (default: `PaddleOCR-VL-1.6`) |
| `PADDLE_POLL_INTERVAL` | Seconds between job polls (default: `5`) |
| `PADDLE_POLL_TIMEOUT` | Max seconds to wait for a job (default: `1800`) |

## Usage

```bash
# List files that need markdown conversion
python main.py list

# Fallback pipeline: pdf-inspector -> paddle -> mineru for named file(s)
python main.py process "path/to/a.pdf" "path/to/b.pdf"

# Same pipeline for every outstanding file
python main.py process

# Download a single file by its Qiniu key
python main.py download "path/to/file.pdf"
python main.py download "path/to/file.pdf" -d /tmp/pdfs

# Download all outstanding files
python main.py download-all

# Convert PDFs in docs/ with pdf-inspector and save to the mineru table
python main.py inspect

# Convert PDFs in a specific folder with pdf-inspector
python main.py inspect /path/to/pdfs

# Convert every outstanding Qiniu file through the MinerU service (no download)
python main.py mineru

# Convert specific Qiniu key(s) through MinerU
python main.py mineru -k "path/to/file.pdf"

# Convert a local folder through MinerU (keys are the file names)
python main.py mineru /path/to/pdfs --model vlm

# Convert PDFs in docs/ locally through PaddleOCR-VL and save to the mineru table
python main.py paddle

# Convert concurrently and also write local .md files
python main.py paddle docs --workers 4 --out out

# Convert a specific folder through PaddleOCR-VL
python main.py paddle /path/to/pdfs
```

## Task runner (`justfile`)

Run `just` from this folder:

```bash
just                              # list recipes

# fallback pipeline (recommended)
just process "path/to/a.pdf" "path/to/b.pdf"   # pdf-inspector -> paddle -> mineru
just process-all                  # same, for every outstanding PDF

# individual engines
just pdfinspect "path/to/file.pdf"   # download key(s) then pdf-inspector
just pdfinspect-all                  # download + pdf-inspector every outstanding PDF
just paddle "path/to/file.pdf"       # download key(s) then PaddleOCR-VL
just paddle-all                      # download + PaddleOCR-VL every outstanding PDF
just mineru "path/to/file.pdf"       # MinerU: specific key(s), no download
just mineru-all                      # MinerU: every outstanding Qiniu file
just mineru-docs                     # MinerU: local PDFs in docs/

just list                            # list PDFs still missing markdown
just shell                           # enter the Nix dev shell
```

`just convert`, `just convert-all` and `just convert-list` remain as aliases for
the pdf-inspector recipes and `list`.

## Project Structure

```
toMarkdown/
├── main.py          # CLI entry point (dispatches to the converters)
├── pipeline.py      # fallback pipeline: pdf-inspector -> paddle -> mineru
├── db.py            # adapter over china_model's QiniuStorage + Mineru models
├── cloud.py         # Qiniu download + signed-URL helpers
├── pdfinspect/      # local conversion via pdf-inspector
│   └── convert.py
├── mineru/          # conversion via the MinerU batch service
│   └── convert.py
├── paddle/          # local conversion via the PaddleOCR-VL job service
│   └── convert.py
├── docs/            # downloaded PDFs (scratch space)
├── justfile         # task runner
├── pyproject.toml
├── shell.nix        # NixOS dev shell
└── README.md
```

## How It Works

1. `db.py` uses the shared `QiniuStorage` and `Mineru` models: it selects keys
   from `qiniu_storage` that have no non-null `markdown` entry in `mineru`.
2. `cloud.py` generates a time-limited signed URL via
   `qiniu.Auth.private_download_url()` and streams the file to disk.
3. **pdf-inspector** (`pdfinspect/convert.py`) reads each local PDF and, for
   every success, immediately upserts the markdown with `model='inspector'`.
4. **PaddleOCR-VL** (`paddle/convert.py`) uploads each local PDF, polls its job
   until done, joins the per-page `markdown.text` values, and upserts each
   success with `model='paddle'` (one at a time). `convert_files()` returns
   `{key: markdown}` and optionally `write_markdowns()` writes local `.md` files.
5. **MinerU** (`mineru/convert.py`) signs the Qiniu key, submits batches to
   `mineru.net/api/v4/extract/task/batch` with a callback, then polls
   `extract-results/batch/{id}`, downloads each result archive, extracts
   `full.md`, and upserts it with `model='mineru'`.
6. `pipeline.py` flows the keys through those engines like a queue: every stage
   re-checks the already-converted keys (`db.converted_keys`) and only the
   still-outstanding files are handed to the next engine, so a PDF converted by
   pdf-inspector is never sent to paddle or MinerU. Run it with `process` /
   `process-all`.
7. `main.py` orchestrates the above via CLI subcommands.
