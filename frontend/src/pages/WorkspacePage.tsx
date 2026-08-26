import { useEffect, useMemo, useState } from "react";
import { Bell, Bookmark, CheckCircle2, Clock3, FolderPlus, Pencil, RefreshCw, Search, Trash2, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { PageHeader } from "../components/PageHeader";
import { MetricStrip } from "../components/MetricStrip";
import { Panel } from "../components/Panel";
import { EmptyState, Loading } from "../components/Loading";
import { useToastStore } from "../store/useToastStore";
import { useAppStore } from "../store/useAppStore";

const routeFor=(x:any)=>x.entity_type==='fund'?`/funds?code=${encodeURIComponent(x.entity_id)}`:x.entity_type==='manager'?`/managers?mid=${encodeURIComponent(x.entity_id)}`:`/explorer?security=${encodeURIComponent(x.entity_id)}`;
const typeLabel=(t:string)=>t==='fund'?'基金':t==='security'?'证券':'基金经理';
const metricLabel=(t:string,m:string,meta:any)=>meta?.[t]?.[m]||m;
const auditLabel=(a:string)=>({
  'collection.create':'新建收藏夹','collection.rename':'重命名收藏夹','collection.delete':'删除收藏夹',
  'research.add':'加入研究收藏','research.update':'更新研究笔记','research.remove':'移出研究收藏',
  'view.save':'保存研究视图','view.delete':'删除研究视图','monitor.create':'创建监控','monitor.update':'更新监控','monitor.delete':'删除监控','monitor.trigger':'监控触发',
  'task.start':'启动采集任务','task.success':'采集任务完成','task.pause':'暂停采集任务','task.resume':'继续采集任务','task.cancel':'取消采集任务','task.error':'采集任务失败'
} as Record<string,string>)[a]||a;

export function WorkspacePage(){
  const navigate=useNavigate();
  const mode=useAppStore(s=>s.mode);
  const push=useToastStore(s=>s.push);
  const[tab,setTab]=useState<'collections'|'monitors'|'recents'>('collections');
  const[overview,setOverview]=useState<any>(null);
  const[collections,setCollections]=useState<any[]>([]);
  const[selected,setSelected]=useState('');
  const[items,setItems]=useState<any[]>([]);
  const[query,setQuery]=useState('');
  const[active,setActive]=useState<any>(null);
  const[creating,setCreating]=useState(false);
  const[newName,setNewName]=useState('');
  const[manage,setManage]=useState<null|'rename'|'delete'>(null);
  const[manageName,setManageName]=useState('');
  const[rules,setRules]=useState<any[]>([]);
  const[events,setEvents]=useState<any[]>([]);
  const[meta,setMeta]=useState<any>({});
  const[recents,setRecents]=useState<any[]>([]);
  const[audit,setAudit]=useState<any[]>([]);
  const[loading,setLoading]=useState(true);

  const load=async()=>{
    setLoading(true);
    try{
      const [o,c,r,e,m,re,a]=await Promise.all([api.workspace(),api.collections(),api.monitors(),api.monitorEvents(100),api.monitorMeta(),api.recents(30),api.audit(80)]);
      setOverview(o);setCollections(c);setRules(r);setEvents(e);setMeta(m);setRecents(re);setAudit(a);
      if(!selected&&c[0])setSelected(c[0].collection_id);
    }finally{setLoading(false)}
  };
  useEffect(()=>{load()},[]);
  useEffect(()=>{if(selected){api.collectionItems(selected).then(x=>{setItems(x);setActive(x[0]||null)}).catch(()=>setItems([]))}},[selected]);

  const currentCollection=collections.find(c=>c.collection_id===selected);
  const visible=useMemo(()=>{const q=query.trim().toLowerCase();return q?items.filter(x=>`${x.entity_name} ${x.entity_id} ${x.note||''}`.toLowerCase().includes(q)):items},[items,query]);

  const createCollection=async()=>{
    if(!newName.trim())return;
    try{const c=await api.createCollection(newName.trim());setCollections(x=>[c,...x]);setSelected(c.collection_id);setNewName('');setCreating(false);push({kind:'success',title:'收藏夹已创建'});setOverview(await api.workspace())}
    catch(e:any){push({kind:'error',title:'创建失败',message:e?.message})}
  };
  const renameCollection=async()=>{
    if(!selected||!manageName.trim())return;
    try{await api.renameCollection(selected,manageName.trim());setCollections(xs=>xs.map(x=>x.collection_id===selected?{...x,name:manageName.trim()}:x));setManage(null);push({kind:'success',title:'收藏夹已重命名'})}
    catch(e:any){push({kind:'error',title:'重命名失败',message:e?.message})}
  };
  const deleteCollection=async()=>{
    if(!selected)return;
    try{await api.deleteCollection(selected);const c=await api.collections();setCollections(c);setSelected(c[0]?.collection_id||'');setItems([]);setActive(null);setManage(null);setOverview(await api.workspace());push({kind:'success',title:'收藏夹已删除'})}
    catch(e:any){push({kind:'error',title:'删除失败',message:e?.message})}
  };
  const saveNote=async(item:any,note:string)=>{
    try{await api.updateResearchItem(item.item_id,{note});setItems(xs=>xs.map(x=>x.item_id===item.item_id?{...x,note}:x));setActive((x:any)=>x?.item_id===item.item_id?{...x,note}:x);push({kind:'success',title:'研究笔记已保存'})}
    catch(e:any){push({kind:'error',title:'保存失败',message:e?.message})}
  };
  const remove=async(item:any)=>{
    try{
      const deleted=await api.removeResearchItem(item.item_id);setItems(xs=>xs.filter(x=>x.item_id!==item.item_id));if(active?.item_id===item.item_id)setActive(null);setOverview(await api.workspace());
      push({kind:'info',title:'已移出收藏夹',actionLabel:'撤回',action:async()=>{await api.addResearchItem(deleted.collection_id,{entity_type:deleted.entity_type,entity_id:deleted.entity_id,entity_name:deleted.entity_name,note:deleted.note||'',meta:JSON.parse(deleted.meta_json||'{}')});setItems(await api.collectionItems(selected));setOverview(await api.workspace())}})
    }catch(e:any){push({kind:'error',title:'操作失败',message:e?.message})}
  };
  const evaluate=async()=>{
    try{const r=await api.evaluateMonitors(mode);push({kind:'success',title:'监控已刷新',message:r.triggered?`新增 ${r.triggered} 条触发记录`:'当前没有新增触发'});const [rr,ee]=await Promise.all([api.monitors(),api.monitorEvents(100)]);setRules(rr);setEvents(ee);setOverview(await api.workspace())}
    catch(e:any){push({kind:'error',title:'刷新失败',message:e?.message})}
  };
  const toggleRule=async(r:any)=>{await api.updateMonitor(r.rule_id,{enabled:!Number(r.enabled)});setRules(xs=>xs.map(x=>x.rule_id===r.rule_id?{...x,enabled:Number(r.enabled)?0:1}:x))};

  if(loading&&!overview)return <Loading label="正在加载研究工作区"/>;
  return <>
    <PageHeader eyebrow="研究工作区" title="我的研究" actions={<div className="workspace-tabs">
      <button className={tab==='collections'?'active':''} onClick={()=>setTab('collections')}><Bookmark size={15}/>收藏</button>
      <button className={tab==='monitors'?'active':''} onClick={()=>setTab('monitors')}><Bell size={15}/>监控{overview?.unseen_events?<i>{overview.unseen_events}</i>:null}</button>
      <button className={tab==='recents'?'active':''} onClick={()=>setTab('recents')}><Clock3 size={15}/>最近</button>
    </div>}/>
    <MetricStrip items={[{label:'收藏夹',value:overview?.collection_count||0},{label:'研究对象',value:overview?.saved_items||0},{label:'启用监控',value:overview?.active_rules||0},{label:'未读触发',value:overview?.unseen_events||0}]}/>

    {tab==='collections'&&<div className="research-workspace-grid">
      <aside className="collection-rail">
        <div className="collection-rail-head"><b>收藏夹</b><div><button title="新建" onClick={()=>setCreating(true)}><FolderPlus size={15}/></button><button title="重命名" disabled={!selected} onClick={()=>{setManageName(currentCollection?.name||'');setManage('rename')}}><Pencil size={14}/></button><button title="删除" disabled={!selected||collections.length<=1} onClick={()=>setManage('delete')}><Trash2 size={14}/></button></div></div>
        {creating&&<div className="collection-create"><input autoFocus value={newName} onChange={e=>setNewName(e.target.value)} placeholder="收藏夹名称" onKeyDown={e=>{if(e.key==='Enter')createCollection();if(e.key==='Escape')setCreating(false)}}/><button onClick={createCollection}>创建</button></div>}
        <div>{collections.map(c=><button key={c.collection_id} className={selected===c.collection_id?'active':''} onClick={()=>setSelected(c.collection_id)}><span>{c.name}</span><small>{c.item_count||0}</small></button>)}</div>
      </aside>
      <section className="collection-main">
        <div className="collection-toolbar"><div className="inline-search"><Search size={15}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索收藏内容或笔记"/></div><span>{visible.length} 项</span></div>
        {visible.length?<div className="research-item-list">{visible.map(x=><button key={x.item_id} className={active?.item_id===x.item_id?'active':''} onClick={()=>setActive(x)} onDoubleClick={()=>navigate(routeFor(x))}><span className={`entity-type ${x.entity_type}`}>{typeLabel(x.entity_type)}</span><div><b>{x.entity_name}</b><small>{x.entity_id}</small></div><p>{x.note||'—'}</p></button>)}</div>:<EmptyState title="当前收藏夹为空" body="可从基金、基金经理或证券研究页加入对象。"/>}
      </section>
      <aside className="research-context">{active?<>
        <div className="research-context-head"><div><small>{typeLabel(active.entity_type)} · {active.entity_id}</small><h2>{active.entity_name}</h2></div><button onClick={()=>remove(active)} title="移出收藏"><Trash2 size={16}/></button></div>
        <label>研究笔记<textarea key={active.item_id} defaultValue={active.note||''} onBlur={e=>{if(e.target.value!==(active.note||''))saveNote(active,e.target.value)}} placeholder="记录判断、待验证问题或后续动作"/></label>
        <div className="context-actions"><button className="primary-action" onClick={()=>navigate(routeFor(active))}>打开研究页</button></div>
      </>:<EmptyState title="未选择研究对象" body="选择一项后可查看笔记和继续研究。"/>}</aside>
    </div>}

    {tab==='monitors'&&<div className="grid two-wide">
      <Panel title="监控规则" meta={<button className="panel-action" onClick={evaluate}><RefreshCw size={13}/>刷新判断</button>}>
        {rules.length?<div className="monitor-rule-list">{rules.map(r=><div key={r.rule_id}><button className={`rule-toggle ${Number(r.enabled)?'on':''}`} onClick={()=>toggleRule(r)} aria-label={Number(r.enabled)?'停用监控':'启用监控'}><i/></button><div><b>{r.entity_name}</b><small>{metricLabel(r.entity_type,r.metric,meta)} {r.operator} {Number(r.threshold).toFixed(2)}</small></div><span>{r.last_value==null?'尚未判断':`当前 ${Number(r.last_value).toFixed(2)}`}</span><button className="icon-action" onClick={async()=>{await api.deleteMonitor(r.rule_id);setRules(xs=>xs.filter(x=>x.rule_id!==r.rule_id));setOverview(await api.workspace());push({kind:'success',title:'监控已删除'})}}><Trash2 size={14}/></button></div>)}</div>:<EmptyState title="还没有监控规则" body="可在基金或证券研究页按指标阈值创建监控。"/>}
      </Panel>
      <Panel title="触发记录" meta={<button className="panel-action" onClick={async()=>{await api.markEventsSeen([]);setEvents(xs=>xs.map(x=>({...x,seen:1})));setOverview({...overview,unseen_events:0})}}><CheckCircle2 size={13}/>全部已读</button>}>
        {events.length?<div className="monitor-event-list">{events.map(e=><button key={e.event_id} className={Number(e.seen)?'seen':''} onClick={()=>navigate(e.entity_type==='fund'?`/funds?code=${encodeURIComponent(e.entity_id)}`:`/explorer?security=${encodeURIComponent(e.entity_id)}`)}><i/><div><b>{e.entity_name}</b><small>{metricLabel(e.entity_type,e.metric,meta)} · {e.period}</small></div><strong>{Number(e.value).toFixed(2)}</strong><span>{e.operator} {Number(e.threshold).toFixed(2)}</span></button>)}</div>:<EmptyState title="暂无触发记录" body="监控条件满足后会保留报告期级记录。"/>}
      </Panel>
    </div>}

    {tab==='recents'&&<div className="grid two-equal">
      <Panel title="最近研究">{recents.length?<div className="recent-list">{recents.map(x=><button key={`${x.entity_type}-${x.entity_id}`} onClick={()=>navigate(x.route||routeFor(x))}><span className={`entity-type ${x.entity_type}`}>{typeLabel(x.entity_type)}</span><div><b>{x.entity_name}</b><small>{x.entity_id}</small></div><em>{x.open_count} 次</em></button>)}</div>:<EmptyState title="暂无最近研究" body="打开研究对象后会记录在这里。"/>}</Panel>
      <Panel title="操作记录">{audit.length?<div className="audit-list">{audit.slice(0,40).map((x:any)=><div key={x.audit_id}><i/><div><b>{auditLabel(x.action)}</b><small>{x.entity_type||'系统'} {x.entity_id||''}</small></div><time>{x.created_at?.replace('T',' ')}</time></div>)}</div>:<EmptyState title="暂无操作记录" body="收藏、监控和采集等关键操作会写入记录。"/>}</Panel>
    </div>}

    {manage==='rename'&&<div className="modal-backdrop" onMouseDown={()=>setManage(null)}><div className="dialog small-dialog" onMouseDown={e=>e.stopPropagation()}><div className="dialog-head"><h3>重命名收藏夹</h3><button onClick={()=>setManage(null)}><X size={17}/></button></div><div className="dialog-body"><label>名称<input autoFocus value={manageName} onChange={e=>setManageName(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')renameCollection()}}/></label></div><div className="dialog-foot"><button className="ghost-action" onClick={()=>setManage(null)}>取消</button><button className="primary-action" onClick={renameCollection}>保存</button></div></div></div>}
    {manage==='delete'&&<div className="modal-backdrop" onMouseDown={()=>setManage(null)}><div className="dialog small-dialog" onMouseDown={e=>e.stopPropagation()}><div className="dialog-head"><h3>删除收藏夹</h3><button onClick={()=>setManage(null)}><X size={17}/></button></div><div className="dialog-body"><div className="danger-confirm"><b>{currentCollection?.name}</b><span>收藏夹及其中的研究笔记会删除。原始基金和持仓数据不会受影响。</span></div></div><div className="dialog-foot"><button className="ghost-action" onClick={()=>setManage(null)}>取消</button><button className="danger-action" onClick={deleteCollection}>删除</button></div></div></div>}
  </>;
}
