from app import fund_master


def test_front_back_fee_variants_are_same_master_name():
    a=fund_master.split_share_class('华夏成长混合')
    b=fund_master.split_share_class('华夏成长混合(后端)')
    assert a[0]==b[0]=='华夏成长混合'
    assert 'BACKEND' in b[1]


def test_a_back_end_variant_merges_with_a_share():
    a=fund_master.split_share_class('华夏大盘精选混合A')
    b=fund_master.split_share_class('华夏大盘精选混合A(后端)')
    assert a[0]==b[0]=='华夏大盘精选混合'
    assert a[1]=='A'
    assert b[1]=='A_BACKEND'


def test_representative_prefers_front_regular_share():
    items=[('A_BACKEND','000002'),('A','000001'),('C','000003')]
    assert min(items,key=lambda x:fund_master._rep_priority(x[0],x[1]))==('A','000001')

import tempfile
from pathlib import Path
import pandas as pd
from app import db, providers, services


def test_eastmoney_profile_cache_via_akshare(monkeypatch):
    class FakeAk:
        @staticmethod
        def fund_overview_em(symbol):
            return pd.DataFrame([{
                '基金全称':'测试成长证券投资基金','基金简称':'测试成长A','基金类型':'混合型-偏股','发行日期':'2020年01月01日',
                '成立日期/规模':'2020年02月01日 / 10亿份','资产规模':'25.5亿元','份额规模':'12亿份','基金管理人':'测试基金',
                '基金托管人':'测试银行','基金经理人':'张三','成立来分红':'2次','管理费率':'1.2%','托管费率':'0.2%',
                '销售服务费率':'0%','最高认购费率':'1.2%','业绩比较基准':'沪深300收益率*80%','跟踪标的':'无'
            }])
    tmp=tempfile.TemporaryDirectory();old=db.DB_PATH
    try:
        db.DB_PATH=Path(tmp.name)/'test.db';db.ensure_schema()
        base=pd.DataFrame([{'fund_code':'000001','fund_name':'测试成长A','fund_type':'混合型-偏股','base_name_candidate':'测试成长','share_class_candidate':'A','master_candidate_id':'x','fetched_at':'2026-08-24'}])
        db.upsert(base,'fund_share_classes',['fund_code']);fund_master.build_fund_master()
        monkeypatch.setattr(providers,'ak',lambda:FakeAk)
        out=providers.sync_fund_profile('000001')
        assert out['rows']==1
        prof=services.fund_profile('000001','local')
        assert prof['fund_company']=='测试基金'
        assert prof['manager_names']=='张三'
    finally:
        db.DB_PATH=old;tmp.cleanup()


def test_major_changes_cache_via_akshare(monkeypatch):
    class FakeAk:
        @staticmethod
        def fund_portfolio_change_em(symbol,indicator,date):
            amount_col='本期累计买入金额' if indicator=='累计买入' else '本期累计卖出金额'
            return pd.DataFrame([{'股票代码':'600000','股票名称':'测试股份',amount_col:1234.5,'占期初基金资产净值比例':2.1,'季度':f'{date}年2季度'}])
    tmp=tempfile.TemporaryDirectory();old=db.DB_PATH
    try:
        db.DB_PATH=Path(tmp.name)/'test.db';db.ensure_schema()
        base=pd.DataFrame([{'fund_code':'000001','fund_name':'测试成长A','fund_type':'混合型-偏股','base_name_candidate':'测试成长','share_class_candidate':'A','master_candidate_id':'x','fetched_at':'2026-08-24'}])
        db.upsert(base,'fund_share_classes',['fund_code']);fund_master.build_fund_master()
        monkeypatch.setattr(providers,'ak',lambda:FakeAk)
        out=providers.sync_fund_major_changes('000001',[2026])
        assert out['rows']==2
        rows=services.fund_major_changes('000001','local',[2026])
        assert {r['direction'] for r in rows}=={'buy','sell'}
        assert rows[0]['quarter']=='2026Q2'
    finally:
        db.DB_PATH=old;tmp.cleanup()
