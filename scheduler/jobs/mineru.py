"""MinerU submission pipeline.

Exact port of the MinerU parts of ``flow/dags/datasource/pdfconvert.py``:

* ``batch_parse_by_url``  -> enqueue a batch of signed document URLs on pgmq;
* ``process_mineru_queue``-> pop the queue and POST each batch to mineru.net;
* ``mineru_by_list``      -> dedupe against ``mineru`` and enqueue work.

The Qiniu signing helper is reused from :mod:`docToCloud`.
"""

from __future__ import annotations

import logging
import os
import threading
import time

import requests
from more_itertools import chunked

import pathsetup  # noqa: F401  (adds docToCloud to sys.path)
import cloud as dtc_cloud  # docToCloud Qiniu helper

from . import db

log = logging.getLogger("scheduler.mineru")

MINERU_BATCH_URL = "https://mineru.net/api/v4/extract/task/batch"
MINERU_MAX_FILES_PER_BATCH = int(os.getenv("MINERU_MAX_FILES_PER_BATCH", "50"))
MINERU_SUBMIT_INTERVAL = int(os.getenv("MINERU_SUBMIT_INTERVAL", "65"))

# Only one submitter should drain the queue at a time.
mineru_submit_lock = threading.Lock()

_queue = None


def _token() -> str:
    token = os.getenv("MINERU_TOKEN", "")
    if not token:
        raise RuntimeError("MINERU_TOKEN must be set")
    return token


def _callback() -> str:
    return os.getenv("MINERU_CALLBACK", "http://101.132.150.211:5000/process-mineru")


def _callback_check_url() -> str:
    return os.getenv("MINERU_CALLBACK_CHECK", "http://101.132.150.211:5000/index")


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_token()}",
    }


def get_queue():
    """Lazily build the pgmq queue client."""
    global _queue
    if _queue is None:
        from pgmq import PGMQueue

        host = os.getenv("PGMQ_HOST") or os.getenv("DATABASE_HOST") or "localhost"
        _queue = PGMQueue(
            host=host,
            port=int(os.getenv("PGMQ_PORT", os.getenv("DATABASE_PORT", "5432"))),
            username=os.getenv("DATABASE_USER", "doadmin"),
            password=os.getenv("DATABASE_PASSWORD", ""),
            database=os.getenv("DATABASE_NAME", "deal-library"),
        )
    return _queue


def get_private_url(key: str) -> str:
    """Signed Qiniu URL for ``key`` (reused from docToCloud)."""
    return dtc_cloud.get_private_url(key)


def batch_parse_by_url(xs, model_version: str = "vlm"):
    """Port of ``batchParseByURL``: enqueue one batch of signed URLs on pgmq."""
    if xs == []:
        return None
    assert len(xs) <= MINERU_MAX_FILES_PER_BATCH, f"max size is {MINERU_MAX_FILES_PER_BATCH}"
    valid_models = ["pipeline", "vlm"]
    assert model_version in valid_models, f"Model version must be in {valid_models}"

    upload_urls = [
        {"url": u, "data_id": str(idx), "is_ocr": True} for (idx, (u, _)) in enumerate(xs)
    ]

    data = {
        "enable_formula": True,
        "language": "ch",
        "enable_table": True,
        "files": upload_urls,
        "model_version": model_version,
        "callback": _callback(),
        "seed": "flask",
    }

    msg_ids = get_queue().send("mineru", data)
    log.info("[batchParseByURL] queued %s file(s): %s", len(upload_urls), msg_ids)
    return {"data": {"batch_id": msg_ids}}


def process_mineru_queue() -> None:
    """Port of ``processMineruQueue``: drain pgmq and submit to mineru.net."""
    q_name = "mineru"
    if not mineru_submit_lock.acquire(blocking=False):
        log.info("[ProcessQueue]: another mineru submitter is active, skip")
        return
    try:
        queue = get_queue()
        while (msg := queue.pop(q_name)):
            r = msg.message
            files = r.get("files", [])
            if len(files) > MINERU_MAX_FILES_PER_BATCH:
                log.info(
                    "[ProcessQueue]: splitting %s files into batches of %s",
                    len(files),
                    MINERU_MAX_FILES_PER_BATCH,
                )
                batches = list(chunked(files, MINERU_MAX_FILES_PER_BATCH))
            else:
                batches = [files]
            for b in batches:
                payload = {**r, "files": b}
                response = requests.post(MINERU_BATCH_URL, headers=_headers(), json=payload)
                if response.status_code == 200:
                    result = response.json()
                    if result.get("code") == 0:
                        log.info("[ProcessQueue]: submitted %s file(s)", len(b))
                    else:
                        log.error("submit task failed, reason: %s", result.get("msg"))
                else:
                    log.error(
                        "response not success. status:%s, result:%s",
                        response.status_code,
                        response.text,
                    )
                log.info("[ProcessQueue]: %s files << %s", len(b), str(payload)[:100])
                log.info("wait for %ss", MINERU_SUBMIT_INTERVAL)
                time.sleep(MINERU_SUBMIT_INTERVAL)
            queue.archive(q_name, msg.msg_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("Error processing queue %s: %s", q_name, exc)
    finally:
        mineru_submit_lock.release()


def _callback_server_active() -> bool:
    try:
        y = requests.get(_callback_check_url(), timeout=30)
        if y.text == "yes":
            log.info("callback server is active")
            return True
        log.warning("callback server is NOT active")
        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("callback server is off: %s", exc)
        return False


def mineru_by_list(_xs, check: bool = True, model: str = "vlm"):
    """Port of ``mineruByList``: enqueue a list of file names for conversion."""
    if check and (not _callback_server_active()):
        log.error("failed to check on callback server")
        return
    xs = list(set(_xs))
    pending = [x for x in xs if not db.has_markdown(x)]
    urls = [(get_private_url(file_name), file_name) for file_name in pending]
    log.info("[mineruByList]: %s url(s) via Qiniu", len(urls))
    for batch in chunked(urls, MINERU_MAX_FILES_PER_BATCH):
        resp = batch_parse_by_url(batch, model_version=model)
        log.info("[mineruByList]: %s", resp)
