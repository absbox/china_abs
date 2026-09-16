"""Load functions from the sibling subprojects.

``docToCloud`` and ``toMarkdown`` are flat-module projects (both define a
top-level ``db`` and ``cloud``), so they cannot simply be put on ``sys.path``
together.  Each is loaded under a private module name with its internal ``db``
dependency injected for the duration of the import.  ``scheduler`` is a
package and is imported normally once its directory is on ``sys.path``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path, deps: dict[str, ModuleType] | None = None) -> ModuleType:
    """Import a file under ``name``, injecting any ``deps`` it imports."""
    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module

    injected: list[str] = []
    for dep_name, dep_module in (deps or {}).items():
        if dep_name not in sys.modules:
            sys.modules[dep_name] = dep_module
            injected.append(dep_name)

    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    finally:
        for dep_name in injected:
            sys.modules.pop(dep_name, None)
    return module


_doc_to_cloud = None
_to_markdown = None


def doc_to_cloud():
    """Return ``(chinabond, cloud, db)`` from the docToCloud project."""
    global _doc_to_cloud
    if _doc_to_cloud is None:
        base = ROOT / "docToCloud"
        db = _load("dashboard_dtc_db", base / "db.py")
        cloud = _load("dashboard_dtc_cloud", base / "cloud.py", {"db": db})
        chinabond = _load("dashboard_dtc_chinabond", base / "chinabond.py")
        _doc_to_cloud = (chinabond, cloud, db)
    return _doc_to_cloud


def to_markdown():
    """Return ``(convert, db, cloud)`` from the toMarkdown project."""
    global _to_markdown
    if _to_markdown is None:
        base = ROOT / "toMarkdown"
        db = _load("dashboard_tmd_db", base / "db.py")
        convert = _load("dashboard_tmd_convert", base / "convert.py", {"db": db})
        cloud = _load("dashboard_tmd_cloud", base / "cloud.py")
        _to_markdown = (convert, db, cloud)
    return _to_markdown


def scheduler():
    """Return ``(jobs.digest, jobs.health)`` from the scheduler project."""
    path = str(ROOT / "scheduler")
    if path not in sys.path:
        sys.path.insert(0, path)
    import jobs.digest as digest
    import jobs.health as health

    return digest, health
