"""Dashboard CLI.

Thin command-line layer over :mod:`api`: each subcommand calls one function
from a sibling subproject and renders its Markdown result.

Usage::

    python main.py --help
    python main.py health
    python main.py scan-download 2026-09-01
    python main.py deal-init 2026-09-16
    python main.py allocate 2026-09-16
    python main.py convert "农盈利信远弘2025年第二期不良资产支持证券发行说明书.pdf"
    python main.py convert-all
    python main.py digest PRICING_ANN "a.pdf" "b.pdf"
    python main.py call health
"""

from __future__ import annotations

import argparse
import logging
import sys

from rich.console import Console
from rich.markdown import Markdown

import api

console = Console()


def _render(markdown: str) -> None:
    console.print(Markdown(markdown or ""))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dashboard",
        description="Manage / health-check / call the china-abs project; renders markdown.",
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("scan-download", help="scan chinabond and download+upload new files")
    p.add_argument("begin", help="cutoff date YYYY-MM-DD")
    p.add_argument("end", nargs="?", default=None, help="end date (default today)")
    p.set_defaults(func=lambda a: api.scan_download(a.begin, a.end))

    p = sub.add_parser("scan-list", help="list scanned files still missing from Qiniu")
    p.add_argument("begin", help="cutoff date YYYY-MM-DD")
    p.add_argument("end", nargs="?", default=None)
    p.set_defaults(func=lambda a: api.scan_list(a.begin, a.end))

    p = sub.add_parser("deal-init", help="run deal init for new documents")
    p.add_argument("since", nargs="?", default=None, help="date YYYY-MM-DD (default today)")
    p.set_defaults(func=lambda a: api.deal_init(a.since))

    p = sub.add_parser("allocate", help="allocate new files to existing deals")
    p.add_argument("since", nargs="?", default=None, help="date YYYY-MM-DD (default today)")
    p.set_defaults(func=lambda a: api.allocate(a.since))

    p = sub.add_parser("convert", help="convert the given Qiniu key(s) to markdown")
    p.add_argument("names", nargs="+")
    p.set_defaults(func=lambda a: api.convert(a.names))

    p = sub.add_parser("convert-all", help="convert all outstanding PDFs to markdown")
    p.set_defaults(func=lambda a: api.convert_all())

    p = sub.add_parser("convert-list", help="list PDFs still missing markdown")
    p.set_defaults(func=lambda a: api.convert_list())

    p = sub.add_parser("digest", help="run one question over a list of reports")
    p.add_argument("question", help="question key, e.g. PRICING_ANN")
    p.add_argument("names", nargs="+", help="mineru keys or local markdown paths")
    p.add_argument("--provider", default="qwen")
    p.add_argument("--model", default=None)
    p.set_defaults(func=lambda a: api.digest(a.question, a.names, a.provider, a.model))

    p = sub.add_parser("health", help="health-check the whole china-abs project")
    p.set_defaults(func=lambda a: api.health())

    p = sub.add_parser("call", help="call a single dashboard function by name")
    p.add_argument("name", choices=sorted(api.REGISTRY))
    p.add_argument("args", nargs="*")
    p.set_defaults(
        func=lambda a: api.REGISTRY[a.name](*a.args) if a.args else api.REGISTRY[a.name]()
    )

    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        sys.exit(1)
    result = args.func(args)
    _render(result)


if __name__ == "__main__":
    main()
