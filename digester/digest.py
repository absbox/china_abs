"""Batch-digest a list of markdown reports with a single question.

Entry point used by the repo ``justfile``.  Run from the ``digester`` project::

    uv run python digest.py --question PRICING_ANN report1.pdf report2.pdf
    uv run python digest.py --question PRICING_ANN ./local.md

Each name is either a path to a local markdown file (read from disk) or a key
in the ``mineru`` table (markdown fetched from Postgres).  The extracted
pydantic model is printed as JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.llm import understand, understand_report


def digest_one(name: str, question: str, provider: str, model: str | None):
    path = Path(name)
    if path.is_file():
        return understand(provider, question, path.read_text(encoding="utf-8"), model=model)
    return understand_report(name, provider=provider, question=question, model=model)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="digest",
        description="Run a single extraction question over a list of markdown reports.",
    )
    parser.add_argument("--question", required=True, help="question key (e.g. PRICING_ANN)")
    parser.add_argument("--provider", default="qwen", help="LLM provider (default: qwen)")
    parser.add_argument("--model", default=None, help="model name override")
    parser.add_argument("names", nargs="+", help="mineru keys or local markdown paths")
    args = parser.parse_args()

    failures = 0
    for name in args.names:
        try:
            result = digest_one(name, args.question, args.provider, args.model)
            print(
                json.dumps(
                    {"_id": name, args.question: result.model_dump()},
                    ensure_ascii=False,
                    default=str,
                )
            )
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"failed {name!r}: {exc}", file=sys.stderr)

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
