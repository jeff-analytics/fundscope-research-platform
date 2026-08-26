import tempfile
from pathlib import Path
import pandas as pd
from app import db, fund_master, providers


def test_strict_research_pool_removes_bonds_and_passive():
    assert fund_master.eligible_equity('混合型-灵活','华夏成长混合')[0] is True
    assert fund_master.eligible_equity('混合型-偏股','主动成长A')[0] is True
    assert fund_master.eligible_equity('股票型','主动股票A')[0] is True
    assert fund_master.eligible_equity('债券型-混合二级','中海可转债债券A')[0] is False
    assert fund_master.eligible_equity('指数型-股票','沪深300指数A')[0] is False
    assert fund_master.eligible_equity('QDII','全球股票(QDII)人民币')[0] is True
    assert fund_master.eligible_equity('QDII','纳斯达克100ETF联接(QDII)A')[0] is False


def test_parse_inception_date():
    assert providers.parse_inception_date('2005年11月17日 / 13.37亿份')=='2005-11-17'
    assert providers.parse_inception_date('2020-02-01 / 10亿份')=='2020-02-01'
    assert providers.parse_inception_date('') is None


def test_report_scope_metadata():
    assert providers._report_meta('2026Q1')==('季度报告','top10')
    assert providers._report_meta('2026Q2')==('中期报告','full')
    assert providers._report_meta('2026Q4')==('年度报告','full')


def test_holdings_plan_fixed_range_uses_cache(monkeypatch):
    tmp=tempfile.TemporaryDirectory();old=db.DB_PATH
    try:
        db.DB_PATH=Path(tmp.name)/'test.db';db.ensure_schema()
        base=pd.DataFrame([{'fund_code':'000001','fund_name':'测试成长混合A','fund_type':'混合型-偏股','base_name_candidate':'测试成长混合','share_class_candidate':'A','master_candidate_id':'x','fetched_at':'2026-08-24'}])
        db.upsert(base,'fund_share_classes',['fund_code']);fund_master.build_fund_master()
        h=pd.DataFrame([['000001',2025,'2025Q1','600000','浦发银行',5,100,1000,'季度报告','top10','2025-04-30'],['000001',2025,'2025Q2','600000','浦发银行',5,100,1000,'中期报告','full','2025-07-31'],['000001',2025,'2025Q3','600000','浦发银行',5,100,1000,'季度报告','top10','2025-10-31'],['000001',2025,'2025Q4','600000','浦发银行',5,100,1000,'年度报告','full','2026-01-31']],columns=['fund_code','requested_year','quarter','stock_code','stock_name','weight_pct','shares','market_value_wan','report_type','disclosure_scope','fetched_at'])
        db.upsert(h,'fund_holdings',['fund_code','quarter','stock_code'])
        out=providers.holdings_plan_preview([2025],1,False,False,None)
        assert out['selected_masters']==1
        assert out['planned_year_requests']==0
        assert out['cached_years']==1
    finally:
        db.DB_PATH=old;tmp.cleanup()


def test_profile_caches_inception_date(monkeypatch):
    class FakeAk:
        @staticmethod
        def fund_overview_em(symbol):
            return pd.DataFrame([{'基金全称':'测试基金','基金简称':'测试基金A','基金类型':'混合型-偏股','成立日期/规模':'2012年03月15日 / 2亿份'}])
    tmp=tempfile.TemporaryDirectory();old=db.DB_PATH
    try:
        db.DB_PATH=Path(tmp.name)/'test.db';db.ensure_schema()
        base=pd.DataFrame([{'fund_code':'000001','fund_name':'测试基金A','fund_type':'混合型-偏股','base_name_candidate':'测试基金','share_class_candidate':'A','master_candidate_id':'x','fetched_at':'2026-08-24'}])
        db.upsert(base,'fund_share_classes',['fund_code']);fund_master.build_fund_master()
        monkeypatch.setattr(providers,'ak',lambda:FakeAk)
        providers.sync_fund_profile('000001')
        row=db.read_sql('SELECT inception_date FROM fund_profiles WHERE fund_code=?',('000001',))
        assert row.iloc[0]['inception_date']=='2012-03-15'
    finally:
        db.DB_PATH=old;tmp.cleanup()
