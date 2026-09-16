"""PostgreSQL access for the ``qiniu_storage`` catalogue.

All persistence now goes through the shared :mod:`china_model` package, so this
module is a thin adapter over the ``QiniuStorage`` model.  The models are
configured lazily on first use, so importing this module has no side effects.
"""

from __future__ import annotations

import china_model
from china_model import QiniuStorage


def ensure_configured() -> None:
    """Bind the shared database proxy on first use."""
    if not china_model.is_configured():
        china_model.configure()


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
