"""Document download / upload jobs built on ``docToCloud``.

Ports ``flow/dags/download_docs.py`` and ``datasource/downloader.scanNewDocs``:

* scanning + download + Qiniu upload now go through ``chinabond`` / ``cloud``
  / ``db`` from the ``docToCloud`` project;
* the post-download steps (allocate to location, MinerU submission) stay the
  same and live in :mod:`jobs.digest` and :mod:`jobs.mineru`.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import pathsetup  # noqa: F401
import chinabond  # docToCloud
import cloud as dtc_cloud  # docToCloud
import db as dtc_db  # docToCloud

from . import db, digest, mineru

log = logging.getLogger("scheduler.docs")

DEFAULT_CHANNELS = chinabond.DEFAULT_CHANNELS
DEFAULT_DOC_TYPES = chinabond.DEFAULT_DOC_TYPES
UPLOAD_WORKERS = 10


def docs_dir() -> str:
    return os.getenv("DOCS_DIR", str(pathsetup.SCHEDULER_DIR / "docs"))


def channel_for_pool_type(pool_type: str | None) -> str:
    """``util.getChannelStr``: RMBS -> MBS channel, otherwise ABS."""
    return "zjzczq_MBS" if pool_type == "RMBS" else "zjzczq_ABS"


def scan_new_docs(
    start_date: str,
    end_date: str,
    upload: bool = True,
    keyword: str = "",
    target: str | None = None,
    channels: list[str] | None = None,
    doc_types: list[str] | None = None,
) -> list[str]:
    """Download documents for a date window, skipping ones already in Qiniu.

    Returns the file names that were newly downloaded (flow's
    ``downloadedFileNames``).
    """
    target = target or docs_dir()
    entries = chinabond.scan(
        channels=channels,
        doc_types=doc_types,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
    )
    existing_keys, _ = dtc_db.existing_docs()
    outstanding = chinabond.outstanding_entries(entries, existing_keys)
    log.info(
        "[scanNewDocs] scanned %s, outstanding %s", len(entries), len(outstanding)
    )
    paths = chinabond.download_entries(outstanding, target)
    names = [Path(p).name for p in paths]
    if upload and names:
        dtc_cloud.upload_directory(target, workers=UPLOAD_WORKERS)
    return names


def download_docs():
    """Port of ``downloadDocs``: scan the last two days (all types)."""
    exe_date = datetime.now()
    today = exe_date.date()
    day_before_yesterday = (exe_date - timedelta(days=2)).date()
    sd = day_before_yesterday.strftime("%Y-%m-%d")
    ed = today.strftime("%Y-%m-%d")
    return scan_new_docs(sd, ed, target=docs_dir())


def download_issuance_pricing(
    cutDaysNum: int = 2,
    docTypesList=("发行文件", "发行结果"),
    kw: str = "",
    chanList: list[str] | None = None,
):
    """Port of ``download_issuance_pricing``."""
    log.info(
        "[DownloadDocs-Early] start with %s and docList %s kw=%s ",
        cutDaysNum,
        docTypesList,
        kw,
    )
    exe_date = datetime.now()
    today = exe_date.date()
    day_before_yesterday = (exe_date - timedelta(days=cutDaysNum)).date()
    sd = day_before_yesterday.strftime("%Y-%m-%d")
    ed = today.strftime("%Y-%m-%d")

    files_downloaded = scan_new_docs(
        sd,
        ed,
        target=docs_dir(),
        doc_types=list(docTypesList),
        keyword=kw,
        channels=chanList,
    )
    log.info("[DownloadDocs-Early] files downloaded: %s", files_downloaded)

    log.info("[DownloadDocs-Early] allocate to by sd %s", sd)
    digest.allocate_to_location_by_date(sd)

    if files_downloaded:
        try:
            mineru.mineru_by_list(tuple(files_downloaded))
            log.info("[MinerU Queue] add files downloaded: %s", files_downloaded)
            mineru.process_mineru_queue()
            log.info("[DownloadDocs-Early] done")
        except Exception as e:  # noqa: BLE001
            log.error("[DownloadDocs-Early] Error in mineru: %s", e)

        try:
            digest.allocate_to_location(files_downloaded)
        except Exception as e:  # noqa: BLE001
            log.error("[DownloadDocs-attach] Error in allocateToLocation: %s", e)

    return files_downloaded


def download_pricing_outstanding_deal(cutDaysNum: int = 10):
    """Port of ``download_pricing_outstanding_deal``."""
    pre_closing_deals = db.q_with_m(
        "os_check_pricing_of_preclosing", ["shortNameKey", "poolType"]
    )
    log.info(
        "[download_pricing_outstanding_deal] get pull with records %s",
        len(pre_closing_deals),
    )
    for x in pre_closing_deals:
        d = x["shortNameKey"]
        ch = [channel_for_pool_type(x["poolType"])]
        log.info("[download_pricing_outstanding_deal]: %s %s", d, ch)
        download_issuance_pricing(
            cutDaysNum=cutDaysNum, docTypesList=["发行结果"], kw=d, chanList=ch
        )


def attach_docs_to_deal(lastDays: int = 2):
    """Port of ``attachDocsToDeal``."""
    exe_date = datetime.now()
    today = exe_date.date()
    day_before_yesterday = (exe_date - timedelta(days=lastDays)).date()
    sd = day_before_yesterday.strftime("%Y-%m-%d")
    ed = today.strftime("%Y-%m-%d")
    digest.process_new(sd, ed)


def convert_deal_docs_to_md():
    """Port of ``convertDealDocsToMd`` (MinerU submission)."""
    exe_date = datetime.now()
    today = exe_date.date()
    day_before_yesterday = (exe_date - timedelta(days=2)).date()
    sd = day_before_yesterday.strftime("%Y-%m-%d")
    ed = today.strftime("%Y-%m-%d")
    digest.digitalized(sd, ed)


def pull_income_docs():
    """Port of ``pullIncomeDocs``."""
    log.info("[DownloadDocs] start")
    download_docs()
    log.info("[Convert to MD] start")
    convert_deal_docs_to_md()
    log.info("[Attach Deal Docs] start")
    attach_docs_to_deal()
    log.info("[UpdateDealStatus] start")
    digest.change_deals_status()
    log.info("[pullIncomeDocs] Done")
