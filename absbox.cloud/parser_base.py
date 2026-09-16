
from enum import StrEnum, auto
from lenses import lens
import json
import toolz as tz
from itertools import dropwhile,takewhile
import re
try:
    from cnc import convert
except ImportError:  # optional/private dependency; only needed for CN numeral parsing
    convert = None
from dateparser import DateDataParser,parse
from more_itertools import split_at,collapse,split_after
from util import readHtmlTblToList,tryToMatch

class META(StrEnum):
    # Meta
    RPT_NUM = auto()
    RPT_DATE = auto()
    DETAIN_TO_NEXT = auto() # 转存下期金额
    IGNORE = auto()

class COMP(StrEnum):
    BOND = auto() # flow & balance 
    POOL =  auto()  # flow & balance 
    ACCOUNT =  auto()  # flow & balance 
    FEE = auto()  # flow
    DATES = auto()
    OTHER =auto()

class ValueType(StrEnum):
    INT = auto()
    MON = auto()
    RATE = auto()
    PCT = auto()
    IN10K = auto()
    IN100M = auto()
    DATE = auto()
    STR = auto()
    BOOL = auto()

class DateType(StrEnum):
    PAY_DATE = auto()
    CLOSING_DATE = auto()
    COLL_BEG_DATE = auto()
    COLL_END_DATE = auto()
    BOND_BEG_DATE = auto()
    BOND_END_DATE = auto()
    END_DATE = auto()

class BalAsOf(StrEnum):
    # Time of the data for balance
    CLOSING =  auto()
    CUR_END =  auto()
    CUR_BEG = auto()
    COLL_END = auto()
    COLL_BEG = auto()

class BalType(StrEnum):
    BAL_PRIN  = auto()
    BAL_AND_ACCRUE_INT = auto()
    BAL_CUM = auto()

    # for pool
    ASSET_NUM = auto()

    # for bond
    FACTOR = auto()
    FACTOR_AMORT = auto()
    COUPON_RATE = auto()
    BOND_CASH =auto()

class BondType(StrEnum):
    PAID_IN_FULL = auto()
    INT_IN_FULL = auto()
    INT_DELAYED = auto()
    BOND_CODE = auto()

class PoolType(StrEnum):
    BuyBack = auto()
    PCT = auto()

class BondSenorityType(StrEnum):
    SENIOR = auto()
    JUNIOR = auto()    

class Status(StrEnum):
    ''' Loan Status '''
    CURRENT = auto()
    DELINQ = auto()
    DEFAULTED = auto()
    IN_DISPOSAL = auto()
    LIQUIDATED = auto()


class Outflow(StrEnum):
    PRIN  = auto() # bond
    INT = auto() # bond 
    PRIN_AND_INT = auto() # bond principal and interest
    YIELD = auto()  # fee and bond
    FEE = auto() # fee
    CASH_OUT = auto() # generic

class Inflow(StrEnum):    
    ## INFLOW TYPE
    RECOVERY = auto() # pool 
    PREPAYMENT = auto() # pool 
    SCHEDULE = auto() # pool 
    OTHER_INCOME = auto() 
    REINVEST = auto() # account 
    CASH_IN = auto() # pool/generic
    PRINCIPAL = auto()
    INTEREST = auto()
    CALL = auto()
    LOC = auto()
    # INT & PRIN

    # Fee
class AggType(StrEnum):
    TOTAL = auto()
    STRATS = auto()

class StratsType(StrEnum):
    ByStatus = auto()
    ByBondPayOut = auto()

class FeeType(StrEnum):
    TAX = auto()
    AGENT = auto()
    ISSUANCE = auto()
    TRUSTEE = auto()
    CASH_MGMT = auto()
    DISPOSAL = auto()
    SERVICER = auto()
    OPERATION =auto()
    FEE_INT = auto()
    AUDIT = auto()
    BANK = auto()
    RATING = auto()
    OTHER  = auto()
    INSURANCE = auto()
    BONUS = auto()
    EXT_DISPOSAL = auto()
    LEGAL = auto()
    VALUATION = auto()


dm = {
    BalAsOf.CLOSING:"设立日"
    ,BalAsOf.CUR_END:"当期期末"
    ,BalAsOf.CUR_BEG:"当期期初"
    ,BalAsOf.COLL_END:"收款期末"
    ,BalAsOf.COLL_BEG:"收款期初"
    ,BalType.BAL_PRIN:"本金余额"
    ,BalType.BAL_AND_ACCRUE_INT:"本金以及利息余额"
    ,BalType.BAL_CUM:"累计余额"
    #,BalType.BAL_CUM:"累计余额"  #<BalType.BAL_CUM: 'bal_cum'>
    ,BondSenorityType.SENIOR:"优先级"
    ,BondSenorityType.JUNIOR:"次级"
    ,Status.CURRENT:"正常"
    ,Status.DELINQ:"拖欠"
    ,Status.DEFAULTED:"已违约"
    ,Status.IN_DISPOSAL:"处置中"
    ,Status.LIQUIDATED:"已处置"
    ,BalType.ASSET_NUM :"债权数量"
    ,BalType.FACTOR:"债券系数"
    ,BalType.FACTOR_AMORT:"债券摊销比例"
    ,BalType.COUPON_RATE:"票面利率"
    ,Outflow.PRIN :"兑付本金"
    ,Outflow.INT:"兑付利息"
    ,Outflow.YIELD:"兑付收益"
    ,Outflow.FEE:"费用支出"
    ,Outflow.PRIN_AND_INT:"兑付本息"
    ,Outflow.CASH_OUT:"现金支出"
    ,Inflow.RECOVERY:"回收款"
    ,Inflow.PREPAYMENT:"提前还款"
    ,Inflow.PRINCIPAL:"本金收入"
    ,Inflow.LOC:"流动性支持汇入"
    ,Inflow.SCHEDULE:"计划还款"
    ,Inflow.INTEREST:"利息收入"
    ,Inflow.OTHER_INCOME:"其他收入"
    ,Inflow.REINVEST:"合格投资"
    ,Inflow.CASH_IN:"现金收入"
    ,AggType.TOTAL:"合计"
    ,AggType.STRATS:"分类"
    ,StratsType.ByStatus :"债权状态"
    ,StratsType.ByBondPayOut:"偿付类型"
    ,FeeType.TAX :"税费"
    ,FeeType.AGENT :"代理支付费用"
    ,FeeType.ISSUANCE:"发行费用"
    ,FeeType.TRUSTEE:"受托费用"
    ,FeeType.CASH_MGMT:"现金管理费用"
    ,FeeType.DISPOSAL:"处置费用"
    ,FeeType.SERVICER :"服务商费用"
    ,FeeType.AUDIT:"审计费用"
    ,FeeType.BANK:"银行费用"
    ,FeeType.RATING :"评级费用"
    ,FeeType.OTHER :"其他费用"
    ,FeeType.OPERATION:"执行费用"
    ,FeeType.FEE_INT:"费用利息"
    ,FeeType.INSURANCE:"保险费用"
    ,FeeType.BONUS:"奖励费用"
    ,FeeType.EXT_DISPOSAL:"超额处置费用"
    ,FeeType.LEGAL:"法律服务费"
    ,FeeType.VALUATION:"评估费用"
    ,DateType.BOND_BEG_DATE:"起息日"
    ,DateType.BOND_END_DATE:"结息日"
    ,DateType.CLOSING_DATE:"设立日"
    ,DateType.COLL_BEG_DATE:"收款期起始日"
    ,DateType.COLL_END_DATE:"收款期截止日"
    ,DateType.PAY_DATE:"支付日"
    ,DateType.END_DATE:"终止日"
    ,BondType.BOND_CODE:"证券代码"
    ,BondType.PAID_IN_FULL:"足额兑付"
    ,BondType.INT_IN_FULL:"足额付息"
    ,BondType.INT_DELAYED:"利息延迟支付"
    ,PoolType.BuyBack:"回购"
    ,PoolType.PCT:"占比"
    ,META.DETAIN_TO_NEXT:"转存下期金额"
    ,META.IGNORE:"忽略字段"
}


FieldMapping = {
    "bond":[
        (r"发行总额",((BalType.BAL_PRIN,BalAsOf.CLOSING,),ValueType.MON)), # 发行总额
        (r"发行面值\(总量\)",((BalType.BAL_PRIN,BalAsOf.CLOSING,),ValueType.MON)),
        #(r"发行总量（面值）",((BalType.BAL_PRIN,BalAsOf.CLOSING,),ValueType.MON)),
        (r"发行总量[\(（]面值[\)）]",((BalType.BAL_PRIN,BalAsOf.CLOSING,),ValueType.MON)),
        #()
        (r"本期兑付前本金",((BalType.BAL_PRIN,BalAsOf.CUR_BEG,),ValueType.MON)),
        (r"本期兑付前本金总额",((BalType.BAL_PRIN,BalAsOf.CUR_BEG,),ValueType.MON)),
        (r"本期兑付前本金值",((BalType.BAL_PRIN,BalAsOf.CUR_BEG,),ValueType.MON)),
        (r"本期兑付前本金\(元\)",((BalType.BAL_PRIN,BalAsOf.CUR_BEG,),ValueType.MON)),
        
        (r"每百元兑付前本金值",((BalType.FACTOR_AMORT,BalAsOf.CUR_BEG),ValueType.MON)),
        (r"本期兑付前每百元面额本金值",((BalType.FACTOR_AMORT,BalAsOf.CUR_BEG),ValueType.MON)),
        (r"本期兑付前本金额",((BalType.BAL_PRIN,BalAsOf.CUR_BEG,),ValueType.MON)),
        (r"本期兑付前本金总额\(元\)",((BalType.BAL_PRIN,BalAsOf.CUR_BEG,),ValueType.MON)),
        
        (r"本金每百元兑付本金金额",((BalType.FACTOR_AMORT,),ValueType.MON)),
        (r"本期每百元面额兑付本金金额",((BalType.FACTOR_AMORT,),ValueType.MON)),
        (r"本次兑付本金值\s*?\(元/百元面额\)",((BalType.FACTOR_AMORT,),ValueType.MON)),
        (r"本次兑付本金值\s*?（元/百元面额）",((BalType.FACTOR_AMORT,),ValueType.MON)),
        (r"本次兑付本金值\S元?百元面额\S",((BalType.FACTOR_AMORT,),ValueType.MON)),
        (r"本期每百元兑付本金值",((BalType.FACTOR_AMORT,),ValueType.MON)),
        (r"本期每百元面额兑付本金值",((BalType.FACTOR_AMORT,),ValueType.MON)),
        (r"本期每百元面额兑付本金额",((BalType.FACTOR_AMORT,),ValueType.MON)),
        (r"每百元兑付本金",((BalType.FACTOR_AMORT,),ValueType.MON)),
        
        (r"本息兑付后每百元面额剩余本金值",((BalType.FACTOR,),ValueType.MON)),
        #(r"")

        
        #(r"本期兑付前本金总额(元)",((BalType.BAL_PRIN,BalAsOf.CUR_BEG,),ValueType.MON)),
        (r"本期兑付本金金额",(Outflow.PRIN,ValueType.MON)),
        (r"本次兑付本金值.*",(Outflow.PRIN,ValueType.MON)),
        (r"本期兑付本金值",(Outflow.PRIN,ValueType.MON)),
        
        
        (r"本期兑付总金额",(Outflow.PRIN_AND_INT,ValueType.MON)),
        (r"总支付金额",(Outflow.PRIN_AND_INT,ValueType.MON)),
        (r"支付总金额",(Outflow.PRIN_AND_INT,ValueType.MON)),
        
        
        (r"累计兑付本金总额",((BalType.BAL_CUM,Outflow.PRIN), ValueType.MON)),
        
        #本次兑付本金值(元/百元面额） 每百元兑付本金
        (r"本期兑付本金总?额",(Outflow.PRIN,ValueType.MON)),
        
        # 本期兑付后剩余本金
        
        (r"本息兑付后剩余本金\S*",((BalType.BAL_PRIN,BalAsOf.CUR_END,),ValueType.MON)),
        #(r"本息兑付后剩余本金总额\(元\)",((BalType.BAL_PRIN,BalAsOf.CUR_END,),ValueType.MON)),
        #(r"本息兑付后剩余本金值",((BalType.BAL_PRIN,BalAsOf.CUR_END,),ValueType.MON)),
        #(r"本息兑付后剩余本金金额",((BalType.BAL_PRIN,BalAsOf.CUR_END,),ValueType.MON)),
        (r"本期兑付后剩余本金[值|金额]",((BalType.BAL_PRIN,BalAsOf.CUR_END,),ValueType.MON)),
        (r"本期本息兑付后本金余额",((BalType.BAL_PRIN,BalAsOf.CUR_END,),ValueType.MON)),
        # 
        
        (r"资产支持证券本金",(Outflow.PRIN,ValueType.MON)),
        #(r"优先级资产支持证券本金",((Outflow.PRIN,BondSenorityType.SENIOR),ValueType.MON)),
        (r"优先[档级]资产支持证券本金",((Outflow.PRIN,BondSenorityType.SENIOR),ValueType.MON)),
        (r"次级档资产支持证券本金",((Outflow.PRIN,BondSenorityType.JUNIOR),ValueType.MON)),        
        # 
        #(r"标的债权资产本息余额",((BalType.BAL_AND_ACCRUE_INT,BalAsOf.CUR_END,),ValueType.MON)),

        
        (r"付息金额",(Outflow.INT,ValueType.MON)),
        (r"本期付息金额",(Outflow.INT,ValueType.MON)),
        (r"资产支持证券利息",(Outflow.INT,ValueType.MON)),
        (r"票面利率",(BalType.COUPON_RATE,ValueType.RATE)),

        # 
        (r"优先档证券利息总支出",((Outflow.INT,BondSenorityType.SENIOR),ValueType.MON)),
        (r"优先档资产支持证券利息",((Outflow.INT,BondSenorityType.SENIOR),ValueType.MON)),
        #(r"次级资产支持证券固定资金成本",((Outflow.INT,BondSenorityType.JUNIOR),ValueType.MON)),

        (r"固定资金成本",((Outflow.INT,BondSenorityType.JUNIOR),ValueType.MON)),
        (r"次级固定资金成本",((Outflow.INT,BondSenorityType.JUNIOR),ValueType.MON)),
        (r"次级档固定资金成本",((Outflow.INT,BondSenorityType.JUNIOR),ValueType.MON)),
        (r"次级档预期资金成本",((Outflow.INT,BondSenorityType.JUNIOR),ValueType.MON)),        
        (r"次级档?资产支持证券固定资金成本?",((Outflow.INT,BondSenorityType.JUNIOR),ValueType.MON)),
        (r"次级档资产支持证券预期资金成本?",((Outflow.INT,BondSenorityType.JUNIOR),ValueType.MON)),
        
        (r"次级档资产支持证券收益",((Outflow.YIELD,BondSenorityType.JUNIOR),ValueType.MON)),
        (r"次级档资产支持证券的收益",((Outflow.YIELD,BondSenorityType.JUNIOR),ValueType.MON)),
        (r"次级档超额收益",((Outflow.YIELD,BondSenorityType.JUNIOR),ValueType.MON)),
        (r"次级档收益",((Outflow.YIELD,BondSenorityType.JUNIOR),ValueType.MON)),
        (r"次级超额收益",((Outflow.YIELD,BondSenorityType.JUNIOR),ValueType.MON)),
        (r"其中:次级档收益",((Outflow.YIELD,BondSenorityType.JUNIOR),ValueType.MON)),
        (r"特别信托受益权特别信托收益",((Outflow.YIELD,),ValueType.MON)),
        (r"次级收益",((Outflow.YIELD,BondSenorityType.JUNIOR),ValueType.MON)),
        (r"特别信托受益权特别信托利益",((Outflow.YIELD,BondSenorityType.JUNIOR),ValueType.MON)),
        (r"特别信托利益",((Outflow.YIELD,BondSenorityType.JUNIOR),ValueType.MON)),        
                                
        (r"证券利息总支出",(Outflow.INT,ValueType.MON)),
        (r"付息\(或收益\)金额",(Outflow.INT,ValueType.MON)),
        (r"证券利息\(或收益\)总支出",(Outflow.INT,ValueType.MON)),
        (r"证券本金总支出",(Outflow.PRIN,ValueType.MON)),
        (r"优先级证券利息支出",((Outflow.INT,BondSenorityType.SENIOR),ValueType.MON)),


        (r"特别信托受益权特别信托本金",((Outflow.PRIN,),ValueType.MON)),


        (r"是否足额兑付|是否按时兑付",(BondType.PAID_IN_FULL,ValueType.BOOL)),
        (r"本期利息\(或收益\)是否延迟支付",(BondType.INT_DELAYED,ValueType.BOOL)),
        (r"本期利息是否延[迟退][支兑]付",(BondType.INT_DELAYED,ValueType.BOOL)),
        #(r"本期利息是否延迟兑付")

        (r"本期兑付本息总额",(Outflow.PRIN_AND_INT,ValueType.MON)),
        
        (r"证券代码",(BondType.BOND_CODE,ValueType.STR)),
        (r"证券简称",(BondType.BOND_CODE,ValueType.STR)),
        #(r"忽略字段",(META.IGNORE,ValueType.STR))
        (r"转存下期金额",(META.DETAIN_TO_NEXT,ValueType.MON)),
        (r"转存下期余额",(META.DETAIN_TO_NEXT,ValueType.MON)),
    ],
    "pool":[#期初本息余额 本金以及利息余额
        (r"信用卡债权笔数",(BalType.ASSET_NUM,ValueType.INT)),
        (r"标的债权资产笔数",(BalType.ASSET_NUM,ValueType.INT)),
        (r"消费贷债权笔数",(BalType.ASSET_NUM,ValueType.INT)),
        (r"标的债权资产户数",(BalType.ASSET_NUM,ValueType.INT)),
        (r"标的资产债权笔数",(BalType.ASSET_NUM,ValueType.INT)),
        (r"资产笔数",(BalType.ASSET_NUM,ValueType.INT)),
        (r"贷款笔数",(BalType.ASSET_NUM,ValueType.INT)),
        (r"债权笔数",(BalType.ASSET_NUM,ValueType.INT)),
        (r"借款人户数",(BalType.ASSET_NUM,ValueType.INT)),
        (r"账户数",(BalType.ASSET_NUM,ValueType.INT)),
        (r"抵押贷款笔数",(BalType.ASSET_NUM,ValueType.INT)),
        (r"户数",(BalType.ASSET_NUM,ValueType.INT)),
        (r"笔数",(BalType.ASSET_NUM,ValueType.INT)),
        (r"标的债权笔数",(BalType.ASSET_NUM,ValueType.INT)),
        (r"贷款户数",(BalType.ASSET_NUM,ValueType.INT)),
        # 期初未尝本息金额
        (r"期初本息金额\(注1\)",((BalType.BAL_AND_ACCRUE_INT, BalAsOf.COLL_BEG),ValueType.MON)),
        (r"期初未尝本息金额",((BalType.BAL_AND_ACCRUE_INT, BalAsOf.COLL_BEG),ValueType.MON)),
        (r"期初未偿本息费[余金]额",((BalType.BAL_AND_ACCRUE_INT, BalAsOf.COLL_BEG),ValueType.MON)),
        (r"期初未偿本息余额\S",((BalType.BAL_AND_ACCRUE_INT, BalAsOf.COLL_BEG),ValueType.MON)),

        (r"标的资产债权本息余额",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        (r"抵押贷款本息费余额",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        (r"债权本息费余额[（\(]元[）\)]",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        (r"标的债权本息余额",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        (r"未偿本息费余额",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        (r"未偿本息费余额[（\(]元[）\)]",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        (r"信用卡债权本息余额",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        (r"信用卡债权本息费余额",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        (r"信用卡债权未偿本息费余额",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        
        (r"信用卡债权本息余领",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        (r"消费贷债权本息余额",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        
        (r"贷款未偿本息余额[（\(]元[）\)]",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        
        (r"资产未偿本金余额",(BalType.BAL_PRIN,ValueType.MON)),
        (r"信用卡债权本金余额",(BalType.BAL_PRIN,ValueType.MON)),
        # #
        (r"标的债权资产本息余额",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),# 期初本息金额(元)
        (r"期初本息金额[（\(]元[）\)]",((BalType.BAL_AND_ACCRUE_INT, BalAsOf.COLL_BEG),ValueType.MON)), 
        (r"期末本息金额[（\(]元[）\)]",((BalType.BAL_AND_ACCRUE_INT, BalAsOf.COLL_END),ValueType.MON)), 
        (r"期初本息资金额",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)), 
        (r"本息[余金]额\(元\)",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        (r"未偿本息余额",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        (r"未偿本息费余额\(元\)",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        
        #(r"未偿本息余额")
        
        (r"信用卡债权本金余领",(BalType.BAL_PRIN,ValueType.MON)),
        (r"标的债权资产本息费余额",(BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        (r"期初(?:未偿)?本息[金余]额$",((BalType.BAL_AND_ACCRUE_INT, BalAsOf.COLL_BEG),ValueType.MON)),
        # 期初未偿本息余额的占比
        #(r"期初未偿本息余额的占比",((BalType.BAL_AND_ACCRUE_INT, BalAsOf.COLL_BEG),ValueType.MON)),
        
        (r"初始起算日未偿本息余额",((BalType.BAL_AND_ACCRUE_INT, BalAsOf.CLOSING),ValueType.MON)),
        # (元)
        (r"期初本息余额[（\(]元[）\)]",((BalType.BAL_AND_ACCRUE_INT, BalAsOf.COLL_BEG),ValueType.MON)),
        (r"期末本息余额[（\(]元[）\)]",((BalType.BAL_AND_ACCRUE_INT, BalAsOf.COLL_END),ValueType.MON)),
        
        (r"期初本息费金额",((BalType.BAL_AND_ACCRUE_INT, BalAsOf.COLL_BEG),ValueType.MON)),
        
        (r"期初未偿本息[余金]额\(元\)",((BalType.BAL_AND_ACCRUE_INT, BalAsOf.COLL_BEG),ValueType.MON)),
        # 期初未偿本息余额(元)
        (r"资产本息余额", (BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        (r"资产本金余额", (BalType.BAL_PRIN,ValueType.MON)),
        (r"贷款本息余额", (BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        (r"贷款本息费余额", (BalType.BAL_AND_ACCRUE_INT,ValueType.MON)),
        # 
        #(r"期初未偿本息余额(注1)",((BalAsOf.COLL_BEG,BalType.BAL_AND_ACCRUE_INT),ValueType.MON)),
        (r"处置完毕的?资产", ((Inflow.RECOVERY,Status.LIQUIDATED),ValueType.MON)),
        
        (r"累计处置完毕资产", ((Inflow.RECOVERY,Status.LIQUIDATED),ValueType.MON)),
        (r"累计_累计处置完毕资产", ((BalType.BAL_CUM, (Inflow.RECOVERY,Status.LIQUIDATED)),ValueType.MON)),
        
        (r"累计_处置完毕的?资产", ((BalType.BAL_CUM, (Inflow.RECOVERY, Status.LIQUIDATED)), ValueType.MON)),
        
        (r"累计处置完毕资产_本金", ((Inflow.PRINCIPAL,Status.LIQUIDATED),ValueType.MON)),
        (r"累计处置完毕资产_收益", ((Inflow.INTEREST,Status.LIQUIDATED),ValueType.MON)),
        
        
        
        (r"本期处置完毕(资产)?_收益", ((Inflow.INTEREST,Status.LIQUIDATED),ValueType.MON)),
        (r"本期处置完毕(资产)?_本金", ((Inflow.PRINCIPAL,Status.LIQUIDATED),ValueType.MON)),
        
        (r"处置中(资产)?_收益", ((Inflow.INTEREST,Status.IN_DISPOSAL),ValueType.MON)),
        (r"处置中(资产)?_本金", ((Inflow.PRINCIPAL,Status.IN_DISPOSAL),ValueType.MON)),
        (r"累计_本期处置完毕(资产)?_收益", ((BalType.BAL_CUM, (Inflow.INTEREST, Status.LIQUIDATED)), ValueType.MON)) ,
        (r"累计_本期处置完毕(资产)?_本金", ((BalType.BAL_CUM, (Inflow.PRINCIPAL, Status.LIQUIDATED)), ValueType.MON)) ,
        (r"累计_累计处置完毕资产_本金", ((BalType.BAL_CUM, (Inflow.PRINCIPAL, Status.LIQUIDATED)), ValueType.MON)) ,
        (r"累计_累计处置完毕资产_收益", ((BalType.BAL_CUM, (Inflow.INTEREST, Status.LIQUIDATED)), ValueType.MON)) ,
        (r"累计_处置中(资产)?_收益", ((BalType.BAL_CUM, (Inflow.INTEREST, Status.IN_DISPOSAL)), ValueType.MON)) ,
        (r"累计_处置中(资产)?_本金", ((BalType.BAL_CUM, (Inflow.PRINCIPAL, Status.IN_DISPOSAL)), ValueType.MON)) ,

        (r"本期处置完毕", ((Inflow.RECOVERY,Status.LIQUIDATED,),ValueType.MON)),
        (r"\S?本期处置完毕资产", ((Inflow.RECOVERY,Status.LIQUIDATED,),ValueType.MON)),
        #(r"", Status.LIQUIDATED),
        (r"处置中(资产)?", ((Inflow.RECOVERY,Status.IN_DISPOSAL),ValueType.MON)),
        # (r"累计处置完毕资产",((Inflow.)))
        (r"回收款", (Inflow.RECOVERY,ValueType.MON)),
        #(r"累计_回收款", ((BalType.BAL_CUM, Inflow.RECOVERY),ValueType.MON)),
        
        (r"累计_\S?本期处置完毕(资产)?",((BalType.BAL_CUM, (Inflow.RECOVERY, Status.LIQUIDATED)), ValueType.MON)) ,
        (r"累计_本期处置完毕", ((BalType.BAL_CUM, (Inflow.RECOVERY, Status.LIQUIDATED)), ValueType.MON)) ,
        (r"累计_处置中(资产)?", ((BalType.BAL_CUM, (Inflow.RECOVERY, Status.IN_DISPOSAL)), ValueType.MON)) ,
        
        (r"累计_其他收入",((BalType.BAL_CUM, Inflow.OTHER_INCOME),ValueType.MON)),
        (r"累计_合格投资",((BalType.BAL_CUM, Inflow.REINVEST),ValueType.MON)),        
        (r"其他收入",(Inflow.OTHER_INCOME,ValueType.MON)),
        (r"其他现金流流入",(Inflow.OTHER_INCOME,ValueType.MON)),
        (r"合格投资",(Inflow.REINVEST,ValueType.MON)),
        (r"价格投资",(Inflow.REINVEST,ValueType.MON)),
        (r"季度结息",(Inflow.REINVEST,ValueType.MON)),
        (r"累计_季度结息",((BalType.BAL_CUM, Inflow.REINVEST),ValueType.MON)),
        (r"累计_价格投资",((BalType.BAL_CUM, Inflow.REINVEST),ValueType.MON)),
        (r"累计_其他现金流流入",((BalType.BAL_CUM, Inflow.OTHER_INCOME),ValueType.MON)),
        (r"流动性支持资金",(Inflow.LOC,ValueType.MON)),
        (r"流动性支持",(Inflow.LOC,ValueType.MON)),
        (r"“流动性支持款项”",(Inflow.LOC,ValueType.MON)),
        (r"累计_“流动性支持款项”",((BalType.BAL_CUM,Inflow.LOC),ValueType.MON)),
        (r"累计_流动性支持",( (BalType.BAL_CUM,Inflow.LOC),ValueType.MON)),
        (r"累计_流动性支持资金",( (BalType.BAL_CUM,Inflow.LOC),ValueType.MON)),
        #(r"累计_流动性支持资金",((BalType.BAL_CUM,Inflow.LOC),ValueType.MON)),
        
        
        (r"清仓回购",(Inflow.CASH_IN,ValueType.MON)),
        (r"累计_清仓回购",((BalType.BAL_CUM, Inflow.CASH_IN),ValueType.MON)),
        # 处置中资产
        (r"本期报告期末",((BalAsOf.COLL_END,BalType.BAL_PRIN),ValueType.MON)),
        (r"初始起算日封包时点",((BalAsOf.CLOSING,BalType.BAL_PRIN),ValueType.MON)),
        (r"本期报告期初",((BalAsOf.COLL_BEG,BalType.BAL_PRIN),ValueType.MON)),
        #(r"赎回\S(信用卡债权)?笔数",((PoolType.BuyBack,BalType.ASSET_NUM),ValueType.INT)),
        #(r"赎回\S资产笔数",((PoolType.BuyBack,BalType.ASSET_NUM),ValueType.INT)),
        # 赎回/资产金额
        #(r"赎回\S资产金额",((PoolType.BuyBack,BalType.BAL_PRIN),ValueType.MON)),
        #(r"赎回\S信用卡债权金额",((PoolType.BuyBack,BalType.BAL_PRIN),ValueType.MON)), 
        #(r"赎回\S信用卡债权占比",((PoolType.BuyBack,BalType.BAL_PRIN),ValueType.RATE)), 
        #(r"占比",((BalType.BAL_PRIN,),ValueType.RATE)),
        #(r"赎回\S资产占比",((BalType.BAL_AND_ACCRUE_INT,BalAsOf.COLL_BEG,),ValueType.RATE))
        (r"期初本息金额的占比",((BalType.BAL_AND_ACCRUE_INT,BalAsOf.COLL_BEG,),ValueType.RATE)),
        # 转存下期金额
        #(r"忽略字段",(META.IGNORE,ValueType.STR))
        (r"占比",(PoolType.PCT,ValueType.RATE)),
        (r"期初本息资金额的占比",(PoolType.PCT,ValueType.RATE)),
    ],
    'poolStrats':[
        (r"处置完毕", Status.LIQUIDATED),
        (r"本期处置完毕", Status.LIQUIDATED),
        (r"累计处置完毕.*", Status.LIQUIDATED), # 累计处置完毕(截至本期期末已结清)
        (r"处置中\(截至本期期末未结清\)", Status.IN_DISPOSAL),
        (r"处置中(资产)?", Status.IN_DISPOSAL),
        #处置中资产
        (r"\S?本期处置完毕资产", Status.LIQUIDATED),
        (r"·本期处置完毕资产", Status.LIQUIDATED),
        (r"累积至本期处置完毕", Status.LIQUIDATED),
        (r"本期累计处置完毕", Status.LIQUIDATED),
        (r"累计至本期处置完毕", Status.LIQUIDATED),
        (r"累计处置完毕资产", Status.LIQUIDATED),
        
    ],
    'asOfTypes':[
        (r"初始起算日封包时点", BalAsOf.CLOSING),
        (r"(报告)?基准日", BalAsOf.CLOSING),
        (r"本报告期期初", BalAsOf.CUR_BEG),
        (r"本报告期期末", BalAsOf.CUR_END),
        (r"本期报告期末", BalAsOf.COLL_END),
        (r"本期报告期初",BalAsOf.COLL_BEG),
        (r"本期报告期", BalAsOf.COLL_END),
        (r"截至本报告期末", BalAsOf.COLL_END),
        (r"未偿本息余额", BalAsOf.COLL_END),
        (r"a?初始起算日", BalAsOf.CLOSING),
        (r"\S?初始起算日\S+", BalAsOf.CLOSING),
        (r"上报告期期末\S+", BalAsOf.CUR_BEG), 
        (r"本报告期末\S*", BalAsOf.CUR_END),
        (r"本报告期初\S*", BalAsOf.CUR_BEG),
        
        # 本报告期末【】
        (r"\S注", META.IGNORE)
    ],
    'account':[
        (r"本报告期期末余额",((BalType.BAL_PRIN,BalAsOf.CUR_END),ValueType.MON)),
        (r"本期间期初余额",((BalType.BAL_PRIN,BalAsOf.CUR_BEG),ValueType.MON)),
        (r"本期期初余额",((BalType.BAL_PRIN,BalAsOf.CUR_BEG),ValueType.MON)),
        # 期初余额
        (r"期初余额",((BalType.BAL_PRIN,BalAsOf.CUR_BEG),ValueType.MON)),
        (r"期末余额",((BalType.BAL_PRIN,BalAsOf.CUR_END),ValueType.MON)),
        
        (r"本收款期期末余额",((BalType.BAL_PRIN,BalAsOf.COLL_END),ValueType.MON)),
        (r"本收款期间期末余额",((BalType.BAL_PRIN,BalAsOf.COLL_END),ValueType.MON)),
        (r"本期期末余额",((BalType.BAL_PRIN,BalAsOf.COLL_END),ValueType.MON)),
        (r"本期现金流分配后余额",((BalType.BAL_PRIN,BalAsOf.CUR_END),ValueType.MON)),
        (r"本收款期间期初余额",((BalType.BAL_PRIN,BalAsOf.COLL_BEG),ValueType.MON)),
        (r"本收款期间期末余额",((BalType.BAL_PRIN,BalAsOf.CUR_END),ValueType.MON)),
        (r"本计息期间期末余额",((BalType.BAL_PRIN,BalAsOf.CUR_END),ValueType.MON)),
        
        (r"本期收入",((Inflow.CASH_IN,),ValueType.MON)),
        (r"本期支出",((Outflow.CASH_OUT,),ValueType.MON))
        # 
        
    ],
    'fee':[
        (r"税收", FeeType.TAX),
        (r"税费", FeeType.TAX),
        (r"增值税及附加", FeeType.TAX),
        (r"代理兑付费用?", FeeType.AGENT),
        #(r"代理兑付费", FeeType.AGENT),
        (r"资金汇划费用?", FeeType.AGENT),
        (r"发行费用",FeeType.ISSUANCE),
        (r"承销费",FeeType.ISSUANCE),
        (r"承销费用",FeeType.ISSUANCE),
        (r"承销报酬",FeeType.ISSUANCE),
        (r"发行服务费用",FeeType.ISSUANCE),
        (r"主承销费\(含承销佣金\)",FeeType.ISSUANCE),
        (r"固定报酬",FeeType.ISSUANCE), # 资产服务机构报酬
        
        (r"受托机构报酬",FeeType.TRUSTEE),
        (r"信托手续费",FeeType.TRUSTEE),
        (r"资金保管机构报酬",FeeType.CASH_MGMT),
        (r"保管机构费用",FeeType.CASH_MGMT),
        (r"保管费",FeeType.CASH_MGMT),
        (r"处置费用", FeeType.DISPOSAL),
        
        (r"贷款服务机构报酬", FeeType.SERVICER),
        (r"贷款服务机构服务费", FeeType.SERVICER),
        (r"资产服务机构报酬", FeeType.SERVICER),
        (r"贷款服务费", FeeType.SERVICER),
        (r"服务报酬", FeeType.SERVICER),
        (r"基本服务费", FeeType.SERVICER),
        (r"基础服务费", FeeType.SERVICER),
        (r"贷款服务机构费", FeeType.SERVICER),
        (r"贷款服务机构资产管理服务费", FeeType.SERVICER),
        
        (r"兑付手续费", FeeType.AGENT),
        (r"银行划款手续费", FeeType.AGENT),
        (r"划款手续费", FeeType.AGENT),
        
        (r"账户管理费", FeeType.AGENT),
        (r"贷款服务机构基本服务费", FeeType.SERVICER),
        (r"执行费用利息$", f"{FeeType.OPERATION}_{FeeType.FEE_INT}"),
        (r"执行费用及对应的执行费用利息", f"{FeeType.OPERATION}_{FeeType.FEE_INT}"),
        (r"执行费用$", FeeType.OPERATION),
        (r"执行费用\(注1\)", FeeType.OPERATION),
        (r"尾包拍卖交易费", FeeType.OPERATION),
        (r"审计费",FeeType.AUDIT),
        (r"银行手续费",FeeType.BANK),
        (r"跟踪评级服务费",FeeType.RATING),
        (r"评级费",FeeType.RATING),
        (r"评级服务费",FeeType.RATING),
        (r"跟踪评级费",FeeType.RATING),
        (r"初始及跟踪评级服务费",FeeType.RATING),
        (r"初始评级服务费",FeeType.RATING),
        (r"其他费用.*",FeeType.OTHER),   
        (r"费用支出",FeeType.OTHER),  
        
        (r"流动性支持机构承诺费",FeeType.INSURANCE),
        (r"流动性支持承诺",FeeType.INSURANCE),
        (r"承诺费",FeeType.INSURANCE),
        (r"执行费用及执行费用利息", f"{FeeType.OPERATION}_{FeeType.FEE_INT}"),
        (r"流动性支持承诺费",FeeType.INSURANCE),
        (r"发行登记服务费",FeeType.ISSUANCE),
        (r"超额奖励服务费",FeeType.BONUS),
        (r"超级奖励服务费",FeeType.BONUS),
        (r"贷款服务机构超额奖励服务费",FeeType.BONUS),
        (r"跟踪审计费\(\d{4}年度\)",FeeType.AUDIT),
        (r"跟踪审计费",FeeType.AUDIT),
        (r"超额处置费用",FeeType.EXT_DISPOSAL),
        (r"法律服务费",FeeType.LEGAL),
        (r"律师费",FeeType.LEGAL),
        (r"律所报酬",FeeType.LEGAL),
        (r"法律顾问费",FeeType.LEGAL),
        (r"尾包处置法律服务费",FeeType.LEGAL),
        
        (r"非现金信托财产评估费",FeeType.VALUATION),
        (r"评估费",FeeType.VALUATION),
        (r"评估服务费",FeeType.VALUATION),
        (r"跟踪评估费",FeeType.VALUATION),
        (r"资产评估费",FeeType.VALUATION),
        (r"资产评估服务费",FeeType.VALUATION),
        (r"尾包处置评估费",FeeType.VALUATION),
        (r"评估机构报酬",FeeType.VALUATION),
        (r"会计顾问费",FeeType.AUDIT),
        (r"会计师",FeeType.AUDIT),
        (r"年度审计费",FeeType.AUDIT),
        (r"清算审计费",FeeType.AUDIT),
        (r"信托报酬",FeeType.TRUSTEE),
    ],
    'date':[
        (r"本[期次]支付日", (DateType.PAY_DATE,ValueType.DATE)),  # 本次支付日
        (r"本计息期支付日", (DateType.PAY_DATE,ValueType.DATE)),
        (r"信托设立日", (DateType.CLOSING_DATE,ValueType.DATE)),
        (r"初始起算日", (DateType.CLOSING_DATE,ValueType.DATE)),
        
        
        
        #(r"信托生效日", (DateType.CLOSING_DATE,ValueType.DATE)),
        (r"信托生效日", (DateType.CLOSING_DATE,ValueType.DATE)),
        (r"本期期初日", (DateType.COLL_BEG_DATE,ValueType.DATE)),
        (r"本报告期期初日", (DateType.COLL_BEG_DATE,ValueType.DATE)),
        (r"本收款期期初日\S*", (DateType.COLL_BEG_DATE,ValueType.DATE)),
        (r"本收款期期末日\S*", (DateType.COLL_END_DATE,ValueType.DATE)),
        (r"本报告收款期间期初日", (DateType.COLL_BEG_DATE,ValueType.DATE)),
        (r"本报告收款期间期末日", (DateType.COLL_END_DATE,ValueType.DATE)),
        (r"本期对应的收款期间期初日", (DateType.COLL_BEG_DATE,ValueType.DATE)),
        (r"本期对应的收款期间期末日", (DateType.COLL_END_DATE,ValueType.DATE)),
        #(r"本收款期期初日")
        #(r"收款期间期初日", (DateType.COLL_BEG_DATE,ValueType.DATE)),
        
        (r"本?收款期间期初日", (DateType.COLL_BEG_DATE,ValueType.DATE)),
        (r"本?收款期间期末日", (DateType.COLL_BEG_DATE,ValueType.DATE)),
        (r"本期期末日", (DateType.COLL_END_DATE,ValueType.DATE)),
        (r"本期初日", (DateType.COLL_BEG_DATE,ValueType.DATE)),
        (r"本期末日", (DateType.COLL_END_DATE,ValueType.DATE)),
        
        #(r"本报告期末日", (DateType.COLL_END_DATE,ValueType.DATE)),
        (r"本报告期期?初日", (DateType.COLL_BEG_DATE,ValueType.DATE)),
        (r"本报告期期?末日", (DateType.COLL_END_DATE,ValueType.DATE)),
        
        (r"本期起息日", (DateType.BOND_BEG_DATE,ValueType.DATE)),

        (r"本次证券计息期初日\S*", (DateType.BOND_BEG_DATE,ValueType.DATE)),
        (r"本计息期起息日\S*", (DateType.BOND_BEG_DATE,ValueType.DATE)),
        
        (r"本次证券计息期末日\S*", (DateType.BOND_END_DATE,ValueType.DATE)),
        (r"本计息期结息日\S*", (DateType.BOND_END_DATE,ValueType.DATE)),
        (r"本计息期计息日", (DateType.BOND_END_DATE,ValueType.DATE)),
        
        (r"本计息期期末日\S*", (DateType.BOND_END_DATE,ValueType.DATE)),
        
        
        (r"本次证券计息期期初日", (DateType.BOND_BEG_DATE,ValueType.DATE)),
        (r"本报告计息期间起息日", (DateType.BOND_BEG_DATE,ValueType.DATE)),
        
        (r"本报告计息期间结息日", (DateType.BOND_END_DATE,ValueType.DATE)),
        (r"本次证券计息期期末日", (DateType.BOND_END_DATE,ValueType.DATE)),
        (r"本期结息日", (DateType.BOND_END_DATE,ValueType.DATE)),
        (r"信托终止日", (DateType.END_DATE,ValueType.DATE)),
        (r"\S+注\d\S+", (META.IGNORE,ValueType.STR)),
    ]
}

def mapInternalKeys(ps:list, m:dict):
    ''' normalized keys of map
        {"bondbal":1} -> {"BOND_BAL":1}
    '''
    assert m is not None, "input map shall not be None"
    whiteList = {"赎回/信用卡债权笔数","赎回/信用卡债权金额","赎回/信用卡债权占比","占比","赎回/资产笔数"
                 ,"赎回/资产金额","赎回/资产占比",'','赎/信用卡债权笔数','赎/信用卡债权金额','赎/信用卡债权占比'
                 ,"累计_","赎回或替换/信用卡债权笔数","赎回或替换/信用卡债权金额","赎回或替换/信用卡债权占比"
                 ,"回购/贷款笔数","回购/贷款金额","回购/贷款占比","1、贷款情况","2、其他现金流流入"
                 ,"累计_1、贷款情况","累计_2、其他现金流流入","赎回/标的债权资产笔数","赎回/标的债权资产金额"
                 ,"赎回/标的债权资产占比","期初本息费金额的占比","金值(元)"
                 ,"回购或赎回/贷款笔数","回购或赎回/贷款金额","回购或赎回/贷款占比","不合格资产赎回","累计_不合格资产赎回"
                 ,"处置状态分布及现金流入","累计_处置状态分布及现金流入","期初未偿本息余额(注1)","回购/贷款本息余额"
                 ,"赎回/","期初本息资金额的占比","赎回或收购/资产笔数","赎回或收购/资产金额","赎回或收购/资产占比"
                 ,"期初未偿本息余额的占比","赎回和/或收购/信用卡债权笔数","赎回和/或收购/信用卡债权金额"
                 ,"赎回和/或收购/信用卡债权占比","赎回和/或收购/标的债权资产笔数","赎回和/或收购/标的债权资产金额"
                 ,"赎回和/或收购/标的债权资产占比","期初未偿本息金额的占比","总计(注2)","累计_总计(注2)"
                 ,"总计(注1)","累计_总计(注1)","赎回或收购/信用卡债权笔数","赎回或收购/信用卡债权金额"
                 ,"赎回或收购/信用卡债权占比","期初本息余额的占比","赎回或收购/标的债权资产笔数","赎回或收购/标的债权资产金额"
                 ,"赎回或收购/标的债权资产占比","赎回或替换/标的债权资产笔数","赎回或替换/标的债权资产金额"
                 ,"赎回或替换/标的债权资产占比","赎回或替换/资产笔数","总计(注)","累计_总计(注)","不合格资产赎回金额","累计_不合格资产赎回金额"
                 ,"不合格资产赎回金额3","累计_不合格资产赎回金额3","/","期初本息金额占比","期初户数的占比"}
    r = {}
    ## loop over the map
    for k,v in m.items():
        if k.startswith("赎回") or k.startswith("回购") or (k in whiteList):
            continue
        ## loop over the (regrex pattern , internal field )
        for (p,nk) in ps:
            #print("matching", k, "with", p)
            if re.match(p, k):
                r[nk] = v
                break
        else:
            raise RuntimeError(f"failed to map key <{k}> in {ps} ")
    return r

def productKeyToValues(m:dict, reverse=False):
    '''
      {"A":{"B":1,"C":2}} -> {("A","B"):1,("A","C"):2}
    '''
    r = {}
    for k,v in m.items():
        for (_k,ann),_v in v.items():
            if isinstance(_k,tuple):
                myKey = (k,*_k)
                if reverse:
                    r[(ann,myKey)] = _v
                else:
                    r[(myKey,ann)] = _v
            else:
                if reverse:
                    r[((_k,k),ann)] = _v
                else:
                    r[((k,_k),ann)] = _v
    return r

def fetchTblByFn(xs, fn):
    for x in xs:
        if fn(x):
            return x
    return None

def fetchTblItemByFnWithSub(xs, fn):
    for x in xs:
        if 'table_body' not in x:
            continue
        for y in x['table_body']:
            if fn(y):
                return x
    return None

def fetchTextByFn(xs, fn):
    for x in xs:
        if 'text' in x:
            if fn(x['text']):
                return x
    return None

def tryParseNumberIntCNEN(x):
    try:
        return int(x)
    except Exception as e:
        if convert is None:
            raise RuntimeError("the 'cnc' package is required to parse Chinese numerals")
        return convert.chinese2number(x)


def tfn(xs):
    ''' transpose a list of list '''
    return list(map(list, zip(*xs)))

def listToMapByKey(xs,k):
    ''' 
        lift a key from a list of dict, make it the map key
        ============== 
        xs -> [{"A":1,"B":2},{"A":3,"B":4}]
        k -> "A" 
        ==============
        return -> {1:{"B":2},3:{"B":4}}
    
    '''
    return {x[k]:tz.dissoc(x,k) for x in xs }

def listToMapByKeys(xs,ks):
    for k in ks:
        if all([ k in x for x in xs]):
            return listToMapByKey(xs,k)
    raise RuntimeError(f"failed to find key among {ks} in {xs} ")


def remove_at_index(lst, index):
    return lst[:index] + lst[index+1:]

def listToMapByIdx(xs, idx):
    return {x[idx]:remove_at_index(x, idx)    for x in xs }

def mergeTwoHeaders(h1,h2,how,symbol="/"):
    '''
        h1 -> ["A","B","C","D"]
        h2 -> ["","X1","X2","X3"]
        how -> [ (2,[0,1,2]) ]  # merge h2 
        
        return -> [ "A","B","C/","C/X1","C/X2","D" ]
    '''
    
    
    try:
        for (h1Index,h2Vals) in how:
            h1[h1Index] = [ f"{h1[h1Index]}{symbol}{h2[_]}" for _ in h2Vals ]
        return list(collapse(h1))
        
    except Exception as e:
        print("error when merging two headers")
        print("h1", h1)
        print("h2", h2)
        print("how", how)
        raise RuntimeError(e)

def patchNestTable(xs, l:int, trim=False):
    '''
        [ ['A','B','C'],[1,2] ] -> [ ['A','B','C'],['A',1,2]]
    '''
    assert len(xs) > 0, " table shall at least has 1 row"
    
    if trim:
        xs = [ _[:l] for _ in xs ]
    
    assert max([ len(_) for _ in xs]) == l, "max length should equal to L "

    header = xs[0]
    assert len(header)==l, "begin header shall have full size"
    r = [header]
    for x in xs[1:]:
        if len(x) == l:
            header = x
            r.append(x)
        if len(x) < len(header):
            patchElements = header[:(len(header) - len(x))]
            r.append(patchElements+x)
    return r



def get_val_by_keys(mapping, keys, default=None):
    """
    Get value from mapping using a list of keys.
    Returns the value for the first key found, or default if none found.
    
    {"A":1,"B":2}, ["C","A"] -> 1
    ---------------
    
    """
    for key in keys:
        if key in mapping:
            return mapping[key]
    return default

def sliceBetween(xs, startFn, endFn):
    rs = dropwhile(tz.complement(startFn), xs)
    r = takewhile(tz.complement(endFn), rs)
    return list(r)

def findCrossPage(yy, ss, es):
    rs = []
    for (l,r) in tz.sliding_window(2, [ _['table_body'] for _ in yy if 'table_body' in _]):
        y = tz.pipe(l + r
                , lambda xs: dropwhile(lambda x: not re.search(ss,x[0]), xs)
                , lambda xs: takewhile(lambda x: not re.search(es,x[0]), xs)
                , list)
        if y:
            rs.append(y)

    return rs[-1]

def firstMatch(fn, xs):
    ''' Fn, iterator '''
    for x in xs:
        if fn(x):
            return x
    return None


'''
{
"type":"text"
"text":"报告日期："
"page_idx":0
}
{
"type":"text"
"text":"中国对外经济贸易信托有限公司"
"page_idx":0
}
{
"type":"text"
"text":"2020年7月20日"
"page_idx":0
}


'''

def extractRptDate(lst):
    if (singleNode:=fetchTextByFn(lst, lambda z: re.search(r"报告日期：\s?(\S+?)日", z))):
        return tz.pipe(singleNode
                ,lambda y: re.search(r"报告日期：\s?(\S+日)", y['text']).groups()[0]
                ,parse
                )
    else:
        for (x,y,z) in tz.sliding_window(3, lst):
            match (x,y,z):
                case ({"type":"text","text":"报告日期：","page_idx":0},_,{"type":"text","text":_date,"page_idx":0}) if _date.endswith("日"):
                    return parse(_date)
                case _:
                    continue
        return None


def parseDict(m:dict):
    def parseValue(k,v):
        # balance type
        try:
            if k[-1] == ValueType.MON:
                if (r:=re.match(r"(.*)\(注\d\)",v)):
                    return parseValue(k, r.groups()[0])
                if v in ["/","=","","-","一","二","1",None,":","·","—","——","--","■","NA",'不适用']:
                    return None
                if v.endswith("万元") or v.endswith("万"):
                    return parseValue(k, str(float(v.replace(",","").rstrip("万元").rstrip("万"))*1e4))
                if v.endswith("亿元") or v.endswith("亿"):
                    return parseValue(k, str(float(v.replace(",","").rstrip("亿元").rstrip("亿"))*1e8))
                if v.endswith("元"):
                    return parseValue(k, v.rstrip("元"))
                if v.endswith("¹"):  #'103.90²'
                    return parseValue(k, v.rstrip("¹"))
                if v.endswith("²"):  #'103.90'
                    return parseValue(k, v.rstrip("²"))
                if v.startswith("k"):
                    return parseValue(k, v.lstrip("k"))
                if (z:=re.match(r"((?:\d*[\.,]\d*)*)\.(\d{1,2})",v)):
                    return float(z.groups()[0].replace(".","").replace(",","")) + float(z.groups()[1])/100
                return float(v.replace(",","").replace(" ",""))
            # coupon type
            if k[-1] == ValueType.RATE:
                if v in ["/","=","",'一','-','■','二','无','不适用','无票面利率','零息式','—','——','无固定利率','NA']:
                    return None
                #print("parsing",k,v)
                return float(v.replace("%",""))/100
            # int type
            if k[-1] == ValueType.INT:
                if v in ['','一','-','/','--']:
                    return None
                if v == "2/25":
                    return 2725
                if (z:=re.match(r"(\d+)[\(（]注\S+[\)）]",v.replace(",",""))):   # 48245(注1)
                    #print(" matched with ", z.groups())
                    return  int(z.groups()[0].replace(",",""))
                if (z:=re.match(r"(\d+)\[\d+\]",v.replace(",",""))): # 48245(注1)
                    #print(" matched with ", z.groups())
                    return  int(z.groups()[0].replace(",",""))
                if v.endswith("笔"):
                    return parseValue(k, v.rstrip("笔"))
                if v.endswith("户"):
                    return parseValue(k, v.rstrip("户"))
                return int(v.replace(".","").replace(",","").replace(" ",""))
            if k[-1] == ValueType.DATE:
                # （不含该日） 
                if v in ["/",None,"不适用","\\","=","",'一','-','--','——','—']:
                    return None
                _d = None
                if (r:=re.match(r"(.*)\s*（.*）\s?",v)):
                    _d = parse(r.groups()[0])
                    return _d.strftime("%Y-%m-%d")
                if (r:=re.match(r"(.*日)\d",v)):
                    _d = parse(r.groups()[0])
                    return _d.strftime("%Y-%m-%d")
                # 2023年4月30日(含该日)
                if (r:=re.match(r"(.*?日)\(",v)):
                    _d = parse(r.groups()[0])
                    return _d.strftime("%Y-%m-%d")                
                _d = parse(v)
                return _d.strftime("%Y-%m-%d")
            if k[-1] == ValueType.STR:
                return str(v)
            if k[-1] == ValueType.BOOL:
                if v in ["是","已足额兑付","足额兑付","对","√","yes","Yes","YES"]:
                    return True
                if v in ["否","未足额兑付","未兑付足额","不对","×","no","No","NO"]:
                    return False
                return None
            if isinstance(k, tuple):
                return parseValue(k[-1],v)
            return None
        except Exception as e:
            print("parsing error",k,v)
            raise RuntimeError("Parsing Error",e)

    #print("Parsing value of", m)
    return {_k:parseValue(_k,_v) for _k,_v in m.items() }

def modifyTable(x):
    return \
        json.loads(x) & lens.Each().Filter(lambda x:'table_body' in x)['table_body'].modify(readHtmlTblToList)\
                      & lens.Each().modify(lambda x: tz.dissoc(x, "bbox"))

def trans(x):
    ''' transform a key/value pair , remap the keys to human readable fields '''

    k,v = x

    if isinstance(v,dict):
        return (k, v & lens.Items().modify(trans))

    elif (not (isinstance(k[0], tuple))):
        return (dm[k[0]] ,v)

    elif isinstance(k[0],tuple):
        return ("_".join([ dm[_] for _ in collapse(k[0])]),v)
    else:
        raise RuntimeError(f"failed to trans with pair {k} {v}")

def babel(report):
    ''' convert intneral rep to human readable format '''
    return \
        report & lens['account'].Values().Items().modify(trans)\
               & lens['bond'].Values().Items().modify(trans)\
               & lens['pool'].Items().modify(trans)\
               & lens['fee'].Values().Items().modify(trans)\
               & lens['dates'].Items().modify(trans)
