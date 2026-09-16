"""docToCloud CLI.

Scan chinabond.com.cn for ABS/MBS disclosure documents, work out which of them
are still missing from Qiniu, download the missing ones to a local folder and
upload them to Qiniu.

Commands::

    list     list scanned documents (optionally only the outstanding ones)
    fetch    download outstanding documents to a local folder
    upload   upload files from a local folder to Qiniu
    sync     fetch + upload (the default end-to-end flow)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import chinabond
import cloud
import db

log = logging.getLogger("doctocloud")

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_DIR = str(PROJECT_DIR / "docs")


def _add_scan_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--keyword", default="", help="full-text keyword filter")
    parser.add_argument("--start", default="", help="start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="", help="end date (YYYY-MM-DD)")
    parser.add_argument(
        "--channel",
        action="append",
        dest="channels",
        default=None,
        help="chinabond channel, repeatable (default: zjzczq_ABS zjzczq_MBS)",
    )
    parser.add_argument(
        "--doc-type",
        action="append",
        dest="doc_types",
        default=None,
        help="document type, repeatable (default: all known types)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="stop after N pages per channel/type (default: unlimited)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="concurrent downloads/uploads (default: 1)",
    )
    parser.add_argument(
        "--dir",
        default=DEFAULT_DIR,
        help=f"local folder for downloads (default: {DEFAULT_DIR})",
    )


def _collect(args: argparse.Namespace) -> list[chinabond.DocEntry]:
    return chinabond.scan(
        channels=args.channels,
        doc_types=args.doc_types,
        keyword=args.keyword,
        start_date=args.start,
        end_date=args.end,
        max_pages=args.max_pages,
    )


def _outstanding(entries: list[chinabond.DocEntry]) -> list[chinabond.DocEntry]:
    return chinabond.outstanding_entries(entries, db.existing_doc_keys())


def cmd_list(args: argparse.Namespace) -> int:
    entries = _collect(args)
    print(f"Scanned {len(entries)} document(s).")
    if not args.outstanding:
        for entry in entries:
            print(f"  {entry.channel}\t{entry.doc_type}\t{entry.key}")
        return 0

    missing = _outstanding(entries)
    print(f"Outstanding (missing from Qiniu): {len(missing)}")
    for entry in missing:
        print(f"  {entry.channel}\t{entry.doc_type}\t{entry.key}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    entries = _collect(args)
    if not args.all:
        entries = _outstanding(entries)
    print(f"Downloading {len(entries)} document(s) to {args.dir} ...")
    paths = chinabond.download_entries(
        entries, args.dir, workers=args.workers, overwrite=args.overwrite
    )
    print(f"Downloaded {len(paths)} file(s).")
    return 0


def cmd_upload(args: argparse.Namespace) -> int:
    keys = cloud.upload_directory(
        args.dir,
        keep=not args.delete_local,
        workers=args.workers,
    )
    print(f"Uploaded {len(keys)} file(s) from {args.dir}.")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    entries = _collect(args)
    missing = _outstanding(entries)
    print(f"Scanned {len(entries)} document(s); {len(missing)} outstanding.")

    if not missing:
        return 0

    paths = chinabond.download_entries(
        missing, args.dir, workers=args.workers, overwrite=args.overwrite
    )
    print(f"Downloaded {len(paths)} file(s) to {args.dir}.")

    keys = cloud.upload_directory(
        args.dir,
        keep=not args.delete_local,
        workers=args.workers,
    )
    print(f"Uploaded {len(keys)} file(s) to Qiniu.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doctocloud",
        description="Scan chinabond.com.cn and sync missing ABS/MBS documents to Qiniu.",
    )
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="list scanned / outstanding documents")
    _add_scan_args(p_list)
    p_list.add_argument(
        "--outstanding",
        action="store_true",
        help="only list documents missing from Qiniu",
    )
    p_list.set_defaults(func=cmd_list)

    p_fetch = sub.add_parser("fetch", help="download documents to a local folder")
    _add_scan_args(p_fetch)
    p_fetch.add_argument(
        "--all",
        action="store_true",
        help="download every scanned document, not only outstanding ones",
    )
    p_fetch.add_argument(
        "--overwrite",
        action="store_true",
        help="re-download files that already exist locally",
    )
    p_fetch.set_defaults(func=cmd_fetch)

    p_upload = sub.add_parser("upload", help="upload a local folder to Qiniu")
    p_upload.add_argument("--dir", default=DEFAULT_DIR, help="folder to upload")
    p_upload.add_argument(
        "--workers", type=int, default=1, help="concurrent uploads (default: 1)"
    )
    p_upload.add_argument(
        "--delete-local",
        action="store_true",
        help="delete local files after a successful upload",
    )
    p_upload.set_defaults(func=cmd_upload)

    p_sync = sub.add_parser("sync", help="fetch outstanding documents then upload")
    _add_scan_args(p_sync)
    p_sync.add_argument(
        "--overwrite",
        action="store_true",
        help="re-download files that already exist locally",
    )
    p_sync.add_argument(
        "--delete-local",
        action="store_true",
        help="delete local files after a successful upload",
    )
    p_sync.set_defaults(func=cmd_sync)

    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        sys.exit(1)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
