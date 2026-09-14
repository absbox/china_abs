import toolz as tz
from htpy import span,i,fragment
from htmlUtil import iconText,toWan,toInt
from dateutil.relativedelta import relativedelta

statusMap = dict(zip((-1,1,2,3),('已取消','预发行','存续中','已清算')))
rateTypeMap = dict(zip(("fix",'floater',None),('固定利率','浮动利率','零息式')))
prinTypeMap = dict(zip(("schedule",'passthrough'),('固定摊还','过手摊还')))

# <i class="fa-regular fa-lock"></i>

assetClassMap = {
    "AUTO":"🚗汽车贷款" ,
    "RMBS":"🏠住房按揭" ,
    "CONSUMER":"🛍️消费贷款",
    "NPL":"⚠️不良资产",
    "SBL":"💼企业贷款", 
    "CREDIT":"💳信用卡",
    "CLO":"💼企业贷款",
    "LEASING":"💼融资租赁"
}

subAssetClassMap={
    "汽车分期":"🚗汽车贷款" ,
    "住房按揭": "🏠住房按揭", 
    "RMBS":"🏠住房按揭", 
    "消费贷款":"🛍️消费贷款",
    "Installment":"🛍️消费贷款",
    "CONSUMER":"🛍️消费贷款",
    "小微企业贷款":"💼企业贷款", 
    "SBL":"💼企业贷款", 
    "信用卡分期":"💳信用卡",
    "CC":"💳信用卡",
    '汽车按揭':"🚗汽车贷款",
    "信用卡分期/信用卡不良债权":"💳信用卡",
    "信用卡不良债权/信用卡分期":"💳信用卡",
    "CLO":"💼企业贷款",
    None:"TBD",
}

bondFieldMap ={
    "name":"债券名称"
    ,"bondID":"债券简称"
    ,"issueFace":"发行规模"
    ,"expectedMaturity":"预期到期"
    ,"prinType":"摊还方式"
    ,"rateType":"利率类型"
    ,"closingDate":"起息日期"
    ,"issueRate":"发行利率"
    ,"issuePrice":"发行价格"
    ,"curFactor":"剩余面额"
    ,"issueDate":"起息日期"
    ,"curBalance":"当前余额"
    ,"curRate":"当前利率"
    ,"paymentDate":"兑付日期"
    ,"currentBalance":"当前余额"
    ,"principal":"偿付本金"
    ,"currentRate":"本期利率"
    ,"interest":"本期利息"
    ,"interestYield":"超额收益"
    ,"cash":"本息合计"
    ,"updatePeriod":"兑付期数"
    ,"spread":"发行利差"
    ,"SHORTNAME":"债券简称"
    ,"EXPECT_MATURITY_DATE":"预期到期"
    ,"INT_TYPE":"利率类型"
    ,"ISSUE_DATE":"起息日期"
    ,"COUPON":"发行利率"
    ,"发行规模/金额":"发行规模"
    ,"偿付类型/方式":"偿付类型"
    ,"预期到期日":"预期到期"
    ,"code":"债券代码"
    ,'sn':"债券简称"
}

poolPerfMapNpl = {
    "EndPoolBalance": "期末池余额",
    "EndAssetCount": "期末资产数量",
    "RecoveryByProcess": "处置中资产",
    "RecoveryByLiquidated": "已处置资产",
    "Recovery": "回收金额",
    "CollectionPeriodBegin": "回收期初",
    "CollectionPeriodEnd": "回收期末",
}


ratingView = {
    
    "positiveView":"🟩 正面观点",
    "negativeView":"🟥 负面观点",
}


def toRate(x):
    if x is None:
        return "/"
    else:
        return f"{x*100:.2f}%"

def toSpread(x):
    if x is None:
        return "/"
    else:
        return f"{x*100:.2f}bps"


def toBalance(x, comma=False,toW=False):
    if x is None:
        return "/"
    else:
        x = float(x)/10000.00 if toW else float(x)
        if comma:
            return f"{x:,.2f}"
        else:
            return f"{x:.2f}"

balanceHandler = toWan
rateHandler = lambda x: f"{round(float(x) * 100.0, 2)} %" if x is not None else "/"

bondFieldDisplayHandler = {
    "currentBalance": toWan,
    "principal": balanceHandler,
    "interest": balanceHandler,
    "cash": balanceHandler,
    "issueFace": balanceHandler,
    "issueRate": rateHandler,
    "curRate": rateHandler,    
    "currentRate": rateHandler,
    "interestYield": toWan,
    "curBalance": toWan,
}

poolPerfMapNplHandler = {
    "EndPoolBalance": toWan,
    "EndAssetCount": toInt,
    "RecoveryByProcess": toWan,
    "RecoveryByLiquidated": toWan,
    "Recovery": toWan,
    "CollectionPeriodBegin": str,
    "CollectionPeriodEnd": str,
    "ARS":toRate,
}



@tz.curry
def applyMap(fnMap, m):
    for k,v in m.items():
        if k in fnMap:
            m[k] = fnMap[k](v)
    return m

displayBondField = applyMap(bondFieldDisplayHandler)
displayNplPoolPerfField = applyMap(poolPerfMapNplHandler)

dealFieldMap = {
    "period":"存续期数"
    ,"shortNameKey":"产品简称"
    ,"closingDate":"设立日期" 
    ,"endDate":"清算日"
    ,"poolType": "资产分类"
    ,"poolSubType": "二级分类"
    ,"stage":"产品阶段"
}

dealClearField = {
    "totalRecoveryAmt":"合计回收"
    ,"interestAmt":"合格投资"
    ,"callAmt":"回购收入"
}

statusMapClass = {
    "已公告":"hsl(141, 71%, 90%)",
    "已要约":"hsl(217, 71%, 90%)",
    #"已公告":"",
    "应急申购":"hsl(348, 100%, 61%)",
    "推迟发行":"hsl(48, 100%, 67%)",
    "申购要约":"hsl(217, 71%, 53%)",
    "已簿记":"hsl(217, 71%, 53%)",
    "已设立":"hsl(171, 100%, 41%)",
    "TBD":"hsl(0, 0%, 86%)",
}

agencyShortName = {
    "中诚信国际信用评级有限责任公司": "中诚信国际",
    "中债资信评估有限责任公司": "中债资信",
    "联合资信评估有限公司": "联合资信",
    "大公国际资信评估有限公司": "大公国际",
    "东方金诚国际信用评估有限公司": "东方金诚",
    "惠誉国际评级有限公司": "惠誉国际",
    "惠誉博华资信评估有限公司": "惠誉博华",
    "穆迪投资者服务公司": "穆迪",
    "标准普尔全球评级有限公司": "标普",
    "新世纪资信评估有限公司": "新世纪",
    "中证鹏元资信评估有限公司": "中证鹏元",
}



@tz.curry
def transMap(m, k):
    return m.get(k, None)

@tz.curry
def remapMapKey(km, m):
    ''' convert key of m according to km '''
    assert isinstance(km, dict), f"km must be a dict but got {km}"
    assert isinstance(m, dict), f"m must be a dict but got {m}"
    r = {}
    for k,v in m.items():
        if k in km:
            r[km[k]] = v 
        else:
            r[k] = v
    return r



def mergeSubdicts(*m):
    return tz.merge_with(tz.merge, *m)

def dateDiff(sd,ed,unit):
    diff = relativedelta(ed, sd)
    match unit:
        case "M":
            return diff.years * 12 + diff.months
        case "Y":
            return diff.years
        case "D":
            return (ed - sd).days
        
# 🔒

def getOrLock(o, path,icon="🔒"):
    return tz.get_in(path, o, default=icon)
    #return iconText(icon, path)
    
ratingList = [
    "AAA",
    "AA+",
    "AA",
    "AA-",
    "A+",
    "A",
    "A-",
    "BBB+",
    "BBB",
    "BBB-",
    "BB+",
    "BB",
    "BB-",
    "B+",
    "B",
    "B-",
    "CCC+",
    "CCC",
    "CCC-",
    "CC",
    "C",
    "D",
]