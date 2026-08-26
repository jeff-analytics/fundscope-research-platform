import tempfile
from pathlib import Path

from app import db, explorer, workspace


def _setup_tmp():
    tmp=tempfile.TemporaryDirectory();old=db.DB_PATH
    db.DB_PATH=Path(tmp.name)/'fundscope.db';db.ensure_schema();explorer._CACHE.clear()
    return tmp,old


def _restore(tmp,old):
    explorer._CACHE.clear();db.DB_PATH=old;tmp.cleanup()


def test_workspace_collections_items_and_undo_payload():
    tmp,old=_setup_tmp()
    try:
        cols=workspace.list_collections();assert len(cols)==1
        cid=cols[0]['collection_id']
        item=workspace.add_item(cid,'fund','D00001','示例科技成长混合','观察季度变化',{'quarter':'2026Q2'})
        rows=workspace.collection_items(cid);assert len(rows)==1 and rows[0]['note']=='观察季度变化'
        workspace.update_item(item['item_id'],note='继续跟踪集中度')
        assert workspace.collection_items(cid)[0]['note']=='继续跟踪集中度'
        deleted=workspace.remove_item(item['item_id']);assert deleted['entity_id']=='D00001'
        assert workspace.collection_items(cid)==[]
        workspace.add_item(cid,deleted['entity_type'],deleted['entity_id'],deleted['entity_name'],deleted['note'],{})
        assert len(workspace.collection_items(cid))==1
    finally:_restore(tmp,old)


def test_saved_views_round_trip():
    tmp,old=_setup_tmp()
    try:
        v=workspace.save_view('fund_explorer','高漂移筛选',{'tag':'高漂移','search':'成长'})
        rows=workspace.list_saved_views('fund_explorer');assert rows[0]['config']['tag']=='高漂移'
        workspace.save_view('fund_explorer','高漂移与集中',{'tag':'高漂移','min_concentration':60},v['view_id'])
        rows=workspace.list_saved_views('fund_explorer');assert rows[0]['name']=='高漂移与集中'
        workspace.delete_view(v['view_id']);assert workspace.list_saved_views('fund_explorer')==[]
    finally:_restore(tmp,old)


def test_monitor_rule_evaluates_and_deduplicates_by_period(monkeypatch):
    tmp,old=_setup_tmp()
    try:
        monkeypatch.setattr(explorer,'fund_explorer',lambda mode='local',period=None:{'selected_period':'2026Q2','rows':[{'fund_code':'D00001','drift_score':72.0}]})
        monkeypatch.setattr(explorer,'security_explorer',lambda mode='local',period=None:{'selected_period':'2026Q2','rows':[]})
        rule=workspace.create_rule('漂移监控','fund','D00001','示例科技成长混合','drift_score','>=',70)
        first=workspace.evaluate_monitors('local');assert first['evaluated']==1 and first['triggered']==1
        second=workspace.evaluate_monitors('local');assert second['evaluated']==1 and second['triggered']==0
        events=workspace.monitor_events();assert len(events)==1 and events[0]['period']=='2026Q2'
        workspace.mark_events_seen();assert workspace.monitor_events()[0]['seen']==1
        workspace.update_rule(rule['rule_id'],enabled=False);assert int(workspace.list_rules()[0]['enabled'])==0
    finally:_restore(tmp,old)


def test_peer_lens_demo_has_transparent_percentiles_and_no_score():
    out=explorer.fund_peer_lens('D00001','demo')
    assert out['fund']['fund_code']=='D00001'
    assert out['universes'] and out['metrics']
    assert all('percentile' in x and 'median' in x for x in out['metrics'])
    assert 'score' not in out
    assert '标准化距离' in out['method']


def test_manager_explorer_demo_returns_behavior_cross_section():
    out=explorer.manager_explorer('demo')
    assert out['selected_period']
    assert out['rows']
    row=out['rows'][0]
    for key in ['manager_name','company','median_drift','median_turnover','median_concentration','tags']:
        assert key in row


def test_recents_and_audit_are_persistent():
    tmp,old=_setup_tmp()
    try:
        workspace.touch_recent('security','300308','中际旭创','/explorer?security=300308')
        workspace.touch_recent('security','300308','中际旭创','/explorer?security=300308')
        rows=workspace.recent_items();assert rows[0]['open_count']==2
        workspace.create_collection('长期观察')
        audits=db.read_sql('SELECT action FROM audit_log ORDER BY audit_id DESC')
        assert 'collection.create' in audits['action'].tolist()
    finally:_restore(tmp,old)
