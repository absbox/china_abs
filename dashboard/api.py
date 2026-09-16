"""Dashboard API: one Python function per pipeline action.

Every function calls into a sibling subproject and returns a Markdown document
that the CLI renders.  Functions are also exposed in :data:`REGISTRY` so the
CLI can dispatch to a single one by name.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import china_model

from bridge import ROOT, doc_to_cloud, scheduler, to_markdown

log = logging.getLogger("dashboard")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _docs_dir() -> Path:
    d = Path(__file__).resolve().parent / "docs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ensure_db() -> None:
    if not china_model.is_configured():
        china_model.configure()


# --------------------------------------------------------------------------
# 1) scan & download
# --------------------------------------------------------------------------

def scan_download(begin: str, end: str | None = None) -> str:
    """Scan chinabond from ``begin`` to ``end`` and download+upload the new files."""
    end = end or _today()
    chinabond, cloud, db = doc_to_cloud()
    entries = chinabond.scan(start_date=begin, end_date=end)
    existing, _ = db.existing_docs()
    outstanding = chinabond.outstanding_entries(entries, existing)
    target = str(_docs_dir())
    paths = chinabond.download_entries(outstanding, target)
    uploaded = cloud.upload_directory(target, workers=10) if paths else []
    lines = [
        f"# Scan & download `{begin}` → `{end}`",
        "",
        f"- scanned: **{len(entries)}**",
        f"- outstanding (missing from Qiniu): **{len(outstanding)}**",
        f"- downloaded: **{len(paths)}**",
        f"- uploaded: **{len(uploaded)}**",
    ]
    if paths:
        lines += ["", "## Uploaded", ""] + [f"- `{Path(p).name}`" for p in paths]
    return "\n".join(lines)


def scan_list(begin: str, end: str | None = None) -> str:
    """List scanned documents still missing from Qiniu."""
    end = end or _today()
    chinabond, _, db = doc_to_cloud()
    entries = chinabond.scan(start_date=begin, end_date=end)
    existing, _ = db.existing_docs()
    outstanding = chinabond.outstanding_entries(entries, existing)
    lines = [
        f"# Outstanding `{begin}` → `{end}`",
        "",
        f"- scanned: **{len(entries)}**",
        f"- outstanding: **{len(outstanding)}**",
        "",
    ]
    lines += [f"- `{e.key}`" for e in outstanding]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 2) deal init / 3) allocate
# --------------------------------------------------------------------------

def deal_init(since: str | None = None) -> str:
    """Initialize deals for documents that arrived since ``since``."""
    since = since or _today()
    digest, _ = scheduler()
    _ensure_db()
    digest.allocate_to_location_by_date(since)
    return "\n".join(
        [
            f"# Deal init since `{since}`",
            "",
            "Allocation ran over `v_outstanding_files_to_location`.",
            "> Classifier / per-type handlers are still being ported from "
            "`flow/dags/datasource/digestByNewFiles.py` (see `scheduler/jobs/digest.py`).",
        ]
    )


def allocate(since: str | None = None) -> str:
    """Allocate newly uploaded files to existing deals since ``since``."""
    since = since or _today()
    digest, _ = scheduler()
    _ensure_db()
    digest.process_new(since)
    return "\n".join(
        [
            f"# Allocate since `{since}`",
            "",
            "Allocation ran over newly uploaded `qiniu_storage` rows.",
            "> Classifier / per-type handlers are still being ported from "
            "`flow/dags/datasource/digestByNewFiles.py` (see `scheduler/jobs/digest.py`).",
        ]
    )


# --------------------------------------------------------------------------
# 4) pdf -> markdown
# --------------------------------------------------------------------------

def _download_and_convert(keys: list[str]) -> str:
    convert, _, cloud = to_markdown()
    tmp = Path(tempfile.mkdtemp(prefix="dashboard_convert_"))
    downloaded: list[str] = []
    failed: list[str] = []
    try:
        for key in keys:
            path = cloud.download_file(key, target_dir=str(tmp))
            if path:
                downloaded.append(Path(path).name)
            else:
                failed.append(key)
        rc = convert.convert_pdfs(str(tmp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    lines = [
        f"# Convert PDF → markdown ({len(keys)} requested)",
        "",
        f"- downloaded: **{len(downloaded)}**",
        f"- failed download: **{len(failed)}**",
        f"- convert exit: **{rc}**",
    ]
    if failed:
        lines += ["", "## Failed", ""] + [f"- `{k}`" for k in failed]
    return "\n".join(lines)


def convert(names) -> str:
    """Convert the given Qiniu key(s) to markdown."""
    return _download_and_convert(list(names))


def convert_all() -> str:
    """Convert every outstanding PDF that has no markdown yet."""
    _, db, _ = to_markdown()
    keys = db.get_outstanding_files()
    return _download_and_convert(list(keys))


def convert_list() -> str:
    """List PDFs that have no markdown yet."""
    _, db, _ = to_markdown()
    keys = db.get_outstanding_files()
    lines = [f"# PDFs without markdown: **{len(keys)}**", ""]
    lines += [f"- `{k}`" for k in keys[:500]]
    if len(keys) > 500:
        lines.append(f"- … and {len(keys) - 500} more")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 5) digest
# --------------------------------------------------------------------------

def digest(question: str, names, provider: str = "qwen", model: str | None = None) -> str:
    """Run a single extraction question over a list of reports / markdown files.

    Delegated to the ``digester`` project's own environment (``uv run``) because
    its ``instructor`` dependency pins ``rich<15`` while the workspace uses
    ``rich>=15``; the two cannot be installed together.
    """
    cmd = ["uv", "run", "python", "digest.py", "--question", question, "--provider", provider]
    if model:
        cmd += ["--model", model]
    cmd += list(names)
    proc = subprocess.run(
        cmd, cwd=str(ROOT / "digester"), capture_output=True, text=True
    )
    lines = [
        f"# Digest `{question}` over {len(names)} report(s)",
        "",
        f"- exit: **{proc.returncode}**",
    ]
    if proc.stdout.strip():
        lines += ["", "```json", proc.stdout.rstrip(), "```"]
    if proc.stderr.strip():
        lines += ["", "## stderr", "", "```", proc.stderr.rstrip(), "```"]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# health
# --------------------------------------------------------------------------

_ENV_VARS = [
    "DATABASE_URI",
    "DATABASE_HOST",
    "QINIU_ACCESS_KEY",
    "QINIU_SECRET_KEY",
    "QINIU_BUCKET",
    "MINERU_TOKEN",
    "MONGODB_URI",
    "QWEN_API_KEY",
    "DEEPSEEK_API_KEY",
    "LLM_API_KEY",
]


def health() -> str:
    """Health-check the whole china-abs project."""
    _ensure_db()
    from china_model import Deal, Mineru, QiniuStorage

    with_md = Mineru.select().where(Mineru.markdown.is_null(False)).count()
    lines = [
        "# china-abs health",
        "",
        "## Database",
        "",
        f"- `deal`: **{Deal.select().count()}**",
        f"- `qiniu_storage`: **{QiniuStorage.select().count()}**",
        f"- `mineru`: **{Mineru.select().count()}** ({with_md} with markdown)",
    ]

    try:
        _, jobs_health = scheduler()
        report = jobs_health.run_check()
        lines += ["", "## Outstanding work", "", "| view | rows |", "|---|---:|"]
        for view, info in sorted(report.items(), key=lambda kv: -kv[1]["size"]):
            lines.append(f"| `{view}` | {info['size']} |")
    except Exception as exc:  # noqa: BLE001
        lines += ["", f"> scheduler health check failed: {exc}"]

    lines += ["", "## Configuration", "", "| variable | state |", "|---|---|"]
    for var in _ENV_VARS:
        lines.append(f"| `{var}` | {'set' if os.getenv(var) else '—'} |")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# dispatch registry ("call single function")
# --------------------------------------------------------------------------

REGISTRY = {
    "scan-download": scan_download,
    "scan-list": scan_list,
    "deal-init": deal_init,
    "allocate": allocate,
    "convert": convert,
    "convert-all": convert_all,
    "convert-list": convert_list,
    "digest": digest,
    "health": health,
}
