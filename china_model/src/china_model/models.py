import datetime
from operator import itemgetter, attrgetter
from peewee import *
import toolz as tz
from lenses import lens
import pickle,json,re,bcrypt
import fire
from rich.console import Console
#from datasource.util import nameChineseNameToDealId
from playhouse.sqlite_ext import JSONField
from playhouse.postgres_ext import *

from .db import db


console = Console()

class BaseModel(Model):
    class Meta:
        database = db

class Group(BaseModel):
    ID = AutoField(unique=True, primary_key=True)
    name = CharField(unique=True)
    active = BooleanField(default=False)

class User(BaseModel):
    ID = AutoField(unique=True, primary_key=True)
    username = CharField(unique=False)
    password = CharField(max_length=256)
    active = BooleanField(default=False)
    group = ForeignKeyField(Group, backref='users')
    register = DateTimeField(default=datetime.datetime.now)
    # class Meta:
    #     constraints = [SQL('UNIQUE(username,group)')]

class UserGroup(BaseModel):
    user = ForeignKeyField(User, backref='groups')
    group = ForeignKeyField(Group, backref='users')
    active = BooleanField(default=False)

class Permission(BaseModel):
    ownerRead = BooleanField()
    ownerWrite = BooleanField()
    ownerExecute = BooleanField()
    groupRead = BooleanField()
    groupWrite = BooleanField()
    groupExecute = BooleanField()
    otherRead = BooleanField()
    otherWrite = BooleanField()
    otherExecute = BooleanField()


# Function to hash a password
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')  # Return as a string to store in CharField

# Function to verify a password
def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

class Stage(BaseModel):
    ID = AutoField(unique=True, primary_key=True)
    name = CharField(unique=True)

class Tag(BaseModel):
    ID = AutoField(unique=True, primary_key=True)
    name = CharField(unique=True)


class Subscription(BaseModel):
    ID = AutoField(unique=True, primary_key=True)
    group = ForeignKeyField(User, backref='subscriptions')
    tag = ForeignKeyField(Tag, backref='subscriptions')
    operator = BooleanField(default=True)
    start = DateTimeField(default=datetime.datetime.now)
    end = DateTimeField(default=datetime.datetime.now)
    active = BooleanField(default=False)



class Deal(BaseModel):
    dealid = CharField(primary_key=True)
    stage = ForeignKeyField(Stage, backref='deals',null=True)
    period = IntegerField(null=True)
    fullName = CharField(null=True)
    shortName = CharField(null=True)
    shortNameKey = CharField(null=True)
    seriesName = CharField(null=True)
    bookDate = DateField(null=True)
    closingDate = DateField(null=True)
    endDate = DateField(null=True)
    poolType = CharField(null=True)
    poolSubType = CharField(null=True)
    data = JSONField(null=True)
    class Meta:
        constraints = [SQL('UNIQUE(fullName)')]

class Institution(BaseModel):
    fullName = CharField(unique=True)
    name = CharField(primary_key=True)

#     "roles": {
#       "originator": "中国工商银行股份有限公司",
#       "underwriter": "中国国际金融股份有限公司",
#       "issuer": "华润深国投信托有限公司",
#       "servicer": "中国工商银行股份有限公司"
#     }

class Roles(BaseModel):
    deal = ForeignKeyField(Deal, backref='role',null=True)
    originator = ForeignKeyField(Institution, backref='originator',null=True)
    underwriter = ForeignKeyField(Institution, backref='underwriter',null=True)
    servicer = ForeignKeyField(Institution, backref='servicer',null=True)
    issuer = ForeignKeyField(Institution, backref='issuer',null=True)



# class DealObj(BaseModel):
#     ID = AutoField(unique=True, primary_key=True)
#     obj = BlobField()
#     json = TextField()
#     buildVersion = CharField(default="0.0.0")
#     period = IntegerField()
#     dealid = ForeignKeyField(Deal, backref='updates',null=True)
#     active = BooleanField(default=False)

class DealMeta(BaseModel):
    deal = ForeignKeyField(Deal, backref='meta')
    creator = ForeignKeyField(User, backref='metas')
    group = ForeignKeyField(Group, backref='metas')
    permission = ForeignKeyField(Permission, backref='metas')
    date = DateTimeField()

class DealTag(BaseModel):
    deal = ForeignKeyField(Deal, backref= 'tags')
    tag = ForeignKeyField(Tag, backref= 'deals')

# class UiSupplement(BaseModel):
#     deal = ForeignKeyField(Deal, backref='uiSupplements')
#     requiredRates = CharField(default="")   
#     poolPerfInput = BlobField()
#     revolvingAsset = BlobField(default=None)
#     revolvingPerf = BlobField(default=None)
#     active = BooleanField(default=True)

class Comment(BaseModel):
    ID = AutoField(unique=True, primary_key=True)
    deal = ForeignKeyField(Deal, backref='comments')
    user = ForeignKeyField(User, backref='comments')
    permission = ForeignKeyField(Permission, backref='comments')
    comment = TextField()
    date = DateTimeField()
    active = BooleanField(default=False)

class News(BaseModel):
    ID = AutoField(unique=True, primary_key=True)
    title = CharField()
    content = TextField()
    date = DateField()
    active = BooleanField(default=False)

class NewsVisibility(BaseModel):
    ID = AutoField(unique=True, primary_key=True)
    public = BooleanField(default=False)


class BondSeniorityType(BaseModel):
    name = CharField(primary_key=True)

class Index(BaseModel):
    name = CharField(primary_key=True)


class Bond(BaseModel):
    name = CharField()
    deal = ForeignKeyField(Deal, backref='bonds')
    curFactor = DecimalField(column_name='curFactor',null=True,max_digits=10,decimal_places=5)
    curBalance = DecimalField(null=True,max_digits=15,decimal_places=2)
    curRate = DecimalField(null=True,max_digits=10,decimal_places=5)
    issueDate = DateField(null=True)
    issuePrice = DecimalField(null=True,max_digits=10,decimal_places=5)
    issueFace = DecimalField(null=True,max_digits=15,decimal_places=2)
    issueRate = DecimalField(null=True,max_digits=10,decimal_places=5)
    expectedMaturity = DateField(null=True)
    seniority = ForeignKeyField(BondSeniorityType, backref='seniorities')
    data = JSONField()

    class Meta:
        indexes = (
            (('name', 'deal'), True),  # True means UNIQUE
        )
        constraints = [
            Check('curBalance >= 0 ')
            ,Check('issueFace >= 0 ')
        ]
        only_save_dirty = True


class PreClosingBond(BaseModel):
    deal = ForeignKeyField(Deal, backref='prebonds')
    name = CharField()
    balance = DecimalField(max_digits=15,decimal_places=2)
    availBal = DecimalField(null=True,max_digits=15,decimal_places=2)
    intType = CharField()
    wal = DecimalField(null=True)
    expectedMaturity = DateField(null=True)
    data = JSONField(null=True)



class Account(BaseModel):
    name = CharField()
    displayName = CharField()
    deal = ForeignKeyField(Deal, backref='accounts')
    class Meta:
        indexes = (
            (('name', 'displayName'), True),  # True means UNIQUE
        )


class AccountSnapshot(BaseModel):
    account = ForeignKeyField(Account, backref='snapshots')
    date = DateField()
    balance = DecimalField(null=True,max_digits=15,decimal_places=2)
    class Meta:
        indexes = (
            (('account', 'date'), True),  # True means UNIQUE
        )

class Fee(BaseModel):
    name = CharField()
    displayName = CharField()
    deal = ForeignKeyField(Deal, backref='fees')
    class Meta:
        indexes = (
            (('name', 'displayName'), True),  # True means UNIQUE
        )
class FeeFlow(BaseModel):
    fee = ForeignKeyField(Fee, backref='flows')
    date = DateField()
    payment = DecimalField(null=True,max_digits=15,decimal_places=2)
    balance = DecimalField(null=True,max_digits=15,decimal_places=2)
    class Meta:
        indexes = (
            (('fee', 'date'), True),  # True means UNIQUE
        )

class DealData(BaseModel):
    deal = ForeignKeyField(Deal, backref='dealdata')
    data = JSONField()


class BondIDType(BaseModel):
    name = CharField(primary_key=True)
    desc = CharField()


class BondID(BaseModel):
    ID = IdentityField(column_name='ID')
    bondID = CharField()
    idType = ForeignKeyField(BondIDType, backref='bondIDs')
    bond = ForeignKeyField(Bond, backref='bondIDs')

class BondPayments(BaseModel):
    bond = ForeignKeyField(Bond, backref='bondPayments')
    paymentDate = DateField()
    currentBalance = DecimalField(null=True) # ending balance
    currentFactor = DecimalField() # bond factor by (ending balance/issuance balance)
    currentRate = DecimalField(null=True)
    principal = DecimalField()
    interest = DecimalField()
    cash = DecimalField(null=True)
    interestYield =  DecimalField(null=True)
    updatePeriod = IntegerField()
    class Meta:
        indexes = (
            (('bond', 'paymentDate'), True),  # True means UNIQUE
        )
        constraints = [
            Check('currentBalance >= 0 ')
            ,Check('principal >= 0 ')
            ,Check('interest >= 0 ')
            ,Check('interestYield >= 0 ')
            ,Check('currentFactor >= 0 AND currentFactor <= 1.0')
        ]
        only_save_dirty = True

class Location(BaseModel):
    name = CharField()
    bucket = CharField()
    key = CharField()
    class Meta:
        indexes = (
            (('name', 'bucket', 'key'), True),  # True means UNIQUE
        )

class ReportType(BaseModel):
    name = CharField(unique=True)
    original = ForeignKeyField('self', backref='corrections', unique=True, null=True)

    @property
    def correction(self):
        """返回该原始类型对应的纠正类型（如果有）"""
        return self.corrections.get_or_none()



class Report(BaseModel):
    loc = ForeignKeyField(Location,unique=True)
    deal = ForeignKeyField(Deal, backref='reports',null=True)
    rptType = ForeignKeyField(ReportType, backref='reports',null=True)
    date = DateField(null=True)
    class Meta:
        indexes = (
            (('loc', 'deal', 'rptType'), True),  # True means UNIQUE
        )

        
class IssueFiles(BaseModel):
    deal = ForeignKeyField(Deal, backref='issueFiles')
    loc = ForeignKeyField(Location, backref='issueFiles', null=False,unique=True)

class TrusteeReport(BaseModel):
    deal = ForeignKeyField(Deal, backref='trusteeReports',null=True)
    loc = ForeignKeyField(Location, backref='trusteeReports', null=True,unique=True)
    period = IntegerField(null=True)
    data = JSONField()
    class Meta:
        indexes = (
            (('deal', 'period'), True),  # True means UNIQUE
        )

class RatingAgency(BaseModel):
    ''' 评级公司 '''
    name = CharField(primary_key = True)


class Rating(BaseModel):
    bond = ForeignKeyField(Bond, backref='ratings')
    agency = ForeignKeyField(RatingAgency, backref='ratings')
    ratingDate = DateField(null=True)
    rating = CharField()
    class Meta:
        indexes = (
            (('bond', 'agency','ratingDate'), True),  # True means UNIQUE
        )


class RatingReport(BaseModel):
    ''' 评级报告 '''
    deal = ForeignKeyField(Deal, backref='ratingReports',null=True)
    loc = ForeignKeyField(Location, backref='ratingReports', null=True, unique=True)
    agency = ForeignKeyField(RatingAgency, backref='ratingReports')
    seq = IntegerField(null=True)
    data = JSONField()


class ClearReport(BaseModel):
    ''' 清算报告 '''
    deal = ForeignKeyField(Deal, backref='clearReports',null=True)
    loc = ForeignKeyField(Location, backref='clearReports', null=True, unique=True)
    data = JSONField()


class PricingReport(BaseModel):
    ''' 簿记结果 '''
    deal = ForeignKeyField(Deal, backref='pricingReport',null=True)
    loc = ForeignKeyField(Location, backref='pricingReport', null=True, unique=True)
    data = JSONField()


class BookingAnn(BaseModel):
    ''' 申购邀约 '''
    deal = ForeignKeyField(Deal, backref='bookingAnn',null=True)
    loc = ForeignKeyField(Location, backref='bookingAnn', null=True, unique=True)
    data = JSONField(null=True)


class IssuePlan(BaseModel):
    ''' 发行办法 '''
    deal = ForeignKeyField(Deal, backref='issuePlan',null=True)
    loc = ForeignKeyField(Location, backref='issuePlan', null=True, unique=True)
    data = JSONField(null=True)


class MaterialEvent(BaseModel):
    ''' 重大时间 '''
    deal = ForeignKeyField(Deal, backref='materialEvent',null=True)
    loc = ForeignKeyField(Location, backref='materialEvent', null=True, unique=True)
    data = JSONField(null=True)

class SalesTeam(BaseModel):
    ''' 承销团队 '''
    deal = ForeignKeyField(Deal, backref='salesTeam',null=True)
    loc = ForeignKeyField(Location, backref='salesTeam', null=True, unique=True)
    data = JSONField(null=True)

class ClosingAnn(BaseModel):
    ''' 发行公告 '''
    deal = ForeignKeyField(Deal, backref='closingAnn',null=True)
    loc = ForeignKeyField(Location, backref='closingAnn', null=True, unique=True)
    data = JSONField(null=True)

class PeriodReport(BaseModel):
    ''' 期间报告 '''
    deal = ForeignKeyField(Deal, backref='periodReport',null=True)
    loc = ForeignKeyField(Location, backref='periodReport', null=True, unique=True)
    data = JSONField(null=True)

class TrustAnn(BaseModel):
    ''' 信托成立公告 '''
    deal = ForeignKeyField(Deal, backref='trustAnn',null=True)
    loc = ForeignKeyField(Location, backref='trustAnn', null=True, unique=True)
    data = JSONField(null=True)

class IssueAnn(BaseModel):
    ''' 发行公告 '''
    deal = ForeignKeyField(Deal, backref='issueAnn',null=True)
    loc = ForeignKeyField(Location, backref='issueAnn', null=True, unique=True)
    data = JSONField(null=True)

class TrustIssueAnn(BaseModel):
    ''' 信托公告: 公告时发行文件 '''
    deal = ForeignKeyField(Deal, backref='trustIssueAnn',null=True)
    loc = ForeignKeyField(Location, backref='trustIssueAnn', null=True, unique=True)
    data = JSONField(null=True)



class Correction(BaseModel):
    ''' 纠正公告 '''
    loc = ForeignKeyField(Location, backref='correction', null=True, unique=True)
    correction = ForeignKeyField(Location, backref='correction', null=True, unique=True)
    deprecated = ForeignKeyField(Location, backref='correction', null=True, unique=True)
    data = JSONField(null=True)


class TradingPrice(BaseModel):
    bond = ForeignKeyField(Bond, backref='tradingPrices')
    date = DateField()
    cleanPrice = DecimalField()
    dirtyPrice = DecimalField()
    tradeCount = IntegerField()
    settleAmount = DecimalField()
    
    class Meta:
        indexes = (
            (('bond', 'date'), True),  # True means UNIQUE
        )

class Question(BaseModel):
    name = CharField(primary_key=True)
    roles = CharField()
    content = TextField()
    expectedOutput = TextField(null=True)
    active = IntegerField()
    desc = TextField(null=True)
    class Meta:
        indexes = (
            (('name', 'active'), True),  # True means UNIQUE
        )




class ReportTrack(BaseModel):
    ''' 
        track the process of report digest with LLM
    '''
    data = HStoreField()

def markLlmRun(loc,m,q):
    ReportTrack.create(data={"reportName":loc
                            ,"model":m
                            ,"q":q
                            ,"run":str(datetime.datetime.now())})    

def hasLlmRun(loc,m,q):
    if list(ReportTrack.select().where(ReportTrack.data.contains({"reportName":loc,"model":m,"q":q})).dicts()):
        return True
    else:
        return False

class HealthCheck(BaseModel):
    date = DateField()
    ts = DateTimeField()
    data = JSONField()

class InternalDealMeta(BaseModel):
    '''
    '''
    deal = ForeignKeyField(Deal, backref='internal_meta')
    data = JSONField(null=True)



class LlmJob(BaseModel):
    ''' 批量LLM解析 '''
    model = CharField()
    txnId = CharField(primary_key=True)
    inputFile = CharField()
    taskCount =  IntegerField(null=True)
    questions = CharField()
    refEntity = CharField() # describle the target entity to fill parse result
    status = IntegerField() # 0: submited 1: pulled 2: loaded
    ts = DateTimeField()

class LlmTxn(BaseModel):
    ''' 每个location解析之后的结果,以及对应job  '''
    job = ForeignKeyField(LlmJob, backref='txns')
    question = CharField()
    loc = ForeignKeyField(Location, backref='txns')
    resp = TextField()


##########################################################

reportMap = {
    'TrusteeReport':TrusteeReport,
    'IssuePlan':IssuePlan,
    'RatingReport':RatingReport,
    'PricingReport':PricingReport
}


def getTrusteeReportBySeries(sn:str):
    return TrusteeReport.select().join(Deal).where(Deal.seriesName==sn).dicts()


def getEquityTranches():
    r = BondID.select().join(Bond).join(BondIDType)\
        .where(Bond.seniority==BondSeniorityType.get(BondSeniorityType.name=='junior')
               ,BondIDType.name=='债券代码').dicts()
    return list(r)



#########################################################
## Deal Data 

def getDealsByIds(ids):
    return Deal.select().where(Deal.dealid.in_(ids))

def ratingReportByKey(k):
    loc = Location.get(Location.key==k)
    if loc:
        return RatingReport.get(loc=loc)

def getInitRatingReports(d):
    return [ _ for _ in list(d.ratingReports) if _.seq==0 ]


######### Util functions
def getNames(xs):
    return [ _.name for _ in xs]

def filterActive(xs):
    return [ _ for _ in xs if _.active==True]

def filterInEffective(xs):
    n = datetime.datetime.now()
    return [ _ for _ in xs if (_.start <= n and _.end >= n)]

def bondIdToDeal(bondId):
    return Deal.select(Deal).join(BondId, join_type=JOIN.INNER)\
            .where(BondID.bondID == bondId)

########### Admin actions

def patchTags(xs):
    curTags = set(tz.pluck('name',Tag.select().dicts()))
    newTags = set(xs) - set(curTags)
    if newTags:
        Tag.insert_many([{"name":_} for _ in newTags]).execute()
    return Tag.select().where(Tag.name.in_(xs)).dicts()


def getDealsByTags(coverageRules):
    """ 
        coverageRules is a list of tuples, each tuple is a pair of tag and operator 
        e.g. [('+','RMBS'),('-','Auto')] 
        return a list of deals that satisfy the rules
    """
    includingTags = [ _[1] for _ in coverageRules if _[0] == '+']
    exemptTags =  [ _[1] for _ in coverageRules if _[0] == '-']
    # Deal.name,Deal.period,Deal.stage,Deal.active,Tag.name.alias('tag')
    # return Deal.select().join(DealTag,JOIN.LEFT_OUTER, on=DealTag.deal).join(Tag,JOIN.LEFT_OUTER, on=DealTag.tag).where( (Tag.name.in_(includingTags)) & (Tag.name.not_in(exemptTags)) ).dicts()
    rs = Deal.select(Deal, fn.GROUP_CONCAT(Tag.name).alias('tags')).join(DealTag, JOIN.LEFT_OUTER).join(Tag, JOIN.LEFT_OUTER).group_by(Deal).dicts()
    #return [ r for r in rs if r['tags'] in includingTags and r['tags'] not in exemptTags]
    return rs


###### User Actions
def loginUser(username:str, password:str):
    if (_u:= User.get_or_none(User.username == username)) :
        #print(password,hash_password(password),_u.password)
        if check_password(password,_u.password):
            return (True,{"group": _u.group.name ,"user":_u.username})
        else:
            return (False,"Incorrect Password")
            #return (True,{"group": [ _.group.name for _ in _u.groups],"user":_u.username})
    else:
        return (False,f" User <{username}> not found")

def pullUserInfo(username:str) -> dict:
    u = User.get(User.username == username)
    return {
        "group":u.group.name,
        "user":u.username
    }


def pullAllUserScope(u, active):
    ''' return all users' scope on deal library 
        u: User object
    '''
    thisUserGroups = UserGroup.select(UserGroup.group).where(UserGroup.user == u).dicts()

    scopeRules = Subscription.select().join(Group, JOIN.LEFT_OUTER, on=(Subscription.group==Group.ID))\
                    .where(Subscription.group.in_(thisUserGroups) & (Subscription.active==True) )\
                    .dicts()
    

    ruleByTag = tz.valmap( lambda x: set(tz.pluck('tag',x)), tz.groupby('operator',list(scopeRules)))
    ruleByTagWithDefault = {False:[],True:[]} | ruleByTag 

    r = Deal.select(Deal.dealid,Tag.name,fn.MAX(DealObj.id))\
        .join(DealTag, JOIN.LEFT_OUTER, on=(DealTag.deal==Deal.dealid))\
        .join(Tag, JOIN.LEFT_OUTER, on=(Tag.id==DealTag.tag))\
        .join(DealObj, JOIN.LEFT_OUTER, on=(DealObj.dealid==Deal.dealid))\
        .group_by(Deal.dealid)\
        .where(DealTag.tag.in_(ruleByTagWithDefault[True]) &\
               DealTag.tag.not_in(ruleByTagWithDefault[False]) &\
               DealObj.active==active)\
        .dicts()

    return r 

def dealTags(dealId):
    return list(Tag.select(Tag.name).join(DealTag).where(DealTag.deal == dealId).dicts())

def getDealUpdatesByQ(q, active=True):
    """
    Given a query string, return a single of deal object
    """
    r = None
    try:
        match q:
            case ("id",_id) |  ("dealid",_id) :
                r = Deal.get_by_id(_id)
            #case ("name",n):
            #    r = Deal.get(Deal.name == n, Deal.active==active)
            #case ("re",n):
            #    r = Deal.get(Deal.name.regexp(n))
            #case x if isinstance(x,str):
            #    r = Deal.get(Deal.name == x)
            case _:
                raise RuntimeError(f"Invalid query {q}")
    except Deal.DoesNotExist:
        raise RuntimeError(f"Deal not found {q}")
    if r is None:
        raise RuntimeError(f"Invalid query {q}")
    
    r = list(DealObj.select()
                .where(DealObj.dealid==r.dealid & DealObj.active==active).dicts()
                )
    if r:
        return r[0]
    else:
        raise RuntimeError(f"Deal Update not found {q}")


def pullDeals(u:str, q:dict, active):
    """
        u: username
        q: query as a map
        if q is none, return all.
        return a list of deal objects
    """
    validDealsByUser = list(pullAllUserScope(User.get(User.username == u),active))
    r = None
    if q == "" or q == {} or q == []:
        r = validDealsByUser
    else:
        r = filterByQ(q, validDealsByUser)
    return r


def filterByQ(q, deals:list):
    " given a q , return a Maybe deal, Nothing represents invalid permission"
    #print("deals before filter", deals)
    match q:
#        case ("name", n):
#            deals = [ d for d in deals if d['name'].find(n)>=0 ]
        case ("id",_id):
            deals = [ d for d in deals if d['dealid'] == _id ]
#        case ("tag",tag):
#            deals = [ d for d in deals if (d['tags'] and d['tags'].find(tag)>=0) ]
#        case ("tags",tags) if isinstance(tags,list):
#            deals = [ d for d in deals if set(d['tags'].split(";")).issubset(set(tags)) ]
        case _:
            raise RuntimeError(f"Invalid query {q}")
    return deals

def userPermission(u, d):
    """ return (read,write,execute) 
        read => view deal
        write => modify deal
        execute => run the deal 
    """
    if (user:=User.get_or_none(User.username == u)):
        ug = UserGroup.select().where(UserGroup.user == user).dicts()
        if (deal:=Deal.get_or_none(Deal.id == d)):
            pass

    return (True,True,True)

def latestUpdateByDealId(dealid:str, active):
    deal = Deal.select().where(Deal.dealid == dealid).get_or_none()
    if not deal:
        return None
    else:
        updates = deal.updates.dicts()
        rs = [ _ for _ in updates if _['active'] == active ]
        if not rs:
            return None
        else:
            rr = sorted(rs, key=lambda x: x['period'], reverse=True)
            return rr[-1]

def calcValidTag(g:str):
    _c = Group.get(Group.name == g)
    return tz.pipe(_c.subsCoverages,
                    lambda x: filterActive(x),
                    lambda x: filterInEffective(x),
    )

def guessBondName(x):
    if (r:=re.search(r"(优先档)",x)):
        return r.groups()[0]
    elif (r:=re.search(r"(次级档)",x)):
        return r.groups()[0]
    elif (r:=re.search(r"(优先\S*?[档级])",x)):
        return r.groups()[0]
    elif (r:=re.search(r"(次级\S?级)",x)):
        return r.groups()[0]
    elif (r:=re.search(r"(优先级)",x)):
        return r.groups()[0]
    elif (r:=re.search(r"(次级)",x)):
        return r.groups()[0]
    elif (r:=re.search(r"(A级)",x)):
        return r.groups()[0]
    else:
        return None


##########################################################################
# Cloud storage catalogue
#
# These two tables are written by the ingestion/ETL projects
# (``docToCloud`` writes ``qiniu_storage``; ``toMarkdown`` writes ``mineru``).
# They are modelled here so every project shares a single schema definition
# instead of hand-writing SQL.

class QiniuStorage(BaseModel):
    ''' Catalogue of objects uploaded to Qiniu. '''
    id = AutoField(column_name="pk", null=True)
    bucket = TextField(null=True)
    key = TextField(null=True, unique=True)
    ts = BigIntegerField(null=True)
    hash = TextField(null=True)
    md5 = CharField(null=True, max_length=255)

    class Meta:
        table_name = "qiniu_storage"


class Mineru(BaseModel):
    ''' PDF-to-markdown conversion results produced by the MinerU pipeline. '''
    key = TextField(primary_key=True)
    url = TextField(null=True)
    ts = BigIntegerField(null=True)
    hash = TextField(null=True)
    parsed_json = TextField(null=True)
    markdown = TextField(null=True)
    model = CharField(null=True, max_length=255)

    class Meta:
        table_name = "mineru"


