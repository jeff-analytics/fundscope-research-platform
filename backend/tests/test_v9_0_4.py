import tempfile
from pathlib import Path

import pandas as pd

from app import db, fund_master, services


def _setup_tmp():
    tmp = tempfile.TemporaryDirectory()
    old = db.DB_PATH
    db.DB_PATH = Path(tmp.name) / "fundscope.db"
    db.ensure_schema()
    return tmp, old


def _restore(tmp, old):
    db.DB_PATH = old
    tmp.cleanup()


def _seed_one_fund():
    funds = pd.DataFrame([["000001", "速度测试A", "混合型-偏股", "速度测试", "A", "x", "2026-08-26"]], columns=[
        "fund_code", "fund_name", "fund_type", "base_name_candidate", "share_class_candidate", "master_candidate_id", "fetched_at"
    ])
    db.upsert(funds, "fund_share_classes", ["fund_code"])
    fund_master.build_fund_master()
    holdings = pd.DataFrame([
        ["000001", 2026, "2026Q1", "300001", "测试证券一", 5.0, 100, 100, "季度报告", "top10", "2026-08-26"],
        ["000001", 2026, "2026Q2", "300001", "测试证券一", 6.0, 110, 120, "季度报告", "top10", "2026-08-26"],
    ], columns=["fund_code", "requested_year", "quarter", "stock_code", "stock_name", "weight_pct", "shares", "market_value_wan", "report_type", "disclosure_scope", "fetched_at"])
    db.upsert(holdings, "fund_holdings", ["fund_code", "quarter", "stock_code"])


def test_v904_schema_has_read_path_indexes():
    tmp, old = _setup_tmp()
    try:
        names = {r[1] for r in db.read_sql("PRAGMA index_list(fund_holdings)").itertuples(index=False, name=None)}
        assert "idx_holdings_quarter_stock_fund" in names
        assert "idx_holdings_fund_quarter_weight" in names
    finally:
        _restore(tmp, old)


def test_fund_detail_does_not_duplicate_full_history_payload():
    tmp, old = _setup_tmp()
    try:
        _seed_one_fund()
        out = services.fund_detail("000001", "local")
        assert out["periods"] == ["2026Q1", "2026Q2"]
        assert len(out["holdings"]) == 2
        assert "history" not in out
    finally:
        _restore(tmp, old)


def test_period_scoped_holdings_read_is_narrow_and_lightweight():
    tmp, old = _setup_tmp()
    try:
        _seed_one_fund()
        out = services.holdings_period("local", "000001", "2026Q2", enriched=False)
        assert out.quarter.tolist() == ["2026Q2"]
        assert "pe" not in out.columns
        assert "sector" in out.columns
    finally:
        _restore(tmp, old)
