"""Health snapshot job (port of ``flow/dags/datasource/healthChecker.py``)."""

from __future__ import annotations

import logging
from datetime import datetime

import china_model

from . import db

log = logging.getLogger("scheduler.health")

# (view name, fields) -- identical to the source list.
SOURCES = [
    ("os_llm_trustee_data", ["trReportID", "key"]),
    ("os_llm_seq_rating_data", ["RatingReportID", "key"]),
    ("os_llm_pricing_data", ["prReportID", "key"]),
    ("os_llm_issue_plan_data", ["ipReportID", "key"]),
    ("os_llm_init_rating_data", ["RatingReportID", "key"]),
    ("os_llm_deal_waterfall", ["dealid", "key"]),
    ("os_llm_clear_data", ["dealid", "clearReportID", "key"]),
    ("os_fill_trusteereport_pool_data_npl", ["deal_id", "period"]),
    ("os_fill_trusteereport_period", ["deal_id", "key"]),
    ("os_fill_trustee_report", ["deal_id", "loc_id", "TrPeriod"]),
    ("os_fill_trading_price", ["bond_id"]),
    ("os_fill_rating_seq_view", ["dealid"]),
    ("os_fill_rating_init_view", ["deal_id"]),
    ("os_fill_pricing_data", ["dealid", "key"]),
    ("os_fill_npl_subpooltype", ["dealid"]),
    ("os_fill_issue_plan", ["dealid", "key"]),
    ("os_fill_isin_code", ["isinCode", "bond_code"]),
    ("os_fill_isin", ["isinCode", "bond_code"]),
    ("os_fill_init_rating_data", ["dealid", "key"]),
    ("os_fill_deal_enddate", ["dealid"]),
    ("os_fill_clear", ["dealid"]),
    ("os_fill_bond_curbalance", ["deal_id"]),
    ("os_fill_bond", ["dealid"]),
]


def run_check(drop_zero: bool = True) -> dict:
    """Port of ``runCheck``: snapshot every outstanding-work view."""

    def pull_view(v_name, v_fields):
        r = db.q_with_m(v_name, v_fields)
        return {"size": len(r), "records": r}

    x = {v: pull_view(v, fs) for (v, fs) in SOURCES}
    if drop_zero:
        x = {k: v for k, v in x.items() if v["size"] > 0}
    return x


def write_health_report():
    """Port of ``writeHealthReport`` (upsert one row per day)."""
    db.ensure_configured()
    health = china_model.HealthCheck
    now = datetime.now()
    today = now.date()
    if (rpt := health.get_or_none(health.date == today)):
        rpt.data = run_check()
        rpt.ts = now
        rpt.save()
    else:
        health.create(date=today, data={}, ts=now)
        write_health_report()
