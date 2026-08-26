from concurrent.futures import ThreadPoolExecutor,as_completed
import logging
from datetime import datetime,timedelta
import time
import pandas as pd
from . import db,fund_master
from .providers import ak,code,num,pick,now,AdaptiveThrottle

logger=logging.getLogger("fundscope.security")


def _market(codev):
    s=str(codev)
    if s.isdigit() and len(s)==6:
        if s.startswith(('6','68')):return 'SH'
        if s.startswith(('0','3')):return 'SZ'
        if s.startswith(('8','4','92')):return 'BJ'
    if s.isdigit() and len(s)==5:return 'HK'
    return 'OTHER'


def _latest_growth(df):
    if df is None or df.empty:return (None,None)
    row=df.iloc[0]
    def first(cands):
        for c in cands:
            if c in row.index:
                v=num(row[c])
                if v is not None:return v
        return None
    rev=first(['营业收入同比增长','营业收入同比增长率','营业总收入同比增长率','营业收入同比增长(%)','营业总收入同比增长(%)'])
    profit=first(['净利润同比增长','净利润同比增长率','归母净利润同比增长率','净利润同比增长(%)','扣非净利润同比增长率'])
    return rev,profit


def _industry_map(target_codes,workers,throttle,progress=None):
    """Map Eastmoney industry boards to held A-shares using board constituents.

    This replaces thousands of stock_individual_info_em calls with roughly one call per
    industry board, which is substantially faster for a broad Security Master refresh.
    """
    target=set(target_codes);mapped={}
    try:
        boards=ak().stock_board_industry_name_em()
    except Exception:
        return mapped
    if boards is None or boards.empty:return mapped
    name_col='板块名称' if '板块名称' in boards.columns else boards.columns[0]
    names=[str(x) for x in boards[name_col].dropna().tolist()]
    total=max(1,len(names));done=0
    def one(name):
        for attempt in range(3):
            throttle.before(progress)
            try:
                raw=ak().stock_board_industry_cons_em(symbol=name);throttle.feedback(True);out=[]
                if raw is not None and not raw.empty:
                    for _,r in raw.iterrows():
                        c=code(pick(r,['代码','股票代码'],''))
                        if c in target:out.append((c,name))
                return out
            except Exception as exc:
                limited=throttle.feedback(False,repr(exc))
                if not limited and attempt<2:time.sleep(.4*(2**attempt))
        return []
    with ThreadPoolExecutor(max_workers=max(2,min(8,workers)),thread_name_prefix='industry-map') as pool:
        fs=[pool.submit(one,n) for n in names]
        for f in as_completed(fs):
            for c,n in f.result():mapped.setdefault(c,n)
            done+=1
            if progress:progress(10+round(done/total*55,1),100,'')
    return mapped


def _growth_one(codev,throttle,progress=None):
    fn=getattr(ak(),'stock_financial_analysis_indicator_em',None)
    if not callable(fn):return codev,None,None
    for attempt in range(3):
        throttle.before(progress)
        try:
            g=fn(symbol=codev);rev,profit=_latest_growth(g);throttle.feedback(True);return codev,rev,profit
        except Exception as exc:
            limited=throttle.feedback(False,repr(exc))
            if not limited and attempt<2:time.sleep(.4*(2**attempt))
    return codev,None,None


def sync_security_master(limit=None,workers=8,progress=None,deep=False):
    workers=max(1,min(12,int(workers or 8)))
    hold=db.read_sql('SELECT DISTINCT stock_code,MAX(stock_name) stock_name FROM fund_holdings GROUP BY stock_code')
    if hold.empty:return {'securities':0,'a_share':0,'enriched':0,'workers':workers,'deep':bool(deep)}
    if limit:hold=hold.head(int(limit))
    target_codes=[code(x) for x in hold.stock_code.tolist()]
    existing=db.read_table('security_master');existing_map={str(r.security_code):r.to_dict() for _,r in existing.iterrows()} if not existing.empty else {}

    if progress:progress(1,100,'')
    spot_map={}
    try:
        spot=ak().stock_zh_a_spot_em()
        for _,r in spot.iterrows():
            c=code(pick(r,['代码'],''))
            if c not in target_codes:continue
            old=existing_map.get(c,{})
            spot_map[c]={
                'security_code':c,'security_name':str(pick(r,['名称'],old.get('security_name',''))).strip(),
                'market':_market(c),'industry_l1':old.get('industry_l1'),'industry_l2':old.get('industry_l2'),
                'total_market_cap':num(pick(r,['总市值'])),'float_market_cap':num(pick(r,['流通市值'])),
                'pe':num(pick(r,['市盈率-动态'])),'pb':num(pick(r,['市净率'])),
                'revenue_growth_yoy':old.get('revenue_growth_yoy'),'profit_growth_yoy':old.get('profit_growth_yoy'),
                'listing_date':old.get('listing_date'),'asof_date':datetime.now().date().isoformat(),
                'source_quality':'spot','updated_at':now()
            }
    except Exception as exc:
        logger.warning("security_spot_refresh_failed error=%s",exc)
    if progress:progress(10,100,'')

    a_codes=[c for c in target_codes if _market(c) in ('SH','SZ','BJ')]
    throttle=AdaptiveThrottle(workers,'security')
    industry=_industry_map(a_codes,workers,throttle,progress)

    rows=[]
    names={code(r.stock_code):str(r.stock_name) for _,r in hold.iterrows()}
    for c in target_codes:
        base=dict(spot_map.get(c) or existing_map.get(c) or {})
        base.update({
            'security_code':c,'security_name':base.get('security_name') or names.get(c,''),'market':base.get('market') or _market(c),
            'industry_l1':industry.get(c) or base.get('industry_l1'),'industry_l2':base.get('industry_l2'),
            'total_market_cap':base.get('total_market_cap'),'float_market_cap':base.get('float_market_cap'),
            'pe':base.get('pe'),'pb':base.get('pb'),'revenue_growth_yoy':base.get('revenue_growth_yoy'),
            'profit_growth_yoy':base.get('profit_growth_yoy'),'listing_date':base.get('listing_date'),
            'asof_date':datetime.now().date().isoformat(),'source_quality':'spot+industry' if industry.get(c) else (base.get('source_quality') or 'basic'),'updated_at':now()
        })
        rows.append(base)
    if progress:progress(72,100,'')

    # Deep mode adds per-security growth calls. It is intentionally optional because this is the slow layer.
    if deep and a_codes:
        growth={};done=0;total=max(1,len(a_codes))
        with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='security-growth') as pool:
            fs=[pool.submit(_growth_one,c,throttle,progress) for c in a_codes]
            for f in as_completed(fs):
                c,rev,profit=f.result();growth[c]=(rev,profit);done+=1
                if progress:progress(72+round(done/total*27,1),100,'')
        for row in rows:
            if row['security_code'] in growth:
                rev,profit=growth[row['security_code']]
                if rev is not None:row['revenue_growth_yoy']=rev
                if profit is not None:row['profit_growth_yoy']=profit
                if rev is not None or profit is not None:row['source_quality']=(row.get('source_quality') or '')+'+growth'

    if rows:
        cols=['security_code','security_name','market','industry_l1','industry_l2','total_market_cap','float_market_cap','pe','pb','revenue_growth_yoy','profit_growth_yoy','listing_date','asof_date','source_quality','updated_at']
        df=pd.DataFrame(rows);[df.__setitem__(c,None) for c in cols if c not in df.columns];db.upsert(df[cols],'security_master',['security_code'],chunk_size=2000)
    if progress:progress(100,100,'')
    return {'securities':len(hold),'a_share':len(a_codes),'enriched':len(rows),'industry_mapped':sum(1 for r in rows if r.get('industry_l1')),'workers':workers,'deep':bool(deep)}


def _date_bounds(years_back=3):
    end=datetime.now().date();start=end-timedelta(days=int(years_back*370));return start.strftime('%Y%m%d'),end.strftime('%Y%m%d')


def _fetch_price(codev,start,end,throttle,progress=None):
    last=''
    for attempt in range(3):
        throttle.before(progress)
        try:
            raw=ak().stock_zh_a_hist(symbol=codev,period='daily',start_date=start,end_date=end,adjust='qfq');throttle.feedback(True)
            if raw is None or raw.empty:return codev,pd.DataFrame(),''
            datecol='日期' if '日期' in raw.columns else raw.columns[0];closecol='收盘' if '收盘' in raw.columns else None
            if not closecol:return codev,pd.DataFrame(),'missing close'
            x=pd.DataFrame({'security_code':codev,'trade_date':pd.to_datetime(raw[datecol],errors='coerce').dt.date.astype(str),'close_adj':pd.to_numeric(raw[closecol],errors='coerce')}).dropna(subset=['trade_date','close_adj'])
            x['return_pct']=x.close_adj.pct_change()*100;x['updated_at']=now();return codev,x,''
        except Exception as exc:
            last=repr(exc);limited=throttle.feedback(False,last)
            if not limited and attempt<2:time.sleep(.4*(2**attempt))
    return codev,pd.DataFrame(),last


def sync_return_gap_inputs(fund_code,years_back=3,workers=8,progress=None):
    workers=max(1,min(12,int(workers or 5)));fund_master.ensure_master();resolved=fund_master.resolve(fund_code);rep=str(resolved.get('representative_code') or fund_code);members=resolved.get('member_codes') or [rep]
    for c in members:
        if db.read_sql('SELECT COUNT(*) n FROM fund_holdings WHERE fund_code=?',(c,)).iloc[0,0]>0:rep=str(c);break
    start,end=_date_bounds(years_back);stats={'fund_code':rep,'nav_rows':0,'price_rows':0,'securities':0,'errors':0,'workers':workers}
    try:
        raw=ak().fund_open_fund_info_em(symbol=rep,indicator='单位净值走势')
        if raw is not None and not raw.empty:
            datecol='净值日期';navcol='单位净值';retcol='日增长率' if '日增长率' in raw.columns else None
            x=pd.DataFrame({'fund_code':rep,'nav_date':pd.to_datetime(raw[datecol],errors='coerce').dt.date.astype(str),'unit_nav':pd.to_numeric(raw[navcol],errors='coerce'),'daily_return_pct':pd.to_numeric(raw[retcol],errors='coerce') if retcol else None})
            x=x[(x.nav_date>=pd.to_datetime(start).date().isoformat())&(x.nav_date<=pd.to_datetime(end).date().isoformat())].dropna(subset=['nav_date','unit_nav']);x['updated_at']=now();stats['nav_rows']=db.upsert(x,'fund_nav',['fund_code','nav_date'],1500)
    except Exception:stats['errors']+=1
    h=db.read_sql('SELECT DISTINCT stock_code FROM fund_holdings WHERE fund_code=?',(rep,));codes=[code(x) for x in h.stock_code.tolist()] if not h.empty else []
    codes=[c for c in codes if _market(c) in ('SH','SZ','BJ')];stats['securities']=len(codes);throttle=AdaptiveThrottle(workers,'return_gap');frames=[];done=0;total=max(1,len(codes))
    with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='return-gap') as pool:
        fs=[pool.submit(_fetch_price,c,start,end,throttle,progress) for c in codes]
        for f in as_completed(fs):
            _,x,err=f.result();done+=1
            if not x.empty:frames.append(x)
            if err:stats['errors']+=1
            if len(frames)>=24:
                z=pd.concat(frames,ignore_index=True);stats['price_rows']+=db.upsert(z,'security_prices',['security_code','trade_date'],2500);frames=[]
            progress and progress(done,total,'')
    if frames:
        z=pd.concat(frames,ignore_index=True);stats['price_rows']+=db.upsert(z,'security_prices',['security_code','trade_date'],2500)
    return stats
