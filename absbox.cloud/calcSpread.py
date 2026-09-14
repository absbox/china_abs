import pandas as pd
from scipy.interpolate import pchip_interpolate
import numpy as np
import toolz as tz
from db import db_pool
from rich.console import Console
from datetime import date, datetime
from functools import lru_cache
from itertools import dropwhile

console = Console()

def interplo(n, x, ys):
    '''
        n -> name of interplo method
        x -> weighted average rate
        ys -> future curve rates
    '''
    match (n, ys) :
        case ("np",[_1,_2,_3,_4,_5,_6,_7,np.nan]):
            return np.interp(x, [0.25,0.5,1.0,3.0,5.0,7.0,10]
                                , [_1,_2,_3,_4,_5,_6,_7]
                                , right=_7,left=_1)
        case ("np", [_1,_2,_3,_4,_5,_6,_7,_8]):
            return np.interp(x, [0.25,0.5,1.0,3.0,5.0,7.0,10,30]
                                , [_1,_2,_3,_4,_5,_6,_7,_8]
                                ,right=_8,left=_1)
        case ("pchip",[_1,_2,_3,_4,_5,_6,_7,np.nan]):
            tenors = [0.25,0.5,1.0,3.0,5.0,7.0,10]
            spot_rates = [_1,_2,_3,_4,_5,_6,_7]
            pchip_interp = pchip_interpolate(tenors, spot_rates, np.array([x]))
            return pchip_interp[0].item()
        case ("pchip",[_1,_2,_3,_4,_5,_6,_7,_8]):
            tenors = [0.25,0.5,1.0,3.0,5.0,7.0,10,30]
            spot_rates = [_1,_2,_3,_4,_5,_6,_7,_8]
            pchip_interp = pchip_interpolate(tenors, spot_rates, np.array([x]))
            return pchip_interp[0].item()

def calcSprds(conn, dates, rates, durations, curveName: str):
    def to_date(v):
        if isinstance(v, date):
            return v if not isinstance(v, datetime) else v.date()
        return pd.to_datetime(v).date()

    spreads = []
    if not dates:
        return spreads

    availableDates = conn.execute(
        f"select distinct(日期) from chinacurves where 曲线名称='{curveName}' order by 日期 desc;"
    ).fetchall()
    
    max_date_ = max(dates)
    min_date_ = min(dates)
    
    #dropwhile(lambda x: x < min_date, availableDates)
    availableDates_ = [_[0].date() for _ in availableDates]
    
    try:
        max_date_idx = next(i for i, d in enumerate(availableDates_) if d <= max_date_)
        max_date = availableDates_[max_date_idx]
    except StopIteration:
        max_date = max_date_

    try:
        min_date_idx = next(i for i, d in reversed(list(enumerate(availableDates_))) if d >= min_date_)
        min_date = availableDates_[min(min_date_idx + 1, len(availableDates_) - 1)]
    except StopIteration:
        min_date = min_date_
    #console.print(f"origin min {min_date_} max {max_date_}")
    #console.print(f"new min {min_date} max {max_date}")
    rows = conn.execute(
        f"select * from chinacurves where 曲线名称='{curveName}' and 日期<='{max_date}' and 日期>='{min_date}' order by 日期 desc;"
    ).fetchall()

    if not rows:
        raise ValueError(f"No curve data for {curveName} up to {max_date}")

    #console.print(f"rows: {rows}")

    for issueDate, issueRate, duration in zip(dates, rates, durations):
        idate = to_date(issueDate)
        
        r = next(
            (row for row in rows if to_date(row[2]) <= idate),
            None
        )
        
        if r is None:
            raise ValueError(f"No curve row <= {issueDate} for curve {curveName}")
        
        expRiskFreeRate = interplo("pchip", duration, r[3:])
        spreads.append(float(issueRate) - expRiskFreeRate)
    return spreads


@lru_cache(maxsize=1024)
def calcProjectRfRate(issueDate,curveName,duration):
    #vs = rateDf.loc[(issueDate,curveName)].iloc[0].drop('index',axis=0).tolist()
    with db_pool.get_conn() as conn:
        r = conn.execute(f"select * from chinacurves where 曲线名称='{curveName}' and 日期<='{issueDate}' order by 日期 desc;").fetchone()
    
    assert duration >=0, f"duration {duration} is invalid"
    expRiskFreeRate = interplo("pchip", duration, r[3:])
    return round(expRiskFreeRate,4)

#@lru_cache(maxsize=1024)
def calcBondSpreads(historyIssuance):
    with db_pool.get_conn() as conn:  
        historySpeads = tz.pipe( (list(tz.pluck('issueDate',historyIssuance))
                                                ,[ 100*_ for _ in tz.pluck('issueRate',historyIssuance)]
                                                ,list(tz.pluck('预期存续',historyIssuance))  #TODO : use 加权存续
                                                )
                                #,lambda xs: tz.do(console.print, xs)
                                ,lambda xs: calcSprds(conn,xs[0], xs[1], xs[2], "中债国债收益率曲线")
        )
        return historySpeads
        


def calcSpreadFn(deal, historyIssuance, sameSeriesDeals, sameTypeDeals,weight=0.65):
    seriesCount,typeCount = len(sameSeriesDeals),len(sameTypeDeals)
    # spread between senior bonds
    # credit card ,non tier 1 -> 20 bps
    # other auto deals -> 10 bps
    # JSD -> 5 bps
    #console.print(historyIssuance)
    with db_pool.get_conn() as conn:    
        historySpeads = tz.pipe( (list(tz.pluck('issueDate',historyIssuance))
                                                ,[ 100*_ for _ in tz.pluck('issueRate',historyIssuance)]
                                                ,list(tz.pluck('预期存续',historyIssuance))  #TODO : use 加权存续
                                                )
                                #,lambda xs: tz.do(console.print, xs)
                                ,lambda xs: calcSprds(conn,xs[0], xs[1], xs[2], "中债国债收益率曲线")
        )
        avgSeriesSpd,avgTypeSpd = np.mean(historySpeads[:seriesCount]),np.mean(historySpeads[seriesCount:])
        match (sameSeriesDeals,sameTypeDeals):
            case (a,b) if len(a)==0 and len(b)==0:
                raise NotImplementedError(f"need to pick largest spread in recent deal in 6 months")
                #expectSpread = round(avgTypeSpd,4)
            # no same series 
            case (a,b) if len(a)==0 :
                expectSpread = round(avgTypeSpd,4)
            # no same class
            case (a,b) if len(b)==0 :
                expectSpread = round(avgSeriesSpd,4)
            case _:
                expectSpread = round(avgSeriesSpd*weight + avgTypeSpd*(1-weight),4)
                
        return expectSpread

def adjustRates(rates, result):
    ''' adjust senior rates in same deal '''
    minimalSpreads = 0.05
    print(rates, result)
    if len(rates)==0:
        return result
    fr,*rest = rates
    if len(result)==0:
        return adjustRates(rest, [fr])
    if (result[-1]+minimalSpreads) > fr :
        return adjustRates(rest,  result+[result[-1]+minimalSpreads])
    else:
        return adjustRates(rest, result+[fr])
        
    
    