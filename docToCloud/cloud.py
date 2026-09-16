"""Qiniu object-storage helpers: upload local files and record them.

Extracted from ``flow/dags/datasource/cloud.py`` (``upload_single_file``,
``uploadToQiniu2`` and ``upload_current_docs``), with the same duplicate
protection:

* a file is skipped when its name is already a key in ``qiniu_storage``;
* a file is skipped when its local MD5 is already recorded for another object;
* after a successful upload the local copy is removed (unless ``keep`` is set)
  and a row is written to ``qiniu_storage``.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from qiniu import Auth, etag, put_file_v2

import db

load_dotenv()

log = logging.getLogger("cloud")

DEFAULT_BUCKET = "deal-docs"
DEFAULT_BUCKET_DOMAIN = "deal-doc.doclink.site"


def _get_auth() -> Auth:
    access_key = os.environ.get("QINIU_ACCESS_KEY", "")
    secret_key = os.environ.get("QINIU_SECRET_KEY", "")
    if not access_key or not secret_key:
        raise RuntimeError("QINIU_ACCESS_KEY and QINIU_SECRET_KEY must be set")
    return Auth(access_key, secret_key)


def bucket_name() -> str:
    return os.environ.get("QINIU_BUCKET", DEFAULT_BUCKET)


def bucket_domain() -> str:
    return os.environ.get("QINIU_BUCKET_DOMAIN", DEFAULT_BUCKET_DOMAIN)


def get_private_url(key: str, expires: int = 7200) -> str:
    """Return a time-limited download URL for ``key``."""
    auth = _get_auth()
    base_url = f"http://{bucket_domain()}/{key}"
    return auth.private_download_url(base_url, expires=expires)


def _remote_md5(key: str) -> str | None:
    """Fetch the stored MD5 of an object via Qiniu's ``qhash/md5`` API."""
    try:
        url = f"http://{bucket_domain()}/{key}?qhash/md5"
        signed = _get_auth().private_download_url(url, expires=7200)
        resp = requests.get(signed, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("hash")
        log.warning("qhash/md5 for %s failed: %s", key, resp.status_code)
    except Exception as exc:  # noqa: BLE001
        log.warning("qhash/md5 for %s failed: %s", key, exc)
    return None


def calc_md5(path: Path | str) -> str:
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def upload_file(
    local_path: str | Path,
    key: str | None = None,
    keep: bool = False,
    record: bool = True,
) -> str | None:
    """Upload one file to Qiniu.

    Args:
        local_path: path of the file to upload.
        key: object key; defaults to the file name.
        keep: keep the local file after a successful upload.
        record: write a row into ``qiniu_storage`` after upload.

    Returns:
        The object key on success, otherwise ``None``.
    """
    path = Path(local_path)
    if not path.is_file():
        log.warning("not a file: %s", path)
        return None

    key = key or path.name
    bucket = bucket_name()
    auth = _get_auth()
    token = auth.upload_token(bucket, key, 36000)

    ret, info = put_file_v2(token, key, str(path))
    if ret is None:
        log.error("upload failed for %s: %s", key, info)
        return None

    if ret.get("hash") != etag(str(path)):
        raise RuntimeError(f"etag mismatch for {path}: {ret.get('hash')} != {etag(str(path))}")

    if record:
        now = int(datetime.now().timestamp())
        db.record_doc(bucket, key, now, ret["hash"], _remote_md5(key))

    log.info("uploaded %s", key)
    if not keep and path.exists():
        path.unlink()
    return key


def upload_directory(
    folder: str | Path,
    pattern: str | None = None,
    keep: bool = False,
    workers: int = 1,
    check_dup: bool = True,
) -> list[str]:
    """Upload every file in ``folder`` that is not already in Qiniu.

    Args:
        folder: directory containing the files to upload.
        pattern: optional regex; only matching file names are considered.
        keep: keep local files after upload.
        workers: number of concurrent uploads.
        check_dup: skip files already present by key or MD5 hash.

    Returns:
        The list of object keys uploaded.
    """
    src = Path(folder)
    if not src.is_dir():
        log.error("folder does not exist: %s", src)
        return []

    files = [f for f in src.iterdir() if f.is_file()]
    if pattern is not None:
        files = [f for f in files if re.search(pattern, f.name)]

    if check_dup:
        keys, hashes = db.existing_docs()
        queue = [f for f in files if f.name not in keys and calc_md5(f) not in hashes]
        skipped = len(files) - len(queue)
        if skipped:
            log.info("skipped %d duplicate file(s)", skipped)
    else:
        queue = files

    log.info("uploading %d of %d file(s) from %s", len(queue), len(files), src)
    if not queue:
        return []

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(lambda f: upload_file(f, keep=keep), queue))
    return [k for k in results if k]
