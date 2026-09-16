"""Document digest / allocation jobs.

The thin, DB-driven steps are ported exactly from
``flow/dags/datasource/digestByNewFiles.py`` and
``flow/dags/datasource/updateStage.py``.  The document *classifier* and the 15
``update*`` allocation handlers are large regex/LLM-adjacent modules that have
not been migrated yet; they are stubbed here so the job graph and the
allocation orchestration stay identical.  Replace the stubs in
:data:`PROCESS_MAP` when porting.
"""

from __future__ import annotations

import logging
from datetime import datetime

import china_model

from . import db, mineru

log = logging.getLogger("scheduler.digest")

# Categories produced by the classifier / consumed by allocate_to_location.
CATEGORIES = [
    "correction",
    "oc",
    "issuePlan",
    "rating",
    "trustee",
    "clear",
    "pricing",
    "booking",
    "event",
    "announce",
    "sales",
    "closingAnn",
    "periodRpt",
    "issueAnn",
    "trustAnn",
]


def _not_migrated(name: str):
    def _stub(*args, **kwargs):
        log.warning("[digest] %s not migrated yet (port from flow/dags/datasource)", name)

    _stub.__name__ = name
    return _stub


def classify_files(acc, xs):
    """TODO(port): ``flow/dags/datasource/digestByNewFiles.classifyFiles``.

    Returns an empty bucket per category so ``allocate_to_location`` can run.
    """
    log.warning("[digest] classify_files not migrated yet; returning empty buckets")
    return {k: [] for k in CATEGORIES}


# One stub per handler; names match the source processMap.
updateCorrection = _not_migrated("updateCorrection")
populateDealInit = _not_migrated("populateDealInit")
updateIssuePlan = _not_migrated("updateIssuePlan")
updateRatingRpt = _not_migrated("updateRatingRpt")
updateTrustee = _not_migrated("updateTrustee")
updateClear = _not_migrated("updateClear")
updatePricing = _not_migrated("updatePricing")
updateBooking = _not_migrated("updateBooking")
updateEvent = _not_migrated("updateEvent")
updateTrustAnn = _not_migrated("updateTrustAnn")
updateSales = _not_migrated("updateSales")
updateClosingAnn = _not_migrated("updateClosingAnn")
updatePeriodReport = _not_migrated("updatePeriodReport")
updateIssueAnn = _not_migrated("updateIssueAnn")
updateTrustIssueAnn = _not_migrated("updateTrustIssueAnn")

PROCESS_MAP = {
    "correction": updateCorrection,
    "oc": populateDealInit,
    "issuePlan": updateIssuePlan,
    "rating": updateRatingRpt,
    "trustee": updateTrustee,
    "clear": updateClear,
    "pricing": updatePricing,
    "booking": updateBooking,
    "event": updateEvent,
    "announce": updateTrustAnn,
    "sales": updateSales,
    "closingAnn": updateClosingAnn,
    "periodRpt": updatePeriodReport,
    "issueAnn": updateIssueAnn,
    "trustAnn": updateTrustIssueAnn,
}


def allocate_to_location(xs, debug: bool = False):
    """Port of ``allocateToLocation`` (orchestration only; handlers stubbed)."""
    classified_new_docs = classify_files({}, xs)
    log.info({k: len(v) for k, v in classified_new_docs.items()})
    if debug:
        log.debug("%s", classified_new_docs)
    for k, fn in PROCESS_MAP.items():
        inputs = classified_new_docs.get(k, [])
        try:
            log.info("[%s]: %s", k, len(inputs))
            fn(inputs)
        except Exception as e:  # noqa: BLE001
            log.error("%s", e)


def allocate_to_location_by_date(sd: str, debug: bool = False):
    """Port of ``allocateToLocationByDate``."""
    st = int(datetime.strptime(sd, "%Y-%m-%d").timestamp())
    rows = db.fetchall(
        "select key from v_outstanding_files_to_location where ts >= %s", (st,)
    )
    xs = [r[0] for r in rows]
    allocate_to_location(xs, debug)


def process_new(sd: str, ed: str | None = None, debug: bool = False):
    """Port of ``processNew``: allocate files uploaded in a time window."""
    st = int(datetime.strptime(sd, "%Y-%m-%d").timestamp())
    et = int(datetime.now().timestamp()) if ed is None else int(
        datetime.strptime(ed, "%Y-%m-%d").timestamp()
    )
    rows = db.fetchall(
        "select key from qiniu_storage where ts >= %s and ts <= %s", (st, et)
    )
    new_files_downloaded = [r[0] for r in rows]
    if not new_files_downloaded:
        log.info("No new file to process")
    log.info(" total coming files %s", len(new_files_downloaded))
    allocate_to_location(new_files_downloaded, debug)


def digitalized(sd: str, ed: str | None = None):
    """Port of ``digitalized``: submit new files to MinerU."""
    st = int(datetime.strptime(sd, "%Y-%m-%d").timestamp())
    et = int(datetime.now().timestamp()) if ed is None else int(
        datetime.strptime(ed, "%Y-%m-%d").timestamp()
    )
    rows = db.fetchall(
        "select key from qiniu_storage where ts >= %s and ts <= %s", (st, et)
    )
    new_files_downloaded = [r[0] for r in rows]
    if not new_files_downloaded:
        log.info("No new file to process")
    return mineru.mineru_by_list(
        list(set(new_files_downloaded) - db.mineru_existing_keys())
    )


def update_deal_status(d):
    """Port of ``updateStage.updateDealStatus``."""
    stage = china_model.Stage
    m = {
        "clear": d.clearReports.count(),
        "trustee": d.trusteeReports.count(),
        "pricing": d.pricingReport.count(),
    }
    if m["clear"]:
        log.info("found clear doc %s, convert to stage 3", m["clear"])
        d.stage = 3
        d.save()
        return
    if (d.stage == stage.get_by_id(1)) and (m["trustee"] > 0 or m["pricing"] > 0):
        log.info(
            "changing deal%s to status <current> by %s,%s",
            d.dealid,
            m["trustee"],
            m["pricing"],
        )
        d.stage = 2
        d.save()
        return


def change_deals_status():
    """Port of ``updateStage.changeDealsStatus``."""
    db.ensure_configured()
    stage = china_model.Stage
    non_cleared_deals = list(stage.get_by_id(1).deals) + list(stage.get_by_id(2).deals)
    for d in non_cleared_deals:
        update_deal_status(d)
