"""Institutional consensus analytics with comparable fund cohorts.

This module intentionally separates market-level research semantics from generic
service plumbing.  Local consensus is derived from canonical Fund Master holdings
and uses a common fund cohort for period comparisons.  All quarter-to-quarter
security breadth calculations are normalized to the top-ten disclosed holdings so
Q1/Q3 and Q2/Q4 remain comparable.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np
import pandas as pd

from . import db, demo_data, disclosure, fund_master

logger = logging.getLogger(__name__)

_CACHE_LOCK = threading.Lock()
_RESULT_CACHE: dict[tuple, tuple[float, Any]] = {}
_SNAPSHOT_CACHE: dict[tuple, tuple[float, pd.DataFrame]] = {}
_PENDING: dict[tuple, threading.Event] = {}
_PROGRESSIVE_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fundscope-consensus")
_PROGRESSIVE_FUTURES: dict[tuple, Any] = {}


def _cached(key: tuple, builder, ttl: float = 600.0, max_items: int = 48):
    """Small in-process TTL cache with single-flight protection for heavy research reads."""
    cache_key=(str(db.DB_PATH),db.data_revision())+tuple(key)
    now=time.monotonic();owner=False
    with _CACHE_LOCK:
        hit=_RESULT_CACHE.get(cache_key)
        if hit and hit[0]>now:return hit[1]
        event=_PENDING.get(cache_key)
        if event is None:
            event=threading.Event();_PENDING[cache_key]=event;owner=True
    if not owner:
        event.wait(timeout=120)
        with _CACHE_LOCK:
            hit=_RESULT_CACHE.get(cache_key)
            if hit and hit[0]>time.monotonic():return hit[1]
        return builder()
    try:
        value=builder()
        with _CACHE_LOCK:
            if len(_RESULT_CACHE)>=max_items:
                oldest=sorted(_RESULT_CACHE.items(),key=lambda kv:kv[1][0])[:max(1,max_items//4)]
                for k,_ in oldest:_RESULT_CACHE.pop(k,None)
            _RESULT_CACHE[cache_key]=(time.monotonic()+ttl,value)
        return value
    finally:
        with _CACHE_LOCK:
            done=_PENDING.pop(cache_key,None)
            if done:done.set()



def _period_key(value: Any) -> int:
    p = disclosure.normalize_period(value)
    try:
        return int(p[:4]) * 4 + int(p[-1])
    except Exception:
        return -1


def _sort_periods(values) -> list[str]:
    return sorted({disclosure.normalize_period(x) for x in values if disclosure.normalize_period(x)}, key=_period_key)


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    return df.replace({np.nan: None, np.inf: None, -np.inf: None}).to_dict("records")


def _local_period_catalog() -> tuple[list[str], dict[str, int]]:
    # Period discovery must stay cheap. Earlier code joined the full holdings table
    # to Fund Master and COUNT DISTINCT-ed every historical quarter before the page
    # could render, which is expensive on a ~GB local database. Cohort counts for the
    # selected pair are already available from the selected snapshots below.
    q = db.read_sql("SELECT quarter FROM fund_holdings WHERE quarter IS NOT NULL GROUP BY quarter")
    if q.empty:
        return [], {}
    periods = _sort_periods(q["quarter"].tolist())
    return periods, {}


def _canonical_top10_local(periods: list[str]) -> pd.DataFrame:
    periods = _sort_periods(periods)
    if not periods:
        return pd.DataFrame()
    cache_key=("top10_snapshot",tuple(periods))
    with _CACHE_LOCK:
        hit=_SNAPSHOT_CACHE.get((str(db.DB_PATH),db.data_revision())+cache_key)
        if hit and hit[0]>time.monotonic():return hit[1].copy()
    marks = ",".join(["?"] * len(periods))
    sql = f"""
    WITH availability AS (
      SELECT mm.master_id,h.quarter,h.fund_code,
             MAX(mm.is_representative) AS is_representative,
             COUNT(DISTINCT h.stock_code) AS row_count
      FROM fund_holdings h
      JOIN fund_master_members mm ON mm.fund_code=h.fund_code
      JOIN fund_master m ON m.master_id=mm.master_id
      WHERE m.eligible_equity=1 AND h.quarter IN ({marks})
      GROUP BY mm.master_id,h.quarter,h.fund_code
    ), chosen AS (
      SELECT *,ROW_NUMBER() OVER (
        PARTITION BY master_id,quarter
        ORDER BY is_representative DESC,row_count DESC,fund_code ASC
      ) AS pick
      FROM availability
    ), ranked AS (
      SELECT c.master_id,m.master_name,m.fund_type,m.representative_code,
             h.fund_code,h.quarter,h.stock_code,h.stock_name,h.weight_pct,
             h.market_value_wan,h.fetched_at,h.report_type,h.disclosure_scope,
             COALESCE(NULLIF(s.industry_l1,''),'未分类') AS sector,
             ROW_NUMBER() OVER (
               PARTITION BY c.master_id,h.quarter
               ORDER BY CAST(h.weight_pct AS REAL) DESC,h.stock_code ASC
             ) AS holding_rank
      FROM chosen c
      JOIN fund_master m ON m.master_id=c.master_id
      JOIN fund_holdings h ON h.fund_code=c.fund_code AND h.quarter=c.quarter
      LEFT JOIN security_master s ON s.security_code=h.stock_code
      WHERE c.pick=1
    )
    SELECT * FROM ranked WHERE holding_rank<=10
    """
    out = db.read_sql(sql, tuple(periods))
    if not out.empty:
        out["quarter"] = out["quarter"].map(disclosure.normalize_period)
        out["weight_pct"] = pd.to_numeric(out["weight_pct"], errors="coerce")
        out["market_value_wan"] = pd.to_numeric(out["market_value_wan"], errors="coerce")
        out = out.drop_duplicates(["master_id", "quarter", "stock_code"], keep="first")
    with _CACHE_LOCK:
        if len(_SNAPSHOT_CACHE)>=24:
            for k,_ in sorted(_SNAPSHOT_CACHE.items(),key=lambda kv:kv[1][0])[:6]:_SNAPSHOT_CACHE.pop(k,None)
        _SNAPSHOT_CACHE[(str(db.DB_PATH),db.data_revision())+cache_key]=(time.monotonic()+600.0,out.copy())
    return out


def _demo_top10(periods: list[str]) -> pd.DataFrame:
    h = demo_data.holdings().copy()
    h["quarter"] = h["quarter"].map(disclosure.normalize_period)
    h = h[h.quarter.isin(periods)].copy()
    h["master_id"] = h["fund_code"].astype(str)
    h["master_name"] = h["fund_code"].astype(str)
    h["representative_code"] = h["fund_code"].astype(str)
    h["fetched_at"] = None
    parts=[]
    for (mid,p),g in h.groupby(["master_id","quarter"]):
        parts.append(disclosure.top_n(g,10))
    return pd.concat(parts,ignore_index=True) if parts else h.iloc[0:0].copy()


def _periods_for_mode(mode: str) -> tuple[list[str], dict[str, int]]:
    if mode == "demo":
        h = demo_data.holdings()
        periods = _sort_periods(h.quarter.tolist())
        counts = {p: int(h[h.quarter == p].fund_code.nunique()) for p in periods}
        return periods, counts
    return _local_period_catalog()


def _snapshots(mode: str, periods: list[str]) -> pd.DataFrame:
    return _demo_top10(periods) if mode == "demo" else _canonical_top10_local(periods)


def _resolve_pair(periods: list[str], period=None, compare_period=None) -> tuple[str | None, str | None, str | None, int | None]:
    if not periods:
        return None, None, None, None
    selected = disclosure.normalize_period(period) if period else periods[-1]
    if selected not in periods:
        selected = periods[-1]
    si = periods.index(selected)
    requested = disclosure.normalize_period(compare_period) if compare_period else None
    compare = requested if requested in periods and _period_key(requested) < _period_key(selected) else (periods[si - 1] if si > 0 else None)
    if not compare:
        return selected, None, None, None
    gap = disclosure.periods_apart(compare, selected)
    prior = None
    if gap and gap > 0:
        target_key = _period_key(compare) - gap
        prior = next((p for p in periods if _period_key(p) == target_key), None)
    return selected, compare, prior, gap


def _cohort(frame: pd.DataFrame, periods: list[str]) -> set[str]:
    sets=[]
    for p in periods:
        x=frame[frame.quarter==p]
        sets.append(set(x.master_id.astype(str)))
    return set.intersection(*sets) if sets else set()


def _security_stats(frame: pd.DataFrame, period: str, cohort: set[str]) -> pd.DataFrame:
    x=frame[(frame.quarter==period) & frame.master_id.astype(str).isin(cohort)].copy()
    if x.empty:
        return pd.DataFrame(columns=["stock_code","stock_name","sector","fund_count","avg_weight","total_weight","market_value_yi"])
    stats=(x.groupby(["stock_code","stock_name","sector"],as_index=False)
           .agg(fund_count=("master_id","nunique"),avg_weight=("weight_pct","mean"),total_weight=("weight_pct","sum"),market_value_wan=("market_value_wan","sum")))
    stats["market_value_yi"]=pd.to_numeric(stats["market_value_wan"],errors="coerce")/10000
    return stats.drop(columns=["market_value_wan"])


def _merge_stats(old: pd.DataFrame, new: pd.DataFrame, cohort_size: int) -> pd.DataFrame:
    a=old.rename(columns={"stock_name":"name_old","sector":"sector_old","fund_count":"fund_old","avg_weight":"avg_old","total_weight":"total_old","market_value_yi":"mv_old"})
    b=new.rename(columns={"stock_name":"name_new","sector":"sector_new","fund_count":"fund_new","avg_weight":"avg_new","total_weight":"total_new","market_value_yi":"mv_new"})
    d=a.merge(b,on="stock_code",how="outer")
    if d.empty:return d
    d["stock_name"]=d["name_new"].fillna(d["name_old"])
    d["sector"]=d["sector_new"].fillna(d["sector_old"]).fillna("未分类")
    for c in ["fund_old","fund_new","avg_old","avg_new","total_old","total_new","mv_old","mv_new"]:
        d[c]=pd.to_numeric(d.get(c),errors="coerce").fillna(0)
    den=max(1,int(cohort_size))
    d["coverage_old_pct"]=d["fund_old"]/den*100
    d["coverage_new_pct"]=d["fund_new"]/den*100
    d["delta"]=d["fund_new"]-d["fund_old"]
    d["coverage_delta_pp"]=d["coverage_new_pct"]-d["coverage_old_pct"]
    return d


def _sector_change(frame: pd.DataFrame, selected: str, compare: str | None, cohort: set[str]) -> list[dict[str, Any]]:
    if not compare or not cohort:return []
    def dist(p):
        x=frame[(frame.quarter==p)&frame.master_id.astype(str).isin(cohort)].copy()
        if x.empty:return pd.DataFrame(columns=["sector","weight"])
        g=x.groupby("sector",as_index=False).weight_pct.sum().rename(columns={"weight_pct":"weight"})
        total=float(g.weight.sum() or 0)
        if total>0:g["weight"]=g.weight/total*100
        return g
    a=dist(compare).rename(columns={"weight":"old"});b=dist(selected).rename(columns={"weight":"new"})
    m=a.merge(b,on="sector",how="outer").fillna(0);m["delta"]=m.new-m.old
    for c in ["old","new","delta"]:m[c]=pd.to_numeric(m[c],errors="coerce").round(2)
    return _records(m.sort_values("delta",ascending=False))


def _history(mode: str, periods: list[str], selected: str, codes: list[str], selected_universe: set[str], window: int = 8) -> list[dict[str, Any]]:
    if not codes:return []
    # Load top-ten canonical rows for the displayed history window.  This is intentionally
    # bounded to 20 periods and only retained for the handful of high-consensus securities.
    hist_periods=[p for p in periods if _period_key(p)<=_period_key(selected)][-max(2,min(int(window or 8),20)):]
    h=_snapshots(mode,hist_periods)
    if h.empty:return []
    selected_set=set(h[h.quarter==selected].master_id.astype(str)) or selected_universe
    rows=[]
    for p in hist_periods:
        pset=set(h[h.quarter==p].master_id.astype(str))
        cohort=selected_set & pset
        den=len(cohort)
        if den<=0:continue
        x=h[(h.quarter==p)&h.master_id.astype(str).isin(cohort)&h.stock_code.astype(str).isin(codes)]
        names={str(r.stock_code):str(r.stock_name) for _,r in x.iterrows()}
        counts=x.groupby(x.stock_code.astype(str)).master_id.nunique().to_dict() if not x.empty else {}
        for code in codes:
            c=int(counts.get(code,0));rows.append({"quarter":p,"stock_code":code,"stock_name":names.get(code,code),"fund_count":c,"cohort_size":den,"coverage_rate_pct":round(c/den*100,2)})
    return rows


def _fallback_market(mode: str, period=None, compare_period=None) -> dict[str, Any]:
    # Kept only for a local database that has market reports but no fund-level holdings.
    from . import services
    mk=services.market(mode);sec=services.sectors(mode);periods=services.sort_periods(mk.quarter.tolist()) if not mk.empty else []
    selected,compare,prior,gap=_resolve_pair(periods,period,compare_period)
    current=mk[mk.quarter==selected].copy() if selected else pd.DataFrame()
    change=services._coverage_change_between(mk,compare,selected) if compare else []
    lifecycle=[]
    for r in change:
        lifecycle.append({**r,"fund_count":r.get("fund_new",0),"previous_fund_count":r.get("fund_old",0),"coverage_rate_pct":None,"previous_coverage_rate_pct":None,"coverage_delta_pp":None,"change_per_quarter":round(float(r.get("delta") or 0)/max(1,gap or 1),2),"acceleration":None,"consensus_level":"未标准化","consensus_trend":"增强" if float(r.get("delta") or 0)>0 else "弱化" if float(r.get("delta") or 0)<0 else "稳定","state":"市场汇总"})
    return services.clean_payload({"periods":periods,"selected_period":selected,"compare_period":compare,"prior_period":prior,"crowded":_records(current.sort_values("fund_count",ascending=False).head(100)),"coverage_change":change,"lifecycle":lifecycle,"coverage_history":[],"sector_history":_records(sec),"sector_change":[],"summary":{"security_count":len(current),"strengthening_count":sum(1 for x in lifecycle if float(x.get("delta") or 0)>0),"weakening_count":sum(1 for x in lifecycle if float(x.get("delta") or 0)<0)},"data_context":{"basis":"market_aggregate","source":"Market aggregate report","sample_funds":None,"note":"本地缺少基金级持仓，无法建立可比基金 cohort；当前仅展示市场汇总。"}})


def _smart_money_uncached(mode="demo", period=None, compare_period=None):
    periods,period_counts=_periods_for_mode(mode)
    if not periods:
        return {"periods":[],"selected_period":None,"compare_period":None,"crowded":[],"coverage_change":[],"lifecycle":[],"coverage_history":[],"sector_history":[],"sector_change":[],"summary":{},"data_context":{}}
    selected,compare,prior,gap=_resolve_pair(periods,period,compare_period)
    need=[p for p in [prior,compare,selected] if p]
    frame=_snapshots(mode,need)
    if frame.empty and mode=="local":
        return _fallback_market(mode,period,compare_period)
    if frame.empty:
        return {"periods":periods,"selected_period":selected,"compare_period":compare,"crowded":[],"coverage_change":[],"lifecycle":[],"coverage_history":[],"sector_history":[],"sector_change":[],"summary":{},"data_context":{}}

    selected_universe=set(frame[frame.quarter==selected].master_id.astype(str))
    compare_universe=set(frame[frame.quarter==compare].master_id.astype(str)) if compare else set()
    pair_cohort=(selected_universe & compare_universe) if compare else selected_universe
    if compare and not pair_cohort:
        return _fallback_market(mode,period,compare_period) if mode=="local" else {"periods":periods,"selected_period":selected,"compare_period":compare,"lifecycle":[],"coverage_history":[],"sector_change":[],"summary":{},"data_context":{}}

    # For acceleration, all three points use the same fund cohort.  This keeps the
    # denominator fixed across both equal-length intervals.
    triple_cohort=set()
    if prior and compare and disclosure.equal_spacing(prior,compare,selected):
        prior_universe=set(frame[frame.quarter==prior].master_id.astype(str))
        triple_cohort=selected_universe & compare_universe & prior_universe

    cur=_security_stats(frame,selected,pair_cohort)
    old=_security_stats(frame,compare,pair_cohort) if compare else pd.DataFrame(columns=cur.columns)
    merged=_merge_stats(old,cur,len(pair_cohort)) if compare else cur.assign(fund_old=0,fund_new=cur.fund_count,coverage_old_pct=0,coverage_new_pct=cur.fund_count/max(1,len(pair_cohort))*100,delta=0,coverage_delta_pp=0,stock_name=cur.stock_name,sector=cur.sector,avg_new=cur.avg_weight,total_new=cur.total_weight,mv_new=cur.market_value_yi)

    prior_deltas={}
    if triple_cohort:
        p0=_security_stats(frame,prior,triple_cohort);p1=_security_stats(frame,compare,triple_cohort);p2=_security_stats(frame,selected,triple_cohort)
        first=_merge_stats(p0,p1,len(triple_cohort));second=_merge_stats(p1,p2,len(triple_cohort))
        prev_map={str(r.stock_code):float(r.coverage_delta_pp) for _,r in first.iterrows()}
        cur_map={str(r.stock_code):float(r.coverage_delta_pp) for _,r in second.iterrows()}
        prior_deltas={c:(cur_map.get(c,0)-prev_map.get(c,0)) for c in set(prev_map)|set(cur_map)}

    active=merged[pd.to_numeric(merged.get("fund_new"),errors="coerce").fillna(0)>0].copy()
    p75_rate=float(active.coverage_new_pct.quantile(.75)) if not active.empty else 0.0
    p90_rate=float(active.coverage_new_pct.quantile(.90)) if not active.empty else 0.0
    rows=[]
    for _,r in merged.iterrows():
        code=str(r.stock_code);new_count=float(r.fund_new or 0);old_count=float(r.fund_old or 0);new_rate=float(r.coverage_new_pct or 0);old_rate=float(r.coverage_old_pct or 0);delta=float(r.delta or 0);rate_delta=float(r.coverage_delta_pp or 0)
        level="高" if p75_rate>0 and new_rate>=p75_rate else "中" if new_rate>0 and new_rate>=max(.01,p75_rate*.4) else "低"
        if compare and old_count<=0<new_count:trend="新形成"
        elif rate_delta>0 and triple_cohort and prior_deltas.get(code,0)>0:trend="持续增强"
        elif rate_delta>0:trend="增强"
        elif rate_delta<0 and level=="高":trend="退潮"
        elif rate_delta<0:trend="弱化"
        else:trend="稳定"
        rows.append({"stock_code":code,"stock_name":str(r.stock_name),"sector":str(r.sector or "未分类"),"fund_count":round(new_count,2),"previous_fund_count":round(old_count,2),"coverage_rate_pct":round(new_rate,2),"previous_coverage_rate_pct":round(old_rate,2),"delta":round(delta,2),"coverage_delta_pp":round(rate_delta,2),"change_per_quarter":round(delta/max(1,gap or 1),2),"coverage_change_per_quarter_pp":round(rate_delta/max(1,gap or 1),2),"acceleration":round(float(prior_deltas[code]),2) if code in prior_deltas else None,"market_value_yi":round(float(r.mv_new or 0),2),"consensus_level":level,"consensus_trend":trend,"state":f"{level}共识 · {trend}"})
    rows=sorted(rows,key=lambda x:(x["coverage_rate_pct"],x["coverage_delta_pp"]),reverse=True)
    coverage_change=sorted([{k:x[k] for k in ["stock_code","stock_name","sector","previous_fund_count","fund_count","delta","previous_coverage_rate_pct","coverage_rate_pct","coverage_delta_pp"]} for x in rows],key=lambda x:x["coverage_delta_pp"],reverse=True)
    crowded=rows[:100]
    # Historical coverage is loaded by a separate endpoint after the core page is
    # visible. Do not make a 20-quarter ranking query block the whole Smart Money page.
    history=[]

    # Sector history is kept as a secondary market-level context when available.
    try:
        from . import services
        sec=services.sectors(mode)
        sector_history=_records(sec)
    except Exception as exc:
        logger.warning("sector_history_failed mode=%s error=%s",mode,exc)
        sector_history=[]
    sector_change=_sector_change(frame,selected,compare,pair_cohort)
    updated=None
    if "fetched_at" in frame.columns and not frame.fetched_at.dropna().empty:
        updated=str(frame.fetched_at.dropna().max())
    summary={"security_count":int(sum(1 for x in rows if x["fund_count"]>0)),"high_consensus_count":int(sum(1 for x in rows if x["consensus_level"]=="高")),"strengthening_count":int(sum(1 for x in rows if x["consensus_trend"] in {"增强","持续增强","新形成"})),"weakening_count":int(sum(1 for x in rows if x["consensus_trend"] in {"弱化","退潮"})),"new_consensus_count":int(sum(1 for x in rows if x["consensus_trend"]=="新形成")),"p75_coverage_rate_pct":round(p75_rate,2),"p90_coverage_rate_pct":round(p90_rate,2),"p75_coverage":round(float(np.quantile([x["fund_count"] for x in rows if x["fund_count"]>0],.75)),2) if any(x["fund_count"]>0 for x in rows) else 0}
    data_context={"basis":"top10_comparable","basis_label":"Top 10 Comparable","source":"Fund Master quarterly holdings" if mode=="local" else "Demo quarterly holdings","selected_period":selected,"compare_period":compare,"selected_universe_funds":len(selected_universe),"compare_universe_funds":len(compare_universe) if compare else None,"sample_funds":len(pair_cohort),"triple_cohort_funds":len(triple_cohort) if triple_cohort else None,"selected_coverage_universe":len(selected_universe),"compare_coverage_universe":len(compare_universe) if compare else None,"updated_at":updated,"note":"Q1/Q3 与 Q2/Q4 统一按每只基金前十大披露持仓比较；变化只使用两期均有有效数据的基金主体。"}
    return {"periods":periods,"selected_period":selected,"compare_period":compare,"prior_period":prior,"comparison_gap_quarters":gap,"crowded":crowded,"coverage_change":coverage_change,"lifecycle":rows,"coverage_history":history,"sector_history":sector_history,"sector_change":sector_change,"summary":summary,"data_context":data_context}


def smart_money(mode="demo", period=None, compare_period=None):
    # Normalize "latest/previous" and explicit UI selections to the same cache key.
    # This prevents the first page load from immediately recomputing the same pair
    # after the frontend resolves the dropdown values.
    periods,_=_periods_for_mode(mode)
    selected,compare,_,_=_resolve_pair(periods,period,compare_period)
    p=selected or "none";c=compare or "none"
    return _cached(("smart_money",mode,p,c),lambda:_smart_money_uncached(mode,selected,compare),ttl=600.0,max_items=64)



def smart_money_progressive(mode="demo", period=None, compare_period=None, wait_seconds: float = 4.0):
    """Return the exact fund-cohort result when it is ready, otherwise a fast market snapshot.

    Large local databases can take several seconds to build a canonical Fund Master
    cohort for the first time.  The UI should still become usable immediately.  A
    single background job computes the exact result and fills the normal cache; the
    next lightweight poll receives that exact result.
    """
    if mode != "local":
        return smart_money(mode, period, compare_period)
    periods, _ = _periods_for_mode(mode)
    selected, compare, _, _ = _resolve_pair(periods, period, compare_period)
    if not selected:
        return smart_money(mode, period, compare_period)
    key = (str(db.DB_PATH), db.data_revision(), "smart_money_progressive", selected, compare or "none")
    # Reuse the regular result cache first.
    regular_key = (str(db.DB_PATH), db.data_revision(), "smart_money", mode, selected, compare or "none")
    with _CACHE_LOCK:
        hit = _RESULT_CACHE.get(regular_key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        fut = _PROGRESSIVE_FUTURES.get(key)
        if fut is None or fut.done():
            fut = _PROGRESSIVE_POOL.submit(smart_money, mode, selected, compare)
            _PROGRESSIVE_FUTURES[key] = fut
    try:
        return fut.result(timeout=max(0.2, float(wait_seconds)))
    except Exception as exc:
        # Timeout is expected on a cold multi-GB database.  Other failures are logged,
        # then the market-level table is used as a safe, clearly labelled fallback.
        if fut.done():
            logger.warning("progressive_consensus_background_failed period=%s compare=%s error=%s", selected, compare, exc)
        fallback = _fallback_market(mode, selected, compare)
        ctx = dict(fallback.get("data_context") or {})
        ctx.update({
            "progressive_pending": not fut.done(),
            "basis_label": "Market Snapshot" if not fut.done() else ctx.get("basis_label", "Market aggregate"),
            "note": "基金级可比样本正在后台整理，当前先展示市场汇总快照；完成后页面会自动刷新。" if not fut.done() else ctx.get("note"),
        })
        fallback["data_context"] = ctx
        return fallback

def smart_money_history(mode="demo", period=None, codes=None, window=8):
    periods,_=_periods_for_mode(mode)
    if not periods:return {"periods":[],"selected_period":None,"coverage_history":[]}
    selected=disclosure.normalize_period(period) if period else periods[-1]
    if selected not in periods:selected=periods[-1]
    clean_codes=[]
    for code in (codes or []):
        c=str(code or "").strip()
        if c and c not in clean_codes:clean_codes.append(c)
        if len(clean_codes)>=12:break
    w=max(2,min(int(window or 8),20))
    def build():
        if not clean_codes:return {"periods":[],"selected_period":selected,"coverage_history":[]}
        selected_frame=_snapshots(mode,[selected])
        selected_universe=set(selected_frame[selected_frame.quarter==selected].master_id.astype(str)) if not selected_frame.empty else set()
        rows=_history(mode,periods,selected,clean_codes,selected_universe,w)
        used=_sort_periods([x.get("quarter") for x in rows])
        return {"periods":used,"selected_period":selected,"coverage_history":rows}
    return _cached(("smart_money_history",mode,selected,tuple(clean_codes),w),build,ttl=900.0,max_items=48)
