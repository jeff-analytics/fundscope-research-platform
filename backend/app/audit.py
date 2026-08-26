import json
from datetime import datetime
from . import db


def log(action, entity_type='', entity_id='', detail=None):
    now=datetime.now().isoformat(timespec='seconds')
    payload=json.dumps(detail or {},ensure_ascii=False,default=str)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO audit_log(action,entity_type,entity_id,detail_json,created_at) VALUES(?,?,?,?,?)",
            (str(action),str(entity_type or ''),str(entity_id or ''),payload,now),
        )
        conn.commit()


def list_recent(limit=80):
    rows=db.read_sql("SELECT * FROM audit_log ORDER BY audit_id DESC LIMIT ?",(max(1,min(int(limit),300)),))
    if rows.empty:return []
    out=[]
    for _,r in rows.iterrows():
        try:detail=json.loads(r.get('detail_json') or '{}')
        except Exception:detail={}
        out.append({
            'audit_id':int(r['audit_id']),
            'action':r['action'],
            'entity_type':r.get('entity_type') or '',
            'entity_id':r.get('entity_id') or '',
            'detail':detail,
            'created_at':r.get('created_at'),
        })
    return out
