import os
import sys
from typing import Optional

import psycopg
import pymongo
from dotenv import load_dotenv

from .enums import DatabaseName, ReportType
from .handler import save_report

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")


def get_os_pricing(num: int) -> list[tuple[str, str]]:
    """Return unprocessed pricing (簿记建档) reports from the ``mineru`` table.

    Queries ``public.mineru`` for keys containing ``簿记建档`` whose markdown
    is not null, then drops report names whose documents already exist in the
    ``raw.pricing`` collection (keyed by ``_id``), finally limiting to ``num``
    records ordered by key.

    Args:
        num: maximum number of records to return; ``0`` or negative returns
            an empty list.

    Returns:
        List of ``(key, markdown)`` tuples that are not yet in ``raw.pricing``.
    """
    if num <= 0:
        return []

    with psycopg.connect(
        host=os.getenv("DATABASE_HOST", "localhost"),
        port=int(os.getenv("DATABASE_PORT", "5432")),
        user=os.getenv("DATABASE_USER"),
        password=os.getenv("DATABASE_PASSWORD"),
        dbname=os.getenv("DATABASE_NAME", "deal-library"),
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT key, markdown FROM public.mineru "
                "WHERE key LIKE %s AND markdown IS NOT NULL "
                "ORDER BY key",
                ("%簿记建档%",),
            )
            rows = cur.fetchall()

    client = pymongo.MongoClient(MONGODB_URI)
    try:
        existing = {
            doc["_id"]
            for doc in client[DatabaseName.raw.value][
                ReportType.pricing.value
            ].find({}, {"_id": 1})
        }
    finally:
        client.close()

    fresh = [(key, markdown) for key, markdown in rows if key not in existing]
    return fresh[:num]


def back_fill_pricing(num: int = 5, model: Optional[str] = None) -> int:
    """Process the next batch of unprocessed pricing reports into ``raw.pricing``.

    Calls :func:`get_os_pricing` for up to ``num`` fresh 簿记建档 reports,
    extracts structured data with :func:`app.handler.save_report` (PRICING_ANN
    question) and persists each result to the ``raw.pricing`` collection.  A
    failing report is reported to stderr and the loop continues with the next
    one.

    Args:
        num: maximum number of reports to process in this batch; ``0`` or
            negative processes none.
        model: optional model name override forwarded to the LLM.

    Returns:
        The number of reports successfully saved.
    """
    inserted = 0
    for key, _ in get_os_pricing(num=num):
        try:
            save_report(
                key,
                DatabaseName.raw,
                ReportType.pricing,
                question="PRICING_ANN",
                model=model,
            )
            inserted += 1
        except Exception as exc:
            print(f"backfill failed for {key!r}: {exc}", file=sys.stderr)
    return inserted
