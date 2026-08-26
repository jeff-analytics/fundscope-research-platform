import logging
import pandas as pd

logger=logging.getLogger("fundscope.quality")
from . import db,fund_master


def _scalar(sql,params=()):
    df=db.read_sql(sql,params);return 0 if df.empty else (df.iloc[0,0] or 0)

def _missing(table,column):
    return int(_scalar(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL OR TRIM(CAST({column} AS TEXT))=''"))

def _table_quality(table,label,fields):
    rows=db.count(table);missing=sum(_missing(table,c) for c in fields) if rows else 0;den=max(1,rows*len(fields));pct=round(missing/den*100,2)
    return {'table':table,'label':label,'rows':rows,'critical_fields':len(fields),'missing':missing,'missing_pct':pct,'completeness_pct':round(100-pct,2),'status':'good' if pct<1 else 'warn' if pct<5 else 'bad'}


def report():
    try:fund_master.ensure_master()
    except Exception as exc:logger.warning("fund_master_quality_refresh_failed error=%s",exc)
    tables=[
      _table_quality('fund_share_classes','基金基础资料',['fund_code','fund_name','fund_type']),
      _table_quality('fund_master','基金主体',['master_id','master_name','representative_code','eligible_equity']),
      _table_quality('fund_managers','基金经理',['manager_name','company']),
      _table_quality('fund_holdings','季度持仓',['fund_code','quarter','stock_code','stock_name','weight_pct']),
      _table_quality('security_master','证券主表',['security_code','security_name','market']),
      _table_quality('market_stock_consensus','市场共识',['report_date','stock_code','stock_name','fund_count']),
      _table_quality('market_industry_allocation','行业配置',['report_date','industry_name','nav_weight_pct']),
    ]
    task_status={};df=db.read_sql("SELECT status,COUNT(*) n FROM task_log GROUP BY status")
    for _,r in df.iterrows():task_status[str(r.status)]=int(r.n)
    errors=int(task_status.get('error',0));empty=int(task_status.get('empty',0));invalid_weight=int(_scalar("SELECT COUNT(*) FROM fund_holdings WHERE weight_pct IS NOT NULL AND (weight_pct<0 OR weight_pct>100)"));duplicate_like=int(_scalar("SELECT COUNT(*) FROM (SELECT fund_code,quarter,stock_code,COUNT(*) n FROM fund_holdings GROUP BY fund_code,quarter,stock_code HAVING n>1)"))
    fm=fund_master.stats();applicable=max(1,int(fm.get('eligible',0) or 0));covered_master=int(_scalar("""SELECT COUNT(DISTINCT mm.master_id) FROM fund_holdings h JOIN fund_master_members mm ON mm.fund_code=h.fund_code JOIN fund_master m ON m.master_id=mm.master_id WHERE m.eligible_equity=1"""));coverage=round(covered_master/applicable*100,2)
    years=db.read_sql("SELECT requested_year year,COUNT(DISTINCT fund_code) funds,COUNT(*) rows FROM fund_holdings WHERE requested_year IS NOT NULL GROUP BY requested_year ORDER BY requested_year DESC")
    recent_errors=db.read_sql("SELECT fund_code,requested_year,error_type,error,updated_at FROM task_log WHERE status='error' ORDER BY updated_at DESC LIMIT 50")
    total_cells=sum(max(1,x['rows']*x['critical_fields']) for x in tables);missing_cells=sum(x['missing'] for x in tables);score=max(0,100-(missing_cells/max(1,total_cells)*100)-min(20,errors*0.05)-min(10,invalid_weight*0.2))
    sec_total=db.count('security_master');sec_industry=int(_scalar("SELECT COUNT(*) FROM security_master WHERE industry_l1 IS NOT NULL AND industry_l1<>''"));sec_marketcap=int(_scalar("SELECT COUNT(*) FROM security_master WHERE total_market_cap IS NOT NULL OR float_market_cap IS NOT NULL"));sec_valuation=int(_scalar("SELECT COUNT(*) FROM security_master WHERE pe IS NOT NULL OR pb IS NOT NULL"));sec_growth=int(_scalar("SELECT COUNT(*) FROM security_master WHERE revenue_growth_yoy IS NOT NULL OR profit_growth_yoy IS NOT NULL"))
    empty_classification={
      'normal_not_applicable':int(task_status.get('not_applicable',0)),
      'source_empty':empty,
      'error':errors,
    }
    return {
      'score':round(score,2),'coverage_pct':coverage,'covered_funds':covered_master,'applicable_funds':applicable,'errors':errors,'empty':empty,'invalid_weight':invalid_weight,'duplicate_keys':duplicate_like,
      'task_status':task_status,'tables':tables,'years':years.where(pd.notna(years),None).to_dict('records'),'recent_errors':recent_errors.where(pd.notna(recent_errors),None).to_dict('records'),
      'fund_master':fm,'security':{'total':sec_total,'industry':sec_industry,'industry_pct':round(sec_industry/max(1,sec_total)*100,2),'market_cap':sec_marketcap,'market_cap_pct':round(sec_marketcap/max(1,sec_total)*100,2),'valuation':sec_valuation,'valuation_pct':round(sec_valuation/max(1,sec_total)*100,2),'growth':sec_growth,'growth_pct':round(sec_growth/max(1,sec_total)*100,2)},'empty_classification':empty_classification
    }
