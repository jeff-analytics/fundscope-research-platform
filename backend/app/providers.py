from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import re
import threading
import time
import pandas as pd
from . import db, fund_master


def ak():
    import akshare as akshare
    return akshare


def now():return datetime.now().isoformat(timespec='seconds')
def num(value):
    try:
        if pd.isna(value):return None
        s=str(value).replace(',','').replace('%','').strip();return float(s) if s and s not in ('-','--') else None
    except Exception:return None

def pick(row,names,default=None):
    for name in names:
        if name in row and not pd.isna(row[name]):return row[name]
    return default

def code(value):
    s=str(value or '').strip()
    if s.endswith('.0') and s[:-2].isdigit():s=s[:-2]
    return s.zfill(6) if s.isdigit() and len(s)<=6 else s

def master_name(name):
    base,cls,_=fund_master.split_share_class(name);mid=hashlib.sha1(base.encode('utf-8')).hexdigest()[:16] if base else ''
    return base,cls,mid

def _norm_period(value):
    s=str(value or '').strip();m=re.search(r'(20\d{2}).*?([1-4])\s*季度',s)
    if m:return f'{m.group(1)}Q{m.group(2)}'
    m=re.search(r'(20\d{2})\D*Q\s*([1-4])',s,re.I)
    if m:return f'{m.group(1)}Q{m.group(2)}'
    digits=re.sub(r'\D','',s)
    if len(digits)>=6:
        y=int(digits[:4]);mo=int(digits[4:6]);return f'{y}Q{(mo-1)//3+1}' if 1<=mo<=12 else s
    return s


def parse_inception_date(value):
    """Parse Eastmoney '成立日期/规模' into YYYY-MM-DD when possible."""
    s=str(value or '').strip()
    if not s:return None
    m=re.search(r'(20\d{2}|19\d{2})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})',s)
    if m:return f'{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    m=re.search(r'(20\d{2}|19\d{2})(\d{2})(\d{2})',re.sub(r'\D','',s))
    if m:return f'{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    return None


def _report_meta(quarter):
    q=_norm_period(quarter)
    if q.endswith('Q1') or q.endswith('Q3'):return '季度报告','top10'
    if q.endswith('Q2'):return '中期报告','full'
    if q.endswith('Q4'):return '年度报告','full'
    return '其他披露','unknown'


def _task_context(progress):
    return getattr(progress, '__self__', None) if progress else None


def _checkpoint(progress):
    ctx=_task_context(progress)
    if ctx and hasattr(ctx,'checkpoint'):
        ctx.checkpoint()


def _is_rate_limited(error):
    text=str(error or '').lower()
    return any(x in text for x in (
        '514','frequency capped','429','too many requests','too many',
        'rate limit','rate_limit','频率限制','访问频率'
    ))


class AdaptiveThrottle:
    """Shared request pacing with automatic cooldown after upstream throttling.

    Thread pools may stay alive, but every new network request must pass through
    ``before``.  When Eastmoney returns 514/429, a shared cooldown is armed and
    all workers stop dispatching new requests until the cooldown expires.
    """
    def __init__(self,workers=8,profile='default'):
        self.workers=max(1,min(12,int(workers)))
        self.profile=str(profile or 'default')
        self.lock=threading.Lock()
        if self.profile=='holdings':
            self.delay=0.34 if self.workers<=2 else 0.22 if self.workers<=4 else 0.16
            self.max_delay=2.5
        elif self.profile=='market':
            self.delay=0.18
            self.max_delay=1.5
        else:
            self.delay=0.08 if self.workers<=4 else 0.05
            self.max_delay=1.5
        self.next_time=0.0
        self.recent=[]
        self.cooldown_until=0.0
        self.rate_limit_streak=0

    def before(self,progress=None):
        _checkpoint(progress)
        while True:
            with self.lock:
                remaining=max(0.0,self.cooldown_until-time.monotonic())
            if remaining<=0:
                break
            ctx=_task_context(progress)
            if ctx and hasattr(ctx,'runtime_state'):
                ctx.runtime_state('cooling',f'限频冷却 {int(remaining)+1}s')
            time.sleep(min(1.0,remaining))
            _checkpoint(progress)
        ctx=_task_context(progress)
        if ctx and hasattr(ctx,'runtime_state'):
            ctx.runtime_state('running','进行中')
        with self.lock:
            wait=max(0,self.next_time-time.monotonic())
            self.next_time=max(self.next_time,time.monotonic())+self.delay
        if wait:
            time.sleep(wait)
        _checkpoint(progress)

    def feedback(self,ok,error=''):
        rate_limited=_is_rate_limited(error)
        with self.lock:
            self.recent=(self.recent+[1 if ok else 0])[-40:]
            fail=1-(sum(self.recent)/len(self.recent)) if self.recent else 0
            if rate_limited:
                self.rate_limit_streak=min(5,self.rate_limit_streak+1)
                cooldown=min(180,20*(2**(self.rate_limit_streak-1)))
                self.cooldown_until=max(self.cooldown_until,time.monotonic()+cooldown)
                self.delay=min(self.max_delay,max(.25,self.delay*1.8))
            elif not ok and fail>.16:
                self.delay=min(self.max_delay,max(.12,self.delay*1.35))
            elif ok:
                self.rate_limit_streak=max(0,self.rate_limit_streak-1)
                if fail<.05:
                    floor=.16 if self.profile=='holdings' and self.workers>=5 else .20 if self.profile=='holdings' else .03
                    self.delay=max(floor,self.delay*.94)
        return rate_limited


def sync_funds(progress=None):
    if progress:progress(0,3,'')
    raw=ak().fund_name_em();rows=[]
    for _,r in raw.iterrows():
        name=str(pick(r,['基金简称','基金名称'],'')).strip();base,cls,mid=master_name(name)
        rows.append([code(pick(r,['基金代码'],'')),name,str(pick(r,['基金类型'],'')).strip(),base,cls,mid,now()])
    df=pd.DataFrame(rows,columns=['fund_code','fund_name','fund_type','base_name_candidate','share_class_candidate','master_candidate_id','fetched_at']).drop_duplicates('fund_code')
    if progress:progress(1,3,'')
    n=db.upsert(df,'fund_share_classes',['fund_code'])
    if progress:progress(2,3,'')
    master_stats=fund_master.build_fund_master()
    if progress:progress(3,3,'')
    return {'rows':n,'fund_master':master_stats}


def sync_managers(progress=None):
    if progress:progress(0,2,'')
    raw=ak().fund_manager_em();rows=[]
    for _,r in raw.iterrows():
        rows.append([str(pick(r,['姓名','基金经理'],'')).strip(),str(pick(r,['所属公司','基金公司'],'')).strip(),str(pick(r,['现任基金代码'],'')).strip(),str(pick(r,['现任基金'],'')).strip(),num(pick(r,['累计从业时间'])),num(pick(r,['现任基金资产总规模'])),num(pick(r,['现任基金最佳回报'])),now()])
    df=pd.DataFrame(rows,columns=['manager_name','company','current_fund_codes','current_funds','career_days','current_aum_billion','best_return_pct','fetched_at'])
    df=df[df.manager_name!=''].drop_duplicates(['manager_name','company']);n=db.upsert(df,'fund_managers',['manager_name','company'])
    if progress:progress(2,2,'')
    return {'rows':n}


def _available_quarters(year,asof=None):
    asof=pd.Timestamp(asof or datetime.now().date());year=int(year);out=[]
    cutoffs=[pd.Timestamp(year,4,30),pd.Timestamp(year,7,31),pd.Timestamp(year,10,31),pd.Timestamp(year+1,1,31)]
    for q,cut in enumerate(cutoffs,1):
        if asof>=cut:out.append(f'{year}Q{q}')
    return out


def _member_codes(master_id,rep):
    x=db.read_sql('SELECT fund_code FROM fund_master_members WHERE master_id=? ORDER BY is_representative DESC,fund_code',(master_id,))
    return x.fund_code.astype(str).tolist() if not x.empty else [str(rep)]


def _profile_row(rep):
    df=db.read_sql('SELECT * FROM fund_profiles WHERE fund_code=? LIMIT 1',(str(rep),))
    return None if df.empty else df.iloc[0].to_dict()


def _profile_to_frame(rep,r):
    def txt(names):
        v=pick(r,names,'');return '' if pd.isna(v) else str(v).strip()
    inception_info=txt(['成立日期/规模','成立日期'])
    inception_date=parse_inception_date(inception_info)
    return pd.DataFrame([[
        rep,txt(['基金全称']),txt(['基金简称']),txt(['基金类型']),txt(['发行日期']),inception_info,
        txt(['资产规模']),txt(['份额规模']),txt(['基金管理人']),txt(['基金托管人']),txt(['基金经理人']),txt(['成立来分红']),
        txt(['管理费率']),txt(['托管费率']),txt(['销售服务费率']),txt(['最高认购费率']),txt(['业绩比较基准']),txt(['跟踪标的']),
        inception_date,'Eastmoney via AKShare',now()
    ]],columns=['fund_code','fund_full_name','fund_short_name','fund_type','issue_date','inception_info','asset_scale','share_scale','fund_company','custodian','manager_names','dividends','management_fee','custodian_fee','sales_service_fee','max_subscription_fee','benchmark','tracking_target','inception_date','source','updated_at'])


def _fetch_inception_year(rep,throttle=None,progress=None):
    cached=_profile_row(rep)
    if cached:
        dt=cached.get('inception_date') or parse_inception_date(cached.get('inception_info'))
        if dt:return int(str(dt)[:4]),None,False
    if throttle:throttle.before(progress)
    else:_checkpoint(progress)
    try:
        raw=ak().fund_overview_em(symbol=str(rep))
        if raw is not None and not raw.empty:
            frame=_profile_to_frame(str(rep),raw.iloc[0]);dt=frame.iloc[0]['inception_date']
            if throttle:throttle.feedback(True)
            if dt:return int(str(dt)[:4]),frame,True
    except Exception as exc:
        if throttle:throttle.feedback(False,repr(exc))
    old=db.read_sql('SELECT MIN(requested_year) y FROM fund_holdings WHERE fund_code=?',(str(rep),))
    if not old.empty and pd.notna(old.iloc[0]['y']):return int(old.iloc[0]['y']),None,True
    return None,None,True


def _selected_masters(limit=None,fund_code=None):
    if fund_code:
        r=fund_master.resolve(str(fund_code))
        if not r.get('master_id'):
            return pd.DataFrame([{'master_id':'','master_name':str(fund_code),'fund_type':'','fund_code':str(fund_code)}])
        return pd.DataFrame([{'master_id':r.get('master_id'),'master_name':r.get('master_name'),'fund_type':r.get('fund_type'),'fund_code':r.get('representative_code')}])
    return fund_master.eligible_representatives(limit)


def holdings_plan_preview(years=None,limit=100,force=False,since_inception=False,fund_code=None):
    fund_master.ensure_master();masters=_selected_masters(limit,fund_code);current=datetime.now().year
    known=0;unknown=0;planned=0;cached=0;oldest=None
    for _,r in masters.iterrows():
        members=_member_codes(r.master_id,r.fund_code) if r.get('master_id') else [str(r.fund_code)]
        if since_inception:
            pr=_profile_row(r.fund_code);dt=(pr or {}).get('inception_date') or parse_inception_date((pr or {}).get('inception_info'))
            if dt:
                start=int(str(dt)[:4]);known+=1;oldest=start if oldest is None else min(oldest,start);ys=range(start,current+1)
            else:
                unknown+=1;ys=[]
        else:
            ys=[int(y) for y in (years or [])]
        for y in ys:
            expected=set(_available_quarters(y));existing={_norm_period(x) for x in db.existing_periods_for_codes(members,y)}
            if force:
                if expected:planned+=1
            elif expected and expected-existing:planned+=1
            else:cached+=1
    return {'selected_masters':len(masters),'known_inception':known,'unknown_inception':unknown,'planned_year_requests':planned,'cached_years':cached,'oldest_inception_year':oldest,'range_mode':'since_inception' if since_inception else 'years'}


def _holdings_plan(years,limit=None,force=False,since_inception=False,fund_code=None,workers=8,progress=None):
    masters=_selected_masters(limit,fund_code);plan=[];skipped=0;current=datetime.now().year;profile_lookups=0;inception_unresolved=0
    if since_inception and len(masters):
        throttle=AdaptiveThrottle(workers,'holdings');results={};done=0
        def get_year(row):
            y,frame,fetched=_fetch_inception_year(str(row.fund_code),throttle,progress);return str(row.fund_code),y,frame,fetched
        with ThreadPoolExecutor(max_workers=max(1,min(workers,12)),thread_name_prefix='fund-profile') as pool:
            futures=[pool.submit(get_year,r) for _,r in masters.iterrows()]
            for fut in as_completed(futures):
                c,y,frame,fetched=fut.result();
                if y is not None:results[c]=y
                else:inception_unresolved+=1
                profile_lookups+=1 if fetched else 0;done+=1
                if frame is not None and not frame.empty:db.upsert(frame,'fund_profiles',['fund_code'])
                if progress:progress(round(done/max(1,len(masters))*15,1),100,'')
    else:results={}
    for _,r in masters.iterrows():
        members=_member_codes(r.master_id,r.fund_code) if r.get('master_id') else [str(r.fund_code)]
        if since_inception and str(r.fund_code) not in results:
            continue
        ys=range(int(results[str(r.fund_code)]),current+1) if since_inception else [int(y) for y in (years or [])]
        for year in ys:
            expected=set(_available_quarters(int(year)))
            existing={_norm_period(x) for x in db.existing_periods_for_codes(members,int(year))}
            missing=expected-existing
            if force:missing=expected or {f'{int(year)}Q{q}' for q in range(1,5)}
            if not force and expected and not missing:skipped+=1;continue
            if not force and not expected:skipped+=1;continue
            plan.append({'master_id':str(r.master_id),'fund_code':str(r.fund_code),'master_name':str(r.master_name),'fund_type':str(r.fund_type),'year':int(year),'missing':missing,'members':members})
    return plan,skipped,len(masters),profile_lookups,inception_unresolved


def _known_empty_error(error):
    s=str(error).lower()
    return any(x in s for x in ("keyerror('占净值比例')",'keyerror("占净值比例")','expected axis has 1 elements','no objects to concatenate'))


def _fetch_holdings_one(item,throttle,progress=None):
    codev=item['fund_code'];year=item['year'];attempts=0;last=''
    for attempt in range(1,5):
        attempts=attempt
        throttle.before(progress)
        try:
            raw=ak().fund_portfolio_hold_em(symbol=codev,date=str(year));rows=[]
            if raw is not None and not raw.empty:
                for _,r in raw.iterrows():
                    quarter=_norm_period(pick(r,['季度','报告期'],''))
                    if item['missing'] and quarter not in item['missing']:continue
                    report_type,scope=_report_meta(quarter)
                    rows.append([codev,year,quarter,code(pick(r,['股票代码','证券代码'],'')),str(pick(r,['股票名称','股票简称','证券简称'],'')).strip(),num(pick(r,['占净值比例','占净值比例(%)','占基金净值比'])),num(pick(r,['持股数','持股数量'])),num(pick(r,['持仓市值','持股市值'])),report_type,scope,now()])
            df=pd.DataFrame(rows,columns=['fund_code','requested_year','quarter','stock_code','stock_name','weight_pct','shares','market_value_wan','report_type','disclosure_scope','fetched_at'])
            throttle.feedback(True)
            return {'item':item,'status':'success' if not df.empty else 'empty','df':df,'attempts':attempts,'error':''}
        except Exception as exc:
            last=repr(exc)
            if _known_empty_error(last):
                throttle.feedback(True)
                return {'item':item,'status':'empty','df':pd.DataFrame(),'attempts':attempts,'error':last}
            limited=throttle.feedback(False,last)
            if attempt<4 and not limited:
                time.sleep(min(4.0,.5*(2**(attempt-1))))
    return {'item':item,'status':'error','df':pd.DataFrame(),'attempts':attempts,'error':last}


def sync_holdings(years=None,limit=100,workers=8,force=False,progress=None,since_inception=False,fund_code=None):
    fund_master.ensure_master();workers=max(1,min(12,int(workers or 4)))
    plan,skipped_cache,master_count,profile_lookups,inception_unresolved=_holdings_plan(years or [],limit,force,since_inception,fund_code,workers,progress);total=len(plan)
    stats={'master_pool':master_count,'planned_requests':total,'success':0,'empty':0,'error':0,'rows':0,'skipped_cache':skipped_cache,'workers':workers,'profile_lookups':profile_lookups,'inception_unresolved':inception_unresolved,'since_inception':bool(since_inception),'filtered_share_classes':max(0,db.count('fund_share_classes')-db.count('fund_master'))}
    if not plan:
        if progress:progress(100,100,'')
        return stats
    throttle=AdaptiveThrottle(workers,'holdings');buffer=[];logs=[];done=0
    def flush():
        nonlocal buffer,logs
        if buffer:
            frame=pd.concat(buffer,ignore_index=True) if len(buffer)>1 else buffer[0]
            stats['rows']+=db.upsert(frame,'fund_holdings',['fund_code','quarter','stock_code'],chunk_size=2000);buffer=[]
        if logs:db.log_tasks_bulk(logs);logs=[]
    with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='fund-holdings') as pool:
        futures=[pool.submit(_fetch_holdings_one,item,throttle,progress) for item in plan]
        for fut in as_completed(futures):
            res=fut.result();done+=1;item=res['item'];status=res['status'];stats[status]+=1
            if status=='success' and not res['df'].empty:buffer.append(res['df'])
            etype=''
            if status=='error':etype='rate_limited' if _is_rate_limited(res['error']) else ('network_error' if any(x in res['error'].lower() for x in ('timeout','connection','remote','reset')) else 'parse_or_source_error')
            logs.append(('holdings',item['fund_code'],item['year'],','.join(sorted(item['missing'])),status,len(res['df']),res['attempts'],etype,res['error'][:1200],now()))
            if len(buffer)>=24 or len(logs)>=60:flush()
            if progress:
                base=15 if since_inception else 0;progress(base+round(done/max(1,total)*(100-base),1),100,'')
    flush();return stats


def quarter_ends(n=8):
    now_ts=pd.Timestamp.now().normalize();dates=pd.date_range(end=now_ts,periods=n+5,freq='QE-DEC')
    return [d for d in dates if d<=now_ts][-n:]

def _period_variants(d):
    q=(d.month-1)//3+1;return [d.strftime('%Y-%m-%d'),d.strftime('%Y%m%d'),f'{d.year}Q{q}',f'{d.year}年{q}季度']

def _market_exists(d):
    vals=_period_variants(d);marks=','.join(['?']*len(vals));stock=db.read_sql(f'SELECT COUNT(*) n FROM market_stock_consensus WHERE report_date IN ({marks})',tuple(vals)).iloc[0,0];industry=db.read_sql(f'SELECT COUNT(*) n FROM market_industry_allocation WHERE report_date IN ({marks})',tuple(vals)).iloc[0,0]
    return int(stock)>0 and int(industry)>0


def _market_stock(d,throttle,progress=None):
    ds=d.strftime('%Y%m%d');throttle.before(progress)
    try:
        raw=ak().fund_report_stock_cninfo(date=ds);rows=[]
        for _,r in raw.iterrows():rows.append([str(pick(r,['报告期'],'')).strip(),code(pick(r,['股票代码'],'')),str(pick(r,['股票简称'],'')).strip(),int(num(pick(r,['基金覆盖家数'])) or 0),num(pick(r,['持股总数'])),num(pick(r,['持股总市值'])),now()])
        throttle.feedback(True);return 'stock',pd.DataFrame(rows,columns=['report_date','stock_code','stock_name','fund_count','shares','market_value_wan','fetched_at']),''
    except Exception as exc:throttle.feedback(False,repr(exc));return 'stock',pd.DataFrame(),repr(exc)


def _market_industry(d,throttle,progress=None):
    ds=d.strftime('%Y%m%d');throttle.before(progress)
    try:
        raw=ak().fund_report_industry_allocation_cninfo(date=ds);rows=[]
        for _,r in raw.iterrows():rows.append([str(pick(r,['报告期'],'')).strip(),str(pick(r,['行业编码'],'')).strip(),str(pick(r,['证监会行业名称'],'')).strip(),int(num(pick(r,['基金覆盖家数'])) or 0),num(pick(r,['行业规模'])),num(pick(r,['占净资产比例'])),now()])
        throttle.feedback(True);return 'industry',pd.DataFrame(rows,columns=['report_date','industry_code','industry_name','fund_count','industry_scale_yi','nav_weight_pct','fetched_at']),''
    except Exception as exc:throttle.feedback(False,repr(exc));return 'industry',pd.DataFrame(),repr(exc)


def sync_market(quarters=8,force=False,progress=None,workers=3):
    workers=max(2,min(4,int(workers or 3)));dates=quarter_ends(quarters);todo=[];stats={'asset_rows':0,'stock_rows':0,'industry_rows':0,'errors':0,'skipped_cache':0,'workers':workers}
    try:
        raw=ak().fund_report_asset_allocation_cninfo();rows=[]
        for _,r in raw.iterrows():rows.append([str(pick(r,['报告期'],'')).strip(),num(pick(r,['基金覆盖家数'])),num(pick(r,['股票权益类占净资产比例'])),num(pick(r,['债券固定收益类占净资产比例'])),num(pick(r,['现金货币类占净资产比例'])),num(pick(r,['基金市场净资产规模'])),now()])
        stats['asset_rows']=db.upsert(pd.DataFrame(rows,columns=['report_date','fund_count','equity_weight_pct','fixed_income_weight_pct','cash_weight_pct','market_nav_yi','fetched_at']),'market_asset_allocation',['report_date'])
    except Exception:stats['errors']+=1
    for d in dates:
        if not force and _market_exists(d):stats['skipped_cache']+=2;continue
        todo.extend([('stock',d),('industry',d)])
    total=max(1,len(todo));done=0;throttle=AdaptiveThrottle(workers,'market')
    with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='market-report') as pool:
        futures=[pool.submit(_market_stock if kind=='stock' else _market_industry,d,throttle,progress) for kind,d in todo]
        for fut in as_completed(futures):
            kind,df,err=fut.result();done+=1
            if err:stats['errors']+=1
            elif kind=='stock' and not df.empty:stats['stock_rows']+=db.upsert(df,'market_stock_consensus',['report_date','stock_code'],chunk_size=2000)
            elif kind=='industry' and not df.empty:stats['industry_rows']+=db.upsert(df,'market_industry_allocation',['report_date','industry_code'],chunk_size=500)
            if progress:progress(done,total,'')
    if not todo and progress:progress(1,1,'')
    return stats


# ---- Eastmoney enrichment via AKShare ----
def sync_fund_profile(fund_code,progress=None):
    resolved=fund_master.resolve(str(fund_code));rep=str(resolved.get('representative_code') or fund_code)
    if progress:progress(0,1,'')
    raw=ak().fund_overview_em(symbol=rep)
    if raw is None or raw.empty:
        if progress:progress(1,1,'')
        return {'fund_code':rep,'rows':0,'status':'empty'}
    frame=_profile_to_frame(rep,raw.iloc[0]);n=db.upsert(frame,'fund_profiles',['fund_code'])
    if progress:progress(1,1,'')
    return {'fund_code':rep,'rows':n,'status':'success','inception_date':frame.iloc[0]['inception_date']}


def sync_fund_major_changes(fund_code,years,progress=None):
    resolved=fund_master.resolve(str(fund_code));rep=str(resolved.get('representative_code') or fund_code)
    years=[int(y) for y in years];total=max(1,len(years)*2);step=0;rows_all=[];stats={'fund_code':rep,'success':0,'empty':0,'error':0,'rows':0}
    for year in years:
        for indicator,direction in [('累计买入','buy'),('累计卖出','sell')]:
            try:
                raw=ak().fund_portfolio_change_em(symbol=rep,indicator=indicator,date=str(year));rows=[]
                if raw is not None and not raw.empty:
                    for _,r in raw.iterrows():
                        quarter=_norm_period(pick(r,['季度','报告期'],f'{year}Q4'))
                        amount=num(pick(r,['本期累计买入金额','本期累计卖出金额','累计买入金额','累计卖出金额']))
                        navpct=num(pick(r,['占期初基金资产净值比例','占期初资产净值比例']))
                        rows.append([rep,year,quarter,direction,code(pick(r,['股票代码','证券代码'],'')),str(pick(r,['股票名称','股票简称'],'')).strip(),amount,navpct,now()])
                if rows:
                    df=pd.DataFrame(rows,columns=['fund_code','requested_year','quarter','direction','stock_code','stock_name','amount_wan','initial_nav_pct','fetched_at'])
                    rows_all.append(df);stats['success']+=1
                else:stats['empty']+=1
            except Exception:stats['error']+=1
            step+=1
            if progress:progress(step,total,'')
    if rows_all:
        frame=pd.concat(rows_all,ignore_index=True);stats['rows']=db.upsert(frame,'fund_major_changes',['fund_code','requested_year','quarter','direction','stock_code'],chunk_size=1000)
    if stats['error']>=total and stats['rows']==0:raise RuntimeError('重大变动数据源暂时不可用')
    return stats


def sync_incremental(workers=8,progress=None):
    """Routine maintenance task: refresh foundation + latest market + current-year holdings only.

    Existing quarters are skipped, so this is the recommended recurring update path.
    """
    workers=max(1,min(12,int(workers or 4)))
    def mapped(start,end):
        def cb(cur,total,msg=''):
            ratio=0 if not total else max(0,min(1,float(cur)/float(total)))
            if progress:progress(start+(end-start)*ratio,100,'')
        return cb
    out={}
    out['funds']=sync_funds(mapped(0,10))
    out['managers']=sync_managers(mapped(10,18))
    out['market']=sync_market(8,False,mapped(18,35),max(2,min(4,workers-1 if workers>2 else 2)))
    out['holdings']=sync_holdings([datetime.now().year],None,workers,False,mapped(35,92),False,None)
    # Fast Security Master layer only: bulk market fields + board-based industry mapping.
    try:
        from . import security
        out['security_master']=security.sync_security_master(None,min(12,max(4,workers*2)),mapped(92,100),False)
    except Exception as exc:
        out['security_master']={'error':repr(exc)}
        if progress:progress(100,100,'')
    return out
