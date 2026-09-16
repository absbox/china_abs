"""PostgreSQL helpers for the scheduler.

Where a shared model exists (``Mineru``, ``HealthCheck``, ``Stage``/``Deal``)
the :mod:`china_model` package is used.  The reporting views and reference
tables that are not modelled are accessed with plain psycopg, mirroring
``flow/dags/datasource/db.py``.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from urllib.parse import unquote, urlparse

import china_model
import psycopg
from dotenv import load_dotenv

load_dotenv()


def ensure_configured() -> None:
    """Bind the shared Peewee database proxy on first use."""
    if not china_model.is_configured():
        china_model.configure()


def _conn_kwargs() -> dict:
    # A full DSN (DATABASE_URI) takes precedence, matching china_model.
    dsn = os.getenv("DATABASE_URI", "")
    if "://" in dsn:
        url = urlparse(dsn)
        return {
            "host": url.hostname or "localhost",
            "port": url.port or 5432,
            "user": unquote(url.username) if url.username else os.getenv("DATABASE_USER", "doadmin"),
            "password": unquote(url.password) if url.password else os.getenv("DATABASE_PASSWORD"),
            "dbname": (url.path or "/").lstrip("/") or os.getenv("DATABASE_NAME", "deal-library"),
            "connect_timeout": 30,
        }
    host = os.getenv("DATABASE_HOST") or os.getenv("DATABASE_URL") or "localhost"
    return {
        "host": host,
        "port": int(os.getenv("DATABASE_PORT", "5432")),
        "user": os.getenv("DATABASE_USER", "doadmin"),
        "password": os.getenv("DATABASE_PASSWORD"),
        "dbname": os.getenv("DATABASE_NAME", "deal-library"),
        "connect_timeout": 30,
    }


@contextmanager
def get_conn():
    conn = psycopg.connect(**_conn_kwargs())
    try:
        yield conn
    finally:
        conn.close()


def fetchall(sql: str, params=None) -> list[tuple]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def execute(sql: str, params=None) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()


def q_with_m(tbl: str, fs, where: str | None = None) -> list[dict]:
    """Port of ``flow/dags/datasource/db.py::q_with_m``."""
    fstr = '","'.join(fs)
    sql = f'select "{fstr}" from {tbl}'
    if where:
        sql += f' where {where}'
    return [dict(zip(fs, r)) for r in fetchall(sql)]


def has_markdown(key: str) -> bool:
    """Whether ``key`` has a non-null markdown extraction in ``mineru``."""
    ensure_configured()
    mineru = china_model.Mineru
    return (
        mineru.select()
        .where((mineru.key == key) & mineru.markdown.is_null(False))
        .exists()
    )


def mineru_existing_keys() -> set[str]:
    """Keys already converted to markdown (port of ``mineruExistingKey``)."""
    ensure_configured()
    mineru = china_model.Mineru
    rows = mineru.select(mineru.key).where(mineru.markdown.is_null(False))
    return {r.key for r in rows}
