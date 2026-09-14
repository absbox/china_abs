from htpy import html, meta, title, link, script, head,body,div
from htpy import h1,h2,h3,h4,h5,h6
from htpy import input
from htpy import Node, Renderable
from datetime import datetime
from markupsafe import Markup
from htmlUtil import dictToTable,tableWithHeader,dictToTable_KeyAsRow

from htpy import p, ul, li, a, h4, span
from .basePage import base_layout

from .chart import bar,render

from .style import modDataTable
from lenses import lens

def analyticPage(x:dict) -> Renderable :

    r = []

    r.append(
        h4(class_="subtitle is-4")[x['deal_fullname']]
    )

    r.append(
        h5(class_="subtitle is-5")["Bonds"]
    )


    bondNames = x['bond'].keys()
    #print("x -> ", x)
    assert isinstance(x['bond'],dict), f"bond should be a map:but got {x['bond']}"

    r.append([tableWithHeader(k, v & lens.Values().modify(lambda x:[x])
                              ,{"class":modDataTable})
            for k,v in x['bond'].items()]
    )

    r.append(
        div[h5(class_="subtitle is-5")["Pools"]
        , *[ dictToTable(x['recoveryCalc'], cls={"class":modDataTable})  ]
        ]
    )

    r.append(
        div[h5(class_="subtitle is-5")["Capital Structure"]
        , *[ 
            [h6(class_="subtitle is-6")[k]
               ,dictToTable_KeyAsRow(v,keyColumnName="Indicators", cls={"class":modDataTable})
            ] 
            for k,v in x['oc'].items()
           ]
        ]
    )
    
    #print()
    r.append(div[Markup(render(bar))])

    return base_layout(
        page_title="Absbox Cloud",
        content=div(class_="container")[
            h1(class_="title is-1")["Welcome to Absbox Cloud"]
            ,h3(class_="subtitle is-3")["信贷ABS-产品分析"]
            ,r
        ]
    )
