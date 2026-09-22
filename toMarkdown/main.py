import argparse
import logging
import sys

from cloud import download_file
from db import check_connection, get_outstanding_files
from mineru.convert import convert_key_list, convert_outstanding, convert_pdfs as mineru_pdfs
from paddle.convert import convert_pdfs as paddle_pdfs
from pdfinspect.convert import convert_pdfs as inspect_pdfs
from pipeline import process as run_pipeline


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
    """Convert PDFs in a folder to markdown with pdf-inspector."""
    rc = inspect_pdfs(args.folder)
    if rc != 0:
        sys.exit(rc)


def cmd_mineru(args):
    """Convert PDFs to markdown through the MinerU service."""
    if args.key:
        rc = convert_key_list(args.key, args.model)
    elif args.folder:
        rc = mineru_pdfs(args.folder, args.model)
    else:
        rc = convert_outstanding(args.model)
    if rc != 0:
        sys.exit(rc)


def cmd_paddle(args):
    """Convert PDFs to markdown through the PaddleOCR-VL service."""
    rc = paddle_pdfs(args.folder, args.workers, args.out)
    if rc != 0:
        sys.exit(rc)


def cmd_process(args):
    """Convert PDFs through the pdf-inspector -> paddle -> mineru pipeline."""
    rc = run_pipeline(args.names, args.model)
    if rc != 0:
        sys.exit(rc)


def main():
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(
        prog="tomarkdown",
        description="Download outstanding PDF files from Qiniu for markdown conversion.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List files needing markdown conversion")

    p_process = sub.add_parser(
        "process",
        help="Fallback pipeline: pdf-inspector -> paddle -> mineru",
    )
    p_process.add_argument(
        "names",
        nargs="*",
        help="Qiniu file name(s) (default: all outstanding)",
    )
    p_process.add_argument(
        "--model",
        default="vlm",
        choices=("pipeline", "vlm"),
        help="MinerU model version for the final stage (default: vlm)",
    )

    p_dl = sub.add_parser("download", help="Download a single file from Qiniu")
    p_dl.add_argument("key", help="Qiniu object key of the file to download")
    p_dl.add_argument("-d", "--dir", default=None, help="Target directory (default: docs/)")

    p_dla = sub.add_parser("download-all", help="Download all outstanding files")
    p_dla.add_argument("-d", "--dir", default=None, help="Target directory (default: docs/)")

    p_inspect = sub.add_parser("inspect", help="Convert PDFs with pdf-inspector")
    p_inspect.add_argument(
        "folder",
        nargs="?",
        default=None,
        help="Folder containing PDF files (default: docs/)",
    )

    p_mineru = sub.add_parser("mineru", help="Convert PDFs through the MinerU service")
    p_mineru.add_argument(
        "folder",
        nargs="?",
        default=None,
        help="Folder of PDFs to convert (default: all outstanding Qiniu files)",
    )
    p_mineru.add_argument(
        "-k",
        "--key",
        action="append",
        default=[],
        help="Qiniu key to convert (repeatable)",
    )
    p_mineru.add_argument(
        "--model",
        default="vlm",
        choices=("pipeline", "vlm"),
        help="MinerU model version (default: vlm)",
    )

    p_paddle = sub.add_parser("paddle", help="Convert PDFs through the PaddleOCR-VL service")
    p_paddle.add_argument(
        "folder",
        nargs="?",
        default=None,
        help="Folder containing PDF files (default: docs/)",
    )
    p_paddle.add_argument(
        "-w",
        "--workers",
        type=int,
        default=1,
        help="Number of concurrent jobs (default: 1)",
    )
    p_paddle.add_argument(
        "-o",
        "--out",
        default=None,
        help="Also write each markdown to <out>/<stem>.md",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Pre-flight: fail with a readable message instead of a mid-run traceback
    # when PostgreSQL is unreachable.
    try:
        check_connection()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.command == "list":
        cmd_list(args)
    elif args.command == "process":
        cmd_process(args)
    elif args.command == "download":
        cmd_download(args)
    elif args.command == "download-all":
        cmd_download_all(args)
    elif args.command == "inspect":
        cmd_inspect(args)
    elif args.command == "mineru":
        cmd_mineru(args)
    elif args.command == "paddle":
        cmd_paddle(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
