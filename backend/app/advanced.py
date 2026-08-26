import math
import re
import time
import threading
from datetime import date
import numpy as np
import pandas as pd
from . import services,db,fund_master,disclosure
from .manager_index import manager_id

_ADV_CACHE_LOCK=threading.Lock()
_STYLE_REF_CACHE={}
_FUND_ADV_CACHE={}
_MANAGER_STYLE_CACHE={}

def _ttl_get(store,key):
    now=time.monotonic();item=store.get(key)
    if item and item[0]>now:return item[1]
    if item:store.pop(key,None)
    return None

def _ttl_put(store,key,value,ttl,max_items=80):
    if len(store)>=max_items:store.clear()
    store[key]=(time.monotonic()+ttl,value)



def _safe(v,default=None):
    try:
        if v is None or pd.isna(v) or not np.isfinite(float(v)):return default
        return float(v)
    except Exception:return default


def _period_end(period):
    m=re.fullmatch(r'(20\d{2})Q([1-4])',services.normalize_period(period))
    if not m:return None
    y,q=int(m.group(1)),int(m.group(2));months={1:3,2:6,3:9,4:12};mo=months[q]
    return pd.Timestamp(y,mo,1)+pd.offsets.MonthEnd(1)


def _period_frame(h,period):
    x=h[h.quarter==period].copy()
    if x.empty:return x
    x['weight_pct']=pd.to_numeric(x['weight_pct'],errors='coerce').fillna(0)
    if 'shares' in x.columns:x['shares']=pd.to_numeric(x['shares'],errors='coerce')
    return x


def _compare(h,p0,p1):
    a0=_period_frame(h,p0);b0=_period_frame(h,p1)
    a0,b0,meta=disclosure.comparable_pair(a0,b0,p0,p1)
    extras=['shares','market_value_wan']
    ac=['stock_code','stock_name','sector','weight_pct']+[c for c in extras if c in a0.columns]
    bc=['stock_code','stock_name','sector','weight_pct']+[c for c in extras if c in b0.columns]
    a=a0[ac].rename(columns={'stock_name':'name_old','sector':'sector_old','weight_pct':'weight_old','shares':'shares_old','market_value_wan':'mv_old'})
    b=b0[bc].rename(columns={'stock_name':'name_new','sector':'sector_new','weight_pct':'weight_new','shares':'shares_new','market_value_wan':'mv_new'})
    m=a.merge(b,on='stock_code',how='outer')
    if m.empty:m.attrs['comparison_meta']=meta;return m
    m['stock_name']=m.get('name_new').fillna(m.get('name_old'));m['sector']=m.get('sector_new').fillna(m.get('sector_old'))
    m['weight_old']=pd.to_numeric(m.get('weight_old'),errors='coerce');m['weight_new']=pd.to_numeric(m.get('weight_new'),errors='coerce');m['delta']=m['weight_new'].fillna(0)-m['weight_old'].fillna(0)
    for c in ['shares_old','shares_new','mv_old','mv_new']:
        if c not in m:m[c]=np.nan
    m.attrs['comparison_meta']=meta
    return m


def _js_divergence(a,b):
    keys=sorted(set(a)|set(b))
    if not keys:return 0.0
    pa=np.array([max(0,a.get(k,0)) for k in keys],dtype=float);pb=np.array([max(0,b.get(k,0)) for k in keys],dtype=float)
    if pa.sum()<=0 or pb.sum()<=0:return 0.0
    pa/=pa.sum();pb/=pb.sum();m=(pa+pb)/2
    def kl(x,y):
        mask=x>0;return float(np.sum(x[mask]*np.log2(x[mask]/y[mask])))
    return max(0,min(1,(kl(pa,m)+kl(pb,m))/2))


def _percentile_map(df,column,transform=None):
    if df.empty or column not in df.columns:return {}
    s=pd.to_numeric(df[column],errors='coerce')
    if transform is not None:s=s.map(lambda x:transform(x) if pd.notna(x) else np.nan)
    rank=s.rank(pct=True)*100
    return {str(c):float(v) for c,v in zip(df.security_code,rank) if pd.notna(v)}


def _style_reference(mode='local'):
    if mode=='demo':return {}
    key=(db.data_revision(),mode)
    with _ADV_CACHE_LOCK:cached=_ttl_get(_STYLE_REF_CACHE,key)
    if cached is not None:return cached
    s=db.read_sql('SELECT security_code,total_market_cap,pb,pe,revenue_growth_yoy,profit_growth_yoy FROM security_master')
    if s.empty:return {}
    out={
      'size':_percentile_map(s,'total_market_cap',lambda x:math.log(max(float(x),1))),
      'pb':_percentile_map(s,'pb'),'pe':_percentile_map(s,'pe'),
      'rev':_percentile_map(s,'revenue_growth_yoy'),'profit':_percentile_map(s,'profit_growth_yoy'),
    }
    with _ADV_CACHE_LOCK:_ttl_put(_STYLE_REF_CACHE,key,out,300.0,8)
    return out


def _demo_factor(codev,kind):
    seed=sum(ord(c) for c in f'{codev}{kind}')%101;return float(seed)


def _weighted(values,weights):
    pairs=[(v,w) for v,w in zip(values,weights) if v is not None and pd.notna(v) and w is not None and pd.notna(w) and w>0]
    if not pairs:return None,0.0
    den=sum(w for _,w in pairs);return sum(v*w for v,w in pairs)/den,den


def _snapshot_style(h,period,refs,mode='local'):
    x=_period_frame(h,period)
    if x.empty:return None
    weights=x.weight_pct.clip(lower=0).tolist();codes=x.stock_code.astype(str).tolist()
    size_vals=[];growth_vals=[]
    for c in codes:
        if mode=='demo':
            size_vals.append(_demo_factor(c,'size'));growth_vals.append(_demo_factor(c,'growth'));continue
        size_vals.append(refs.get('size',{}).get(c))
        comps=[]
        for k,w in [('pb',.30),('pe',.20),('rev',.25),('profit',.25)]:
            v=refs.get(k,{}).get(c)
            if v is not None:comps.append((v,w))
        growth_vals.append(sum(v*w for v,w in comps)/sum(w for _,w in comps) if comps else None)
    size,size_cov=_weighted(size_vals,weights);growth,growth_cov=_weighted(growth_vals,weights)
    total=max(float(sum(weights)),1e-9);top10=float(x.nlargest(10,'weight_pct').weight_pct.sum())
    mapped=x[~x.sector.fillna('未分类').eq('未分类')]
    sector_cov=float(mapped.weight_pct.sum()/total*100) if not mapped.empty else 0
    sector_hhi=None
    sector_dist={}
    if not mapped.empty:
        sector_dist=mapped.groupby('sector').weight_pct.sum().to_dict();arr=np.array(list(sector_dist.values()),dtype=float);arr=arr/arr.sum() if arr.sum() else arr;sector_hhi=float(np.sum(arr**2)*100)
    style_cov=np.mean([min(100,size_cov/total*100),min(100,growth_cov/total*100)])
    return {'period':period,'size_score':round(size,2) if size is not None else None,'value_growth_score':round(growth,2) if growth is not None else None,'sector_concentration':round(sector_hhi,2) if sector_hhi is not None else None,'top10_concentration':round(top10,2),'style_data_coverage':round(style_cov,2),'sector_coverage':round(sector_cov,2),'sector_dist':sector_dist}


def _style_history(h,mode='local'):
    periods=services.sort_periods(h.quarter.tolist());refs=_style_reference(mode);snaps=[]
    normalized=disclosure.comparable_history(h,periods)
    prev=None
    for p in periods:
        s=_snapshot_style(normalized,p,refs,mode)
        if not s:continue
        drift=None
        if prev:
            factor_diffs=[]
            for key in ['size_score','value_growth_score']:
                if s.get(key) is not None and prev.get(key) is not None:factor_diffs.append(abs(s[key]-prev[key])/100)
            factor_shift=float(np.mean(factor_diffs)) if factor_diffs else None
            concentration_shift=abs(s['top10_concentration']-prev['top10_concentration'])/60 if s.get('top10_concentration') is not None and prev.get('top10_concentration') is not None else None
            sector_js=_js_divergence(prev.get('sector_dist',{}),s.get('sector_dist',{})) if prev.get('sector_dist') and s.get('sector_dist') else None
            sector_conc_shift=abs(s['sector_concentration']-prev['sector_concentration'])/100 if s.get('sector_concentration') is not None and prev.get('sector_concentration') is not None else None
            sector_parts=[v for v in [sector_js,sector_conc_shift] if v is not None];sector_shift=float(np.mean(sector_parts)) if sector_parts else None
            structural=0;m=_compare(normalized,prev['period'],p)
            if not m.empty:structural=min(1,float(m.delta.abs().sum()/2)/25)
            pieces=[(.35,factor_shift),(.30,sector_shift),(.20,concentration_shift),(.15,structural)];valid=[(w,v) for w,v in pieces if v is not None];drift=100*sum(w*v for w,v in valid)/sum(w for w,_ in valid) if valid else None
        s['drift_score']=round(drift,2) if drift is not None else None
        s['drift_level']='—' if drift is None else ('稳定' if drift<25 else '轻微漂移' if drift<45 else '明显漂移' if drift<65 else '高漂移')
        s['comparison_basis']='top10_comparable';s.pop('sector_dist',None);snaps.append(s);prev=_snapshot_style(normalized,p,refs,mode)
    return snaps


def _hidden_signals(h,p0,p1):
    m=_compare(h,p0,p1)
    if m.empty:return [],0.0
    valid=m[(m['shares_old'].notna())&(m['shares_new'].notna())&(m['shares_old']>0)&(m['shares_new']>=0)].copy();coverage=round(len(valid)/max(1,len(m))*100,2)
    if valid.empty:return [],coverage
    valid['share_change_pct']=(valid['shares_new']/valid['shares_old']-1)*100;rows=[]
    for _,r in valid.iterrows():
        sc=float(r.share_change_pct);wd=float(r.delta)
        if abs(sc)<8:continue
        opposite=(sc>0 and wd<0) or (sc<0 and wd>0);masked=abs(wd)<=0.6 or opposite
        if not masked:continue
        rows.append({'stock_code':str(r.stock_code),'stock_name':r.stock_name,'sector':r.sector,'share_change_pct':round(sc,2),'weight_delta':round(wd,2),'signal':'隐形增仓' if sc>0 else '隐形减仓','confidence':'高' if abs(sc)>=15 and abs(sc)<200 else '中','opposite_direction':bool(opposite)})
    return sorted(rows,key=lambda x:abs(x['share_change_pct']),reverse=True)[:24],coverage


def _migration_sankey_from_delta(delta,name_col='name',basis='stock'):
    neg=delta[delta.delta<-.05].copy();pos=delta[delta.delta>.05].copy()
    if neg.empty or pos.empty:return {'nodes':[],'links':[],'basis':basis,'matched_weight':0}
    neg=neg.assign(_abs=neg.delta.abs()).sort_values('_abs',ascending=False).head(8)
    pos=pos.sort_values('delta',ascending=False).head(8)
    negv=[(str(r[name_col]),abs(float(r.delta))) for _,r in neg.iterrows()];posv=[(str(r[name_col]),float(r.delta)) for _,r in pos.iterrows()]
    total_neg=sum(v for _,v in negv);total_pos=sum(v for _,v in posv);mass=min(total_neg,total_pos)
    nodes=[{'name':f'{n} · 减','side':'source'} for n,_ in negv]+[{'name':f'{n} · 增','side':'target'} for n,_ in posv];links=[]
    for sn,sv in negv:
        for tn,tv in posv:
            value=mass*(sv/total_neg)*(tv/total_pos)
            if value>=.03:links.append({'source':f'{sn} · 减','target':f'{tn} · 增','value':round(value,3)})
    return {'nodes':nodes,'links':sorted(links,key=lambda x:x['value'],reverse=True)[:24],'basis':basis,'matched_weight':round(mass,2)}


def _fund_sankey(h,p0,p1):
    m=_compare(h,p0,p1)
    if m.empty:return {'nodes':[],'links':[],'basis':'stock'}
    mapped=not m.sector.fillna('未分类').eq('未分类').all()
    if mapped:
        g=m.groupby('sector',as_index=False).delta.sum().rename(columns={'sector':'name'});return _migration_sankey_from_delta(g,'name','sector')
    g=m[['stock_name','delta']].rename(columns={'stock_name':'name'});sel=pd.concat([g.nlargest(8,'delta'),g.nsmallest(8,'delta')]).drop_duplicates('name');return _migration_sankey_from_delta(sel,'name','stock')


def _nearest_value(df,datecol,valuecol,target,before=True):
    if df.empty:return None
    x=df.copy();x[datecol]=pd.to_datetime(x[datecol],errors='coerce');x=x.dropna(subset=[datecol,valuecol])
    t=pd.Timestamp(target);z=x[x[datecol]<=t] if before else x[x[datecol]>=t]
    if z.empty:z=x
    row=z.sort_values(datecol).iloc[-1] if before else z.sort_values(datecol).iloc[0]
    return _safe(row[valuecol])


def _return_gap_series(code,h):
    resolved=fund_master.resolve(code) if code else {'representative_code':code,'member_codes':[code]};members=resolved.get('member_codes') or [code]
    nav=pd.DataFrame();nav_code=None
    for c in [resolved.get('representative_code')]+members:
        if not c:continue
        q=db.read_sql('SELECT nav_date,unit_nav FROM fund_nav WHERE fund_code=? ORDER BY nav_date',(str(c),))
        if not q.empty:nav=q;nav_code=str(c);break
    if nav.empty:return []
    periods=services.sort_periods(h.quarter.tolist())
    if len(periods)<2:return []
    ends=[_period_end(p) for p in periods];valid_ends=[x for x in ends if x is not None]
    if not valid_ends:return []
    dmin=(min(valid_ends)-pd.Timedelta(days=10)).date().isoformat();dmax=(max(valid_ends)+pd.Timedelta(days=10)).date().isoformat()
    codes=sorted(set(h.stock_code.astype(str)));price_parts=[]
    for i in range(0,len(codes),800):
        chunk=codes[i:i+800];marks=','.join(['?']*len(chunk))
        price_parts.append(db.read_sql(f'SELECT security_code,trade_date,close_adj FROM security_prices WHERE security_code IN ({marks}) AND trade_date BETWEEN ? AND ? ORDER BY security_code,trade_date',tuple(chunk)+ (dmin,dmax)))
    prices=pd.concat([x for x in price_parts if not x.empty],ignore_index=True) if any(not x.empty for x in price_parts) else pd.DataFrame(columns=['security_code','trade_date','close_adj'])
    price_map={str(c):g[['trade_date','close_adj']].copy() for c,g in prices.groupby('security_code')} if not prices.empty else {}
    rows=[]
    for i in range(1,len(periods)):
        p0,p1=periods[i-1],periods[i];d0=_period_end(p0);d1=_period_end(p1)
        if d0 is None or d1 is None:continue
        n0=_nearest_value(nav,'nav_date','unit_nav',d0,True);n1=_nearest_value(nav,'nav_date','unit_nav',d1,True)
        if not n0 or not n1:continue
        fund_ret=(n1/n0-1)*100;a=_period_frame(h,p0);contrib=0;covered=0;valid=0
        for _,r in a.iterrows():
            px=price_map.get(str(r.stock_code),pd.DataFrame())
            pxa=_nearest_value(px,'trade_date','close_adj',d0,False);pxb=_nearest_value(px,'trade_date','close_adj',d1,True)
            w=_safe(r.weight_pct,0)
            if pxa and pxb and w>0:
                rr=(pxb/pxa-1)*100;contrib+=(w/100)*rr;covered+=w;valid+=1
        if valid==0:continue
        gap=fund_ret-contrib;confidence='高' if covered>=75 else '中' if covered>=50 else '低'
        rows.append({'from_period':p0,'to_period':p1,'fund_return_pct':round(fund_ret,2),'disclosed_contribution_pct':round(contrib,2),'return_gap_pct':round(gap,2),'holding_weight_coverage_pct':round(covered,2),'priced_securities':valid,'confidence':confidence,'nav_code':nav_code})
    return rows


def fund_advanced(code,mode='demo'):
    key=(db.data_revision(),mode,str(code))
    if mode=='local':
        with _ADV_CACHE_LOCK:cached=_ttl_get(_FUND_ADV_CACHE,key)
        if cached is not None:return cached
    h=services.holdings(mode,code,enriched=True)
    if h.empty:return {'periods':[],'style_history':[],'latest_style':None,'hidden_signals':[],'share_coverage_pct':0,'sankey':{'nodes':[],'links':[]},'return_gap':[],'method':'no_data'}
    periods=services.sort_periods(h.quarter.tolist());styles=_style_history(h,mode);hidden=[];coverage=0;sankey={'nodes':[],'links':[]};p0=p1=None
    if len(periods)>=2:
        p0,p1=periods[-2],periods[-1];hidden,coverage=_hidden_signals(h,p0,p1);sankey=_fund_sankey(h,p0,p1)
    gap=[] if mode=='demo' else _return_gap_series(code,h)
    cmp_meta=_compare(h,p0,p1).attrs.get('comparison_meta') if p0 and p1 else None
    out=services.clean_payload({'periods':periods,'from_period':p0,'to_period':p1,'style_history':styles,'latest_style':styles[-1] if styles else None,'hidden_signals':hidden,'share_coverage_pct':coverage,'sankey':sankey,'return_gap':gap,'method':'security_master' if mode=='local' and db.count('security_master') else 'structure_only','data_context':{'comparison':cmp_meta,'basis_label':disclosure.context_label(cmp_meta),'note':'连续季度风格与调仓统一按前十大披露持仓比较。'}})
    if mode=='local':
        with _ADV_CACHE_LOCK:_ttl_put(_FUND_ADV_CACHE,key,out,45.0,64)
    return out


def manager_style_timeline(name,mode='demo',company=None):
    cache_key=(db.data_revision(),mode,str(name),str(company or ''))
    with _ADV_CACHE_LOCK:cached=_ttl_get(_MANAGER_STYLE_CACHE,cache_key)
    if cached is not None:return cached
    detail=services.manager_detail(name,mode,company)
    if not detail:return None
    codes=detail.get('fund_codes') or [];period_map={};funds_used=0;seen=set()
    for c in codes:
        if mode=='local':
            rr=fund_master.resolve(c);key=rr.get('master_id') or str(c)
            if key in seen:continue
            seen.add(key)
        wanted=None
        if mode=='local':
            ps=services.fund_periods(mode,c);wanted=ps[-24:] if ps else None
        h=services.holdings(mode,c,wanted)
        if h.empty:continue
        funds_used+=1
        for s in _style_history(h,mode):period_map.setdefault(s['period'],[]).append(s)
    timeline=[]
    for p in sorted(period_map,key=services.period_key):
        arr=period_map[p];row={'period':p,'fund_count':len(arr)}
        for k in ['size_score','value_growth_score','sector_concentration','top10_concentration','drift_score','style_data_coverage']:
            vals=[x[k] for x in arr if x.get(k) is not None];row[k]=round(float(np.mean(vals)),2) if vals else None
        timeline.append(row)
    tenure=db.read_sql('SELECT COUNT(*) n FROM manager_tenure')
    attribution='historical_tenure' if not tenure.empty and int(tenure.iloc[0]['n'])>0 else 'current_product_set'
    out=services.clean_payload({'manager':detail['manager'],'timeline':timeline,'funds_used':funds_used,'attribution_basis':attribution})
    with _ADV_CACHE_LOCK:_ttl_put(_MANAGER_STYLE_CACHE,cache_key,out,300.0,96)
    return out


def institutional_migration(mode='demo'):
    sec=services.sectors(mode)
    periods=services.sort_periods(sec.quarter.tolist()) if not sec.empty else []
    if len(periods)<2:return {'periods':periods,'from_period':None,'to_period':None,'sankey':{'nodes':[],'links':[]},'basis':'market_report'}
    p0,p1=periods[-2],periods[-1];a=sec[sec.quarter==p0][['sector','weight_pct']].rename(columns={'weight_pct':'old'});b=sec[sec.quarter==p1][['sector','weight_pct']].rename(columns={'weight_pct':'new'});m=a.merge(b,on='sector',how='outer').fillna(0);m['delta']=m['new']-m['old'];m=m.rename(columns={'sector':'name'})
    sankey=_migration_sankey_from_delta(m[['name','delta']],'name','sector')
    leaders=m.sort_values('delta',ascending=False)
    return services.clean_payload({'periods':periods,'from_period':p0,'to_period':p1,'sankey':sankey,'basis':'market_report','increases':leaders.head(10).to_dict('records'),'decreases':leaders.tail(10).sort_values('delta').to_dict('records')})
