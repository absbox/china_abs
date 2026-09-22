"""Dashboard CLI.

Thin command-line layer over :mod:`api`: the dashboard reports on the health
of the china-abs project and renders the result as Markdown.

Usage::

    python main.py --help
    python main.py health
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
        description="Status / health checks for the china-abs project; renders markdown.",
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("health", help="health-check the whole china-abs project")
    p.set_defaults(func=lambda a: api.health())

    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
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
