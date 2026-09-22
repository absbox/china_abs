"""PDF-to-markdown conversion through the MinerU batch service.

Local PDFs are addressed by their Qiniu key (the file name).  Each key is
signed into a time-limited URL and submitted to MinerU's batch endpoint, with
the callback server notified as results land.  ``convert_keys`` also polls the
batch endpoint and writes the returned ``full.md`` into the ``mineru`` table,
so the conversion works even when the callback server is offline.
"""

from __future__ import annotations

import io
import logging
import os
import time
import zipfile
from pathlib import Path

import requests

from cloud import get_private_url
from db import converted_keys, get_outstanding_files, save_markdown

log = logging.getLogger("mineru")

MODEL = "mineru"

BATCH_URL = "https://mineru.net/api/v4/extract/task/batch"
RESULT_URL = "https://mineru.net/api/v4/extract-results/batch"
VALID_MODELS = ("pipeline", "vlm")


def _token() -> str:
    token = os.getenv("MINERU_TOKEN", "")
    if not token:
        raise RuntimeError("MINERU_TOKEN must be set")
    return token


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_token()}",
    }


def _callback() -> str:
    return os.getenv("MINERU_CALLBACK", "http://101.132.150.211:5000/process-mineru")


def _batch_size() -> int:
    return int(os.getenv("MINERU_MAX_FILES_PER_BATCH", "50"))


def _submit_interval() -> int:
    return int(os.getenv("MINERU_SUBMIT_INTERVAL", "65"))


def _poll_interval() -> int:
    return int(os.getenv("MINERU_POLL_INTERVAL", "30"))


def _poll_timeout() -> int:
    return int(os.getenv("MINERU_POLL_TIMEOUT", "3600"))


def _chunked(xs: list, n: int):
    for i in range(0, len(xs), n):
        yield xs[i : i + n]


def callback_active() -> bool:
    """Whether the MinerU callback server is reachable."""
    url = os.getenv("MINERU_CALLBACK_CHECK", "http://101.132.150.211:5000/index")
    try:
        return requests.get(url, timeout=30).text.strip() == "yes"
    except Exception:
        return False


def submit_batch(keys: list[str], model_version: str = "vlm") -> str:
    """Submit one batch of Qiniu keys to MinerU and return its batch id."""
    if model_version not in VALID_MODELS:
        raise ValueError(f"model_version must be one of {VALID_MODELS}")
    files = [
        {"url": get_private_url(k), "data_id": str(i), "is_ocr": True}
        for i, k in enumerate(keys)
    ]
    data = {
        "enable_formula": True,
        "language": "ch",
        "enable_table": True,
        "files": files,
        "model_version": model_version,
        "callback": _callback(),
        "seed": "tomarkdown",
    }
    resp = requests.post(BATCH_URL, headers=_headers(), json=data, timeout=60)
    resp.raise_for_status()
    result = resp.json()
    if result.get("code") != 0:
        raise RuntimeError(f"submit failed: {result.get('msg')}")
    batch_id = result["data"]["batch_id"]
    log.info("submitted %d file(s), batch_id=%s", len(keys), batch_id)
    return batch_id


def get_batch_results(batch_id: str) -> list[dict]:
    """Return the current ``extract_result`` entries for a batch."""
    resp = requests.get(f"{RESULT_URL}/{batch_id}", headers=_headers(), timeout=60)
    resp.raise_for_status()
    return resp.json()["data"]["extract_result"]


def download_markdown(zip_url: str) -> str | None:
    """Download a MinerU result archive and extract its ``full.md``."""
    resp = requests.get(zip_url, timeout=300)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = [n for n in zf.namelist() if n.endswith("full.md")]
        if not names:
            return None
        return zf.read(names[0]).decode("utf-8")


def save_batch_results(batch_id: str, timeout: int | None = None) -> int:
    """Poll a batch and upsert each finished markdown. Returns the count saved."""
    timeout = timeout or _poll_timeout()
    deadline = time.monotonic() + timeout
    handled: set[str] = set()
    saved = 0
    while True:
        results = get_batch_results(batch_id)
        for r in results:
            key = r.get("file_name")
            state = r.get("state")
            if not key or key in handled:
                continue
            if state == "done":
                zip_url = r.get("full_zip_url")
                if not zip_url:
                    log.warning("no archive url for: %s", key)
                    handled.add(key)
                    continue
                markdown = download_markdown(zip_url)
                if markdown:
                    save_markdown(key, markdown, MODEL)
                    saved += 1
                    log.info("converted: %s", key)
                else:
                    log.warning("no full.md in archive: %s", key)
                handled.add(key)
            elif state == "failed":
                log.error("failed: %s - %s", key, r.get("err_msg", ""))
                handled.add(key)
        if results and all(r.get("state") in ("done", "failed") for r in results):
            break
        if time.monotonic() >= deadline:
            log.warning("timed out waiting for batch %s", batch_id)
            break
        time.sleep(_poll_interval())
    return saved


def convert_keys(
    keys: list[str],
    model_version: str = "vlm",
    poll: bool = True,
    check: bool = True,
) -> list[str]:
    """Convert a list of Qiniu keys, skipping those already converted."""
    unique = list(dict.fromkeys(keys))
    converted = converted_keys()
    outstanding = [k for k in unique if k not in converted]
    if not outstanding:
        log.info("no outstanding keys to convert")
        return []
    log.info(
        "%d key(s) to convert (%d already done)",
        len(outstanding),
        len(unique) - len(outstanding),
    )
    if check:
        if callback_active():
            log.info("callback server is active")
        else:
            log.warning("callback server unreachable; results will be polled")

    batches = list(_chunked(outstanding, _batch_size()))
    batch_ids: list[str] = []
    for i, batch in enumerate(batches):
        try:
            batch_ids.append(submit_batch(batch, model_version))
        except Exception as exc:
            log.error("submit batch %d/%d failed: %s", i + 1, len(batches), exc)
        if i < len(batches) - 1:
            log.info("waiting %ss before next submission", _submit_interval())
            time.sleep(_submit_interval())

    if poll:
        for batch_id in batch_ids:
            save_batch_results(batch_id)
    return batch_ids


def convert_key_list(keys: list[str], model_version: str = "vlm") -> int:
    """Convert an explicit list of Qiniu keys. Returns ``0``/``1``."""
    try:
        convert_keys(keys, model_version)
    except Exception as exc:
        log.error("mineru conversion failed: %s", exc)
        return 1
    return 0


def convert_outstanding(model_version: str = "vlm") -> int:
    """Convert every Qiniu file that has no markdown yet, without downloading."""
    keys = get_outstanding_files()
    if not keys:
        log.info("no outstanding files found")
        return 0
    log.info("found %d outstanding file(s)", len(keys))
    return convert_key_list(keys, model_version)


def convert_pdfs(folder: str | None = None, model_version: str = "vlm") -> int:
    """Convert the PDFs in a folder through MinerU and save them to ``mineru``.

    Args:
        folder: directory containing the PDF files.  Defaults to ``docs``
            inside the project folder.
        model_version: MinerU model, either ``pipeline`` or ``vlm``.

    Returns:
        ``0`` on success, ``1`` if the batch could not be processed.
    """
    if folder is None:
        folder = str(Path(__file__).parents[1] / "docs")
    docs_dir = Path(folder)
    if not docs_dir.is_dir():
        log.error("folder does not exist: %s", docs_dir)
        return 1

    pdfs = sorted(docs_dir.glob("*.pdf"))
    if not pdfs:
        log.info("no PDF files found in %s", docs_dir)
        return 0

    return convert_key_list([p.name for p in pdfs], model_version)
