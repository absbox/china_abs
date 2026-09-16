"""Scan and download ABS/MBS disclosure documents from chinabond.com.cn.

This is a dependency-light extraction of the scanning logic that used to live in
``flow/dags/datasource/chinabond.py`` and
``flow/dags/datasource/downloader.py``.

The site exposes a JSON search endpoint (``getContentByConditions``) that returns
one page of disclosure entries at a time.  Each entry points at a detail page
(``docPubUrl``).  The downloadable attachments are described either directly in
the ``appendixIds`` field (``id=serverName=displayName``) or, when that field is
empty, by links embedded in the detail page itself.

Typical use::

    entries = scan(["zjzczq_ABS"], ["发行文件"], start_date="2026-09-01")
    paths = download_entries(entries, "docs")
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("chinabond")

SEARCH_URL = "https://www.chinabond.com.cn/cbiw/trs/getContentByConditions"

DEFAULT_CHANNELS = ["zjzczq_ABS", "zjzczq_MBS"]

DEFAULT_DOC_TYPES = [
    "发行文件",
    "发行结果",
    "付息兑付与行权公告",
    "评级文件",
    "财务报告",
    "其他公告通知",
]

# Detail-page selector used to enumerate attachments when ``appendixIds`` is
# empty.  Kept in sync with the selector used by the legacy downloader.
_SUBPAGE_CSS = (
    "body > div.allDetailBox > div.allDetailFileBox > ul > li > div > span.rightFileImport > font > a"
)
_SUBPAGE_FALLBACK_CSS = "span.rightFileImport a, div.allDetailFileBox a"

_SEARCH_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json",
    "Origin": "https://www.chinabond.com.cn",
    "Referer": "https://www.chinabond.com.cn/xxpl/ywzc_fxyfxdh/fxyfxdh_zqzl/zqzl_zjzzczj/zjzczq_ABS",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
}

_DOWNLOAD_HEADERS = {
    "Origin": "https://www.chinabond.com.cn",
    "Content-Type": "application/pdf",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
}

# A handful of historical attachments are published under an opaque server name
# that is either not unique or not descriptive.  These are mapped to the
# human-readable name the rest of the pipeline expects.  Keyed on the raw
# (server-side) file name.
RENAMES = {
    "P020230716354318590503.pdf": "建鑫2016年第一期中诚信国际评级售前评级报告及跟踪评级安排.pdf",
    "P020230716354319899992.pdf": "建鑫2016年第一期中债资信售前评级报告及跟踪评级安排.pdf",
    "P020230716449704792640.pdf": "橙益2022年第一期联合资信售前评级报告及跟踪评级安排说明.pdf",
    "P020230716449705165126.pdf": "橙益2022年第一期中债资信售前评级报告及跟踪评级安排说明.pdf",
    "P020230716444848633370.pdf": "工元至诚2021年第六期不良资产支持证券信用评级报告（中诚信）.pdf",
    "P020230716464085283924.pdf": "邮盈惠兴2022年第四期不良资产-发行办法.pdf",
    "P020230716464085711423.pdf": "邮盈惠兴2022年第四期不良资产-发行说明书.pdf",
    "P020230716464086782073.pdf": "邮盈惠兴2022年第四期不良资产-联合资信评级报告.pdf",
    "P020230716464087199394.pdf": "邮盈惠兴2022年第四期中债资信评级报告.pdf",
}


@dataclass(frozen=True)
class DocEntry:
    """A single downloadable attachment discovered on chinabond.com.cn."""

    channel: str
    doc_type: str
    doc_pub_url: str
    raw_name: str
    file_name: str
    meta: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def key(self) -> str:
        """The object key this file is stored under in Qiniu."""
        return self.file_name

    @property
    def local_name(self) -> str:
        """The file name to use on disk (honouring :data:`RENAMES`)."""
        return RENAMES.get(self.raw_name, self.file_name)


def _post_json(payload: dict, referer: str) -> dict | None:
    headers = _SEARCH_HEADERS | {"Referer": referer}
    resp = requests.post(SEARCH_URL, json=payload, headers=headers, timeout=60)
    if resp.status_code != 200:
        log.error("search failed (%s): %s", resp.status_code, resp.text[:200])
        return None
    return resp.json()


def search_docs(
    channel: str,
    doc_type: str,
    keyword: str = "",
    start_date: str = "",
    end_date: str = "",
    page_size: int = 12,
    max_pages: int | None = None,
) -> list[dict]:
    """Return every raw entry for ``channel``/``doc_type`` matching the filters.

    Paginates until the API reports an empty page (or ``max_pages`` is hit).
    """
    referer = (
        "https://www.chinabond.com.cn/xxpl/ywzc_fxyfxdh/"
        f"fxyfxdh_zqzl/zqzl_zjzzczj/{channel}"
    )
    results: list[dict] = []
    page = 1
    while True:
        payload = {
            "parentChnlName": channel,
            "excludeParentChnlNames": [],
            "childChnlDesc": doc_type,
            "hasAppendix": True,
            "siteName": "chinaBond",
            "jrzqChnName": "",
            "pageSize": page_size,
            "pageNum": page,
            "queryParam": {
                "keywords": keyword,
                "startDate": start_date,
                "endDate": end_date,
                "reportType": "",
                "reportYear": "",
                "ratingAgency": "",
            },
        }
        data = _post_json(payload, referer)
        if data is None:
            break
        block = data.get("data") or {}
        items = block.get("list") or []
        size = block.get("size", 0)
        log.info(
            "[search] %s %s page %s -> %s item(s)",
            channel,
            doc_type,
            page,
            size,
        )
        results.extend(items)
        if not size:
            break
        page += 1
        if max_pages is not None and page > max_pages:
            break
    return results


def fetch_subpage_files(page_url: str) -> list[tuple[str, str]]:
    """Parse a detail page for attachments.

    Returns ``(raw_name, file_name)`` pairs, where ``raw_name`` is the relative
    href (used to build the download URL) and ``file_name`` is the display name.
    """
    resp = requests.get(page_url, headers=_SEARCH_HEADERS, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")
    nodes = soup.select(_SUBPAGE_CSS) or soup.select(_SUBPAGE_FALLBACK_CSS)

    files: list[tuple[str, str]] = []
    for node in nodes:
        href = (node.get("href") or "").strip()
        if not href:
            continue
        display = (node.get("download") or node.get_text() or "").strip()
        if not display:
            display = Path(href).name
        files.append((href.lstrip("./"), display))
    return files


def parse_entries(
    results: list[dict],
    channel: str,
    doc_type: str,
    expand_subpages: bool = True,
) -> list[DocEntry]:
    """Turn raw search results into :class:`DocEntry` objects."""
    entries: list[DocEntry] = []
    for item in results:
        doc_pub_url = item.get("docPubUrl") or ""
        appendix = item.get("appendixIds")
        if appendix:
            parts = appendix.split("=")
            if len(parts) >= 3:
                entries.append(
                    DocEntry(
                        channel=channel,
                        doc_type=doc_type,
                        doc_pub_url=doc_pub_url,
                        raw_name=parts[1],
                        file_name="=".join(parts[2:]),
                        meta=item,
                    )
                )
            else:
                log.warning("unexpected appendixIds %r for %s", appendix, doc_pub_url)
        elif expand_subpages and doc_pub_url:
            try:
                for raw_name, file_name in fetch_subpage_files(doc_pub_url):
                    entries.append(
                        DocEntry(
                            channel=channel,
                            doc_type=doc_type,
                            doc_pub_url=doc_pub_url,
                            raw_name=raw_name,
                            file_name=file_name,
                            meta=item,
                        )
                    )
            except Exception as exc:  # noqa: BLE001 - one bad page shouldn't stop the scan
                log.warning("failed to expand %s: %s", doc_pub_url, exc)
    return entries


def scan(
    channels: list[str] | None = None,
    doc_types: list[str] | None = None,
    keyword: str = "",
    start_date: str = "",
    end_date: str = "",
    max_pages: int | None = None,
    expand_subpages: bool = True,
) -> list[DocEntry]:
    """Scan chinabond.com.cn and return all matching, de-duplicated documents."""
    channels = channels or DEFAULT_CHANNELS
    doc_types = doc_types or DEFAULT_DOC_TYPES

    seen: set[tuple[str, str]] = set()
    entries: list[DocEntry] = []
    for channel in channels:
        for doc_type in doc_types:
            raw = search_docs(
                channel,
                doc_type,
                keyword=keyword,
                start_date=start_date,
                end_date=end_date,
                max_pages=max_pages,
            )
            for entry in parse_entries(
                raw, channel, doc_type, expand_subpages=expand_subpages
            ):
                dedup_key = (entry.doc_pub_url, entry.file_name)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                entries.append(entry)
    return entries


def outstanding_entries(
    entries: list[DocEntry], existing_keys: set[str]
) -> list[DocEntry]:
    """Filter ``entries`` down to files whose key is not already in the cloud."""
    return [e for e in entries if e.key not in existing_keys]


def update_download_link(page_url: str, raw_name: str) -> str:
    """Replace the last path segment of ``page_url`` with ``raw_name``."""
    return "/".join(page_url.split("/")[:-1]) + "/" + raw_name


def download_file(
    url: str,
    file_name: str,
    output_dir: str,
    overwrite: bool = False,
) -> str | None:
    """Stream a single file from ``url`` into ``output_dir``.

    Files that are already present locally are skipped unless ``overwrite`` is
    true.  Returns the local path when the file was newly downloaded, otherwise
    ``None``.
    """
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    dest = target / file_name
    if not overwrite and dest.exists() and dest.stat().st_size > 0:
        log.info("skipping %s (already downloaded)", file_name)
        return None
    try:
        with requests.get(
            url, stream=True, headers=_DOWNLOAD_HEADERS, timeout=120
        ) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
        log.info("downloaded %s", file_name)
        return str(dest)
    except Exception as exc:  # noqa: BLE001
        log.error("failed to download %s (%s): %s", file_name, url, exc)
        if dest.exists():
            dest.unlink()
        return None


def download_entries(
    entries: list[DocEntry],
    output_dir: str,
    workers: int = 1,
    overwrite: bool = False,
) -> list[str]:
    """Download every entry into ``output_dir`` and return the new local paths.

    Entries whose file already exists locally are skipped (and therefore not
    included in the returned list) unless ``overwrite`` is true.
    """
    if not entries:
        return []

    def _one(entry: DocEntry) -> str | None:
        url = update_download_link(entry.doc_pub_url, entry.raw_name)
        return download_file(url, entry.local_name, output_dir, overwrite=overwrite)

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_one, entries))
    else:
        results = [_one(e) for e in entries]

    return [r for r in results if r]
