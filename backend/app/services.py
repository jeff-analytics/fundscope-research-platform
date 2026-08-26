import math
import re
import time
import threading
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from . import db, demo_data, fund_master, disclosure
from .manager_index import manager_id, surname_initial

_HOLDINGS_CACHE_LOCK=threading.Lock()
_HOLDINGS_CACHE={}
_HOLDINGS_CACHE_MAX=96
_FUND_ROW_CACHE={}
_MANAGER_CACHE_LOCK=threading.Lock()
_MANAGER_CATALOG_CACHE={}
_MANAGER_DETAIL_CACHE={}
_ELIGIBLE_CODES_CACHE={}


def _cache_get(store,key,ttl):
    now=time.monotonic();item=store.get(key)
    if item and item[0]>now:return item[1]
    if item:store.pop(key,None)
    return None


def _cache_put(store,key,value,ttl,max_items=96):
    now=time.monotonic()
    if len(store)>=max_items:
        expired=[k for k,v in store.items() if v[0]<=now]
        for k in expired:store.pop(k,None)
        if len(store)>=max_items:
            # Simple bounded cache: remove the oldest-expiring quarter of entries.
            for k,_ in sorted(store.items(),key=lambda kv:kv[1][0])[:max(1,max_items//4)]:store.pop(k,None)
    store[key]=(now+ttl,value)



def clean_payload(value: Any):
    """Convert pandas/numpy values into strict JSON-safe Python values."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): clean_payload(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [clean_payload(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return float(value)
    if isinstance(value, (int, str, bool)):
        return value
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _records(df):
    if df is None or df.empty:
        return []
    safe = df.replace([np.inf, -np.inf], np.nan).astype(object)
    safe = safe.where(pd.notna(safe), None)
    return clean_payload(safe.to_dict("records"))


def normalize_period(value):
    s = str(value or "").strip()
    if not s:
        return ""
    m = re.search(r"(20\d{2})\D*Q\s*([1-4])", s, re.I)
    if m:
        return f"{m.group(1)}Q{m.group(2)}"
    m = re.search(r"(20\d{2}).*?([1-4])\s*季度", s)
    if m:
        return f"{m.group(1)}Q{m.group(2)}"
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 6 and digits[:4].startswith("20"):
        year = int(digits[:4])
        month = int(digits[4:6])
        if 1 <= month <= 12:
            q = (month - 1) // 3 + 1
            return f"{year}Q{q}"
    m = re.search(r"(20\d{2})", s)
    return m.group(1) if m else s


def period_key(value):
    s = normalize_period(value)
    m = re.fullmatch(r"(20\d{2})Q([1-4])", s)
    if m:
        return int(m.group(1)) * 10 + int(m.group(2))
    m = re.search(r"(20\d{2})", s)
    return int(m.group(1)) * 10 if m else 0


def sort_periods(values):
    normalized = {normalize_period(v) for v in values if normalize_period(v)}
    return sorted(normalized, key=period_key)


def _demo_funds(q="", research_only=True):
    df = demo_data.FUNDS.copy()
    if research_only and "fund_type" in df.columns:
        mask=df.apply(lambda r: fund_master.eligible_equity(r.get("fund_type"),r.get("fund_name"))[0],axis=1)
        df=df[mask]
    if q:
        needle = q.lower()
        mask = (
            df["fund_code"].astype(str).str.lower().str.contains(needle, regex=False)
            | df["fund_name"].astype(str).str.lower().str.contains(needle, regex=False)
            | df["manager_name"].astype(str).str.lower().str.contains(needle, regex=False)
        )
        df = df[mask]
    return _records(df.head(100))


def funds(mode="demo", q="", research_only=True):
    if mode == "demo":
        return _demo_funds(q,research_only)
    needle = f"%{q.strip()}%"
    if research_only:
        fund_master.ensure_master()
        if q.strip():
            df=db.read_sql(
                """
                SELECT DISTINCT m.representative_code AS fund_code,
                       COALESCE(NULLIF(rep.fund_name,''),m.master_name) AS fund_name,
                       m.fund_type,'' AS manager_name,NULL AS aum_yi
                FROM fund_master m
                JOIN fund_share_classes rep ON rep.fund_code=m.representative_code
                LEFT JOIN fund_master_members mm ON mm.master_id=m.master_id
                LEFT JOIN fund_share_classes member ON member.fund_code=mm.fund_code
                WHERE m.eligible_equity=1 AND (
                    m.representative_code LIKE ? OR m.master_name LIKE ? OR
                    mm.fund_code LIKE ? OR member.fund_name LIKE ?
                )
                ORDER BY m.representative_code LIMIT 100
                """,(needle,needle,needle,needle)
            )
        else:
            df=db.read_sql(
                """
                SELECT m.representative_code AS fund_code,
                       COALESCE(NULLIF(rep.fund_name,''),m.master_name) AS fund_name,
                       m.fund_type,'' AS manager_name,NULL AS aum_yi
                FROM fund_master m JOIN fund_share_classes rep ON rep.fund_code=m.representative_code
                WHERE m.eligible_equity=1 ORDER BY m.representative_code LIMIT 100
                """
            )
        return _records(df)
    if q.strip():
        df=db.read_sql(
            "SELECT fund_code,fund_name,fund_type,'' AS manager_name,NULL AS aum_yi FROM fund_share_classes WHERE fund_code LIKE ? OR fund_name LIKE ? OR base_name_candidate LIKE ? ORDER BY fund_code LIMIT 100",
            (needle,needle,needle)
        )
    else:
        df=db.read_sql("SELECT fund_code,fund_name,fund_type,'' AS manager_name,NULL AS aum_yi FROM fund_share_classes ORDER BY fund_code LIMIT 100")
    return _records(df)



def _eligible_member_codes():
    key=('eligible_codes',db.data_revision())
    with _MANAGER_CACHE_LOCK:
        cached=_cache_get(_ELIGIBLE_CODES_CACHE,key,600.0)
    if cached is not None:return set(cached)
    try:
        fund_master.ensure_master()
        df=db.read_sql('''SELECT mm.fund_code FROM fund_master_members mm JOIN fund_master m ON m.master_id=mm.master_id WHERE m.eligible_equity=1''')
        out=set(df.fund_code.astype(str).tolist()) if not df.empty else set()
    except Exception:
        out=set()
    with _MANAGER_CACHE_LOCK:_cache_put(_ELIGIBLE_CODES_CACHE,key,frozenset(out),600.0,8)
    return out


def _filter_equity_managers(df):
    if df is None or df.empty:return df
    eligible=_eligible_member_codes()
    if not eligible:return df.iloc[0:0]
    mask=[]
    for _,r in df.iterrows():
        codes=set(re.findall(r'(?<!\d)\d{6}(?!\d)',str(r.get('current_fund_codes') or '')))
        mask.append(bool(codes & eligible))
    return df[pd.Series(mask,index=df.index)]

def _decorate_managers(df):
    if df is None or df.empty:return []
    out=pd.DataFrame({
      "manager_name":df["manager_name"],"company":df["company"],
      "career_years":pd.to_numeric(df.get("career_days",df.get("career_years")),errors="coerce")/365.25 if "career_days" in df.columns else pd.to_numeric(df.get("career_years"),errors="coerce"),
      "aum_yi":pd.to_numeric(df.get("current_aum_billion",df.get("aum_yi")),errors="coerce"),
      "best_return_pct":pd.to_numeric(df.get("best_return_pct"),errors="coerce"),
      "fund_codes":df.get("current_fund_codes",df.get("fund_codes",pd.Series([""]*len(df)))).fillna(""),
      "current_funds":df.get("current_funds",pd.Series([""]*len(df))).fillna("")
    })
    out["manager_id"]=[manager_id(n,c) for n,c in zip(out.manager_name,out.company)]
    out["surname_initial"]=[surname_initial(n) for n in out.manager_name]
    return _records(out)

def _demo_managers(q=""):
    df=demo_data.MANAGERS.copy()
    if q:
        needle=q.lower();df=df[df["manager_name"].astype(str).str.lower().str.contains(needle,regex=False)|df["company"].astype(str).str.lower().str.contains(needle,regex=False)]
    return _decorate_managers(df.head(100))

def managers(mode="demo",q=""):
    if mode=="demo":return _demo_managers(q)
    needle=f"%{q.strip()}%"
    if q.strip():m=db.read_sql("SELECT * FROM fund_managers WHERE manager_name LIKE ? OR company LIKE ? ORDER BY manager_name LIMIT 500",(needle,needle))
    else:m=db.read_sql("SELECT * FROM fund_managers ORDER BY manager_name")
    m=_filter_equity_managers(m)
    return _decorate_managers(m.head(100))

def manager_catalog(mode="demo"):
    key=('manager_catalog',mode,db.data_revision())
    with _MANAGER_CACHE_LOCK:
        cached=_cache_get(_MANAGER_CATALOG_CACHE,key,600.0)
    if cached is not None:return cached
    if mode=="demo":out=_decorate_managers(demo_data.MANAGERS.copy())
    else:out=_decorate_managers(_filter_equity_managers(db.read_sql("SELECT * FROM fund_managers ORDER BY manager_name")))
    with _MANAGER_CACHE_LOCK:_cache_put(_MANAGER_CATALOG_CACHE,key,out,600.0,8)
    return out

def manager_by_id(mid,mode="demo"):
    key=('manager_by_id',mode,str(mid),db.data_revision())
    with _MANAGER_CACHE_LOCK:
        cached=_cache_get(_MANAGER_DETAIL_CACHE,key,300.0)
    if cached is not None:return cached
    catalog=manager_catalog(mode)
    item=next((x for x in catalog if x.get("manager_id")==mid),None)
    if not item:return None
    out=manager_detail(item["manager_name"],mode,company=item.get("company"))
    if out is not None:
        with _MANAGER_CACHE_LOCK:_cache_put(_MANAGER_DETAIL_CACHE,key,out,300.0,96)
    return out

def _holding_source_code(code):
    code=str(code)
    resolved=fund_master.resolve(code)
    members=resolved.get("member_codes") or [code]
    rep=str(resolved.get("representative_code") or code)
    preferred=[rep]+[str(x) for x in members if str(x)!=rep]
    # One grouped lookup is cheaper and more stable than one COUNT query per share class.
    marks=','.join(['?']*len(preferred))
    counts=db.read_sql(f"SELECT fund_code,COUNT(*) n FROM fund_holdings WHERE fund_code IN ({marks}) GROUP BY fund_code",tuple(preferred)) if preferred else pd.DataFrame()
    available={str(r.fund_code):int(r.n or 0) for _,r in counts.iterrows()} if not counts.empty else {}
    chosen=next((c for c in preferred if available.get(c,0)>0),code)
    return resolved,chosen


def fund_periods(mode="demo",code=None):
    if mode=='demo':
        h=demo_data.holdings().copy();
        if code is not None:h=h[h['fund_code'].astype(str)==str(code)]
        return sort_periods(h.quarter.tolist()) if not h.empty else []
    if code is None:return []
    rev=db.data_revision();key=('periods',rev,str(code))
    with _HOLDINGS_CACHE_LOCK:cached=_cache_get(_HOLDINGS_CACHE,key,20.0)
    if cached is not None:return list(cached)
    _,chosen=_holding_source_code(code)
    q=db.read_sql("SELECT DISTINCT quarter FROM fund_holdings WHERE fund_code=? ORDER BY requested_year,quarter",(chosen,))
    out=sort_periods(q.quarter.tolist()) if not q.empty else []
    with _HOLDINGS_CACHE_LOCK:_cache_put(_HOLDINGS_CACHE,key,tuple(out),20.0,_HOLDINGS_CACHE_MAX)
    return out


def holdings(mode="demo", code=None, periods=None, enriched=True):
    if mode == "demo":
        h = demo_data.holdings().copy()
        if code is not None:
            h = h[h["fund_code"].astype(str) == str(code)]
        wanted={normalize_period(x) for x in (periods or []) if normalize_period(x)}
        if wanted:h=h[h['quarter'].map(normalize_period).isin(wanted)].copy()
        if "shares" not in h.columns:h["shares"] = np.nan
        if "market_value_wan" not in h.columns:h["market_value_wan"] = np.nan
        if "report_type" not in h.columns:h["report_type"] = h["quarter"].map(lambda q: "季度报告" if str(q).endswith(("Q1","Q3")) else "中期/年度报告")
        if "disclosure_scope" not in h.columns:h["disclosure_scope"] = h["quarter"].map(disclosure.scope_for_period)
        return h
    if code is None:return pd.DataFrame()
    wanted=tuple(sort_periods(periods or []))
    rev=db.data_revision();key=('holdings',rev,str(code),wanted,bool(enriched))
    with _HOLDINGS_CACHE_LOCK:cached=_cache_get(_HOLDINGS_CACHE,key,180.0)
    if cached is not None:return cached.copy()
    resolved,chosen=_holding_source_code(code)
    period_clause='';params=[chosen]
    if wanted:
        marks=','.join(['?']*len(wanted));period_clause=f" AND h.quarter IN ({marks})";params.extend(wanted)
    if enriched:
        select_extra=""",s.total_market_cap,s.float_market_cap,s.pe,s.pb,s.revenue_growth_yoy,s.profit_growth_yoy"""
    else:
        select_extra=''
    h=db.read_sql(f"""
        SELECT h.fund_code,h.quarter,h.stock_code,h.stock_name,h.weight_pct,h.shares,h.market_value_wan,h.report_type,h.disclosure_scope,h.fetched_at,
               COALESCE(NULLIF(s.industry_l1,''),'未分类') AS sector{select_extra}
        FROM fund_holdings h LEFT JOIN security_master s ON s.security_code=h.stock_code
        WHERE h.fund_code=?{period_clause}
        ORDER BY h.requested_year,h.quarter,h.weight_pct DESC
        """,tuple(params))
    if h.empty:return h
    h["requested_fund_code"] = str(code);h["quarter"] = h["quarter"].map(normalize_period)
    numeric=["weight_pct","shares","market_value_wan"]
    if enriched:numeric += ["total_market_cap","float_market_cap","pe","pb","revenue_growth_yoy","profit_growth_yoy"]
    for c in numeric:
        if c in h.columns:h[c]=pd.to_numeric(h[c],errors="coerce")
    with _HOLDINGS_CACHE_LOCK:_cache_put(_HOLDINGS_CACHE,key,h.copy(),180.0,_HOLDINGS_CACHE_MAX)
    return h


def holdings_period(mode,code,period,enriched=False):
    p=normalize_period(period)
    return holdings(mode,code,[p] if p else None,enriched=enriched)


def market(mode="demo"):
    if mode == "demo":
        return demo_data.market_consensus().copy()
    m = db.read_sql("""
        SELECT c.*,COALESCE(NULLIF(s.industry_l1,''),'未分类') AS mapped_sector
        FROM market_stock_consensus c
        LEFT JOIN security_master s ON s.security_code=c.stock_code
        WHERE c.report_date IN (SELECT report_date FROM (SELECT DISTINCT report_date FROM market_stock_consensus ORDER BY report_date DESC LIMIT 24))
    """)
    if m.empty:
        return m
    out = m.rename(columns={"report_date": "quarter", "market_value_wan": "market_value_yi"}).copy()
    out["quarter"] = out["quarter"].map(normalize_period)
    out["market_value_yi"] = pd.to_numeric(out["market_value_yi"], errors="coerce") / 10000
    out["fund_count"] = pd.to_numeric(out["fund_count"], errors="coerce").fillna(0)
    out["sector"] = out.get("mapped_sector", "未分类")
    out["avg_weight"] = np.nan
    out["_period_key"]=out["quarter"].map(period_key)
    out=out.sort_values(["_period_key","stock_code"]).drop(columns="_period_key")
    return out[["quarter", "stock_code", "stock_name", "sector", "fund_count", "market_value_yi", "avg_weight"]]


def sectors(mode="demo"):
    if mode == "demo":
        return demo_data.sector_history().copy()
    s = db.read_sql("""SELECT * FROM market_industry_allocation
        WHERE report_date IN (SELECT report_date FROM (SELECT DISTINCT report_date FROM market_industry_allocation ORDER BY report_date DESC LIMIT 24))""")
    if s.empty:
        return s
    out = s.rename(
        columns={"report_date": "quarter", "industry_name": "sector", "nav_weight_pct": "weight_pct"}
    ).copy()
    out["quarter"] = out["quarter"].map(normalize_period)
    out["weight_pct"] = pd.to_numeric(out["weight_pct"], errors="coerce")
    out["_period_key"]=out["quarter"].map(period_key)
    out=out.sort_values(["_period_key","sector"]).drop(columns="_period_key")
    return out[["quarter", "sector", "weight_pct"]]


def assets(mode="demo"):
    if mode == "demo":
        return demo_data.asset_history().copy()
    # Asset allocation is a small quarterly aggregate table. Return the complete
    # locally collected history instead of a fixed 12-quarter window so the chart
    # timeline always reflects the user's actual database depth.
    a = db.read_sql("""SELECT * FROM market_asset_allocation ORDER BY report_date""")
    if a.empty:
        return a
    out = a.rename(
        columns={
            "report_date": "quarter",
            "equity_weight_pct": "equity",
            "fixed_income_weight_pct": "fixed_income",
            "cash_weight_pct": "cash",
        }
    ).copy()
    out["quarter"] = out["quarter"].map(normalize_period)
    for c in ["equity", "fixed_income", "cash"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out["_period_key"]=out["quarter"].map(period_key)
    out=out.sort_values("_period_key").drop(columns="_period_key")
    return out[["quarter", "equity", "fixed_income", "cash"]]


def compare_periods(h, code, p0, p1):
    """Compare two report snapshots on a disclosure-comparable basis.

    Q1/Q3 normally expose top-ten holdings while Q2/Q4 may expose a broader
    portfolio.  The comparison normalizes both sides to top ten whenever either
    side is top-ten scope, preventing disclosure breadth from being interpreted
    as a real entry or exit.
    """
    if h is None or h.empty:
        return pd.DataFrame()
    codes = set(h["fund_code"].astype(str)) if "fund_code" in h.columns else set()
    base = h[h["fund_code"].astype(str) == str(code)].copy() if str(code) in codes else h.copy()
    a0 = base[base.quarter == p0].copy()
    b0 = base[base.quarter == p1].copy()
    a0,b0,meta = disclosure.comparable_pair(a0,b0,p0,p1)
    a = a0[["stock_code", "stock_name", "sector", "weight_pct"]].rename(
        columns={"stock_name": "name_old", "sector": "sector_old", "weight_pct": "weight_old"}
    )
    b = b0[["stock_code", "stock_name", "sector", "weight_pct"]].rename(
        columns={"stock_name": "name_new", "sector": "sector_new", "weight_pct": "weight_new"}
    )
    m = a.merge(b, on="stock_code", how="outer")
    if m.empty:
        m.attrs["comparison_meta"] = meta
        return m
    m["stock_name"] = m["name_new"].fillna(m["name_old"])
    m["sector"] = m["sector_new"].fillna(m["sector_old"])
    m["delta"] = m["weight_new"].fillna(0) - m["weight_old"].fillna(0)

    def label(r):
        if pd.isna(r["weight_old"]):
            return "新进入披露"
        if pd.isna(r["weight_new"]):
            return "退出披露"
        if r["delta"] > 0.05:
            return "权重上升"
        if r["delta"] < -0.05:
            return "权重下降"
        return "基本稳定"

    m["activity"] = m.apply(label, axis=1)
    out=m[["stock_code", "stock_name", "sector", "weight_old", "weight_new", "delta", "activity"]].sort_values("delta", ascending=False)
    out.attrs["comparison_meta"] = meta
    return out


def _fund_row(code, mode):
    if mode == "demo":
        row = demo_data.FUNDS[demo_data.FUNDS["fund_code"].astype(str) == str(code)]
        return None if row.empty else _records(row)[0]
    rev=db.data_revision();key=(rev,str(code));cached=_cache_get(_FUND_ROW_CACHE,key,45.0)
    if cached is not None:return dict(cached)
    row = db.read_sql(
        """SELECT fund_code,fund_name,fund_type,base_name_candidate,share_class_candidate,master_candidate_id
        FROM fund_share_classes WHERE fund_code=? LIMIT 1""",(str(code),))
    if row.empty:return None
    result=_records(row)[0]
    prof=db.read_sql("SELECT manager_names,fund_company FROM fund_profiles WHERE fund_code=? LIMIT 1",(str(code),))
    if not prof.empty and str(prof.iloc[0].get('manager_names') or '').strip():
        result['manager_name']=clean_payload(prof.iloc[0].get('manager_names'));result['manager_company']=clean_payload(prof.iloc[0].get('fund_company'))
    else:
        # Compatibility fallback for older databases that have no cached profile.
        mgr=db.read_sql("SELECT manager_name,company FROM fund_managers WHERE current_fund_codes LIKE ? LIMIT 1",(f"%{code}%",))
        result['manager_name']=None if mgr.empty else clean_payload(mgr.iloc[0]['manager_name']);result['manager_company']=None if mgr.empty else clean_payload(mgr.iloc[0]['company'])
    result['aum_yi']=None
    _cache_put(_FUND_ROW_CACHE,key,dict(result),45.0,300)
    return result


def fund_detail(code, mode="demo"):
    fund = _fund_row(code, mode)
    if not fund:
        return None
    h = holdings(mode, code, enriched=False)
    if h.empty:
        return clean_payload(
            {
                "fund": fund,
                "periods": [],
                "holdings": [],
                "latest": [],
                "activity": [],
                "sector_shift": [],
                "metrics": {
                    "concentration": None,
                    "change_intensity": None,
                    "persistence": None,
                    "sector_count": 0,
                    "sector_mapped": False,
                },
            }
        )
    periods = sort_periods(h.quarter.tolist())
    latest = h[h.quarter == periods[-1]].sort_values("weight_pct", ascending=False)
    mapped = bool(not latest.empty and not latest["sector"].fillna("未分类").eq("未分类").all())
    activity = []
    sector_shift = []
    change_intensity = None
    comparison_meta = None
    if len(periods) >= 2:
        c = compare_periods(h, code, periods[-2], periods[-1])
        comparison_meta = c.attrs.get("comparison_meta")
        activity = _records(c)
        if not c.empty:
            change_intensity = round(float(c["delta"].abs().sum() / 2), 2)
            if mapped:
                s = (
                    c.groupby("sector", as_index=False)
                    .agg(old=("weight_old", "sum"), new=("weight_new", "sum"), delta=("delta", "sum"))
                    .sort_values("delta", ascending=False)
                )
                sector_shift = _records(s)
    top10 = float(latest.head(10)["weight_pct"].sum()) if not latest.empty else None
    sector_count = int(latest["sector"].nunique()) if mapped else 0
    persistent = 0
    if len(periods) >= 2:
        recent=periods[-min(4, len(periods)):]
        comparable_hist=disclosure.comparable_history(h,recent)
        sets = [set(comparable_hist[comparable_hist.quarter.map(normalize_period) == p].stock_code.astype(str)) for p in recent]
        if sets:
            persistent = len(set.intersection(*sets))
    metrics = {
        "concentration": round(top10, 2) if top10 is not None else None,
        "change_intensity": change_intensity,
        "persistence": persistent,
        "sector_count": sector_count,
        "sector_mapped": mapped,
    }
    return clean_payload(
        {
            "fund": fund,
            "periods": periods,
            "holdings": _records(h),
            "latest": _records(latest),
            "activity": activity,
            "sector_shift": sector_shift,
            "metrics": metrics,
            "data_context": {
                "selected_period": periods[-1] if periods else None,
                "comparison": comparison_meta,
                "source": "Local quarterly holdings" if mode == "local" else "Demo holdings",
                "disclosure_scope": disclosure.frame_scope(latest, periods[-1]) if periods else None,
                "updated_at": (str(h["fetched_at"].dropna().max()) if "fetched_at" in h.columns and not h["fetched_at"].dropna().empty else None),
                "sample_funds": 1,
            },
        }
    )


def manager_detail(name, mode="demo", company=None):
    cache_key=('manager_detail',mode,str(name),str(company or ''),db.data_revision())
    with _MANAGER_CACHE_LOCK:
        cached=_cache_get(_MANAGER_DETAIL_CACHE,cache_key,300.0)
    if cached is not None:return cached
    manager = None
    if mode == "demo":
        row = demo_data.MANAGERS[demo_data.MANAGERS.manager_name == name]
        if not row.empty:
            manager = _records(row)[0]
    else:
        m = db.read_sql("SELECT * FROM fund_managers WHERE manager_name=? AND company=? LIMIT 1", (name, company)) if company else db.read_sql("SELECT * FROM fund_managers WHERE manager_name=? LIMIT 1", (name,))
        if not m.empty:
            r = m.iloc[0]
            manager = clean_payload(
                {
                    "manager_name": r["manager_name"],
                    "company": r["company"],
                    "career_years": float(r["career_days"]) / 365.25 if pd.notna(r["career_days"]) else None,
                    "aum_yi": float(r["current_aum_billion"]) if pd.notna(r["current_aum_billion"]) else None,
                    "best_return_pct": float(r["best_return_pct"]) if pd.notna(r["best_return_pct"]) else None,
                    "fund_codes": str(r["current_fund_codes"] or ""),
                    "current_funds": str(r["current_funds"] or ""),
                    "manager_id": manager_id(r["manager_name"], r["company"]),
                    "surname_initial": surname_initial(r["manager_name"]),
                }
            )
    if manager is None:
        return None
    codes = re.findall(r"[A-Za-z]?\d{5,6}", str(manager.get("fund_codes", "")))
    if mode == "demo" and not codes:
        codes = demo_data.FUNDS[demo_data.FUNDS.manager_name == name].fund_code.astype(str).tolist()
    if mode == "local" and not codes:
        return clean_payload(
            {
                "manager": manager,
                "fund_codes": [],
                "periods": [],
                "consensus": [],
                "sector_history": [],
                "metrics": {"sector_mapped": False},
            }
        )
    frames = []
    analysis_codes=[]
    seen_master=set()
    for c in codes:
        if mode=="local":
            rr=fund_master.resolve(c);key=rr.get("master_id") or str(c)
            if key in seen_master:continue
            seen_master.add(key);analysis_codes.append(str(rr.get("representative_code") or c))
        else:
            analysis_codes.append(str(c))
        wanted=None
        if mode=='local':
            ps=fund_periods(mode,c);wanted=ps[-24:] if ps else None
        hh = holdings(mode, c, wanted)
        if not hh.empty:
            frames.append(hh)
    mh = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if mh.empty:
        return clean_payload(
            {
                "manager": manager,
                "fund_codes": codes,
                "periods": [],
                "consensus": [],
                "sector_history": [],
                "metrics": {"sector_mapped": False},
            }
        )
    periods = sort_periods(mh.quarter.tolist())
    latest = mh[mh.quarter == periods[-1]]
    consensus = (
        latest.groupby(["stock_code", "stock_name", "sector"], as_index=False)
        .agg(fund_coverage=("fund_code", "nunique"), avg_weight=("weight_pct", "mean"), sum_weight=("weight_pct", "sum"))
        .sort_values(["fund_coverage", "sum_weight"], ascending=False)
    )
    mapped = bool(not latest.empty and not latest["sector"].fillna("未分类").eq("未分类").all())
    sector = mh.groupby(["quarter", "sector"], as_index=False)["weight_pct"].sum() if mapped else pd.DataFrame()
    if not sector.empty:
        sector["_period_key"]=sector["quarter"].map(period_key)
        sector=sector.sort_values(["_period_key","sector"]).drop(columns="_period_key")
    fund_count = max(1, latest["fund_code"].nunique())
    high_conviction = (
        int((consensus["fund_coverage"] >= max(1, math.ceil(fund_count * 0.5))).sum()) if not consensus.empty else 0
    )
    metrics = {
        "mapped_funds": len(codes),
        "analysis_funds": len(analysis_codes),
        "collected_funds": int(latest["fund_code"].nunique()),
        "high_conviction": high_conviction,
        "latest_period": periods[-1] if periods else None,
        "sector_mapped": mapped,
    }
    out=clean_payload(
        {
            "manager": manager,
            "fund_codes": codes,
            "periods": periods,
            "consensus": _records(consensus),
            "sector_history": _records(sector),
            "metrics": metrics,
        }
    )
    with _MANAGER_CACHE_LOCK:_cache_put(_MANAGER_DETAIL_CACHE,cache_key,out,300.0,96)
    return out


def _coverage_change(mk):
    if mk.empty:
        return [], []
    periods = sort_periods(mk.quarter.tolist())
    if len(periods) < 2:
        return periods, []
    a = mk[mk.quarter == periods[-2]][["stock_code", "stock_name", "sector", "fund_count"]]
    b = mk[mk.quarter == periods[-1]][["stock_code", "stock_name", "sector", "fund_count"]]
    d = a.merge(b, on="stock_code", how="outer", suffixes=("_old", "_new"))
    d["stock_name"] = d["stock_name_new"].fillna(d["stock_name_old"])
    d["sector"] = d["sector_new"].fillna(d["sector_old"])
    d["fund_old"] = d["fund_count_old"].fillna(0)
    d["fund_new"] = d["fund_count_new"].fillna(0)
    d["delta"] = d["fund_new"] - d["fund_old"]
    return periods, _records(
        d[["stock_code", "stock_name", "sector", "fund_old", "fund_new", "delta"]].sort_values("delta", ascending=False)
    )


def overview(mode="demo"):
    if mode == "demo":
        fund_count = len(demo_data.FUNDS)
        manager_count = len(demo_data.MANAGERS)
        holding_rows = len(demo_data.holdings())
    else:
        try:
            fund_count=int(fund_master.stats().get("eligible",0) or 0)
        except Exception:
            fund_count=db.count("fund_share_classes")
        manager_count = db.count("fund_managers")
        holding_rows = db.count("fund_holdings")
    mk = market(mode)
    sec = sectors(mode)
    ass = assets(mode)
    periods, coverage = _coverage_change(mk)
    latest = periods[-1] if periods else None
    crowded = []
    if not mk.empty and latest:
        crowded = _records(mk[mk.quarter == latest].sort_values(["fund_count", "market_value_yi"], ascending=False).head(20))
    insight = {"positive": [], "negative": []}
    if coverage:
        insight = {"positive": [x["stock_name"] for x in coverage[:3]], "negative": [x["stock_name"] for x in coverage[-3:]]}
    return clean_payload(
        {
            "fund_count": fund_count,
            "manager_count": manager_count,
            "holding_rows": holding_rows,
            "latest_period": latest,
            "crowded": crowded,
            "coverage_change": coverage,
            "sector_history": _records(sec),
            "asset_history": _records(ass),
            "insight": insight,
        }
    )


def _coverage_change_between(mk, old_period, new_period):
    if mk.empty or not old_period or not new_period:
        return []
    a = mk[mk.quarter == old_period][["stock_code", "stock_name", "sector", "fund_count"]]
    b = mk[mk.quarter == new_period][["stock_code", "stock_name", "sector", "fund_count"]]
    d = a.merge(b, on="stock_code", how="outer", suffixes=("_old", "_new"))
    if d.empty:
        return []
    d["stock_name"] = d["stock_name_new"].fillna(d["stock_name_old"])
    d["sector"] = d["sector_new"].fillna(d["sector_old"])
    d["fund_old"] = pd.to_numeric(d["fund_count_old"], errors="coerce").fillna(0)
    d["fund_new"] = pd.to_numeric(d["fund_count_new"], errors="coerce").fillna(0)
    d["delta"] = d["fund_new"] - d["fund_old"]
    return _records(d[["stock_code", "stock_name", "sector", "fund_old", "fund_new", "delta"]].sort_values("delta", ascending=False))


def smart_money(mode="demo", period=None, compare_period=None):
    # Kept as a compatibility entry point for extensions and older tests.
    # Research-integrity logic lives in app.consensus to keep services.py focused.
    from . import consensus
    return clean_payload(consensus.smart_money(mode, period, compare_period))


def compare_funds(code_a, code_b, quarter, mode="demo"):
    quarter = normalize_period(quarter)
    a = holdings(mode, code_a)
    b = holdings(mode, code_b)
    a = a[a.quarter == quarter].copy() if not a.empty else a
    b = b[b.quarter == quarter].copy() if not b.empty else b
    set_a = set(a.stock_code.astype(str)) if not a.empty else set()
    set_b = set(b.stock_code.astype(str)) if not b.empty else set()
    both = set_a & set_b
    union = set_a | set_b
    common = pd.concat([a[a.stock_code.astype(str).isin(both)], b[b.stock_code.astype(str).isin(both)]]) if both else pd.DataFrame()
    if common.empty:
        common_out = []
    else:
        piv = common.pivot_table(
            index=["stock_code", "stock_name", "sector"], columns="fund_code", values="weight_pct", aggfunc="max"
        ).reset_index()
        piv.columns = [str(c) for c in piv.columns]
        common_out = _records(piv)
    mapped = not (
        (not a.empty and a["sector"].eq("未分类").all()) and (not b.empty and b["sector"].eq("未分类").all())
    )
    if mapped:
        sa = (
            a.groupby("sector", as_index=False)["weight_pct"].sum().rename(columns={"weight_pct": "weight_a"})
            if not a.empty
            else pd.DataFrame(columns=["sector", "weight_a"])
        )
        sb = (
            b.groupby("sector", as_index=False)["weight_pct"].sum().rename(columns={"weight_pct": "weight_b"})
            if not b.empty
            else pd.DataFrame(columns=["sector", "weight_b"])
        )
        sector_df = sa.merge(sb, on="sector", how="outer").fillna(0)
    else:
        sector_df = pd.DataFrame(columns=["sector", "weight_a", "weight_b"])
    sim = None
    if not sector_df.empty:
        va = sector_df.weight_a.to_numpy(float)
        vb = sector_df.weight_b.to_numpy(float)
        denom = np.linalg.norm(va) * np.linalg.norm(vb)
        sim = float(np.dot(va, vb) / denom * 100) if denom else 0.0
    return clean_payload(
        {
            "overlap": len(both),
            "union": len(union),
            "overlap_ratio": round(len(both) / len(union) * 100, 2) if union else 0,
            "sector_similarity": round(sim, 2) if sim is not None else None,
            "sector_mapped": mapped,
            "common": common_out,
            "sectors": _records(sector_df),
        }
    )


def _max_value(table, column):
    try:
        df = db.read_sql(f"SELECT MAX({column}) AS v FROM {table}")
        return clean_payload(df.iloc[0]["v"]) if not df.empty else None
    except Exception:
        return None



def data_presence():
    """Very cheap local-data readiness check for app startup.

    Avoid COUNT / DISTINCT scans on large holdings tables. The full health report
    remains available in Data Center when the user explicitly opens it.
    """
    try:
        x=db.read_sql("""
            SELECT
              EXISTS(SELECT 1 FROM fund_holdings LIMIT 1) AS holdings,
              EXISTS(SELECT 1 FROM market_stock_consensus LIMIT 1) AS market_consensus,
              EXISTS(SELECT 1 FROM fund_managers LIMIT 1) AS managers,
              EXISTS(SELECT 1 FROM fund_share_classes LIMIT 1) AS funds
        """)
        if x.empty:return {'has_local_data':False,'holdings':False,'market_consensus':False,'managers':False,'funds':False}
        r=x.iloc[0]
        out={k:bool(int(r.get(k) or 0)) for k in ['holdings','market_consensus','managers','funds']}
        out['has_local_data']=bool(out['holdings'] or out['market_consensus'])
        return out
    except Exception:
        return {'has_local_data':False,'holdings':False,'market_consensus':False,'managers':False,'funds':False}

def health():
    funds_n = db.count("fund_share_classes")
    managers_n = db.count("fund_managers")
    holdings_n = db.count("fund_holdings")
    consensus_n = db.count("market_stock_consensus")
    industry_n = db.count("market_industry_allocation")
    asset_n = db.count("market_asset_allocation")
    try:
        hf = int(db.read_sql("SELECT COUNT(DISTINCT fund_code) AS n FROM fund_holdings").iloc[0]["n"]) if holdings_n else 0
    except Exception:
        hf = 0
    try:
        hp = db.read_sql("SELECT DISTINCT quarter FROM fund_holdings") if holdings_n else pd.DataFrame()
        latest_holding = sort_periods(hp["quarter"].tolist())[-1] if not hp.empty else None
    except Exception:
        latest_holding = None
    try:
        mp = db.read_sql("SELECT DISTINCT report_date FROM market_stock_consensus") if consensus_n else pd.DataFrame()
        latest_market = sort_periods(mp["report_date"].tolist())[-1] if not mp.empty else None
    except Exception:
        latest_market = None
    try:
        fm=fund_master.stats()
    except Exception:
        fm={}
    try:
        hm=int(db.read_sql("SELECT COUNT(DISTINCT mm.master_id) n FROM fund_holdings h JOIN fund_master_members mm ON mm.fund_code=h.fund_code").iloc[0]["n"]) if holdings_n else 0
    except Exception:
        hm=hf
    eligible=int(fm.get("eligible",0) or 0) if fm else funds_n
    coverage=round(hm/max(1,eligible)*100,2)
    security_n=db.count("security_master")
    security_industry=int(db.read_sql("SELECT COUNT(*) n FROM security_master WHERE industry_l1 IS NOT NULL AND industry_l1<>''").iloc[0]["n"]) if security_n else 0
    ready = {
        "foundation": funds_n > 0 and managers_n > 0,
        "holdings": holdings_n > 0,
        "market": consensus_n > 0,
        "allocation": industry_n > 0 or asset_n > 0,
    }
    return clean_payload(
        {
            "funds": funds_n,
            "managers": managers_n,
            "holdings": holdings_n,
            "market_consensus": consensus_n,
            "market_industry": industry_n,
            "asset_allocation": asset_n,
            "tasks": db.count("task_log"),
            "holding_funds": hm,
            "holding_coverage_pct": coverage,
            "latest_holding_period": latest_holding,
            "latest_market_period": latest_market,
            "last_holdings_update": _max_value("fund_holdings", "fetched_at"),
            "last_market_update": _max_value("market_stock_consensus", "fetched_at"),
            "ready": ready,
            "fund_master": fm,
            "security_master": security_n,
            "security_industry": security_industry,
        }
    )


def validate_local_data():
    h = health()
    checks = [
        {"id": "funds", "label": "基金基础资料", "status": "ready" if h["funds"] else "missing", "value": h["funds"]},
        {"id": "managers", "label": "基金经理", "status": "ready" if h["managers"] else "missing", "value": h["managers"]},
        {"id": "holdings", "label": "季度持仓", "status": "ready" if h["holdings"] else "missing", "value": h["holdings"]},
        {"id": "market", "label": "市场共识", "status": "ready" if h["market_consensus"] else "missing", "value": h["market_consensus"]},
        {
            "id": "allocation",
            "label": "行业与资产配置",
            "status": "ready" if (h["market_industry"] or h["asset_allocation"]) else "missing",
            "value": h["market_industry"] + h["asset_allocation"],
        },
    ]
    return clean_payload({"health": h, "checks": checks})



def fund_profile(code,mode='demo'):
    if mode=='demo':
        f=_fund_row(code,mode)
        if not f:return None
        return clean_payload({'fund_code':str(code),'fund_short_name':f.get('fund_name'),'fund_type':f.get('fund_type'),'fund_company':'示例基金管理人','manager_names':f.get('manager_name'),'source':'demo'})
    resolved=fund_master.resolve(str(code));rep=str(resolved.get('representative_code') or code)
    df=db.read_sql('SELECT * FROM fund_profiles WHERE fund_code=? LIMIT 1',(rep,))
    return None if df.empty else _records(df)[0]


def fund_major_changes(code,mode='demo',years=None):
    if mode=='demo':return []
    resolved=fund_master.resolve(str(code));rep=str(resolved.get('representative_code') or code)
    if years:
        years=[int(x) for x in years];marks=','.join(['?']*len(years))
        df=db.read_sql(f'SELECT * FROM fund_major_changes WHERE fund_code=? AND requested_year IN ({marks}) ORDER BY requested_year,quarter,direction,amount_wan DESC',tuple([rep]+years))
    else:
        df=db.read_sql('SELECT * FROM fund_major_changes WHERE fund_code=? ORDER BY requested_year,quarter,direction,amount_wan DESC',(rep,))
    return _records(df)
