import json
import operator as pyop
import uuid
from datetime import datetime
from typing import Any

from . import audit, db, explorer, services

DEFAULT_COLLECTION_NAME='我的研究'
ALLOWED_ENTITY_TYPES={'fund','security','manager'}
MONITOR_METRICS={
    'fund':{
        'drift_score':'风格漂移',
        'turnover_pct':'调仓强度',
        'top10_concentration':'前十集中度',
        'retention_pct':'持仓延续率',
    },
    'security':{
        'breadth_cur':'覆盖基金数',
        'breadth_delta':'覆盖变化',
        'breadth_acceleration':'共识加速度',
        'avg_weight':'平均持仓权重',
    },
}
OPS={'>':pyop.gt,'>=':pyop.ge,'<':pyop.lt,'<=':pyop.le}


def _now():return datetime.now().isoformat(timespec='seconds')
def _id(prefix):return f"{prefix}_{uuid.uuid4().hex[:12]}"


def ensure_default_collection():
    row=db.read_sql("SELECT collection_id FROM research_collections ORDER BY created_at LIMIT 1")
    if not row.empty:return str(row.iloc[0]['collection_id'])
    return create_collection(DEFAULT_COLLECTION_NAME)['collection_id']


def list_collections():
    rows=db.read_sql("""
        SELECT c.collection_id,c.name,c.created_at,c.updated_at,COUNT(i.item_id) AS item_count
        FROM research_collections c LEFT JOIN research_items i ON i.collection_id=c.collection_id
        GROUP BY c.collection_id,c.name,c.created_at,c.updated_at ORDER BY c.updated_at DESC,c.created_at DESC
    """)
    if rows.empty:
        ensure_default_collection()
        return list_collections()
    return services.clean_payload(rows.to_dict('records'))


def create_collection(name):
    name=str(name or '').strip()
    if not name:raise ValueError('收藏夹名称不能为空')
    cid=_id('col');now=_now()
    with db.connect() as conn:
        conn.execute("INSERT INTO research_collections(collection_id,name,created_at,updated_at) VALUES(?,?,?,?)",(cid,name[:60],now,now));conn.commit()
    audit.log('collection.create','collection',cid,{'name':name[:60]})
    return {'collection_id':cid,'name':name[:60],'created_at':now,'updated_at':now,'item_count':0}


def rename_collection(collection_id,name):
    name=str(name or '').strip()
    if not name:raise ValueError('收藏夹名称不能为空')
    now=_now()
    with db.connect() as conn:
        cur=conn.execute("UPDATE research_collections SET name=?,updated_at=? WHERE collection_id=?",(name[:60],now,collection_id));conn.commit()
    if not cur.rowcount:raise KeyError(collection_id)
    audit.log('collection.rename','collection',collection_id,{'name':name[:60]})
    return {'ok':True}


def delete_collection(collection_id):
    cols=list_collections()
    if len(cols)<=1:raise ValueError('至少保留一个收藏夹')
    with db.connect() as conn:
        conn.execute("DELETE FROM research_items WHERE collection_id=?",(collection_id,))
        cur=conn.execute("DELETE FROM research_collections WHERE collection_id=?",(collection_id,));conn.commit()
    if not cur.rowcount:raise KeyError(collection_id)
    audit.log('collection.delete','collection',collection_id,{})
    return {'ok':True}


def collection_items(collection_id):
    rows=db.read_sql("SELECT * FROM research_items WHERE collection_id=? ORDER BY updated_at DESC,created_at DESC",(collection_id,))
    if rows.empty:return []
    out=[]
    for _,r in rows.iterrows():
        try:meta=json.loads(r.get('meta_json') or '{}')
        except Exception:meta={}
        out.append({
            'item_id':r['item_id'],'collection_id':r['collection_id'],'entity_type':r['entity_type'],
            'entity_id':r['entity_id'],'entity_name':r['entity_name'],'note':r.get('note') or '',
            'meta':meta,'created_at':r.get('created_at'),'updated_at':r.get('updated_at')
        })
    return services.clean_payload(out)


def add_item(collection_id,entity_type,entity_id,entity_name,note='',meta=None):
    if entity_type not in ALLOWED_ENTITY_TYPES:raise ValueError('不支持的研究对象类型')
    if db.read_sql("SELECT collection_id FROM research_collections WHERE collection_id=?",(collection_id,)).empty:raise KeyError(collection_id)
    now=_now();iid=_id('item')
    payload=json.dumps(meta or {},ensure_ascii=False,default=str)
    with db.connect() as conn:
        existing=conn.execute("SELECT item_id FROM research_items WHERE collection_id=? AND entity_type=? AND entity_id=?",(collection_id,entity_type,str(entity_id))).fetchone()
        if existing:
            iid=existing[0]
            conn.execute("UPDATE research_items SET entity_name=?,note=CASE WHEN ?<>'' THEN ? ELSE note END,meta_json=?,updated_at=? WHERE item_id=?",(str(entity_name)[:160],str(note),str(note)[:2000],payload,now,iid))
        else:
            conn.execute("INSERT INTO research_items(item_id,collection_id,entity_type,entity_id,entity_name,note,meta_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(iid,collection_id,entity_type,str(entity_id),str(entity_name)[:160],str(note)[:2000],payload,now,now))
        conn.execute("UPDATE research_collections SET updated_at=? WHERE collection_id=?",(now,collection_id));conn.commit()
    audit.log('research.add',entity_type,str(entity_id),{'collection_id':collection_id,'entity_name':entity_name})
    return {'item_id':iid,'collection_id':collection_id,'entity_type':entity_type,'entity_id':str(entity_id),'entity_name':entity_name,'note':note,'meta':meta or {},'updated_at':now}


def update_item(item_id,note=None,collection_id=None):
    row=db.read_sql("SELECT * FROM research_items WHERE item_id=?",(item_id,))
    if row.empty:raise KeyError(item_id)
    current=row.iloc[0];fields=[];vals=[]
    if note is not None:fields.append('note=?');vals.append(str(note)[:2000])
    if collection_id is not None:
        if db.read_sql("SELECT collection_id FROM research_collections WHERE collection_id=?",(collection_id,)).empty:raise KeyError(collection_id)
        fields.append('collection_id=?');vals.append(collection_id)
    now=_now();fields.append('updated_at=?');vals.append(now);vals.append(item_id)
    with db.connect() as conn:
        conn.execute(f"UPDATE research_items SET {','.join(fields)} WHERE item_id=?",vals);conn.commit()
    audit.log('research.update',current['entity_type'],current['entity_id'],{'item_id':item_id})
    return {'ok':True,'updated_at':now}


def remove_item(item_id):
    row=db.read_sql("SELECT * FROM research_items WHERE item_id=?",(item_id,))
    if row.empty:raise KeyError(item_id)
    r=row.iloc[0].to_dict()
    with db.connect() as conn:conn.execute("DELETE FROM research_items WHERE item_id=?",(item_id,));conn.commit()
    audit.log('research.remove',r.get('entity_type'),r.get('entity_id'),{'item_id':item_id,'collection_id':r.get('collection_id')})
    return services.clean_payload(r)


def touch_recent(entity_type,entity_id,entity_name,route=''):
    if entity_type not in ALLOWED_ENTITY_TYPES:return {'ok':False}
    now=_now()
    with db.connect() as conn:
        conn.execute("""INSERT INTO research_recents(entity_type,entity_id,entity_name,route,last_opened_at,open_count)
        VALUES(?,?,?,?,?,1) ON CONFLICT(entity_type,entity_id) DO UPDATE SET entity_name=excluded.entity_name,route=excluded.route,last_opened_at=excluded.last_opened_at,open_count=research_recents.open_count+1""",
        (entity_type,str(entity_id),str(entity_name)[:160],str(route)[:300],now));conn.commit()
    return {'ok':True}


def recent_items(limit=30):
    rows=db.read_sql("SELECT * FROM research_recents ORDER BY last_opened_at DESC LIMIT ?",(max(1,min(int(limit),100)),))
    return [] if rows.empty else services.clean_payload(rows.to_dict('records'))


def list_saved_views(view_type=''):
    if view_type:rows=db.read_sql("SELECT * FROM saved_views WHERE view_type=? ORDER BY updated_at DESC",(view_type,))
    else:rows=db.read_sql("SELECT * FROM saved_views ORDER BY updated_at DESC")
    out=[]
    for _,r in rows.iterrows():
        try:cfg=json.loads(r.get('config_json') or '{}')
        except Exception:cfg={}
        out.append({'view_id':r['view_id'],'view_type':r['view_type'],'name':r['name'],'config':cfg,'created_at':r['created_at'],'updated_at':r['updated_at']})
    return out


def save_view(view_type,name,config,view_id=None):
    name=str(name or '').strip()
    if not name:raise ValueError('视图名称不能为空')
    now=_now();vid=view_id or _id('view');payload=json.dumps(config or {},ensure_ascii=False,default=str)
    with db.connect() as conn:
        if view_id:
            cur=conn.execute("UPDATE saved_views SET view_type=?,name=?,config_json=?,updated_at=? WHERE view_id=?",(view_type,name[:80],payload,now,view_id))
            if not cur.rowcount:raise KeyError(view_id)
        else:
            conn.execute("INSERT INTO saved_views(view_id,view_type,name,config_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",(vid,view_type,name[:80],payload,now,now))
        conn.commit()
    audit.log('view.save','saved_view',vid,{'view_type':view_type,'name':name[:80]})
    return {'view_id':vid,'view_type':view_type,'name':name[:80],'config':config or {},'updated_at':now}


def delete_view(view_id):
    with db.connect() as conn:
        cur=conn.execute("DELETE FROM saved_views WHERE view_id=?",(view_id,));conn.commit()
    if not cur.rowcount:raise KeyError(view_id)
    audit.log('view.delete','saved_view',view_id,{})
    return {'ok':True}


def monitor_metadata():return MONITOR_METRICS


def list_rules():
    rows=db.read_sql("SELECT * FROM monitor_rules ORDER BY enabled DESC,updated_at DESC")
    return [] if rows.empty else services.clean_payload(rows.to_dict('records'))


def create_rule(name,entity_type,entity_id,entity_name,metric,operator,threshold):
    if entity_type not in MONITOR_METRICS or metric not in MONITOR_METRICS[entity_type]:raise ValueError('不支持的监控指标')
    if operator not in OPS:raise ValueError('不支持的判断条件')
    rid=_id('rule');now=_now()
    with db.connect() as conn:
        conn.execute("INSERT INTO monitor_rules(rule_id,name,entity_type,entity_id,entity_name,metric,operator,threshold,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,1,?,?)",
                     (rid,str(name or f'{entity_name}监控')[:100],entity_type,str(entity_id),str(entity_name)[:160],metric,operator,float(threshold),now,now));conn.commit()
    audit.log('monitor.create',entity_type,str(entity_id),{'rule_id':rid,'metric':metric,'operator':operator,'threshold':float(threshold)})
    return {'rule_id':rid,'name':name,'entity_type':entity_type,'entity_id':str(entity_id),'entity_name':entity_name,'metric':metric,'operator':operator,'threshold':float(threshold),'enabled':1}


def update_rule(rule_id,enabled=None,threshold=None,operator=None,name=None):
    row=db.read_sql("SELECT * FROM monitor_rules WHERE rule_id=?",(rule_id,))
    if row.empty:raise KeyError(rule_id)
    fields=[];vals=[]
    if enabled is not None:fields.append('enabled=?');vals.append(1 if enabled else 0)
    if threshold is not None:fields.append('threshold=?');vals.append(float(threshold))
    if operator is not None:
        if operator not in OPS:raise ValueError('不支持的判断条件')
        fields.append('operator=?');vals.append(operator)
    if name is not None:fields.append('name=?');vals.append(str(name)[:100])
    fields.append('updated_at=?');vals.append(_now());vals.append(rule_id)
    with db.connect() as conn:conn.execute(f"UPDATE monitor_rules SET {','.join(fields)} WHERE rule_id=?",vals);conn.commit()
    audit.log('monitor.update',row.iloc[0]['entity_type'],row.iloc[0]['entity_id'],{'rule_id':rule_id})
    return {'ok':True}


def delete_rule(rule_id):
    row=db.read_sql("SELECT * FROM monitor_rules WHERE rule_id=?",(rule_id,))
    if row.empty:raise KeyError(rule_id)
    with db.connect() as conn:
        conn.execute("DELETE FROM monitor_events WHERE rule_id=?",(rule_id,));conn.execute("DELETE FROM monitor_rules WHERE rule_id=?",(rule_id,));conn.commit()
    audit.log('monitor.delete',row.iloc[0]['entity_type'],row.iloc[0]['entity_id'],{'rule_id':rule_id})
    return {'ok':True}


def monitor_events(limit=100,unseen_only=False):
    where='WHERE seen=0' if unseen_only else ''
    rows=db.read_sql(f"SELECT * FROM monitor_events {where} ORDER BY created_at DESC LIMIT ?",(max(1,min(int(limit),500)),))
    return [] if rows.empty else services.clean_payload(rows.to_dict('records'))


def mark_events_seen(event_ids=None):
    with db.connect() as conn:
        if event_ids:
            ids=[str(x) for x in event_ids];marks=','.join(['?']*len(ids));conn.execute(f"UPDATE monitor_events SET seen=1 WHERE event_id IN ({marks})",ids)
        else:conn.execute("UPDATE monitor_events SET seen=1")
        conn.commit()
    return {'ok':True}


def _metric_maps(mode='local'):
    funds=explorer.fund_explorer(mode)
    secs=explorer.security_explorer(mode)
    frows=funds.get('rows') or [];srows=secs.get('rows') or []
    fmap={str(r.get('fund_code')):r for r in frows}
    smap={str(r.get('stock_code')):r for r in srows}
    return (funds.get('selected_period'),fmap),(secs.get('selected_period'),smap)


def evaluate_monitors(mode='local'):
    rules=[r for r in list_rules() if int(r.get('enabled') or 0)==1]
    if not rules:return {'evaluated':0,'triggered':0,'events':[]}
    (fund_period,fmap),(sec_period,smap)=_metric_maps(mode)
    now=_now();events=[];evaluated=0
    for r in rules:
        entity_type=r['entity_type'];row=fmap.get(str(r['entity_id'])) if entity_type=='fund' else smap.get(str(r['entity_id'])) if entity_type=='security' else None
        period=fund_period if entity_type=='fund' else sec_period if entity_type=='security' else None
        if not row or not period:continue
        value=row.get(r['metric'])
        try:value=float(value)
        except Exception:continue
        evaluated+=1;triggered=OPS.get(r['operator'],lambda a,b:False)(value,float(r['threshold']))
        with db.connect() as conn:
            conn.execute("UPDATE monitor_rules SET last_evaluated_period=?,last_value=?,updated_at=? WHERE rule_id=?",(period,value,now,r['rule_id']))
            if triggered and str(r.get('last_triggered_period') or '')!=str(period):
                eid=_id('evt')
                conn.execute("INSERT OR IGNORE INTO monitor_events(event_id,rule_id,period,value,threshold,operator,entity_type,entity_id,entity_name,metric,created_at,seen) VALUES(?,?,?,?,?,?,?,?,?,?,?,0)",
                             (eid,r['rule_id'],period,value,float(r['threshold']),r['operator'],entity_type,str(r['entity_id']),r['entity_name'],r['metric'],now))
                conn.execute("UPDATE monitor_rules SET last_triggered_period=? WHERE rule_id=?",(period,r['rule_id']))
                events.append({'event_id':eid,'rule_id':r['rule_id'],'period':period,'value':value,'entity_type':entity_type,'entity_id':r['entity_id'],'entity_name':r['entity_name'],'metric':r['metric'],'threshold':float(r['threshold']),'operator':r['operator']})
            conn.commit()
    if events:audit.log('monitor.trigger','monitor','',{'count':len(events),'periods':sorted(set(str(e['period']) for e in events))})
    return {'evaluated':evaluated,'triggered':len(events),'events':events}


def overview():
    cols=list_collections();rules=list_rules();events=monitor_events(100);recents=recent_items(12)
    return {
        'collections':cols,
        'collection_count':len(cols),
        'saved_items':sum(int(x.get('item_count') or 0) for x in cols),
        'active_rules':sum(1 for x in rules if int(x.get('enabled') or 0)==1),
        'unseen_events':sum(1 for x in events if int(x.get('seen') or 0)==0),
        'rules':rules,'events':events,'recents':recents,
    }


def global_search(mode='demo',q='',limit=8):
    q=str(q or '').strip()
    if not q:return {'funds':[],'managers':[],'securities':[]}
    funds=services.funds(mode,q,True)[:max(1,min(int(limit),20))]
    managers=services.managers(mode,q)[:max(1,min(int(limit),20))]
    if mode=='demo':
        from . import demo_data
        h=demo_data.holdings().copy();mask=h['stock_code'].astype(str).str.contains(q,case=False,na=False)|h['stock_name'].astype(str).str.contains(q,case=False,na=False)
        sec=h.loc[mask,['stock_code','stock_name','sector']].drop_duplicates().head(limit).to_dict('records')
    else:
        like=f"%{q}%"
        secdf=db.read_sql("""
            SELECT h.stock_code,MAX(h.stock_name) AS stock_name,COALESCE(NULLIF(MAX(s.industry_l1),''),'未分类') AS sector,COUNT(DISTINCT h.fund_code) AS records
            FROM fund_holdings h LEFT JOIN security_master s ON s.security_code=h.stock_code
            WHERE h.stock_code LIKE ? OR h.stock_name LIKE ?
            GROUP BY h.stock_code ORDER BY records DESC LIMIT ?
        """,(like,like,max(1,min(int(limit),20))))
        sec=[] if secdf.empty else services.clean_payload(secdf.to_dict('records'))
    return {'funds':funds,'managers':managers,'securities':sec}
