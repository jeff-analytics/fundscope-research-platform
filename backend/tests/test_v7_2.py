import tempfile
from pathlib import Path
import pandas as pd
from app import services, fund_master, db


def test_period_order_is_chronological():
    values=['2026Q2','2008Q2','2021Q4','2018Q4','2024Q4']
    assert services.sort_periods(values)==['2008Q2','2018Q4','2021Q4','2024Q4','2026Q2']


def test_equity_research_filter_excludes_fixed_income():
    assert fund_master.eligible_equity('混合型-偏股','测试基金')[0] is True
    assert fund_master.eligible_equity('混合型-灵活','测试基金')[0] is True
    assert fund_master.eligible_equity('股票型','测试基金')[0] is True
    assert fund_master.eligible_equity('债券型-长债','测试基金')[0] is False
    assert fund_master.eligible_equity('货币型','测试基金')[0] is False
    assert fund_master.eligible_equity('同业存单指数','测试基金')[0] is False


def test_demo_research_funds_have_no_fixed_income_types():
    rows=services.funds('demo','',True)
    assert rows
    for r in rows:
        ok,_=fund_master.eligible_equity(r.get('fund_type'),r.get('fund_name'))
        assert ok


def test_local_research_picker_returns_only_equity_masters():
    tmp=tempfile.TemporaryDirectory();old=db.DB_PATH
    try:
        db.DB_PATH=Path(tmp.name)/"test.db";db.ensure_schema()
        df=pd.DataFrame([
            {"fund_code":"000001","fund_name":"成长混合A","fund_type":"混合型-偏股","base_name_candidate":"成长混合","share_class_candidate":"A","master_candidate_id":"x","fetched_at":"2026-08-24"},
            {"fund_code":"000002","fund_name":"成长混合C","fund_type":"混合型-偏股","base_name_candidate":"成长混合","share_class_candidate":"C","master_candidate_id":"x","fetched_at":"2026-08-24"},
            {"fund_code":"000003","fund_name":"纯债A","fund_type":"债券型-长债","base_name_candidate":"纯债","share_class_candidate":"A","master_candidate_id":"y","fetched_at":"2026-08-24"},
            {"fund_code":"000004","fund_name":"货币A","fund_type":"货币型","base_name_candidate":"货币","share_class_candidate":"A","master_candidate_id":"z","fetched_at":"2026-08-24"},
        ])
        db.upsert(df,"fund_share_classes",["fund_code"]);fund_master.build_fund_master()
        rows=services.funds("local","",True)
        assert len(rows)==1
        assert rows[0]["fund_code"]=="000001"
        assert "债" not in rows[0]["fund_type"] and "货币" not in rows[0]["fund_type"]
    finally:
        db.DB_PATH=old;tmp.cleanup()
