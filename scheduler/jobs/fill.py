"""Deal-data extraction / fill jobs.

Ports the orchestration in ``flow/dags/fill_data.py``.  The underlying LLM
extraction functions (``datasource/LLM_filling_preClosing.py``) and the deal
fill functions (``datasource/fill_data_fun.py``, >1500 lines) depend on the LLM
infrastructure and are not migrated here yet; they are stubbed so the job graph
and the function lists stay identical.  Replace the stubs to complete the port.
"""

from __future__ import annotations

import logging

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

# --- deal fill functions (fill_data_fun.py) -------------------------------
toFillPricing = _not_migrated("toFillPricing")
toFillBond = _not_migrated("toFillBond")
IssuePlansInit = _not_migrated("IssuePlansInit")
preClosingDealsDataInit = _not_migrated("preClosingDealsDataInit")
initClearRpt = _not_migrated("initClearRpt")
fillTrusteePeriod = _not_migrated("fillTrusteePeriod")
processTrusteeReports = _not_migrated("processTrusteeReports")
fixPoolType = _not_migrated("fixPoolType")
fillWaterfall = _not_migrated("fillWaterfall")
fillInitView = _not_migrated("fillInitView")
fillSeqView = _not_migrated("fillSeqView")
fillDealEndDate = _not_migrated("fillDealEndDate")
tieoutBalanceForBalance = _not_migrated("tieoutBalanceForBalance")
fillPoolPerfNPL = _not_migrated("fillPoolPerfNPL")
fillIsin = _not_migrated("fillIsin")
fill_trading_price = _not_migrated("fill_trading_price")


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


def fill_deal_data_obj():
    """Port of ``fill_deal_data_obj`` (all sixteen fill functions)."""
    fill_funcs = [
        toFillPricing,
        toFillBond,
        IssuePlansInit,
        preClosingDealsDataInit,
        initClearRpt,
        fillTrusteePeriod,
        processTrusteeReports,
        fixPoolType,
        fillWaterfall,
        fillInitView,
        fillSeqView,
        fillDealEndDate,
        tieoutBalanceForBalance,
        fillPoolPerfNPL,
        fillIsin,
        fill_trading_price,
    ]
    for fn in fill_funcs:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            log.error("[fill fun ] fun:%s error:%s", fn, e)
