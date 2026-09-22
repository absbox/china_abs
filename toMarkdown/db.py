"""PostgreSQL access for the ``qiniu_storage`` and ``mineru`` catalogues.

All persistence now goes through the shared :mod:`china_model` package, so this
module is a thin adapter over the ``QiniuStorage`` and ``Mineru`` models.  The
models are configured lazily on first use, so importing this module has no side
effects.
"""

from __future__ import annotations

import time

import china_model
from china_model import Mineru, QiniuStorage


def ensure_configured() -> None:
    """Bind the shared database proxy on first use."""
    if not china_model.is_configured():
        china_model.configure()


def check_connection() -> None:
    """Fail fast with a readable error if PostgreSQL is unreachable."""
    ensure_configured()
    china_model.check_connection()


def get_outstanding_files() -> list[str]:
    """Return names of files in qiniu_storage that have no markdown in mineru."""
    ensure_configured()
    already_converted = Mineru.select(Mineru.key).where(Mineru.markdown.is_null(False))
    query = (
        QiniuStorage.select(QiniuStorage.key)
        .where(
            QiniuStorage.key.is_null(False)
            & QiniuStorage.key.not_in(already_converted)
        )
        .distinct()
    )
    return [row.key for row in query]


def converted_keys() -> set[str]:
    """Return the set of keys that already have a non-null markdown extraction."""
    ensure_configured()
    rows = Mineru.select(Mineru.key).where(Mineru.markdown.is_null(False))
    return {row.key for row in rows}


def has_markdown(key: str) -> bool:
    """Whether ``key`` already has a non-null markdown extraction."""
    ensure_configured()
    return (
        Mineru.select()
        .where((Mineru.key == key) & Mineru.markdown.is_null(False))
        .exists()
    )


def save_markdown(key: str, markdown: str, model: str) -> None:
    """Upsert a markdown result into the mineru table."""
    ensure_configured()
    now = int(time.time())
    (
        Mineru.insert(key=key, markdown=markdown, model=model, ts=now)
        .on_conflict(
            conflict_target=[Mineru.key],
            update={Mineru.markdown: markdown, Mineru.model: model, Mineru.ts: now},
        )
        .execute()
    )
