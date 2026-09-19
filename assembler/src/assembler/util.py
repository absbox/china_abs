"""Shared helpers re-exported from the repository-root ``util.py``.

The fill steps only need the dependency-light helpers that are shared across the
monorepo; the canonical implementations live in the root ``util.py``, which is
loaded by path.
"""

from __future__ import annotations

import importlib.util as _importlib_util
import sys as _sys
from pathlib import Path as _Path

__all__ = [
    "tryToMatch",
    "tblListToMap",
    "isSenior",
    "shortNameToBondName",
    "mapKey",
    "subMap",
    "nToZ",
    "getValByKeySeq",
    "getValByPs",
    "findFirstByFn",
]


def _load_root_util():
    name = "china_abs_root_util"
    if name in _sys.modules:
        return _sys.modules[name]
    here = _Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "util.py"
        if candidate.is_file() and (parent / "pyproject.toml").is_file():
            spec = _importlib_util.spec_from_file_location(name, candidate)
            module = _importlib_util.module_from_spec(spec)
            _sys.modules[name] = module
            spec.loader.exec_module(module)
            return module
    raise ImportError(f"could not locate the repository-root util.py from {here}")


_shared = _load_root_util()

tryToMatch = _shared.tryToMatch
tblListToMap = _shared.tblListToMap
isSenior = _shared.isSenior
shortNameToBondName = _shared.shortNameToBondName
mapKey = _shared.mapKey
subMap = _shared.subMap
nToZ = _shared.nToZ
getValByKeySeq = _shared.getValByKeySeq
getValByPs = _shared.getValByPs
findFirstByFn = _shared.findFirstByFn
