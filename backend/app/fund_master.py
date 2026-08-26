import hashlib
import re
import threading
import time
import copy
from datetime import datetime
import pandas as pd
from . import db

# V8 research universe is intentionally strict: active equity / equity-heavy mixed funds only.
# Bond, money-market, passive index/ETF and feeder products remain in the raw fund table but
# are excluded from the default research universe and holdings collection plan.
_MASTER_STATE_LOCK=threading.RLock()
_MASTER_CHECK_UNTIL=0.0
_RESOLVE_CACHE={}
_RESOLVE_CACHE_MAX=600

HARD_EXCLUDE_PATTERNS=(
    "货币","债券","纯债","短债","中短债","长债","可转债","同业存单","理财",
    "FOF","养老目标","REIT","商品","联接","指数","ETF","被动","增强指数","固收"
)


def now():return datetime.now().isoformat(timespec='seconds')


def split_share_class(name):
    """Normalize share/fee variants that share the same underlying portfolio.

    Supports common A/C/E/I/H/Y classes, numeric variants such as A1/C1, and
    front/back-end fee suffixes. Currency remains part of the master name so RMB,
    USD and HKD share classes are not merged unless the source explicitly names
    them identically.
    """
    s=re.sub(r"\s+","",str(name or ""))
    if not s:return "","",.5
    s=s.replace('（','(').replace('）',')')
    fee=''
    fee_m=re.search(r"(?:\()?((?:前端|后端))(?:收费)?(?:\))?$",s)
    if fee_m:
        fee='BACKEND' if fee_m.group(1)=='后端' else 'FRONT';s=s[:fee_m.start()]
    currency=''
    cm=re.search(r"(人民币|美元|港币|RMB|USD|HKD)$",s,re.I)
    if cm:
        currency=cm.group(1).upper() if cm.group(1).upper() in {'RMB','USD','HKD'} else cm.group(1);s=s[:cm.start()]
    cls=''
    # Accept A/C/E/I/H/Y and numbered share variants (A1, C1, etc.).
    m=re.match(r"^(.*?)(?:\()?([A-Z](?:\d{1,2})?)(?:类|份额)?(?:\))?$",s,re.I)
    if m and len(m.group(1))>=3:
        base=m.group(1);cls=m.group(2).upper()
    else:base=s
    # Some names place currency before the class, e.g. 产品人民币A.
    cm2=re.search(r"(人民币|美元|港币|RMB|USD|HKD)$",base,re.I)
    if cm2:
        currency=cm2.group(1).upper() if cm2.group(1).upper() in {'RMB','USD','HKD'} else cm2.group(1);base=base[:cm2.start()]
    base=base+currency
    parts=[x for x in (cls,fee) if x];share='_'.join(parts)
    confidence=.97 if fee and cls else .96 if fee else (.94 if cls else .82)
    return base,share,confidence


def eligible_equity(fund_type,name=""):
    """Return whether a fund belongs to the default active-equity research pool.

    V8 deliberately excludes bond funds (including secondary-bond / convertible-bond),
    passive index/ETF/feeder products, money funds, FOF and REITs.
    """
    ftype=str(fund_type or '').strip()
    fname=str(name or '').strip()
    text=f"{ftype} {fname}".upper()

    for p in HARD_EXCLUDE_PATTERNS:
        if p.upper() in text:
            return False,p

    # Core active-equity categories used by Eastmoney fund_name_em.
    if "股票型" in ftype:
        return True,''
    if "混合型" in ftype:
        return True,''

    # Some QDII rows are typed only as QDII. Keep only clearly active equity names.
    if "QDII" in ftype.upper() and ("股票" in fname or "混合" in fname):
        return True,''

    return False,'不属于主动偏股研究池'


def _rep_priority(share_class,code):
    sc=str(share_class or '').upper()
    backend='BACKEND' in sc or '后端' in sc
    base=sc.replace('_BACKEND','').replace('BACKEND','').replace('_FRONT','').replace('FRONT','')
    order={'A':0,'A1':0,'':1,'I':2,'E':3,'C':4,'C1':4,'B':5,'D':6,'H':7,'Y':8}
    return (1 if backend else 0,order.get(base,9),str(code))


def build_fund_master():
    global _MASTER_CHECK_UNTIL
    with _MASTER_STATE_LOCK:
        _MASTER_CHECK_UNTIL=0.0
        _RESOLVE_CACHE.clear()
    f=db.read_table('fund_share_classes')
    if f.empty:return {'masters':0,'members':0,'eligible':0,'excluded':0,'saved_requests_estimate':0}
    groups={}
    for _,r in f.iterrows():
        base,cls,confidence=split_share_class(r.get('fund_name'))
        ftype=str(r.get('fund_type') or '')
        key=f"{base}|{ftype}"
        mid=hashlib.sha1(key.encode('utf-8')).hexdigest()[:18]
        eligible,reason=eligible_equity(ftype,base)
        item={'fund_code':str(r.fund_code),'fund_name':str(r.get('fund_name') or ''),'fund_type':ftype,'base':base,'share_class':cls,'confidence':confidence,'eligible':eligible,'reason':reason,'master_id':mid}
        groups.setdefault(mid,[]).append(item)
    master_rows=[];member_rows=[]
    for mid,items in groups.items():
        rep=min(items,key=lambda x:_rep_priority(x['share_class'],x['fund_code']))
        master_rows.append([mid,rep['base'],rep['fund_type'],rep['fund_code'],1 if rep['eligible'] else 0,rep['reason'],len(items),min(x['confidence'] for x in items),now()])
        for x in items:member_rows.append([x['fund_code'],mid,x['share_class'],1 if x['fund_code']==rep['fund_code'] else 0,now()])
    mdf=pd.DataFrame(master_rows,columns=['master_id','master_name','fund_type','representative_code','eligible_equity','exclusion_reason','share_count','confidence','updated_at'])
    mem=pd.DataFrame(member_rows,columns=['fund_code','master_id','share_class','is_representative','updated_at'])
    db.upsert(mdf,'fund_master',['master_id']);db.upsert(mem,'fund_master_members',['fund_code'])
    eligible=int(mdf.eligible_equity.sum());saved=max(0,len(mem)-len(mdf))
    return {'masters':len(mdf),'members':len(mem),'eligible':eligible,'excluded':len(mdf)-eligible,'saved_requests_estimate':saved}


def ensure_master(force=False):
    """Validate Fund Master at most once per process window.

    Earlier versions performed several COUNT/LIKE scans every time a fund was
    resolved. On a large research database this became visible as UI latency.
    """
    global _MASTER_CHECK_UNTIL
    now_ts=time.monotonic()
    if not force and _MASTER_CHECK_UNTIL>now_ts:
        return None
    with _MASTER_STATE_LOCK:
        now_ts=time.monotonic()
        if not force and _MASTER_CHECK_UNTIL>now_ts:
            return None
        if db.count('fund_master')==0 or db.count('fund_master_members')==0:
            out=build_fund_master();_MASTER_CHECK_UNTIL=time.monotonic()+300;return out
        stale=db.read_sql("""SELECT COUNT(*) n FROM fund_master
            WHERE master_name LIKE '%后端%' OR master_name LIKE '%前端%'
               OR (eligible_equity=1 AND (
                   fund_type LIKE '%债券%' OR master_name LIKE '%债券%'
                   OR fund_type LIKE '%指数%' OR master_name LIKE '%ETF%'
                   OR master_name LIKE '%联接%' OR master_name LIKE '%可转债%'
               ))""")
        if not stale.empty and int(stale.iloc[0]['n'] or 0)>0:
            out=build_fund_master();_MASTER_CHECK_UNTIL=time.monotonic()+300;return out
        _MASTER_CHECK_UNTIL=time.monotonic()+300
        return None


def resolve(code):
    ensure_master();code=str(code);rev=db.data_revision();key=(rev,code)
    cached=_RESOLVE_CACHE.get(key)
    if cached is not None:
        return copy.deepcopy(cached)
    row=db.read_sql("""SELECT m.*,mm.share_class,mm.is_representative FROM fund_master_members mm JOIN fund_master m ON m.master_id=mm.master_id WHERE mm.fund_code=? LIMIT 1""",(code,))
    if row.empty:
        out={'requested_code':code,'master_id':None,'representative_code':code,'member_codes':[code],'eligible_equity':1}
    else:
        r=row.iloc[0].to_dict();members=db.read_sql('SELECT fund_code FROM fund_master_members WHERE master_id=? ORDER BY is_representative DESC,fund_code',(r['master_id'],))
        r['requested_code']=code;r['member_codes']=members.fund_code.astype(str).tolist();out=r
    if len(_RESOLVE_CACHE)>=_RESOLVE_CACHE_MAX:_RESOLVE_CACHE.clear()
    _RESOLVE_CACHE[key]=copy.deepcopy(out)
    return out


def eligible_representatives(limit=None):
    ensure_master()
    sql="""SELECT m.master_id,m.master_name,m.fund_type,m.representative_code AS fund_code,m.share_count,m.confidence
           FROM fund_master m WHERE eligible_equity=1 ORDER BY representative_code"""
    if limit:sql+=f" LIMIT {int(limit)}"
    return db.read_sql(sql)


def stats():
    ensure_master()
    q=db.read_sql("""SELECT COUNT(*) masters,SUM(CASE WHEN eligible_equity=1 THEN 1 ELSE 0 END) eligible,
    SUM(CASE WHEN eligible_equity=0 THEN 1 ELSE 0 END) excluded,SUM(share_count) shares,SUM(CASE WHEN share_count>1 THEN share_count-1 ELSE 0 END) duplicate_shares FROM fund_master""")
    return q.iloc[0].to_dict() if not q.empty else {}
