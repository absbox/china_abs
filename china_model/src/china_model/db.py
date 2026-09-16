"""Database configuration for the shared china-model library.

The models are bound to a :class:`peewee.DatabaseProxy` so that importing
``china_model`` has **no** side effects: nothing connects and no environment
variables are read until the host application calls :func:`configure`.

Typical use::

    import china_model

    china_model.configure()                       # read DATABASE_* env vars
    china_model.configure("postgresql://...")     # or pass a DSN explicitly

    from china_model import Deal
    Deal.select().count()
"""

from __future__ import annotations

import os
from urllib.parse import parse_qs, unquote, urlparse

from dotenv import load_dotenv
from peewee import DatabaseProxy
from playhouse.postgres_ext import PooledPsycopg3Database

__all__ = ["db", "configure", "is_configured"]

# Every model's ``Meta.database`` points at this proxy.  It is initialised by
# :func:`configure` (usually once, at application startup).
db = DatabaseProxy()

_DEFAULTS = {
    "max_connections": 20,
    "stale_timeout": 300,
    "register_hstore": True,
}


def is_configured() -> bool:
    """Return whether :func:`configure` has been called."""
    return db.obj is not None


def _dsn_to_options(dsn: str) -> dict:
    """Parse a ``postgresql://`` URL into connection kwargs."""
    url = urlparse(dsn)
    options = {
        "database": (url.path or "/").lstrip("/"),
        "user": unquote(url.username) if url.username else None,
        "password": unquote(url.password) if url.password else None,
        "host": url.hostname or "localhost",
    }
    if url.port:
        options["port"] = url.port
    for key, values in parse_qs(url.query).items():
        options[key] = values[0]
    return options


def configure(
    dsn: str | None = None,
    *,
    load_env: bool = True,
    env_file: str | None = None,
    **overrides,
):
    """Bind the shared :data:`db` proxy to a PostgreSQL database.

    Args:
        dsn: optional URL (``postgresql://user:pw@host:port/db``).  When
            omitted, the connection is built from ``DATABASE_*`` env vars.
        load_env: call ``load_dotenv`` before reading env vars (ignored when
            ``dsn`` is provided).
        env_file: explicit path to a ``.env`` file.
        **overrides: connection kwargs, e.g. ``max_connections=20``.

    Returns:
        The initialised database instance.
    """
    if dsn is not None:
        options = _dsn_to_options(dsn)
    else:
        if load_env:
            load_dotenv(env_file) if env_file else load_dotenv()
        env_dsn = os.getenv("DATABASE_URI", "")
        if "://" in env_dsn:
            options = _dsn_to_options(env_dsn)
        else:
            # ``DATABASE_URL`` was historically used to hold just the host (no
            # scheme) by the web app and the flow pipeline; accept it as a
            # fallback.
            host = os.getenv("DATABASE_HOST")
            if not host:
                legacy = os.getenv("DATABASE_URL", "")
                host = legacy if legacy and "://" not in legacy else "localhost"
            options = {
                "database": os.getenv("DATABASE_NAME", "deal-library"),
                "user": os.getenv("DATABASE_USER", "doadmin"),
                "password": os.getenv("DATABASE_PASSWORD"),
                "host": host,
                "port": int(os.getenv("DATABASE_PORT", "5432")),
            }

    options = _DEFAULTS | options | overrides
    conn = PooledPsycopg3Database(**options)
    db.initialize(conn)
    return conn
