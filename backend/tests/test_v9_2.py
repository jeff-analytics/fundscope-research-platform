import pandas as pd
from app import disclosure, fund_master, services, consensus


def test_disclosure_pair_normalizes_mixed_scope_to_top10():
    old=pd.DataFrame({"quarter":["2026Q1"]*10,"stock_code":[str(i) for i in range(10)],"weight_pct":range(10,0,-1),"disclosure_scope":["top10"]*10})
    new=pd.DataFrame({"quarter":["2026Q2"]*15,"stock_code":[str(i) for i in range(15)],"weight_pct":range(15,0,-1),"disclosure_scope":["full"]*15})
    a,b,meta=disclosure.comparable_pair(old,new,"2026Q1","2026Q2")
    assert meta["basis"]=="top10_comparable"
    assert len(a)==10 and len(b)==10


def test_full_scope_pair_keeps_full_portfolio():
    a=pd.DataFrame({"quarter":["2025Q4"]*12,"stock_code":[str(i) for i in range(12)],"weight_pct":[1]*12,"disclosure_scope":["full"]*12})
    b=a.assign(quarter="2026Q2")
    x,y,meta=disclosure.comparable_pair(a,b,"2025Q4","2026Q2")
    assert meta["basis"]=="full_portfolio" and len(x)==12 and len(y)==12


def test_share_class_parser_handles_numbered_y_currency_and_fee_classes():
    assert fund_master.split_share_class("测试成长混合A1")[:2]==("测试成长混合","A1")
    assert fund_master.split_share_class("测试成长混合Y")[:2]==("测试成长混合","Y")
    assert fund_master.split_share_class("测试成长混合A(后端)")[:2]==("测试成长混合","A_BACKEND")
    assert fund_master.split_share_class("测试全球股票人民币A")[:2]==("测试全球股票人民币","A")
    assert fund_master.split_share_class("测试全球股票美元C")[:2]==("测试全球股票美元","C")


def test_demo_consensus_exposes_cohort_rates_and_level_trend():
    out=consensus.smart_money("demo","2025Q4","2025Q2")
    assert out["data_context"]["basis"]=="top10_comparable"
    assert out["data_context"]["sample_funds"]>0
    assert out["lifecycle"]
    row=out["lifecycle"][0]
    assert "coverage_rate_pct" in row and "coverage_delta_pp" in row
    assert row["consensus_level"] in {"高","中","低"}
    assert row["consensus_trend"] in {"新形成","增强","持续增强","稳定","弱化","退潮"}
    # 2025Q2 -> 2025Q4 is two quarters; acceleration is only valid against an equal-length prior interval.
    assert out["comparison_gap_quarters"]==2


def test_services_smart_money_compatibility_entrypoint():
    out=services.smart_money("demo","2026Q2","2026Q1")
    assert out["selected_period"]=="2026Q2"
    assert out["compare_period"]=="2026Q1"


def test_progressive_consensus_keeps_demo_exact():
    out=consensus.smart_money_progressive("demo","2026Q2","2026Q1",wait_seconds=.2)
    assert out["selected_period"]=="2026Q2"
    assert out["data_context"]["basis"]=="top10_comparable"

