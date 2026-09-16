import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from qiniu import Auth

load_dotenv()


def _get_auth() -> Auth:
    access_key = os.environ.get("QINIU_ACCESS_KEY", "")
    secret_key = os.environ.get("QINIU_SECRET_KEY", "")
    if not access_key or not secret_key:
        raise RuntimeError("QINIU_ACCESS_KEY and QINIU_SECRET_KEY must be set")
    return Auth(access_key, secret_key)


def download_file(file_key: str, target_dir: str | None = None) -> str | None:
    """Download a file from Qiniu by its key.

    Args:
        file_key: the object key in the Qiniu bucket.
        target_dir: local directory to save the file.
            Defaults to ``docs`` inside the project folder.

    Returns:
        The full local path of the downloaded file, or ``None`` on failure.
    """
    try:
        if target_dir is None:
            target_dir = str(Path(__file__).parent / "docs")
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)

        filename = Path(file_key).name
        dest = target / filename
        if dest.exists():
            return str(dest)

        auth = _get_auth()
        bucket_domain = os.environ.get("QINIU_BUCKET_DOMAIN", "deal-doc.doclink.site")
        base_url = f"http://{bucket_domain}/{file_key}"
        url = auth.private_download_url(base_url, expires=7200)

        with requests.get(url, stream=True) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
        return str(dest)
    except Exception:
        return None
