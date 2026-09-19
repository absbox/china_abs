"""Shared helper functions for the china-abs monorepo.

These helpers used to be duplicated across the per-project ``util.py`` files
(``absbox.cloud/util.py``, ``flow/dags/datasource/util.py`` and
``assembler/src/assembler/util.py``).  The canonical implementations live here;
each project's ``util.py`` loads this file by path and re-exports the names it
needs, so existing imports keep working.

This is a repository-root module rather than an installed package, so it is
loaded via :func:`importlib.util.spec_from_file_location` (see the shims) and
not with a plain ``import util``.  Heavy optional dependencies (``bs4``,
``rich``, ``more-itertools``) are imported lazily inside the functions that
need them.
"""

from __future__ import annotations

import re

import toolz as tz
from lenses import lens

__all__ = [
    "tryToMatch",
    "tryToMatchBut",
    "tblListToMap",
    "tblToMap",
    "listOfMapToMap",
    "list2DictBy",
    "convert_list_to_map",
    "liftToDict",
    "subMap",
    "mapKey",
    "bondNameMapping",
    "printableTbl",
    "printTbl",
    "readHtmlTblToList",
    "isSenior",
    "shortNameToBondName",
    "nToZ",
    "getValByKeySeq",
    "getValByPs",
    "findFirstByFn",
]


def tryToMatch(y: str, xs, capture: bool = True):
    for x in xs:
        if (r := re.search(x, y)):
            if capture:
                return r.groups()[0]
            return True
    return None


def tryToMatchBut(y: str, xs, but, capture: bool = True):
    for x in xs:
        if (r := re.search(x, y)) and (not (any([re.search(b, y) for b in but]))):
            if capture:
                return r.groups()[0]
            return True
    return None


def tblListToMap(lst):
    """
    [['A','B'],[1,2],[3,4]]
    -> [ {"A":1,"B":2},{"A":3,"B":4}]
    """
    assert len(lst) > 1, "at least two row"

    header, *rs = lst
    return [dict(zip(header, x)) for x in rs]


def tblToMap(tbl):
    """
    tbl: -> [[Col1,Val1,Val2],[Col2,Val3,Val4]]
    keyColumn -> Col1
    return : {Val1:{Col2:Val3},Val2:{Col2:Val4}}
    """
    from more_itertools import transpose

    ks, *rs = transpose(tbl)
    vs = [dict(zip(ks, r)) for r in rs]
    return vs


def listOfMapToMap(lst, k, remove=True):
    if not remove:
        return {item[k]: item for item in lst}
    return {item[k]: {_k: _v for (_k, _v) in item.items() if _k != k} for item in lst}


def list2DictBy(lst, keyField):
    """
    [ {'A':1,'B':2},{'A':3,'B':4} ]
    => {1: {'A':1,'B':2}, 3:{'A':3,'B':4}}
    """
    assert all([keyField in item for item in lst]), f"key field {keyField} not in all items {[ item for item in lst if keyField not in item]}"
    return {item[keyField]: item for item in lst}


def convert_list_to_map(lst, k, v):
    return {item[k]: item[v] for item in lst}


def liftToDict(lst, keyField):
    return [{keyField: item} for item in lst]


def subMap(m, ks=[], default=None):
    if default is not None:
        return {k: m.get(k, default) for k in ks}
    return {k: m[k] for k in ks}


def mapKey(km, m):
    r = {}
    for k, v in m.items():
        if k in km:
            r[km[k]] = v
        else:
            r[k] = v
    return r


def bondNameMapping(x):
    match x:
        case "次级档资产支持证券":
            return "C"

        case _:
            return None


def printableTbl(lst, title=""):
    """
    lst: list of dict
    """
    from rich.table import Table

    if len(lst) == 0:
        return Table(title=title)
    headers = lst[0].keys()

    table = Table(title=title)

    for h in headers:
        table.add_column(h, justify="left", style="cyan", no_wrap=True)

    for item in lst:
        vs = map(str, item.values())
        table.add_row(*vs)

    return table


def printTbl(lst, title=""):
    from rich.console import Console

    Console().print(printableTbl(lst, title=title))


def readHtmlTblToList(html_string: str):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_string, 'html.parser')
    vals = [[__.get_text() for __ in _.select("td")] for _ in soup.css.select("tr")]
    vals &= lens.Each().Each().modify(lambda y: y.replace(" ", "").replace("\n", ""))
    return vals


def isSenior(x):
    if "A" in x:
        return True
    if "优" in x:
        return True
    if "次" in x:
        return False
    if "C" in x:
        return False


def shortNameToBondName(x: str):
    return tz.pipe(
        x,
        lambda x: re.sub(r"bc|BC|\(bc\)|\(bc", "", x),  # remove the `bc`
        lambda x: re.match(r"\d{2}\S+?\d{1,2}(.*)|华驭\d{4}(.*)", x),  # get 优先A from 25XX1优先A, "华驭2014优先A"
        lambda x: (x.group(1) or x.group(2)),
    )


def nToZ(x):
    if x is None:
        return 0
    return x


def getValByKeySeq(m, ks):
    for k in ks:
        if k in m:
            return m[k]
    return None


def getValByPs(m, ps):
    for p in ps:
        if (r := tz.get_in(p, m)):
            return r
    return None


def findFirstByFn(xs, fn):
    for x in xs:
        if fn(x):
            return x
    return None
