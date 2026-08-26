from pathlib import Path
import json
import os
import shutil
import sqlite3
import threading
import time
import random
from datetime import datetime
import pandas as pd

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("FUNDSCOPE_DATA_DIR", str(Path.home()/".fundscope"))).expanduser()
DB_PATH = DATA_DIR / "fundscope.db"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
LOG_PATH = DATA_DIR / "fundscope.log"

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA temp_store=MEMORY;
PRAGMA wal_autocheckpoint=2000;
PRAGMA journal_size_limit=67108864;

CREATE TABLE IF NOT EXISTS fund_share_classes (
 fund_code TEXT PRIMARY KEY,fund_name TEXT,fund_type TEXT,base_name_candidate TEXT,
 share_class_candidate TEXT,master_candidate_id TEXT,fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS fund_master (
 master_id TEXT PRIMARY KEY,master_name TEXT,fund_type TEXT,representative_code TEXT,
 eligible_equity INTEGER DEFAULT 0,exclusion_reason TEXT,share_count INTEGER DEFAULT 1,
 confidence REAL DEFAULT 1.0,updated_at TEXT
);
CREATE TABLE IF NOT EXISTS fund_master_members (
 fund_code TEXT PRIMARY KEY,master_id TEXT,share_class TEXT,is_representative INTEGER DEFAULT 0,
 updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_fund_master_members_master ON fund_master_members(master_id);

CREATE TABLE IF NOT EXISTS fund_managers (
 manager_name TEXT,company TEXT,current_fund_codes TEXT,current_funds TEXT,career_days REAL,
 current_aum_billion REAL,best_return_pct REAL,fetched_at TEXT,PRIMARY KEY(manager_name,company)
);
CREATE TABLE IF NOT EXISTS manager_tenure (
 manager_id TEXT,fund_code TEXT,start_date TEXT,end_date TEXT,source TEXT,updated_at TEXT,
 PRIMARY KEY(manager_id,fund_code,start_date)
);

CREATE TABLE IF NOT EXISTS fund_profiles (
 fund_code TEXT PRIMARY KEY,fund_full_name TEXT,fund_short_name TEXT,fund_type TEXT,issue_date TEXT,
 inception_info TEXT,asset_scale TEXT,share_scale TEXT,fund_company TEXT,custodian TEXT,manager_names TEXT,
 dividends TEXT,management_fee TEXT,custodian_fee TEXT,sales_service_fee TEXT,max_subscription_fee TEXT,
 benchmark TEXT,tracking_target TEXT,inception_date TEXT,source TEXT,updated_at TEXT
);

CREATE TABLE IF NOT EXISTS fund_major_changes (
 fund_code TEXT,requested_year INTEGER,quarter TEXT,direction TEXT,stock_code TEXT,stock_name TEXT,
 amount_wan REAL,initial_nav_pct REAL,fetched_at TEXT,
 PRIMARY KEY(fund_code,requested_year,quarter,direction,stock_code)
);
CREATE INDEX IF NOT EXISTS idx_major_changes_code_year ON fund_major_changes(fund_code,requested_year);

CREATE TABLE IF NOT EXISTS fund_holdings (
 fund_code TEXT,requested_year INTEGER,quarter TEXT,stock_code TEXT,stock_name TEXT,
 weight_pct REAL,shares REAL,market_value_wan REAL,report_type TEXT,disclosure_scope TEXT,fetched_at TEXT,
 PRIMARY KEY(fund_code,quarter,stock_code)
);
CREATE INDEX IF NOT EXISTS idx_holdings_code_quarter ON fund_holdings(fund_code,quarter);
CREATE INDEX IF NOT EXISTS idx_holdings_stock_quarter ON fund_holdings(stock_code,quarter);
CREATE INDEX IF NOT EXISTS idx_holdings_year_quarter ON fund_holdings(requested_year,quarter);
CREATE INDEX IF NOT EXISTS idx_holdings_quarter_fund ON fund_holdings(quarter,fund_code);
CREATE INDEX IF NOT EXISTS idx_holdings_quarter_stock_fund ON fund_holdings(quarter,stock_code,fund_code);
CREATE INDEX IF NOT EXISTS idx_holdings_fund_quarter_weight ON fund_holdings(fund_code,quarter,weight_pct DESC);
CREATE INDEX IF NOT EXISTS idx_master_eligible_rep ON fund_master(eligible_equity,representative_code);

CREATE TABLE IF NOT EXISTS security_master (
 security_code TEXT PRIMARY KEY,security_name TEXT,market TEXT,industry_l1 TEXT,industry_l2 TEXT,
 total_market_cap REAL,float_market_cap REAL,pe REAL,pb REAL,revenue_growth_yoy REAL,
 profit_growth_yoy REAL,listing_date TEXT,asof_date TEXT,source_quality TEXT,updated_at TEXT
);
CREATE TABLE IF NOT EXISTS security_prices (
 security_code TEXT,trade_date TEXT,close_adj REAL,return_pct REAL,updated_at TEXT,
 PRIMARY KEY(security_code,trade_date)
);
CREATE INDEX IF NOT EXISTS idx_security_prices_date ON security_prices(trade_date);
CREATE TABLE IF NOT EXISTS fund_nav (
 fund_code TEXT,nav_date TEXT,unit_nav REAL,daily_return_pct REAL,updated_at TEXT,
 PRIMARY KEY(fund_code,nav_date)
);
CREATE INDEX IF NOT EXISTS idx_fund_nav_date ON fund_nav(nav_date);

CREATE TABLE IF NOT EXISTS market_stock_consensus (
 report_date TEXT,stock_code TEXT,stock_name TEXT,fund_count INTEGER,shares REAL,
 market_value_wan REAL,fetched_at TEXT,PRIMARY KEY(report_date,stock_code)
);
CREATE INDEX IF NOT EXISTS idx_market_consensus_report ON market_stock_consensus(report_date);
CREATE TABLE IF NOT EXISTS market_industry_allocation (
 report_date TEXT,industry_code TEXT,industry_name TEXT,fund_count INTEGER,industry_scale_yi REAL,
 nav_weight_pct REAL,fetched_at TEXT,PRIMARY KEY(report_date,industry_code)
);
CREATE INDEX IF NOT EXISTS idx_market_industry_report ON market_industry_allocation(report_date);
CREATE TABLE IF NOT EXISTS market_asset_allocation (
 report_date TEXT PRIMARY KEY,fund_count REAL,equity_weight_pct REAL,fixed_income_weight_pct REAL,
 cash_weight_pct REAL,market_nav_yi REAL,fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS task_log (
 task TEXT,fund_code TEXT,requested_year INTEGER,subtask TEXT,status TEXT,rows_written INTEGER,
 attempts INTEGER,error_type TEXT,error TEXT,updated_at TEXT,
 PRIMARY KEY(task,fund_code,requested_year,subtask)
);
CREATE TABLE IF NOT EXISTS task_runs (
 task_id TEXT PRIMARY KEY,task_type TEXT,status TEXT,progress REAL,current INTEGER,total INTEGER,
 message TEXT,created_at TEXT,started_at TEXT,finished_at TEXT,result_json TEXT,error TEXT,
 cancel_requested INTEGER DEFAULT 0,pause_requested INTEGER DEFAULT 0,queue_position INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS research_collections (
 collection_id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at TEXT,updated_at TEXT
);
CREATE TABLE IF NOT EXISTS research_items (
 item_id TEXT PRIMARY KEY,collection_id TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,
 entity_name TEXT NOT NULL,note TEXT DEFAULT '',meta_json TEXT DEFAULT '{}',created_at TEXT,updated_at TEXT,
 UNIQUE(collection_id,entity_type,entity_id)
);
CREATE INDEX IF NOT EXISTS idx_research_items_collection ON research_items(collection_id,created_at);

CREATE TABLE IF NOT EXISTS saved_views (
 view_id TEXT PRIMARY KEY,view_type TEXT NOT NULL,name TEXT NOT NULL,config_json TEXT NOT NULL,
 created_at TEXT,updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_saved_views_type ON saved_views(view_type,updated_at);

CREATE TABLE IF NOT EXISTS research_recents (
 entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,entity_name TEXT NOT NULL,route TEXT,
 last_opened_at TEXT,open_count INTEGER DEFAULT 1,PRIMARY KEY(entity_type,entity_id)
);

CREATE TABLE IF NOT EXISTS monitor_rules (
 rule_id TEXT PRIMARY KEY,name TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,entity_name TEXT NOT NULL,
 metric TEXT NOT NULL,operator TEXT NOT NULL,threshold REAL NOT NULL,enabled INTEGER DEFAULT 1,
 created_at TEXT,updated_at TEXT,last_evaluated_period TEXT,last_value REAL,last_triggered_period TEXT
);
CREATE TABLE IF NOT EXISTS monitor_events (
 event_id TEXT PRIMARY KEY,rule_id TEXT NOT NULL,period TEXT,value REAL,threshold REAL,operator TEXT,
 entity_type TEXT,entity_id TEXT,entity_name TEXT,metric TEXT,created_at TEXT,seen INTEGER DEFAULT 0,
 UNIQUE(rule_id,period)
);
CREATE INDEX IF NOT EXISTS idx_monitor_events_created ON monitor_events(created_at);

CREATE TABLE IF NOT EXISTS audit_log (
 audit_id INTEGER PRIMARY KEY AUTOINCREMENT,action TEXT NOT NULL,entity_type TEXT,entity_id TEXT,
 detail_json TEXT DEFAULT '{}',created_at TEXT
);
"""


def _legacy_candidates():
    parent=PACKAGE_ROOT.parent
    patterns=["FundScope_Web_v*/backend/data/fundscope.db","FundScope_AllFunds_v*/data/fundscope.db","FundScope_Studio_v*/data/fundscope.db"]
    out=[]
    for pat in patterns: out.extend(parent.glob(pat))
    local=PACKAGE_ROOT/'backend'/'data'/'fundscope.db'
    if local.exists(): out.append(local)
    return [p for p in out if p.exists() and p.resolve()!=DB_PATH.resolve()]


def bootstrap_storage():
    DATA_DIR.mkdir(parents=True,exist_ok=True);SNAPSHOT_DIR.mkdir(parents=True,exist_ok=True)
    if DB_PATH.exists():return None
    candidates=_legacy_candidates()
    if not candidates:return None
    source=max(candidates,key=lambda p:(p.stat().st_size,p.stat().st_mtime))
    shutil.copy2(source,DB_PATH)
    return str(source)


_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY_FOR: str | None = None
_DATA_REVISION_LOCK = threading.Lock()
_DATA_REVISION = 0
_ANALYTIC_TABLES = {
    "fund_share_classes","fund_master","fund_master_members","fund_managers","manager_tenure",
    "fund_profiles","fund_major_changes","fund_holdings","security_master","security_prices","fund_nav",
    "market_stock_consensus","market_industry_allocation","market_asset_allocation"
}


def data_revision():
    return _DATA_REVISION


def _bump_data_revision(table=None):
    global _DATA_REVISION
    if table is not None and str(table) not in _ANALYTIC_TABLES:
        return _DATA_REVISION
    with _DATA_REVISION_LOCK:
        _DATA_REVISION += 1
        return _DATA_REVISION


def _db_key():
    try:return str(DB_PATH.expanduser().resolve())
    except Exception:return str(DB_PATH)


def _raw_connect():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(DB_PATH,timeout=45,check_same_thread=False)
    # Local analytics are read-heavy. These pragmas reduce lock sensitivity and
    # repeated disk paging without changing data semantics.
    conn.execute("PRAGMA busy_timeout=45000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-32768")
    try:conn.execute("PRAGMA mmap_size=268435456")
    except Exception:pass
    return conn


def _initialize_schema_once():
    global _SCHEMA_READY_FOR
    key=_db_key()
    if _SCHEMA_READY_FOR==key:return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY_FOR==key:return
        bootstrap_storage();DATA_DIR.mkdir(parents=True,exist_ok=True)
        conn=_raw_connect()
        try:
            conn.executescript(SCHEMA);conn.execute("PRAGMA optimize");conn.commit()
        finally:conn.close()
        _SCHEMA_READY_FOR=key


def connect():
    # DDL is intentionally not re-executed on every request. On large local databases,
    # repeating the full schema script for each read adds lock contention and latency.
    _initialize_schema_once()
    return _raw_connect()


def _ensure_column(conn,table,column,ddl):
    cols={r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def ensure_schema():
    _initialize_schema_once()
    with _raw_connect() as conn:
        _ensure_column(conn,'task_runs','queue_position','INTEGER DEFAULT 0')
        _ensure_column(conn,'task_runs','pause_requested','INTEGER DEFAULT 0')
        _ensure_column(conn,'fund_profiles','inception_date','TEXT')
        _ensure_column(conn,'fund_holdings','report_type','TEXT')
        _ensure_column(conn,'fund_holdings','disclosure_scope','TEXT')
        conn.execute("UPDATE task_runs SET status='interrupted',message='任务因应用重启中断',finished_at=? WHERE status IN ('queued','running','paused','cooling')",(datetime.now().isoformat(timespec='seconds'),))
        conn.commit()


def count(table):
    try:
        with connect() as conn:return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except Exception:return 0


def read_sql(query,params=(),retries=4):
    """Stable read helper for the local SQLite research store.

    Collection tasks write in WAL mode while research pages are reading. Short
    transient busy/locked windows are retried here so a tab does not fail merely
    because a batch commit happened at the same moment.
    """
    last=None
    attempts=max(1,int(retries))
    for i in range(attempts):
        conn=None
        try:
            conn=connect()
            conn.execute("PRAGMA query_only=ON")
            return pd.read_sql_query(query,conn,params=params)
        except (sqlite3.OperationalError,sqlite3.DatabaseError,OSError) as exc:
            last=exc
            msg=str(exc).lower()
            transient=any(x in msg for x in ("locked","busy","disk i/o","database is locked","interrupted","temporarily unavailable"))
            if (not transient) or i>=attempts-1:
                raise
            time.sleep((0.08*(2**i))+random.random()*0.05)
        finally:
            if conn is not None:
                try:conn.close()
                except Exception:pass
    if last:raise last
    return pd.DataFrame()


def read_table(table):return read_sql(f"SELECT * FROM {table}")


def upsert(df,table,keys,chunk_size=1000):
    if df is None or df.empty:return 0
    cols=list(df.columns);updates=','.join(f"{c}=excluded.{c}" for c in cols if c not in keys)
    sql=f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))}) ON CONFLICT({','.join(keys)}) DO UPDATE SET {updates}"
    clean=df.where(pd.notna(df),None);rows=clean.to_numpy(dtype=object).tolist()
    with connect() as conn:
        for i in range(0,len(rows),max(1,int(chunk_size))):conn.executemany(sql,rows[i:i+chunk_size])
        conn.commit()
    _bump_data_revision(table)
    return len(rows)


def execute_many(sql,rows,chunk_size=1000):
    if not rows:return 0
    with connect() as conn:
        for i in range(0,len(rows),chunk_size):conn.executemany(sql,rows[i:i+chunk_size])
        conn.commit()
    return len(rows)


def log_task(task,fund_code,year,subtask,status,rows=0,attempts=1,error_type='',error=''):
    log_tasks_bulk([(task,str(fund_code),int(year),str(subtask),status,int(rows),int(attempts),error_type,str(error)[:1200],datetime.now().isoformat(timespec='seconds'))])


def log_tasks_bulk(rows):
    sql="""INSERT INTO task_log(task,fund_code,requested_year,subtask,status,rows_written,attempts,error_type,error,updated_at)
    VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(task,fund_code,requested_year,subtask) DO UPDATE SET
    status=excluded.status,rows_written=excluded.rows_written,attempts=excluded.attempts,error_type=excluded.error_type,error=excluded.error,updated_at=excluded.updated_at"""
    return execute_many(sql,rows,500)


def existing_periods_for_codes(codes,year):
    codes=[str(x) for x in codes if x]
    if not codes:return set()
    marks=','.join(['?']*len(codes))
    df=read_sql(f"SELECT DISTINCT quarter FROM fund_holdings WHERE fund_code IN ({marks}) AND requested_year=?",tuple(codes)+ (int(year),))
    return set(df['quarter'].astype(str).tolist()) if not df.empty else set()


def create_task_run(task_id,task_type,queue_position=0):
    now=datetime.now().isoformat(timespec='seconds')
    with connect() as conn:
        conn.execute("INSERT INTO task_runs(task_id,task_type,status,progress,current,total,message,created_at,queue_position) VALUES(?,?,?,?,?,?,?,?,?)",(task_id,task_type,'queued',0,0,0,'等待',now,int(queue_position)));conn.commit()


def update_task_run(task_id,**fields):
    if not fields:return
    sets=','.join(f"{k}=?" for k in fields);vals=list(fields.values())+[task_id]
    with connect() as conn:conn.execute(f"UPDATE task_runs SET {sets} WHERE task_id=?",vals);conn.commit()


def get_task_run(task_id):
    df=read_sql("SELECT * FROM task_runs WHERE task_id=?",(task_id,))
    if df.empty:return None
    row=df.iloc[0].to_dict()
    if row.get('result_json'):
        try:row['result']=json.loads(row['result_json'])
        except Exception:row['result']=None
    else:row['result']=None
    return row


def list_task_runs(limit=30):
    df=read_sql("SELECT * FROM task_runs ORDER BY created_at DESC LIMIT ?",(int(limit),))
    if df.empty:return []
    return df.where(pd.notna(df),None).to_dict('records')


def request_cancel(task_id):
    update_task_run(task_id,cancel_requested=1,pause_requested=0,message='正在取消')


def request_pause(task_id):
    row=get_task_run(task_id)
    if not row:return False
    if row.get('status') not in ('running','cooling'):return False
    update_task_run(task_id,pause_requested=1,message='正在暂停')
    return True


def request_resume(task_id):
    row=get_task_run(task_id)
    if not row:return False
    update_task_run(task_id,pause_requested=0)
    if row.get('status')=='paused':
        update_task_run(task_id,status='running',message='继续中')
    return True


def is_cancel_requested(task_id):
    with connect() as conn:
        row=conn.execute("SELECT cancel_requested FROM task_runs WHERE task_id=?",(task_id,)).fetchone()
    return bool(row and row[0])


def is_pause_requested(task_id):
    with connect() as conn:
        row=conn.execute("SELECT pause_requested FROM task_runs WHERE task_id=?",(task_id,)).fetchone()
    return bool(row and row[0])


def import_legacy_db(path):
    mapping={'fund_share_classes':['fund_code'],'fund_managers':['manager_name','company'],'fund_holdings':['fund_code','quarter','stock_code'],
             'market_stock_consensus':['report_date','stock_code'],'market_industry_allocation':['report_date','industry_code'],'market_asset_allocation':['report_date'],
             'task_log':['task','fund_code','requested_year','subtask'],'fund_master':['master_id'],'fund_master_members':['fund_code'],
             'security_master':['security_code'],'security_prices':['security_code','trade_date'],'fund_nav':['fund_code','nav_date'],
             'fund_profiles':['fund_code'],'fund_major_changes':['fund_code','requested_year','quarter','direction','stock_code']}
    copied={}
    with sqlite3.connect(path) as source:
        existing={r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table,keys in mapping.items():
            if table not in existing:continue
            df=pd.read_sql_query(f"SELECT * FROM {table}",source);target=list(read_sql(f"SELECT * FROM {table} LIMIT 0").columns)
            for col in target:
                if col not in df.columns:df[col]=None
            copied[table]=upsert(df[target],table,keys)
    return copied


def create_snapshot():
    SNAPSHOT_DIR.mkdir(parents=True,exist_ok=True)
    if not DB_PATH.exists():return None
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S');target=SNAPSHOT_DIR/f"fundscope_{stamp}.db"
    with connect() as src,sqlite3.connect(target) as dst:src.backup(dst)
    return {'name':target.name,'created_at':datetime.fromtimestamp(target.stat().st_mtime).isoformat(timespec='seconds'),'size_mb':round(target.stat().st_size/1024/1024,2)}


def list_snapshots():
    SNAPSHOT_DIR.mkdir(parents=True,exist_ok=True);out=[]
    for p in sorted(SNAPSHOT_DIR.glob('fundscope_*.db'),key=lambda x:x.stat().st_mtime,reverse=True):out.append({'name':p.name,'created_at':datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds'),'size_mb':round(p.stat().st_size/1024/1024,2)})
    return out[:30]


def restore_snapshot(name):
    source=(SNAPSHOT_DIR/name).resolve()
    if source.parent!=SNAPSHOT_DIR.resolve() or not source.exists():raise FileNotFoundError(name)
    backup=create_snapshot();shutil.copy2(source,DB_PATH)
    global _SCHEMA_READY_FOR;_SCHEMA_READY_FOR=None;ensure_schema();_bump_data_revision()
    return {'restored':name,'backup_before_restore':backup}


def storage_info():
    DATA_DIR.mkdir(parents=True,exist_ok=True);SNAPSHOT_DIR.mkdir(parents=True,exist_ok=True)
    return {'data_dir':str(DATA_DIR),'db_path':str(DB_PATH),'snapshot_dir':str(SNAPSHOT_DIR),'db_exists':DB_PATH.exists(),'db_size_mb':round(DB_PATH.stat().st_size/1024/1024,2) if DB_PATH.exists() else 0,'log_path':str(LOG_PATH)}


def open_data_dir():
    import subprocess,sys
    DATA_DIR.mkdir(parents=True,exist_ok=True);path=str(DATA_DIR)
    if os.name=='nt':os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform=='darwin':subprocess.Popen(['open',path])
    else:subprocess.Popen(['xdg-open',path])
    return storage_info()
