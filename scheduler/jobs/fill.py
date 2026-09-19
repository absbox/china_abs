"""Deal-data fill jobs.

Port of the orchestration in ``flow/dags/fill_data.py``.  The deal fill
functions now live in the :mod:`assembler` subproject and are imported from
there, so the scheduler only owns the schedule and the LLM-extraction stubs.

The LLM extractors that produce the parse results the fill steps consume
(``datasource/LLM_filling_preClosing.py``) still depend on the LLM
infrastructure and are stubbed; they belong with the ``digester`` / ``reader``
projects rather than the assembler.
"""

from __future__ import annotations

import logging

from assembler.fill import (  # noqa: F401  (re-exported for the scheduler)
    IssuePlansInit,
    fill_trading_price,
    fillDealEndDate,
    fillInitView,
    fillIsin,
    fillPoolPerfNPL,
    fillSeqView,
    fillTrusteePeriod,
    fillWaterfall,
    fixPoolType,
    initClearRpt,
    preClosingDealsDataInit,
    processTrusteeReports,
    tieoutBalanceForBalance,
    toFillBond,
    toFillPricing,
)
from assembler.fill import fill_deal_data_obj  # noqa: F401

log = logging.getLogger("scheduler.fill")


def _not_migrated(name: str):
    def _stub(*args, **kwargs):
        log.warning("[fill] %s not migrated yet (port from flow/dags/datasource)", name)

    _stub.__name__ = name
    return _stub


# --- LLM extraction functions (LLM_filling_preClosing.py) -----------------
runInitRatingReport = _not_migrated("runInitRatingReport")
runSeqRatingReport = _not_migrated("runSeqRatingReport")
runIssuePlan = _not_migrated("runIssuePlan")
runPricingAnns = _not_migrated("runPricingAnns")
runTrusteeReports = _not_migrated("runTrusteeReports")
runClearReports = _not_migrated("runClearReports")


def llm_extract_deal_data():
    """Port of ``llm_extract_deal_data`` (all six LLM extractors)."""
    llm_funcs = [
        runInitRatingReport,
        runSeqRatingReport,
        runIssuePlan,
        runPricingAnns,
        runTrusteeReports,
        runClearReports,
    ]
    for fn in llm_funcs:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            log.error("[llm fun ] fun:%s error:%s", fn, e)


def parse_issuance_pricing():
    """Port of ``parse_issuance_pricing`` (init rating / issue plan / pricing)."""
    llm_funcs = [
        runInitRatingReport,
        runIssuePlan,
        runPricingAnns,
    ]
    for fn in llm_funcs:
        try:
            log.info("[llm fun ] run fun:%s", fn)
            fn()
        except Exception as e:  # noqa: BLE001
            log.error("[llm fun ] fun:%s error:%s", fn, e)
