from sqlite3 import connect
from datetime import timedelta,datetime
from lenses import lens
import toolz as tz

from itertools import accumulate
import json 

from model import Deal,TrusteeReport,Stage,DealData,TradingPrice,BondID,BondPayments
from model import Bond,BondSeniorityType,BondIDType,Location

from typing import Annotated, Literal, Union

from fastapi import FastAPI,Query
from util import bondNameMapping,subMap,convert_list_to_map
from playhouse.shortcuts import model_to_dict
from dateutil.parser import parse

from pyxirr import xirr,InvalidPaymentsError
from rich.console import Console

#from db import read_sqlite_table
#from trustee_builder import digest
from pydantic import BaseModel, Field

console = Console()

app = FastAPI()

EndedStage = Stage.get_by_id(3)
CurrentStage = Stage.get_by_id(2)
PreClosingState = Stage.get_by_id(1)


def getDiff(xs):
    r = []
    for i in range(1,len(xs)):
        r.append(xs[i]-xs[i-1])
    return r

def divList(xs,ys):
    r = []
    for x,y in zip(xs,ys):
        r.append(x/y if y!=0 else None)
    return r

def getTrusteeReportByDealAndPeriod(deal_id: str, rpt_period: int):
    r = TrusteeReport.get(TrusteeReport.deal==deal_id, TrusteeReport.period==rpt_period)
    return r

def getTrusteeReportsByDeal(deal_id: str):
    '''
        return a map: period -> report data
    '''
    r = TrusteeReport.select().where(TrusteeReport.deal==deal_id)
    return {x['period']:x for x in list(r.dicts())}
    
def getDealData(deal_id:str)-> dict:
    r = list(Deal.get(dealid=deal_id).dealdata.dicts())
    if r:
        return r[0]['data']
    else:
        raise RuntimeError(f"Failed to find deal data from {deal_id}")


def backoutYieldByPrice(tradingPrice:float, bondID:int) -> float:

    investment = []
    inflows = []
    flows = []

    return xirr(flows)


def getTradingPrice(asOfDate:str):
    d = parse(asOfDate)
    rs = list(TradingPrice.select().where(TradingPrice.date>=d).dicts())
    r = []
    for x in rs:
        vs = list(BondID.select(BondID.bondID,BondID.idType).where(BondID.bond==x['bond']).dicts())
        r.append(x | convert_list_to_map(vs,'idType','bondID'))
    return r

def getBondFromBondID(bondId,idType:str):

    b = BondID.select().join(Bond).where(BondID.idType==idType,BondID.bondID==bondId).first().bond

    return b


def calcCapitalStructure(poolBal:list, bonds:list, account:list=[]):
    ''' 
    '''
    r = {
        #"asset": poolBal,
        #"bonds": [  for b in bonds ]
    }


  

def calcNPL_OC(poolBalance, realizedRecovery, est:dict, bondBalance, account=[]):
    '''
    NPL 资本结构
    est: k="estimate name",v= estimated recovery rate
    bonds: bondBalance
    accounts: [("Acc1",200)...]
    '''

    
    if len(est)==0:
        return {}
    
    estWithAvg = est | {"avgEstRate": sum(est.values())/len(est) } | {"minEstRate": min(est.values()) } | {"maxEstRate": max(est.values()) }
    estMap = tz.valmap(lambda v: round(poolBalance * v - realizedRecovery), estWithAvg)
    #liabilities = dict(accumulate(bonds,accBond))
    OcAmt = {k: round(v - bondBalance,2) for k,v in estMap.items() }
    OcRate = {k:  round(v/bondBalance,4) for k,v in OcAmt.items() }
    
    OcRatio = {scen: round(recovery/bondBalance,6) 
                for scen,recovery in estMap.items() }
    
    return {
        'pool':estMap,
        'OcAmt': OcAmt, 
        'OcRate': OcRate,
        'OcCoverage': OcRatio
    }

def calcCumRecoveryRate(tr):
    '''
    tr: trustee report data
    '''
    totalRecovery = 0
    beginBalance = 0 
    r = totalRecovery/beginBalance
    return (totalRecovery, beginBalance, r)


def calcIrrByBond(bondId:int):
    '''
    Calculate the IRR of a bond ,with given a bond id
    
    '''
    def mapNoneToZero(y):
        if y is None:
            return 0
        else:
            return y
    bond = Bond.get_by_id(bondId)
    issueDate = bond.issueDate 
    issueFace = bond.issueFace 
    issuePrice = bond.issuePrice 
    init = (issueDate, -1 * issuePrice / 100 * issueFace )
    
    bondflows = tz.pipe(BondPayments.select(BondPayments.paymentDate,BondPayments.principal,BondPayments.interest,BondPayments.interestYield).where(BondPayments.bond == bond).dicts()
                        ,list
                        ,lambda xs : [  (x['paymentDate'],x & lens['principal'].modify(mapNoneToZero) & lens['interest'].modify(mapNoneToZero) & lens['interestYield'].modify(mapNoneToZero) )
                                        for x in xs ]
                        ,lambda xs : [ (x, sum(tz.dissoc(y,'paymentDate').values())) for (x, y) in xs ]
                    )
    try:
        return xirr([init]+bondflows)
    except InvalidPaymentsError as e:
        return "Failed to Calc"

def juniorIrr(dealList):
    ''' calculate Junior tranhces of closed NPL deals '''
    selectedField = [Bond.id,Bond.issueDate,Bond.issuePrice,Bond.issueFace,Deal.dealid,Deal.endDate,Deal.seriesName,Deal.closingDate]
    juniorBonds = list(Bond.select(*selectedField)\
                .join(Deal).where(Bond.seniority==BondSeniorityType.get_by_id("junior")
                                    ,Deal.stage==Stage.get_by_id(3)).dicts())
    if juniorBonds:
        return \
            tz.pipe(juniorBonds
                    ,list
                    ,lambda xs: tz.do(print(f"len of junior bonds {len(juniorBonds)}"),xs)
                    ,lambda xs: [ tz.assoc(x, 'irr', calcIrrByBond(x['id'])) for x in xs ]
                    )
    else:
        return []
    

def irrOfClosedDeal(deal_id:str):
    Bond.select().join(Deal).where(Deal.dealid==deal_id, Deal.stage==EndedStage)

def generateAnalytics(deal_id:str, selectPeriod:int=None):

    d = Deal.get(Deal.dealid==deal_id)
    #TODO need to check selectPeriod is less than or equal to latest rpt period
    
    poolType,stage = d.poolType,d.stage
    curPeriod = d.period

    data = getDealData(deal_id)
    #bonds = d.bonds
    trusteeRpts = getTrusteeReportsByDeal(deal_id)
    
    currentTrusteeRpt = trusteeRpts[curPeriod]
    data = currentTrusteeRpt['data']
    chData = json.loads(data['ch'])
    
    #print("currentTrusteeRpt", currentTrusteeRpt)
    ## bond info
    bonds = tz.dissoc(chData['bond'], 'strats')
    #print("bonds", bonds)
    bondsBal = [ (bname,binfo['本金余额_当期期末']) for bname,binfo in bonds.items() ]
    ## pool info 
    
    #bondNames =
    
    def accBond(acc, cur):
       name,amt = cur
       accName,accAmt = acc
       return (f"{accName}+{name}", accAmt+amt)
   
    bondsWithStackBal = dict(accumulate(bondsBal,accBond))
    console.print("bond stack", bondsWithStackBal)

    #print("bond init info ", {b.name:model_to_dict(b) for b in d.bonds })
    r = {"deal_id":deal_id,"deal_fullname":d.fullName,"poolType":poolType
         ,"subPoolType":d.poolSubType
         ,"period":curPeriod}

    r = {"bond": {b.name: subMap(model_to_dict(b)
                                 ,['curFactor','curBalance','curRate','issuePrice','issueDate'])
                    for b in d.bonds}
        ,"pool":{}
        } | r

    #print("agency", list(d.ratingReports) )
    ratingData = tz.pipe({ratingRpt.agency.name:ratingRpt.data for ratingRpt in d.ratingReports }
                        ,lambda m: {k: json.loads(v) for k,v in m.items()}                    
    )
    dealDates = {per: json.loads(rpt['data']['ch'])['dates'] for per,rpt in trusteeRpts.items()}
    poolCollectionDates = {per: (parse(dates['收款期截止日']) - parse(dates['收款期起始日'])).days/365 
                           for per,dates in dealDates.items()}
    poolData = {per: json.loads(rpt['data']['ch'])['pool'] for per,rpt in trusteeRpts.items()}

    #recoveryDiff = 
    # EndedStage
    match (poolType,stage):
        case ("NPL",st) :
            #return "It's NPL"
            ### Pool Performance 
            poolBegBalance = [poolData[1]['本金以及利息余额_设立日']] + [ poolData[per]['本金以及利息余额_收款期末'] for per in range(1,5)]
            poolAssetNum =  [poolData[1]['债权数量_设立日'] ] + [ poolData[per]['债权数量_收款期末'] for per in range(1,5) ]
            poolAssetNumDiff = getDiff(poolAssetNum)
            #console.print(poolCollectionDates)
            totalRecovery0 = tz.pipe(poolData
                                    ,lambda m: {k: subMap(v,['回收款_处置中_当期','回收款_已处置_当期'])
                                                    for k,v in m.items()}
                                    ,lambda m: [ (m[i]['回收款_处置中_当期'],m[i]['回收款_已处置_当期']) for i in range(1,len(poolData)+1)]
                                    )
            totalRecovery = [x+y for x,y in totalRecovery0 ]
            recoveryByWriteOff = [y for x,y in totalRecovery0 ]
            recSpeed = {per: (totalRecovery[per-1]/fraction)/poolBegBalance[per-1] for per,fraction in poolCollectionDates.items() }
            
            assetNumAmortRate = [ round(x/y,4) for x,y in zip(poolAssetNumDiff, poolAssetNum[1:] ) ]
            console.print("poolRecoveries", poolBegBalance, totalRecovery,recSpeed,poolAssetNum
                          ,poolAssetNumDiff,assetNumAmortRate)
            poolProgress = []
            
            r = {"progress": poolProgress
                , "recoveryCalc": {"Recoveries":totalRecovery
                                   ,"RecoverySpeed": recSpeed
                                   ,"AssetNumDown":poolAssetNumDiff
                                   ,"AssetNumAmort":assetNumAmortRate
                                   ,"AvgRecoveryByAssetNum":divList(recoveryByWriteOff,poolAssetNumDiff) }
                } | r 
            
            ### Capital Structure
            currPoolBal = chData['pool']['本金以及利息余额_收款期末']
            cumuRecovery1 = chData['pool']['回收款_处置中_累计']
            cumuRecovery2 = chData['pool']['回收款_已处置_累计']
    
            ratingData = {k:v['ExpectRecovery']/v['totalBalance'] for k,v in ratingData.items() }
            
            npl_oc = {k: calcNPL_OC(currPoolBal, cumuRecovery1 + cumuRecovery2, ratingData, v)
                        for k,v in bondsWithStackBal.items()}
            
            #console.print(npl_oc)
            r = {"oc": npl_oc} | r 
            ## Rating estimated rec



            ## Bond summary

            ### EndedStage
            ### extract Xirr of equity tranche
            #xirrMap = {k:v["xirr"]["result"] for k,v in data['bond'].items() }
            #r = {"xirr":xirrMap} | r
            #r &= lens['bond'].modify(lambda xs: tz.merge(xs[0],xs[1]))
        case _:
            return f"it's not matched {(poolType,stage)}"

    return r

def fetchBondFlow(bond):
    rs = BondPayments.select().where(BondPayments.bond==bond).dicts()
    return \
    tz.pipe(tz.pluck(["principal","interest","paymentDate"],rs)
           ,list
           ,lambda xs: [ (_[2],_[0]+_[1]) for _ in xs ]
           )



def BondView():
    r = Deal.select(Deal.seriesName,Deal.shortNameKey,Bond.name,Bond.issuePrice,Bond.curFactor,BondID.bondID,Deal.closingDate,Deal.stage).join(Bond).join(BondID)\
        .where(BondID.idType=='债券代码'
              )\
        .order_by(Deal.closingDate.desc()).dicts()    


def EquityBondView():
    r = Deal.select(Deal.seriesName,Deal.shortNameKey,Bond.name,Bond.issuePrice,Bond.curFactor,BondID.bondID,Deal.closingDate,Deal.stage).join(Bond).join(BondID)\
        .where(Bond.seniority==BondSeniorityType.get(BondSeniorityType.name=='junior')
              ,BondID.idType=='债券代码'
              ,Deal.poolType=='NPL'
              )\
        .order_by(Deal.closingDate.desc()).dicts()

    return list(r)



    
class DealQuery(BaseModel):
    poolType: Union[str, None] = None
    stage: Union[int, None] = None
    page: int = Field(gt=0)
    pageSize: int = Field(gt=10, le=100, default=25)
    order_by: Literal["closingDate", "endedDate"] = "closingDate"


@app.get("/deals/")
def findDeals(q: Annotated[DealQuery, Query()]):
    pg = (q.page, q.pageSize)
    deals = None
    match (q.poolType, q.stage):
        case (None, None):
            deals = Deal.select().paginate(*pg)
        case (None, _):
            deals = Deal.select().where(Deal.stage == Stage(q.stage)).paginate(*pg)
        case (_, None):
            deals = Deal.select().where(Deal.poolType == q.poolType).paginate(*pg)
        case (_, _):
            deals = Deal.select().where(
                Deal.poolType == q.poolType, Deal.stage == Stage(q.stage)
            ).paginate(*pg)
    return list(deals.dicts())






# @app.get("/deal/{deal_id}")
# def get_deal(deal_id: str):
#     deal = Deal.get(Deal.dealid == deal_id)
#     # 
#     relatesFiles = read_sqlite_table('source.db','qiniu_storage')
#     if deal:
#         rawFiles = relatesFiles[relatesFiles.key.str.match(deal.shortNameKey)]['key'].to_list()
#         #print("total ",rawFiles['key'].to_list())
#         groupFiles = [] # digest(rawFiles, deal.shortNameKey)
#         return {
#             "deal": deal.dealid,
#             "name": deal.fullName,
#             "rawFiles": rawFiles,
#             "groupFiles": groupFiles,
#             "trusteeReports": list(deal.trusteeReports.select(TrusteeReport.period,Location.key).join(Location).order_by(TrusteeReport.period).dicts())
#         }    
#     return deal


@app.get("/deal/{deal_id}/data")
def get_deal(deal_id: str):

    return getDealData(deal_id)

@app.get("/deal/{deal_id}/analytics")
def get_deal(deal_id: str):

    return generateAnalytics(deal_id)

@app.get("/trading/{as_of_date}/")
def get_deal(as_of_date: str):
    return getTradingPrice(as_of_date)


@app.get("/data/deal/{deal_id}/trusteeRpt/{rpt_period}")
def get_deal(deal_id: str, rpt_period: int):
    r = getTrusteeReportByDealAndPeriod(deal_id, rpt_period)
    return r.data

@app.get("/data/deal/{deal_id}/trusteeRpts/")
def get_deal(deal_id: str):
    r = TrusteeReport.select().where(TrusteeReport.deal==deal_id)
    return list(tz.pluck('data', r.dicts()))



