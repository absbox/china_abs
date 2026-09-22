"""Fallback PDF-to-markdown pipeline.

A list of Qiniu file names flows through three engines like a queue.  Each
engine converts only the keys still without markdown and persists every
success to the ``mineru`` table as it happens, so whatever it could not convert
is handed to the next engine:

1. **pdf-inspector** locally (fast, no network service);
2. **paddle** for files pdf-inspector could not read (e.g. image-based PDFs),
   one at a time;
3. **mineru** for anything still outstanding.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from cloud import download_file
from db import converted_keys, get_outstanding_files
from mineru.convert import convert_key_list
from paddle.convert import convert_files as paddle_convert_files
from pdfinspect.convert import convert_files as inspect_convert_files

log = logging.getLogger("pipeline")


def _outstanding(names: list[str]) -> list[str]:
    converted = converted_keys()
    return [name for name in names if name not in converted]


def _stage(
    label: str,
    queue: list[str],
    local: dict[str, str],
    convert: Callable[[list[str]], dict[str, str]],
) -> list[str]:
    """Run one engine over the outstanding local files; return what is left."""
    paths = [local[name] for name in queue if name in local]
    log.info("%s on %d file(s)", label, len(paths))
    if paths:
        convert(paths)
    return _outstanding(queue)


def process(names: list[str] | None = None, model_version: str = "vlm") -> int:
    """Run the fallback pipeline over ``names`` (default: all outstanding).

    Returns ``0`` when every file ends up with markdown, ``1`` otherwise.
    """
    queue = _outstanding(list(dict.fromkeys(names or [])) or get_outstanding_files())
    if not queue:
        log.info("nothing outstanding to process")
        return 0
    log.info("%d file(s) to process", len(queue))

    local: dict[str, str] = {}
    for name in queue:
        path = download_file(name)
        if path:
            local[name] = path
        else:
            log.warning("could not download: %s", name)

    queue = _stage("stage 1/3: pdf-inspector", queue, local, inspect_convert_files)
    if not queue:
        log.info("done after pdf-inspector")
        return 0

    queue = _stage(
        "stage 2/3: paddle",
        queue,
        local,
        lambda paths: paddle_convert_files(paths, workers=1),
    )
    if not queue:
        log.info("done after paddle")
        return 0

    log.info("stage 3/3: mineru on %d file(s)", len(queue))
    convert_key_list(queue, model_version)

    remaining = _outstanding(queue)
    if remaining:
        log.error("%d file(s) still outstanding: %s", len(remaining), remaining)
        return 1
    log.info("pipeline complete")
    return 0
