"""Cleanup jobs (port of ``flow/dags/cleanup.py``)."""

from __future__ import annotations

import logging
import os
import random
from pathlib import Path

import pathsetup

from . import db, mineru

log = logging.getLogger("scheduler.cleanup")


def _cleanup_dirs() -> list[str]:
    default = os.pathsep.join(
        [
            str(pathsetup.SCHEDULER_DIR),
            str(pathsetup.SCHEDULER_DIR / "docs"),
            str(pathsetup.SCHEDULER_DIR / "docs" / "downloaded"),
        ]
    )
    return [p for p in os.getenv("CLEANUP_DIRS", default).split(os.pathsep) if p]


def outstanding_pdf(x: int):
    """Random sample of ``x`` not-yet-converted files from ``os_mineru``."""
    r = [m["key"] for m in db.q_with_m("os_mineru", ["key"])]
    return random.sample(list(r), x)


def catch_up_pdf():
    """``catchUpPdf``: submit 498 outstanding PDFs to MinerU."""
    ofiles = outstanding_pdf(498)
    job_ids = mineru.mineru_by_list(ofiles)
    log.info("[catchUpPdf] submit with job: %s", job_ids)


def delete_legacy_pdf(p: str) -> None:
    """Delete local pdf/zip/doc/docx files that already have markdown."""
    folder = Path(p)
    if not folder.exists():
        log.error("path '%s' does not exist", folder)
        return
    if not folder.is_dir():
        log.error("'%s' is not a directory", folder)
        return

    all_pdfs = []
    for file_path in folder.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in [".pdf", ".zip", ".doc", ".docx"]:
            all_pdfs.append((file_path.name, file_path))

    log.info("outstanding files: %s", all_pdfs)
    the_pdf_has_markdown = [fpath for (fn, fpath) in all_pdfs if db.has_markdown(fn)]
    log.info("files to be delete: %s", the_pdf_has_markdown)
    [x.unlink() for x in the_pdf_has_markdown]


def delete_unused_files():
    """``deleteUnusedFiles``: prune converted files from the staging folders."""
    for d in _cleanup_dirs():
        delete_legacy_pdf(d)
