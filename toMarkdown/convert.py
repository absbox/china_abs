import logging
from pathlib import Path

import pdf_inspector

from db import save_markdown

log = logging.getLogger("convert")

MODEL = "inspector"


def convert_pdfs(folder: str | None = None) -> int:
    """Convert PDF files in a folder to markdown and save them to ``mineru``.

    Args:
        folder: directory containing the PDF files.  Defaults to ``docs``
            inside the project folder.

    Returns:
        ``0`` on success (or when there is nothing to do), ``1`` if any file
        failed to convert.
    """
    if folder is None:
        folder = str(Path(__file__).parent / "docs")
    docs_dir = Path(folder)
    if not docs_dir.is_dir():
        log.error("folder does not exist: %s", docs_dir)
        return 1

    pdfs = sorted(docs_dir.glob("*.pdf"))
    if not pdfs:
        log.info("no PDF files found in %s", docs_dir)
        return 0

    converted = 0
    skipped = 0
    failed = 0

    for pdf_path in pdfs:
        try:
            data = pdf_path.read_bytes()
            result = pdf_inspector.process_pdf_bytes(data)
            markdown = result.markdown
            if not markdown:
                log.warning(
                    "no markdown produced: %s (pdf_type=%s)",
                    pdf_path.name,
                    result.pdf_type,
                )
                skipped += 1
                continue
            save_markdown(pdf_path.name, markdown, MODEL)
            converted += 1
            log.info(
                "converted: %s (pdf_type=%s, pages=%d)",
                pdf_path.name,
                result.pdf_type,
                result.page_count,
            )
        except Exception as exc:
            failed += 1
            log.error("failed: %s — %s", pdf_path.name, exc)

    log.info("done: converted=%d skipped=%d failed=%d", converted, skipped, failed)
    return 0 if failed == 0 else 1
