import tempfile
from pathlib import Path

import pandas as pd

from app import db, explorer, fund_master


def _setup_tmp():
    tmp = tempfile.TemporaryDirectory()
    old = db.DB_PATH
    db.DB_PATH = Path(tmp.name) / "fundscope.db"
    db.ensure_schema()
    explorer._CACHE.clear()
    return tmp, old


def _restore(tmp, old):
    explorer._CACHE.clear()
    db.DB_PATH = old
    tmp.cleanup()


def _seed_funds():
    funds = pd.DataFrame([
        {"fund_code":"000001","fund_name":"探索成长A","fund_type":"混合型-偏股","base_name_candidate":"探索成长","share_class_candidate":"A","master_candidate_id":"x","fetched_at":"2026-08-25"},
        {"fund_code":"000002","fund_name":"探索成长C","fund_type":"混合型-偏股","base_name_candidate":"探索成长","share_class_candidate":"C","master_candidate_id":"x","fetched_at":"2026-08-25"},
        {"fund_code":"000003","fund_name":"均衡价值A","fund_type":"混合型-偏股","base_name_candidate":"均衡价值","share_class_candidate":"A","master_candidate_id":"y","fetched_at":"2026-08-25"},
        {"fund_code":"000004","fund_name":"制造精选A","fund_type":"股票型","base_name_candidate":"制造精选","share_class_candidate":"A","master_candidate_id":"z","fetched_at":"2026-08-25"},
        {"fund_code":"000005","fund_name":"测试纯债A","fund_type":"债券型-长债","base_name_candidate":"测试纯债","share_class_candidate":"A","master_candidate_id":"b","fetched_at":"2026-08-25"},
    ])
    db.upsert(funds,"fund_share_classes",["fund_code"])
    fund_master.build_fund_master()


def _seed_holdings():
    rows=[]
    # A/C share classes intentionally carry duplicate disclosures; explorer must count the master once.
    portfolios={
        "000001":{
            "2025Q4":[("300308","中际旭创",4.0),("300750","宁德时代",5.0),("600519","贵州茅台",6.0)],
            "2026Q1":[("300308","中际旭创",7.0),("300750","宁德时代",3.0),("688041","海光信息",5.0)],
            "2026Q2":[("300308","中际旭创",9.0),("688041","海光信息",7.0),("300502","新易盛",5.0)],
        },
        "000002":{
            "2025Q4":[("300308","中际旭创",4.0),("300750","宁德时代",5.0),("600519","贵州茅台",6.0)],
            "2026Q1":[("300308","中际旭创",7.0),("300750","宁德时代",3.0),("688041","海光信息",5.0)],
            "2026Q2":[("300308","中际旭创",9.0),("688041","海光信息",7.0),("300502","新易盛",5.0)],
        },
        "000003":{
            "2025Q4":[("600036","招商银行",7.0),("600519","贵州茅台",5.0),("300750","宁德时代",3.0)],
            "2026Q1":[("600036","招商银行",7.0),("600519","贵州茅台",5.0),("300308","中际旭创",2.0)],
            "2026Q2":[("600036","招商银行",6.0),("600519","贵州茅台",4.0),("300308","中际旭创",4.0)],
        },
        "000004":{
            "2025Q4":[("300750","宁德时代",6.0),("300124","汇川技术",5.0),("300308","中际旭创",2.0)],
            "2026Q1":[("300750","宁德时代",5.0),("300124","汇川技术",5.0),("300308","中际旭创",3.0)],
            "2026Q2":[("688041","海光信息",4.0),("300124","汇川技术",4.0),("300308","中际旭创",5.0)],
        },
        "000005":{
            "2026Q2":[("019547","测试债券",80.0)]
        }
    }
    for code, periods in portfolios.items():
        for q, items in periods.items():
            year=int(q[:4])
            for sc,name,w in items:
                rows.append([code,year,q,sc,name,w,1000,1000,"季度报告","top10","2026-08-25"])
    df=pd.DataFrame(rows,columns=["fund_code","requested_year","quarter","stock_code","stock_name","weight_pct","shares","market_value_wan","report_type","disclosure_scope","fetched_at"])
    db.upsert(df,"fund_holdings",["fund_code","quarter","stock_code"])
    sm=pd.DataFrame([
        ["300308","中际旭创","CN","通信","",1000,900,30,4,25,30,"","2026-08-25","test","2026-08-25"],
        ["300750","宁德时代","CN","电力设备","",8000,7000,22,5,15,12,"","2026-08-25","test","2026-08-25"],
        ["600519","贵州茅台","CN","食品饮料","",20000,19000,20,7,8,9,"","2026-08-25","test","2026-08-25"],
        ["688041","海光信息","CN","电子","",1800,1500,45,8,35,40,"","2026-08-25","test","2026-08-25"],
        ["300502","新易盛","CN","通信","",1200,1000,28,6,30,32,"","2026-08-25","test","2026-08-25"],
        ["600036","招商银行","CN","银行","",10000,9000,6,1,5,6,"","2026-08-25","test","2026-08-25"],
        ["300124","汇川技术","CN","机械设备","",2500,2200,25,5,20,18,"","2026-08-25","test","2026-08-25"],
    ],columns=["security_code","security_name","market","industry_l1","industry_l2","total_market_cap","float_market_cap","pe","pb","revenue_growth_yoy","profit_growth_yoy","listing_date","asof_date","source_quality","updated_at"])
    db.upsert(sm,"security_master",["security_code"])
    explorer._CACHE.clear()


def test_explorer_canonical_holdings_dedupes_share_classes_and_excludes_bonds():
    tmp,old=_setup_tmp()
    try:
        _seed_funds();_seed_holdings()
        h=explorer._canonical_holdings("local")
        q=h[h.quarter=="2026Q2"]
        # Three eligible masters, even though 探索成长 has both A and C disclosures.
        assert q.master_id.nunique()==3
        assert set(q.fund_code.astype(str)).issubset({"000001","000003","000004"})
        assert "测试债券" not in " ".join(q.stock_name.astype(str))
    finally:_restore(tmp,old)


def test_fund_explorer_returns_real_cross_section_metrics():
    tmp,old=_setup_tmp()
    try:
        _seed_funds();_seed_holdings()
        out=explorer.fund_explorer("local","2026Q2")
        assert out["selected_period"]=="2026Q2"
        assert len(out["rows"])==3
        row=next(x for x in out["rows"] if x["fund_code"]=="000001")
        assert row["history_periods"]==3
        assert row["turnover_pct"] is not None
        assert row["top10_concentration"]==21.0
        assert row["top_sector"]=="通信"
        assert isinstance(row["tags"],list)
    finally:_restore(tmp,old)


def test_security_explorer_detects_breadth_change_without_duplicate_share_inflation():
    tmp,old=_setup_tmp()
    try:
        _seed_funds();_seed_holdings()
        out=explorer.security_explorer("local","2026Q2")
        row=next(x for x in out["rows"] if x["stock_code"]=="300308")
        # Held by all three Fund Masters in Q2. A/C does not count twice.
        assert row["breadth_cur"]==3
        assert row["breadth_prev"]==3
        assert "breadth_acceleration" in row
        assert row["state"] in {"新共识","持续增强","高共识","高位退潮","共识减弱","退出观察","稳定"}
    finally:_restore(tmp,old)


def test_fund_peers_are_weighted_and_clickable_by_representative_code():
    tmp,old=_setup_tmp()
    try:
        _seed_funds();_seed_holdings()
        out=explorer.fund_peers("000001","local","2026Q2",10)
        assert out["period"]=="2026Q2"
        assert out["peers"]
        top=out["peers"][0]
        assert top["fund_code"] in {"000003","000004"}
        assert top["common_count"]>=2
        assert 0<=top["similarity_pct"]<=100
        assert top["weighted_overlap_pct"]>=0
    finally:_restore(tmp,old)


def test_rank_trajectory_is_chronological_and_has_latest_holdings():
    tmp,old=_setup_tmp()
    try:
        _seed_funds();_seed_holdings()
        out=explorer.fund_rank_trajectory("000001","local",8,12)
        assert out["periods"]==["2025Q4","2026Q1","2026Q2"]
        assert out["series"]
        latest=[s for s in out["series"] if s["points"][-1]["rank"] is not None]
        assert latest
        assert all(p["period"] in out["periods"] for s in out["series"] for p in s["points"])
    finally:_restore(tmp,old)


def test_local_peer_lens_uses_selected_quarter_and_returns_neighbors():
    tmp,old=_setup_tmp()
    try:
        _seed_funds();_seed_holdings()
        out=explorer.fund_peer_lens("000001","local","2026Q2","all")
        assert out["period"]=="2026Q2"
        assert out["fund"]["fund_code"]=="000001"
        assert out["metrics"]
        assert any(x["key"]=="top10_concentration" for x in out["metrics"])
        assert out["peers"]
        assert all(x["fund_code"]!="000001" for x in out["peers"])
    finally:_restore(tmp,old)


def test_local_peer_lens_switches_with_quarter():
    tmp,old=_setup_tmp()
    try:
        _seed_funds();_seed_holdings()
        q1=explorer.fund_peer_lens("000001","local","2026Q1","all")
        q2=explorer.fund_peer_lens("000001","local","2026Q2","all")
        m1=next(x for x in q1["metrics"] if x["key"]=="top10_concentration")
        m2=next(x for x in q2["metrics"] if x["key"]=="top10_concentration")
        assert q1["period"]=="2026Q1" and q2["period"]=="2026Q2"
        assert m1["value"]!=m2["value"]
    finally:_restore(tmp,old)
