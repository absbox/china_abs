"""Local PDF-to-markdown conversion with ``pdf-inspector``.

``convert_file`` converts one PDF, ``convert_files`` converts a list of paths
and saves each success into the shared ``mineru`` table with
``model='inspector'`` as it happens, and ``convert_pdfs`` wires them together
for a folder.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pdf_inspector

from db import converted_keys, save_markdown

log = logging.getLogger("pdfinspect")

MODEL = "inspector"


def convert_file(path: str) -> str | None:
    """Convert a single PDF to markdown, or ``None`` when nothing was produced."""
    pdf_path = Path(path)
    result = pdf_inspector.process_pdf_bytes(pdf_path.read_bytes())
    markdown = result.markdown
    if not markdown:
        log.warning(
            "no markdown produced: %s (pdf_type=%s)",
            pdf_path.name,
            result.pdf_type,
        )
        return None
    log.info(
        "converted: %s (pdf_type=%s, pages=%d)",
        pdf_path.name,
        result.pdf_type,
        result.page_count,
    )
    return markdown


def convert_files(paths: list[str]) -> dict[str, str]:
    """Convert many PDFs, saving each success to ``mineru`` as it happens.

    Returns ``{key: markdown}`` for the files that converted successfully.
    Failures are logged and omitted.
    """
    results: dict[str, str] = {}
    for path in paths:
        try:
            markdown = convert_file(path)
        except Exception as exc:
            log.error("failed: %s - %s", path, exc)
            continue
        if not markdown:
            continue
        key = Path(path).name
        save_markdown(key, markdown, MODEL)
        results[key] = markdown
    return results


def convert_pdfs(folder: str | None = None) -> int:
    """Convert the outstanding PDFs in a folder and save them to ``mineru``.

    Args:
        folder: directory containing the PDF files.  Defaults to ``docs``
            inside the project folder.

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

    results = convert_files([str(p) for p in outstanding])
    return 0 if len(results) == len(outstanding) else 1
