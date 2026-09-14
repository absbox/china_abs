import re
from bidict import bidict,OnDup,OnDupAction
import pandas as pd
import sqlite3
from lenses import lens
from bs4 import BeautifulSoup
from more_itertools import transpose
import toolz as tz

from rich.console import Console
from rich.table import Table
console = Console()

m = [
    (("建元飞驰",""),"JYFC"),
    (("建元",""),"JIANYUAN"),
    (("福元",""),"FUYUAN"),
    (("瑞泽天驰",""),"RZTC"),
    (("农盈","个人住房"),"NONGYING"),
    (("工元乐居","个人住房"),"GYLJ"),
    (("工元安居","个人住房"),"GYAJ"),
    (("农盈汇寓","个人住房"),"NONGYINGHY"),
    (("中盈万家","个人住房"),"ZHONGYINGWANJIA"),
    (("安逸花","个人消费"),"ANYIHUA"),
    (("兴元","个人住房"),"XINGYUAN"),
    (("盛世融迪","个人汽车"),"SSRD"),
    (("速利银丰中国","个人汽车"),"SLYF"),
    (("吉时代","个人汽车"),"JSD"),
    (("长盈","个人汽车"),"CHANGYING"),
    (("汇聚融","个人汽车"),"HUIJURONG"),
    (("汇聚达","个人汽车"),"HUIJUDA"),
    (("融腾","个人汽车"),"RONGTENG"),
    (("融腾通元","个人汽车"),"RONGTENGTY"),
    (("长金","个人汽车"),"CHANGJIN"),
    (("唯盈","个人汽车"),"WEIYING"),
    (("瑞泽","个人汽车"),"RUIZE"),
    (("德宝天元","个人汽车"),"DBTY"),
    #(("德宝天元","汽车"),"DBTY"),
    (("德宝天元之信","个人汽车"),"DBTYZX"),
    (("丰耀","个人汽车"),"FENGYAO"),
    #(("华驭","个人汽车"),"HUAYU"),
    (("欣荣","个人汽车"),"XINRONG"),
    (("鼎柚","个人消费"),"DINGYOU"),
    (("和享","个人消费"),"HEXIANG"),
    (("招银和家","个人住房"),"ZYHJ"),
    (("工元至诚","不良资产"),"GYZC"),
    (("工元至诚普银","不良资产"),"GYZCPY"),
    (("工元至诚惠银","不良资产"),"GYZCHY"),
    
    (("鸿富",""),"HONGFU"),
    (("飞驰建融","(绿色)?信贷资产"),"FCJR"),
    (("隆和","微小企业贷款"),"LONGHE"),
    (("浦鑫归航",""),"PXGH"),
    (("招元和萃","不良资产"),"ZYHC"),
    (("工元","不良资产"),"GONGYUAN"),
    (("橙益","不良资产"),"CHENGYI"),
    (("臻粹","不良资产"),"ZHENCUI"),
    (("邮盈惠泽","不良资产"),"YYHZ"),
    (("惠元","不良"),"HUIYUAN"),
    (("邮盈惠兴","不良资产"),"YYHX"),
    (("福鑫","不良资产"),"FUXIN"),
    (("农盈利信众兴","不良资产"),"NYLXZX"),
    (("农盈利信远新","不良资产"),"NYLXYX"),
    (("农盈利信远诚","不良资产"),"NYLXYC"),
    (("中誉至诚","不良资产"),"ZYZC"),
    (("兴瑞","不良资产"),"XINGRUI"),
    (("建鑫","不良资产"),"JIANXIN"),
    (("永动","个人消费贷款"),"YONGDONG"),
    (("惠益","信用卡分期"),"HUIYI"),
    (("惠益","个人住房"),"HUIYIRMBS"),
    (("交元","信用卡分期"),"JIAOYUANCC"),
    (("捷赢","个人消费贷款"),"JIEYING"),
    (("开元","信贷资产支持证券"),"KAIYUAN"),
    (("开元铁路专项信贷",""),"KAIYUANTL"),
    (("中盈","个人住房"),"ZHONGYING_RMBS"),
    (("中盈","信贷资产"),"ZHONGYING_CLO"),
    (("中誉","不良资产"),"ZHONGYU"),
    (("中誉致信","不良资产"),"ZHONGYUZX"),
    (("农盈利信","不良资产"),"NYLX"),
    (("农盈利信惠众","不良资产"),"NYLXHZH"),
    (("农盈利信惠泽","不良资产"),"NYLXHZE"),
    (("农盈利信远弘","不良资产"),"NYLXYH"),
    (("农盈利信众合","不良资产"),"NYLXZH"),
    (("飞驰建普","微小企业贷款"),"FCJP"),
    (("飞驰建普","信贷资产"),"FCJPCL"),
    (("上和","(绿色)?个人汽车抵押贷款"),"SHANGHE"),
    (("和萃","不良资产"),"HECUI"),
    (("屹腾","个人汽车贷款"),"YITENG"),
    (("屹隆","个人汽车贷款"),"YILONG"),
    (("工元宜居","个人住房"),"GYYJ"),
    (("交诚","不良资产"),"JIAOCHENG"),
    (("兴银","信贷资产"),"XINGYIN"),
    (("兴晴","个人消费贷款"),"XINGQING"),
    (("兴惠","微小企业贷款"),"XINGHUI"),
    (("兴渝","微小企业贷款"),"XINGYU"),
    (("兴渝","个人住房"),"XINGYUMBS"),
    (("鑫宁","个人住房"),"XINNING_RMBS"),
    (("杭盈","个人住房"),"HANGYING"),
    (("工元","个人住房"),"GONGYUAN_RMBS"),
    (("杭诚","微小企业贷款"),"HANGCHENG"),
    (("杭邦","个人消费贷款"),"HANGBANG"),
    (("建欣","不良资产"),"JIANXIN2"),
    (("旭越","个人住房"),"XUYUE"),
    (("旭越惠诚","微小企业贷款"),"XYHUICHENG"),
    (("常兴业","微小企业贷款"),"CXY"),
    (("常星","个人消费贷款"),"CHANGXING"),
    (("幸福","个人消费贷款"),"XINGFU"),
    (("楚赢","个人消费贷款"),"CHUYING"),
    (("臻金","不良资产"),"ZHENJIN"),
    (("融享","个人住房"),"RONGXIANG"),
    (("邮元家和","个人住房"),"YYJIAHEMBS"),
    (("睿程","个人汽车(抵押贷款)?"),"RUICHENG"),
    (("爽誉","不良资产"),"SHUANGYU"),
    (("浦鑫安居","个人住房"),"PXAJ"),
    (("交盈","个人住房"),"JIAOYING"),
    (("招银和信","汽车分期贷款"),"ZYHX"),
    (("招银和智","个人消费贷款"),"ZYHZ"),
    (("够花","个人消费贷款"),"GOUHUA"),
    (("海鑫","个人消费贷款"),"HAIXIN"),
    (("江南","信贷资产"),"JIANGNAN"),
    (("上元","个人汽车抵押贷款"),"SHANGYUAN"),
    (("中赢","个人消费贷款"),"ZHONGYING"),
    (("中赢新易贷","个人消费贷款"),"ZYXYD"),
    (("中银","信贷资产"),"ZHONGYIN"),
    (("丰元","个人汽车"),"FENGYUAN"),
    (("汇聚通","个人汽车"),"HJT"),
    (("九银","信贷资产"),"JIUYIN"),
    (("交融","租赁资产"),"JIAORONG"),
    (("交银","信贷资产"),"JIAOYIN"),
    (("京元","信贷资产"),"JINGYUAN"),
    (("亲诚","信贷资产"),"QINCHENG"),
    (("众赢","信贷资产"),"ZHONGYING2_CLO"),
    (("住元","个人住房"),"ZHUYUAN"),
    (("信瑞","不良资产"),"XINRUI"),
    (("信融宜居","个人住房"),"XRYJ"),
    (("信融","个人住房"),"XINRONG_RMBS"),
    (("信银","信贷资产"),"XINYIN"),
    (("充银","信贷资产"),"CHONGYIN"),
    (("光盈","信贷资产"),"GUANGYING"),
    (("冀元","信贷资产"),"JIYUAN"),
    (("冀租稳健","租赁资产"),"JZWJ"),
    (("农银","信贷资产"),"NONGYIN"),
    (("创盈","个人住房"),"CHUANGYING"),
    (("创盈徽元","个人住房"),"CYHY"),
    (("富桂","信贷资产"),"FUGUI"),
    (("甬银",""),"YONGYIN"),
    (("海信","信贷资产"),"HAIXIN_CLO"),
    (("苏誉","不良资产"),"SUYU"),
    (("渤惠","微小企业贷款"),"BOHUI"),
    (("龙兴","不良资产"),"LONGXING"),
    (("泸银",""),"LUYIN"),
    (("盈风","个人汽车"),"YINGFENG"),
    (("鑫航",""),"XINHANG"),
    (("宁惠",""),"NINGHUI"),
    (("温兴",""),"WENXING"),
    (("鑫宁",""),"XINNING"),
    (("南银法巴",""),"NYFB"),
    (("三翊",""),"SANYI"),
    (("萧盈",""),"XIAOYING"),
    (("城一代",""),"CHENGYIDAI"),
    (("湘业",""),"XIANGYE"),
    (("温惠",""),"WENHUI"),
    (("润和",""),"RUNHE"),
    (("红棉广赢",""),"HONGMIAN"),
    (("张微融",""),"ZHANGWEIRONG"),
    (("吉湘",""),"JIXIANG"),
    (("建晟",""),"JIANSHENG"),
    (("鹭盈",""),"LUYING"),
    (("天盈",""),"TIANYING"),
    (("长融",""),"CHANGRONG"),
    (("温盈",""),"WENYING"),
    (("安顺",""),"ANSHUN"),
    (("融发",""),"RONGFA"),
    (("永惠",""),"YONGHUI"),
    (("工元致远",""),"GYZY"),
    (("京诚",""),"JINGCHENG"),
    (("瑞泽质享",""),"RZZX"),
    (("兴华",""),"XINGHUA"),
    (("邮赢惠泽",""),"YYHZ2"),
    (("邮赢",""),"YOUYING"),
    (("东元",""),"DONGYUAN"),
    (("连泰",""),"LIANTAI"),
    (("海盈",""),"HAIYING"),
    (("华通",""),"HUATONG"),
    (("莞鑫",""),"GUANXIN"),
    (("盛世迪耀",""),"SSDY"),
    (("温润",""),"WENRUN"),
    (("皖金",""),"WANJIN"),
    (("安元",""),"ANYUAN"),
    (("和衷",""),"HEZHONG"),
    (("钱江",""),"QIANJIANG"),
    (("兴银","疫情防控"),"XINGYIN_COVID"),
    (("盛世",""),"SHENGSHI"),
    (("金聚",""),"JINJU"),
    (("和智",""),"HEZHI"),
    (("锦融",""),"JINRONG"),
    (("农盈","不良资产"),"NONGYING_NPL"),
    (("安行",""),"ANXING"),
    (("乐融",""),"LERONG"),
    (("爽元",""),"SHUANGYUAN"),
    (("臻鑫",""),"ZHENXIN"),
    (("泰和",""),"TAIHE"),
    (("和信",""),"HEXIN"),
    (("阳光",""),"YANGGUANG"),
    (("飞驰建荣",""),"FCJR_GREEN"),
    (("汇通",""),"HUITONG"),
    (("屹昂",""),"YIANG"),
    (("苏租",""),"SUZU"),
    (("苏享盈",""),"SUXIANGYING"),
    (("浦鑫","信用卡"),"PUXIN_CC"),
    (("开元","信贷资产"),"KAIYUAN_CLO"),
    (("和家",""),"HEJIA"),
    (("家美",""),"JIAMEI"),
    (("广元",""),"GUANGYUAN"),
    (("居融",""),"JURONG"),
    (("企富",""),"QIFU"),
    (("龙居",""),"LONGJU"),
    (("招元",""),"ZHAOYUAN"),
    (("威元",""),"WEIYUAN"),
    (("招金",""),"ZHAOJIN"),
    (("金信",""),"JINXIN"),
    (("融汇",""),"RONGHUI"),
    (("安鑫",""),"ANXIN"),
    (("发元",""),"FAYUAN"),
    (("浦发机械",""),"PFJX"),
    (("恒丰",""),"HENGFENG"),
    (("江银",""),"JIANGYIN"),
    (("锦银",""),"JINYIN"),
    (("湘元",""),"XIANGYUAN"),
    (("渤银",""),"BOYIN"),
    (("成银",""),"CHENGYIN"),
    (("富瑞",""),"FURUI"),
    (("润元",""),"RUNYUAN"),
    (("永盈",""),"YONGYING"),
    (("天元",""),"TIANYUAN"),
    (("桂元",""),"GUIYUAN"),
    (("恒金",""),"HENGJIN"),
    (("金桥通诚",""),"JQTONGCHENG"),
    (("新锐",""),"XINRUI_CLO"),
    (("龙元",""),"LONGYUAN"),
    (("普盈",""),"PUYING"),
    (("蓝海",""),"LANHAI"),
    (("烟银",""),"YANYIN"),
    (("珠江",""),"ZHUJIANG"),
    (("包银",""),"BAOYIN"),
    (("安赢",""),"ANYING"),
    (("惠金",""),"HUIJIN"),
    (("锦源",""),"JINYUAN"),
    (("神融",""),"SHENRONG"),
    (("楚元",""),"CHUYUAN"),
    (("莞盈",""),"GUANYING"),
    (("紫鑫",""),"ZIXIN"),
    (("金鹿",""),"JINLU"),
    (("庆春",""),"QINGCHUN"),
    (("苏福",""),"SUFU"),
    (("粤鑫",""),"YUEXIN"),
    (("进元",""),"JINYUAN_CLO"),
    (("鼎信",""),"DINGXIN"),
    (("钱潮",""),"QIANCHAO"),
    (("建鑫租赁",""),"JIANXINZULIN"),
    (("泉融",""),"QUANRONG"),
    (("芙蓉",""),"FURONG"),
    (("九通",""),"JIUTONG"),
    (("工银海天",""),"GYHT"),
    (("浔银",""),"XUNYIN"),
    (("浙元",""),"ZHEYUAN"),
    (("华永",""),"HUAYONG"),
    (("龙居安盈",""),"LONGJUAY"),
    (("广汽汇通",""),"GQHT"),
    (("富安",""),"FUAN"),
    (("台银",""),"TAIYIN"),
    (("海元",""),"HAIYUAN"),
    (("徽行",""),"HUIHANG"),
    (("农银信贷",""),"NYXD"),
    #(("甬银",""),"YONGYIN")
    
    (("华驭",""),"HUAYU")
    #(("芙蓉",""),"FURONG")
]


#b = dict(m)
def getDealNameMap():
    b = bidict({})
    b.putall(m,on_dup=OnDup(key=OnDupAction.RAISE, val=OnDupAction.RAISE))
    return b

def sortBondBySeniority(xs):
    priority_order = {
        'senior': 1,
        'mezz': 2,
        'junior': 3,
    }

def nameChineseNameToDealId(fn:str):
    ''' 
        guess deal id from deal issuance file name:
        full name  -> deal id
        
    '''
    nMapping = dict(zip(["一","二","三","四","五","六","七","八","九","十"
                         ,"十一","十二","十三","十四","十五","十六","十七","十八"
                         ,"十九","二十","二十一","二十二","二十三","二十四","二十五","二十六","二十七","二十八"]
                        ,[1,2,3,4,5,6,7,8,9,10
                          ,11,12,13,14,15,16,17,18
                          ,19,20,21,22,23,24,25,26,27,28]))
    b = getDealNameMap()
    for (k,v) in b.items():
        
        (k0,k1) = k
        # 建欣2024年第十三期不良资产支持证券2025年度定期
        if (r:=re.search(k0+r"\d{2}(\d{2})年?第(\S+?)期"+k1,fn.replace(" ",""))):
            r = r.groups()
            return f"{r[0]}{v}{nMapping[r[1]]:02}"
        
        # 华驭第十六期汽车抵押贷款支持证券
        if (r:=re.search(k0+r"第(\S+?)期"+k1,fn.replace(" ",""))):
            r = r.groups()
            return f"{v}{nMapping[r[0]]:02}"
        
        # 2014年第二期农银信贷资产支持证券发行说明书.pdf 
        if (r:=re.search(r"\d{2}(\d{2})年第(\S+?)期"+k0,fn.replace(" ",""))):
            r = r.groups()
            return f"{r[0]}{v}{nMapping[r[1]]:02}"        
        
        
        
    raise RuntimeError(f"Failed to convert deal id from file name {fn}")     

def bondNameMapping(x):
    match x:
        case "次级档资产支持证券":
            return "C"

        case _:
            return None

def subMap(m,ks=[],default=None):
    if default is not None:
        return {k:m.get(k,default) for k in ks}
    else:
        return {k:m[k] for k in ks}

def convert_list_to_map(lst,k,v):
    return {item[k]: item[v] for item in lst}

def tblListToMap(lst):
    header,*rs = lst
    return [ dict(zip(header,x)) for x in rs]

def listOfMapToMap(lst, k, remove=True):
    if not remove:
        return {item[k]: item for item in lst}
    else:
        return {item[k]: { _k:_v for (_k,_v) in item.items() if _k != k } for item in lst}

def dropFieldInListOfMap(lst, field, dropFn=None):
    if all(map(dropFn, tz.pluck(field,lst))):
        return [ { _k:_v for (_k,_v) in item.items() if _k != field } for item in lst ]
    else:
        return lst
    

def tryToMatch(y:str, xs, capture=True):
    for x in xs:
        if (r:=re.search(x, y)):
            if capture:
                return r.groups()[0]
            else:
                return True
    return None

def tryToMatchBut(y:str, xs, but, capture=True):
    for x in xs:
        if (r:=re.search(x, y)) and (not (any([ re.search(b, y) for b in but ]))):
            #print("r>>", y, x , r , r.groups())
            if capture:
                return r.groups()[0]
            else:
                return True
    else:
        return None

def liftToDict(lst, keyField):
    return [ {keyField:item} for item in lst ]

def list2DictBy(lst, keyField):
    assert all([ keyField in item for item in lst ]), f"key field {keyField} not in all items {[ item for item in lst if keyField not in item]}"
    return { item[keyField]: item for item in lst }

def findFirstInMap(m,ks,default=None):
    for k in ks:
        if k in m:
            return m[k]
    if default is not None:
        return default
    raise RuntimeError(f"Failed to find any of {ks} in map {m}")

def getFirstKeyInMap(m,ks):
    for k in ks:
        if k in m:
            return k
    return None

def tblToMap(tbl):
    '''
        tbl: -> [[Col1,Val1,Val2],[Col2,Val3,Val4]]
        keyColumn -> Col1
        return : {Val1:{Col2:Val3},Val2:{Col2:Val4}}
    '''
    ks,*rs = transpose(tbl)
    vs = [ dict(zip(ks,r)) for r in rs ]
    return vs
    
def tryToMatch(y:str, xs, capture=True):
    for x in xs:
        if (r:=re.search(x, y)):
            if capture:
                return r.groups()[0]
            else:
                return True
    return None
    

def printableTbl(lst,title=""):
    '''
        lst: list of dict
    '''
    if len(lst)==0:
        return Table(title=title)
    headers = lst[0].keys()
    
    table = Table(title=title)

    for h in headers:
        table.add_column(h, justify="left", style="cyan", no_wrap=True)
        #table.add_column("Title", style="magenta")
        #table.add_column("Box Office", justify="right", style="green")

    for item in lst:
        vs = map(str,item.values())
        table.add_row(*vs)

    return table

def printTbl(lst,title=""):
    console.print(printableTbl(lst,title=title))

def readHtmlTblToList(html_string:str):
    soup = BeautifulSoup(html_string, 'html.parser')
    vals = [ [ __.get_text() for __ in _.select("td") ] for _ in soup.css.select("tr") ]
    vals &=  lens.Each().Each().modify(lambda y: y.replace(" ","").replace("\n",""))
    return vals


from dateutil.relativedelta import relativedelta
def get_month_diff(start_date, end_date):
    """
    计算两个日期之间的月份差
    返回：整数，可以是正数或负数
    """
    delta = relativedelta(end_date, start_date)
    # 计算总月份数 = 年份差 × 12 + 月份差
    months = delta.years * 12 + delta.months
    
    # 如果需要考虑天数影响（不足整月的情况）
    # 如果结束日期的天数 < 开始日期的天数，则月份数减1
    if delta.days < 0:
        months -= 1
    return months