from dateutil.relativedelta import relativedelta
import decimal, os
from datetime import timedelta, datetime, date
from collections import OrderedDict
from lenses import lens
from typing import Union
from pydantic import BaseModel
import toolz as tz
from functools import reduce
from functools import lru_cache

from htpy import render_html, section, option, select
from htpy import div, span, li, ol, ul, h4, h5, h2, h3, h1, h6, p, a, pre, hr, form, dl
from htpy import input, template, button
from htpy import html, label, em, script,article
from markupsafe import Markup
import json, re
from itertools import dropwhile
from util import (
    subMap,
    listOfMapToMap,
    getFirstKeyInMap,
    get_month_diff,
    dropFieldInListOfMap,
)
from profiling_decorator import profile
from line_profiler import LineProfiler

lp = LineProfiler()

from htmlUtil import (
    dictToTable,
    tableWithHeader,
    dictToTable_KeyAsRow,
    dictListToTable,
    genLink,
)
from htmlUtil import (
    iconText,
    mkTabs,
    buildPath,
    buildDropdown,
    warning,
    info,
    listToTable,
    toWan,
    floatN,
    toPct,
)
from htmlUtil import dictToTable_KeyAsCol, breakdownAccount

from pages.basePage import base_page

# --------------------------------------------------------------------------
#  Select which theme to render. Change this string to switch the whole site.
#      "neo_brutalism_lite_brown"  -> Neo-Brutalism Lite (Brown)
#      "default"                   -> Default Bulma (Light)
# --------------------------------------------------------------------------
from pages.themes import set_theme
set_theme("neo_brutalism_lite_brown")

from pages.reportViewer import rptPage
from pages.analtyicViewr import analyticPage
from pages.chart import render
from calcSpread import calcProjectRfRate, calcSpreadFn, adjustRates, calcBondSpreads
from analytics import calcWAL

from webApi import *
from parser_base import dm, FeeType
from pages.style import modDataTable
from model import Bond, BondID, Deal, getEquityTranches, Stage, Location
from model import TradingPrice, BondPayments, PricingReport, Roles, Institution,PreClosingBond
from model import (
    RatingReport,
    ClearReport,
    TrusteeReport,
    IssueFiles,
    BookingAnn,
    IssuePlan,
    BondSeniorityType,
    HealthCheck,
)
from model import db
from rich.console import Console

from data import deal_status
from util import findFirstInMap, tryToMatch

# from dateutil.relativedelta import relativedelta
from const import (
    statusMap,
    assetClassMap,
    prinTypeMap,
    rateTypeMap,
    transMap,
    subAssetClassMap,
    bondFieldMap,
    remapMapKey,
    ratingView,
    ratingList,
)
from const import (
    statusMapClass,
    dealFieldMap,
    agencyShortName,
    toRate,
    displayBondField,
    mergeSubdicts,
)
from const import toBalance, dateDiff, dealClearField, toSpread
from const import poolPerfMapNpl, displayNplPoolPerfField
import numpy as np
from db import hasMarkdown, getMuMd, getMdFilesByKey, getFilesByKey, db_pool, q_with_m

from peewee import prefetch, JOIN
from playhouse.shortcuts import model_to_dict
import mistune
from pyxirr import xirr
from itertools import chain


from fastapi.staticfiles import StaticFiles
from fastapi import Form
from fastapi import Query
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse


from flask import Flask
from pyecharts.charts import Line
from pyecharts import options as opts
from fastapi import Request
from urllib.parse import parse_qs

# app = Flask(__name__)


tranAc = transMap(assetClassMap)
transSubAc = transMap(subAssetClassMap)


console = Console()

app = FastAPI()
# app.add_middleware(PyInstrumentProfilerMiddleware)
app.mount("/static", StaticFiles(directory="pages/static"), name="static")

productionFlag = True if os.path.exists("prd.flag") else False


transBnd = remapMapKey(bondFieldMap)
transRatingView = remapMapKey(ratingView)


# @profile(output='log',sort_by="time",n_rows=20)
def relatedBonds(deal: Deal, m: int, n: int):
    """
    m -> last M months' same series
    n -> last N months' same pool Type (NPL -subPoolType )
    """

    # You can use relativedelta from dateutil for easier month arithmetic
    def add_months(dt: datetime, months: int) -> datetime:
        return dt + relativedelta(months=months)

    cDate = parse(tz.get_in(["issuePlan","closingDate"],deal.data)).date() 
    
    if deal.poolType == "NPL":
        sameSeries = (
            Bond.select(Bond, Deal)
            .join(Deal)
            .where(
                Deal.poolSubType == deal.poolSubType,
                Deal.seriesName == deal.seriesName,
                Deal.closingDate >= add_months(cDate, -m),
                Deal.closingDate <= cDate,
                Deal.dealid != deal.dealid,
                Bond.seniority != BondSeniorityType.get_by_id("junior"),
            )
            .order_by(Deal.closingDate.desc())
        )
        sameType = (
            Bond.select(Bond, Deal)
            .join(Deal)
            .where(
                Deal.poolSubType == deal.poolSubType,
                Deal.closingDate >= add_months(cDate, -n),
                Deal.closingDate <= cDate,
                Deal.dealid != deal.dealid,
                Deal.seriesName != deal.seriesName,
                Bond.seniority != BondSeniorityType.get_by_id("junior"),
            )
            .order_by(Deal.closingDate.desc())
        )
    else:
        sameSeries = (
            Bond.select(Bond, Deal)
            .join(Deal)
            .where(
                Deal.seriesName == deal.seriesName,
                Deal.closingDate >= add_months(cDate, -m),
                Deal.closingDate <= cDate,
                Deal.dealid != deal.dealid,
                Bond.seniority != BondSeniorityType.get_by_id("junior"),
            )
            .order_by(Deal.closingDate.desc())
        )
        sameType = (
            Bond.select(Bond, Deal)
            .join(Deal)
            .where(
                Deal.poolType == deal.poolType,
                Deal.closingDate >= add_months(cDate, -n),
                Deal.closingDate <= cDate,
                Deal.dealid != deal.dealid,
                Deal.seriesName != deal.seriesName,  # exclude all in sameSeries
                Bond.seniority != BondSeniorityType.get_by_id("junior"),
            )
            .order_by(Deal.closingDate.desc())
        )
    return (list(sameSeries.dicts()), list(sameType.dicts()))


def ratingReportNPL(deal: Deal):
    """
    ratingRpts -> a list of map of rating data
    """

    poolData = tz.get_in(["preClosing", "pool"], deal.data, default={})
    recoveryEst = tz.get_in(["ExpectRecovery"], poolData, default=None)
    classify = tz.get_in(["classify"], poolData, default=None)
    totalPoolBalance = tz.get_in(["totalBalance"], poolData, default=None)
    totalPrinBalance = tz.get_in(["totalPrincipalBalance"], poolData, default=None)
    cutoffDate = tz.get_in(
        ["dates", "cutoffdate"], deal.data["preClosing"], default="/"
    )

    return div[
        p[
            hr,
            h6(".title.is-6")["资产池统计"],
            div["起算日期: ", cutoffDate],
            div["本息费余额:", toWan(totalPoolBalance)],
            div["本金余额:", toWan(totalPrinBalance)],
        ],
        p[
            hr,
            h6(".title.is-6")["资产池回收预测"],
            [
                ul[
                    f"{agencyShortName.get(k,'/')}: {toWan(v)}  (回收率: {toPct(v,totalPoolBalance)})"
                ]
                for k, v in recoveryEst.items()
            ],
        ],
        p[
            hr,
            h6(".title.is-6")["资产池五级分类"],
            classify and [ul[f"{k}: {toRate(v)}"] for k, v in classify.items()],
        ],
    ]

def ratingReportAuto(deal: Deal):
    '''
        rating data for auto deal
    '''
    poolData = tz.get_in(["preClosing", "pool"], deal.data, default={})
    #recoveryEst = tz.get_in(["ExpectRecovery"], poolData, default=None)
    #classify = tz.get_in(["classify"], poolData, default=None)
    totalPoolBalance = tz.get_in(["totalBalance"], poolData, default=None)
    #totalPrinBalance = tz.get_in(["totalPrincipalBalance"], poolData, default=None)
    cutoffDate = tz.get_in(
        ["dates", "cutoffdate"], deal.data["preClosing"], default="/"
    )

    return div[
        p[
            hr,
            h6(".title.is-6")["资产池统计"],
            div["起算日期: ", cutoffDate],
            div["本息费余额:", toWan(totalPoolBalance)],
            div["平均余额: ", toWan(tz.get_in(["AvgBalance"], poolData, default=None))],
            div["平均利率: ", toRate(tz.get_in(["AvgCoupon"], poolData, default=None))],
        ],
    ]


def calculateDealStatus(deal):
    '''
        deal object in a dictionary form
        return a tuple -> ("<data to show>","<data tooltip>")
    '''
    """
        only applicable for preClosingDeal
        1、时间安排
        （1）2025年6月12日，公告《盈风2025年第一期个人汽车抵押贷款绿色资
        产支持证券发行说明书》等发行文件；
        （2）2025年6月18日，公告《盈风2025年第一期个人汽车抵押贷款绿色资
        产支持证券申购和配售办法说明》；
        （3）2025年6月19日，北京时间09:30至18:00，簿记管理人接收申购订单并
        进行簿记（根据发行情况，经发行人及簿记管理人同意，申购及簿记时间可以
        延长）；发行人与主承销商根据簿记结果讨论决定本期资产支持证券的票面利
        率，根据有效订单进行配售；2025年6月20日至2025年6月23日，与获得配售的
        投资者签署《盈风2025年第一期个人汽车抵押贷款绿色资产支持证券分销协
        议》（以下简称“《分销协议》”）或向该等投资者发送缴款通知书，约定双方
        的权利义务，明确获得配售的投资者的获配证券金额及缴款时间；
        （4）2025年6月23日，获得配售的投资者缴款；当日北京时间下午16:00前
        投资者向主承销商指定账户缴款；
        （5）2025年6月23日，北京时间17:00前，发行人和簿记管理人将簿记配售
        结果提交中央结算公司；2025年6月23日北京时间17:00前，发行人将募集资金
        到账情况通知中央结算公司，中央结算公司据此办理资产支持证券确权登记。
    """
    if deal["data"] is None:
        return ("TBD", "无 data")
    # print(deal)
    #assert "preClosing" in deal["data"], f"Deal {deal['dealid']} has no preClosing data"
    if 'issuePlan' not in deal["data"]:
        return ("TBD", "无 data")    
    bookdate = deal["data"]["issuePlan"].get("bookDate", None)
    
    closingdate = parse(deal["data"]["issuePlan"]["closingDate"]).date()


    if 'pricing' in deal["data"]:
        return ("已设立", "已有债券上市公告")

    '''
        if f := anyKeyInList((r"应急申购书",), rawFiles):
            return ("应急申购", f)

        if f := anyKeyInList((r"申购要约",), rawFiles):
            return ("已要约", f)

        if f := anyKeyInList((r"推迟发行的?公告",), rawFiles):
            return ("推迟发行", f)
    '''
    
    return ("已公告", "已公告")


def getBondPricing(deal: Deal):
    pricingReports = list(deal.pricingReport)

    def useful(xs):
        if len(xs) == 0:
            console.print(f"{deal.dealid}: no pricing report")
            return None
        if len(xs) == 1:
            return xs[0]
        if re.match(r".*的更正公告", xs[0].loc.key):
            return useful(xs[1:])

    return useful(pricingReports)


def yearFraction(d1, d2) -> float:
    if isinstance(d1, str) and isinstance(d2, str):
        return round((parse(d2) - parse(d1)).days / 365, 2)
    return round((d2 - d1).days / 365, 2)


def getSeniorBond(xs):
    seniorKeys = ["优"]
    return [x for x in xs if tryToMatch(x["债券名称"], seniorKeys, capture=False)]


def getDealDates(deal: Deal):
    '''
        get estimated dates in preClosing stage
    '''
    if "preClosing" not in deal.data:
        return None
    
    cutoffDate = tz.get_in(
        ["dates", "cutoffdate"], deal.data["preClosing"], default="/"
    )

    annDate = deal.data["issuePlan"].get("annDate", None)
    bookingDate = deal.data["issuePlan"].get("bookDate", None)
    closingDate = deal.data["issuePlan"].get("closingDate", None)
    statedDate = deal.data["preClosing"]["dates"]["statedDate"]
    
    #endDate = tz.get_in(["clear", "endDate"], deal.data, default=None)
    # console.print(deal.data)
    return {
        "cutoffDate": cutoffDate,
        "annDate": annDate,
        "bookingDate": bookingDate,
        "closingDate": closingDate,
        "statedDate": statedDate,
        #"freq": 
        #"endDate": endDate,
    }

    
def dealBasicInfo(deal: Deal):
    today = date.today()
    rolesR = list(Roles.select().where(Roles.deal == deal).dicts())
    
    if deal.data is None:
        return div[f"{deal.dealid}: <Deal Data is empty>"]
    if 'issuePlan' not in deal.data:
        return div[f"{deal.dealid}: <Deal Data has no issuePlan>"]
    if 'preClosing' not in deal.data:
        return div[f"{deal.dealid}: <Deal Data has no preClosing>"]
    
    
    isClosed = False if deal.closingDate is None else True
    
    
    datesMap = getDealDates(deal)
    
    if datesMap is None:
        return div[f"{deal.dealid}: <Deal Data has no planned dates info>"]

    issuePlan = deal.data["issuePlan"]

    tillClosingDays = (parse(datesMap["closingDate"]).date() - today).days
    

    
    tillBookDays = (
        (parse(datesMap["bookingDate"]).date() - today).days
        if datesMap["bookingDate"] is not None
        else None
    )
    
    
    freq = tz.get_in(["preClosing", "dates", "freq"], deal.data, default=None),

    return div(".box.container")[
        h4(".title.is-6")["基础信息"],
        div(".columns")[
            ul(".column")[  # li[f"起算日期: {datesMap['cutoffDate']}"]
                li[f"公告日期: {datesMap['annDate']}"],
                li(
                    {
                        "class": "has-tooltip",
                        "data-tooltip": f" (距今:{tillBookDays}天)",
                    }
                    if (tillBookDays > 0 and tillBookDays is not None)
                    else ""
                )[ f"簿记建档: {deal.bookDate}" if isClosed else f"簿记建档(预计): {datesMap['bookingDate']}"],
                li(
                    {
                        "class": "has-tooltip",
                        "data-tooltip": f" (距今:{tillClosingDays}天)",
                    }
                    if (tillClosingDays > 0 and tillClosingDays is not None)
                    else ""
                )[f"设立日期: {deal.closingDate}" if isClosed else f"设立日期(预计): {datesMap['closingDate']}"],
                
                li[f"清算日期: {deal.endDate}" ] if deal.endDate else None,
                li[f"法定到期: {datesMap['statedDate']}"],
            ],
            ul(".column")[
                li(
                    {
                        "class": "has-tooltip",
                        "data-tooltip": str(issuePlan.get("payDate", "")),
                    }
                )[f"付款周期: ",freq],
                li[f"底层资产: ", span[assetClassMap.get(deal.poolType, "")]],
                (
                    li[f"细分资产: ", span[subAssetClassMap.get(deal.poolSubType, "")]]
                    if deal.poolType == "NPL"
                    else None
                ),
                li[
                    f"产品系列: ", genLink(deal.seriesName, ["series", deal.seriesName])
                ],
            ],
            ul(".column")[
                li[rolesR and f"发起人: {rolesR[0]['originator']}"],
                li[rolesR and f"承销商: {rolesR[0]['underwriter']}"],
                li[rolesR and f"发行人: {rolesR[0]['issuer']}"],
                li[f"簿记人: {tranAc(issuePlan.get('booker','/'))}"],
                li[rolesR and f"服务商: {rolesR[0]['servicer']}"],
            ],
        ],
    ]


def currentBondInfo(deal: Deal, highlightBond: str | None = None):
    """
    当前最新证券信息

    """
    if deal.data is None:
        return div[f"{deal.dealid}: Deal Data is None"]
    bondObj = (
        Bond.select()
        .join(Deal)
        .where(Bond.deal == deal)
    )
    bondPaymentsObj = (
        BondPayments.select(Bond.name, BondPayments)
        .join(Bond)
        .where(BondPayments.bond.deal == deal)
    )
    dealPayments = list(bondPaymentsObj.dicts())
    dealPaymentsByBond = tz.thread_last(
        tz.groupby("name", dealPayments),
        (tz.valmap, tz.curry(sorted, key=lambda x: x["paymentDate"])),
    )
    dealBonds = list(bondObj.dicts())
    console.print(dealBonds)

    dealBondsM = listOfMapToMap(dealBonds, "name", remove=False)
    bondLastPayRecord = tz.valmap(tz.last, dealPaymentsByBond)
    bondPaidOffFlag = tz.valmap(
        lambda x: {"清偿完毕": x["currentBalance"] == 0 or x["currentBalance"] is None},
        bondLastPayRecord,
    )

    dealBondsM = tz.merge_with(tz.merge, dealBondsM, bondPaidOffFlag)
    ksToShow = [
        "name",
        "curFactor",
        "curBalance",
        "curRate",
        "issueDate",
        "expectedMaturity",
        "issueFace",
        "issuePrice",
        "seniority",
    ]
    bonds = [subMap(m, ks=ksToShow) for m in dealBondsM.values()] & lens.Each()[
        "curFactor"
    ].modify(lambda x: round(x * 100, 2))
    bonds = [
        tz.dissoc(x, "seniority")
        for x in sorted(bonds, key=lambda x: x["seniority"], reverse=True)
    ]
    bonds &= lens.Each().modify(tz.compose(transBnd, displayBondField))

    
    # issue 
    bondData = list(PreClosingBond.select().where(PreClosingBond.deal == deal).dicts())
    issuePlan = deal.data["issuePlan"]
    
    expectClosingDate = tz.get_in(["issuePlan", "closingDate"], deal.data, default=None)
    assert expectClosingDate is not None, "Expected closing date is missing in issue plan data"

    #TODO use PreClosingBond table instead 
    bondsAtIssuance = (
        bondData
        & lens.Each().modify(lambda bm: tz.assoc(bm, "closingDate", parse(expectClosingDate).date()))
        & lens.Each()["balance"].modify(toWan)
        & lens.Each()["availBal"].modify(toWan)
        & lens.Each().modify(remapMapKey({"name":"名称","balance":"发行规模","availBal":"配售规模","intType":"利率类型","wal":"加权平均期限","closingDate":"设立日期"}))
        & lens.Each().modify(
            lambda z: tz.dissoc(z, "id","deal","data","expectedMaturity")
        )
    )

    defaultSelect = (
        """{selectedTable: 'currentInfo'}"""
        if dealBonds
        else """{selectedTable: 'issuanceInfo'}"""
    )
    optionList = (
        {"currentInfo": "当前状态", "issuanceInfo": "发行状态"}
        if dealBonds
        else {"issuanceInfo": "发行状态"}
    )

    return div(".box.container", {"x-data": defaultSelect})[
        h4(".title.is-6")["支持证券"],
        div(".field.is-grouped.mb-3")[
            div(".control")[
                [
                    label(".radio")[
                        input(
                            type="radio",
                            name="bondSnapshotStatus",
                            x_model="selectedTable",
                            value=opt,
                        ),
                        span[f"{optionList[opt]}"],
                    ]
                    for opt in optionList.keys()
                ]
            ]
        ],
        div(".columns")[
            div[
                div({"x-show": "selectedTable == 'currentInfo'"})[
                    dictListToTable(
                        bonds, cls={"class": modDataTable + " is-fullwidth"}
                    )
                ],
                div({"x-show": "selectedTable == 'issuanceInfo'"})[
                    dictListToTable(
                        bondsAtIssuance, {"class": modDataTable + " is-fullwidth"}
                    )
                ],
            ]
        ],
    ]


def nplRecoveryChart(tdraw, estRecovery):

    try:
        recoveries = list(tz.pluck("Recovery", tdraw.values()))
        cumRecovery = dict(zip(tdraw.keys(), np.cumsum(recoveries)))

        recoveryBench = tz.pipe(
            tz.merge_with(
                lambda ms: {"CumRecovery": float(ms[0])} | ms[1],
                cumRecovery,
                tdraw,
            ),
            lambda m: {
                v["CollectionPeriodEnd"]: tz.dissoc(
                    v,
                    "RecoveryByProcess",
                    "RecoveryByLiquidated",
                    "CollectionPeriodBegin",
                )
                for k, v in m.items()
            },
        )

        x_axis = list(recoveryBench.keys())
        y_axis = [
            round(v["CumRecovery"] / 10000.0, 2)
            for v in recoveryBench.values()
            if "CumRecovery" in v and isinstance(v["CumRecovery"], (int, float))
        ]

        assert (
            len(estRecovery) == 2
        ), "ExpectRecovery data is missing or empty in preClosing pool data"
        r1est, r2est = estRecovery.items()

        agencyEst1 = round(r1est[1] / 10000.0, 2) if r1est[1] is not None else 0
        agencyEst2 = round(r2est[1] / 10000.0, 2) if r2est[1] is not None else 0

        chart = (
            Line()
            .add_xaxis(x_axis)
            .add_yaxis(
                "累计回收金额(万)",
                y_axis,
                is_smooth=True,
                yaxis_index=0,
                label_opts=opts.LabelOpts(is_show=False),
            )
            .add_yaxis(
                r1est[0],
                [agencyEst1] * len(x_axis),
                is_smooth=True,
                yaxis_index=0,
                linestyle_opts=opts.LineStyleOpts(type_="dashed"),
                label_opts=opts.LabelOpts(is_show=False),
            )
            .add_yaxis(
                r2est[0],
                [agencyEst2] * len(x_axis),
                is_smooth=True,
                yaxis_index=0,
                linestyle_opts=opts.LineStyleOpts(type_="dashed"),
                label_opts=opts.LabelOpts(is_show=False),
            )
            .set_global_opts(
                title_opts=opts.TitleOpts(title="累计回收金额"),
                xaxis_opts=opts.AxisOpts(name="日期"),
                yaxis_opts=opts.AxisOpts(name="累计回收金额(万)", position="left"),
            )
        )

        return div[ #span["Tbl"]
                    Markup(render(chart))
            ]
    except Exception as e:
        return div[f"nplRecoveryChart not ready"]


def poolPerformanceNPL(deal: Deal, html=True):
    """
    池表现
    """

    def calcARS(bal: float, begDate: str, endDate: str, recovery: float):
        yearFraction = (parse(endDate) - parse(begDate)).days / 365
        annualizedRecovery = recovery / yearFraction if yearFraction > 0 else 0
        ars = annualizedRecovery / bal if bal > 0 else 0
        return round(ars, 4)

    poolIssuanceBal = float(
        tz.get_in(["preClosing", "pool", "totalBalance"], deal.data, default=0)
    )
    assert isinstance(
        poolIssuanceBal, (int, float)
    ), f"poolIssuanceBal must be a number but got {poolIssuanceBal}"

    if deal.data is None:
        return div[f"{deal.dealid}:<Deal Data is None>"]
    if "current" not in deal.data:
        return div[f"{deal.dealid}:<Deal Data has no current data>"]
    if "trustee" not in deal.data["current"]:
        return div[f"{deal.dealid}:<Deal Data has no trustee data>"]

    trusteeDataRaw = tz.pipe(
        tz.get_in(["current", "trustee"], deal.data),
        lambda m: sorted(m.items(), key=lambda kv: int(kv[0])),
        dict,
    )

    estRecovery = tz.get_in(
        ["preClosing", "pool", "ExpectRecovery"], deal.data, default=[]
    )
    recoveryChart = nplRecoveryChart(trusteeDataRaw, estRecovery)

    # console.print("cumRecovery", recoveryBench)

    trusteeData = tz.pipe(
        trusteeDataRaw,
        lambda m: {
            k: tz.assoc(
                v,
                "ARS",
                calcARS(
                    poolIssuanceBal,
                    v["CollectionPeriodBegin"],
                    v["CollectionPeriodEnd"],
                    float(v["Recovery"]),
                ),
            )
            for k, v in m.items()
        },
        lambda m: m & lens.Values().modify(displayNplPoolPerfField),
        lambda ms: ms & lens.Values().modify(lambda v: remapMapKey(poolPerfMapNpl, v)),
    )

    if html:
        return p[
            p["资产池处置"],
            dictToTable_KeyAsRow(trusteeData, "报告期数", {"class": modDataTable}),
            p["累计回收"],
            recoveryChart,
        ]
    else:
        return trusteeData


def poolPerformance(deal: Deal):
    """
    池表现
    """
    match (deal.poolType, deal):
        case ("NPL", _):
            return poolPerformanceNPL(deal)

        case _:
            return div["池表现数据仅在NPL产品中展示"]


def currentInfo(deal: Deal):
    """
    产品存续信息
    """
    ksToShow = [
        "name",
        "curFactor",
        "curBalance",
        "curRate",
        "issueDate",
        "expectedMaturity",
        "issueFace",
        "issuePrice",
        "issueRate",
    ]
    transBnd = remapMapKey(bondFieldMap)
    today = date.today()

    ## input data
    bondObj = (
        Bond.select()
        .join(Deal)
        .switch(Bond)
        .join(BondID)
        .where(Bond.deal == deal, BondID.idType == "简称")
    )
    dealBonds = list(bondObj.dicts())
    dealBondsM = listOfMapToMap(dealBonds, "name", remove=False)

    bondPaymentsObj = (
        BondPayments.select(Bond.name, BondPayments)
        .join(Bond)
        .where(BondPayments.bond.in_(bondObj))
        #.order_by(Bond.seniority.asc())
    )
    dealPayments = list(bondPaymentsObj.dicts())
    dealPaymentsByBond = tz.thread_last(
        tz.groupby("name", dealPayments),
        (tz.valmap, tz.curry(sorted, key=lambda x: x["paymentDate"])),
    )

    bondData = tz.merge_with(
        tz.merge, dealBondsM, tz.valmap(lambda vs: {"payments": vs}, dealPaymentsByBond)
    )

    ## Bond analytics data
    bondLastPayRecord = tz.valmap(tz.last, dealPaymentsByBond)
    bondPaidOffFlag = tz.valmap(
        lambda x: {"清偿完毕": x["currentBalance"] == 0 or x["currentBalance"] is None},
        bondLastPayRecord,
    )

    dealBondsM = tz.merge_with(tz.merge, dealBondsM, bondPaidOffFlag)
    bonds = [subMap(m, ks=ksToShow) for m in dealBondsM.values()]
    bonds &= lens.Each().modify(tz.compose(transBnd, displayBondField))

    ## bond payments
    # console.print(f"<debug>:{dealPaymentsByBond}")
    bondPayments = tz.thread_last(
        dealPaymentsByBond,
        (
            tz.valmap,
            tz.curry(
                map,
                lambda m: subMap(
                    m,
                    ks=[
                        "updatePeriod",
                        "paymentDate",
                        "currentBalance",
                        "principal",
                        "currentRate",
                        "interest",
                        "interestYield",
                        "cash",
                    ],
                ),
            ),
        ),
        (tz.valmap, list),
        (
            tz.valmap,
            lambda xs: dropFieldInListOfMap(
                xs, "interestYield", dropFn=lambda v: v == 0 or v is None
            ),
        ),
        lens.Values().Each().modify(displayBondField),
        lens.Values().Each().modify(transBnd),
    )
    ### UI
    
    default_bond = next(iter(bondPayments.keys()), None)
    bNameList = sorted(bondPayments.keys(),reverse=True)  # sort bond name in reverse order to show senior bond first

    ## bond 
    bondPaymentUI = div(".box")[
                    div(".field.is-grouped")[
                        [
                            div(".control")[
                                label(".radio")[
                                    input(
                                        type="radio",
                                        name="bondSelect",
                                        **{
                                            "x-model": "selectedBond",
                                            ":value": f"'{bName}'",
                                        },
                                    ),
                                    span[f" {bName} "],
                                ]
                            ]
                            for bName in bNameList
                        ]
                    ],
                    [
                        div({"x-show": f"selectedBond === '{bName}'"})[
                            dictListToTable(
                                payments,
                                cls={"class": modDataTable},
                            )
                        ]
                        for bName, payments in bondPayments.items()
                    ],
                ]
    ## pool performance
    poolPerf = div(".box")[poolPerformance(deal)]



    return [
        div(".box.content")[
            div(".block", {"x-data": f"{{ selectedBond: {json.dumps(default_bond)} }}"})[
                mkTabs({"资产表现":poolPerf,"证券兑付": bondPaymentUI}
                       ,activeTab="资产表现"
                       ,tabFontSize=6)
            ]
        ]
    ]


def relatedIssuance(deal: Deal, sameSeriesMonths: int, samePoolTypeMonths: int):

    sameSeriesDeals, sameTypeDeals = relatedBonds(
        deal, sameSeriesMonths, samePoolTypeMonths
    )

    historyIssuance = tz.pipe(
        sameSeriesDeals + sameTypeDeals,
        lambda xs: xs
        & lens.Each().modify(
            lambda z: tz.assoc(
                z, "预期存续", yearFraction(z["issueDate"], z["expectedMaturity"])
            )
        ),
    )
    return (
        historyIssuance[: len(sameSeriesDeals)],
        historyIssuance[len(sameSeriesDeals) :],
    )


@app.get("/deal/{deal_id}/projectIssuanceRate")
def projectIssuanceRate(
    deal_id, scenario: str = Query("normal", enum=["normal", "short"])
):
    with db:
        deal = Deal.get(Deal.dealid == deal_id)
        assert scenario in ["normal", "short"], f"scenario {scenario} is not supported"
        w = 0.65
        adj = 0
        match (deal, scenario):
            case (_, "normal"):
                sameSeriesMonths = 18
                samePoolTypeMonths = 12
                spreadRange = 0.08
            case (_, "short"):
                sameSeriesMonths = 6
                samePoolTypeMonths = 3
                spreadRange = 0.1

        # print("mathcing ",deal.poolType,deal.poolSubType)
        match (deal, scenario):
            case (_, _) if deal.poolType == "NPL" and deal.poolSubType == "住房按揭":
                w = 0.8
                adj = 0.4
            case (_, _) if (
                deal.poolType == "NPL"
            ) and deal.poolSubType == "小微企业贷款":
                # w = 0.8
                adj = 0.4
                # console.print("hit here")
            case _:
                pass
                # adj = 3.8

        # console.print("using params", sameSeriesMonths, samePoolTypeMonths, spreadRange, w)

        bondData = deal.data["preClosing"]["bonds"]

        bondStartDate = deal.data["issuePlan"]["bondStartDate"]
        bndWithExpectedMaturity = tz.pipe(
            bondData
            & lens.Each().modify(
                lambda z: tz.assoc(
                    z,
                    "预期存续",
                    yearFraction(
                        deal.data["issuePlan"]["bondStartDate"], z["预期到期日"]
                    ),
                )
            ),
            lambda xs: listOfMapToMap(xs, "债券名称"),
        )
        bndWithAvgMaturity = deal.data["issuePlan"]["bonds"] & lens.Each()[
            "债券名称"
        ].modify(lambda z: z.replace("资产支持证券", ""))
        expectSpread = calcSpreadFn(
            deal, historyIssuance, sameSeriesDeals, sameTypeDeals, weight=w
        )
        # console.print("bond bndWithExpectedMaturity", bndWithExpectedMaturity)

        projectedRate = {}
        for k, v in listOfMapToMap(bndWithAvgMaturity, "债券名称").items():
            if v["发行利率"] in ["零息式"]:
                continue
            avgLookupKey = getFirstKeyInMap(
                v, ["预计加权平均期限", "预计加权平均期限(如有)"]
            )  #
            if avgLookupKey is None:
                print("v -> ", v)
            print(
                f"{k} -> using avgLookupKey:{avgLookupKey} with value {v[avgLookupKey]}"
            )
            projectedRate[k] = round(
                calcProjectRfRate(
                    bondStartDate,
                    "中债国债收益率曲线",
                    (
                        v[avgLookupKey]
                        if (v[avgLookupKey] is not None)
                        else bndWithExpectedMaturity[k]["预期存续"]
                    ),
                ),
                2,
            )

        projectedRateAfterSpread = (
            projectedRate
            & lens.Values().modify(lambda z: z + expectSpread + adj)
            & lens.Values().modify(
                lambda z: f"{round(z - spreadRange,2)}% - {round(z + spreadRange,2)}%"
            )
        )

        r = [
            div(".block")["预计利率", str(projectedRateAfterSpread)],
            hr,
            info(
                f"过去{sameSeriesMonths}个月同系列产品,以及过去{samePoolTypeMonths}个月同底层资产类别产品"
            ),
            (
                dictListToTable(
                    historyIssuance
                    & lens.Each()["issueRate"].modify(
                        lambda y: f"{round(y*100,4)}%" if y is not None else "/"
                    )
                    & lens.Each().modify(
                        lambda m: tz.assoc(
                            m, "产品", genLink(m["shortNameKey"], ["deal", m["dealid"]])
                        )
                    )
                    & lens.Each().modify(
                        lambda m: tz.dissoc(
                            m,
                            "id",
                            "发行面额",
                            "curFactor",
                            "curRate",
                            "issuePrice",
                            "seniority",
                            "deal",
                            "stage",
                            "period",
                            "fullName",
                            "bookDate",
                            "poolType",
                            "poolSubType",
                            "seriesName",
                            "curBalance",
                            "data",
                            "shortName",
                            "endDate",
                            "dealid",
                            "shortNameKey",
                        )
                    )
                    # & lens.Each().modify(transBnd)
                    ,
                    cls={"class": modDataTable},
                )
                if historyIssuance
                else warning("无参考项目")
            ),
        ]
        return HTMLResponse(html[r])


@app.get("/related/{deal_id}/{sameSeriesMonths}/{samePoolTypeMonths}")
def relatedIssuanceView(
    deal_id: str, sameSeriesMonths: int = 18, samePoolTypeMonths: int = 12
):
    with db:
        deal = Deal.get(Deal.dealid == deal_id)
        (sameSeriesBonds, sameTypeBonds) = relatedIssuance(deal, 18, 12)
        subMapFn = lambda m: subMap(
            m, ks=["产品", "name", "issueDate", "issueRate", "spread"]
        )
        sameSeriesSpreads = (
            [
                tz.assoc(b, "spread", s)
                for (b, s) in zip(sameSeriesBonds, calcBondSpreads(sameSeriesBonds))
            ]
            & lens.Each()["issueRate"].modify(toRate)
            & lens.Each()["spread"].modify(toSpread)
            & lens.Each().modify(
                lambda m: tz.assoc(
                    m, "产品", genLink(m["shortNameKey"], ["deal", m["deal"]])
                )
            )
        )
        sameTypeSpreads = (
            [
                tz.assoc(b, "spread", s)
                for (b, s) in zip(sameTypeBonds, calcBondSpreads(sameTypeBonds))
            ]
            & lens.Each()["issueRate"].modify(toRate)
            & lens.Each()["spread"].modify(toSpread)
            & lens.Each().modify(
                lambda m: tz.assoc(
                    m, "产品", genLink(m["shortNameKey"], ["deal", m["deal"]])
                )
            )
        )
        sameSeriesSpreads &= lens.Each().modify(tz.compose(transBnd, subMapFn))
        sameTypeSpreads &= lens.Each().modify(tz.compose(transBnd, subMapFn))

        return tz.pipe(
            mkTabs(
                {
                    "同系列发行": div[
                        dictListToTable(
                            sameSeriesSpreads, {"class": modDataTable + " is-fullwidth"}
                        ),
                    ],
                    "同类型发行": div[
                        dictListToTable(
                            sameTypeSpreads, {"class": modDataTable + " is-fullwidth"}
                        ),
                    ],
                },
                activeTab="同系列发行",
            ),
            HTMLResponse,
        )


# @profile(output='log',sort_by="time",n_rows=20)
def preClosingInfo(deal: Deal):
    if deal.data is None:
        return div[f"{deal.dealid}:<Deal Data is None>"]
    assert (
        "preClosing" in deal.data
    ), f"The deal {deal.dealid} shall have preclosing data"
    assert "issuePlan" in deal.data, f"The deal {deal.dealid} shall have issuePlan data"

    poolType = deal.poolType
    bondData = deal.data["preClosing"]["bonds"]
    issuanceAmt_ = sum(bondData & lens.Each()["发行规模/金额"].collect())
    issuanceAmt = toWan(issuanceAmt_)

    match deal.poolType:
        case "NPL":
            dataByAssetClass = ratingReportNPL(deal)
        case "AUTO":
            dataByAssetClass = ratingReportAuto(deal)
        case _:
            dataByAssetClass = div[""]

    return div(".box")[
        div(".columns")[
            div(".column")[
                hr,
                p(".title.is-6")["融资结构"],
                div[f"募集规模: {issuanceAmt}"],
                div[
                    f"次级比例: {toPct(bondData[-1].get('发行规模/金额',0),issuanceAmt_)}"
                ],
            ],
            div(".column")[dataByAssetClass],
        ]
    ]


def relateIssuance(deal: Deal, m=18, n=12):
    return div(".box")[
        hr
        ,p[f"相关发行: 过去{m}个月同系列产品,以及过去{n}个月同底层资产类别产品,以及发行利差"]
        ,button(
            {
                "hx-get": f"/related/{deal.dealid}/{m}/{n}",
                "hx-target": "#related-issuance-content",
                "hx-swap": "innerHTML",
                "hx-on:htmx:after-request": "this.style.display='none';",
                "class": "button",
            }
        )["加载相关发行"],
        div({"id": "related-issuance-content"}),
    ]


def ratingReportView(deal: Deal):
    # 📉  📈 🟩 🟥
    if deal.data is None:
        return div(".box.content")["🔒"]
    if "preClosing" not in deal.data:
        return div(".box.content")["🔒"]

    initViews = tz.get_in(["preClosing", "view"], deal.data, default={})
    seqViews = sorted(
        tz.get_in(
            [
                "seqViews",
            ],
            deal.data,
            default={},
        ).values(),
        key=lambda x: x["ratingDate"],
        reverse=True,
    )

    initViewUI = [hr, p[h6(".title.is-6")[f"售前报告:"]]] + [
        article(".message.is-dark")[
            div(".message-body")[
                p[em[f"{agency}"]],
                [p[em[ratingView[v]], ul[[li[b] for b in vs[v]]]] for v in vs]
            ],
        ]
        for (agency, vs) in initViews.items()
    ]
    seqViewsUI = (
        [hr, p[h6(".title.is-6")[f"跟踪报告:"]]]
        + [
            article(".message.is-dark")[
                div(".message-body")[
                    p[em[f"{m['agency']}"]],
                    ul[
                        li[f"评级日期: {m['ratingDate']}"],
                        li[
                            f"基准日: 债券/{m.get('bondDate','/')} , 资产池/{m.get('poolDate','/')}"
                        ],
                        li["跟踪评级: ", [f" <{b}/{r}> " for b, r in m["bonds"].items()]],
                    ],
                    [
                        p[
                            em[ratingView[k]],
                            ul[[li[b] for b in v] if isinstance(v, list) else li[v]],
                        ]
                        for k, v in subMap(
                            m,
                            ks=[
                                "positiveView",
                                "negativeView",
                            ],
                        ).items()
                    ],
                    ]
            ]
            for m in seqViews
        ]
        if seqViews
        else []
    )
    if initViews:
        return div(".box.content")[seqViewsUI + initViewUI]

    else:
        return div(".box.content")["🔒"]


def waterfallTab(deal: Deal):

    if ws := tz.get_in(["waterfall", "normal"], deal.data, default=None):
        r = div(".box.content")[
            p(".title.is-size-6")[f"违约前分配 "], hr, ol[[li[w] for w in ws]]
        ]

    else:
        r = div(".box.content")["🔒"]
    return r


def clearInfo(deal: Deal):
    if "clear" not in deal.data:
        return div(".box")["🔒"]

    ## bond payment data
    cd = deal.data["clear"]
    pd = deal.data["preClosing"]
    bondObj = (
        Bond.select()
        .join(Deal)
        .switch(Bond)
        .join(BondID)
        .where(Bond.deal == deal, BondID.idType == "简称")
    )
    dealBonds = list(bondObj.dicts())
    # console.print("dealBonds", dealBonds)
    dealBondsM = listOfMapToMap(dealBonds, "name", remove=False)

    bondPaymentsObj = (
        BondPayments.select(Bond.name, BondPayments)
        .join(Bond)
        .where(BondPayments.bond.in_(bondObj))
    )
    dealPayments = list(bondPaymentsObj.dicts())
    dealPaymentsByBond = tz.thread_last(
        tz.groupby("name", dealPayments),
        (tz.valmap, tz.curry(sorted, key=lambda x: x["paymentDate"])),
    )

    bondData = tz.merge_with(
        tz.merge, dealBondsM, tz.valmap(lambda vs: {"payments": vs}, dealPaymentsByBond)
    )

    _bondWithPayment = tz.pipe(
        bondData,
        lambda x: x
        & lens.Values()["payments"].modify(
            lambda ps: (
                list(tz.pluck("paymentDate", ps)),
                list(map(floatN, tz.pluck("principal", ps))),
                list(map(floatN, tz.pluck("cash", ps))),
            )
        ),
    )

    _bondEndDate = tz.pipe(
        {
            k: list(
                dropwhile(
                    lambda y: (y["currentBalance"] is not None)
                    and y["currentBalance"] > 0,
                    ys,
                )
            )
            for k, ys in dealPaymentsByBond.items()
        },
        lambda m: {
            k: {"本金结清": v[0]["paymentDate"] if v else None} for k, v in m.items()
        },
    )

    _bondWal = tz.pipe(
        _bondWithPayment,
        lambda x: {
            bn: ([v["issueDate"]] + v["payments"][0], [0.0] + v["payments"][1])
            for bn, v in _bondWithPayment.items()
        },
        lambda x: tz.valmap(lambda v: {"加权存续": round(calcWAL(v[0], v[1]), 2)}, x),
    )

    _bondXirr = tz.pipe(
        _bondWithPayment,
        lambda x: {
            bn: (
                [v["issueDate"]] + v["payments"][0],
                [-1 * float(v["issuePrice"]) / 100.0 * float(v["issueFace"])]
                + v["payments"][2],
            )
            for bn, v in _bondWithPayment.items()
        }
        # , lambda x: tz.do(console.print, x)
        ,
        lambda x: tz.valmap(
            lambda v: {
                "年化回报": toRate(xirr(v[0], v[1])),
                "静态收益": toWan(sum(v[1])),
                "静态回报": toPct(sum(v[1]), v[1][0] * -1),
            },
            x,
        ),
    )

    bondStats = tz.merge_with(tz.merge, _bondXirr, _bondWal, _bondEndDate)

    commonFields = {
        "存续时间": get_month_diff(parse(cd["startDate"]), parse(cd["endDate"])),
        "起始日期": cd["startDate"],
        "结束日期": cd["endDate"],
    }

    match deal.poolType:
        case "NPL":
            cd = deal.data["clear"]
            outflow = [
                {"name": k, "balance": v}
                for k, v in cd.get("outflow", {}).items()
                if (v is not None) and v > 0
            ]
            inflowField = ["totalRecoveryAmt", "interestAmt", "callAmt"]
            inflow = [
                {"name": dealClearField.get(k, k), "balance": cd.get(k, 0)}
                for k in inflowField
            ]
            pd = deal.data["preClosing"]
            recoveryEsti = tz.keymap(
                lambda x: agencyShortName[x], pd["pool"]["ExpectRecovery"]
            )
            assert (
                "totalRecoveryAmt" in cd
            ), f"deal {deal.dealid} clear data has no totalRecoveryAmt field"
            assert (
                cd["totalRecoveryAmt"] is not None
            ), f"deal {deal.dealid} clear data has zero totalRecoveryAmt field"
            assert isinstance(cd["totalRecoveryAmt"], float) or isinstance(
                cd["totalRecoveryAmt"], int
            ), f"deal {deal.dealid} clear data totalRecoveryAmt field is not float but {type(cd['totalRecoveryAmt'])} with value {cd['totalRecoveryAmt']}"
            recoveryEstiDev = tz.valmap(
                lambda x: round(x / cd["totalRecoveryAmt"] * 100, 2), recoveryEsti
            )
            # console.print(cd)
            return div(".box")[
                div(".columns")[
                    div(".column")[
                        h5(".title .is-6")["产品统计"],
                        ul(".list")[
                            li[f"产品存续: {commonFields['存续时间']}月"],
                            ul[
                                li[f"起始日期: {commonFields['起始日期']}"],
                                li[f"结束日期: {commonFields['结束日期']}"],
                            ],
                            li[f"回收款项: {toWan(cd['totalRecoveryAmt'])}"],
                            li[f"初始余额: {toWan(pd['pool']['totalBalance'])}"],
                            li[
                                f"回收比率: {toPct(cd['totalRecoveryAmt'], pd['pool']['totalBalance'])}"
                            ],
                            li[
                                "预计回收: ",
                                ul[
                                    [
                                        li[
                                            f"{raName}: {toWan(raEsti)} / ({recoveryEstiDev[raName]}%)"
                                        ]
                                        for raName, raEsti in recoveryEsti.items()
                                    ]
                                ],
                            ],
                        ],
                    ],
                    div(".column")[
                        h5(".title .is-6")["债券统计"],
                        div(".content")[dictToTable_KeyAsCol(bondStats)],
                    ],
                ],
                div(".columns")[
                    div(".column")[
                        h5(".title .is-6")["收入统计"],
                        div(".content")[breakdownAccount(inflow)],
                    ],
                    div(".column")[
                        h5(".title .is-6")["支出统计"],
                        div(".content")[breakdownAccount(outflow)],
                    ],
                ],
            ]
        case _:
            return div[""]


def buildFileViewer(m: dict, showCategories: bool = True):
    """
    m -> a map with key as category, value as list of file names
         -> value : [ {'key': filename}, ... ]
    显示为：左侧 radio，右侧 select，选择后展示 markdown
    """
    # 筛选有 Markdown 的文件
    fs = {k: [v["key"] for v in vs] for k, vs in m.items() if len(vs) > 0}
    categories = list(fs.keys())
    # 默认选中第一个类别
    default_cat = categories[0] if categories else ""
    # 默认选中第一个文件
    default_file = fs[default_cat][0] if default_cat and fs[default_cat] else ""

    return div(
        {
            "x-data": f"""{{
                selectedCat: {json.dumps(default_cat)},
                selectedFile: {json.dumps(default_file)},
                filesInDropdown: {json.dumps(fs[default_cat])},
                content: '',
                files: {json.dumps(fs)},
                async loadMarkdown() {{
                    if (!this.selectedFile) {{
                        this.content = '';
                        return;
                    }}
                    try {{
                        const response = await fetch(`/file/${{this.selectedFile}}/md`);
                        const text = await response.text();
                        this.content = text;
                    }} catch (error) {{
                        this.content = '<p>加载失败</p>';
                    }}
                }},
                updateFiles() {{
                    if (this.selectedCat && this.files[this.selectedCat] && this.files[this.selectedCat].length > 0) {{
                        this.filesInDropdown = this.files[this.selectedCat];
                        selectedFile = this.files[this.selectedCat][0];
                        this.loadMarkdown();

                    }} else {{
                        this.selectedFile = '';
                        this.content = '';
                    }}
                }}
            }}""",
            "x-init": """
                    if (selectedFile) loadMarkdown()
                """,
        }
    )[
        div(".field.is-grouped")[
            div(".control")[
                select(
                    {
                        "x-model": "selectedCat",
                        "@change": "updateFiles()",
                        "class": "select",
                    }
                )[*[option({"value": cat})[cat] for cat in categories]]
            ],
            div(".control")[
                select(
                    {
                        "x-model": "selectedFile",
                        "@change": "loadMarkdown()",
                        "class": "select",
                    }
                )[
                    option(value="")["请选择文件"],
                    # 这里生成所有类别的所有文件，但在客户端会根据选中的类别筛选
                    # 或者使用 Alpine.js 的 x-for 在客户端动态生成
                    template({"x-for": "file in filesInDropdown"})[
                        option(
                            {"x-text": "file", ":value": "file"}
                        )  # Use :value for Alpine.js binding
                    ],
                ]
            ],
        ],
        div(
            {"class": "title is-5", "x-text": "selectedFile", "x-show": "selectedFile"}
        ),
        div(
            {
                "x-html": "content",
                "class": "content box markdown-body",
                "x-show": "content",
            }
        ),
        div({"class": "box", "x-show": "!content && selectedFile"})["加载中..."],
        div({"class": "box has-text-grey", "x-show": "!selectedFile"})[
            "请选择一个文件"
        ],
    ]


def docInfo(deal: Deal):
    ratingDocs = list(
        RatingReport.select(Location.key, RatingReport.seq)
        .join(Location)
        .where(RatingReport.deal == deal)
        .dicts()
    )
    initRatingDocs = [d for d in ratingDocs if d["seq"] == 0]
    seqRatingDocs = [d for d in ratingDocs if d["seq"] != 0]
    issuanceDocs = list(
        IssueFiles.select(Location.key)
        .join(Location)
        .where(IssueFiles.deal == deal)
        .dicts()
    )
    bookingDocs = list(
        BookingAnn.select(Location.key)
        .join(Location)
        .where(BookingAnn.deal == deal)
        .dicts()
    )
    pricingDocs = list(
        PricingReport.select(Location.key)
        .join(Location)
        .where(PricingReport.deal == deal)
        .dicts()
    )
    issuePlanDocs = list(
        IssuePlan.select(Location.key)
        .join(Location)
        .where(IssuePlan.deal == deal)
        .dicts()
    )
    clearDocs = list(
        ClearReport.select(Location.key)
        .join(Location)
        .where(ClearReport.deal == deal)
        .dicts()
    )
    trusteeDocs = list(
        TrusteeReport.select(Location.key)
        .join(Location)
        .where(TrusteeReport.deal == deal)
        .order_by(TrusteeReport.period)
        .dicts()
    )
    rFiles = {
        "公告文件": initRatingDocs + issuePlanDocs + issuanceDocs,
        "跟踪评级": seqRatingDocs,
        "上市文件": bookingDocs + pricingDocs,
        "受托报告": trusteeDocs,
        "清算报告": clearDocs,
    }

    # TODO : make sure file viewer has the corresponding markdown files
    return div[
        warning("仅为机器翻译,存在表格错位,图表缺失情况."),
        buildFileViewer(rFiles),
    ]


@app.get("/deal/{deal_id}/")
def dealinfo(deal_id, bond: str | None = Query(default=None)):
    # print("bond", bond)
    with db:
        deal = Deal.get(Deal.dealid == deal_id)
        dealTemplate = [
            h3(".title .is-4")[f"{deal.shortNameKey}"],
            buildPath(
                [
                    ("首页", "/index"),
                    ({deal.seriesName}, f"/series/{deal.seriesName}/"),
                    (deal.shortNameKey, f"deal/{deal.dealid}"),
                ]
            ),
            dealBasicInfo(deal),
            currentBondInfo(deal, highlightBond=bond),
        ]
        initTabs = {
            "发行信息": preClosingInfo(deal),
            "相关发行": relateIssuance(deal),
            "评级观点": ratingReportView(deal),
            "分配规则": waterfallTab(deal),
        }
        docTab = {"文档速览": docInfo(deal)}
        vipTab = {
            "🔒现金流": div(".box")["🔒 债券/资产池 现金流测算 | 估值"],
            "🔒信息流": div(".box")["🔒 产品全周期公告 | 摘要分析 | 指标跟踪 "]
        }  # Placeholder for future implementation
        if deal.stage == Stage.get_by_id(1):
            r = initTabs | docTab | vipTab
            dt = "发行信息"
        elif deal.stage == Stage.get_by_id(2):
            r = initTabs | {"存续信息": currentInfo(deal)} | docTab | vipTab
            dt = "存续信息"
        elif deal.stage == Stage.get_by_id(3):
            r = (
                initTabs
                | {"存续信息": currentInfo(deal), "清算信息": clearInfo(deal)}
                | docTab
                | vipTab
            )
            dt = "清算信息"
        else:
            raise RuntimeError(
                f"Failed to load {deal_id} deal with invalid stage {deal.stage}"
            )
        return HTMLResponse(
            base_page(
                dealTemplate
                + [
                    hr,
                ]
                + [mkTabs(r, activeTab=dt)]
            )
        )


@app.get("/series/")
def seriesListView():
    with db:
        fieldsOfDeal = [
            Deal.stage,
            Deal.period,
            Deal.shortNameKey,
            Deal.seriesName,
            Deal.closingDate,
            Deal.poolType,
            Deal.poolSubType,
        ]
        deals = list(
            Deal.select(*fieldsOfDeal)
            .where(Deal.stage.not_in([-1, -2]), Deal.poolType.in_(["NPL","AUTO"]))
            .order_by(Deal.stage.asc(), Deal.closingDate.desc())
            .dicts()
        )
        seriesGrp = tz.groupby("seriesName", deals)
        vvv = tz.valmap(lambda xs: tz.valmap(len, tz.groupby("stage", xs)), seriesGrp)
        vvv &= lens.Values().modify(remapMapKey(statusMap))
        vvv &= lens.Values().modify(
            lambda m: {"预发行": 0, "存续中": 0, "已清算": 0} | m
        )
        vvv &= lens.Keys().modify(lambda k: genLink(k, ["series", k]))
        r = [
            # buildPath([("首页","/index"),("系列",f"/series/")])
            h3(".title .is-4")["系列一览"],
            dictToTable_KeyAsRow(vvv, cls={"class": modDataTable}),
        ]
        return HTMLResponse(base_page(r))


@app.get("/series/{series}/")
def seriesView(series):
    with db:
        transBnd = remapMapKey(dealFieldMap)
        tranAc = transMap(assetClassMap)

        deals = list(
            Deal.select()
            .where(Deal.seriesName == series, Deal.stage > 0, Deal.poolType.in_(["NPL","AUTO"]))
            .order_by(Deal.stage.asc(), Deal.closingDate.desc())
            .dicts()
        )
        dealWithLink = (
            deals
            & lens.Each().modify(
                lambda z: tz.assoc(
                    z, "shortNameKey", genLink(z["shortNameKey"], ["deal", z["dealid"]])
                )
            )
            & lens.Each().modify(
                lambda z: tz.dissoc(
                    z,
                    "data",
                    "fullName",
                    "seriesName",
                    "shortName",
                    "dealid",
                    "bookDate",
                )
            )
            & lens.Each()["poolType"].modify(tranAc)
            & lens.Each()["poolSubType"].modify(transSubAc)
            & lens.Each()["stage"].modify(lambda z: statusMap[z])
            & lens.Each().modify(transBnd)
        )

        r = [
            h3(".title .is-4")[f"{series}"],
            dictListToTable(dealWithLink, cls={"class": modDataTable}),
        ]
        return HTMLResponse(base_page(r))


@app.post("/bondScreen/")
async def bondScreenFn(request: Request):
    # read raw form-encoded body like: "faceValueMin=0&faceValueMax=100&rateMin=0&rateMax=100"
    body = await request.body()
    qs = body.decode("utf-8")
    raw = parse_qs(qs, keep_blank_values=True)

    # normalize params: single-value -> string, multi-value -> list
    params = {k: (v if len(v) > 1 else v[0]) for k, v in raw.items()}

    def to_float(key, default=0.0):
        try:
            return float(params.get(key, default))
        except Exception:
            return default

    faceValueMin = to_float("faceValueMin", 0)/100
    faceValueMax = to_float("faceValueMax", 100)/100
    rateMin = to_float("rateMin", 0)/100
    rateMax = to_float("rateMax", 100)/100

    # checkbox may come as "on" or be absent
    nullCpn = params.get("nullCpn", "")
    nullCpn = str(nullCpn).lower() in ("on", "true", "1")
    nullCpnFlag = " or \"curRate\" is null" if nullCpn else ""
    
    print("nullCpnFlag", nullCpnFlag)

    # rating may be single value or list
    ratings = params.get("rating", [])
    if isinstance(ratings, str):
        ratings = [ratings]

    
    
    r = q_with_m('v_bonds',['sn','shortNameKey','code','curFactor','curBalance','curRate','issueDate','isin','deal_id']
                ,f" \"curFactor\" between {faceValueMin} and {faceValueMax}"
                 f" and ( \"curRate\" between {rateMin} and {rateMax} {nullCpnFlag} )"
                 f" and \"curBalance\" > 0")
    
    r &= lens.Each()['curFactor'].modify(lambda x: round(x * 100, 2))
    r &= lens.Each()['curRate'].modify(lambda x: f"{round(x * 100, 2)}%" if x is not None else "/")
    r &= lens.Each()['curBalance'].modify(toWan)
    r &= lens.Each()['isin'].modify(lambda z: z if z is not None else "/")
    r &= lens.Each().modify(lambda m: tz.assoc(m, 'shortNameKey', genLink(m['shortNameKey'], ["deal", m['deal_id']])))
    r &= lens.Each().modify(lambda m: tz.dissoc(m, 'deal_id'))
    r &= lens.Each().modify(transBnd)
    
    t = dictListToTable(r,cls={"class": modDataTable})
    
    return HTMLResponse(t)


@app.get("/bondScreen/")
def bondScreenView():
    # vRate = q_with_m("s_bond_cur_range",[])
    def bondFilterForm():
        ratingListOpts = div(".field")[
            label(".label")["选择评级"],
            div(".control")[
                ul[
                    [
                        li[
                            label[
                                input(type="checkbox", name="rating", value=rating),
                                span[f" {rating}"],
                            ]
                        ]
                        for rating in ratingList
                    ]
                ],
            ],
        ]
        assetClasses = ["NPL", "AUTO", "CLO", "CONSUMER", "RMBS", "SBL"]
        assetClassesOpts = div(".field")[
            label(".label")["资产类别"],
            div(".control")[
                ul[
                    [
                        li[
                            label[
                                input(type="checkbox", name="assetClass", value=ac),
                                span[f" {ac}"],
                            ]
                        ]
                        for ac in assetClasses
                    ]
                ],
            ],
        ]
        seniority = ["Senior", "Mezz", "Junior"]
        seniorityOpts = div(".field")[
            label(".label")["优先级"],
            div(".control")[
                ul[
                    [
                        li[
                            label[
                                input(type="checkbox", name="seniority", value=s),
                                span[f" {s}"],
                            ]
                        ]
                        for s in seniority
                    ]
                ],
            ],
        ]

        def inputTemplate(
            x_model: str,
            value: str = "0",
            minv: str = "0",
            maxv: str = "100",
            id: str | None = None,
            cls: str = "input is-small",
            style: str = "width: 6rem;",
            type_: str = "text",
        ):
            """
            Helper to render a div(".control")[ input({...}) ] block.
            x_model: Alpine.js model name (e.g. "faceValueMax")
            """
            if id is not None:
                safe = (
                    x_model.replace('"', "")
                    .replace("'", "")
                    .replace(".", "-")
                    .replace(" ", "-")
                )
                id = f"{safe}"
                attrs = {
                    "type": type_,
                    "name": x_model,
                    "x-model": x_model,
                    "min": str(minv),
                    "max": str(maxv),
                    "value": str(value),
                    "id": id,
                    "class": cls,
                    "style": style,
                }
                return div(".control")[input(attrs)]

        return form(
            "#bond-filter-form",
            {
                "x-data": """{
                            liveSearch: false,
                            faceValueMin: 0,
                            faceValueMax: 100,
                            rateMin: 0,
                            rateMax: 100,
                            activeBond: true,
                            nullCpn: false,
                            }"""
                
                # ,"hx-include": "this input"
            },
        )[
            div(
                {
                    "style": "display:flex;flex-wrap:wrap;gap:1rem;align-items:flex-start;"
                }
            )[
                div(
                    ".field.is-horizontal", {"style": "flex:0 0 auto;min-width:220px;"}
                )[
                    div(".field-label.is-normal")[label(".label")["面值"]],
                    div(".field-body")[
                        div(".field.is-grouped.is-horizontal")[
                            inputTemplate(
                                "faceValueMin",
                                value="0",
                                minv="0",
                                maxv="100",
                                id="face-value-min"
                            ),
                            inputTemplate(
                                "faceValueMax",
                                value="100",
                                minv="0",
                                maxv="100",
                                id="face-value-max",
                            ),
                        ]
                    ],
                ],
                div(
                    ".field.is-horizontal", {"style": "flex:0 0 auto;min-width:220px;"}
                )[
                    div(".field-label.is-normal")[label(".label")["利率"]],
                    div(".field-body")[
                        div(".field.is-grouped.is-horizontal")[
                            # wrap inputs with a tooltip container (Bulma 'has-tooltip' + data-tooltip)
                            div(".has-tooltip", {"data-tooltip": "利率下限 (%)，3.5% 输入 3.5 "})[
                                inputTemplate(
                                    "rateMin",
                                    value="0",
                                    minv="0",
                                    maxv="100",
                                    id="rate-min",
                                )
                            ],
                            div(".has-tooltip", {"data-tooltip": "利率上限 (%)，3.5% 输入 3.5"})[
                                inputTemplate(
                                    "rateMax",
                                    value="100",
                                    minv="0",
                                    maxv="100",
                                    id="rate-max",
                                )
                            ],
                        ]
                    ],
                ],
                div(
                    ".field.is-horizontal", {"style": "flex:0 0 auto;min-width:160px;"}
                )[
                    div(".field-label.is-normal")[label(".label")["*"]],
                    div(".field-body.is-grouped")[
                        div(".has-tooltip.field.is-grouped.is-horizontal",{"data-tooltip": "是否包含无利率债券"})[
                            label(".checkbox")[
                                input(
                                    {
                                        "type": "checkbox",
                                        "x-model": "nullCpn",
                                        "id": "null-cpn-toggle",
                                        "name": "nullCpn",
                                    }
                                ),
                                span["零息式"],
                            ]
                            #,label(".checkbox")[
                            #    input(
                            #        {
                            #            "type": "checkbox",
                            #            "x-model": "liveSearch",
                            #            "id": "live-search-toggle",
                            #        }
                            #    ),
                            #    span[" live "],
                            #],
                        ],
                        div(".control")[
                            button(
                                {
                                    "type": "button",
                                    "x-show": "!liveSearch",
                                    # "@click": "search",
                                    "class": "button is-primary is-small",
                                    "hx-post": "/bondScreen/",
                                    "hx-target": "#bond-search-result",
                                    "hx-include": "#bond-filter-form",
                                    "type": "submit",
                                    # "hx-include": "inherit",
                                    "hx-swap": "innerHTML",
                                }
                            )["Search"]
                        ],
                    ],
                ],
            ]
        ]

    with db:
        activeBond = []
        r = [
            h3(".title.is-4")["债券筛选"],
            div(".box")[bondFilterForm(), hr, div("#bond-search-result")["<Result>"]],
        ]
        return HTMLResponse(base_page(r))

@app.get("/api/")
def apiPage():
    r = [
        p[
            h3(".title.is-4")["🔒API介绍"],
            div(".box.content")[
                p["账户开通后可使用API进行数据查询和模型的测算调用"],
                p["用户可以通过 Python包 ",em["absbox"], " 进行操作。"],
            ]
        ]
    ]
    
    return HTMLResponse(base_page(r))


@app.get("/trading/{as_of_date}/")
def trading_view(as_of_date):
    with db:
        prices = getTradingPrice(as_of_date)
        pricingData = tz.pipe(
            prices,
            lambda xs: sorted(xs, key=lambda x: x["date"], reverse=True),
            lambda xs: [
                subMap(
                    x,
                    [
                        "date",
                        "债券代码",
                        "简短",
                        "ISIN",
                        "cleanPrice",
                        "dirtyPrice",
                        "tradeCount",
                        "settleAmount",
                    ],
                    default="",
                )
                for x in xs
            ],
            lambda xs: xs & lens.Each()["settleAmount"].modify(lambda y: y / 10000),
        )

        bondSecCode = list(tz.pluck("债券代码", pricingData))

        summaryData = (
            BondID.select(
                BondID.bondID,
                Bond.seniority,
                Deal.poolType,
                Deal.poolSubType,
                Deal.seriesName,
            )
            .join(Bond)
            .join(Deal)
            .where(BondID.bondID.in_(bondSecCode))
            .dicts()
        )

        # totalTradingAmt =

        patchedData = tz.pipe(
            summaryData,
            lambda x: {_["bondID"]: _ for _ in x},
            lambda m: [(_ | m[_["债券代码"]]) for _ in pricingData],
            list,
        )

        category = ["seniority", "poolType", "seriesName"]

        def sumup(xs):
            return tz.merge_with(
                sum, [subMap(x, ["tradeCount", "settleAmount"]) for x in xs]
            )

        # OrderedDict(sorted(ship.items())
        def sortMapByVol(m: dict):
            # console.print("sorting dict", m.items())
            return OrderedDict(
                sorted(m.items(), key=lambda x: x[1]["settleAmount"], reverse=True)
            )

        summaryTables = tz.pipe(
            [
                (cat, tz.groupby(cat, patchedData) & lens.Values().modify(sumup))
                for cat in category
            ],
            lambda xs: [(cat, sortMapByVol(d)) for (cat, d) in xs],
            lambda tbls: [
                dictToTable_KeyAsRow(tData, tName, {"class": modDataTable})
                for (tName, tData) in tbls
            ],
        )

        # console.print(groupBySeniority,groupByPool,groupBySeries)
        pricingTable = tableWithHeader(
            "交易价格", tz.merge_with(tz.identity, pricingData), {"class": modDataTable}
        )
        return HTMLResponse(base_page([summaryTables, pricingTable]))


@app.get("/")
def root():
    with db:
        return index()


@app.get("/index")
def index():
    return RedirectResponse(url="/preClosing")


@app.get("/preClosing")
def preClosing():
    today = date.today()
    daysAfterClosing = 14
    fourteen_days_ago = today - timedelta(days=daysAfterClosing)
    
    with db:
        
        preClosingHeader = [
            Deal.dealid,
            Deal.fullName,
            Deal.shortNameKey,
            Deal.seriesName,
            Deal.poolType,
            Deal.poolSubType,
            Deal.closingDate,
            Deal.bookDate,
            Deal.data,
        ]
        
        preClosingDeals = tz.pipe(
            list(
                Deal.select(*preClosingHeader)
                .where(Deal.stage == Stage.get_by_id(1)
                        , Deal.poolType.in_(["NPL","AUTO"])
                        , (Deal.bookDate >= fourteen_days_ago) | Deal.bookDate.is_null(True))
                .order_by(Deal.bookDate,Deal.dealid)
                .dicts()
            ),
            lambda xs: xs
            & lens.Each()["seriesName"].modify(lambda z: genLink(z, ["series", z])),
            lambda xs: xs
            & lens.Each().modify(
                lambda z: tz.assoc(z, "_status", calculateDealStatus(z))
            ),
            lambda xs: xs
            & lens.Each().modify(
                lambda z: tz.assoc(
                    z,
                    "status",
                    span(
                        {
                            "class": "has-tooltip",
                            "data-tooltip": f"{z['_status'][1]}",
                            "style": f"background-color:{statusMapClass[z['_status'][0]]};",
                        }
                    )[z["_status"][0]],
                )
            )
            & lens.Each()["poolType"].modify(tranAc)
            & lens.Each()["poolSubType"]
            .Filter(lambda x: x is not None)
            .modify(transSubAc)
            & lens.Each()["poolSubType"].Filter(lambda x: x is None).set("/"),
            lambda xs: xs
            & lens.Each().modify(
                lambda z: tz.assoc(
                    z, "shortNameKey", genLink(z["shortNameKey"], ["deal", z["dealid"]]) if (z['data'] is not None and 'issuePlan' in z['data'] and 'preClosing' in z['data']) else z["shortNameKey"]
                )
            ),
            lambda xs: xs
            & lens.Each()
            .modify(
                lambda y: tz.assoc(
                    y,
                    "拟簿记日",
                    f"{y['data']['issuePlan']['bookDate']}" if y['data'] is not None and 'issuePlan' in y['data'] and y['data']['issuePlan']['bookDate'] is not None else "/"
                )
            ),  
            lambda xs: xs
            & lens.Each()
            .modify(
                lambda y: tz.assoc(
                    y,
                    "距簿记日",
                    (
                        f"{(parse(y['拟簿记日']).date()-today).days}天" if y['拟簿记日'] != "/" else "/"
                        if (y["status"] != "已设立")
                        else "/"
                    ),
                )
            ),            
            lambda xs: xs
            & lens.Each().modify(
                lambda z: tz.dissoc(z, "data", "fullName", "dealid",)
            )
        )

        dealByStatus = tz.groupby(lambda x: x['_status'][0]=='已设立', preClosingDeals)

        r = [
            mkTabs({"待成立":tableWithHeader(
                        span(),
                        tz.merge_with(tz.identity, dealByStatus[False]),
                        {"class": modDataTable + " is-fullwidth"},
                        headerMapping={
                            "shortNameKey": "产品简称",
                            "status": "状态",
                            "拟簿记日": "拟簿记日",
                            "距簿记日":"距拟簿记日",
                            "poolType": "资产分类",
                            "poolSubType": "资产二级分类",
                            "seriesName": "产品系列",
                        },
                        ) if False in dealByStatus else div["暂无待成立产品"]
                    ,"新成立": tableWithHeader(
                            span(),
                            tz.merge_with(tz.identity, dealByStatus[True]),
                            {"class": modDataTable + " is-fullwidth"},
                            headerMapping={
                                "shortNameKey": "产品简称",
                                "status": "状态",
                                "bookDate": "簿记日",
                                "poolType": "资产分类",
                                "poolSubType": "资产二级分类",
                                "seriesName": "产品系列",
                            },
                        ) if True in dealByStatus else div["近14天暂无新成立产品"]
                }
                , activeTab="待成立"    
            ),
        ]

        return HTMLResponse(base_page(r))


@app.get("/reader")
def reader():
    with db:
        r = [
            # buildPath([("首页","/index"),("文件速读","/reader")])
            h3(".title .is-4")["文件速读"],
            info("提供仅文字版本的交易文件查阅。"),
            div[
                form(
                    {
                        "hx-post": "/docs/search",
                        "hx-encoding": "application/x-www-form-urlencoded",
                        "hx-target": "#reader-result",
                        "hx-swap": "innerHTML",
                        "hx-indicator": "#reader-indicator",
                        "class": "box",
                    }
                )[
                    div(".field.is-grouped")[
                        div(".control.is-expanded")[
                            input(
                                {
                                    "type": "text",
                                    "class": "input",
                                    "placeholder": "关键字",
                                    "name": "keyword",
                                }
                            )
                        ],
                        div(".control")[
                            input(
                                {
                                    "type": "submit",
                                    "value": "查询",
                                    "class": "button is-primary",
                                }
                            )
                        ],
                    ]
                ],
                div({"class": "box", "style": "min-height:4rem;"})[
                    div({"id": "reader-indicator", "style": "display:none;"})[
                        "查询中..."
                    ],
                    div({"id": "reader-result", "class": "content mt-2"})[""],
                ],
            ],
        ]

        return HTMLResponse(base_page(r))


@app.get("/market")
def market():
    with db:
        opts = []
        
        r = []
        
        return HTMLResponse(base_page(r))


@app.post("/docs/search")
def docSearch(keyword: str = Form(...)):
    # Process the extracted keyword
    # For example, perform a search or return a response

    # buildFileViewer
    with db:
        fsFound = getMdFilesByKey(keyword)
        if fsFound:
            d = {"搜索结果": [{"key": k[0]} for k in fsFound]}
            # console.print(d)
            return tz.pipe(buildFileViewer(d), HTMLResponse)
        else:
            return HTMLResponse(div["未找到相关文件。"])

@app.get("/health")
def health():
    def peekNow():
        rpts = list(HealthCheck.select().order_by(HealthCheck.date.desc()).dicts().limit(1))
        rpt = rpts[0]
        return rpt
    with db:
        return peekNow()
        #if productionFlag:
        #    return HTMLResponse("In production: No healthcheck implemented")
        #else:
        #    return HTMLResponse("Not OK")
        

@app.get("/deal/{deal_id}/debug")
def dealinfoDebug(deal_id):
    with db:
        if productionFlag:
            return RedirectResponse(url=f"/deal/{deal_id}/")

        deal = Deal.get(Deal.dealid == deal_id)

        ratingDocs = tz.pipe(
            list(
                RatingReport.select(
                    RatingReport.id,
                    RatingReport.agency,
                    Location.id,
                    Location.key,
                    RatingReport.data,
                )
                .join(Location)
                .where(RatingReport.deal == deal)
                .dicts()
            ),
            lambda xs: [tz.assoc(x, "hasMd", hasMarkdown(x["key"])) for x in xs],
        )
        issuanceDocs = list(
            IssueFiles.select(Location.id, Location.key)
            .join(Location)
            .where(IssueFiles.deal == deal)
            .dicts()
        )
        trusteeRpts = list(
            TrusteeReport.select(Location.id, Location.key)
            .join(Location)
            .where(TrusteeReport.deal == deal)
            .dicts()
        )
        issuePlans = list(
            IssuePlan.select(Location.id, Location.key, IssuePlan.data)
            .join(Location)
            .where(IssuePlan.deal == deal)
            .dicts()
        )
        pricingRpts = list(
            PricingReport.select(Location.id, Location.key)
            .join(Location)
            .where(PricingReport.deal == deal)
            .dicts()
        )
        clearRpts = list(
            ClearReport.select(Location.id, Location.key, ClearReport.data)
            .join(Location)
            .where(ClearReport.deal == deal)
            .dicts()
        )

        rFiles = {
            "评级报告": ratingDocs,
            "发行文件": issuanceDocs,
            "发行办法": issuePlans,
            "受托文件": trusteeRpts,
            "定价文件": pricingRpts,
            "清算文件": clearRpts,
        }
        bonds = [b for b in deal.bonds.dicts()]
        rawFiles = getFilesByKey(deal.shortNameKey)
        console.print(rawFiles)
        r = [
            h2[deal.dealid, "/", deal.fullName],
            h3["相关文件"],
            [
                dictListToTable(v, cls={"class": modDataTable}, header=k)
                for k, v in rFiles.items()
            ],
            h3["bonds"],
            dictListToTable(bonds),
            h3["deal data"],
            div[pre[json.dumps(deal.data, ensure_ascii=False)]]
            # ,h3["pricing"]
            # ,div[pre[json.dumps(pricingRpt.data,ensure_ascii=False)]] if pricingRpt else div[""]
            ,
            h3["raw files"],
            div[(li[_[0]] for _ in rawFiles)],
        ]

        return HTMLResponse(base_page(r))


@app.get("/file/{fn}/md")
@lru_cache(maxsize=256)
def showMdFile(fn):
    with db:

        def addClass(y):
            return tz.thread_last(
                re.sub(
                    r"<table>",
                    "<table class='table is-bordered is-striped is-hoverable'>",
                    y,
                ),
                (re.sub, r"<p>", "<p class='is-size-6'>"),
                (re.sub, r"<h1>", "<h1 class='is-size-6'>"),
            )

        if fn == "null" or fn == "请选择文件":
            return span[""]
        try:
            r = getMuMd(fn)
        except Exception as e:
            return span["文件不存在"]
        return tz.pipe(
            r
            # remove images
            # \n\n![](images/b25a345928bb282461aa3c973156acb8d64adb981145a1b6bb59df3f92e46cf1.jpg)
            ,
            lambda x: re.sub(r"\n\!\[\]\(images/\S+\.jpg\)", "", x),
            mistune.html,
            lambda x: re.sub(r"\n", "", x),
            addClass,
            # , lambda x: tz.do(console.print, x)
        )


class SearchInput(BaseModel):
    searchKey: str


@app.post("/search")
def handleSearch(searchKey: str = Form(...)):
    if not searchKey:
        return HTMLResponse(div["请输入搜索关键词"])
    with db:
        return HTMLResponse(div["DDD"])


@app.get("/not-found/{key}")
def notFound(key: str):
    return HTMLResponse(
        base_page([div[f"未找到相关债券代码/债券简称/产品简称: < {key} > "]])
    )


@app.post("/quick-search")
def handleQuickSearch(searchKey: str = Form(...)):
    def rtn(dealStr):
        return JSONResponse(
            content={"message": "Success"}, headers={"HX-Redirect": f"/deal/{dealStr}"}
        )

    sk = searchKey.strip()
    if r := BondID.get_or_none(BondID.bondID == sk):
        d = r.bond.deal
        return rtn(d.dealid)
    if r := Deal.get_or_none(Deal.dealid == sk):
        return rtn(r.dealid)
    if r := Deal.get_or_none(Deal.shortNameKey == sk):
        return rtn(r.dealid)

    return JSONResponse(
        content={"message": "Success"},
        headers={"HX-Redirect": f"/not-found/{searchKey}"},
    )
