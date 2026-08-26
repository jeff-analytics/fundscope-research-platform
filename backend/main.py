import logging
from pathlib import Path
import tempfile,traceback,uuid,os,time
from fastapi import FastAPI,Query,UploadFile,File,HTTPException,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field
from app import db,services,providers,tasks,quality,advanced,security,fund_master,collection_policy,explorer,workspace,audit,consensus

db.ensure_schema();logging.basicConfig(filename=db.LOG_PATH,level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
app=FastAPI(title='FundScope 接口服务',version='9.2.2')
APP_ROLE=os.environ.get('FUNDSCOPE_ROLE','maintainer').strip().lower()
if APP_ROLE not in {'analyst','maintainer'}:APP_ROLE='maintainer'
def require_maintainer():
    if APP_ROLE!='maintainer':raise HTTPException(403,detail={'code':'forbidden','message':'当前以研究员角色运行，数据维护操作已锁定'})
app.add_middleware(GZipMiddleware,minimum_size=1024,compresslevel=5)
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:5173','http://localhost:5173'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
@app.middleware('http')
async def request_timing(request:Request,call_next):
    started=time.perf_counter()
    try:
        resp=await call_next(request)
        elapsed=time.perf_counter()-started
        resp.headers['Server-Timing']=f'app;dur={elapsed*1000:.1f}'
        if elapsed>=2.0:logging.warning('slow_request path=%s elapsed=%.3fs',request.url.path,elapsed)
        return resp
    except Exception:
        elapsed=time.perf_counter()-started
        if elapsed>=2.0:logging.warning('slow_request_failed path=%s elapsed=%.3fs',request.url.path,elapsed)
        raise

def response(data,status_code=200):return JSONResponse(content=services.clean_payload(data),status_code=status_code)
@app.exception_handler(Exception)
async def unhandled(request:Request,exc:Exception):
    eid=uuid.uuid4().hex[:8];logging.error('error_id=%s path=%s\n%s',eid,request.url.path,traceback.format_exc())
    return response({'detail':{'code':'server_error','message':'数据服务暂时无法完成该请求','error_id':eid}},500)

@app.get('/api/health')
def health():
    # Lightweight process-readiness endpoint. Do not query the research database here:
    # large local databases can make full data-health checks take several seconds and
    # should never block the Windows launcher from recognizing a live API process.
    return response({
        'ok': True,
        'app': 'FundScope',
        'version': app.version,
        'service': 'api',
        'role': APP_ROLE,
    })
@app.get('/api/overview')
def overview(mode:str=Query('demo',pattern='^(demo|local)$')):return response(services.overview(mode))
@app.get('/api/funds')
def funds(mode:str='demo',q:str='',research_only:bool=True):return response(services.funds(mode,q,research_only))
@app.get('/api/funds/{code}')
def fund(code:str,mode:str='demo'):
    out=services.fund_detail(code,mode)
    if out is None:raise HTTPException(404,'未找到该基金')
    return response(out)

@app.get('/api/funds/{code}/advanced')
def fund_advanced(code:str,mode:str='demo'):
    return response(advanced.fund_advanced(code,mode))

@app.get('/api/funds/{code}/profile')
def fund_profile(code:str,mode:str='demo',refresh:bool=False):
    if mode=='demo':return response(services.fund_profile(code,mode))
    cached=services.fund_profile(code,mode)
    # Normal research navigation is cache-first. External provider access is explicit
    # so opening a fund never stalls on a remote profile request.
    if refresh:
        try:providers.sync_fund_profile(code)
        except Exception as exc:logging.warning('fund_profile_refresh_failed code=%s error=%s',code,exc)
        cached=services.fund_profile(code,mode)
    return response(cached or {})

@app.get('/api/funds/{code}/major-changes')
def major_changes(code:str,mode:str='demo',years:str=''):
    ys=[int(x) for x in years.split(',') if x.strip().isdigit()] if years else None
    return response(services.fund_major_changes(code,mode,ys))

@app.get('/api/managers')
def managers(mode:str='demo',q:str=''):return response(services.managers(mode,q))
@app.get('/api/managers/catalog')
def manager_catalog(mode:str='demo'):return response(services.manager_catalog(mode))
@app.get('/api/managers/id/{mid}')
def manager_id_detail(mid:str,mode:str='demo'):
    out=services.manager_by_id(mid,mode)
    if out is None:raise HTTPException(404,'未找到该基金经理')
    return response(out)
@app.get('/api/managers/{name}')
def manager(name:str,mode:str='demo'):
    out=services.manager_detail(name,mode)
    if out is None:raise HTTPException(404,'未找到该基金经理')
    return response(out)

@app.get('/api/managers/{name}/style')
def manager_style(name:str,mode:str='demo',company:str|None=None):
    out=advanced.manager_style_timeline(name,mode,company)
    if out is None:raise HTTPException(404,'未找到该基金经理')
    return response(out)

@app.get('/api/institutional-migration')
def institutional_migration(mode:str='demo'):
    return response(advanced.institutional_migration(mode))

@app.get('/api/smart-money')
def smart(mode:str='demo',period:str='',compare_period:str=''):
    return response(consensus.smart_money_progressive(mode,period or None,compare_period or None))

@app.get('/api/smart-money/history')
def smart_history(mode:str='demo',period:str='',codes:str='',window:int=8):
    selected_codes=[x.strip() for x in codes.split(',') if x.strip()][:12]
    return response(consensus.smart_money_history(mode,period or None,selected_codes,max(2,min(window,20))))
@app.get('/api/compare')
def compare(a:str,b:str,quarter:str,mode:str='demo'):return response(services.compare_funds(a,b,quarter,mode))


@app.get('/api/explorer/funds')
def explorer_funds(mode:str='demo',period:str=''):
    return response(explorer.fund_explorer(mode,period or None))

@app.get('/api/explorer/securities')
def explorer_securities(mode:str='demo',period:str=''):
    return response(explorer.security_explorer(mode,period or None))

@app.get('/api/explorer/securities/{code}')
def explorer_security_detail(code:str,mode:str='demo',period:str=''):
    out=explorer.security_detail(code,mode,period or None)
    if out is None:raise HTTPException(404,'未找到该证券的基金持仓记录')
    return response(out)

@app.get('/api/funds/{code}/peers')
def explorer_fund_peers(code:str,mode:str='demo',quarter:str='',limit:int=15):
    return response(explorer.fund_peers(code,mode,quarter or None,limit))

@app.get('/api/funds/{code}/rank-trajectory')
def explorer_fund_rank_trajectory(code:str,mode:str='demo',max_names:int=8,max_periods:int=12):
    return response(explorer.fund_rank_trajectory(code,mode,max_names,max_periods))


@app.get('/api/session')
def session_info():return response({'role':APP_ROLE,'capabilities':{'research':True,'maintenance':APP_ROLE=='maintainer'}})

@app.get('/api/explorer/managers')
def explorer_managers(mode:str='demo',period:str=''):
    return response(explorer.manager_explorer(mode,period or None))

@app.get('/api/funds/{code}/peer-lens')
def explorer_fund_peer_lens(code:str,mode:str='demo',period:str='',universe:str='all'):
    if universe not in {'all','type','style'}:universe='all'
    return response(explorer.fund_peer_lens(code,mode,period or None,universe))

@app.get('/api/search')
def global_search(mode:str='demo',q:str='',limit:int=8):return response(workspace.global_search(mode,q,limit))

@app.get('/api/workspace')
def workspace_overview():return response(workspace.overview())
@app.get('/api/workspace/collections')
def workspace_collections():return response(workspace.list_collections())
class CollectionCreate(BaseModel):name:str
class CollectionRename(BaseModel):name:str
class ResearchItemBody(BaseModel):entity_type:str;entity_id:str;entity_name:str;note:str='';meta:dict=Field(default_factory=dict)
class ResearchItemUpdate(BaseModel):note:str|None=None;collection_id:str|None=None
class RecentBody(BaseModel):entity_type:str;entity_id:str;entity_name:str;route:str=''
class SavedViewBody(BaseModel):view_type:str;name:str;config:dict;view_id:str|None=None
class MonitorCreate(BaseModel):name:str;entity_type:str;entity_id:str;entity_name:str;metric:str;operator:str;threshold:float
class MonitorUpdate(BaseModel):enabled:bool|None=None;threshold:float|None=None;operator:str|None=None;name:str|None=None
class SeenBody(BaseModel):event_ids:list[str]=Field(default_factory=list)

@app.post('/api/workspace/collections')
def workspace_create_collection(body:CollectionCreate):return response(workspace.create_collection(body.name))
@app.patch('/api/workspace/collections/{collection_id}')
def workspace_rename_collection(collection_id:str,body:CollectionRename):return response(workspace.rename_collection(collection_id,body.name))
@app.delete('/api/workspace/collections/{collection_id}')
def workspace_delete_collection(collection_id:str):return response(workspace.delete_collection(collection_id))
@app.get('/api/workspace/collections/{collection_id}/items')
def workspace_items(collection_id:str):return response(workspace.collection_items(collection_id))
@app.post('/api/workspace/collections/{collection_id}/items')
def workspace_add_item(collection_id:str,body:ResearchItemBody):return response(workspace.add_item(collection_id,body.entity_type,body.entity_id,body.entity_name,body.note,body.meta))
@app.patch('/api/workspace/items/{item_id}')
def workspace_update_item(item_id:str,body:ResearchItemUpdate):return response(workspace.update_item(item_id,body.note,body.collection_id))
@app.delete('/api/workspace/items/{item_id}')
def workspace_remove_item(item_id:str):return response(workspace.remove_item(item_id))
@app.post('/api/workspace/recents')
def workspace_touch_recent(body:RecentBody):return response(workspace.touch_recent(body.entity_type,body.entity_id,body.entity_name,body.route))
@app.get('/api/workspace/recents')
def workspace_recents(limit:int=30):return response(workspace.recent_items(limit))
@app.get('/api/workspace/views')
def workspace_views(view_type:str=''):return response(workspace.list_saved_views(view_type))
@app.post('/api/workspace/views')
def workspace_save_view(body:SavedViewBody):return response(workspace.save_view(body.view_type,body.name,body.config,body.view_id))
@app.delete('/api/workspace/views/{view_id}')
def workspace_delete_view(view_id:str):return response(workspace.delete_view(view_id))
@app.get('/api/workspace/monitors/meta')
def workspace_monitor_meta():return response(workspace.monitor_metadata())
@app.get('/api/workspace/monitors')
def workspace_monitors():return response(workspace.list_rules())
@app.post('/api/workspace/monitors')
def workspace_create_monitor(body:MonitorCreate):return response(workspace.create_rule(body.name,body.entity_type,body.entity_id,body.entity_name,body.metric,body.operator,body.threshold))
@app.patch('/api/workspace/monitors/{rule_id}')
def workspace_update_monitor(rule_id:str,body:MonitorUpdate):return response(workspace.update_rule(rule_id,body.enabled,body.threshold,body.operator,body.name))
@app.delete('/api/workspace/monitors/{rule_id}')
def workspace_delete_monitor(rule_id:str):return response(workspace.delete_rule(rule_id))
@app.post('/api/workspace/monitors/evaluate')
def workspace_evaluate_monitors(mode:str='local'):return response(workspace.evaluate_monitors(mode))
@app.get('/api/workspace/events')
def workspace_events(limit:int=100,unseen_only:bool=False):return response(workspace.monitor_events(limit,unseen_only))
@app.post('/api/workspace/events/seen')
def workspace_seen(body:SeenBody):return response(workspace.mark_events_seen(body.event_ids or None))
@app.get('/api/workspace/audit')
def workspace_audit(limit:int=80):return response(audit.list_recent(limit))

@app.get('/api/data/presence')
def data_presence():return response(services.data_presence())
@app.get('/api/data/health')
def data_health():return response(services.health())
@app.get('/api/data/fund-master')
def data_fund_master():return response(fund_master.stats())
@app.get('/api/data/validate')
def validate():return response(services.validate_local_data())
@app.get('/api/data/quality')
def data_quality():return response(quality.report())
@app.get('/api/data/storage')
def storage():return response(db.storage_info())
@app.post('/api/data/open-folder')
def open_folder():
    require_maintainer()
    return response(db.open_data_dir())

class MarketSync(BaseModel):quarters:int=8;force:bool=False;strategy:str='standard';workers:int|None=None
class HoldingSync(BaseModel):
    years:list[int]=Field(default_factory=list)
    limit:int|None=100
    strategy:str='standard'
    workers:int|None=None
    force:bool=False
    since_inception:bool=False
    fund_code:str|None=None
class SecuritySync(BaseModel):limit:int|None=None;strategy:str='standard';workers:int|None=None;deep:bool=False
class IncrementalSync(BaseModel):strategy:str='standard';workers:int|None=None
class GapSync(BaseModel):fund_code:str;years_back:int=3;strategy:str='standard';workers:int|None=None
class MajorChangeSync(BaseModel):fund_code:str;years:list[int];strategy:str='standard'

@app.post('/api/tasks/funds')
def task_funds():
    require_maintainer()
    return response(tasks.start_task('funds',lambda ctx:providers.sync_funds(ctx.progress)))
@app.post('/api/tasks/managers')
def task_managers():
    require_maintainer()
    return response(tasks.start_task('managers',lambda ctx:providers.sync_managers(ctx.progress)))
@app.post('/api/tasks/fund-master')
def task_fund_master():
    require_maintainer()
    return response(tasks.start_task('fund_master',lambda ctx:fund_master.build_fund_master()))
@app.post('/api/tasks/market')
def task_market(body:MarketSync):
    require_maintainer()
    workers=collection_policy.workers_for('market',body.strategy,body.workers)
    return response(tasks.start_task('market',lambda ctx:providers.sync_market(max(4,min(body.quarters,20)),body.force,ctx.progress,workers)))
@app.post('/api/tasks/holdings')
def task_holdings(body:HoldingSync):
    require_maintainer()
    workers=collection_policy.workers_for('holdings',body.strategy,body.workers)
    return response(tasks.start_task('holdings',lambda ctx:providers.sync_holdings(body.years,body.limit,workers,body.force,ctx.progress,body.since_inception,body.fund_code)))
@app.post('/api/tasks/security-master')
def task_security(body:SecuritySync):
    require_maintainer()
    workers=collection_policy.workers_for('security_master',body.strategy,body.workers)
    return response(tasks.start_task('security_master',lambda ctx:security.sync_security_master(body.limit,workers,ctx.progress,body.deep)))
@app.post('/api/tasks/incremental')
def task_incremental(body:IncrementalSync):
    require_maintainer()
    workers=collection_policy.workers_for('holdings',body.strategy,body.workers)
    return response(tasks.start_task('incremental',lambda ctx:providers.sync_incremental(workers,ctx.progress)))

@app.post('/api/data/holdings-plan')
def holdings_plan(body:HoldingSync):return response(providers.holdings_plan_preview(body.years,body.limit,body.force,body.since_inception,body.fund_code))
@app.get('/api/data/collection-profiles')
def collection_profiles():return response(collection_policy.public_profiles())
@app.post('/api/tasks/return-gap')
def task_gap(body:GapSync):
    require_maintainer()
    workers=collection_policy.workers_for('return_gap',body.strategy,body.workers)
    return response(tasks.start_task('return_gap',lambda ctx:security.sync_return_gap_inputs(body.fund_code,max(1,min(body.years_back,6)),workers,ctx.progress)))

@app.post('/api/tasks/major-changes')
def task_major_changes(body:MajorChangeSync):
    require_maintainer()
    years=[int(y) for y in body.years if 2000<=int(y)<=2100]
    return response(tasks.start_task('major_changes',lambda ctx:providers.sync_fund_major_changes(body.fund_code,years,ctx.progress)))
@app.get('/api/tasks')
def list_tasks(limit:int=30):return response(db.list_task_runs(limit))
@app.get('/api/tasks/{task_id}')
def task_detail(task_id:str):
    out=db.get_task_run(task_id)
    if not out:raise HTTPException(404,'未找到任务')
    return response(out)
@app.post('/api/tasks/{task_id}/pause')
def pause_task(task_id:str):
    require_maintainer()
    if not db.get_task_run(task_id):raise HTTPException(404,'未找到任务')
    ok=db.request_pause(task_id)
    if ok:audit.log('task.pause','task',task_id,{})
    return response({'ok':ok})
@app.post('/api/tasks/{task_id}/resume')
def resume_task(task_id:str):
    require_maintainer()
    if not db.get_task_run(task_id):raise HTTPException(404,'未找到任务')
    ok=db.request_resume(task_id)
    if ok:audit.log('task.resume','task',task_id,{})
    return response({'ok':ok})
@app.post('/api/tasks/{task_id}/cancel')
def cancel_task(task_id:str):
    require_maintainer()
    if not db.get_task_run(task_id):raise HTTPException(404,'未找到任务')
    db.request_cancel(task_id);audit.log('task.cancel','task',task_id,{});return response({'ok':True})

# old synchronous endpoints retained for API compatibility
@app.post('/api/data/sync/funds')
def sync_funds():
    require_maintainer()
    return response(providers.sync_funds())
@app.post('/api/data/sync/managers')
def sync_managers():
    require_maintainer()
    return response(providers.sync_managers())
@app.post('/api/data/sync/market')
def sync_market(body:MarketSync):
    require_maintainer()
    return response(providers.sync_market(body.quarters,body.force,None,collection_policy.workers_for('market',body.strategy,body.workers)))
@app.post('/api/data/sync/holdings')
def sync_holdings(body:HoldingSync):
    require_maintainer()
    return response(providers.sync_holdings(body.years,body.limit,collection_policy.workers_for('holdings',body.strategy,body.workers),body.force,None,body.since_inception,body.fund_code))

@app.post('/api/data/import-db')
async def import_db(file:UploadFile=File(...)):
    require_maintainer()
    suffix=Path(file.filename or 'fundscope.db').suffix or '.db'
    with tempfile.NamedTemporaryFile(delete=False,suffix=suffix) as f:f.write(await file.read());path=f.name
    try:return response(db.import_legacy_db(path))
    except Exception as exc:raise HTTPException(400,f'数据库导入失败: {exc}')
@app.get('/api/data/snapshots')
def snapshots():return response(db.list_snapshots())
@app.post('/api/data/snapshots')
def create_snapshot():
    require_maintainer()
    return response(db.create_snapshot() or {})
@app.post('/api/data/snapshots/{name}/restore')
def restore_snapshot(name:str):
    require_maintainer()
    return response(db.restore_snapshot(name))
