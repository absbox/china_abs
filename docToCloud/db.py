"""PostgreSQL access for the ``qiniu_storage`` catalogue.

All persistence now goes through the shared :mod:`china_model` package, so this
module is a thin adapter over the ``QiniuStorage``, ``Location``, ``ReportType``
and ``Report`` models.  The models are configured lazily on first use, so
importing this module has no side effects.

An uploaded document is registered in two places:

* ``qiniu_storage`` — the object-storage catalogue (:func:`record_doc`);
* ``report`` — the unified report catalogue, backed by a ``location`` row and a
  report type inferred from the file name (:func:`record_report`).
"""

from __future__ import annotations

import re

import china_model
from china_model import Location, QiniuStorage, Report, ReportType

# Ordered ``(report-type name, pattern)`` rules; the first match wins.  The
# names mirror the rows in ``reporttype``; a name missing from that table is
# simply skipped (see :func:`classify_report_type_name`).
_REPORT_TYPE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("更正公告/更正说明", re.compile(r"更正")),
    ("资产支持证券持有人大会（召集/决议）公告", re.compile(r"持有人大会|持有人会议")),
    ("承销团成员/投标人名单", re.compile(r"承销团|投标人名单")),
    ("投资者报告", re.compile(r"投资者报告")),
    ("持续购买公告", re.compile(r"持续购买公告")),
    ("重大事件/重大事项报告书", re.compile(r"重大事件报告书|重大事项报告书")),
    ("清算专项复核说明/报告", re.compile(r"专项复核")),
    ("清算专项报告/说明", re.compile(r"清算专项")),
    ("审计报告（年度/清算专项审计）", re.compile(r"审计报告")),
    ("清算报告", re.compile(r"清算报告")),
    ("受托机构报告（月度/期间报告）", re.compile(r"受托.*报告")),
    ("信用评级/跟踪评级报告", re.compile(r"评级报告|信用评级|跟踪评级|售前评级|评级安排")),
    ("发行结果公告（簿记建档）", re.compile(r"簿记建档|薄记建档|发行结果公告")),
    ("发行公告", re.compile(r"发行公告")),
    ("发行说明书", re.compile(r"发行说明书")),
    ("发行办法", re.compile(r"发行办法")),
    ("申购和配售办法说明/申购要约", re.compile(r"申购")),
    ("信托公告/成立公告/信托设立公告", re.compile(r"信托公告|成立公告|设立公告")),
    ("年度专项报告", re.compile(r"专项报告")),
    ("发行变更/推迟发行公告", re.compile(r"推迟发行|变更的说明")),
]


def ensure_configured() -> None:
    """Bind the shared database proxy on first use."""
    if not china_model.is_configured():
        china_model.configure()


def classify_report_type_name(key: str) -> str | None:
    """Return the consolidated report-type name for ``key``, or ``None``."""
    for name, pattern in _REPORT_TYPE_RULES:
        if pattern.search(key):
            return name
    return None


def existing_docs() -> tuple[set[str], set[str]]:
    """Return ``(keys, hashes)`` already recorded in ``qiniu_storage``."""
    ensure_configured()
    rows = QiniuStorage.select(QiniuStorage.key, QiniuStorage.hash).tuples()
    keys = {r[0] for r in rows if r[0]}
    hashes = {r[1] for r in rows if r[1]}
    return keys, hashes


def existing_doc_keys() -> set[str]:
    """Return the set of object keys already stored in Qiniu."""
    return existing_docs()[0]


def has_doc(key: str) -> bool:
    """Return whether ``key`` is already recorded in ``qiniu_storage``."""
    ensure_configured()
    return QiniuStorage.select().where(QiniuStorage.key == key).exists()


def record_doc(bucket: str, key: str, ts: int, file_hash: str, md5: str | None) -> None:
    """Record an uploaded object, updating the row if the key already exists."""
    ensure_configured()
    (
        QiniuStorage.insert(bucket=bucket, key=key, ts=ts, hash=file_hash, md5=md5)
        .on_conflict(
            conflict_target=[QiniuStorage.key],
            update={
                QiniuStorage.bucket: bucket,
                QiniuStorage.ts: ts,
                QiniuStorage.hash: file_hash,
                QiniuStorage.md5: md5,
            },
        )
        .execute()
    )


def _report_type(key: str) -> ReportType | None:
    """Look up the ``reporttype`` row matching ``key`` (``None`` if unknown)."""
    name = classify_report_type_name(key)
    if name is None:
        return None
    return ReportType.get_or_none(ReportType.name == name)


def record_location(bucket: str, key: str, name: str = "qiniu") -> Location:
    """Return the ``location`` row for an object, creating it when missing."""
    ensure_configured()
    location, _ = Location.get_or_create(name=name, bucket=bucket, key=key)
    return location


def record_report(bucket: str, key: str, *, date=None) -> Report:
    """Register an uploaded document in the unified ``report`` catalogue.

    Creates the backing ``location`` row and a ``report`` row whose type is
    inferred from the file name.  Existing rows are reused and their report
    type back-filled when it was previously unknown.
    """
    ensure_configured()
    location = record_location(bucket, key)
    rpt_type = _report_type(key)
    report, created = Report.get_or_create(
        loc=location,
        defaults={"deal": None, "rptType": rpt_type, "date": date},
    )
    if not created and report.rptType_id is None and rpt_type is not None:
        report.rptType = rpt_type
        report.save(only=[Report.rptType])
    return report
