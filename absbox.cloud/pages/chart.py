from pyecharts.charts import Bar
from pyecharts import options as opts
from bs4 import BeautifulSoup


bar = (
    Bar()
    .add_xaxis(["衬衫", "毛衣", "领带", "裤子", "风衣", "高跟鞋", "袜子"])
    .add_yaxis("商家A", [114, 55, 27, 101, 125, 27, 105])
    .add_yaxis("商家B", [57, 134, 137, 129, 145, 60, 49])
    .set_global_opts(title_opts=opts.TitleOpts(title="某商场销售情况"))
)


def buildBar() -> Bar:
    return bar

def render(x) -> str:
    r = x.render_embed()
    soup = BeautifulSoup(r, "html.parser")
    body_content = "".join(str(tag) for tag in soup.body.contents if tag.name or getattr(tag, 'strip', lambda: False)())
    return body_content