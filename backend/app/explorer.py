import math
import time
import threading
from pathlib import Path
from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from . import advanced, db, demo_data, fund_master, services, disclosure

_CACHE: dict[tuple[Any, ...], Any] = {}
_CACHE_LOCK=threading.Lock()
_CACHE_PENDING: dict[tuple[Any, ...], threading.Event] = {}


def _db_signature():
    # Kept for compatibility with older tests/extensions. Analytics caching in V9.0.2
    # intentionally uses a TTL instead of the SQLite WAL mtime, because research notes,
    # recents and task heartbeats also touch the WAL and used to invalidate heavy analytics.
    parts = []
    for path in [db.DB_PATH, Path(str(db.DB_PATH) + "-wal")]:
        try:
            st = path.stat();parts.extend([st.st_mtime_ns, st.st_size])
        except Exception:parts.extend([0, 0])
    return tuple(parts)


def _cached(key, builder, ttl=90.0):
    """TTL cache with single-flight protection for heavy cross-sectional analytics.

    React can prefetch a view at the same moment the user opens another view that
    depends on the same fund cross-section. V9.2.0 allowed both requests to rebuild
    the same pandas snapshot concurrently. Here later callers wait for the first
    computation and reuse its result.
    """
    cache_key=tuple(key);now=time.monotonic();owner=False
    with _CACHE_LOCK:
        hit=_CACHE.get(cache_key)
        if hit and isinstance(hit,tuple) and len(hit)==2 and hit[0]>now:return hit[1]
        event=_CACHE_PENDING.get(cache_key)
        if event is None:
            event=threading.Event();_CACHE_PENDING[cache_key]=event;owner=True
    if not owner:
        event.wait(timeout=120.0)
        with _CACHE_LOCK:
            hit=_CACHE.get(cache_key)
            if hit and isinstance(hit,tuple) and len(hit)==2 and hit[0]>time.monotonic():return hit[1]
        # If the owner failed or timed out, allow this caller to retry normally.
        return builder()
    try:
        value=builder();now=time.monotonic()
        with _CACHE_LOCK:
            if len(_CACHE)>40:
                expired=[k for k,v in _CACHE.items() if isinstance(v,tuple) and len(v)==2 and v[0]<=now]
                for k in expired:_CACHE.pop(k,None)
                if len(_CACHE)>40:_CACHE.clear()
            _CACHE[cache_key]=(now+float(ttl),value)
        return value
    finally:
        with _CACHE_LOCK:
            done=_CACHE_PENDING.pop(cache_key,None)
            if done:done.set()


def _local_period_catalog(period_hint=None):
    """Return recent canonical Fund-Master coverage without loading the full holdings history."""
    hint=services.normalize_period(period_hint) if period_hint else ''
    hint_year=int(hint[:4]) if len(hint)>=4 and hint[:4].isdigit() else None
    def build():
        fund_master.ensure_master()
        if hint_year is None:
            y=db.read_sql("SELECT MAX(requested_year) AS y FROM fund_holdings")
            max_year=int(y.iloc[0]['y']) if not y.empty and pd.notna(y.iloc[0]['y']) else None
        else:max_year=hint_year
        if max_year is None:return []
        lo=max_year-2 if hint_year is None else max_year
        hi=max_year
        raw=db.read_sql("""
            SELECT h.quarter,mm.master_id
            FROM fund_holdings h
            JOIN fund_master_members mm ON mm.fund_code=h.fund_code
            JOIN fund_master m ON m.master_id=mm.master_id
            WHERE m.eligible_equity=1 AND h.requested_year BETWEEN ? AND ?
            GROUP BY h.quarter,mm.master_id
        """,(lo,hi))
        if raw.empty:return []
        raw['quarter']=raw['quarter'].map(services.normalize_period)
        raw=raw[raw.quarter.astype(str).str.len()>0]
        out=raw.groupby('quarter',as_index=False).master_id.nunique().rename(columns={'master_id':'fund_count'})
        out['_key']=out.quarter.map(services.period_key);out=out.sort_values('_key').drop(columns='_key')
        return services.clean_payload(out.to_dict('records'))
    return _cached(('local_period_catalog',hint_year),build,300.0)


def _select_local_period(period=None):
    counts=_local_period_catalog(period)
    periods=[x['quarter'] for x in counts]
    if not periods:return None,counts
    wanted=services.normalize_period(period) if period else ''
    if wanted in periods:return wanted,counts
    max_count=max(int(x.get('fund_count') or 0) for x in counts)
    eligible=[x['quarter'] for x in counts if int(x.get('fund_count') or 0)>=max(3,int(max_count*.35))]
    return (eligible[-1] if eligible else periods[-1]),counts


def _canonical_snapshot_local(periods):
    periods=services.sort_periods([services.normalize_period(x) for x in periods if x])
    if not periods:return pd.DataFrame()
    years=sorted({int(p[:4]) for p in periods if len(p)>=4 and p[:4].isdigit()})
    def build():
        fund_master.ensure_master()
        marks=','.join(['?']*len(years))
        raw=db.read_sql(f"""
            SELECT m.master_id,m.master_name,m.fund_type,m.representative_code,
                   mm.is_representative,h.fund_code,h.quarter,h.stock_code,h.stock_name,
                   h.weight_pct,h.shares,h.market_value_wan,h.report_type,h.disclosure_scope,h.fetched_at,
                   COALESCE(NULLIF(s.industry_l1,''),'未分类') AS sector,
                   s.total_market_cap,s.float_market_cap,s.pe,s.pb,
                   s.revenue_growth_yoy,s.profit_growth_yoy
            FROM fund_holdings h
            JOIN fund_master_members mm ON mm.fund_code=h.fund_code
            JOIN fund_master m ON m.master_id=mm.master_id
            LEFT JOIN security_master s ON s.security_code=h.stock_code
            WHERE m.eligible_equity=1 AND h.requested_year IN ({marks})
        """,tuple(years))
        if raw.empty:return raw
        raw['quarter']=raw['quarter'].map(services.normalize_period)
        raw=raw[raw.quarter.isin(periods)].copy()
        if raw.empty:return raw
        for col in ['weight_pct','shares','market_value_wan','total_market_cap','float_market_cap','pe','pb','revenue_growth_yoy','profit_growth_yoy']:
            raw[col]=pd.to_numeric(raw[col],errors='coerce')
        availability=(raw.groupby(['master_id','quarter','fund_code'],as_index=False)
            .agg(is_representative=('is_representative','max'),row_count=('stock_code','nunique'))
            .sort_values(['master_id','quarter','is_representative','row_count','fund_code'],ascending=[True,True,False,False,True]))
        chosen=availability.groupby(['master_id','quarter'],as_index=False).head(1)[['master_id','quarter','fund_code']]
        out=raw.merge(chosen,on=['master_id','quarter','fund_code'],how='inner').drop_duplicates(['master_id','quarter','stock_code'],keep='first')
        return out
    return _cached(('canonical_snapshot_local',tuple(periods)),build,120.0).copy()


def _history_meta_for_current(cur):
    if cur is None or cur.empty:return {}
    codes=cur[['master_id','fund_code']].drop_duplicates().copy();result={}
    fund_codes=codes.fund_code.astype(str).tolist();code_to_mid=dict(zip(codes.fund_code.astype(str),codes.master_id.astype(str)))
    for i in range(0,len(fund_codes),800):
        chunk=fund_codes[i:i+800];marks=','.join(['?']*len(chunk))
        x=db.read_sql(f"SELECT fund_code,COUNT(DISTINCT quarter) AS n,MIN(requested_year) AS y FROM fund_holdings WHERE fund_code IN ({marks}) GROUP BY fund_code",tuple(chunk))
        for _,r in x.iterrows():
            mid=code_to_mid.get(str(r.fund_code));
            if mid:result[mid]={'history_periods':int(r.n or 0),'history_start':f"{int(r.y)}Q1" if pd.notna(r.y) else None}
    return result


def _style_cross_section(frame, refs):
    """Vectorized style snapshot for many Fund Masters at one period."""
    if frame is None or frame.empty:return pd.DataFrame()
    x=frame.copy();x['master_id']=x['master_id'].astype(str);x['weight_pct']=pd.to_numeric(x['weight_pct'],errors='coerce').fillna(0).clip(lower=0)
    total=x.groupby('master_id')['weight_pct'].sum().rename('total_weight')
    # Precompute security-level style references once, then map all holdings in one pass.
    codes=x['stock_code'].astype(str)
    x['_size_ref']=codes.map(refs.get('size',{}))
    growth_map={}
    for c in codes.drop_duplicates().tolist():
        vals=[]
        for k,w in [('pb',.30),('pe',.20),('rev',.25),('profit',.25)]:
            v=refs.get(k,{}).get(c)
            if v is not None:vals.append((float(v),w))
        growth_map[c]=(sum(v*w for v,w in vals)/sum(w for _,w in vals)) if vals else np.nan
    x['_growth_ref']=codes.map(growth_map)
    out=pd.DataFrame(index=total.index)
    coverages=[]
    for source,name in [('_size_ref','size_score'),('_growth_ref','value_growth_score')]:
        valid=x[source].notna() & x['weight_pct'].gt(0)
        t=x.loc[valid,['master_id','weight_pct',source]].copy()
        if t.empty:
            out[name]=np.nan;coverages.append(pd.Series(0.0,index=out.index));continue
        t['_num']=t['weight_pct']*pd.to_numeric(t[source],errors='coerce')
        num=t.groupby('master_id')['_num'].sum();den=t.groupby('master_id')['weight_pct'].sum()
        out[name]=(num/den).reindex(out.index)
        coverages.append((den/total*100).reindex(out.index).fillna(0))
    if coverages:out['style_data_coverage']=pd.concat(coverages,axis=1).mean(axis=1)
    mapped=x[~x['sector'].fillna('未分类').eq('未分类')].copy()
    if mapped.empty:
        out['sector_concentration']=np.nan;out['sector_coverage_pct']=0.0;out['top_sector']='未分类';out['top_sector_weight']=np.nan
    else:
        sec=mapped.groupby(['master_id','sector'],as_index=False)['weight_pct'].sum()
        mapped_total=sec.groupby('master_id')['weight_pct'].sum().rename('_mapped_total')
        sec=sec.join(mapped_total,on='master_id');sec['_share']=sec['weight_pct']/sec['_mapped_total'].replace(0,np.nan);sec['_sq']=sec['_share']**2
        out['sector_concentration']=(sec.groupby('master_id')['_sq'].sum()*100).reindex(out.index)
        out['sector_coverage_pct']=(mapped_total/total*100).reindex(out.index).fillna(0)
        top=sec.sort_values(['master_id','weight_pct'],ascending=[True,False]).groupby('master_id',as_index=False).head(1).set_index('master_id')
        out['top_sector']=top['sector'].reindex(out.index).fillna('未分类');out['top_sector_weight']=top['weight_pct'].reindex(out.index)
    return out.reset_index()


def _sector_js_cross_section(old_frame,new_frame):
    if old_frame is None or new_frame is None or old_frame.empty or new_frame.empty:return pd.Series(dtype=float)
    def sec(frame,label):
        x=frame[~frame['sector'].fillna('未分类').eq('未分类')].copy();x['weight_pct']=pd.to_numeric(x['weight_pct'],errors='coerce').fillna(0).clip(lower=0)
        if x.empty:return pd.DataFrame(columns=['master_id','sector',label])
        g=x.groupby(['master_id','sector'],as_index=False)['weight_pct'].sum();tot=g.groupby('master_id')['weight_pct'].transform('sum').replace(0,np.nan);g[label]=g['weight_pct']/tot
        return g[['master_id','sector',label]]
    a=sec(old_frame,'pa');b=sec(new_frame,'pb');m=a.merge(b,on=['master_id','sector'],how='outer').fillna(0)
    if m.empty:return pd.Series(dtype=float)
    mid=(m['pa']+m['pb'])/2
    ta=np.zeros(len(m),dtype=float);tb=np.zeros(len(m),dtype=float)
    ma=(m['pa']>0)&(mid>0);mb=(m['pb']>0)&(mid>0)
    ta[ma.to_numpy()]=(m.loc[ma,'pa']*np.log2(m.loc[ma,'pa']/mid.loc[ma])).to_numpy()
    tb[mb.to_numpy()]=(m.loc[mb,'pb']*np.log2(m.loc[mb,'pb']/mid.loc[mb])).to_numpy()
    m['_js']=0.5*(ta+tb)
    return m.groupby('master_id')['_js'].sum().clip(lower=0,upper=1)


def _fund_explorer_local_fast(period=None):
    selected,period_counts=_select_local_period(period);all_periods=[x['quarter'] for x in period_counts]
    if not selected:return {'periods':all_periods,'selected_period':None,'period_coverage':period_counts,'rows':[],'thresholds':{},'view_counts':{}}
    idx=all_periods.index(selected) if selected in all_periods else -1;prev=all_periods[idx-1] if idx>0 else None
    h=_canonical_snapshot_local([p for p in [prev,selected] if p]);current=h[h.quarter==selected].copy() if not h.empty else pd.DataFrame();previous=h[h.quarter==prev].copy() if prev and not h.empty else pd.DataFrame()
    if current.empty:return {'periods':all_periods,'selected_period':selected,'period_coverage':period_counts,'rows':[],'thresholds':{},'view_counts':{}}
    for x in [current,previous]:
        if not x.empty:
            x['master_id']=x['master_id'].astype(str);x['stock_code']=x['stock_code'].astype(str);x['weight_pct']=pd.to_numeric(x['weight_pct'],errors='coerce').fillna(0).clip(lower=0)
    refs=_cached(('style_reference_local',),lambda:advanced._style_reference('local'),300.0);history_meta=_history_meta_for_current(current)
    # Current-period summary and concentration use the disclosed snapshot itself.
    cur_sorted=current.sort_values(['master_id','weight_pct'],ascending=[True,False]);cur_sorted['_rank']=cur_sorted.groupby('master_id').cumcount()+1
    base=cur_sorted.groupby('master_id',as_index=True).agg(holdings_count=('stock_code','nunique'))
    base['top5_concentration']=cur_sorted[cur_sorted['_rank']<=5].groupby('master_id')['weight_pct'].sum();base['top10_concentration']=cur_sorted[cur_sorted['_rank']<=10].groupby('master_id')['weight_pct'].sum()
    first=current.sort_values(['master_id','weight_pct'],ascending=[True,False]).groupby('master_id',as_index=True).first()
    base['fund_code']=first['representative_code'].fillna(first['fund_code']).astype(str);base['fund_name']=first['master_name'].astype(str);base['fund_type']=first['fund_type'].astype(str)
    # Normalize disclosure scope per Fund Master in bulk. A minority of source rows can
    # occasionally carry a different explicit scope even in the same report period;
    # keep Full Portfolio only for masters whose two snapshots are both full scope.
    comparison_basis_map=pd.Series(index=base.index,dtype=object);comparison_note_map=pd.Series(index=base.index,dtype=object)
    if prev and not previous.empty:
        def scope_by_master(frame,period):
            z=frame[['master_id','disclosure_scope']].copy() if 'disclosure_scope' in frame.columns else frame[['master_id']].assign(disclosure_scope=None)
            z['_scope']=z['disclosure_scope'].map(lambda v:disclosure.scope_for_period(period,v))
            return z.groupby('master_id')['_scope'].agg(lambda vals:'top10' if (vals=='top10').any() else 'full' if (vals=='full').any() else disclosure.scope_for_period(period))
        old_sc=scope_by_master(previous,prev);new_sc=scope_by_master(current,selected);scope=pd.concat([old_sc.rename('old'),new_sc.rename('new')],axis=1).reindex(base.index)
        comparison_basis_map=pd.Series(np.where((scope['old']=='full')&(scope['new']=='full'),'full_portfolio','top10_comparable'),index=base.index)
        comparison_note_map=comparison_basis_map.map({'full_portfolio':'两期均为较完整披露，按完整组合比较','top10_comparable':'两期统一按前十大披露持仓比较'})
        full_mids=set(comparison_basis_map[comparison_basis_map=='full_portfolio'].index.astype(str));top_mids=set(comparison_basis_map[comparison_basis_map!='full_portfolio'].index.astype(str))
        ptop=previous.sort_values(['master_id','weight_pct'],ascending=[True,False]).groupby('master_id',as_index=False).head(10).copy();ctop=cur_sorted[cur_sorted['_rank']<=10].drop(columns='_rank').copy()
        parts_p=[];parts_c=[]
        if full_mids:
            parts_p.append(previous[previous.master_id.astype(str).isin(full_mids)].copy());parts_c.append(current[current.master_id.astype(str).isin(full_mids)].copy())
        if top_mids:
            parts_p.append(ptop[ptop.master_id.astype(str).isin(top_mids)].copy());parts_c.append(ctop[ctop.master_id.astype(str).isin(top_mids)].copy())
        p=pd.concat(parts_p,ignore_index=True) if parts_p else previous.iloc[0:0].copy();c=pd.concat(parts_c,ignore_index=True) if parts_c else current.iloc[0:0].copy()
        a=p[['master_id','stock_code','weight_pct']].rename(columns={'weight_pct':'old'});b=c[['master_id','stock_code','weight_pct']].rename(columns={'weight_pct':'new'});chg=a.merge(b,on=['master_id','stock_code'],how='outer')
        chg['_old_present']=chg['old'].notna();chg['_new_present']=chg['new'].notna();chg['old']=pd.to_numeric(chg['old'],errors='coerce').fillna(0);chg['new']=pd.to_numeric(chg['new'],errors='coerce').fillna(0);chg['_abs']=(chg['new']-chg['old']).abs()
        g=chg.groupby('master_id');base['turnover_pct']=(g['_abs'].sum()/2).reindex(base.index);inter=g.apply(lambda z:int((z['_old_present']&z['_new_present']).sum()),include_groups=False);union=g.apply(lambda z:int((z['_old_present']|z['_new_present']).sum()),include_groups=False)
        base['retention_pct']=(inter/union.replace(0,np.nan)*100).reindex(base.index);base['new_positions']=g.apply(lambda z:int((~z['_old_present']&z['_new_present']).sum()),include_groups=False).reindex(base.index).fillna(0);base['exits']=g.apply(lambda z:int((z['_old_present']&~z['_new_present']).sum()),include_groups=False).reindex(base.index).fillna(0)
        cur_style=_style_cross_section(c,refs).set_index('master_id');prev_style=_style_cross_section(p,refs).set_index('master_id')
        for col in ['size_score','value_growth_score','style_data_coverage','sector_concentration','sector_coverage_pct','top_sector','top_sector_weight']:base[col]=cur_style[col].reindex(base.index) if col in cur_style else np.nan
        factor_parts=[]
        for col in ['size_score','value_growth_score']:
            d=(pd.to_numeric(cur_style.get(col),errors='coerce')-pd.to_numeric(prev_style.get(col),errors='coerce')).abs()/100;factor_parts.append(d.rename(col))
        factor_shift=pd.concat(factor_parts,axis=1).mean(axis=1,skipna=True) if factor_parts else pd.Series(dtype=float)
        js=_sector_js_cross_section(p,c);conc_shift=(pd.to_numeric(cur_style.get('sector_concentration'),errors='coerce')-pd.to_numeric(prev_style.get('sector_concentration'),errors='coerce')).abs()/100
        sector_shift=pd.concat([js.rename('js'),conc_shift.rename('conc')],axis=1).mean(axis=1,skipna=True)
        concentration_shift=(pd.to_numeric(cur_style.get('top10_concentration'),errors='coerce')-pd.to_numeric(prev_style.get('top10_concentration'),errors='coerce')).abs()/60 if 'top10_concentration' in cur_style and 'top10_concentration' in prev_style else (base['top10_concentration']*np.nan)
        # _style_cross_section does not emit top10 because the bulk rank sum is already in base; derive comparable top10 here.
        def top10_series(frame):
            z=frame.sort_values(['master_id','weight_pct'],ascending=[True,False]);z['_r']=z.groupby('master_id').cumcount()+1;return z[z['_r']<=10].groupby('master_id')['weight_pct'].sum()
        tcur=top10_series(c);tprev=top10_series(p);concentration_shift=(tcur-tprev).abs()/60
        structural=(pd.to_numeric(base['turnover_pct'],errors='coerce').fillna(0)/25).clip(upper=1)
        parts=pd.concat([factor_shift.rename('factor'),sector_shift.rename('sector'),concentration_shift.rename('conc'),structural.rename('struct')],axis=1).reindex(base.index)
        weights={'factor':.35,'sector':.30,'conc':.20,'struct':.15};num=pd.Series(0.0,index=base.index);den=pd.Series(0.0,index=base.index)
        for col,w in weights.items():valid=parts[col].notna();num.loc[valid]+=parts.loc[valid,col]*w;den.loc[valid]+=w
        base['drift_score']=(num/den.replace(0,np.nan)*100);base['factor_shift']=factor_shift.reindex(base.index)*100;base['sector_shift']=sector_shift.reindex(base.index)*100;base['concentration_shift']=concentration_shift.reindex(base.index)*100
    else:
        base['turnover_pct']=np.nan;base['retention_pct']=np.nan;base['new_positions']=0;base['exits']=0;base['drift_score']=np.nan;base['factor_shift']=np.nan;base['sector_shift']=np.nan;base['concentration_shift']=np.nan
        cur_style=_style_cross_section(current,refs).set_index('master_id')
        for col in ['size_score','value_growth_score','style_data_coverage','sector_concentration','sector_coverage_pct','top_sector','top_sector_weight']:base[col]=cur_style[col].reindex(base.index) if col in cur_style else np.nan
    base['period']=selected;base['prev_period']=prev;base['comparison_basis']=comparison_basis_map.reindex(base.index);base['comparison_note']=comparison_note_map.reindex(base.index)
    base['history_periods']=[history_meta.get(str(mid),{}).get('history_periods') for mid in base.index];base['history_start']=[history_meta.get(str(mid),{}).get('history_start') for mid in base.index]
    df=base.reset_index().rename(columns={'index':'master_id'});df['new_positions']=pd.to_numeric(df['new_positions'],errors='coerce').fillna(0).astype(int);df['exits']=pd.to_numeric(df['exits'],errors='coerce').fillna(0).astype(int)
    for col in ['top5_concentration','top10_concentration','turnover_pct','retention_pct','top_sector_weight','sector_coverage_pct','size_score','value_growth_score','style_data_coverage','sector_concentration','drift_score','factor_shift','sector_shift','concentration_shift']:
        if col in df:df[col]=pd.to_numeric(df[col],errors='coerce').round(2)
    thresholds={'turnover_high':_quantile(df,'turnover_pct',.80),'turnover_low':_quantile(df,'turnover_pct',.20),'concentration_high':_quantile(df,'top10_concentration',.80),'concentration_low':_quantile(df,'top10_concentration',.20),'drift_high':_quantile(df,'drift_score',.80),'retention_high':_quantile(df,'retention_pct',.80)}
    def tags_for(r):
        tags=[]
        if thresholds['drift_high'] is not None and pd.notna(r.get('drift_score')) and float(r['drift_score'])>=thresholds['drift_high']:tags.append('风格漂移')
        if thresholds['turnover_high'] is not None and pd.notna(r.get('turnover_pct')) and float(r['turnover_pct'])>=thresholds['turnover_high']:tags.append('高换手')
        if thresholds['concentration_high'] is not None and pd.notna(r.get('top10_concentration')) and float(r['top10_concentration'])>=thresholds['concentration_high']:tags.append('高集中')
        if thresholds['turnover_low'] is not None and thresholds['retention_high'] is not None and pd.notna(r.get('turnover_pct')) and pd.notna(r.get('retention_pct')) and float(r['turnover_pct'])<=thresholds['turnover_low'] and float(r['retention_pct'])>=thresholds['retention_high'] and int(r.get('history_periods') or 0)>=3:tags.append('稳定持有')
        if thresholds['concentration_low'] is not None and pd.notna(r.get('top10_concentration')) and float(r['top10_concentration'])<=thresholds['concentration_low']:tags.append('分散持仓')
        return tags
    df['tags']=df.apply(tags_for,axis=1);counter=Counter(t for ts in df.tags for t in ts);df['_sort']=pd.to_numeric(df.drift_score,errors='coerce').fillna(-1);df=df.sort_values(['_sort','turnover_pct','top10_concentration'],ascending=[False,False,False]).drop(columns='_sort')
    return services.clean_payload({'periods':all_periods[-12:],'selected_period':selected,'period_coverage':period_counts[-12:],'rows':df.to_dict('records'),'thresholds':thresholds,'view_counts':dict(counter)})

def _canonical_holdings(mode="local"):
    """Return one holdings record set per Fund Master and report period.

    Multiple share classes can have identical portfolio disclosures. This helper chooses one available
    share class for each master-period, preferring the representative share, so cross-sectional analysis
    does not double count A/C/E/front-end/back-end variants.
    """
    if mode == "demo":
        h = demo_data.holdings().copy()
        f = demo_data.FUNDS[["fund_code", "fund_name", "fund_type"]].copy()
        h = h.merge(f, on="fund_code", how="left")
        h["master_id"] = h["fund_code"].astype(str)
        h["master_name"] = h["fund_name"]
        h["representative_code"] = h["fund_code"].astype(str)
        h["is_representative"] = 1
        for col in ["total_market_cap", "float_market_cap", "pe", "pb", "revenue_growth_yoy", "profit_growth_yoy"]:
            if col not in h:
                h[col] = np.nan
        h["quarter"] = h["quarter"].map(services.normalize_period)
        return h

    def build():
        fund_master.ensure_master()
        raw = db.read_sql(
            """
            SELECT m.master_id,m.master_name,m.fund_type,m.representative_code,
                   mm.is_representative,h.fund_code,h.quarter,h.stock_code,h.stock_name,
                   h.weight_pct,h.shares,h.market_value_wan,h.report_type,h.disclosure_scope,h.fetched_at,
                   COALESCE(NULLIF(s.industry_l1,''),'未分类') AS sector,
                   s.total_market_cap,s.float_market_cap,s.pe,s.pb,
                   s.revenue_growth_yoy,s.profit_growth_yoy
            FROM fund_master m
            JOIN fund_master_members mm ON mm.master_id=m.master_id
            JOIN fund_holdings h ON h.fund_code=mm.fund_code
            LEFT JOIN security_master s ON s.security_code=h.stock_code
            WHERE m.eligible_equity=1
            """
        )
        if raw.empty:
            return raw
        raw["quarter"] = raw["quarter"].map(services.normalize_period)
        raw = raw[raw["quarter"].astype(str).str.len() > 0].copy()
        for col in ["weight_pct", "shares", "market_value_wan", "total_market_cap", "float_market_cap", "pe", "pb", "revenue_growth_yoy", "profit_growth_yoy"]:
            raw[col] = pd.to_numeric(raw[col], errors="coerce")

        availability = (
            raw.groupby(["master_id", "quarter", "fund_code"], as_index=False)
            .agg(is_representative=("is_representative", "max"), row_count=("stock_code", "nunique"))
            .sort_values(["master_id", "quarter", "is_representative", "row_count", "fund_code"], ascending=[True, True, False, False, True])
        )
        chosen = availability.groupby(["master_id", "quarter"], as_index=False).head(1)[["master_id", "quarter", "fund_code"]]
        out = raw.merge(chosen, on=["master_id", "quarter", "fund_code"], how="inner")
        out = out.drop_duplicates(["master_id", "quarter", "stock_code"], keep="first")
        out["_period_key"] = out["quarter"].map(services.period_key)
        return out.sort_values(["_period_key", "master_id", "weight_pct"], ascending=[True, True, False]).drop(columns="_period_key")

    return _cached(("canonical_holdings",), build).copy()


def _period_counts(h):
    if h is None or h.empty:
        return []
    x = h[["quarter", "master_id"]].drop_duplicates()
    rows = x.groupby("quarter", as_index=False).master_id.nunique().rename(columns={"master_id": "fund_count"})
    rows["_key"] = rows["quarter"].map(services.period_key)
    rows = rows.sort_values("_key").drop(columns="_key")
    return services.clean_payload(rows.to_dict("records"))


def _select_period(h, period=None):
    counts = _period_counts(h)
    periods = [x["quarter"] for x in counts]
    if not periods:
        return None, counts
    normalized = services.normalize_period(period) if period else ""
    if normalized in periods:
        return normalized, counts
    max_count = max(int(x["fund_count"]) for x in counts) if counts else 0
    eligible = [x["quarter"] for x in counts if int(x["fund_count"]) >= max(3, int(max_count * 0.35))]
    return (eligible[-1] if eligible else periods[-1]), counts


def _sector_distribution(x):
    if x is None or x.empty:
        return {}, 0.0
    mapped = x[~x["sector"].fillna("未分类").eq("未分类")].copy()
    total = float(pd.to_numeric(x["weight_pct"], errors="coerce").fillna(0).clip(lower=0).sum())
    if mapped.empty or total <= 0:
        return {}, 0.0
    dist = mapped.groupby("sector")["weight_pct"].sum().clip(lower=0).to_dict()
    mapped_weight = float(sum(dist.values()))
    return dist, round(mapped_weight / total * 100, 2)


def _top10_by_master_period(h):
    if h is None or h.empty:return h.copy() if isinstance(h,pd.DataFrame) else pd.DataFrame()
    x=h.copy();x['weight_pct']=pd.to_numeric(x['weight_pct'],errors='coerce')
    if 'master_id' in x.columns:
        x=x.sort_values(['master_id','quarter','weight_pct'],ascending=[True,True,False],na_position='last')
        x['_cmp_rank']=x.groupby(['master_id','quarter']).cumcount()+1
        return x[x['_cmp_rank']<=10].drop(columns='_cmp_rank').copy()
    parts=[]
    for p,g in x.groupby('quarter'):parts.append(disclosure.top_n(g,10))
    return pd.concat(parts,ignore_index=True) if parts else x.iloc[0:0].copy()


def _drift_components(cur, prev, refs, mode, turnover):
    if cur is None or prev is None or cur.empty or prev.empty:
        return {"drift_score": None, "factor_shift": None, "sector_shift": None, "concentration_shift": None}
    pcur = str(cur.iloc[0]["quarter"])
    pprev = str(prev.iloc[0]["quarter"])
    prev_cmp,cur_cmp,_meta=disclosure.comparable_pair(prev,cur,pprev,pcur)
    scur = advanced._snapshot_style(cur_cmp, pcur, refs, mode)
    sprev = advanced._snapshot_style(prev_cmp, pprev, refs, mode)
    if not scur or not sprev:
        return {"drift_score": None, "factor_shift": None, "sector_shift": None, "concentration_shift": None}

    factor_parts = []
    for k in ["size_score", "value_growth_score"]:
        if scur.get(k) is not None and sprev.get(k) is not None:
            factor_parts.append(abs(float(scur[k]) - float(sprev[k])) / 100)
    factor_shift = float(np.mean(factor_parts)) if factor_parts else None

    sector_js = None
    sector_conc = None
    if sprev.get("sector_dist") and scur.get("sector_dist"):
        sector_js = advanced._js_divergence(sprev["sector_dist"], scur["sector_dist"])
    if scur.get("sector_concentration") is not None and sprev.get("sector_concentration") is not None:
        sector_conc = abs(float(scur["sector_concentration"]) - float(sprev["sector_concentration"])) / 100
    sector_parts = [v for v in [sector_js, sector_conc] if v is not None]
    sector_shift = float(np.mean(sector_parts)) if sector_parts else None

    concentration_shift = None
    if scur.get("top10_concentration") is not None and sprev.get("top10_concentration") is not None:
        concentration_shift = abs(float(scur["top10_concentration"]) - float(sprev["top10_concentration"])) / 60
    structural = min(1.0, float(turnover or 0) / 25.0)
    parts = [(0.35, factor_shift), (0.30, sector_shift), (0.20, concentration_shift), (0.15, structural)]
    valid = [(w, v) for w, v in parts if v is not None]
    drift = 100 * sum(w * v for w, v in valid) / sum(w for w, _ in valid) if valid else None
    return {
        "drift_score": round(drift, 2) if drift is not None else None,
        "factor_shift": round((factor_shift or 0) * 100, 2) if factor_shift is not None else None,
        "sector_shift": round((sector_shift or 0) * 100, 2) if sector_shift is not None else None,
        "concentration_shift": round((concentration_shift or 0) * 100, 2) if concentration_shift is not None else None,
        "style": scur,
    }


def _quantile(df, col, q, fallback=None):
    if df.empty or col not in df:
        return fallback
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    return fallback if s.empty else float(s.quantile(q))


def fund_explorer(mode="demo", period=None):
    if mode=="local":
        return _cached(("fund_explorer_local",services.normalize_period(period) if period else "latest"),lambda:_fund_explorer_local_fast(period),600.0)
    h = _canonical_holdings(mode)
    selected, period_counts = _select_period(h, period)
    if h.empty or not selected:
        return {"periods": [], "selected_period": None, "period_coverage": [], "rows": [], "thresholds": {}, "view_counts": {}}

    refs = advanced._style_reference(mode)
    rows = []
    selected_key = services.period_key(selected)
    for mid, g in h.groupby("master_id"):
        periods = services.sort_periods(g["quarter"].tolist())
        if selected not in periods:
            continue
        current = g[g.quarter == selected].copy()
        prev_periods = [p for p in periods if services.period_key(p) < selected_key]
        prev_period = prev_periods[-1] if prev_periods else None
        prev = g[g.quarter == prev_period].copy() if prev_period else pd.DataFrame(columns=g.columns)

        weights = pd.to_numeric(current["weight_pct"], errors="coerce").fillna(0).clip(lower=0)
        current = current.assign(weight_pct=weights)
        top10 = float(current.nlargest(10, "weight_pct")["weight_pct"].sum()) if not current.empty else None
        top5 = float(current.nlargest(5, "weight_pct")["weight_pct"].sum()) if not current.empty else None
        turnover = None
        retention = None
        new_positions = 0
        exits = 0
        comparison_meta=None
        if not prev.empty:
            prev_cmp,current_cmp,comparison_meta=disclosure.comparable_pair(prev,current,prev_period,selected)
            a = prev_cmp[["stock_code", "weight_pct"]].rename(columns={"weight_pct": "old"})
            b = current_cmp[["stock_code", "weight_pct"]].rename(columns={"weight_pct": "new"})
            m = a.merge(b, on="stock_code", how="outer").fillna(0)
            turnover = float((m["new"] - m["old"]).abs().sum() / 2)
            cur_set = set(current_cmp.stock_code.astype(str))
            prev_set = set(prev_cmp.stock_code.astype(str))
            union = cur_set | prev_set
            retention = len(cur_set & prev_set) / len(union) * 100 if union else None
            new_positions = len(cur_set - prev_set)
            exits = len(prev_set - cur_set)

        sector_dist, sector_cov = _sector_distribution(current)
        if sector_dist:
            top_sector, top_sector_weight = max(sector_dist.items(), key=lambda x: x[1])
        else:
            top_sector, top_sector_weight = "未分类", None

        drift = _drift_components(current, prev, refs, mode, turnover)
        style = drift.pop("style", None) or advanced._snapshot_style(current, selected, refs, mode) or {}
        first = current.iloc[0]
        rows.append(
            {
                "master_id": str(mid),
                "fund_code": str(first.get("representative_code") or first.get("fund_code") or ""),
                "fund_name": str(first.get("master_name") or ""),
                "fund_type": str(first.get("fund_type") or ""),
                "period": selected,
                "prev_period": prev_period,
                "history_periods": len(periods),
                "history_start": periods[0] if periods else None,
                "holdings_count": int(current.stock_code.nunique()),
                "top5_concentration": round(top5, 2) if top5 is not None else None,
                "top10_concentration": round(top10, 2) if top10 is not None else None,
                "turnover_pct": round(turnover, 2) if turnover is not None else None,
                "retention_pct": round(retention, 2) if retention is not None else None,
                "comparison_basis": (comparison_meta or {}).get("basis"),
                "comparison_note": (comparison_meta or {}).get("note"),
                "new_positions": int(new_positions),
                "exits": int(exits),
                "top_sector": top_sector,
                "top_sector_weight": round(float(top_sector_weight), 2) if top_sector_weight is not None else None,
                "sector_coverage_pct": sector_cov,
                "size_score": style.get("size_score"),
                "value_growth_score": style.get("value_growth_score"),
                "style_data_coverage": style.get("style_data_coverage"),
                "sector_concentration": style.get("sector_concentration"),
                **drift,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return {"periods": [x["quarter"] for x in period_counts], "selected_period": selected, "period_coverage": period_counts, "rows": [], "thresholds": {}, "view_counts": {}}

    thresholds = {
        "turnover_high": _quantile(df, "turnover_pct", 0.80),
        "turnover_low": _quantile(df, "turnover_pct", 0.20),
        "concentration_high": _quantile(df, "top10_concentration", 0.80),
        "concentration_low": _quantile(df, "top10_concentration", 0.20),
        "drift_high": _quantile(df, "drift_score", 0.80),
        "retention_high": _quantile(df, "retention_pct", 0.80),
    }

    def tags_for(r):
        tags = []
        if thresholds["drift_high"] is not None and pd.notna(r.get("drift_score")) and float(r["drift_score"]) >= thresholds["drift_high"]:
            tags.append("风格漂移")
        if thresholds["turnover_high"] is not None and pd.notna(r.get("turnover_pct")) and float(r["turnover_pct"]) >= thresholds["turnover_high"]:
            tags.append("高换手")
        if thresholds["concentration_high"] is not None and pd.notna(r.get("top10_concentration")) and float(r["top10_concentration"]) >= thresholds["concentration_high"]:
            tags.append("高集中")
        if (
            thresholds["turnover_low"] is not None
            and thresholds["retention_high"] is not None
            and pd.notna(r.get("turnover_pct"))
            and pd.notna(r.get("retention_pct"))
            and float(r["turnover_pct"]) <= thresholds["turnover_low"]
            and float(r["retention_pct"]) >= thresholds["retention_high"]
            and int(r.get("history_periods") or 0) >= 3
        ):
            tags.append("稳定持有")
        if thresholds["concentration_low"] is not None and pd.notna(r.get("top10_concentration")) and float(r["top10_concentration"]) <= thresholds["concentration_low"]:
            tags.append("分散持仓")
        return tags

    df["tags"] = df.apply(tags_for, axis=1)
    counter = Counter(tag for tags in df["tags"] for tag in tags)
    df["_sort"] = pd.to_numeric(df["drift_score"], errors="coerce").fillna(-1)
    df = df.sort_values(["_sort", "turnover_pct", "top10_concentration"], ascending=[False, False, False]).drop(columns="_sort")
    return services.clean_payload(
        {
            "periods": [x["quarter"] for x in period_counts],
            "selected_period": selected,
            "period_coverage": period_counts,
            "rows": df.to_dict("records"),
            "thresholds": thresholds,
            "view_counts": dict(counter),
        }
    )


def _security_period_stats(h, period, cohort=None):
    x = h[h.quarter == period].copy()
    if cohort is not None:
        x=x[x.master_id.astype(str).isin(set(map(str,cohort)))]
    if x.empty:
        return pd.DataFrame(columns=["stock_code", "stock_name", "sector", "breadth", "avg_weight", "median_weight", "total_weight", "max_weight"]), {}
    stats = (
        x.groupby(["stock_code", "stock_name", "sector"], as_index=False)
        .agg(breadth=("master_id", "nunique"),avg_weight=("weight_pct", "mean"),median_weight=("weight_pct", "median"),total_weight=("weight_pct", "sum"),max_weight=("weight_pct", "max"))
    )
    holders = {str(code): set(g.master_id.astype(str)) for code, g in x.groupby("stock_code")}
    return stats, holders


def security_explorer(mode="demo", period=None):
    if mode=="local":
        selected,period_counts=_select_local_period(period);periods=[x["quarter"] for x in period_counts]
        if not selected:return {"periods":periods,"selected_period":selected,"rows":[],"state_counts":{},"thresholds":{},"data_context":{}}
        idx0=periods.index(selected) if selected in periods else -1
        need=[periods[j] for j in range(max(0,idx0-5),idx0+1)] if idx0>=0 else [selected]
        h=_canonical_snapshot_local(need)
    else:
        h = _canonical_holdings(mode)
        selected, period_counts = _select_period(h, period)
        periods = [x["quarter"] for x in period_counts]
    if h.empty or not selected:
        return {"periods": periods, "selected_period": selected, "rows": [], "state_counts": {}, "thresholds": {},"data_context":{}}
    h=_top10_by_master_period(h)
    idx = periods.index(selected)
    prev = periods[idx - 1] if idx > 0 else None
    prev2 = periods[idx - 2] if idx > 1 else None
    cur_universe=set(h[h.quarter==selected].master_id.astype(str))
    prev_universe=set(h[h.quarter==prev].master_id.astype(str)) if prev else set()
    pair_cohort=(cur_universe&prev_universe) if prev else cur_universe
    triple_cohort=set()
    if prev2 and prev:
        p2u=set(h[h.quarter==prev2].master_id.astype(str));triple_cohort=cur_universe&prev_universe&p2u

    cur_stats, cur_sets = _security_period_stats(h, selected, pair_cohort)
    prev_stats, prev_sets = _security_period_stats(h, prev, pair_cohort) if prev else (pd.DataFrame(), {})
    # Acceleration uses the same three-period cohort.
    accel_map={}
    if triple_cohort:
        s0,_=_security_period_stats(h,prev2,triple_cohort);s1,_=_security_period_stats(h,prev,triple_cohort);s2,_=_security_period_stats(h,selected,triple_cohort)
        def bm(df):return {str(r.stock_code):float(r.breadth or 0) for _,r in df.iterrows()}
        a0,a1,a2=bm(s0),bm(s1),bm(s2)
        for c in set(a0)|set(a1)|set(a2):accel_map[c]=(a2.get(c,0)-a1.get(c,0))-(a1.get(c,0)-a0.get(c,0))

    cur = cur_stats.rename(columns={"stock_name": "name_cur", "sector": "sector_cur", "breadth": "breadth_cur"})
    prv = prev_stats[["stock_code", "stock_name", "sector", "breadth"]].rename(columns={"stock_name": "name_prev", "sector": "sector_prev", "breadth": "breadth_prev"}) if not prev_stats.empty else pd.DataFrame(columns=["stock_code", "name_prev", "sector_prev", "breadth_prev"])
    m = cur.merge(prv, on="stock_code", how="outer")
    if m.empty:return {"periods":periods,"selected_period":selected,"previous_period":prev,"rows":[],"state_counts":{},"thresholds":{},"data_context":{}}
    m["stock_name"] = m.get("name_cur").fillna(m.get("name_prev"));m["sector"] = m.get("sector_cur").fillna(m.get("sector_prev")).fillna("未分类")
    for col in ["breadth_cur", "breadth_prev", "avg_weight", "median_weight", "total_weight", "max_weight"]:
        if col not in m:m[col]=np.nan
    m["breadth_cur"]=pd.to_numeric(m["breadth_cur"],errors="coerce").fillna(0);m["breadth_prev"]=pd.to_numeric(m["breadth_prev"],errors="coerce").fillna(0);m["breadth_delta"]=m["breadth_cur"]-m["breadth_prev"]
    den=max(1,len(pair_cohort));m["coverage_rate_pct"]=m["breadth_cur"]/den*100;m["previous_coverage_rate_pct"]=m["breadth_prev"]/den*100;m["coverage_delta_pp"]=m["coverage_rate_pct"]-m["previous_coverage_rate_pct"]
    m["breadth_acceleration"]=m.stock_code.astype(str).map(accel_map) if accel_map else np.nan

    entrants=[];exits=[];new_ratio=[];exit_ratio=[];persistence=[]
    recent_periods=periods[max(0,idx-5):idx+1];presence={p:set(h[h.quarter==p].stock_code.astype(str)) for p in recent_periods}
    for code in m.stock_code.astype(str):
        cset=cur_sets.get(code,set());pset=prev_sets.get(code,set());en=len(cset-pset);ex=len(pset-cset);entrants.append(en);exits.append(ex);new_ratio.append(en/max(1,len(cset))*100 if cset else 0);exit_ratio.append(ex/max(1,len(pset))*100 if pset else 0);persistence.append(sum(1 for p in recent_periods if code in presence.get(p,set())))
    m["entrants"]=entrants;m["exits"]=exits;m["new_ratio"]=new_ratio;m["exit_ratio"]=exit_ratio;m["persistence_periods"]=persistence
    active=m[m["breadth_cur"]>0].copy();thresholds={"breadth_high":_quantile(active,"breadth_cur",.85,0),"coverage_high":_quantile(active,"coverage_rate_pct",.75,0),"delta_high":_quantile(active,"coverage_delta_pp",.80,0),"delta_low":_quantile(active,"coverage_delta_pp",.20,0),"conviction_high":_quantile(active,"avg_weight",.80,0),"new_ratio_high":_quantile(active,"new_ratio",.75,0)}
    def level_for(r):
        rate=float(r.get("coverage_rate_pct") or 0);hi=float(thresholds.get("coverage_high") or 0)
        return "高" if hi>0 and rate>=hi else "中" if rate>=max(.01,hi*.4) else "低"
    def trend_for(r):
        d=float(r.get("coverage_delta_pp") or 0);bp=float(r.get("breadth_prev") or 0);bc=float(r.get("breadth_cur") or 0);lvl=level_for(r)
        if bc==0 and bp>0:return "退出观察"
        if bp<=0<bc:return "新形成"
        if d>0 and pd.notna(r.get("breadth_acceleration")) and float(r.get("breadth_acceleration") or 0)>0:return "持续增强"
        if d>0:return "增强"
        if d<0 and lvl=="高":return "退潮"
        if d<0:return "弱化"
        return "稳定"
    m["consensus_level"]=m.apply(level_for,axis=1);m["consensus_trend"]=m.apply(trend_for,axis=1)
    # Backward-compatible state labels for existing Explorer filters.
    def legacy(r):
        t=r["consensus_trend"];lvl=r["consensus_level"]
        if t=="退出观察":return "退出观察"
        if t=="新形成":return "新共识"
        if t=="持续增强":return "持续增强"
        if t=="退潮" and lvl=="高":return "高位退潮"
        if t=="弱化":return "共识减弱"
        if lvl=="高":return "高共识"
        return "稳定"
    m["state"]=m.apply(legacy,axis=1);counts=m["state"].value_counts().to_dict()
    for c in ["avg_weight","median_weight","total_weight","max_weight","new_ratio","exit_ratio","coverage_rate_pct","previous_coverage_rate_pct","coverage_delta_pp","breadth_acceleration"]:m[c]=pd.to_numeric(m[c],errors="coerce").round(2)
    m=m.sort_values(["coverage_delta_pp","coverage_rate_pct","avg_weight"],ascending=[False,False,False])
    keep=["stock_code","stock_name","sector","breadth_cur","breadth_prev","breadth_delta","coverage_rate_pct","previous_coverage_rate_pct","coverage_delta_pp","breadth_acceleration","entrants","exits","new_ratio","exit_ratio","avg_weight","median_weight","total_weight","max_weight","persistence_periods","consensus_level","consensus_trend","state"]
    updated=str(h.fetched_at.dropna().max()) if "fetched_at" in h.columns and not h.fetched_at.dropna().empty else None
    return services.clean_payload({"periods":periods,"selected_period":selected,"previous_period":prev,"rows":m[keep].to_dict("records"),"state_counts":counts,"thresholds":thresholds,"data_context":{"basis":"top10_comparable","basis_label":"Top 10 Comparable","sample_funds":len(pair_cohort),"selected_universe_funds":len(cur_universe),"previous_universe_funds":len(prev_universe) if prev else None,"updated_at":updated,"note":"证券覆盖变化仅使用两期均有有效披露的基金主体，并统一按前十大持仓比较。"}})


def security_detail(code, mode="demo", period=None):
    code=str(code)
    if mode=="local":
        _,counts=_select_local_period(period);all_periods=[x["quarter"] for x in counts]
        selected=services.normalize_period(period) if period else (all_periods[-1] if all_periods else None)
        if selected not in all_periods:selected=all_periods[-1] if all_periods else None
        idx=all_periods.index(selected) if selected in all_periods else -1;hist_periods=all_periods[max(0,idx-11):idx+1] if idx>=0 else []
        h=_canonical_snapshot_local(hist_periods)
    else:
        raw=_canonical_holdings(mode);all_periods=services.sort_periods(raw.quarter.tolist()) if not raw.empty else []
        selected=services.normalize_period(period) if period else (all_periods[-1] if all_periods else None)
        if selected not in all_periods:selected=all_periods[-1] if all_periods else None
        idx=all_periods.index(selected) if selected in all_periods else -1;hist_periods=all_periods[max(0,idx-11):idx+1] if idx>=0 else [];h=raw[raw.quarter.isin(hist_periods)].copy()
    if h.empty or not selected:return None
    h=_top10_by_master_period(h);sh=h[h.stock_code.astype(str)==code].copy()
    if sh.empty:return None
    idx=hist_periods.index(selected) if selected in hist_periods else -1;prev=hist_periods[idx-1] if idx>0 else None
    selected_universe=set(h[h.quarter==selected].master_id.astype(str));prev_universe=set(h[h.quarter==prev].master_id.astype(str)) if prev else set();pair_cohort=(selected_universe&prev_universe) if prev else selected_universe
    history=[]
    for p in hist_periods:
        p_universe=set(h[h.quarter==p].master_id.astype(str));cohort=selected_universe&p_universe if p!=selected else selected_universe;den=len(cohort);x=sh[(sh.quarter==p)&sh.master_id.astype(str).isin(cohort)]
        history.append({"period":p,"fund_count":int(x.master_id.nunique()) if not x.empty else 0,"cohort_size":den,"coverage_rate_pct":round((x.master_id.nunique()/max(1,den))*100,2) if den else None,"avg_weight":round(float(x.weight_pct.mean()),2) if not x.empty else None,"total_weight":round(float(x.weight_pct.sum()),2) if not x.empty else 0})
    cur=sh[(sh.quarter==selected)&sh.master_id.astype(str).isin(pair_cohort)].copy();prv=sh[(sh.quarter==prev)&sh.master_id.astype(str).isin(pair_cohort)].copy() if prev else sh.iloc[0:0].copy()
    cur_idx={str(r.master_id):r for _,r in cur.iterrows()};prev_idx={str(r.master_id):r for _,r in prv.iterrows()};meta=h[h.quarter.isin([p for p in [prev,selected] if p])].sort_values("quarter").drop_duplicates("master_id",keep="last").set_index(h[h.quarter.isin([p for p in [prev,selected] if p])].sort_values("quarter").drop_duplicates("master_id",keep="last").master_id.astype(str),drop=False) if pair_cohort else pd.DataFrame()
    changes=[]
    for mid in sorted(pair_cohort):
        a=prev_idx.get(mid);b=cur_idx.get(mid)
        if a is None and b is None:continue
        old=float(a.weight_pct) if a is not None and pd.notna(a.weight_pct) else None;new=float(b.weight_pct) if b is not None and pd.notna(b.weight_pct) else None;delta=(new or 0)-(old or 0);base=b if b is not None else a
        if base is None and not meta.empty and mid in meta.index:base=meta.loc[mid]
        status="新进入披露" if a is None else "退出披露" if b is None else "权重上升" if delta>.05 else "权重下降" if delta<-.05 else "基本稳定"
        changes.append({"fund_code":str(base.representative_code),"fund_name":str(base.master_name),"fund_type":str(base.fund_type),"weight_old":round(old,2) if old is not None else None,"weight_new":round(new,2) if new is not None else None,"delta":round(delta,2),"status":status})
    changes=sorted(changes,key=lambda x:abs(float(x["delta"])),reverse=True);latest=sh.sort_values("quarter",key=lambda q:q.map(services.period_key)).iloc[-1];updated=str(h.fetched_at.dropna().max()) if "fetched_at" in h.columns and not h.fetched_at.dropna().empty else None
    return services.clean_payload({"security":{"stock_code":code,"stock_name":latest.stock_name,"sector":latest.sector},"periods":hist_periods,"selected_period":selected,"previous_period":prev,"history":history,"fund_changes":changes,"current_holders":[x for x in changes if x["weight_new"] is not None][:30],"entrants":[x for x in changes if x["status"]=="新进入披露"],"exits":[x for x in changes if x["status"]=="退出披露"],"data_context":{"basis":"top10_comparable","basis_label":"Top 10 Comparable","sample_funds":len(pair_cohort),"selected_universe_funds":len(selected_universe),"previous_universe_funds":len(prev_universe) if prev else None,"updated_at":updated,"note":"基金进入/退出仅在两期都有有效披露的基金主体中识别。"}})


def _previous_period(period):
    p=services.normalize_period(period)
    if len(p)!=6 or p[4]!='Q':return None
    try:y=int(p[:4]);q=int(p[-1])
    except Exception:return None
    return f"{y-1}Q4" if q==1 else f"{y}Q{q-1}"


def _behavior_snapshot_local(periods):
    """Canonical Fund-Master holdings for a small set of periods.

    V9.0.4 uses a two-stage query: first select one best share code per Fund
    Master/period, then fetch holdings only for those codes. This avoids loading
    every A/C/E or fee share into pandas and discarding duplicates afterwards.
    """
    periods=services.sort_periods([services.normalize_period(x) for x in periods if x])
    if not periods:return pd.DataFrame()
    def build():
        fund_master.ensure_master();frames=[]
        for period in periods:
            availability=db.read_sql("""
                SELECT m.master_id,m.master_name,m.fund_type,m.representative_code,
                       h.fund_code,MAX(mm.is_representative) AS is_representative,
                       COUNT(DISTINCT h.stock_code) AS row_count
                FROM fund_holdings h
                JOIN fund_master_members mm ON mm.fund_code=h.fund_code
                JOIN fund_master m ON m.master_id=mm.master_id
                WHERE m.eligible_equity=1 AND h.quarter=?
                GROUP BY m.master_id,h.fund_code
            """,(period,))
            if availability.empty:continue
            availability=availability.sort_values(['master_id','is_representative','row_count','fund_code'],ascending=[True,False,False,True])
            chosen=availability.groupby('master_id',as_index=False).head(1).copy()
            codes=chosen.fund_code.astype(str).tolist();meta=chosen.set_index('fund_code')[['master_id','master_name','fund_type','representative_code','is_representative']].to_dict('index')
            for i in range(0,len(codes),700):
                chunk=codes[i:i+700];marks=','.join(['?']*len(chunk))
                part=db.read_sql(f"""SELECT fund_code,quarter,stock_code,stock_name,weight_pct,shares
                    FROM fund_holdings WHERE quarter=? AND fund_code IN ({marks})""",tuple([period]+chunk))
                if part.empty:continue
                for col in ['master_id','master_name','fund_type','representative_code','is_representative']:
                    part[col]=part.fund_code.astype(str).map(lambda c:meta.get(c,{}).get(col))
                frames.append(part)
        if not frames:return pd.DataFrame()
        raw=pd.concat(frames,ignore_index=True);raw['quarter']=raw['quarter'].map(services.normalize_period)
        raw['weight_pct']=pd.to_numeric(raw['weight_pct'],errors='coerce').fillna(0).clip(lower=0);raw['shares']=pd.to_numeric(raw['shares'],errors='coerce')
        return raw.drop_duplicates(['master_id','quarter','stock_code'],keep='first')
    return _cached(('behavior_snapshot_local_v904',db.data_revision(),tuple(periods)),build,240.0).copy()


def _weighted_group(frame,value_col):
    if frame.empty or value_col not in frame.columns:return pd.Series(dtype=float)
    x=frame[['master_id','weight_pct',value_col]].copy()
    x['weight_pct']=pd.to_numeric(x['weight_pct'],errors='coerce').fillna(0).clip(lower=0)
    x[value_col]=pd.to_numeric(x[value_col],errors='coerce')
    x=x[x[value_col].notna() & (x.weight_pct>0)]
    if x.empty:return pd.Series(dtype=float)
    x['_num']=x[value_col]*x.weight_pct
    num=x.groupby('master_id')['_num'].sum();den=x.groupby('master_id').weight_pct.sum().replace(0,np.nan)
    return num/den


def _peer_cross_section_local(period,prev_period=None):
    """Fast period-level peer metrics used only by 同类定位.

    The calculation is vectorized across the selected and previous quarter and
    deliberately avoids the full Research Explorer pipeline.  It keeps the
    peer tab usable even when fundscope.db contains decades of disclosures.
    """
    selected=services.normalize_period(period)
    prev=services.normalize_period(prev_period) if prev_period else _previous_period(selected)
    def build():
        h=_behavior_snapshot_local([prev,selected])
        cur=h[h.quarter==selected].copy() if not h.empty else pd.DataFrame()
        prv=h[h.quarter==prev].copy() if prev and not h.empty else pd.DataFrame()
        if cur.empty:return []
        # Peer behavior must remain comparable across Q1/Q3 Top 10 and Q2/Q4 full disclosures.
        # This fast path therefore normalizes both snapshots to each Fund Master's Top 10.
        cur=_top10_by_master_period(cur)
        if not prv.empty:prv=_top10_by_master_period(prv)
        cur=cur.sort_values(['master_id','weight_pct'],ascending=[True,False])
        cur['_rank']=cur.groupby('master_id').cumcount()+1
        meta=(cur.groupby('master_id',as_index=False).first()[['master_id','master_name','fund_type','representative_code']])
        top10=(cur[cur._rank<=10].groupby('master_id').weight_pct.sum()).rename('top10_concentration')
        count=(cur.groupby('master_id').stock_code.nunique()).rename('holdings_count')
        frame=meta.set_index('master_id').join([top10,count])
        if not prv.empty:
            a=prv[['master_id','stock_code','weight_pct']].rename(columns={'weight_pct':'old'})
            b=cur[['master_id','stock_code','weight_pct']].rename(columns={'weight_pct':'new'})
            m=a.merge(b,on=['master_id','stock_code'],how='outer')
            m['old']=pd.to_numeric(m.old,errors='coerce').fillna(0);m['new']=pd.to_numeric(m.new,errors='coerce').fillna(0)
            m['_abs']=(m['new']-m['old']).abs();m['_common']=((m.old>0)&(m.new>0)).astype(int);m['_union']=((m.old>0)|(m.new>0)).astype(int)
            turnover=(m.groupby('master_id')._abs.sum()/2).rename('turnover_pct')
            common=m.groupby('master_id')._common.sum();union=m.groupby('master_id')._union.sum().replace(0,np.nan)
            retention=(common/union*100).rename('retention_pct')
            frame=frame.join([turnover,retention])
        else:
            frame['turnover_pct']=np.nan;frame['retention_pct']=np.nan

        refs=_cached(('peer_style_refs',),lambda:advanced._style_reference('local'),600.0)
        codes=cur.stock_code.astype(str)
        cur['_size_item']=codes.map(refs.get('size',{}))
        growth_map={}
        for c in codes.drop_duplicates().tolist():
            comps=[]
            for k,w in [('pb',.30),('pe',.20),('rev',.25),('profit',.25)]:
                v=refs.get(k,{}).get(c)
                if v is not None:comps.append((v,w))
            if comps:growth_map[c]=sum(v*w for v,w in comps)/sum(w for _,w in comps)
        cur['_growth_item']=codes.map(growth_map)
        size_cur=_weighted_group(cur,'_size_item').rename('size_score')
        growth_cur=_weighted_group(cur,'_growth_item').rename('value_growth_score')
        frame=frame.join([size_cur,growth_cur])

        # Drift uses the same available factor/concentration/structural components as
        # the fund style model. Sector terms are omitted here to keep peer discovery fast.
        if not prv.empty:
            pcodes=prv.stock_code.astype(str)
            prv['_size_item']=pcodes.map(refs.get('size',{}))
            pgrowth={}
            for c in pcodes.drop_duplicates().tolist():
                comps=[]
                for k,w in [('pb',.30),('pe',.20),('rev',.25),('profit',.25)]:
                    v=refs.get(k,{}).get(c)
                    if v is not None:comps.append((v,w))
                if comps:pgrowth[c]=sum(v*w for v,w in comps)/sum(w for _,w in comps)
            prv['_growth_item']=pcodes.map(pgrowth)
            size_prev=_weighted_group(prv,'_size_item');growth_prev=_weighted_group(prv,'_growth_item')
            p2=prv.sort_values(['master_id','weight_pct'],ascending=[True,False]);p2['_rank']=p2.groupby('master_id').cumcount()+1
            top10_prev=p2[p2._rank<=10].groupby('master_id').weight_pct.sum()
            drift=[]
            for mid,r in frame.iterrows():
                parts=[]
                if pd.notna(r.get('size_score')) and mid in size_prev and pd.notna(size_prev.get(mid)):parts.append((.35,abs(float(r.size_score)-float(size_prev[mid]))/100))
                if pd.notna(r.get('value_growth_score')) and mid in growth_prev and pd.notna(growth_prev.get(mid)):parts.append((.35,abs(float(r.value_growth_score)-float(growth_prev[mid]))/100))
                if mid in top10_prev and pd.notna(top10_prev.get(mid)):parts.append((.20,abs(float(r.top10_concentration)-float(top10_prev[mid]))/60))
                if pd.notna(r.get('turnover_pct')):parts.append((.15,min(1,float(r.turnover_pct)/25)))
                score=100*sum(w*v for w,v in parts)/sum(w for w,_ in parts) if parts else None
                drift.append(round(score,2) if score is not None else None)
            frame['drift_score']=drift
        else:frame['drift_score']=np.nan
        frame=frame.reset_index()
        frame['fund_code']=frame.representative_code.astype(str);frame['fund_name']=frame.master_name.astype(str);frame['period']=selected;frame['prev_period']=prev;frame['comparison_basis']='top10_comparable'
        for c in ['top10_concentration','turnover_pct','retention_pct','size_score','value_growth_score','drift_score']:
            if c in frame.columns:frame[c]=pd.to_numeric(frame[c],errors='coerce').round(2)
        return services.clean_payload(frame[['master_id','fund_code','fund_name','fund_type','period','prev_period','holdings_count','top10_concentration','turnover_pct','retention_pct','size_score','value_growth_score','drift_score','comparison_basis']].to_dict('records'))
    return _cached(('peer_cross_section_local',selected,prev),build,180.0)


def _candidate_peer_snapshot_local(selected,target_codes,target_mid,max_candidates=500):
    """Fetch only canonical share codes for funds overlapping target holdings."""
    target_codes=[str(x) for x in target_codes if str(x)]
    if not target_codes:return pd.DataFrame()
    fund_master.ensure_master();scores={}
    for i in range(0,len(target_codes),700):
        chunk=target_codes[i:i+700];marks=','.join(['?']*len(chunk))
        q=db.read_sql(f"""
            SELECT m.master_id,COUNT(DISTINCT h.stock_code) AS common_count
            FROM fund_holdings h
            JOIN fund_master_members mm ON mm.fund_code=h.fund_code
            JOIN fund_master m ON m.master_id=mm.master_id
            WHERE m.eligible_equity=1 AND h.quarter=? AND h.stock_code IN ({marks})
            GROUP BY m.master_id
        """,tuple([selected]+chunk))
        for _,r in q.iterrows():scores[str(r.master_id)]=max(scores.get(str(r.master_id),0),int(r.common_count or 0))
    ids=[mid for mid,_ in sorted(scores.items(),key=lambda x:x[1],reverse=True) if mid!=str(target_mid)][:max_candidates]
    if not ids:return pd.DataFrame()

    availability_parts=[]
    for i in range(0,len(ids),600):
        chunk=ids[i:i+600];marks=','.join(['?']*len(chunk))
        availability_parts.append(db.read_sql(f"""
            SELECT m.master_id,m.master_name,m.fund_type,m.representative_code,h.fund_code,
                   MAX(mm.is_representative) AS is_representative,COUNT(DISTINCT h.stock_code) AS row_count
            FROM fund_holdings h
            JOIN fund_master_members mm ON mm.fund_code=h.fund_code
            JOIN fund_master m ON m.master_id=mm.master_id
            WHERE h.quarter=? AND m.master_id IN ({marks})
            GROUP BY m.master_id,h.fund_code
        """,tuple([selected]+chunk)))
    availability=pd.concat([x for x in availability_parts if not x.empty],ignore_index=True) if any(not x.empty for x in availability_parts) else pd.DataFrame()
    if availability.empty:return pd.DataFrame()
    availability=availability.sort_values(['master_id','is_representative','row_count','fund_code'],ascending=[True,False,False,True])
    chosen=availability.groupby('master_id',as_index=False).head(1).copy();codes=chosen.fund_code.astype(str).tolist()
    meta=chosen.set_index('fund_code')[['master_id','master_name','fund_type','representative_code']].to_dict('index');parts=[]
    for i in range(0,len(codes),700):
        chunk=codes[i:i+700];marks=','.join(['?']*len(chunk))
        part=db.read_sql(f"SELECT fund_code,stock_code,stock_name,weight_pct FROM fund_holdings WHERE quarter=? AND fund_code IN ({marks})",tuple([selected]+chunk))
        if part.empty:continue
        for col in ['master_id','master_name','fund_type','representative_code']:
            part[col]=part.fund_code.astype(str).map(lambda c:meta.get(c,{}).get(col))
        parts.append(part)
    raw=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
    if raw.empty:return raw
    raw['weight_pct']=pd.to_numeric(raw.weight_pct,errors='coerce').fillna(0).clip(lower=0)
    return raw.drop_duplicates(['master_id','stock_code'],keep='first')


def fund_peers(code, mode="demo", quarter=None, limit=15):
    if mode=="local":
        resolved=fund_master.resolve(str(code));mid=str(resolved.get("master_id") or "")
        periods=services.fund_periods('local',str(code))
        selected=services.normalize_period(quarter) if quarter else (periods[-1] if periods else None)
        if selected not in periods:selected=periods[-1] if periods else selected
        if not mid or not selected:return {"fund":None,"period":selected,"peers":[]}
        target=services.holdings_period('local',str(code),selected,enriched=False).copy()
        if target.empty:return {"fund":None,"period":selected,"peers":[]}
        target['weight_pct']=pd.to_numeric(target.weight_pct,errors='coerce').fillna(0).clip(lower=0)
        tw={str(r.stock_code):float(r.weight_pct or 0) for _,r in target.iterrows() if pd.notna(r.weight_pct)};tset=set(tw);tnorm=math.sqrt(sum(v*v for v in tw.values()))
        period_df=_candidate_peer_snapshot_local(selected,tset,mid)
        peers=[];target_names=dict(zip(target.stock_code.astype(str),target.stock_name.astype(str)))
        if not period_df.empty:
            for cid,g in period_df.groupby('master_id'):
                cw=dict(zip(g.stock_code.astype(str),pd.to_numeric(g.weight_pct,errors='coerce').fillna(0).astype(float)));cset=set(cw);common=tset&cset
                if not common:continue
                cnorm=math.sqrt(sum(v*v for v in cw.values()));cosine=sum(tw[x]*cw[x] for x in common)/(tnorm*cnorm)*100 if tnorm and cnorm else 0;overlap=sum(min(tw[x],cw[x]) for x in common);union=tset|cset;jaccard=len(common)/len(union)*100 if union else 0
                names=sorted(common,key=lambda x:min(tw.get(x,0),cw.get(x,0)),reverse=True);first=g.iloc[0]
                peers.append({'fund_code':str(first.representative_code),'fund_name':str(first.master_name),'fund_type':str(first.fund_type),'similarity_pct':round(float(cosine),2),'weighted_overlap_pct':round(float(overlap),2),'jaccard_pct':round(float(jaccard),2),'common_count':len(common),'common_holdings':[target_names.get(x,x) for x in names[:4]],'top10_concentration':round(float(g.nlargest(10,'weight_pct').weight_pct.sum()),2),'low_overlap':len(common)<2})
        strong=[x for x in peers if x['common_count']>=2]
        chosen=strong if strong else peers
        chosen=sorted(chosen,key=lambda x:(x['similarity_pct'],x['weighted_overlap_pct']),reverse=True)[:max(1,min(int(limit),30))]
        return services.clean_payload({'fund':{'fund_code':str(resolved.get('representative_code') or code),'fund_name':str(resolved.get('master_name') or ''),'fund_type':str(resolved.get('fund_type') or '')},'period':selected,'peers':chosen,'method':'披露持仓权重余弦相似度 + 权重重合率；优先要求至少 2 只共同证券，样本不足时降级展示单一共同持仓并明确标记。','fallback_overlap':bool(chosen and not strong)})
    h = _canonical_holdings(mode)
    if h.empty:
        return {"fund": None, "period": None, "peers": []}
    if mode == "local":
        resolved = fund_master.resolve(str(code))
        mid = str(resolved.get("master_id") or "")
        if not mid:
            return {"fund": None, "period": None, "peers": []}
    else:
        mid = str(code)
    target_all = h[h.master_id.astype(str) == mid].copy()
    if target_all.empty:
        return {"fund": None, "period": None, "peers": []}
    periods = services.sort_periods(target_all.quarter.tolist())
    selected = services.normalize_period(quarter) if quarter else periods[-1]
    if selected not in periods:
        selected = periods[-1]
    target = target_all[target_all.quarter == selected].copy()
    period_df = h[h.quarter == selected].copy()
    if target.empty or period_df.empty:
        return {"fund": None, "period": selected, "peers": []}

    tw = {str(r.stock_code): float(r.weight_pct or 0) for _, r in target.iterrows() if pd.notna(r.weight_pct)}
    tnorm = math.sqrt(sum(v * v for v in tw.values()))
    tset = set(tw)
    candidate_ids = set(period_df[period_df.stock_code.astype(str).isin(tset)].master_id.astype(str)) - {mid}
    peers = []
    for cid in candidate_ids:
        g = period_df[period_df.master_id.astype(str) == cid]
        cw = {str(r.stock_code): float(r.weight_pct or 0) for _, r in g.iterrows() if pd.notna(r.weight_pct)}
        cset = set(cw)
        common = tset & cset
        if len(common) < 2:
            continue
        cnorm = math.sqrt(sum(v * v for v in cw.values()))
        cosine = sum(tw[s] * cw[s] for s in common) / (tnorm * cnorm) * 100 if tnorm and cnorm else 0
        weighted_overlap = sum(min(tw[s], cw[s]) for s in common)
        union = tset | cset
        jaccard = len(common) / len(union) * 100 if union else 0
        common_names = (
            target[target.stock_code.astype(str).isin(common)]
            .assign(_common_weight=lambda x: x.stock_code.astype(str).map(lambda s: min(tw.get(s, 0), cw.get(s, 0))))
            .sort_values("_common_weight", ascending=False)
            .stock_name.astype(str)
            .head(4)
            .tolist()
        )
        first = g.iloc[0]
        peers.append(
            {
                "fund_code": str(first.representative_code),
                "fund_name": str(first.master_name),
                "fund_type": str(first.fund_type),
                "similarity_pct": round(float(cosine), 1),
                "weighted_overlap_pct": round(float(weighted_overlap), 2),
                "jaccard_pct": round(float(jaccard), 2),
                "common_count": len(common),
                "common_holdings": common_names,
                "top10_concentration": round(float(g.nlargest(10, "weight_pct").weight_pct.sum()), 1),
            }
        )
    peers = sorted(peers, key=lambda x: (x["similarity_pct"], x["weighted_overlap_pct"]), reverse=True)[: max(1, min(int(limit), 30))]
    first = target.iloc[0]
    return services.clean_payload(
        {
            "fund": {"fund_code": str(first.representative_code), "fund_name": str(first.master_name), "fund_type": str(first.fund_type)},
            "period": selected,
            "peers": peers,
            "method": "披露持仓权重余弦相似度 + 权重重合率",
        }
    )


def fund_rank_trajectory(code, mode="demo", max_names=8, max_periods=12):
    h = services.holdings(mode, code)
    if h.empty:
        return {"periods": [], "series": []}
    periods = services.sort_periods(h.quarter.tolist())[-max(4, min(int(max_periods), 20)) :]
    hh = h[h.quarter.isin(periods)].copy()
    ranked = []
    for p in periods:
        x = disclosure.top_n(hh[hh.quarter == p].copy(),10)
        x["rank"] = np.arange(1, len(x) + 1)
        ranked.append(x[["quarter", "stock_code", "stock_name", "weight_pct", "rank"]])
    r = pd.concat(ranked, ignore_index=True) if ranked else pd.DataFrame()
    if r.empty:
        return {"periods": periods, "series": []}
    latest = r[r.quarter == periods[-1]].sort_values("rank").head(5).stock_code.astype(str).tolist()
    top10 = r[r["rank"] <= 10]
    persistence = (
        top10.groupby(["stock_code", "stock_name"], as_index=False)
        .agg(appearances=("quarter", "nunique"), avg_rank=("rank", "mean"))
        .sort_values(["appearances", "avg_rank"], ascending=[False, True])
    )
    candidates = []
    for c in latest + persistence.stock_code.astype(str).tolist():
        if c not in candidates:
            candidates.append(c)
        if len(candidates) >= max(3, min(int(max_names), 12)):
            break
    series = []
    for c in candidates:
        x = r[r.stock_code.astype(str) == c]
        name = str(x.iloc[-1].stock_name) if not x.empty else c
        point_map = {str(row.quarter): {"rank": int(row["rank"]), "weight": round(float(row.weight_pct), 2)} for _, row in x.iterrows()}
        points = [{"period": p, **point_map[p]} if p in point_map else {"period": p, "rank": None, "weight": None} for p in periods]
        series.append({"stock_code": c, "stock_name": name, "points": points})
    max_rank = int(min(20, max([p["rank"] or 0 for s in series for p in s["points"]] + [10])))
    return services.clean_payload({"periods": periods, "series": series, "max_rank": max_rank})


def fund_peer_lens(code, mode='demo', period=None, universe='all'):
    if mode=='local':
        resolved=fund_master.resolve(str(code));target_code=str(resolved.get('representative_code') or code);target_mid=str(resolved.get('master_id') or '')
        tperiods=services.fund_periods('local',str(code))
        selected=services.normalize_period(period) if period else (tperiods[-1] if tperiods else None)
        if selected not in tperiods:selected=tperiods[-1] if tperiods else selected
        tidx=tperiods.index(selected) if selected in tperiods else -1;selected_prev=tperiods[tidx-1] if tidx>0 else None
        rows=_peer_cross_section_local(selected,selected_prev) if selected else []
        data={'rows':rows,'selected_period':selected}
        target=next((r for r in rows if str(r.get('master_id'))==target_mid or str(r.get('fund_code'))==target_code),None)
    else:
        data=fund_explorer(mode,period);rows=data.get('rows') or []
        target=next((r for r in rows if str(r.get('fund_code'))==str(code)),None)
    rows=data.get('rows') or []
    if not rows:return {'fund':None,'period':data.get('selected_period'),'universe':universe,'peer_count':0,'metrics':[],'peers':[]}
    if not target:return {'fund':None,'period':data.get('selected_period'),'universe':universe,'peer_count':0,'metrics':[],'peers':[]}
    peers=[r for r in rows if r is not target]
    if universe=='type' and target.get('fund_type'):
        peers=[r for r in peers if str(r.get('fund_type') or '')==str(target.get('fund_type') or '')]
    elif universe=='style' and target.get('size_score') is not None and target.get('value_growth_score') is not None:
        ts=float(target['size_score']);tg=float(target['value_growth_score'])
        peers=[r for r in peers if r.get('size_score') is not None and r.get('value_growth_score') is not None and abs(float(r['size_score'])-ts)<=20 and abs(float(r['value_growth_score'])-tg)<=20]
    sample=peers+[target]
    definitions=[
        ('turnover_pct','调仓强度','%','越高代表季度披露权重变化越大'),
        ('top10_concentration','前十集中度','%','越高代表组合更集中'),
        ('drift_score','风格漂移','','越高代表与上一报告期的风格变化更明显'),
        ('retention_pct','持仓延续率','%','越高代表前后期持仓集合更稳定'),
        ('size_score','规模风格','','0偏小盘，100偏大盘'),
        ('value_growth_score','价值成长','','0偏价值，100偏成长'),
    ]
    metrics=[]
    for key,label,unit,help_text in definitions:
        vals=pd.to_numeric(pd.Series([r.get(key) for r in sample]),errors='coerce').dropna()
        tv=target.get(key)
        try:tv=float(tv)
        except Exception:tv=None
        if tv is None or vals.empty:continue
        pct=float((vals<=tv).mean()*100)
        metrics.append({
            'key':key,'label':label,'unit':unit,'help':help_text,'value':round(tv,2),'percentile':round(pct,2),
            'p25':round(float(vals.quantile(.25)),2),'median':round(float(vals.median()),2),'p75':round(float(vals.quantile(.75)),2),
            'min':round(float(vals.min()),2),'max':round(float(vals.max()),2),'sample_count':int(vals.shape[0]),
        })
    # Transparent nearest peers using normalized distance across available behavior/style metrics.
    distance_keys=['turnover_pct','top10_concentration','drift_score','retention_pct','size_score','value_growth_score']
    frame=pd.DataFrame(sample)
    usable=[]
    for k in distance_keys:
        s=pd.to_numeric(frame.get(k),errors='coerce') if k in frame else pd.Series(dtype=float)
        if s.notna().sum()>=2 and float(s.std(skipna=True) or 0)>1e-9:usable.append((k,float(s.mean()),float(s.std())))
    neighbor_rows=[]
    for r in peers:
        parts=[]
        for k,mu,sd in usable:
            try:a=float(target.get(k));b=float(r.get(k))
            except Exception:continue
            if math.isfinite(a) and math.isfinite(b):parts.append(((a-b)/sd)**2)
        if parts:
            neighbor_rows.append({**r,'distance':round(math.sqrt(sum(parts)/len(parts)),3),'distance_dimensions':len(parts)})
    neighbor_rows=sorted(neighbor_rows,key=lambda x:x['distance'])[:12]
    return services.clean_payload({
        'fund':target,'period':data.get('selected_period'),'universe':universe,'peer_count':len(peers),
        'metrics':metrics,'peers':neighbor_rows,
        'universes':[{'key':'all','label':'全部偏股基金'},{'key':'type','label':'同基金类型'},{'key':'style','label':'相近风格'}],
        'method':'百分位按当前报告期横截面计算；相近基金使用已展示指标标准化距离，不生成综合评分。'
    })


def manager_explorer(mode='demo', period=None):
    fund_data=fund_explorer(mode,period)
    selected=fund_data.get('selected_period');frows=fund_data.get('rows') or []
    if not selected:return {'periods':fund_data.get('periods') or [],'selected_period':selected,'rows':[],'thresholds':{},'tag_counts':{}}
    fmap={str(r.get('fund_code')):r for r in frows}
    managers=services.manager_catalog(mode)
    rows=[]
    for m in managers:
        codes=[]
        raw=str(m.get('current_fund_codes') or m.get('fund_codes') or '')
        import re as _re
        codes=_re.findall(r'[A-Za-z]?\d{5,6}',raw)
        if mode=='demo' and not codes:
            try:
                codes=demo_data.FUNDS[demo_data.FUNDS.manager_name==m.get('manager_name')].fund_code.astype(str).tolist()
            except Exception:codes=[]
        seen=set();items=[]
        for c in codes:
            if mode=='local':
                rr=fund_master.resolve(c);rc=str(rr.get('representative_code') or c);mid=str(rr.get('master_id') or rc)
                if mid in seen:continue
                seen.add(mid);item=fmap.get(rc)
            else:
                if c in seen:continue
                seen.add(c);item=fmap.get(str(c))
            if item:items.append(item)
        if not items:continue
        df=pd.DataFrame(items)
        def med(col):
            s=pd.to_numeric(df.get(col),errors='coerce').dropna() if col in df else pd.Series(dtype=float)
            return None if s.empty else round(float(s.median()),1)
        size=pd.to_numeric(df.get('size_score'),errors='coerce').dropna() if 'size_score' in df else pd.Series(dtype=float)
        growth=pd.to_numeric(df.get('value_growth_score'),errors='coerce').dropna() if 'value_growth_score' in df else pd.Series(dtype=float)
        dispersion_parts=[]
        if size.shape[0]>=2:dispersion_parts.append(float(size.std()))
        if growth.shape[0]>=2:dispersion_parts.append(float(growth.std()))
        dispersion=round(float(np.mean(dispersion_parts)),1) if dispersion_parts else None
        rows.append({
            'manager_id':m.get('manager_id'),'manager_name':m.get('manager_name'),'company':m.get('company'),
            'career_years':m.get('career_years'),'aum_yi':m.get('aum_yi'),'managed_funds':len(seen),'collected_funds':len(items),
            'median_drift':med('drift_score'),'median_turnover':med('turnover_pct'),'median_concentration':med('top10_concentration'),
            'median_retention':med('retention_pct'),'size_centroid':round(float(size.mean()),1) if not size.empty else None,
            'growth_centroid':round(float(growth.mean()),1) if not growth.empty else None,'style_dispersion':dispersion,
        })
    df=pd.DataFrame(rows)
    if df.empty:return {'periods':fund_data.get('periods') or [],'selected_period':selected,'rows':[],'thresholds':{},'tag_counts':{}}
    thresholds={
        'drift_high':_quantile(df,'median_drift',.80),
        'turnover_high':_quantile(df,'median_turnover',.80),
        'concentration_high':_quantile(df,'median_concentration',.80),
        'dispersion_low':_quantile(df,'style_dispersion',.20),
        'dispersion_high':_quantile(df,'style_dispersion',.80),
    }
    def tags(r):
        out=[]
        if pd.notna(r.get('median_drift')) and thresholds['drift_high'] is not None and float(r['median_drift'])>=thresholds['drift_high']:out.append('高漂移')
        if pd.notna(r.get('median_turnover')) and thresholds['turnover_high'] is not None and float(r['median_turnover'])>=thresholds['turnover_high']:out.append('高换手')
        if pd.notna(r.get('median_concentration')) and thresholds['concentration_high'] is not None and float(r['median_concentration'])>=thresholds['concentration_high']:out.append('高集中')
        if pd.notna(r.get('style_dispersion')) and int(r.get('collected_funds') or 0)>=2:
            if thresholds['dispersion_low'] is not None and float(r['style_dispersion'])<=thresholds['dispersion_low']:out.append('风格一致')
            elif thresholds['dispersion_high'] is not None and float(r['style_dispersion'])>=thresholds['dispersion_high']:out.append('跨产品分散')
        return out
    df['tags']=df.apply(tags,axis=1)
    counter=Counter(t for ts in df.tags for t in ts)
    df['_sort']=pd.to_numeric(df['median_drift'],errors='coerce').fillna(-1)
    df=df.sort_values(['_sort','collected_funds'],ascending=[False,False]).drop(columns='_sort')
    return services.clean_payload({'periods':fund_data.get('periods') or [],'selected_period':selected,'rows':df.to_dict('records'),'thresholds':thresholds,'tag_counts':dict(counter)})


# V9.2.1: keep expensive local cross-sections warm for normal navigation.
# These wrappers are intentionally defined after the implementations so all
# internal helpers stay unchanged while route calls benefit from longer TTLs.
_security_explorer_uncached = security_explorer
def security_explorer(mode="demo", period=None):
    if mode=="local":
        p=services.normalize_period(period) if period else "latest"
        return _cached(("security_explorer_local",p),lambda:_security_explorer_uncached(mode,period),600.0)
    return _security_explorer_uncached(mode,period)

_manager_explorer_uncached = manager_explorer
def manager_explorer(mode='demo', period=None):
    if mode=='local':
        p=services.normalize_period(period) if period else 'latest'
        return _cached(("manager_explorer_local",p),lambda:_manager_explorer_uncached(mode,period),600.0)
    return _manager_explorer_uncached(mode,period)
