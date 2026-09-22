"""Local PDF-to-markdown conversion with the PaddleOCR-VL service.

The service is job based: a PDF (local path or URL) is submitted, polled until
``done``, then its JSONL result is fetched and the per-page markdown joined
into a single document.  The functions here are small and composable so callers
can submit, poll, and persist independently::

    sources = [str(p) for p in Path("docs").glob("*.pdf")]
    results = convert_files(sources)      # converts and saves each success
    write_markdowns(results, "out")       # optional local .md files
"""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from db import converted_keys, save_markdown

log = logging.getLogger("paddle")

MODEL = "paddle"

DEFAULT_JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
DEFAULT_MODEL_NAME = "PaddleOCR-VL-1.6"

OPTIONAL_PAYLOAD = {
    "useDocOrientationClassify": False,
    "useDocUnwarping": False,
    "useChartRecognition": False,
}


class PaddleError(RuntimeError):
    """Raised when the PaddleOCR service rejects or fails a job."""


def _token() -> str:
    token = os.getenv("PADDLE_TOKEN", "")
    if not token:
        raise PaddleError("PADDLE_TOKEN must be set")
    return token


def _job_url() -> str:
    return os.getenv("PADDLE_JOB_URL", DEFAULT_JOB_URL).rstrip("/")


def _model_name() -> str:
    return os.getenv("PADDLE_MODEL", DEFAULT_MODEL_NAME)


def _headers() -> dict:
    return {"Authorization": f"bearer {_token()}"}


def _poll_interval() -> int:
    return int(os.getenv("PADDLE_POLL_INTERVAL", "5"))


def _poll_timeout() -> int:
    return int(os.getenv("PADDLE_POLL_TIMEOUT", "1800"))


def submit_job(source: str) -> str:
    """Submit a local PDF path or remote URL and return the job id."""
    url = _job_url()
    headers = _headers()
    if source.startswith("http"):
        headers["Content-Type"] = "application/json"
        payload = {
            "fileUrl": source,
            "model": _model_name(),
            "optionalPayload": OPTIONAL_PAYLOAD,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
    else:
        path = Path(source)
        if not path.is_file():
            raise PaddleError(f"file not found: {path}")
        data = {
            "model": _model_name(),
            "optionalPayload": json.dumps(OPTIONAL_PAYLOAD),
        }
        with path.open("rb") as fh:
            resp = requests.post(
                url, headers=headers, data=data, files={"file": fh}, timeout=300
            )
    if resp.status_code != 200:
        raise PaddleError(f"submit failed ({resp.status_code}): {resp.text}")
    return resp.json()["data"]["jobId"]


def poll_job(job_id: str, timeout: int | None = None, interval: int | None = None) -> str:
    """Wait for a job to finish and return its result JSONL URL."""
    timeout = timeout or _poll_timeout()
    interval = interval or _poll_interval()
    deadline = time.monotonic() + timeout
    url = f"{_job_url()}/{job_id}"
    while True:
        resp = requests.get(url, headers=_headers(), timeout=60)
        if resp.status_code != 200:
            raise PaddleError(
                f"job {job_id} poll failed ({resp.status_code}): {resp.text}"
            )
        data = resp.json()["data"]
        state = data.get("state")
        if state == "done":
            return data["resultUrl"]["jsonUrl"]
        if state == "failed":
            raise PaddleError(f"job {job_id} failed: {data.get('errorMsg', '')}")
        if time.monotonic() >= deadline:
            raise PaddleError(f"job {job_id} timed out after {timeout}s")
        log.info("job %s: %s", job_id, state)
        time.sleep(interval)


def fetch_markdown(jsonl_url: str) -> str:
    """Download a result JSONL and join its pages into one markdown string."""
    resp = requests.get(jsonl_url, timeout=300)
    resp.raise_for_status()
    parts: list[str] = []
    for line in resp.text.splitlines():
        line = line.strip()
        if not line:
            continue
        result = json.loads(line)["result"]
        for page in result.get("layoutParsingResults", []):
            text = page.get("markdown", {}).get("text", "")
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def convert_pdf(source: str) -> str:
    """Convert a single local PDF or URL to markdown."""
    log.info("processing: %s", Path(source).name or source)
    job_id = submit_job(source)
    log.info("submitted %s -> job %s", source, job_id)
    return fetch_markdown(poll_job(job_id))


def convert_files(sources: list[str], workers: int = 1) -> dict[str, str]:
    """Convert many PDFs, saving each success to ``mineru`` as it happens.

    Returns ``{key: markdown}`` for the files that converted successfully.
    Failures are logged and omitted.  ``workers > 1`` runs jobs concurrently;
    results are still persisted one at a time on the calling thread.
    """
    unique = list(dict.fromkeys(sources))

    def run(source: str) -> tuple[str, str | None]:
        try:
            return source, convert_pdf(source)
        except Exception as exc:
            log.error("failed: %s - %s", source, exc)
            return source, None

    results: dict[str, str] = {}
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run, source) for source in unique]
            for future in as_completed(futures):
                source, markdown = future.result()
                if markdown:
                    _store(source, markdown, results)
    else:
        for source in unique:
            _, markdown = run(source)
            if markdown:
                _store(source, markdown, results)
    return results


def _store(source: str, markdown: str, results: dict[str, str]) -> None:
    key = Path(source).name
    save_markdown(key, markdown, MODEL)
    log.info("saved: %s", key)
    results[key] = markdown


def write_markdowns(results: dict[str, str], out_dir: str) -> list[Path]:
    """Write ``{key: markdown}`` to ``<out_dir>/<stem>.md``."""
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for key, markdown in results.items():
        dest = target / f"{Path(key).stem}.md"
        dest.write_text(markdown, encoding="utf-8")
        written.append(dest)
    return written


def convert_pdfs(
    folder: str | None = None,
    workers: int = 1,
    out_dir: str | None = None,
) -> int:
    """Convert outstanding PDFs in a folder and save them to ``mineru``.

    Args:
        folder: directory containing the PDF files.  Defaults to ``docs``
            inside the project folder.
        workers: number of concurrent jobs.
        out_dir: when set, also write each markdown to ``<out_dir>/<stem>.md``.

    Returns:
        ``0`` when every outstanding PDF converted, ``1`` otherwise.
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

    converted = converted_keys()
    outstanding = [p for p in pdfs if p.name not in converted]
    if not outstanding:
        log.info("no outstanding PDFs to convert")
        return 0

    results = convert_files([str(p) for p in outstanding], workers)
    if out_dir:
        write_markdowns(results, out_dir)
    return 0 if len(results) == len(outstanding) else 1
