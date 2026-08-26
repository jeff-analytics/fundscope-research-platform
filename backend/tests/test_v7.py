import os
import pandas as pd
import numpy as np


def test_fund_master_dedup(tmp_path,monkeypatch):
    monkeypatch.setenv('FUNDSCOPE_DATA_DIR',str(tmp_path))
    from importlib import reload
    from app import db as dbmod,fund_master as fmmod
    reload(dbmod);reload(fmmod);dbmod.ensure_schema()
    df=pd.DataFrame([
      ['000001','测试成长混合A','混合型-偏股','', '', '', '2026-01-01'],
      ['000002','测试成长混合C','混合型-偏股','', '', '', '2026-01-01'],
      ['000003','测试货币A','货币型','', '', '', '2026-01-01'],
    ],columns=['fund_code','fund_name','fund_type','base_name_candidate','share_class_candidate','master_candidate_id','fetched_at'])
    dbmod.upsert(df,'fund_share_classes',['fund_code'])
    out=fmmod.build_fund_master();assert out['masters']==2;assert out['eligible']==1;assert out['saved_requests_estimate']==1
    rep=fmmod.eligible_representatives();assert len(rep)==1;assert rep.iloc[0].fund_code=='000001'


def test_style_and_migration_demo():
    from app import advanced
    a=advanced.fund_advanced('D00001','demo');assert a['latest_style']['size_score'] is not None;assert 'momentum_score' not in a['latest_style'];assert len(a['style_history'])>=2
    m=advanced.institutional_migration('demo');assert m['sankey']['basis']=='sector';assert len(m['sankey']['links'])>0


def test_return_gap_formula(tmp_path,monkeypatch):
    monkeypatch.setenv('FUNDSCOPE_DATA_DIR',str(tmp_path))
    from importlib import reload
    from app import db as dbmod,services as smod,advanced as amod,fund_master as fmmod
    reload(dbmod);reload(fmmod);reload(smod);reload(amod);dbmod.ensure_schema()
    funds=pd.DataFrame([['000001','测试成长混合A','混合型-偏股','','','','2026-01-01']],columns=['fund_code','fund_name','fund_type','base_name_candidate','share_class_candidate','master_candidate_id','fetched_at']);dbmod.upsert(funds,'fund_share_classes',['fund_code']);fmmod.build_fund_master()
    h=pd.DataFrame([
      ['000001',2025,'2025Q4','600000','浦发银行',80,100,1000,'2026-01-01'],
      ['000001',2026,'2026Q1','600000','浦发银行',80,100,1100,'2026-04-01'],
    ],columns=['fund_code','requested_year','quarter','stock_code','stock_name','weight_pct','shares','market_value_wan','fetched_at']);dbmod.upsert(h,'fund_holdings',['fund_code','quarter','stock_code'])
    nav=pd.DataFrame([['000001','2025-12-31',1.0,None,'x'],['000001','2026-03-31',1.1,None,'x']],columns=['fund_code','nav_date','unit_nav','daily_return_pct','updated_at']);dbmod.upsert(nav,'fund_nav',['fund_code','nav_date'])
    px=pd.DataFrame([['600000','2025-12-31',10,None,'x'],['600000','2026-03-31',11,None,'x']],columns=['security_code','trade_date','close_adj','return_pct','updated_at']);dbmod.upsert(px,'security_prices',['security_code','trade_date'])
    out=amod.fund_advanced('000001','local');assert out['return_gap'];row=out['return_gap'][-1];assert round(row['fund_return_pct'],1)==10.0;assert round(row['disclosed_contribution_pct'],1)==8.0;assert round(row['return_gap_pct'],1)==2.0

def test_equity_pool_is_strict_active_equity():
    from app import fund_master
    assert fund_master.eligible_equity('货币型','测试货币A')[0] is False
    assert fund_master.eligible_equity('债券型-长债','测试长债A')[0] is False
    assert fund_master.eligible_equity('债券型-混合二级','测试二级债A')[0] is False
    assert fund_master.eligible_equity('混合型-偏股','测试成长混合A')[0] is True
    assert fund_master.eligible_equity('指数型-股票','测试指数A')[0] is False
    assert fund_master.eligible_equity('指数型-联接','测试ETF联接A')[0] is False
