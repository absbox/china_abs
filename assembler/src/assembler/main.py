"""CLI for the assembler fill steps.

Commands::

    python -m assembler.main list                 list the fill steps
    python -m assembler.main run                  run every fill step (default)
    python -m assembler.main run to_fill_bond ... run selected steps
"""

from __future__ import annotations

import argparse
import logging
import sys

from .db import ensure_configured
from .fill import FILL_FUNCS, fill_deal_data_obj, resolve_step

log = logging.getLogger("assembler")


def _step_name(fn) -> str:
    name = fn.__name__
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not name[i - 1].isupper():
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def cmd_list(_args: argparse.Namespace) -> int:
    for fn in FILL_FUNCS:
        print(f"  {_step_name(fn):<28} ({fn.__name__})")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    ensure_configured()
    if not args.steps:
        fill_deal_data_obj()
        return 0

    funcs = []
    for name in args.steps:
        try:
            funcs.append(resolve_step(name))
        except KeyError as exc:
            log.error("%s", exc)
            return 2

    for fn in funcs:
        try:
            log.info("[fill] %s", fn.__name__)
            fn()
        except Exception as exc:  # noqa: BLE001
            log.error("[fill] %s error: %s", fn.__name__, exc)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assembler",
        description="Fill deal data from the os_fill_* reporting views.",
    )
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="list the fill steps")
    p_list.set_defaults(func=cmd_list)

    p_run = sub.add_parser("run", help="run every fill step, or the named ones")
    p_run.add_argument(
        "steps",
        nargs="*",
        help="optional step names (e.g. to_fill_bond fill_isin); default: all",
    )
    p_run.set_defaults(func=cmd_run)
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args()

    if not getattr(args, "command", None):
        cmd_run(argparse.Namespace(steps=[]))
        return
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
