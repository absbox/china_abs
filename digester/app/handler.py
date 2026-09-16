import os
from datetime import datetime, timezone
from typing import Optional

import pymongo
from dotenv import load_dotenv

from .enums import DatabaseName, ReportType
from .extracter import route_function
from .llm import understand_report

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")


def _require_enum(value, enum_type, name: str) -> None:
    if not isinstance(value, enum_type):
        raise TypeError(
            f"{name} must be a {enum_type.__name__}, got {type(value).__name__}: {value!r}"
        )


def ensure_database(database: DatabaseName) -> None:
    """Create ``database`` and both report collections if they don't exist."""
    _require_enum(database, DatabaseName, "database")
    client = pymongo.MongoClient(MONGODB_URI)
    try:
        db = client[database.value]
        existing = set(db.list_collection_names())
        for report_type in ReportType:
            if report_type.value not in existing:
                db.create_collection(report_type.value)
    finally:
        client.close()


def save_report(
    report_name: str,
    database: DatabaseName = DatabaseName.raw,
    report_type: ReportType = ReportType.pricing,
    question: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """Extract a report via the LLM and store the result in MongoDB.

    The report name is the top-level key of the document (``_id``) in the
    collection; the LLM response is stored under the question key used, along
    with the save timestamp:

    .. code-block:: json

        {
          "_id": "<report_name>",
          "<question_string>": { <LLM response> },
          "timestamp": "<saved at>"
        }

    The target database and collection are given as enums
    (:class:`app.enums.DatabaseName`, :class:`app.enums.ReportType`) and
    created on demand.

    Args:
        report_name: report key used as the document ``_id`` (e.g. the
            ``mineru`` key, with or without the ``.pdf`` extension).
        database: target database, a :class:`app.enums.DatabaseName`; defaults
            to :attr:`app.enums.DatabaseName.raw`.
        report_type: report category, a :class:`app.enums.ReportType`, whose
            value names the collection; defaults to
            :attr:`app.enums.ReportType.pricing`.
        question: optional question key (a key of ``QUESTION_MODELS``).  When
            given it is used directly; otherwise it is inferred from the report
            name via :func:`app.extracter.route_function`.
        model: optional model name override forwarded to ``understand_report``.

    Returns:
        The document written to MongoDB.

    Raises:
        ValueError: if neither an explicit ``question`` nor a matching route
            is available for ``report_name``.
        TypeError: if ``database`` or ``report_type`` is not the expected enum.
    """
    _require_enum(database, DatabaseName, "database")
    _require_enum(report_type, ReportType, "report_type")

    question_key = question or route_function(report_name)
    if question_key is None:
        raise ValueError(f"No question route matched report {report_name!r}")

    response = understand_report(report_name, question=question_key, model=model)

    now = datetime.now(timezone.utc)
    doc = {
        "_id": report_name,
        question_key: response.model_dump(),
        "timestamp": now,
    }

    client = pymongo.MongoClient(MONGODB_URI)
    try:
        db = client[database.value]
        if report_type.value not in db.list_collection_names():
            db.create_collection(report_type.value)
        db[report_type.value].update_one(
            {"_id": report_name},
            {"$set": {question_key: response.model_dump(), "timestamp": now}},
            upsert=True,
        )
    finally:
        client.close()

    return doc