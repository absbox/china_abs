from htpy import html, meta, title, link, script, head,body,div
from htpy import h1,h3,thead,tbody,tr,td,th
from htpy import input,table
from htpy import Node, Renderable,span, i
from htpy import class_, a,li,ui,ul,nav
from htpy import hr, button,p,article

import toolz as tz
from lenses import lens

from rich.console import Console
console = Console()

def dictListToTable(ms:list, cls={}, header=None, highlightIdx=None):
    ''' 
        ms -> [ {"A":1,"B":4} , {"A":2,"B":5} , {"A":3,"B":6} ]
        highlightIdx -> None | [1,2,3]
    '''
    if ms is None or len(ms)==0:
        if header is None:
            return table(cls)["Empty"]
        else:
            return tableWithHeader(header,{},cls)
    
    r = tz.merge_with(tz.identity,ms)
    
    if header is None:
        return dictToTable(r,cls)
    else:
        return tableWithHeader(header,r,cls,highlightIdx=highlightIdx)


def dictToTable(m:dict, cls={}, highlightIdx=None):
    ''' 
        key as column names 
        values are a list of rows 
        m -> {"A":[1,2,3],"B":[4,5,6]}
        highlightIdx -> None | [1,2,3]
    '''
    if m is None or len(m)==0:
        return table(cls)["None"]
    
    headers = list(m.keys())
    rows = list(zip(*m.values()))
    if len(set([len(_) for _ in m.values()]))!=1:
        for _ in m.values():
            print("len", len(_),_)
        raise RuntimeError("All columns must have same number of rows")
    
    
    
    table_head = thead[
        tr[*[th[h] for h in headers]]
    ]
    if highlightIdx :
        table_body = tbody[
            [ tr({"class":"is-selected"})[*[td[str(cell)] for cell in row]] if idx in highlightIdx else tr[*[td[str(cell)] for cell in row]]
                for idx, row in enumerate(rows)
            ]
        ]
    else:
        table_body = tbody[
            [ tr[*[td[str(cell)] for cell in row]] 
                for row in rows
            ]
        ]        
    return table(cls)[table_head, table_body]


def tableWithHeader(header:str, m:dict, cls, heading=h3 ,headerMapping=None,highlightIdx=None):
    ''' 
        key as column names 
        values are a list of rows
    '''
    if m is None or len(m)==0:
        return div[
            heading({"class":"title is-4"})[header],
            dictToTable({}, cls)
        ]
    
    if headerMapping:
        r = {}
        for k,v in headerMapping.items():
            r[v] = m[k]
        m = r
    return div[
        heading({"class":"title is-4"})[header],
        dictToTable(m, cls, highlightIdx=highlightIdx)
    ]

def listToTable(xs,header=True,cls={},highlightIdx=None):
    '''
        [[1,2,3],[4,5,6]]
    '''
    if not xs:
        return span[""]
    if header:
        table_head = thead[
            tr[*[th[h] for h in xs[0]]]
        ]
        xs = xs[1:]
    else:
        pass
        
    table_body = tbody[
        [ tr[*[td[str(cell)] for cell in row]] 
            for row in xs]
    ]
    if header:
        return table(cls)[table_head, table_body]
    else:
        return table(cls)[table_body]

def dictToTable_KeyAsRow(m:dict,keyColumnName="",cls={}):
    '''
    {
        "a":{"column":d,"column":c} ,
        "b":{"column":d,"column":c} ,
    }
    '''
    if not m:
        return "Empty Table"

    headers = [keyColumnName] + list(list(m.values())[0].keys())

    table_head = thead[
        tr[*[th[h] for h in headers]]
    ]

    rows = [ [k]+list(v.values()) for k,v in m.items() ]

    table_body = tbody[
        [ tr[*[td[str(cell)] for cell in row]]
            for row in rows]
    ]
    return table(cls)[table_head, table_body]

def dictToTable_KeyAsCol(m:dict,keyColumnName="",cls={}):
    '''
        {
        "a":{"b":1,"c":2} ,
        "d":{"b":3,"c":4} 
        }
    '''
    if not m:
        return "Empty Table"

    headers = [keyColumnName] + list(m.keys())

    table_head = thead[
        tr[*[th[h] for h in headers]]
    ]

    rows = [ [k,*v] for k,v in tz.merge_with(list,m.values()).items() ]

    table_body = tbody[
        [ tr[*[td[str(cell)] for cell in row]]
            for row in rows]
    ]
    return table(cls)[table_head, table_body]

def mkTabs(m, activeTab: str, tabFontSize=6):
    """
    m: dict of {tab_name: content}
    activeTab: the tab to show as active initially
    Uses Alpine.js for tab switching.
    """
    tab_names = list(m.keys())
    return div(".tabs-container", {
        "x-data": f"{{ tab: '{activeTab}' }}"
    })[
        div(".tabs.is-boxed")[
            ul[
                *[
                    li(
                        {":class": f"{{ 'is-active': tab === '{tab}' }}"}
                    )[
                        a(
                            {"@click": f"tab = '{tab}'", "href": "#"}
                        )[span(f".is-size-{tabFontSize}")[tab]]
                    ]
                    for tab in tab_names
                ]
            ]
        ],
        div[
            *[
                div(
                    { "x-show": f"tab === '{tab}'", "style": "display: none;" }
                )[m[tab]]
                for tab in tab_names
            ]
        ]
    ]


def buildPath(xs):
    if len(xs)==0:
        return \
            nav(".breadcrumb", {"aria-label": "breadcrumbs"})
    else:
        previous = xs[:-1]
        lastName,lastLink = xs[-1]
        return \
            nav(".breadcrumb", {"aria-label": "breadcrumbs"})[
                ul[ [li[a({"href": l})[n]] for (n,l) in previous ]+ [li(".is-active")[a({"href": lastLink, "aria-current": "page"})[lastName]]],
                ]
            ]

def buildDropdown(n, m):
    '''
        n -> dropdown name
        m -> {"cat":[],cat2:[]}
    '''
    #print(m)
    items = [ [hr(".dropdown-divider")
               , *[ (a(".dropdown-item", {"href": "#"})[_]) for _ in v ]
                ]
            for k,v in m.items()
            ]
    #print(items)
    return div(".dropdown")[
        div(".dropdown-trigger")[
            button(".button", {
                "aria-haspopup": "true",
                "aria-controls": "dropdown-menu3"
            })[
                span[n],
                span(".icon.is-small")[
                    i(".fas.fa-angle-down", {"aria-hidden": "true"})
                ]
            ]
        ],
        div(".dropdown-menu", {
            "id": "dropdown-menu3",
            "role": "menu"
        })[
            div(".dropdown-content")[*(list(tz.concat(items)))]
        ]
    ]

def warning(x: str):
    return article(".message.is-warning.is-small")[
        div(".message-header.is-small.px-2.py-1")[
            p["Warning"]
        ],
        div(".message-body.is-small.px-2.py-1")[
            x
        ]
    ]
    
def info(x: str):
    return article(".message.is-info.is-small")[
        div(".message-header.is-small.px-2.py-1")[
            p["Info"]
        ],
        div(".message-body.is-small.px-2.py-1")[
            x
        ]
    ]

def verTable(m):
    ''' 
    xs -> : {"rowA":1000,"rowB":200}
    '''
    #cols = [  for x in xs.values() ]

def genLink(t:str, xs):
    return a({"href":"/"+'/'.join(xs)})[t]

def iconText(icon,text):
    return span(".icon-text")[span(".icon")[i(f".fas.fa-{icon}")],span[text]]

def toWan(x):
    if x is None:
        return "/"
    else:
        return f"{float(x) / 10000:,.2f}"

def toInt(x):
    if x is None:
        return "/"
    else:
        return f"{int(x):,}"


def toPct(x,y):
    if y == 0 or x is None or y is None:
        return "/"
    return f"{(x / y) * 100:.3f}%"

def floatN(x):
    if x is None:
        return 0.0
    else:
        return float(x)
    
def breakdownAccount(xs:list,header=None,sumLoc="Top"):
    ''' 
    
    '''
    addUp = sum([floatN(row['balance']) for row in xs])
    
    return \
    table[
        thead[
            tr[
                th["科目"],
                th["余额"],
                th["备注"]
            ]
        ],
        tbody[
            *[
                tr[
                    td[row['name']],
                    td[toWan(row['balance'])],
                ]
                for row in xs
            ]
        ]
    ]
