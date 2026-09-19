"""Dashboard API: status / health checks for the china-abs project.

The dashboard is read-only.  :func:`health` inspects the shared database and
the outstanding-work views and returns a Markdown document that the CLI
renders.  Actions live in the component that owns them; see each component's
``justfile``.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import china_model

from bridge import scheduler


def _ensure_db() -> None:
    if not china_model.is_configured():
        china_model.configure()


_ENV_VARS = [
    "DATABASE_URI",
    "DATABASE_HOST",
    "QINIU_ACCESS_KEY",
    "QINIU_SECRET_KEY",
    "QINIU_BUCKET",
    "MINERU_TOKEN",
    "MONGODB_URI",
    "QWEN_API_KEY",
    "DEEPSEEK_API_KEY",
    "LLM_API_KEY",
]


def _cell(text: object) -> str:
    """Render ``text`` as a single Markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def _pg_target() -> str:
    """Human-readable PostgreSQL target (no credentials)."""
    dsn = os.getenv("DATABASE_URI", "")
    if "://" in dsn:
        u = urlparse(dsn)
        host = u.hostname or "localhost"
        port = f":{u.port}" if u.port else ""
        name = (u.path or "").lstrip("/")
        return f"{host}{port}/{name}" if name else f"{host}{port}"
    host = os.getenv("DATABASE_HOST", "localhost")
    port = os.getenv("DATABASE_PORT", "5432")
    name = os.getenv("DATABASE_NAME", "deal-library")
    return f"{host}:{port}/{name}"


def check_postgres() -> tuple[bool, str]:
    """Connect to PostgreSQL and run a trivial query. Returns ``(ok, detail)``."""
    _ensure_db()
    from china_model import db as pg_db

    target = _pg_target()
    try:
        with pg_db.connection_context():
            row = pg_db.execute_sql("SELECT version()").fetchone()
        version = (row[0] if row else "?").split(" on ")[0]
        return True, f"{target} — {version}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{target} — {type(exc).__name__}: {exc}"


def _mongo_target() -> str:
    """Human-readable MongoDB target (no credentials)."""
    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    try:
        u = urlparse(uri)
        host = u.hostname or "localhost"
        port = f":{u.port}" if u.port else ""
        return f"mongodb://{host}{port}"
    except Exception:  # noqa: BLE001
        return "mongodb"


def check_mongo() -> tuple[bool, str]:
    """Ping MongoDB. Returns ``(ok, detail)``."""
    from pymongo import MongoClient

    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    target = _mongo_target()
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
        version = client.server_info().get("version", "?")
        return True, f"{target} — MongoDB {version}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{target} — {type(exc).__name__}: {exc}"
    finally:
        client.close()


def health() -> str:
    """Health-check the whole china-abs project."""
    pg_ok, pg_detail = check_postgres()
    mongo_ok, mongo_detail = check_mongo()

    lines = [
        "# china-abs health",
        "",
        "## Database connections",
        "",
        "| database | status | detail |",
        "|---|---|---|",
        f"| PostgreSQL | {'OK' if pg_ok else 'FAIL'} | {_cell(pg_detail)} |",
        f"| MongoDB | {'OK' if mongo_ok else 'FAIL'} | {_cell(mongo_detail)} |",
        "",
        "## Database",
        "",
    ]

    if pg_ok:
        try:
            from china_model import Deal, Mineru, QiniuStorage

            with_md = Mineru.select().where(Mineru.markdown.is_null(False)).count()
            lines += [
                f"- `deal`: **{Deal.select().count()}**",
                f"- `qiniu_storage`: **{QiniuStorage.select().count()}**",
                f"- `mineru`: **{Mineru.select().count()}** ({with_md} with markdown)",
            ]
        except Exception as exc:  # noqa: BLE001
            lines.append(f"> database query failed: {_cell(exc)}")
    else:
        lines.append("> skipped — PostgreSQL is not reachable")

    try:
        _, jobs_health = scheduler()
        report = jobs_health.run_check()
        lines += ["", "## Outstanding work", "", "| view | rows |", "|---|---:|"]
        for view, info in sorted(report.items(), key=lambda kv: -kv[1]["size"]):
            lines.append(f"| `{view}` | {info['size']} |")
    except Exception as exc:  # noqa: BLE001
        lines += ["", f"> scheduler health check failed: {_cell(exc)}"]

    lines += ["", "## Configuration", "", "| variable | state |", "|---|---|"]
    for var in _ENV_VARS:
        lines.append(f"| `{var}` | {'set' if os.getenv(var) else '—'} |")
    return "\n".join(lines)
