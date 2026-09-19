# toMarkdown

Download outstanding PDF files from Qiniu cloud storage for markdown conversion. Queries the `qiniu_storage` and `mineru` tables — via the shared [`china-model`](../china_model) package — to identify files that have not yet been converted.

## Setup

Requires Python 3.13+.

```bash
nix-shell          # NixOS: provides python/uv + native libs
uv sync            # from the repo root (workspace member)
```

Create a `.env` (git-ignored) with the credentials:

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

## Usage

```bash
# List files that need markdown conversion
python main.py list

# Download a single file by its Qiniu key
python main.py download "path/to/file.pdf"

# Download to a specific directory
python main.py download "path/to/file.pdf" -d /tmp/pdfs

# Download all outstanding files
python main.py download-all

# Download all outstanding files to a custom directory
python main.py download-all -d /tmp/pdfs

# Convert PDFs in docs/ to markdown and save to the mineru table
python main.py inspect

# Convert PDFs in a specific folder
python main.py inspect /path/to/pdfs
```

## Task runner (`justfile`)

Run `just` from this folder:

```bash
just                              # list recipes
just convert "path/to/file.pdf"   # download key(s) then convert docs/
just convert-all                  # download + convert every outstanding PDF
just convert-list                 # list PDFs still missing markdown
just shell                        # enter the Nix dev shell
```

## Project Structure

```
toMarkdown/
├── main.py       # CLI entry point
├── db.py         # adapter over china_model's QiniuStorage + Mineru models
├── cloud.py      # Qiniu file download via signed URLs
├── convert.py    # PDF-to-markdown conversion via pdf-inspector
├── justfile      # task runner (`just convert` / `convert-all` / `convert-list`)
├── pyproject.toml
├── shell.nix     # NixOS dev shell
└── README.md
```

## How It Works

1. `db.py` uses the shared `QiniuStorage` and `Mineru` models: it selects keys from `qiniu_storage` that have no non-null `markdown` entry in `mineru`.
2. `cloud.py` generates a time-limited signed URL via `qiniu.Auth.private_download_url()` and streams the file to disk.
3. `convert.py` reads each PDF in the target folder, converts it with `pdf-inspector`, and upserts the result into `mineru` with `model='inspector'`. PDFs that yield no markdown are skipped.
4. `main.py` orchestrates the above via CLI subcommands.

