import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from app import db, services


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.ensure_schema()

    def tearDown(self):
        db.DB_PATH = self.original
        self.tmp.cleanup()

    def seed(self):
        db.upsert(pd.DataFrame([{
            "fund_code":"000001","fund_name":"测试基金A","fund_type":"混合型",
            "base_name_candidate":"测试基金","share_class_candidate":"A","master_candidate_id":"m1",
            "fetched_at":"2026-08-24T12:00:00"
        }]),"fund_share_classes",["fund_code"])
        db.upsert(pd.DataFrame([{
            "manager_name":"张三","company":"测试公司","current_fund_codes":"000001","current_funds":"测试基金A",
            "career_days":1000.0,"current_aum_billion":12.3,"best_return_pct":np.nan,
            "fetched_at":"2026-08-24T12:00:00"
        }]),"fund_managers",["manager_name","company"])
        db.upsert(pd.DataFrame([
            {"fund_code":"000001","requested_year":2025,"quarter":"2025年4季度","stock_code":"600000","stock_name":"浦发银行","weight_pct":4.0,"shares":np.nan,"market_value_wan":1000,"fetched_at":"2026-08-24T12:00:00"},
            {"fund_code":"000001","requested_year":2026,"quarter":"2026年2季度","stock_code":"600000","stock_name":"浦发银行","weight_pct":5.2,"shares":np.nan,"market_value_wan":1000,"fetched_at":"2026-08-24T12:00:00"},
        ]),"fund_holdings",["fund_code","quarter","stock_code"])
        db.upsert(pd.DataFrame([
            {"report_date":"2025-12-31","stock_code":"600000","stock_name":"浦发银行","fund_count":100,"shares":np.nan,"market_value_wan":50000,"fetched_at":"2026-08-24T12:00:00"},
            {"report_date":"2026-06-30","stock_code":"600000","stock_name":"浦发银行","fund_count":120,"shares":np.nan,"market_value_wan":54000,"fetched_at":"2026-08-24T12:00:00"},
        ]),"market_stock_consensus",["report_date","stock_code"])

    def test_period_normalization(self):
        self.assertEqual(services.normalize_period("2026-06-30"), "2026Q2")
        self.assertEqual(services.normalize_period("2026年3季度"), "2026Q3")
        self.assertEqual(services.sort_periods(["2026-06-30","2025-12-31","2026-03-31"]), ["2025Q4","2026Q1","2026Q2"])

    def test_local_payload_is_strict_json(self):
        self.seed()
        for payload in [
            services.overview("local"),
            services.fund_detail("000001","local"),
            services.manager_detail("张三","local"),
            services.smart_money("local"),
            services.health(),
            services.validate_local_data(),
        ]:
            json.dumps(payload, ensure_ascii=False, allow_nan=False)


    def test_asset_history_returns_all_collected_quarters(self):
        rows=[]
        year=2022
        for i in range(16):
            y=year+i//4;q=i%4+1
            rows.append({
                "report_date":f"{y}Q{q}","fund_count":100,"equity_weight_pct":60+i/10,
                "fixed_income_weight_pct":30,"cash_weight_pct":10-i/10,"market_nav_yi":1000,
                "fetched_at":"2026-08-26T12:00:00"
            })
        db.upsert(pd.DataFrame(rows),"market_asset_allocation",["report_date"])
        out=services.assets("local")
        self.assertEqual(len(out),16)
        self.assertEqual(out.iloc[0]["quarter"],"2022Q1")
        self.assertEqual(out.iloc[-1]["quarter"],"2025Q4")


if __name__ == "__main__":
    unittest.main()
