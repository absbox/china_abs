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
   (default `docs/`). A document is skipped when its key is already in
   `qiniu_storage` **or** when the file already exists in the target folder; in
   the latter case the local copy is uploaded to Qiniu instead of being
   downloaded again (so `fetch` both downloads missing files and uploads
   pre-existing local ones). Use `--overwrite` to force a re-download.
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

Credentials come from the repo-root `.env` (git-ignored; see
[`.env.example`](../.env.example)) — the variables this project reads are:

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

All commands also accept `--workers N` to download/upload concurrently.

## Task runner (`justfile`)

Run `just` from this folder:

```bash
just                                  # list recipes
just scan 2026-09-01                  # scan BEGIN..END, list files missing from Qiniu
just download /tmp/pdfs 2026-09-01    # download those files into PATH
just download-keyword /tmp/pdfs "邮盈惠丰2026年第五期"   # download by keyword
just download-issuance 2026-09-19     # 发行文件 for BEGIN..END into ./docs
just download-pricing 2026-09-10      # 发行结果 for BEGIN..END into ./docs
just download-issuance-pricing 2026-09-18   # 发行文件 + 发行结果 into ./docs
just download-deal-docs 2026-09-18    # every doc type into ./docs
just shell                            # enter the Nix dev shell
```

- `just scan BEGIN [END]` scans chinabond from `BEGIN` to `END` and lists the
  files that are not yet in `qiniu_storage`.
- `just download PATH BEGIN [END]` downloads the missing files into `PATH`.
- `just download-keyword PATH KEYWORD [BEGIN] [END]` downloads the missing files
  whose name matches `KEYWORD`; `BEGIN`/`END` are optional date filters.
- `just download-issuance BEGIN [END]`, `just download-pricing BEGIN [END]`,
  `just download-issuance-pricing BEGIN [END]` and
  `just download-deal-docs BEGIN [END]` are the deal-docs download jobs from
  `flow/dags/scheduler.py` (`eager_download_issue_file`,
  `eager_download_pricing_file`, `safenet_eager_download` and the download step
  of `pullIncomeDocs`). They download into this project's `docs/` folder; the
  post-download steps (location allocation, MinerU, deal attachment) stay in the
  `scheduler` project.
- `BEGIN`/`END` accept `YYYY-MM-DD`; `END` defaults to today.

Both download recipes avoid duplication in two ways:

- a document whose Qiniu key is **already in `qiniu_storage`** is never fetched
  (the renamed attachments in `chinabond.RENAMES` are compared under their
  stored local name);
- a document whose file **already exists in the target folder** is not
  downloaded again — the local file is uploaded to Qiniu and recorded in
  `qiniu_storage` directly.

## Scheduled downloads (Docker)

`doctocloud.cron` schedules the deal-docs download recipes at the same
frequencies as `flow/dags/scheduler.py`. The Dockerfile installs it as
`/etc/cron.d/doctocloud` and `docker-entrypoint.sh` starts the cron daemon, so a
container started with the image runs the jobs automatically:

| cron expression | run interval | recipe (scan window) | scheduler job |
|---|---|---|---|
| `30 9-21 * * 1-6` | Every hour at **:30**, from 09:30 to 21:30, Monday–Saturday (13 runs/day) | `download-issuance` (last 1 day) | `eager_download_issue_file` |
| `0 9-21 * * 1-6` | Every hour on the hour, from 09:00 to 21:00, Monday–Saturday (13 runs/day) | `download-pricing` (last 10 days) | `eager_download_pricing_file` |
| `0 22 * * 1-6` | Once a day at **22:00**, Monday–Saturday | `download-issuance-pricing` (last 2 days) | `safenet_eager_download` |
| `0 19 * * *` | Once a day at **19:00**, every day | `download-deal-docs` (last 2 days) | `pullIncomeDocs` |

The cron fields are `minute hour day-of-month month day-of-week`; `1-6` means
Monday through Saturday. Times use the container's local time (UTC unless `TZ`
is set).

Credentials are taken from the container environment (`docker run --env-file`),
never the image. Use the repository-root [`.env.example`](../.env.example),
which defines the `DATABASE_*` and `QINIU_*` variables these recipes need, and
supply it at run time together with the download folder mount:

```bash
cp .env.example .env   # run from the repo root, then fill in the real values
mkdir -p docToCloud/docs docToCloud/logs

docker run -d --name china-abs --restart unless-stopped \
    --env-file .env \
    -v "$PWD/docToCloud/docs:/app/docToCloud/docs" \
    -v "$PWD/docToCloud/logs:/app/docToCloud/logs" \
    china-abs:latest
```

- `/app/docToCloud/docs` is the recipes' target folder (`main.py --dir` default
  inside the image). **Mount it** so downloaded PDFs survive container
  recreation.
- `/app/docToCloud/logs` holds the daily `YYYY-MM-DD.log` files; mounting it is
  optional but useful for auditing.
- The entrypoint snapshots the environment to `/etc/doctocloud.env`, which the
  cron jobs source, and starts the cron daemon. Cron's own run output is
  appended to `/var/log/doctocloud-cron.log` inside the container.

Inspect or trigger the schedule with:

```bash
docker exec china-abs tail -f /var/log/doctocloud-cron.log   # follow job output
docker exec china-abs /usr/sbin/cron -N                      # run jobs now
docker stop china-abs                                        # stop the container
```

## Logs

Every run logs to both stderr and a daily text file under `docToCloud/logs/`,
named `YYYY-MM-DD.log` (one file per calendar day; a long-running process rolls
over at midnight). Each successfully downloaded file is recorded, as are
failures and a per-run summary:

```
2026-09-20 09:30:01 - chinabond - INFO - downloading 3 file(s) into /tmp/pdfs
2026-09-20 09:30:03 - chinabond - INFO - downloaded OK: 建欣...发行说明书.pdf -> /tmp/pdfs/建欣...发行说明书.pdf
2026-09-20 09:30:04 - chinabond - ERROR - download FAILED: 某文件.pdf (https://...): 404 Client Error
2026-09-20 09:30:05 - chinabond - INFO - download summary: 1 downloaded, 2 skipped/failed
```

The log directory defaults to `docToCloud/logs/` and can be overridden with the
`DOCTOCLOUD_LOG_DIR` environment variable. The `logs/` folder is git-ignored.

## Project structure

```
docToCloud/
├── main.py       # CLI: list / fetch / upload / sync
├── chinabond.py  # scanning, attachment parsing and download
├── cloud.py      # Qiniu upload + duplicate protection
├── db.py         # adapter over china_model's QiniuStorage model
├── logging_utils.py  # daily file logging (logs/YYYY-MM-DD.log)
├── justfile      # task runner (`just scan` / `just download` / `just download-keyword`)
├── doctocloud.cron   # cron schedule installed at /etc/cron.d/doctocloud
├── logs/         # daily run logs (git-ignored)
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
