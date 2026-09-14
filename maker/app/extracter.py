from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class SchemaModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class AccountBalance(SchemaModel):
    BegBalance: Optional[float] = Field(default=None, description="账户期初余额")
    EndBalance: Optional[float] = Field(default=None, description="账户期末余额")


class TrusteeDateInfo(SchemaModel):
    collection: Optional[List[str]] = Field(
        default=None,
        description="收款期间[期初日,期末日]，格式[BegDate,EndDate]，均为YYYY-MM-dd；若收款期间已被划掉/留空则填null",
    )
    bond: Optional[List[str]] = Field(
        default=None, description="计息期间(起息日和结息日)[BegDate,EndDate]，格式均为YYYY-MM-dd；没有就留空"
    )
    payDate: Optional[str] = Field(default=None, description="支付日，单一日期，YYYY-MM-dd，非列表")
    dayCount: Optional[str] = Field(default=None, description="计息方式(DayCount)")
    reportDate: Optional[str] = Field(default=None, description="报告日期，YYYY-MM-dd")
    reportNumber: Optional[int] = Field(default=None, description="报告期数(产品成立以来报告的期数)，阿拉伯数字")


class TrusteeCallInfo(SchemaModel):
    callDate: Optional[str] = Field(default=None, description="清仓回购起算日，格式YYYY-MM-dd")
    callAmount: Optional[float] = Field(default=None, description="清仓回购价格/清仓回购兑付款/清仓回购金额")
    callBalance: Optional[float] = Field(default=None, description="清仓回购对应资产池余额")


class NplClassificationRow(SchemaModel):
    category: Optional[str] = Field(
        default=None, alias="分类", description="资产池五级分类名称，表头严格为'分类'"
    )
    ratio: Optional[float] = Field(
        default=None,
        alias="占资产池余额比例",
        description="该分类占资产池余额比例，单位要转换成小数(不是带百分号的百分比)，最终小数之和应为1.0，表头严格为'占资产池余额比例'",
    )


class PoolType(str, Enum):
    credit_card = "信用卡分期"
    consumer_loan = "消费贷款"
    auto_installment = "汽车分期"
    auto_mortgage = "汽车按揭"
    housing_mortgage = "住房按揭"
    small_business = "小微企业贷款"


class NplInitReport(SchemaModel):
    totalBalance: Optional[float] = Field(default=None, description="初始起算日未偿本息费余额")
    totalPrincipalBalance: Optional[float] = Field(
        default=None, description="初始起算日未偿本金余额，即不含利息或者不含手续费的金额"
    )
    poolType: Optional[PoolType] = Field(
        default=None,
        description="基础资产是什么贷款，必须严格从[信用卡分期,消费贷款,汽车分期,汽车按揭,住房按揭,小微企业贷款]中选择其一",
    )
    WaDueMonths: Optional[float] = Field(
        default=None,
        description="入池资产截至起算日的加权逾期月份，单位为月份；如源数据是天数需转换成月份",
    )
    ExpectRecovery: Optional[float] = Field(
        default=None,
        description="评级公司预计资产池回收总金额(或称毛回收金额，有时可用36/48个月内的毛回收金额代替)；若只有毛回收率则用毛回收率乘以totalBalance；存在多个预计回收率时选基准假设/正常场景回收率，禁止使用压力情景(如AAA场景)下较低的回收率",
    )
    AvgBalance: Optional[float] = Field(
        default=None,
        description="资产池平均单个债权余额；如存在预计整体回收分布情况表格，直接取表格的合计金额",
    )
    classify: Optional[List[NplClassificationRow]] = Field(
        default=None, description="底层资产池按五级分类的资产余额比例表，表头为[分类,占资产池余额比例]"
    )


class BondInitInfo(SchemaModel):
    name: Optional[str] = Field(
        default=None, alias="债券名称", description="债券名称，较为简短(如优先级/次级/优先档/次级档/A1/A2)，不包含整个产品名字"
    )
    size: Optional[float] = Field(
        default=None,
        alias="发行规模/金额",
        description="发行规模/金额，多个债券发行规模总和应与产品总体发行规模一致",
    )
    payoff: Optional[str] = Field(
        default=None, alias="偿付类型/方式", description="偿付类型/方式，只有'固定摊还'(约定了偿付计划)和'过手摊还'两种"
    )
    rate_type: Optional[str] = Field(
        default=None,
        alias="利率类型",
        description="利率类型，分为固定利率和浮动利率两种；浮动利率需注明其基准利率和利差(如有)",
    )
    expected_maturity: Optional[str] = Field(default=None, alias="预期到期日", description="预期到期日，格式YYYY-MM-dd")
    credit_rating: Optional[str] = Field(default=None, alias="信用等级", description="信用等级")
    credit_enhancement: Optional[float] = Field(
        default=None, alias="信用增级/信用支持比例", description="信用增级/信用支持比例"
    )


class WaterfallStep(SchemaModel):
    source: Optional[str] = Field(
        default=None, alias="分配资金来源", description="现金流分配的分配资金来源"
    )
    target: Optional[str] = Field(default=None, alias="分配资金去向", description="现金流分配的分配资金去向")
    amount: Optional[str] = Field(
        default=None, alias="分配资金金额和计算方式", description="现金流分配的分配资金金额和计算方式"
    )
    method: Optional[str] = Field(
        default=None,
        alias="分配方式",
        description="分配方式：若存在多个支付对象，这些对象之间是顺序支付还是按比例支付",
    )


class CreditEnhancement(SchemaModel):
    per: Optional[float] = Field(
        default=None, description="资产池债权中有抵押物的债权余额占比"
    )
    coll: Optional[str] = Field(default=None, description="抵押物的具体内容总结")


class GenInitReport(SchemaModel):
    cutoffdate: Optional[str] = Field(default=None, description="资产池初始起算日，格式YYYY-MM-dd")
    closingdate: Optional[str] = Field(
        default=None, description="信托拟订成立日/债券发行日/起息日/预计设立日，格式YYYY-MM-dd"
    )
    freq: Optional[str] = Field(
        default=None,
        description="债券的付款频率周期，可选[每月,每两个月,季度,半年度,年度]；找不到宁留null不要瞎猜",
    )
    statedDate: Optional[str] = Field(default=None, description="法定到期日，格式YYYY-MM-dd")
    reserveAccount: Optional[str] = Field(
        default=None,
        description="流动性储备账户(不是混同储备账户)的现金流入流出规则，特别是初始余额以及必备流动性储备金额的计算方式",
    )
    poolBalance: Optional[float] = Field(default=None, description="初始资产池余额")
    bonds: Optional[List[BondInitInfo]] = Field(
        default=None, description="债券信息表格，表头[债券名称,发行规模/金额,偿付类型/方式,利率类型,预期到期日(格式YYYY-MM-dd),信用等级,信用增级/信用支持比例]，表头作为列表的第一个元素；债券至少2个"
    )
    originator: Optional[str] = Field(default=None, description="原始权益人/发起人/委托/发起机构")
    underwriter: Optional[str] = Field(default=None, description="主要承销商")
    issuer: Optional[str] = Field(default=None, description="发行机构/管理人机构")
    servicer: Optional[str] = Field(default=None, description="贷款服务机构")
    ratingDate: Optional[str] = Field(default=None, description="评级报告日，格式YYYY-MM-dd")
    waterfall: Optional[List[WaterfallStep]] = Field(
        default=None,
        description="现金流分配顺序规则(只搜集违约前/未违约/正常情况下的分配顺序)，每个元素是一次分配步骤，含分配资金来源/去向/金额和计算方式/分配方式",
    )
    collected: Optional[List[Union[str, float]]] = Field(
        default=None, description="资产池已回收金额，格式[<date>,<amount>]，date为截止日期(格式YYYY-MM-dd)"
    )
    positiveView: Optional[List[str]] = Field(
        default=None, description="关于产品的正面/优势评级信息列表，每个正面因素一个元素；涉及金额统一转换为万元"
    )
    negativeView: Optional[List[str]] = Field(
        default=None, description="关于产品的负面/关注评级信息列表，每个负面因素一个元素；涉及金额统一转换为万元"
    )
    ce: Optional[CreditEnhancement] = Field(default=None, description="资产池抵押物信息")
    juniorRate: Optional[float] = Field(
        default=None, description="次级'固定资金成本'或有关次级利率的描述"
    )
    reportDate: Optional[str] = Field(default=None, description="本报告的评级报告日，格式YYYY-MM-dd")


class PoolInitBase(SchemaModel):
    poolType: Optional[str] = Field(default=None, description="基础资产是什么贷款")
    originatorBalance: Optional[float] = Field(
        default=None, description="发起机构的存量零售信贷资产总额"
    )
    originatorDelinqRate: Optional[float] = Field(
        default=None, description="发起机构的零售信贷资产不良率"
    )
    AaaOcRate: Optional[float] = Field(default=None, description="AAA证券信用增级比例")
    AssetNum: Optional[int] = Field(default=None, description="贷款笔数")
    totalBalance: Optional[float] = Field(default=None, description="初始起算日未偿本金余额")
    totalFaceValue: Optional[float] = Field(default=None, description="初始起算日资产池合同金额")
    AvgFaceBalance: Optional[float] = Field(default=None, description="单笔贷款平均合同金额")
    AvgBalance: Optional[float] = Field(default=None, description="单笔贷款平均余额")
    AvgCoupon: Optional[float] = Field(default=None, description="加权平均贷款利率")
    AvgTotalTerm: Optional[float] = Field(default=None, description="加权平均合同期限，转换为月作为单位")
    AvgRemainTerm: Optional[float] = Field(default=None, description="加权平均剩余期限，转换为月作为单位")
    ITL: Optional[float] = Field(default=None, description="加权收入债务比")


class AutoInitReport(PoolInitBase):
    AvgAging: Optional[float] = Field(default=None, description="加权平均贷款账龄，转换为月作为单位")
    LTV: Optional[float] = Field(default=None, description="加权平均贷款价值比")
    InitPayRate: Optional[float] = Field(default=None, description="加权平均贷款首付比例")


class ConsumerInitReport(PoolInitBase):
    AssetAvgAging: Optional[float] = Field(
        default=None, description="加权平均贷款账龄，转换为月作为单位"
    )
    BorrowerAvgAging: Optional[float] = Field(
        default=None, description="加权平均借款人年龄，转换为月作为单位"
    )
    ITL: Optional[float] = Field(default=None, description="加权平均借款人收入债务比例")


class SblInitReport(PoolInitBase):
    AssetAvgAging: Optional[float] = Field(
        default=None, description="加权平均贷款账龄，转换为月作为单位"
    )
    ITL: Optional[float] = Field(default=None, description="加权平均借款人收入债务比例")


class BondPlanInfo(SchemaModel):
    name: Optional[str] = Field(
        default=None,
        description="债券名称；尽量去除'资产支持证券'字样、'xxxx年第yy期'字样以及产品名字的前缀(如'招元和萃2026年第四期')，保持简洁",
    )
    issueSize: Optional[float] = Field(default=None, description="债券发行规模，换成元作为单位")
    allocatedAmount: Optional[float] = Field(
        default=None, description="配售金额，换成元作为单位，配售金额可能是0"
    )
    rate: Optional[str] = Field(
        default=None, description="发行利率，固定利率/浮动利率/零息式三种，必须从中选择一种"
    )
    avgLife: Optional[float] = Field(
        default=None,
        description="预计加权平均期限，转换成年作为单位(去掉'年'字)；多情景时选择'0违约0早偿'场景的单一数值",
    )


class PlanReport(SchemaModel):
    annDate: Optional[str] = Field(default=None, description="产品公告日，格式YYYY-MM-dd")
    bookDate: Optional[str] = Field(default=None, description="簿记建档日，格式YYYY-MM-dd")
    salesDate: Optional[str] = Field(
        default=None, description="分销日；如是区间则选取开始日，确保是单一日期，格式YYYY-MM-dd"
    )
    cutoffDate: Optional[str] = Field(default=None, description="缴款截止日，格式YYYY-MM-dd")
    bondStartDate: Optional[str] = Field(default=None, description="起息日，格式YYYY-MM-dd")
    closingDate: Optional[str] = Field(default=None, description="信托设立日，格式YYYY-MM-dd")
    payDate: Optional[str] = Field(default=None, description="支付日，是描述债券支付日期的规则，日期格式YYYY-MM-dd")
    payFreq: Optional[str] = Field(default=None, description="债券偿付的频率，用文字描述")
    firstPay: Optional[str] = Field(default=None, description="首次支付日，格式YYYY-MM-dd")
    dealName: Optional[str] = Field(default=None, description="资产支持证券名称")
    originator: Optional[str] = Field(default=None, description="发起机构")
    issuer: Optional[str] = Field(default=None, description="发行人")
    booker: Optional[str] = Field(default=None, description="簿记管理人")
    bonds: Optional[List[BondPlanInfo]] = Field(
        default=None, description="债券列表[name,issueSize,allocatedAmount,rate,avgLife]；产品通常至少有两个或以上证券，勿遗漏"
    )


class PricingBondInfo(SchemaModel):
    BONDNAME: Optional[str] = Field(default=None, description="证券名称，需把空格剔除掉")
    SHORTNAME: Optional[str] = Field(default=None, description="证券简称，需把空格剔除掉")
    CODE: Optional[str] = Field(default=None, description="证券代码")
    EXPECT_MATURITY: Optional[str] = Field(default=None, description="预期到期日，格式YYYY-MM-dd，可能不存在则填null")
    WAL: Optional[float] = Field(default=None, description="加权平均期限，可能不存在则填null")
    INT_TYPE: Optional[str] = Field(
        default=None, description="计息方式，固定利率/浮动利率/零息式三种"
    )
    ISSUE_DATE: Optional[str] = Field(default=None, description="发行日(也可能叫起息日)，格式YYYY-MM-dd")
    PLAN_AMT: Optional[float] = Field(
        default=None, description="计划发行总额，换成元作为单位"
    )
    ISSUE_AMT: Optional[float] = Field(
        default=None, description="实际发行总额，换成元作为单位，其中配售金额可能是0"
    )
    ISSUE_PRICE: Optional[float] = Field(
        default=None,
        description="发行价格，取数字即可不要中文字符(数字大约在100左右)；如果不配售/不适用则价格可能为null",
    )
    ISSUE_COUPON: Optional[float] = Field(
        default=None,
        description="票面利率，转换成小数(如2.45%读成0.0245)；零息式或者不适用则写null",
    )


class PricingAnnReport(SchemaModel):
    annDate: Optional[str] = Field(
        default=None, description="报告的公告日期(通常位于最后一页)，格式YYYY-MM-dd，可能解析不出来就写null"
    )
    bonds: Optional[List[PricingBondInfo]] = Field(
        default=None, description="债券发行结果列表"
    )


class ClearReportBase(SchemaModel):
    startDate: Optional[str] = Field(default=None, description="产品起始日，信托成立日，格式YYYY-MM-dd")
    endDate: Optional[str] = Field(
        default=None, description="产品结束日期/信托终止日/信托清算日/提前终止日，格式YYYY-MM-dd"
    )
    reportDate: Optional[str] = Field(
        default=None, description="报告编撰的日期/清算报告发布日期，格式YYYY-MM-dd"
    )
    callDate: Optional[str] = Field(
        default=None,
        description="清仓回购日期，格式YYYY-MM-dd；如报告没有提到或没有清仓回购事项则留null",
    )


class NplClearReport(ClearReportBase):
    totalRecoveryAmt: Optional[float] = Field(
        default=None,
        description="从资产池总共回收本金和利息的总和；报告单独列示本金回收款和利息回收款时求和合并抓取。注意这不是'投资收益'，不含清仓回购/不合格资产赎回/合格投资/银行利息收入/信托结息等收入，这里的'利息'不是银行利息收益(勿与interestAmt混淆)",
    )
    interestAmt: Optional[float] = Field(
        default=None,
        description="活期投资/合格投资/银行利息收益/活期存款利息/账户结息收入",
    )
    callAmt: Optional[float] = Field(
        default=None,
        description="清仓回购金额(信托财产变现产生的现金流入)，描述着原始权益人付钱从产品中回购资产池内剩余资产的款项；严格按字面和相近字面抓取，不展开联想推理；找不到就填null。绝非证券本金余额/利息收益金额，也绝非任何费用",
    )
    buyBack: Optional[float] = Field(default=None, description="不合格资产赎回款项；找不到就留null")
    outflow: Optional[Dict[str, Any]] = Field(
        default=None,
        description="项目支出总和统计：各项税费支出(有明细则列出明细，无明细则列示总和，不要瞎猜明细金额)，用中文字段作为字段名称；债券支出也需要明细(证券利息支出，本金支出，次级档收益，次级固定资金成本)；outflow下不需要嵌套结构，直接用字段/数值对表示",
    )
    residualPlan: Optional[str] = Field(
        default=None,
        description="结余资金/剩余资金信息：结余金额，分成比例，各自分了多少钱；也可能全部给了次级投资人",
    )
    feeCalc: Optional[str] = Field(
        default=None,
        description="管理费和税费(包括但不限于受托机构报酬、贷款服务费)的描述中的计算规则",
    )


class TrusteeReportBase(SchemaModel):
    accounts: Optional[Dict[str, AccountBalance]] = Field(
        default=None,
        description="各账户信息，账户名称为key，字段为期初余额(BegBalance)和期末余额(EndBalance)；增信信息/储备账户信息也需合并进入",
    )
    date: Optional[TrusteeDateInfo] = Field(default=None, description="日期信息汇总")
    call: Optional[TrusteeCallInfo] = Field(default=None, description="清仓回购信息")


class TrusteeNplBondInfo(SchemaModel):
    secCode: Optional[str] = Field(default=None, description="债券代码，一组数字")
    onTime: Optional[bool] = Field(default=None, description="是否按时兑付")
    rate: Optional[float] = Field(default=None, description="票面利率")
    begBalance: Optional[float] = Field(
        default=None,
        description="本期兑付前债券本金总余额；是兑付本金前后的总余额(勾稽关系begBalance-repay=endBalance)，绝对不是债券的'发行总额'，也绝非'每百元面额'之类的余额表示；若兑付前本金用百元面额表达则填null",
    )
    repay: Optional[float] = Field(
        default=None,
        description="本期兑付的本金数额；若本金用百元面额表达，则填本期兑付本金总额(元)数值",
    )
    endBalance: Optional[float] = Field(
        default=None,
        description="本期兑付后债券本金总余额(勾稽关系begBalance-repay=endBalance)，绝对不是债券的'发行总额'，也绝非'每百元面额'之类的余额表示；若兑付后本金用百元面额表达则填null",
    )
    downFactor: Optional[float] = Field(
        default=None,
        description="本期兑付本金比例值；是小于100的数字，单位是元/百元面额，表示债券摊销了多少面额比例",
    )
    interest: Optional[float] = Field(default=None, description="本期优先级和次级的付息金额")
    onTimeInterest: Optional[bool] = Field(default=None, description="本期利息是否按时支付")
    JuiniorInterest: Optional[float] = Field(
        default=None, description="次级/次级档债券利息细分项：次级固定资金成本"
    )
    JuniorYield: Optional[float] = Field(
        default=None, description="次级/次级档债券利息细分项：次级超额收益"
    )


class TrusteeNplPoolInfo(SchemaModel):
    IssuancePoolBalance: Optional[float] = Field(
        default=None, description="起算日资产池本息费总余额"
    )
    IssuanceAssetCount: Optional[int] = Field(default=None, description="起算日债权总笔数")
    EndPoolBalance: Optional[float] = Field(
        default=None, description="当期期末资产池本息费总余额"
    )
    EndAssetCount: Optional[int] = Field(default=None, description="当期期末债权总笔数")
    ProcessAssetCount: Optional[int] = Field(
        default=None, description="资产处置状态为'处置中'的户数/债权数量"
    )
    ProcessBalance: Optional[float] = Field(
        default=None, description="资产处置状态为'处置中'的余额"
    )
    LiquidatedAssetCount: Optional[int] = Field(
        default=None, description="处置完毕/已经清算的户数/债权数量"
    )
    LiquidatedBalance: Optional[float] = Field(
        default=None, description="处置完毕/已经清算的余额"
    )


class TrusteeNplInflow(SchemaModel):
    reinvestment: Optional[float] = Field(
        default=None, description="合格投资；指当期流入的金额，不是累积值"
    )
    other: Optional[float] = Field(
        default=None, description="其他收入；指当期流入的金额，不是累积值"
    )
    ProcessIncome: Optional[float] = Field(
        default=None, description="本期处置中资产回收金额"
    )
    LiquidatedIncome: Optional[float] = Field(
        default=None, description="本期处置完毕资产回收金额"
    )
    ProcessIncomeTotal: Optional[float] = Field(
        default=None, description="累计回收的处置中资产回收金额"
    )
    LiquidatedIncomeTotal: Optional[float] = Field(
        default=None, description="累计回收的本期处置完毕资产金额"
    )
    PoolInflow: Optional[float] = Field(
        default=None,
        description="资产池处置回收总额，为计算值(=ProcessIncome+LiquidatedIncome)，inflow里一定要有该字段",
    )
    PoolInflowTotal: Optional[float] = Field(
        default=None,
        description="累计处置回收总额，为计算值(=ProcessIncomeTotal+LiquidatedIncomeTotal)，inflow里一定要有该字段",
    )


class TrusteeNplOutflow(SchemaModel):
    Principal: Optional[float] = Field(default=None, description="证券兑付本金")
    SeniorInterest: Optional[float] = Field(default=None, description="优先档兑付利息")
    JuniorInterest: Optional[float] = Field(default=None, description="次级档固定资金成本")
    JuniorYield: Optional[float] = Field(default=None, description="次级档超额收益")
    Interest: Optional[float] = Field(
        default=None, description="债券利息；若次级档未披露明细，报告仅披露债券本金和利息时使用"
    )


class TrusteeNplReport(TrusteeReportBase):
    bonds: Optional[Dict[str, TrusteeNplBondInfo]] = Field(
        default=None, description="资产支持证券本息兑付情况，以债券代码(secCode)作为key"
    )
    pool: Optional[TrusteeNplPoolInfo] = Field(default=None, description="资产池描述情况")
    inflow: Optional[TrusteeNplInflow] = Field(default=None, description="现金流流入情况")
    outflow: Optional[TrusteeNplOutflow] = Field(
        default=None, description="现金流流出情况；字段名称即为税费的科目"
    )


class SeqRatingReport(SchemaModel):
    agency: Optional[str] = Field(default=None, description="做出评级的评级公司名字")
    ratingDate: Optional[str] = Field(default=None, description="跟踪评级报告日，格式YYYY-MM-dd")
    bonds: Optional[Dict[str, str]] = Field(
        default=None,
        description="评级公司对债券和对应的信用评级结论，key/字段名是债券名字，value是对应的信用评级符号",
    )
    positiveView: Optional[List[str]] = Field(
        default=None, description="评级背后的正面/优势因素列表"
    )
    negativeView: Optional[List[str]] = Field(
        default=None, description="评级背后的负面/关注因素列表"
    )
    bondDate: Optional[str] = Field(default=None, description="债券跟踪基准日/计算日，格式YYYY-MM-dd")
    poolDate: Optional[str] = Field(default=None, description="资产池跟踪基准日/计算日，格式YYYY-MM-dd")
    raingPeriod: Optional[List[str]] = Field(
        default=None, description="评级跟踪期间，格式为[YYYY-MM-dd,YYYY-MM-dd]"
    )


class TrusteeAutoBondInfo(SchemaModel):
    secCode: Optional[str] = Field(default=None, description="债券代码，一组数字")
    rate: Optional[float] = Field(default=None, description="票面利率")
    begBalance: Optional[float] = Field(
        default=None,
        description="本期兑付前债券本金总余额；是兑付本金前后总余额(勾稽关系begBalance-repay=endBalance)，绝对不是'发行总额'或'每百元面额'；若用百元面额表达则填null",
    )
    repay: Optional[float] = Field(
        default=None,
        description="本期兑付的本金数额；若本金用百元面额表达，则填本期兑付本金总额(元)数值",
    )
    endBalance: Optional[float] = Field(
        default=None,
        description="本期兑付后债券本金总余额(勾稽关系begBalance-repay=endBalance)，绝对不是'发行总额'或'每百元面额'；若用百元面额表达则填null",
    )
    downFactor: Optional[float] = Field(
        default=None,
        description="本期兑付本金比例值(表格名可能是'每100元支付本金')；是小于100的数字，单位是元/百元面额",
    )
    interest: Optional[float] = Field(
        default=None, description="本期的付息金额；注意不是每百元支付利息"
    )
    rating: Optional[str] = Field(default=None, description="证券评级(如有)")


class TrusteeAutoPoolStat(SchemaModel):
    balance: Optional[float] = Field(default=None, description="当期未偿本金余额")
    avgCoupon: Optional[float] = Field(default=None, description="当期加权平均利率")
    avgAge: Optional[float] = Field(default=None, description="当期加权平均账龄")
    avgRemainTerm: Optional[float] = Field(default=None, description="当期加权平均剩余期限")


class TrusteeAutoPoolInfo(SchemaModel):
    perf: Optional[Dict[str, Any]] = Field(
        default=None,
        description="整体表现情况，用抵押状态(如正常/逾期N天/回购)作为key，对应金额作为value",
    )
    process: Optional[Dict[str, Any]] = Field(
        default=None,
        description="资产池逾期处置状态信息(如有)，用处置状态(如经处置无拖欠/诉讼准备/受理程序/拍卖程序/经处置已核销等)作为key，对应逾期贷款金额作为value",
    )
    newDefault: Optional[float] = Field(
        default=None, description="当期新增违约贷款的余额(有多项则合并余额)"
    )
    delinquenceRate: Optional[float] = Field(
        default=None,
        description="当期严重拖欠率；单一数值，报告列举过去所有期数时只抓取当前期数",
    )
    defaultRate: Optional[float] = Field(
        default=None,
        description="当期累计违约率；单一数值，报告列举过去所有期数时只抓取当前期数",
    )
    projectCashflow: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="现金流归集表整理成列表，列表中每个元素用字典方式标注表头",
    )
    stat: Optional[TrusteeAutoPoolStat] = Field(
        default=None, description="按基础资产总体情况描述构造的stat对象"
    )


class TrusteeAutoInflow(SchemaModel):
    schedule: Optional[float] = Field(default=None, description="正常回收，当期流入金额")
    prepay: Optional[float] = Field(default=None, description="提前偿还，当期流入金额")
    delinq: Optional[float] = Field(default=None, description="拖欠回收，当期流入金额")
    default: Optional[float] = Field(default=None, description="违约回收，当期流入金额")
    reinvestment: Optional[float] = Field(default=None, description="合格投资，当期流入金额")
    other: Optional[float] = Field(default=None, description="其他收入，当期流入金额")
    buyBack: Optional[float] = Field(default=None, description="不合格资产赎回，当期流入金额")
    call: Optional[float] = Field(default=None, description="清仓回购，当期流入金额")


class TrusteeAutoOutflow(SchemaModel):
    service: Optional[float] = Field(default=None, description="服务总费用")
    VAT: Optional[float] = Field(default=None, description="增值税")
    VatAddon: Optional[float] = Field(default=None, description="增值税附加")
    other: Optional[float] = Field(default=None, description="其他费用")
    bondInterest: Optional[float] = Field(default=None, description="证券利息")
    bondPrincipal: Optional[float] = Field(default=None, description="债券本金")
    yield_: Optional[float] = Field(default=None, alias="yield", description="次级档超额收益")
    buy: Optional[float] = Field(default=None, description="循环购买支出")


class TrusteeAutoReport(TrusteeReportBase):
    bonds: Optional[Dict[str, TrusteeAutoBondInfo]] = Field(
        default=None, description="资产支持证券本息兑付情况，以证券名称为key"
    )
    pool: Optional[TrusteeAutoPoolInfo] = Field(default=None, description="资产池描述情况")
    inflow: Optional[TrusteeAutoInflow] = Field(
        default=None,
        description="现金流流入情况；各字段可能是当期流入的金额(非累积值)，从收入分账户/本金分账户或利息/本金/违约金等子科目累加合并抓取",
    )
    outflow: Optional[TrusteeAutoOutflow] = Field(default=None, description="现金流流出情况")


class TrusteeAutoBuyReport(SchemaModel):
    buyDate: Optional[str] = Field(default=None, description="循环购买日期，格式YYYY-MM-dd")
    period: Optional[int] = Field(default=None, description="第几次进行购买，用阿拉伯数字表示")
    buyBalance: Optional[float] = Field(default=None, description="购买金额")
    type: Optional[str] = Field(
        default=None,
        description="用于修饰购买金额性质，只有两种可能：'本金余额'或'资产折后本息余额'",
    )


class ClearSummaryInflow(SchemaModel):
    interestAmt: Optional[float] = Field(
        default=None, description="信托收益情况：合格投资款/投资收益/银行存款利息"
    )
    callAmt: Optional[float] = Field(default=None, description="信托收益情况：清仓回购价款")
    buyBack: Optional[float] = Field(default=None, description="信托收益情况：不合格回购款项")
    pool: Optional[float] = Field(
        default=None,
        description="信托账户来自于资产池的回款；本金回收款和利息回收款分别计入principal/interest，如是合并披露的收入则计为cash",
    )
    reserve: Optional[float] = Field(default=None, description="必备流动性储备金额")
    principal: Optional[float] = Field(default=None, description="资产池本金回收款")
    interest: Optional[float] = Field(
        default=None, description="资产池利息回收款(或叫收入回收款/债权投资利息)"
    )
    cash: Optional[float] = Field(
        default=None, description="合并披露的来自资产池的收入"
    )


class ClearRepayPlan(SchemaModel):
    principal: Optional[float] = Field(default=None, description="债券支出本金")
    interest: Optional[float] = Field(
        default=None, description="债券支出利息/收益金额；次级债券可能没有interest收益，找不到可标注为null"
    )


class ClearSummaryResidual(SchemaModel):
    plan: Optional[str] = Field(default=None, description="剩余信托财产的分配方案总结")


class ClearSummaryPerf(SchemaModel):
    cumDef: Optional[float] = Field(
        default=None, description="最终项目结束时累计违约率"
    )
    defAmt: Optional[float] = Field(
        default=None, description="最终违约贷款金额/贷款减值损失"
    )


class AutoClearSummaryReport(ClearReportBase):
    trustee: Optional[str] = Field(default=None, description="受托人/受托机构")
    originator: Optional[str] = Field(default=None, description="发起机构")
    servicer: Optional[str] = Field(default=None, description="贷款服务机构")
    inflow: Optional[ClearSummaryInflow] = Field(
        default=None,
        description="信托收益情况；若有其他收入也对应转换成英文key存入该节点",
    )
    fee: Optional[Dict[str, Any]] = Field(
        default=None, description="信托费用支出情况：费用名字作为key，费用支出金额作为value"
    )
    repay: Optional[Dict[str, ClearRepayPlan]] = Field(
        default=None,
        description="信托本息兑付情况：债券名字作为key，支出本金和利息/收益金额用{principal,interest}作为value；报告可能只披露全部债券兑付情况没有明细",
    )
    residual: Optional[ClearSummaryResidual] = Field(
        default=None, description="信托剩余财产"
    )
    perf: Optional[ClearSummaryPerf] = Field(default=None, description="资产池表现情况")


class ClearAuditBalance(SchemaModel):
    begBalance: Optional[float] = Field(
        default=None, description="初始信贷资产包/资产池的初始本金余额"
    )
    begCashBalance: Optional[float] = Field(
        default=None,
        description="产品在发行时的现金，特指产品开始时的储备账户初始余额",
    )
    endBalance: Optional[float] = Field(
        default=None, description="产品清算时资产池的非现金资产余额"
    )
    endCashBalance: Optional[float] = Field(
        default=None, description="产品清算时资产池的现金资产余额"
    )


class ClearAuditInflow(SchemaModel):
    interestAmt: Optional[float] = Field(
        default=None,
        description="活期投资/合格投资/银行利息收益/活期存款利息/账户结息收入",
    )
    callAmt: Optional[float] = Field(
        default=None,
        description="清仓回购金额(信托财产变现产生的现金流入)，描述着原始权益人付钱从产品中回购资产池内剩余资产的款项；严格按字面和相近字面抓取；找不到就填null。绝非证券本金余额/利息收益金额，也绝非任何费用",
    )
    buyBack: Optional[float] = Field(
        default=None, description="不合格资产赎回产生的现金流入(概率较小，有则记录)"
    )
    pool: Optional[float] = Field(
        default=None,
        description="资产池回款；清算报告可能对周期内回款细分，本次将各细分项目合并计算作为资产池现金流入",
    )


class ClearAuditOutflow(SchemaModel):
    fee: Optional[Dict[str, Any]] = Field(
        default=None,
        description="各项税费支出：有明细则列出明细，无明细则列示税费总和，不要瞎猜；务必用中文作为字段名称，outflow下不需要嵌套结构",
    )
    bond: Optional[Dict[str, Any]] = Field(
        default=None,
        description="债券的各项支出明细(证券利息支出，本金支出，次级档收益，次级固定资金成本)；次级超额收益和次级固定资金成本可能合计或分列，尽量分开抓取",
    )


class ClearAuditResidual(SchemaModel):
    residualPlan: Optional[str] = Field(
        default=None, description="信托项目清算时剩余资产的分配方案"
    )


class AutoClearAuditReport(ClearReportBase):
    trustee: Optional[str] = Field(default=None, description="受托人")
    originator: Optional[str] = Field(default=None, description="发起机构")
    balance: Optional[ClearAuditBalance] = Field(default=None, description="余额信息")
    inflow: Optional[ClearAuditInflow] = Field(
        default=None, description="产品生命周期内全部的现金流入信息"
    )
    outflow: Optional[ClearAuditOutflow] = Field(
        default=None, description="产品生命周期内全部的现金流出信息"
    )
    residual: Optional[ClearAuditResidual] = Field(
        default=None, description="信托项目清算时结余资金/剩余资金分配情况"
    )
    feeCalc: Optional[str] = Field(
        default=None, description="管理费和税费描述中的计算规则"
    )


QUESTION_MODELS: Dict[str, tuple[str, type[SchemaModel]]] = {
    "NPL_INIT_RPT": ("ABS债券投资人", NplInitReport),
    "GEN_INIT_RPT": ("ABS债券投资人", GenInitReport),
    "AUTO_INIT_RPT": ("ABS债券投资人", AutoInitReport),
    "CONSUMER_INIT_RPT": ("ABS债券投资人", ConsumerInitReport),
    "SBL_INIT_RPT": ("ABS债券投资人", SblInitReport),
    "PLAN_RPT": ("债券发行人", PlanReport),
    "PRICING_ANN": ("债券簿记人", PricingAnnReport),
    "NPL_CLEAR_RPT": ("财务人员", NplClearReport),
    "TRUSTEE_NPL_RPT": ("债券簿记人", TrusteeNplReport),
    "SEQ_RATING": ("金融风控", SeqRatingReport),
    "TRUSTEE_AUTO_RPT": ("ABS债券投资人", TrusteeAutoReport),
    "TRUSTEE_AUTO_BUY_RPT": ("ABS债券投资人", TrusteeAutoBuyReport),
    "AUTO_CLEAR_SUMMARY_RPT": ("财务人员", AutoClearSummaryReport),
    "AUTO_CLEAR_AUDIT_RPT": ("财务人员", AutoClearAuditReport),
}

_ASSET_AUTO = lambda f: "汽车" in f or "个人汽车" in f


def route_function(filename: str) -> Optional[str]:
    """Map a mineru table filename to the corresponding QUESTION_MODELS key.

    More specific patterns (e.g. 清算审计) are checked before broader ones
    (e.g. 清算报告).  Asset-type modifiers (汽车/不良/消费/微小企业)
    refine the match within each report category.
    Returns ``None`` when no known question type applies.
    """
    if not filename:
        return None

    match filename:
        # ---- 清算审计 (must come before 清算报告) ----
        case f if "清算审计" in f and _ASSET_AUTO(f):
            return "AUTO_CLEAR_AUDIT_RPT"

        # ---- 清算报告 ----
        case f if "清算报告" in f and "不良" in f:
            return "NPL_CLEAR_RPT"
        case f if "清算报告" in f and _ASSET_AUTO(f):
            return "AUTO_CLEAR_SUMMARY_RPT"

        # ---- 受托机构报告 / 受托机构年度报告 ----
        case f if ("受托机构报告" in f or "受托机构年度报告" in f) and "不良" in f:
            return "TRUSTEE_NPL_RPT"
        case f if ("受托机构报告" in f or "受托机构年度报告" in f) and _ASSET_AUTO(f):
            return "TRUSTEE_AUTO_RPT"

        # ---- 发行说明书 ----
        case f if "发行说明书" in f and "不良" in f:
            return "NPL_INIT_RPT"
        case f if "发行说明书" in f and _ASSET_AUTO(f):
            return "AUTO_INIT_RPT"
        case f if "发行说明书" in f and "消费" in f:
            return "CONSUMER_INIT_RPT"
        case f if "发行说明书" in f and "微小企业" in f:
            return "SBL_INIT_RPT"
        case f if "发行说明书" in f:
            return "GEN_INIT_RPT"

        # ---- simple keyword matches ----
        case f if "发行结果" in f or "簿记建档" in f:
            return "PRICING_ANN"
        case f if "跟踪评级" in f:
            return "SEQ_RATING"
        case f if "信托公告" in f:
            return "PLAN_RPT"
        case f if "循环购买" in f:
            return "TRUSTEE_AUTO_BUY_RPT"

        case _:
            return None
