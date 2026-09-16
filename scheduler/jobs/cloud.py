"""Qiniu archive job (port of the archive part of ``datasource/cloud.py``)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from qiniu import Auth, BucketManager

log = logging.getLogger("scheduler.cloud")


def _auth() -> Auth:
    access_key = os.environ.get("QINIU_ACCESS_KEY", "")
    secret_key = os.environ.get("QINIU_SECRET_KEY", "")
    if not access_key or not secret_key:
        raise RuntimeError("QINIU_ACCESS_KEY and QINIU_SECRET_KEY must be set")
    return Auth(access_key, secret_key)


def _bucket_name() -> str:
    return os.environ.get("QINIU_BUCKET", "deal-docs")


def list_docs_files(bucket_name: str, marker, r=None, limit: int = 1000) -> list[dict]:
    """Port of ``listDocsFiles`` (recursive listing)."""
    if r is None:
        r = []
    bucket = BucketManager(_auth())
    ret, _, _ = bucket.list(bucket_name, None, marker, limit, None)
    if "marker" in ret:
        return list_docs_files(bucket_name, ret["marker"], r=r + ret["items"], limit=limit)
    return r + ret["items"]


def conver_to_stage(b_name: str, fnames, to_num: int) -> None:
    bucket = BucketManager(_auth())
    for fname in fnames:
        bucket.change_type(b_name, fname, to_num)


def archieve_files(days_cutoff: int = 90) -> None:
    """Port of ``archieveFiles``: move objects older than the cutoff to type 4."""
    log.info("[archieve files] begin")
    bucket_name = _bucket_name()
    fs = list_docs_files(bucket_name, None, limit=1000)
    cutoff = datetime.today() - timedelta(days=days_cutoff)
    active_files = [
        f["key"]
        for f in fs
        if f["type"] == 0
        and datetime.fromtimestamp(f["putTime"] / 1000_0000) <= cutoff
    ]
    conver_to_stage(bucket_name, active_files, 4)
    log.info("[archieve files] end")
