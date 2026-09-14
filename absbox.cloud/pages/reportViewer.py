from htpy import html, meta, title, link, script, head,body,div
from htpy import h1,h3
from htpy import input
from htpy import Node, Renderable
from datetime import datetime

from htpy import p, ul, li, a, h4, span
from .basePage import base_layout


def rptPage(bondTable) -> Renderable :
    return base_layout(
        page_title="Absbox Cloud",
        content=div(class_="container")[
            h1(class_="title is-1")["Welcome to Absbox Cloud"]
            ,h3(class_="subtitle is-3")["信贷ABS数据浏览器"]
            ,bondTable
            
        ]
    )