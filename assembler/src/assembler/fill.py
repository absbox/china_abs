"""Fill deal data from the ``os_fill_*`` reporting views.

This is the port of ``flow/dags/datasource/fill_data_fun.py``.  Every public
step reads one reporting view (or ``os_llm_deal_waterfall``) and writes the
result into the shared :mod:`china_model` tables.  The two steps that need a
model (``fillWaterfall`` and ``calibrateTheName``) call into
:mod:`assembler.llm`.
"""

from __future__ import annotations

import json
import logging
import re
import traceback
from collections import Counter
from functools import partial
from typing import Any, Iterable, Optional

import dateparser as dp
import toolz as tz
from lenses import lens
from rich.console import Console

from china_model import (
    Bond,
    BondID,
    BondIDType,
    BondPayments,
    BondSeniorityType,
    ClearReport,
    Deal,
    InternalDealMeta,
    IssuePlan,
    Location,
    PreClosingBond,
    PricingReport,
    RatingReport,
    TradingPrice,
    TrusteeReport,
)
from .db import q_with_m
from .llm import ask, merge_two_waterfalls
from .util import (
    findFirstByFn,
    getValByKeySeq,
    getValByPs,
    isSenior,
    mapKey,
    nToZ,
    shortNameToBondName,
    subMap,
    tblListToMap,
    tryToMatch,
)

console = Console()


def pickByLocationKey(rpts):
    """
    针对存在修正改正报告的情况，按照文件名选择修正后的报告
    """
    if len(rpts) == 1:
        return rpts[0]

    rs = [r"更正", r"更新", r"以此为准"]
    ex = [r"\(英文版\)", r"（英文版）", r"英文版\.pdf"]

    rpts = list(filter(lambda x: not tryToMatch(x.loc.key, ex, capture=False), rpts))
    if len(rpts) == 1:
        return rpts[0]

    for rpt in rpts:
        if tryToMatch(rpt.loc.key, rs, capture=False):
            return rpt

    raise RuntimeError(f"failed to find  {[ (z,z.loc,z.loc.key) for z in rpts]} ")


def fillToData(deal: Deal, k, v):
    if deal.data is None:
        deal.data = {}
    deal.data = tz.assoc(deal.data, k, v)
    r = deal.save()
    print(f"successfull write into {deal.dealid} {r}")


def fillToDataByPath(deal: Deal, p, v):
    if deal.data is None:
        deal.data = {}
    deal.data = tz.assoc_in(deal.data, p, v)
    r = deal.save()
    print(f"successfull write into {deal.dealid} {r}")


def pricingReportInit(pricingRpt, ow=False, models=['qwen-flash', 'ds', 'qwen-long']):
    """
    move data of pricing data into deal object
    """
    for model in models:
        if (prData := tz.get_in([model, 'PRICING_ANN'], pricingRpt.data)):
            bondData = prData['bonds']
            deal = pricingRpt.deal
            fillToData(deal, 'pricing', prData)

            issueDates = bondData & lens.Each()['ISSUE_DATE'].collect()
            assert len(set(issueDates)) == 1, f"issue date should be same"
            deal.closingDate = dp.parse(issueDates[0])
            print(f"<Init Pricing Report>: success with model: {model}")
            return


def toFillPricing():
    """
    Query the view:os_fill_pricing_data
    Pricing.Data -> Deal.Data
    """
    r = q_with_m("os_fill_pricing_data", ["pricingRptID"])
    prIDs = tz.pluck('pricingRptID', r)
    prs = [PricingReport.get_by_id(_) for _ in prIDs]
    for pr in prs:
        logging.info(f"[fillPricing] fill with report {pr.deal}/{pr}")
        pricingReportInit(pr)

    toFillBond()


def loadPoolDataFromTruestee(tr):
    """
    pull period data from trustee report
    and insert to deal data object
    """
    deal = tr.deal
    period = tr.period
    assert period, f"{tr} should have a valid period but got {period}"

    pData = tr.data
    assert pData, f"{tr} should have a valid data but got {pData}"

    d = deal.data if (deal.data is not None) else {}

    pIncome = pData & lens['qwen-flash']['TRUSTEE_NPL_RPT']['inflow']['ProcessIncome'].get()
    lIncome = pData & lens['qwen-flash']['TRUSTEE_NPL_RPT']['inflow']['LiquidatedIncome'].get()
    totalIncome = pData & lens['qwen-flash']['TRUSTEE_NPL_RPT']['inflow']['PoolInflow'].get()
    pBal = pData & lens['qwen-flash']['TRUSTEE_NPL_RPT']['pool']['EndPoolBalance'].get()
    pAsscetCount = pData & lens['qwen-flash']['TRUSTEE_NPL_RPT']['pool']['EndAssetCount'].get()
    pCollectionB, pCollectionE = pData & lens['qwen-flash']['TRUSTEE_NPL_RPT']['date']['collection'].get()

    match (pIncome, lIncome, totalIncome):
        case (None, None, _) | (0, 0, _) if totalIncome is not None:
            periodData = {
                'EndPoolBalance': float(nToZ(pBal)),
                'EndAssetCount': int(nToZ(pAsscetCount)),
                'RecoveryByProcess': None,
                'RecoveryByLiquidated': None,
                'Recovery': float(totalIncome),
                'CollectionPeriodBegin': pCollectionB,
                'CollectionPeriodEnd': pCollectionE,
            }
        case _:
            periodData = {
                'EndPoolBalance': float(nToZ(pBal)),
                'EndAssetCount': int(nToZ(pAsscetCount)),
                'RecoveryByProcess': float(nToZ(pIncome)),
                'RecoveryByLiquidated': float(nToZ(lIncome)),
                'Recovery': nToZ(pIncome) + nToZ(lIncome),
                'CollectionPeriodBegin': pCollectionB,
                'CollectionPeriodEnd': pCollectionE,
            }

    deal.data = tz.assoc_in(d, ['current', 'trustee', period], periodData)
    deal.save()


def fillPoolPerfNPL():
    """load outstanding pool perf data to deal obj NPL"""
    rs = q_with_m('os_fill_trusteereport_pool_data_npl', ['id'])
    ids = tz.pluck('id', rs)
    for i in ids:
        loadPoolDataFromTruestee(TrusteeReport.get_by_id(i))


def fillPoolPerfAuto():
    def loadDataFromTruestee(tr):
        deal = tr.deal
        period = tr.period
        assert period, f"{tr} should have a valid period but got {period}"

        pData = tr.data
        assert pData, f"{tr} should have a valid data but got {pData}"

        d = deal.data if (deal.data is not None) else {}

        pIncome = pData & lens['qwen-flash']['TRUSTEE_NPL_RPT']['inflow']['ProcessIncome'].get()
        lIncome = pData & lens['qwen-flash']['TRUSTEE_NPL_RPT']['inflow']['LiquidatedIncome'].get()
        totalIncome = pData & lens['qwen-flash']['TRUSTEE_NPL_RPT']['inflow']['PoolInflow'].get()
        pBal = pData & lens['qwen-flash']['TRUSTEE_NPL_RPT']['pool']['EndPoolBalance'].get()
        pAsscetCount = pData & lens['qwen-flash']['TRUSTEE_NPL_RPT']['pool']['EndAssetCount'].get()
        pCollectionB, pCollectionE = pData & lens['qwen-flash']['TRUSTEE_NPL_RPT']['date']['collection'].get()

        periodData = {
            'EndPoolBalance': float(nToZ(pBal)),
            'EndAssetCount': int(nToZ(pAsscetCount)),
            'RecoveryByProcess': None,
            'RecoveryByLiquidated': None,
            'Recovery': float(totalIncome),
            'CollectionPeriodBegin': pCollectionB,
            'CollectionPeriodEnd': pCollectionE,
        }

        deal.data = tz.assoc_in(d, ['current', 'trustee', period], periodData)
        deal.save()

    rs = q_with_m('os_fill_trusteereport_pool_data_npl', ['id'])
    ids = tz.pluck('id', rs)
    for i in ids:
        loadDataFromTruestee(TrusteeReport.get_by_id(i))


def fillIsin():
    xrs = q_with_m('os_fill_isin_code', ['isinCode', 'bond_code', 'bond_id'])
    print(f'total ISIN # to fill {len(xrs)}')
    for x in xrs:
        bid, f = BondID.get_or_create(
            idType=BondIDType.get_by_id("ISIN"),
            bond=Bond.get_by_id(x['bond_id']),
            bondID=x['isinCode'],
        )


def initBonds(deal):
    """
    Init bonds objects from deal obj
    """
    assert 'pricing' in deal.data, "Deal data should have 'pricing'"
    assert 'bonds' in deal.data['pricing'], "Pricing should have 'bonds'"

    bondData = deal.data['pricing']['bonds']
    issueDatesVals = bondData & lens.Each()['ISSUE_DATE'].collect()

    if len(set(issueDatesVals)) == 2 and (None in issueDatesVals):
        issueDate = [x for x in issueDatesVals if x is not None][0]
    elif len(set(issueDatesVals)) == 1 and (None not in issueDatesVals):
        issueDate = issueDatesVals[0]
    elif len(set(issueDatesVals)) == 1 and (None in issueDatesVals):
        issueDate = deal.data['issuePlan']['closingDate']
    else:
        raise RuntimeError(f"Failed to find issue date from {deal.dealid} {issueDatesVals}")

    for bData in bondData:
        try:
            b, f = Bond.get_or_create(
                name=shortNameToBondName(bData['SHORTNAME']),
                deal=deal,
                curRate=bData['ISSUE_COUPON'],
                curBalance=bData['ISSUE_AMT'],
                issueDate=issueDate,
                issuePrice=bData['ISSUE_PRICE'],
                issueFace=bData['ISSUE_AMT'],
                issueRate=bData['ISSUE_COUPON'],
                expectedMaturity=bData['EXPECT_MATURITY'],
                seniority=BondSeniorityType.get_by_id('senior') if isSenior(bData['SHORTNAME']) else BondSeniorityType.get_by_id('junior'),
            )
        except Exception as e:
            print(e)
            continue
        if f:
            b.save()

        bid, f = BondID.get_or_create(
            bondID=bData['CODE'],
            idType=BondIDType.get_by_id("债券代码"),
            bond=b,
        )
        if f:
            bid.save()

        bid, f = BondID.get_or_create(
            bondID=bData['SHORTNAME'],
            idType=BondIDType.get_by_id("简称"),
            bond=b,
        )
        if f:
            bid.save()

    # TODO need to add junior tranche which not in pricing report
    # issuePlanBonds = deal.data['issuePlan']['bonds']
    # if len(bondData)+1==len(issuePlanBonds):
    #     juniorBond = issuePlanBonds[-1]
    #     b,f = Bond.get_or_create(
    #         name =  juniorBond['债券名称']
    #         ,deal = deal
    #         ,curRate = None
    #         ,curBalance = juniorBond['发行规模']
    #         ,issueDate = issueDate
    #         ,issuePrice = None
    #         ,issueFace = juniorBond['发行规模']
    #         ,issueRate = None
    #         ,expectedMaturity = None
    #         ,seniority = BondSeniorityType.get_by_id('junior')
    #     )
    #     b.save()


def toFillBond():
    """
    Query the view : "os_fill_bond"
    Deal.Data -> Bond
    """
    r = q_with_m("os_fill_bond", ["dealid"])
    dealIDs = tz.pluck('dealid', r)
    for d in dealIDs:
        initBonds(Deal.get_by_id(d))


def insertBondPaymentsByReport(rpt, model='qwen-flash'):
    """
    input of trustee report id
    fill the bond payment from the trustee report
    """
    r = rpt
    deal = rpt.deal
    insertingPeriod = r.period
    assert insertingPeriod is not None, f"report period shouldn't be None {rpt.id}"

    bData = r.data[model]['TRUSTEE_NPL_RPT']['bonds']
    pDateStr = r.data[model]['TRUSTEE_NPL_RPT']['date']['payDate']
    assert pDateStr is not None, f"payment date shouln't be empty"
    pDate = dp.parse(pDateStr) if isinstance(pDateStr, str) else dp.parse(pDateStr[0]),
    print(f"inserting with date {pDateStr} {pDate}")

    for bondid, bdata in bData.items():
        print(f"insert bond id {bondid}")
        bondInstant = BondID.get(BondID.bondID == bondid).bond
        b, f = BondPayments.get_or_create(
            bond=bondInstant,
            paymentDate=pDate,
            updatePeriod=insertingPeriod,
        )
        if (bdata['repay'] is not None) and (bdata['repay'] <= 100.0) and (bdata['repay'] != 0):
            assert deal.dealid[2:-2] in ["HUIYUAN", "JIAOCHENG"], f"100.0 issue only restricted to HUIYUAN"
            # assert 'ds' in r.data, "the report shall has 'ds' field "
            model_path = 'ds' if 'ds' in r.data else 'qwen-flash'
            lastPeriod = r.period - 1
            begBal = BondPayments.get(BondPayments.bond == bondInstant, BondPayments.updatePeriod == lastPeriod).currentBalance if lastPeriod > 0 else bondInstant.issueFace

            bDataDS = r.data[model_path]['TRUSTEE_NPL_RPT']['bonds'][bondid]
            b.principal = bDataDS['repay']
            b.currentBalance = float(begBal) - b.principal
        else:
            b.currentBalance = bdata['endBalance']
            b.principal = bdata['repay']

        b.interest = bdata['interest']
        b.interestYield = bdata.get('JuniorYield', None)
        b.currentRate = bdata['rate']
        b.updatePeriod = insertingPeriod
        print(f"saving {b}")
        b.save()


def insertBondPaymentsByReportAuto(rpt, model='qwen-flash'):
    """
    insert bond payment for auto reports
    """
    r = rpt
    deal = rpt.deal
    insertingPeriod = r.period

    bData = r.data[model]['TRUSTEE_AUTO_RPT']['bonds']
    pDateStr = r.data[model]['TRUSTEE_AUTO_RPT']['date']['payDate']
    assert pDateStr is not None, f"payment date shouln't be empty"
    pDate = dp.parse(pDateStr) if isinstance(pDateStr, str) else dp.parse(pDateStr[0]),
    print(f"inserting with date {pDateStr} {pDate}")
    dealMeta = InternalDealMeta.get_or_none(InternalDealMeta.deal == deal)
    if not dealMeta:
        print(f"failed to find bond mapping for {deal}")
        return

    bondMapping = dealMeta.data['bondMapping'] if 'bondMapping' in dealMeta.data else None

    assert bondMapping is not None, f"failed to find the bond mapping {deal}"

    for bName, bData in bData.items():
        assert bName in bondMapping, f"deal: {deal} period: {insertingPeriod} failed to find {bName} in {bondMapping}"
        assert bondMapping[bName], f"[bond mapping] is None,{bondMapping},{bName}"
        bond = Bond.get_by_id(bondMapping[bName]['id'])
        b, f = BondPayments.get_or_create(
            bond=bond,
            paymentDate=pDate,
            updatePeriod=insertingPeriod,
        )

        b.currentBalance = bData['endBalance']
        b.principal = bData['repay']
        b.interest = bData['interest']
        b.interestYield = bData.get('JuniorYield', None)
        b.currentRate = bData['rate']
        b.updatePeriod = insertingPeriod
        print(f"saving {b}")
        b.save()


def updateBondBalance(deal: Deal):
    """
    update bond balance from payments
    """
    def getLastPayStat(_b):
        if (pays := list(b.bondPayments)):
            return sorted(pays, key=lambda x: x.paymentDate)[-1].currentBalance
        else:
            return b.issueFace

    bonds = list(deal.bonds)
    for b in bonds:
        newBal = getLastPayStat(b)
        b.curBalance = 0 if newBal is None else newBal
        # b.curFactor = round(float(b.curBalance) / float(b.issueFace),4)
        b.save()


def processTrusteeReport(deal, trRpt):
    print(f"loading trustee <{trRpt}> to <{deal}>")

    periodToLoad = trRpt.period
    if not periodToLoad:
        print(f"Failed to load trustee report with period is {periodToLoad}")
        return

    print(f"Loading period <{periodToLoad}>")

    # insert bond payment
    print(f"inserting bond payment {trRpt}")
    if deal.poolType == 'NPL':
        insertBondPaymentsByReport(trRpt)
    if deal.poolType == 'AUTO':
        insertBondPaymentsByReportAuto(trRpt)

    # update bond balance
    print(f"update bond balance {deal}")
    updateBondBalance(deal)

    # update deal
    deal.period = periodToLoad
    deal.save()


def processTrusteeReportByDeal(deal: Deal):
    print(f"loading trustees of <{deal}>")

    rpts = TrusteeReport.select().where(TrusteeReport.deal == deal).order_by(TrusteeReport)


def processTrusteeReports():
    def goodToInsert(dp, tp):
        match (dp, tp):
            case (_, None):
                return False
            case (None, 1):
                return True
            case (None, _):
                return False
            case _ if (tp - dp) == 1:
                return True
            case _:
                return False

    rs = q_with_m("os_fill_trustee_report", ["deal_id", 'id', 'TrPeriod', 'DealPeriod'])
    print(f"Total os records {len(rs)}")
    for r in rs:
        if not goodToInsert(r['DealPeriod'], r['TrPeriod']):
            continue
        d = Deal.get_by_id(r['deal_id'])
        trRpt = TrusteeReport.get_by_id(r['id'])
        try:
            processTrusteeReport(d, trRpt)
        except Exception as e:
            print(f"{e} when inserting {d} {trRpt}")
            print(traceback.format_exc())


def fillInitViewFn(deal: Deal):
    initRpts = [rpt for rpt in deal.ratingReports if rpt.seq == 0]
    for rpt in initRpts:
        vs = rpt.data['qwen-long']["GEN_INIT_RPT/NPL_INIT_RPT"]
        fillToDataByPath(
            deal,
            ['preClosing', 'view', rpt.agency.name],
            subMap(vs, ["positiveView", "negativeView"], None),
        )


def fillInitView():
    """os_fill_rating_init_view"""
    rs = q_with_m("os_fill_rating_init_view", ["deal_id"])
    osDeals = list(tz.pluck('deal_id', rs))
    for d in osDeals:
        fillInitViewFn(Deal.get_by_id(d))


def fillDealEndDate():
    osr = q_with_m('os_fill_deal_enddate', ['dealid', 'ClearData'])

    def getEndDate(cd, q):
        vs = cd & lens.Values()[q]['endDate'].collect()
        v = set(vs)
        if (len(v) == 1) and (v is not None):
            return vs[0]
        return None

    q_map = {
        "AUTO": "AUTO_CLEAR_SUMMARY_RPT",
        "NPL": "NPL_CLEAR_RPT",
    }

    for r in osr:
        d = Deal.get_by_id(r['dealid'])
        if (x := getEndDate(r['ClearData'], q_map[d.poolType])):
            d.endDate = x
            d.save()


def preClosingDealDataInit(deal, ow=False):
    """
    [PreClosing] init deal data from parsed rating reports
    """
    if (not ow) and ('preClosing' in deal.data):
        console.print(f"[{deal.dealid}] The deal data has been filled")
        return

    initRpts = [rpt for rpt in deal.ratingReports if rpt.seq == 0]
    assert all([(_.data is not None) for _ in initRpts]), f"Missing rating report data {[ _.loc.key for _ in initRpts if _.data is None ]}"

    def getIfAny(x, y):
        match (x, y):
            case (None, None):
                return None
                # raise RuntimeError(f"Both {x} and {y} are None")
            case (None, y):
                return y
            case (x, None):
                return x
            case (x, y) if x == y:
                return x
            case _:
                return f"{x}/{y}"
                # raise RuntimeError(f"Both {x} and {y} are not None, but they are not equal either")

    def mergeTwo(x, y, t, names=None):
        match t:
            case ("reg", reg):
                match (re.match(reg, x), re.match(reg, y)):
                    case (None, None):
                        return mergeTwo(x, y, "eq")
                    case (x, None):
                        return mergeTwo(x.groups()[0], y, "eq")
                    case (None, y):
                        return mergeTwo(x, y.groups()[0], "eq")
                    case (x, y):
                        return mergeTwo(re.match(reg, x).groups()[0], re.match(reg, y).groups()[0], "eq")
                if (re.match(reg, x).groups()[0]) == (re.match(reg, y).groups()[0]):
                    if (z := re.match(reg, x)):
                        return z.groups()[0]
                    else:
                        print("failed to match z", z)
            case "eq":
                seniorShortCut = [{"次级档", "工元至诚2021年第一期不良资产支持证券次级"}, {"建欣2025年第七期不良资产支持证券", "优先档"}, {"交诚2025年第二期不良资产支持证券优先级", "优先档"}, {"交诚2025年第一期不良资产支持证券优先级", "优先级"}, {"邮盈惠泽2023年第六期优先档", "优先档"}, {"鸿富2022年第三期优先档", "优先档"}, {"优先级", "优先档"}, {"优先档", "优先S"}, {"优先档", "优级 AAAsf"}, {"优先档", "E 优先档"}, {"优先档证券", "优先档"}, {"优", "优先档"}, {"优先", "优先档"}, {"优先档", "优先档资产支持证券"}, {'-优先档', '优先档'}, {'优先级', '交诚2023年第三期不良资产支持证券优先级'}, {'优先级', '优先级证券'}, {'优先A级', '优先A档证券'}]
                if set([x, y]) in seniorShortCut:
                    return "优先级"
                if set([x, y]) == {"交诚2025年第二期不良资产支持证券次级", "次级档"}:
                    return "次级"
                if set([x, y]) == {"交诚2025年第一期不良资产支持证券次级", "次级"}:
                    return "次级"
                if set([x, y]) == {"邮盈惠泽2023年第六期次级档", "次级档"}:
                    return "次级"
                if set([x, y]) == {"次级档", "鸿富2022年第三期次级档"}:
                    return "次级"
                juniorCut = [{'NR 0班', "次级档"}, {"次级档", "次级债券"}, {"次级档", "次级档资产支持证券"}, {'-次级档', '次级档'}
                             , {'次级', '交诚2023年第三期不良资产支持证券次级'}, {"次级档", "NR 次级档"}, {"次级档 NR", "次级档"}, {"次级档", "次级档合计"}, {"次级档证券", "次级档"}, {"次级档", "次级 R"}, {"次级", "次级档"}, {'次级', '次级证券'}]  # 次级 交诚2023年第三期不良资产支持证券次级
                if set([x, y]) in juniorCut:
                    return "次级"
                if x == y:
                    return x
                if str(x) == str(y):
                    return x
                if x.replace("证券", "") == y.replace("证券", ""):
                    return x.replace("证券", "")
                if re.sub(r"(.*期)?优先档", "优先档", x) == re.sub(r"(.*期)?优先档", "优先档", y):
                    return "优先档"
                if re.sub(r"(.*期)?次级档", "次级档", x) == re.sub(r"(.*期)?次级档", "次级档", y):
                    return "次级档"
                else:
                    raise RuntimeError(f"Eq failed {x} {y}")
            case "eqNum":
                # if "元"
                if isinstance(x, str):
                    x = x.replace("元", "")
                if isinstance(y, str):
                    y = y.replace("元", "")
                if float(x) == float(y):
                    return float(x)
                else:
                    raise RuntimeError(f"eqNum failed {x} {y}")
            case ("closeNum", n):
                if round(x, n) == round(y, n):
                    return min(x, y)
                raise RuntimeError(f"close Num failed {x} {y} with rounding {n}")
            case ("int", n):
                if int(x) == int(y):
                    return min(x, y)
                raise RuntimeError(f"Int failed {x} {y} with int")
            case "min":
                return min(x, y)
            case "detailNum":
                def getMostDetail(x, y):
                    for _x, _y in zip(str(x), str(y)):
                        if _x == _y:
                            continue
                        if _x == '0':
                            return y
                        elif _y == '0':
                            return x
                        elif _x < _y:
                            return x
                        elif _x > _y:
                            return y
                        raise RuntimeError(f"Failed getMostDetail get{(x,y)}")

                if isinstance(x, str):
                    x = x.replace("元", "")
                if isinstance(y, str):
                    y = y.replace("元", "")
                if float(x) == float(y):
                    return float(x)
                if (0.95 <= float(x) / float(y)) and (float(x) / float(y) <= 1.05):
                    if round(float(x), -2) == float(y):
                        return x
                    if round(float(y), -2) == float(x):
                        return y
                    if round(float(y), -2) == round(float(x), -2):
                        return y
                    if round(float(x), -3) == float(y):
                        return x
                    if round(float(y), -3) == float(x):
                        return y
                    return getMostDetail(x, y)
            case ("map", r):
                newX = {k: v for k, v in x.items() if (v != 0.0)}
                newY = {k: v for k, v in y.items() if (v != 0.0)}
                assert set(newX.keys()) == set(newY.keys()), f"comparing maps: keys should be same but got {x.keys()} {y.keys()}"
                rm = {}
                for k in newX:
                    rm[k] = mergeTwo(newX[k], newY[k], r)
                return rm
            case "rate":
                if isinstance(x, str):
                    if "%" in x:
                        x = float(x.replace("%", "")) / 100.0
                    else:
                        x = float(x)

                if isinstance(y, str):
                    if "%" in y:
                        y = float(y.replace("%", "")) / 100.0
                    else:
                        y = float(y)
                if round(x, 3) == round(y, 3):
                    return round(x, 3)
                if (x / 100) == y:
                    return y
                if (y / 100) == x:
                    return x
                else:
                    raise RuntimeError(f"rate failed {x} {y}")
            case "date":
                #        'cutoffdate': '2025/8/10 24:00',
                # 'closingdate': '2025/9/18（预计）',
                # def mergeTwo(x,y,t,names=None):
                if x is None:
                    return y
                if y is None:
                    return x
                if ("24:00" in x) or ("24:00" in y) or ("（预计）" in y) or ("（预计）" in y):
                    return mergeTwo(re.sub(r"( 24:00|（预计）)", r"", x)
                                    , re.sub(r"( 24:00|（预计）)", r"", y)
                                    , "date"
                                    )
                if len(x) > len(y):
                    return dp.parse(x).strftime("%Y-%m-%d")
                if len(y) > len(x):
                    return dp.parse(y).strftime("%Y-%m-%d")
                d1 = dp.parse(x)
                d2 = dp.parse(y)
                if d1 == d2:
                    return d1.strftime("%Y-%m-%d")
                else:
                    if d1 < d2:
                        return d1.strftime("%Y-%m-%d")
                    else:
                        return d2.strftime("%Y-%m-%d")
                    # raise RuntimeError(f"Eq date failed {x} {y}")
            case ('threshold', v):
                if abs(x - y) < v:
                    return min(x, y)
            case ('over', vs):
                if x == y:
                    return x
                else:
                    if (vs.index(x) > vs.index(y)):
                        return y
                    else:
                        return x
            case "name":
                # （中国）
                if x is None:
                    return y
                if y is None:
                    return x
                x = '/'.join(x) if isinstance(x, list) else x
                y = '/'.join(y) if isinstance(y, list) else y
                if "未明确" in x:
                    return y
                if "未明确" in y:
                    return x
                if x == y:
                    return x
                if x.replace("（", "(").replace("）", ")") == y:
                    return y
                if y.replace("（", "(").replace("）", ")") == x:
                    return x

                if set(re.split(r"[/、]", x)) == set(re.split(r"[/、]", y)):
                    return x

            case "keep":
                return {names[0]: x, names[1]: y}

    assert len(initRpts) != 0, f"zero rating reports {deal.dealid}: {len(initRpts)}"

    def extract_black_pool(files):
        """
        判断四个文件名中是否恰好包含两个“红池”和两个“黑池”，
        若是则返回两个包含“黑池”的字符串，否则返回空列表。
        """
        red_pool = []
        black_pool = []

        for f in files:
            if "红池" in f.loc.key:
                red_pool.append(f)
            if "黑池" in f.loc.key:
                black_pool.append(f)

        if len(red_pool) == 2 and len(black_pool) == 2:
            return black_pool
        elif len(red_pool) == 0 and len(black_pool) == 2:
            return black_pool
        else:
            return []

    if len(initRpts) == 4:
        initRpts = extract_black_pool(initRpts)

    if len(initRpts) == 3 and 'DBTY' in deal.dealid:
        initRpts = initRpts[:2]

    assert len(initRpts) == 2, f"report number is not 2 but {len(initRpts)},{[ _.loc.key for _ in initRpts]}"

    modelTag = "ds" if "ds" in list(tz.concat([_.data.keys() for _ in initRpts])) else "qwen-long"
    pMap = {
        "NPL": [modelTag, "GEN_INIT_RPT/NPL_INIT_RPT"]
        , "AUTO": [modelTag, "GEN_INIT_RPT/AUTO_INIT_RPT"]
        # ,"AUTO":["qwen-long","AUTO_INIT_RPT/GEN_INIT_RPT"]
        , "CONSUMER": [modelTag, "GEN_INIT_RPT/CONSUMER_INIT_RPT"]
        , "SBL": [modelTag, "GEN_INIT_RPT/SBL_INIT_RPT"]
        , "CREDIT": [modelTag, "GEN_INIT_RPT/CONSUMER_INIT_RPT"]
    }

    dataPath = pMap[deal.poolType]
    print("data path to lookup", dataPath)
    # a map with key = agency , value = data
    ds = {rpt.agency.name: tz.get_in(dataPath, rpt.data) for rpt in initRpts}

    # assert all([ (v is not None) for k,v in ds.items()]),f"No data for report {deal.dealid}"
    for k, v in ds.items():
        if v is None:
            raise RuntimeError(f"{deal.dealid}: {k} is none")

    fields_dates = (['cutoffdate', 'closingdate', 'freq', 'statedDate'], [])
    fields_roles = (['originator', 'underwriter', 'issuer', 'servicer'], [])

    poolFieldsMap = {
        "NPL": (['totalBalance', 'WaDueMonths', 'AvgBalance', 'poolType', 'classify', 'totalPrincipalBalance'], [])
        , "AUTO": ([], [])
        , "CONSUMER": ([], [])
        , "SBL": ([], [])
        , "CREDIT": ([], [])
    }

    fields_pool = poolFieldsMap[deal.poolType]

    def extractor(data, fields):
        """
        extract fields from data object
        """
        required, optional = fields
        try:
            result = {}
            for field in required:
                result[field] = data[field]
            for field in optional:
                result[field] = data.get(field, None)
            return result
        except Exception as e:
            print("extractor", e)
            print(data)
            print(required, optional)

    def pullFromRpts(fs, ds):
        return tz.pipe(tz.valmap(lambda x: extractor(x, fs), ds).values()
                       , lambda z: tz.merge_with(lambda y: getIfAny(y[0], y[1]) if len(y) > 1 else y[0]
                                                 , *z))

    def mergeWithRules(fsMap):
        r = {}
        vs = list(ds.values())
        ks = list(ds.keys())
        for f, rule in fsMap.items():
            v = [_[f] for _ in vs]
            try:
                r[f] = mergeTwo(v[0], v[1], rule, ks)
            except Exception as e:
                print("error with matching")
                print("value", v[0], v[1])
                print("merge with rule", f, rule)

        return r

    def normalizedClassify(y):
        if y is None:
            return None
        if y == [['分类', '占资产池余额比例']]:
            return None
        if isinstance(y, list) and len(y) > 0 and isinstance(y[0], dict):
            return normalizedClassify([ [m['分类'], m['占资产池余额比例']] for m in y])
        if y[0] == ['分类', '占资产池余额比例']:
            return normalizedClassify(y[1:])

        elif all([_.endswith("类") for _ in (y & lens.Each()[0].collect())]):
            return normalizedClassify(y & lens.Each()[0].modify(lambda z: z.replace("类", "")))

        elif all([((_ is None) or (_ == '未知')) for _ in (y & lens.Each()[1].collect())]):
            return dict(y)
        elif all([(isinstance(_, str) and ("%" in _)) for _ in (y & lens.Each()[1].collect())]):
            return normalizedClassify(y & lens.Each()[1].modify(lambda z: float(z.replace("%", ""))))
        elif round(sum(y & lens.Each()[1].collect()), 1) == 100.0:
            return normalizedClassify(y & lens.Each()[1].modify(lambda z: round(float(z) / 100, 4)))
        else:
            return dict(y)

    def mergeBonds(ba_list, bb_list):
        """
        merge two bond list into a single one list if it match rules
        """
        if isinstance(ba_list[0], list):
            am = tblListToMap(ba_list)
            bm = tblListToMap(bb_list)
        else:
            am = ba_list
            bm = bb_list

        mergeRule = {
            # '债券名称':("reg", r".*证券(.*[档级])"),
            '发行规模/金额': 'detailNum',
            '偿付类型/方式': ('over', ['固定摊还', '固定摊还（目标余额）', '过手摊还', '过手型', '过手摊还型', '过手', '过手还本', None, '-', '', '—', '－', '--', '---', '无本金计划偿付', '不适用', '剩余收益', '不分配期间收益', '不计息', '未说明']),
            '利率类型': ('over', [None, '无票面利率', '固定利率', '无利率', '固定', '', 'N/A', '浮动利率（年化9%预期资金成本）', '固定利率（年化9%预期资金成本）', '无', "/", '--', '---', '-', '浮动利率', '浮动', '浮动利率（以中国人民银行一年期定期存款利率作为基准利率）', '浮动利率（以央行一年期贷款利率为基准）', '浮动（基准利率为一年期定期存款利率）', '!', '=', '.', '无利息', '—', '无息（不参与期间分配）', '固定利率0.037', '固定利率0.043', '浮动利率，以央行一年期贷款利率为基准', '浮动利率（以一年期存款利率为基准）', '浮动利率（以央行一年期贷款基准利率为基准）', '浮动利率（以央行一年期定期存款利率为基准）', '浮动利率（基准利率为中国人民银行一至五年期贷款基准利率，基本利差由簿记建档确定）', '浮动利率，基准利率为中国人民银行公布的1-5年期贷款基准利率，基本利差根据簿记建档结果确定', '浮动利率（基准为一年期定期存款利率）', '浮动利率（基准利率为中国人民银行一年期定期存款利率加基本利差）', '浮动利率（以一年期定期存款利率为基准）', '浮动利率（基准利率为中国人民银行公布的一年期贷款基准利率，基本利差根据簿记建档结果确定）', '浮动利率，基准利率为中国人民银行公布的一年期贷款基准利率，基本利差根据簿记建档结果确定', '浮动利率，基准利率为中国人民银行公布的1~5年期贷款基准利率加上基本利差', '浮动利率，以央行的一年期贷款利率作为基准利率', '浮动利率，基准为一年期贷款利率', '浮动（以央行一年期贷款利率为基准）', '浮动（基准利率为央行一年期贷款利率）', '浮动利率，以一年期贷款利率作为基准利率', '浮动利率，基准利率为央行一年期存款利率', '：', '无期间收益', '不适用', '无评级', '未予评级', '－', '无息', '浮动利率为主（83.53%）,固定利率为辅（16.47%）', '浮动利率（基准：一年期定期存款利率，利差：+3.50%）', '浮动利率，以央行的一年期贷款利率作为基准利率，发行利率3.95%', '浮动利率（基准：1~5年期贷款基准利率+基本利差）', '浮动利率（基准为1~5年期贷款基准利率+基本利差）', '浮动利率（基准为一年期贷款基准利率，利差由簿记建档确定）', '浮动利率（基准利率为中国人民银行一年期定期存款利率）', '浮动利率（基准：一年期定期存款利率，利差：+4.50%）', '浮动利率，以央行的一年期贷款利率作为基准利率，发行利率3.20%', '浮动利率（按不超过5%/年的收益率分配期间收益）', '浮动利率（以央行的一年期贷款利率作为基准利率）', '浮动利率（基准为一年期贷款基准利率+基本利差）', '按季付息，摊还期按月还本付息', '浮动利率（期间收益不超过0%/年）', '浮动利率，以央行的一年期贷款利率作为基准利率，发行利率3.20%', '浮动利率，基准利率为中国人民银行一年期定期存款利率', '浮动利率，基准利率为中国人民银行公布的一年期贷款基准利率加上基本利差', '浮动利率（基准利率为人民银行公布的一年期定期存款利率，基本利差根据簿记建档结果确定）', '浮动利率（基准：1年期LPR？注：原文为‘中国人民银行公布的一年期贷款基准利率’+基本利差）', '浮动利率（基准：1年期贷款基准利率+基本利差）', '浮动利率（基准利率为人民银行公布的一年期贷款基准利率加上基本利差）', '浮动利率（基准利率为一年期定期存款利率）', '固定资金成本', '---', '不设票面利率', '无评级（无利率约定）', '不设票面利率，在既定条件下获得期间收益以及最终的清算收益', '不计息', '未设票面利率', '无票面利率，在既定条件下取得期间收益以及最终的清算收益', '不设票面利率，在既定条件下取得每年不高于10%的期间收益以及最终的清算收益', '固定利率（利率为0%）', '无票面利率（期间收益不超过年化2%）', '浮动利率，基准为一年期贷款利率，发行利率3.29%', '浮动利率，基准为一年期贷款利率，发行利率2.90%', '无评级，无明确利率', '固定利率0.035', '固定利率0.04', '无票面利率，在既定条件下取得最终的清算收益', '剩余收益', '未说明']),
            '预期到期日': 'date',
        }
        # if len(ba_list)!=len(bb_list):
        #     if len(ba_list)>len(bb_list):
        #         return [ {k:v for k,v in m.items() if k in mergeRule }  for m in am ]
        #     else:
        #         return [ {k:v for k,v in m.items() if k in mergeRule }  for m in bm ]

        def mergeBondName(ba, bb):
            baN = ba['债券名称']
            bbN = bb['债券名称']
            if baN == bbN:
                return baN
            else:
                return baN

            return None

        assert len(am) == len(bm), f"length of bonds should be same: {len(am)} {len(bm)}"

        r = {}

        def mergeBondInfo(ba, bb):
            """
            two dict of bond from two reports
            """
            r = {}
            for fieldName, rule in mergeRule.items():
                r[fieldName] = mergeTwo(ba[fieldName], bb[fieldName], rule)
            if (mergedName := mergeBondName(ba, bb)):
                r['债券名称'] = mergedName
                return r

        return [mergeBondInfo(a, b) for (a, b) in zip(am, bm)]

    consolePool = pullFromRpts(fields_pool, ds)

    poolMergeRule = {}

    if deal.poolType == 'NPL':
        ds &= lens.Values()['classify'].modify(normalizedClassify)
        poolMergeRule = {"totalBalance": "detailNum"
                         , 'totalPrincipalBalance': "detailNum"
                         # ,'WaDueMonths':("closeNum",1)
                         , 'AvgBalance': "min"
                         , 'poolType': ("over", "信用卡分期", "个人信用卡不良贷款债权")
                         , 'classify': ("map", ("closeNum", 2))
                         , 'ExpectRecovery': "keep"
                         }
        # deal.poolSubType = consolePool['poolType']
    elif deal.poolType in ['AUTO', 'CONSUMER', 'CREDIT']:
        poolMergeRule = {"totalBalance": "detailNum"
                         , 'totalFaceValue': "detailNum"
                         , 'AvgBalance': "detailNum"
                         , 'AvgCoupon': 'rate'
                         , 'AvgTotalTerm': ("int")
                         , 'AvgRemainTerm': ("int")
                         }
    try:
        mergedData = {
            "pool": mergeWithRules(poolMergeRule)
            , "bonds": mergeBonds(*(ds & lens.Values()['bonds'].collect()))
            , "dates": mergeWithRules(
                {"cutoffdate": "date"
                 , "closingdate": "date"
                 , "freq": ("over", ['半年度', '季度', '每季度', '每月', None, '按季付息，摊还期按月还本付息', '按月还本付息（持续购买期至摊还期第一个支付日按季付息，之后为按月还本付息）', '按季付息，之后为按月还本付息'])
                 , "statedDate": "date"
                 }
            )
            , "roles": mergeWithRules({
                "originator": "name",
                "underwriter": "name",
                "issuer": "name",
                "servicer": "name"})
            , "view": tz.valmap(lambda v: subMap(v, ["positiveView", "negativeView"], None), ds)

        }
        if deal.data is None:
            deal.data = {"preClosing": mergedData}
        else:
            deal.data = tz.assoc(deal.data, "preClosing", mergedData)

        # if (cDate:= tz.get_in(['issuePlan','closingDate'], deal.data) ):
        #    deal.closingDate = dp.parse(cDate)
        # if (bDate:= tz.get_in(['issuePlan','bookDate'], deal.data) ):
        #    deal.bookDate = dp.parse(bDate)

        print("Save", deal.save())
    except Exception as e:
        logging.warning(ds)
        raise logging.warning(e)


def preClosingDealsDataInit(ow=False):
    """
    填充评级报告信息
    """
    dealIDStrs = q_with_m("os_fill_init_rating_data", ['dealid'])
    console.print(f"total records in view :  {dealIDStrs}")
    preClosingDeals = [Deal.get_by_id(x['dealid']) for x in dealIDStrs]

    for d in preClosingDeals:
        console.print(f"fill deal data {d.dealid}")
        try:
            preClosingDealDataInit(d, ow=ow)
        except Exception as e:
            logging.warning(f"failed to run {d.dealid} with {e}")


def backfillPreClosingBonds(d):
    expectIssueDate = d.data['issuePlan']['closingDate']
    expectBookDate = d.data['issuePlan']['bookDate']
    bondInPreClosing = tz.get_in(['preClosing', 'bonds'], d.data)

    for _b in d.data['issuePlan']['bonds']:
        print(f"insert with b {_b}")
        match _b:
            case {"债券名称": _}:
                expWal = getValByKeySeq(_b, ['预计加权平均期限', '预计加权平均期限(如有)'])
                bal = getValByKeySeq(_b, ['expectedWeightedAverageTerm'])
                pb, f = PreClosingBond.get_or_create(deal=d, name=_b['债券名称'], balance=_b['发行规模'], availBal=_b['配售金额'], intType=_b['发行利率'], wal=expWal, expectedMaturity=None)
                pb.save()
            # {'bondName': '优先A1级资产支持证券', 'issueSize': 1250000000, 'allocatedAmount': 1250000000, 'couponRate': '固定利率', 'expectedWeightedAverageTerm': None}
            case {'bondName': bn, 'issueSize': issueSize, 'allocatedAmount': allocatedAmount, 'couponRate': couponRate, 'expectedWeightedAverageTerm': expWal}:
                expWal = getValByKeySeq(_b, ['expectedWeightedAverageTerm'])
                pb, f = PreClosingBond.get_or_create(deal=d, name=bn, balance=issueSize, availBal=allocatedAmount, intType=couponRate, wal=expWal, expectedMaturity=None)
                pb.save()  #
            case {'bondName': bn} | {'name': bn}:
                issueSize = getValByKeySeq(_b, ['issueAmount', 'issueSize', 'size'])
                expWal = getValByKeySeq(_b, ['expectedWeightedAverageTerm', 'weightedAverageTerm', 'weightedAverageLife', 'avgLife'])
                cr = getValByKeySeq(_b, ['interestRate', 'couponRate', 'rate', 'couponType'])
                allocatedAmount = getValByKeySeq(_b, ['allocationAmount', 'allotmentAmount', 'allocatedAmount', 'placementAmount', 'placement'])
                pb, f = PreClosingBond.get_or_create(deal=d, name=bn, balance=issueSize, availBal=allocatedAmount, intType=cr, wal=expWal, expectedMaturity=None)
                pb.save()  # placementAmount

            case _:
                print(f"<passing> {_b}")


def issuePlanInitFn(issuePlan, ow=False):
    deal = issuePlan.deal

    assert (not issuePlan.data is None), f"[Issue plan init]issue plan {issuePlan}, loc:{issuePlan.loc} {issuePlan.loc.key} data is None"

    def extractInfo(m: dict):
        if 'ds' in m:
            print(f"in ds>> fill")
            if isinstance(m['ds']['PLAN_RPT']['bonds'][0], list):
                print("bonds are list , covnert it to map")
                return m['ds']['PLAN_RPT'] & lens['bonds'].Each().modify(lambda xs: dict(zip(["债券名称", "发行规模", "配售金额", "发行利率", "预计加权平均期限"], xs)))
            # if has wrong key in the map
            elif isinstance(m['ds']['PLAN_RPT']['bonds'][0], dict):
                if set(m['ds']['PLAN_RPT']['bonds'][0].keys()) == {'bondName', 'issueSize', 'allocatedAmount', 'interestRate', 'expectedWeightedAverageTerm'}:
                    # rename
                    mk = {"bondName": "债券名称", "issueSize": "发行规模", "allocatedAmount": "配售金额", "interestRate": "发行利率"
                          , "expectedWeightedAverageTerm": "预计加权平均期限(如有)"}
                    mFn = partial(mapKey, mk)
                    return m['ds']['PLAN_RPT'] & lens['bonds'].Each().modify(mFn)
                if set(m['ds']['PLAN_RPT']['bonds'][0].keys()) == {'bondName', 'issueSize', 'allocatedAmount', 'interestRate', 'weightedAverageTerm'}:
                    # rename
                    mk = {"bondName": "债券名称", "issueSize": "发行规模", "allocatedAmount": "配售金额", "interestRate": "发行利率"
                          , "weightedAverageTerm": "预计加权平均期限(如有)"}
                    mFn = partial(mapKey, mk)
                    return m['ds']['PLAN_RPT'] & lens['bonds'].Each().modify(mFn)

                return m['ds']['PLAN_RPT']
            else:
                print("bonds are map , won't do anything ")
                return m['ds']['PLAN_RPT']

        if 'qwen-long' in m:
            return m['qwen-long']['PLAN_RPT']
        if 'qwen-flash' in m:
            if isinstance(m['qwen-flash']['PLAN_RPT']['bonds'][0], list):
                print("bonds are list , covnert it to map")
                return m['qwen-flash']['PLAN_RPT'] & lens['bonds'].Each().modify(lambda xs: dict(zip(["债券名称", "发行规模", "配售金额", "发行利率", "预计加权平均期限"], xs)))
            # if has wrong key in the map
            elif isinstance(m['qwen-flash']['PLAN_RPT']['bonds'][0], dict):
                if set(m['qwen-flash']['PLAN_RPT']['bonds'][0].keys()) == {'bondName', 'issueSize', 'allocatedAmount', 'interestRate', 'expectedWeightedAverageTerm'}:
                    # rename
                    mk = {"bondName": "债券名称", "issueSize": "发行规模", "allocatedAmount": "配售金额", "interestRate": "发行利率"
                          , "expectedWeightedAverageTerm": "预计加权平均期限(如有)"}
                    mFn = partial(mapKey, mk)
                    return m['qwen-flash']['PLAN_RPT'] & lens['bonds'].Each().modify(mFn)
                if set(m['qwen-flash']['PLAN_RPT']['bonds'][0].keys()) == {'bondName', 'issueSize', 'allocatedAmount', 'interestRate', 'weightedAverageTerm'}:
                    # rename
                    mk = {"bondName": "债券名称", "issueSize": "发行规模", "allocatedAmount": "配售金额", "interestRate": "发行利率"
                          , "weightedAverageTerm": "预计加权平均期限(如有)"}
                    mFn = partial(mapKey, mk)
                    return m['qwen-flash']['PLAN_RPT'] & lens['bonds'].Each().modify(mFn)

                return m['qwen-flash']['PLAN_RPT']
            else:
                print("bonds are map , won't do anything ")
                return m['qwen-flash']['PLAN_RPT']

    ipContentParsed = tz.pipe(extractInfo(issuePlan.data))

    deal.closingDate = ipContentParsed['closingDate']
    deal.bookDate = ipContentParsed['bookDate']

    fillToData(deal, 'issuePlan', ipContentParsed)

    backfillPreClosingBonds(deal)

    console.print(f"[Issue plan init]filled with {deal.dealid}")


def IssuePlansInit():
    """
    发行管理办法 信息处理
    """
    r = q_with_m("os_fill_issue_plan", ["issuePlanID"])
    rpts = [IssuePlan.get_by_id(x) for x in tz.pluck('issuePlanID', r)]
    for rpt in rpts:
        issuePlanInitFn(rpt)


def voteForMost(iterator: Iterable[Any], removeNone=True, fn=tz.identity) -> Optional[Any]:
    """
    使用Counter的most_common方法实现的简洁版本。
    """
    if removeNone:
        iter = [x for x in iterator if x is not None]
    else:
        iter = iterator
    try:
        # 创建Counter对象
        counter = Counter(map(fn, iter))
        if not counter:
            return None
        return counter.most_common(1)[0][0]
    except TypeError:
        raise TypeError("参数必须是一个可迭代对象")


def parseClearData(d):
    """NPL clear report loader"""
    assert d.poolType == 'NPL', f"this clear extract only applies to NPL deal but {d.poolType}"
    clrRpts = list(ClearReport.select(ClearReport, Location).join(Location).where(ClearReport.deal == d).dicts())
    assert all([(x['data'] is not None) for x in clrRpts]), "all clear report should have data"

    print(f"getting dealid {d} clear data with location {[ (loc['key'],loc['id']) for loc in clrRpts]}")
    clrData = {x['key']: x['data'] & lens.Values()['NPL_CLEAR_RPT'].collect() for x in clrRpts}

    def pickCorrectOne(m: dict):
        if len(list(map(lambda x: x is not None, m.values()))) > 1:
            return {k: v for k, v in m.items() if re.search(r"清算报告", k) or re.search(r"清算专项报告", k) or re.search(r"专项复核说明", k) or re.search(r"浦鑫归航\d{4}年第\S+期不良资产证券化信托审计报告\.pdf", k) or re.search(r"苏誉\d{4}年第\S+期不良资产证券化信托专项审计报告\.pdf", k) }
        else:
            return m

    def returnIfSame(_xs, dropNone=True, fn=tz.identity):
        xs = [fn(x) for x in _xs if (x is not None and x != 0.0)]
        if xs == []:
            return None
        if len(set(xs)) == 1:
            return xs[0]
        else:
            raise RuntimeError(f"[returnIfSame] should be only one but got {xs}")

    totalRecoveryFromClear = pickCorrectOne({k: voteForMost(v & lens.Each()['totalRecoveryAmt'].collect()) for k, v in clrData.items()})

    print(f"getting from clear report {d}", totalRecoveryFromClear.values())
    votedRecovery = returnIfSame(totalRecoveryFromClear.values())

    # endDate
    endDates_ = clrRpts & lens.Each()['data'].Values()['NPL_CLEAR_RPT']['endDate'].collect()
    endDate = voteForMost(endDates_)

    # startDate
    startDates_ = clrRpts & lens.Each()['data'].Values()['NPL_CLEAR_RPT']['startDate'].collect()
    startDate = voteForMost([x for x in startDates_ if x is not None and len(x) == 10])

    # interestAmt
    interestAmts_ = pickCorrectOne({k: voteForMost(v & lens.Each()['interestAmt'].collect(), fn=lambda y: (float(y.replace(",", "")) if isinstance(y, str) else y)) for k, v in clrData.items()})

    interestAmt = returnIfSame(interestAmts_.values(), fn=float)

    callAmts_ = {k: voteForMost(v & lens.Each()['callAmt'].collect(), removeNone=False) for k, v in clrData.items()}
    callAmt = returnIfSame(callAmts_.values())

    # clrData
    outflow = None
    for k, clr in pickCorrectOne(clrData).items():
        if clr == []:
            outflow = None
        if len(clr) == 1:
            outflow = clr[0]['outflow']
        else:
            _clr = sorted(clr, key=lambda x: len(x['outflow'].keys()), reverse=True)[0]
            outflow = clr[0]['outflow']

    clearData = {"clear": clrData, 'totalRecoveryAmt': votedRecovery
                 , 'endDate': endDate, 'startDate': startDate
                 , 'interestAmt': interestAmt, 'callAmt': callAmt
                 , 'outflow': outflow & lens.Values().modify(tz.compose(float, nToZ))
                 }

    return (endDate, clearData)


def returnIfSame(xs):
    if len(set(xs)) == 1:
        return xs[0]
    if None in xs:
        return None
    return None


def pickModelPath(ms, d):
    for m in ms:
        yield d[m]


def parseClearDataAuto(d):
    """Auto clear report loader"""

    clrRpts = list(ClearReport.select(ClearReport, Location).join(Location).where(ClearReport.deal == d).dicts())
    assert all([(x['data'] is not None) for x in clrRpts]), "all clear report should have data"

    q = 'AUTO_CLEAR_SUMMARY_RPT'
    ms = ['qwen-plus', 'qwen-flash']
    picker = tz.curry(pickModelPath)(ms)

    callDate = clrRpts & lens['data'].Fold(picker).collect()

    r = {
        'callDate': callDate
    }

    return (endDate, r)

    # d.endDate = endDate
    # fillToData(d,'clear',clearData)


def initClearRpt():
    """

    """
    r = q_with_m("os_fill_clear", ["dealid"])
    ds = [Deal.get_by_id(x) for x in tz.pluck('dealid', r)]
    for d in ds:
        match d.poolType:
            case "NPL":
                (endDate, cd) = parseClearData(d)
            case "AUTO":
                (endDate, cd) = parseClearDataAuto(d)

        d.endDate = endDate
        fillToData(d, 'clear', cd)
        d.save()
        print(f"fill done with {d}")


def mergePt(x):
    match x:
        case _ if set(x) == {'信用卡分期', '信用卡不良债权'}:
            return "信用卡分期"
        case _ if set(x) == {'信用卡分期', '信用卡个人消费类不良贷款'}:
            return "信用卡分期"
        case _ if set(x) == {'信用卡分期', '个人信用卡不良贷款债权'}:
            return "信用卡分期"
            # {'信用卡不良债权', '信用卡个人消费类不良贷款'}
        case _ if set(x) == {'信用卡不良债权', '信用卡个人消费类不良贷款'}:
            return "信用卡分期"
        case _ if set(x) == {'信用卡分期', '个人信用卡不良债权'}:
            return "信用卡分期"
        case _ if set(x) == {'汽车分期', '汽车按揭'}:
            return "汽车按揭"
        case _ if set(x) == {'消费贷款', '汽车按揭'}:
            return "汽车按揭"
        case _ if set(x) == {'小微企业贷款', '汽车按揭'}:
            return "汽车按揭"
        case _ if set(x) == {'信用卡分期', '汽车分期'}:
            return "汽车按揭"
        case _ if set(x) == {'信用卡不良贷款债权', '信用卡个人消费类不良贷款'}:
            return "信用卡分期"
        case _ if set(x) == {'小微企业贷款', '对公不良贷款'}:
            return "小微企业贷款"
        case _ if set(x) == {'小微企业贷款', '对公不良贷款债权'}:
            return "小微企业贷款"
        case _ if set(x) == {'小微企业贷款'}:
            return "小微企业贷款"
        case _ if set(x) == {'住房按揭'}:
            return "住房按揭"
        case _ if set(x) == {'小微企业贷款', '住房按揭'}:
            return "住房按揭"
        case _ if set(x) == {'信用卡分期'}:
            return "信用卡分期"
        case _ if set(x) == {'消费贷款'}:
            return "消费贷款"
        case _ if set(x) == {'信用卡不良债权', None}:
            return "信用卡分期"
            # {'信用卡不良债权', None}
        case _ if set(x) == {'消费贷款', '信用卡分期'}:
            return "信用卡分期"
        case _:
            raise RuntimeError(f"failed to match {x}")


def fixPoolTypeFn(dealid: str):
    d = Deal.get_by_id(dealid)
    assert d.poolType == 'NPL', f"{dealid}: sub pool type only for NPL deals"
    # initRpts = [ model_to_dict(rpt) for rpt in d.ratingReports if rpt.seq==0]
    initRpts = [rpt for rpt in list(d.ratingReports) if rpt.seq == 0]
    assert len(initRpts) == 2, f"{dealid}: Only need two init rating  but got {len(initRpts)}"
    ra, rb = initRpts
    if isinstance(ra.data['ds']['GEN_INIT_RPT/NPL_INIT_RPT'], str):
        return
    if isinstance(rb.data['ds']['GEN_INIT_RPT/NPL_INIT_RPT'], str):
        return
    pts = set([ra.data, rb.data] & lens.Each()['ds']['GEN_INIT_RPT/NPL_INIT_RPT']['poolType'].collect())
    validSubPoolType = ["小微企业贷款", "住房按揭", "信用卡分期", "消费贷款", "汽车按揭", "对公不良"]
    r = mergePt(pts)
    if r in validSubPoolType:
        return r
    else:
        return None


def fixPoolType():
    xs = q_with_m("os_fill_npl_subpooltype", ['dealid', ])
    dealids = tz.pluck('dealid', xs)
    for dealid in dealids:
        if (pt := fixPoolTypeFn(dealid)):
            d = Deal.get_by_id(dealid)
            d.poolSubType = pt
            d.save()


def tryToGetPeriod(x):
    tryPaths = [
        ['qwen-flash', 'TRUSTEE_NPL_RPT', 'date', 'reportNumber']
        , ['qwen-flash', 'TRUSTEE_AUTO_RPT', 'date', 'reportNumber']
        , ['qwen-plus', 'TRUSTEE_NPL_RPT', 'date', 'reportNumber']
        , ['ds', 'TRUSTEE_NPL_RPT', 'date', 'reportNumber']
        , ['ds', 'TRUSTEE_AUTO_RPT', 'date', 'reportNumber']
    ]
    for pt in tryPaths:
        if (f := tz.get_in(pt, x)):
            return f
    return None


def tryToGetPayDate(x):
    tryPaths = [
        ['qwen-flash', 'TRUSTEE_NPL_RPT', 'date', 'payDate']
        , ['qwen-flash', 'TRUSTEE_AUTO_RPT', 'date', 'payDate']
        , ['qwen-plus', 'TRUSTEE_NPL_RPT', 'date', 'payDate']
        , ['ds', 'TRUSTEE_NPL_RPT', 'date', 'payDate']
        , ['ds', 'TRUSTEE_AUTO_RPT', 'date', 'payDate']
    ]
    for pt in tryPaths:
        if (f := tz.get_in(pt, x)):
            return f
    return None


def resetPeriod(did):
    d = Deal.get_by_id(did)
    rpts = list(d.trusteeReports)
    rptsWithR = tz.groupby(lambda x: tz.get_in(['qwen-flash', 'TRUSTEE_AUTO_RPT'], x.data, default=None) is not None, rpts)
    #  revolve buy , normal trustee
    match (rptsWithR.get(False, []), rptsWithR.get(True, [])):
        case ([], []):
            print(f"empty report to reset")
        case ([], _rpts):
            print(f"patching non-revolving {len(_rpts)}")
            for _rpt in _rpts:
                if (_p := tryToGetPeriod(_rpt.data)):
                    _rpt.period = _p
                    _rpt.save()
        case (_rpts, []):
            print(f"patching revolving {len(_rpts)}")
            for _rpt in _rpts:
                if (_p := getValByPs(_rpt.data, [['qwen-flash', 'TRUSTEE_AUTO_BUY_RPT', 'period'], ])):
                    _rpt.period = _p
                    _rpt.save()
        case (_rpts_r, _rpts_n):
            print(f"{len(_rpts_r)} {len(_rpts_n)}")
            maxP = 0
            for _rpt in _rpts_r:
                if (_p := getValByPs(_rpt.data, [['qwen-flash', 'TRUSTEE_AUTO_BUY_RPT', 'period'], ])):
                    _rpt.period = _p
                    maxP = max(_p, maxP)
                    _rpt.save()
            for _rpt in _rpts_n:
                # print(f"_rpt.data",_rpt.data)
                if (_p := tryToGetPeriod(_rpt.data)):
                    _rpt.period = _p + maxP
                    _rpt.save()
        case (x, y):
            print(f"[Failed]: failed to match {x} {y}")


def fillTrusteePeriod():
    rs = q_with_m('os_fill_trusteereport_period', ['id', 'deal_id', 'data'])
    dealid_set = set(list(tz.pluck('deal_id', rs)))
    for d in dealid_set:
        resetPeriod(d)

    for r in rs:
        try:
            if (p := tryToGetPeriod(r['data'])):
                tr = TrusteeReport.get_by_id(r['id'])
                tr.period = int(p)
                tr.save()
        except Exception as e:
            print(r)
            print(f"error with {e}")


def extractWaterfallFn(dealid, w1, w2):
    d = Deal.get_by_id(dealid)
    w = json.loads(merge_two_waterfalls(w1, w2))
    if isinstance(w, dict) and ('merged_sequence' in w):
        newData = tz.assoc_in(d.data, ['waterfall', 'normal'], w['merged_sequence'])
    elif isinstance(w, dict) and ('merged_allocation_order' in w):
        newData = tz.assoc_in(d.data, ['waterfall', 'normal'], w['merged_allocation_order'])
    elif isinstance(w, dict) and ('merged_allocation_sequence' in w):
        newData = tz.assoc_in(d.data, ['waterfall', 'normal'], w['merged_allocation_sequence'])
    else:
        newData = tz.assoc_in(d.data, ['waterfall', 'normal'], w)
    d.data = newData
    d.save()


def fillWaterfallFn(k: str, v):
    """
    k: dealid in string
    v: a list of rating report data: ['dealid','DealData','RRData']
    """
    d = Deal.get_by_id(k)
    if d.poolType == 'NPL':
        path = 'GEN_INIT_RPT/NPL_INIT_RPT'
    elif d.poolType == 'AUTO':
        path = 'GEN_INIT_RPT/AUTO_INIT_RPT'
    else:
        raise RuntimeError(f"failed to match deal type {d.poolType}")

    vs = v & lens.Each()['RRData']['ds'][path]['waterfall'].collect()
    extractWaterfallFn(k, vs[0], vs[1])


def fillWaterfall():
    oRecords = q_with_m('os_llm_deal_waterfall', ['dealid', 'DealData', 'RRData'])
    print("total os", len(oRecords))
    ips = tz.pipe(tz.groupby('dealid', oRecords)
                  , lambda m: {k: v for k, v in m.items() if len(v) == 2}
                  )
    for k, v in ips.items():
        assert len(v) == 2, f"{k} should only has two init rating report but got {len(v)}"
        fillWaterfallFn(k, v)


def tieoutBalanceForBalanceFn(b):
    """
    update bond curBalance and curFactor
    update bondpayment : currentbalance/factor by principal payments and issue face
    """
    begBal = b.issueFace
    pays_ = b.bondPayments
    assert begBal is not None, f"begbal shouldn't be none"
    pays = sorted(pays_, key=lambda x: x.paymentDate)
    for pay in pays:
        print(f"beg bal {begBal}, prin:{pay.principal}, date:{pay.paymentDate}")
        if pay.principal is None:
            pay.currentBalance = begBal
            # pay.factor = begFactor
        else:
            pay.currentBalance = begBal - pay.principal
        pay.currentFactor = pay.currentBalance / b.issueFace
        begBal = pay.currentBalance
        pay.save()

    b.curBalance = begBal
    print(f"final bond cur balance {b.curBalance}")
    bSaveFlag = b.save()
    print(f"bSaveFlag: {bSaveFlag}")


def tieoutBalanceForBalance():
    osRecords = q_with_m('os_fill_bond_curbalance', ['id'])
    for r in osRecords:
        tieoutBalanceForBalanceFn(Bond.get_by_id(r['id']))


def fillSeqView():
    rs = q_with_m('os_fill_rating_seq_view', ['dealid'])
    for r in rs:
        d = Deal.get_by_id(r['dealid'])
        rpts = list(RatingReport.select().where(RatingReport.seq != 0, ~RatingReport.data.is_null(), RatingReport.deal == d))
        for rpt in rpts:
            seqRatingData = tz.get_in(['qwen-plus', 'SEQ_RATING'], rpt.data)
            ratingDate = seqRatingData['ratingDate']
            newData = tz.assoc_in(d.data, ['seqViews', ratingDate], seqRatingData)
            d.data = newData
            d.save()


def fill_trading_price():
    rs = q_with_m('os_fill_trading_price', ['bond_id', 'date', 'cleanPrice', 'dirtyPrice', 'tradeCount', 'settleAmount'])
    for r in rs:
        # print(f"getting bond id {r['bond_id']}")
        b = Bond.get_by_id(r['bond_id'])
        d = r['date']
        cp = r['cleanPrice']
        dp = r['dirtyPrice']
        tc = r['tradeCount']
        stl = r['settleAmount']
        s, f = TradingPrice.get_or_create(bond=b, date=d, cleanPrice=cp, dirtyPrice=dp, tradeCount=tc, settleAmount=stl)
        if f:
            s.save()


def calibrateTheName(dealid: str, rptIdx=0, ow=False, acc=False):
    d = Deal.get_by_id(dealid)
    tRpts = sorted(list(d.trusteeReports.dicts()), key=lambda x: x['period'])
    tRptsPerds = set(tz.pluck('period', tRpts))
    if rptIdx not in tRptsPerds:
        print(f"[calibrateTheName] {rptIdx} not in {tRptsPerds}")
        return

    if len(tRpts) == 0:
        print(f"{dealid} no trustee reports ")
        return

    theRpt = findFirstByFn(tRpts, lambda x: x['period'] == rptIdx)

    rptBond = tz.get_in(['data', 'qwen-flash', 'TRUSTEE_AUTO_RPT', 'bonds'], theRpt)
    if not rptBond:
        print(f"{dealid} no bond in trustee reports ")
        return

    rptBondNames = rptBond.keys()

    dm, f = InternalDealMeta.get_or_create(deal=d)

    bondJsonData = [subMap(x, ['id', 'name', 'seniority']) for x in list(d.bonds.dicts())]

    print(f"bond data:{bondJsonData}, period:{rptIdx} reportBondNames:{rptBondNames}")

    qq = f'''
这是这个债券的json数据{bondJsonData},这里是受托报告中的债券名字{rptBondNames}(这些债券名字可能相比较多).请按照name进行匹配, 最后组成一个map,key是受托报告中债券名字,value是对应json数据,如果找不到就把value设置成null. 最后返回严格用json格式.不要提供额外注释
'''
    if dm.data is not None:
        if (bm := dm.data.get("bondMapping", False)):
            if ow:
                v = ask(qq, "你是一个ABS证券分析师和数据库分析师")
                print(f"proceed with overriding {v}")
                dm.data = tz.assoc(dm.data, "bondMapping", v)
            elif acc:
                print(f"mergeing : current{bm}")
                v = ask(qq, "你是一个ABS证券分析师和数据库分析师")
                new = tz.merge(bm, v)
                dm.data = tz.assoc(dm.data, "bondMapping", new)
            else:
                print(f"no override: current{bm}")
        else:
            v = ask(qq, "你是一个ABS证券分析师和数据库分析师")
            dm.data = tz.assoc({}, "bondMapping", v)
    else:
        v = ask(qq, "你是一个ABS证券分析师和数据库分析师")
        dm.data = tz.assoc({}, "bondMapping", v)

    dm.save()


FILL_FUNCS = [
    toFillPricing,
    toFillBond,
    IssuePlansInit,
    preClosingDealsDataInit,
    initClearRpt,
    fillTrusteePeriod,
    processTrusteeReports,
    fixPoolType,
    fillWaterfall,
    fillInitView,
    fillSeqView,
    fillDealEndDate,
    tieoutBalanceForBalance,
    fillPoolPerfNPL,
    fillIsin,
    fill_trading_price,
]


def fill_deal_data_obj():
    """Run every fill step, mirroring ``flow/dags/fill_data.py::fill_deal_data_obj``."""
    for fn in FILL_FUNCS:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            logging.error("[fill fun ] fun:%s error:%s", fn.__name__, e)


def resolve_step(name: str):
    """Resolve a CLI step name (``to_fill_bond``, ``toFillBond``, ...) to a function."""
    key = name.replace("-", "_").replace(" ", "").lower()
    for fn in FILL_FUNCS:
        if fn.__name__.replace("_", "").lower() == key.replace("_", ""):
            return fn
    raise KeyError(f"unknown fill step: {name!r}")
