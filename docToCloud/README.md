# docToCloud

Scan [chinabond.com.cn](https://www.chinabond.com.cn) for ABS/MBS disclosure
documents, work out which of them are still missing from Qiniu, download the
missing ones and upload them to Qiniu.

This is a dependency-light refactor of the relevant pieces of the legacy
`flow/dags` pipeline. It has no dependency on the `flow` `datasource` package.
The `qiniu_storage` catalogue is accessed through the shared
[`china-model`](../china_model) package rather than raw SQL.

## How it works

1. **Scan** — `chinabond.py` calls the site's `getContentByConditions` search
   API for each channel (default `zjzczq_ABS`, `zjzczq_MBS`) and each document
   type (发行文件, 发行结果, 付息兑付与行权公告, 评级文件, 财务报告,
   其他公告通知), paginating until no more results are returned.
   Attachments described by `appendixIds` are parsed directly; entries without
   it have their detail page parsed for download links.
2. **Look up outstanding** — the scanned file names are compared against the
   keys recorded in the shared `QiniuStorage` model (`qiniu_storage` table).
   Files that are not present are "outstanding".
3. **Download** — outstanding documents are streamed to the local folder
   (default `docs/`). Files that already exist locally are skipped, so a
   re-run never downloads the same PDF twice (use `--overwrite` to force it).
4. **Upload** — `cloud.py` uploads each local file with `put_file_v2`, verifies
   the returned etag against the local Qiniu etag, records the object in
   `qiniu_storage`, registers the document in the unified `report` catalogue
   (creating its `location` row and inferring its `reporttype` from the file
   name), and (optionally) removes the local copy. Files already present by key
   or MD5 are skipped.

## Setup

Requires Python 3.13+.

```bash
nix-shell          # NixOS: provides python/uv + native libs
uv sync            # from the repo root (workspace member)
```

Create a `.env` in this folder (it is git-ignored) with:

```
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=deal-library
DATABASE_USER=doadmin
DATABASE_PASSWORD=...
QINIU_ACCESS_KEY=...
QINIU_SECRET_KEY=...
QINIU_BUCKET=deal-docs
QINIU_BUCKET_DOMAIN=deal-doc.doclink.site
```

## Usage

```bash
# List every document found on chinabond for the default channels/types
python main.py list

# List only documents missing from Qiniu
python main.py list --outstanding

# Narrow the scan
python main.py list --keyword "邮盈惠丰2026年第五期" --start 2026-09-01 --end 2026-09-16
python main.py list --channel zjzczq_ABS --doc-type 发行文件 --max-pages 2

# Download outstanding documents into ./docs
python main.py fetch
python main.py fetch --dir /tmp/pdfs --workers 4
python main.py fetch --all            # download everything, present or not
python main.py fetch --overwrite      # re-download files already on disk

# Upload a folder to Qiniu (deleting local files after upload)
python main.py upload --dir ./docs --delete-local

# End-to-end: scan -> compute outstanding -> download -> upload
python main.py sync --start 2026-09-01 --end 2026-09-16
```

Run with `uv run doctocloud ...` to use the installed console script.

## Task runner (`justfile`)

Run `just` from this folder:

```bash
just                            # list recipes
just scan-download 2026-09-01   # scan, download and upload new files
just scan-list 2026-09-01       # preview: list files still missing from Qiniu
just shell                      # enter the Nix dev shell
```

`BEGIN`/`END` accept `YYYY-MM-DD`; `END` defaults to today.

## Project structure

```
docToCloud/
├── main.py       # CLI: list / fetch / upload / sync
├── chinabond.py  # scanning, attachment parsing and download
├── cloud.py      # Qiniu upload + duplicate protection
├── db.py         # adapter over china_model's QiniuStorage model
├── justfile      # task runner (`just scan-download` / `scan-list`)
├── pyproject.toml
├── shell.nix     # NixOS dev shell
└── README.md
```

## Mapping to the legacy `flow` code

| docToCloud | Legacy source |
|---|---|
| `chinabond.search_docs` / `parse_entries` / `scan` | `datasource/chinabond.py` `searchChinabondDocs`, `datasource/downloader.py` `download_from_cb`, `scanNewDocs` |
| `chinabond.fetch_subpage_files` | `datasource/downloader.py` `downloadFilesFromCbByPage`, `safe_decode` |
| `chinabond.download_entries` / `download_file` | `datasource/downloader.py` `downloadAction`, `datasource/chinabond.py` `downloadFilesFromCb` |
| `chinabond.RENAMES` | `datasource/downloader.py` `downloadAction` filename `match` cases |
| `cloud.upload_file` / `upload_directory` | `datasource/cloud.py` `upload_single_file`, `uploadToQiniu2`, `upload_current_docs` |
| `db.existing_docs` / `record_doc` | `datasource/db.py` `existingDocKey`, `hasFileByKey`, insert in `uploadToQiniu2` (now via `china_model.QiniuStorage`) |
| `db.record_report` / `classify_report_type_name` | `datasource/digestByNewFiles.py` `classifyFiles` / `allocateToLocation` (location + report-type allocation) |
