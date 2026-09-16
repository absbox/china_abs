from htpy import html, meta, title, link, script, head,body,div
from htpy import h1,h3,nav,i,button
from htpy import Node, Renderable,Element, input,form
from datetime import datetime

from htpy import p, ul, li, a, h4, span,h2,hr, style
from markupsafe import Markup
from htmlUtil import genLink
from pages.themes import theme_style, theme_fonts_href, active_theme

assetPath = {
    "CDN":[
            link({"rel": "stylesheet", "href": "https://cdn.bootcdn.net/ajax/libs/bulma/1.0.4/css/bulma.min.css"}),
            #link({"rel": "stylesheet", "href": "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"}),
            link({"rel": "stylesheet", "href": "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/7.0.1/css/all.min.css"}),
            script({"src": "https://cdn.bootcdn.net/ajax/libs/htmx/2.0.7/htmx.min.js"}),
            script({"src": "https://cdn.bootcdn.net/ajax/libs/alpinejs/3.15.0/cdn.min.js","defer":True}),
            #script({"src": "https://cdn.jsdelivr.net/npm/chart.js"})
            script({"src": "https://cdn.jsdelivr.net/npm/echarts@6.0.0/dist/echarts.min.js"})
    ],
    "LOCAL":[
            link({"rel": "stylesheet", "href": "/static/bulma.min.css"}),
            link({"rel": "stylesheet", "href": "/static/all.min.css"}),
            link({"rel": "stylesheet", "href": "/static/bulma-tooltip.min.css"}),
            link({"rel": "stylesheet", "href": "/static/local.css"}),
            link({"rel": "stylesheet", "href": "/static/fa.css"}),
            #link({"rel": "stylesheet", "href": "/static/bulma.toggle.min.css"}),
            
            #script({"src":"/static/tailwind.min.js"}),
            script({"src": "/static/htmx.min.js"}),
            #script({"src": "/static/focus.min.js"}),
            #script({"src": "/static/collapse.min.js"}),
            script({"src": "/static/cdn.min.js","defer":True}),
            #script({"src": "/static/chart.js"}),
            script({"src": "/static/local.js"}),
            script({"src": "/static/bd.js"}),
            script({"src": "/static/echarts.min.js"})
    ]
}

def theme_navbar() -> Element:
    return nav(
        ".navbar",
        role="navigation",
    )[
        div(".navbar-menu")[
            div(".navbar-end")[
                div(".navbar-item")[
                    button(
                        ".button.is-outlined.is-small",
                        **{":title": "theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'","@click":"toggleTheme"},
                    )[
                        span(".icon")[
                            i(**{":class": "iconClass"})
                        ]
                    ]
                ]
            ]
        ]
    ]


def _theme_head(theme: dict) -> list[Node]:
    out: list[Node] = []
    href = theme_fonts_href(theme)
    if href:
        out.append(link({"rel": "stylesheet", "href": href}))
    out.append(style[Markup(theme_style(theme))])
    return out


def base_layout(*,
    page_title: str | None = None,
    extra_head: Node = None,
    content: Node = None,
    body_class: str | None = None,
) -> Renderable:
    _theme = active_theme()
    return html({"x-data":"themeSwitcher()",":class":"{ 'dark-mode': theme === 'dark' }"})[
        head[
            title[page_title],
            # theme_navbar(),
            *_theme_head(_theme),
            *assetPath["LOCAL"],
            extra_head,
        ],
        body(class_=f"{body_class or ''} theme-{_theme['id']}")[
            div[
                content,
                div(style="height:2em;"),  # Extra blank space above footer
                div(
                    id="footer",
                    class_="has-text-centered is-size-7",
                    style="margin-top:2em;"
                )[ span()[f"Copyright all reserved 2024,2025 ,{datetime.today().year} by absbox.com.cn ."
                    # ,genLink("🔒API",["api"])
                    ]
                ],
            ]
        ],
    ]


def searchBox():
    return \
    div[
        form({
            "hx-post": "/quick-search",
            "hx-headers": '{"Content-Type": "application/json"}',
            "hx-target": "#content",
            "hx-swap": "innerHTML",
        })[
            div(".field.has-addons")[
                div(".control")[
                    input({"type":"text","class":"input is-link is-small","placeholder":"债券代码/债券简称/产品ID/产品简称/ISIN","name":"searchKey"})
                ],
                div(".control")[
                    button(".button.is-link.is-small",type="submit")[
                        span(".icon.is-small")[
                            i(".fas.fa-search")
                        ]
                    ]
                ]
            ]
        ]
    ]


def base_page(*x) -> Renderable :
    return base_layout(
        page_title="Absbox Cloud",
        content=div(class_="container")[
            div(".navbar.is-light.mb-4")[
                div(".navbar-brand")[
                    a({ "class": "navbar-item", "href": "/preClosing" })["<待成立>"],
                    a({ "class": "navbar-item", "href": "/series" })["<系列一览>"],
                    a({ "class": "navbar-item", "href": "/bondScreen" })["<债券筛选>"],
                    a({ "class": "navbar-item", "href": "/reader" })["<文档速读>"],
                    # a({ "class": "navbar-item", "href": "#" })["<🔒信息流>"],
                    div(".navbar-item")[searchBox()]
                ]
            ],
            div("#content")[*x]
        ]
    )


