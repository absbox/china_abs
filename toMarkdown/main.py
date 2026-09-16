import argparse
import logging
import sys

from convert import convert_pdfs
from db import get_outstanding_files
from cloud import download_file


def cmd_list(args):
    """List files that exist in qiniu but have no markdown yet."""
    files = get_outstanding_files()
    if not files:
        print("No outstanding files found.")
        return
    print(f"Found {len(files)} outstanding file(s):\n")
    for f in files:
        print(f)
    return files


def cmd_download(args):
    """Download a single file from Qiniu."""
    result = download_file(args.key, target_dir=args.dir)
    if result is None:
        print(f"Failed to download: {args.key}", file=sys.stderr)
        sys.exit(1)
    print(f"Downloaded: {result}")


def cmd_download_all(args):
    """Download all outstanding files from Qiniu."""
    files = get_outstanding_files()
    if not files:
        print("No outstanding files to download.")
        return
    print(f"Downloading {len(files)} file(s)...\n")
    ok, fail = 0, 0
    for key in files:
        result = download_file(key, target_dir=args.dir)
        if result:
            ok += 1
            print(f"  [ok]   {key}")
        else:
            fail += 1
            print(f"  [fail] {key}", file=sys.stderr)
    print(f"\nDone. {ok} downloaded, {fail} failed.")


def cmd_inspect(args):
    """Convert PDFs in a folder to markdown and store them in mineru."""
    rc = convert_pdfs(args.folder)
    if rc != 0:
        sys.exit(rc)


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(
        prog="tomarkdown",
        description="Download outstanding PDF files from Qiniu for markdown conversion.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List files needing markdown conversion")

    p_dl = sub.add_parser("download", help="Download a single file from Qiniu")
    p_dl.add_argument("key", help="Qiniu object key of the file to download")
    p_dl.add_argument("-d", "--dir", default=None, help="Target directory (default: docs/)")

    p_dla = sub.add_parser("download-all", help="Download all outstanding files")
    p_dla.add_argument("-d", "--dir", default=None, help="Target directory (default: docs/)")

    p_inspect = sub.add_parser("inspect", help="Convert PDFs in a folder to markdown")
    p_inspect.add_argument(
        "folder",
        nargs="?",
        default=None,
        help="Folder containing PDF files (default: docs/)",
    )

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "download":
        cmd_download(args)
    elif args.command == "download-all":
        cmd_download_all(args)
    elif args.command == "inspect":
        cmd_inspect(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
