import { BellPlus, LoaderCircle, X } from "lucide-react";
import { useEffect,useState } from "react";
import { api } from "../lib/api";
import { useToastStore } from "../store/useToastStore";

export function MonitorRuleButton({entityType,entityId,entityName,current={},compact=false}:{entityType:"fund"|"security";entityId:string;entityName:string;current?:Record<string,number|null|undefined>;compact?:boolean}){
  const[open,setOpen]=useState(false);const[meta,setMeta]=useState<any>({});const[metric,setMetric]=useState("");const[op,setOp]=useState(">=");const[threshold,setThreshold]=useState(0);const[busy,setBusy]=useState(false);const push=useToastStore(s=>s.push);
  useEffect(()=>{if(!open)return;api.monitorMeta().then(m=>{setMeta(m);const keys=Object.keys(m?.[entityType]||{});const k=keys[0]||'';setMetric(k);const v=current[k];setThreshold(v==null?0:Number(v))}).catch(()=>setMeta({}))},[open,entityType]);
  useEffect(()=>{if(metric){const v=current[metric];if(v!=null&&Number.isFinite(Number(v)))setThreshold(Number(v))}},[metric]);
  const save=async()=>{if(!metric||busy)return;setBusy(true);try{await api.createMonitor({name:`${entityName} · ${meta?.[entityType]?.[metric]||metric}`,entity_type:entityType,entity_id:entityId,entity_name:entityName,metric,operator:op,threshold:Number(threshold)});push({kind:'success',title:'监控已创建'});setOpen(false)}catch(e:any){push({kind:'error',title:'创建监控失败',message:e?.message||String(e)})}finally{setBusy(false)}};
  return <>
    <button className={`secondary-action ${compact?'compact':''}`} disabled={busy} onClick={(e)=>{e.stopPropagation();setOpen(true)}}>{busy?<LoaderCircle className="spin" size={15}/>:<BellPlus size={15}/>} {!compact&&<span>监控</span>}</button>
    {open&&<div className="modal-backdrop" onMouseDown={()=>!busy&&setOpen(false)}><div className="dialog" onMouseDown={e=>e.stopPropagation()}>
      <div className="dialog-head"><div><small>{entityType==='fund'?'基金监控':'证券监控'}</small><h3>{entityName}</h3></div><button disabled={busy} onClick={()=>setOpen(false)}><X size={17}/></button></div>
      <div className="dialog-body"><label>指标<select disabled={busy} value={metric} onChange={e=>setMetric(e.target.value)}>{Object.entries(meta?.[entityType]||{}).map(([k,v])=><option key={k} value={k}>{String(v)}</option>)}</select></label><div className="rule-grid"><label>条件<select disabled={busy} value={op} onChange={e=>setOp(e.target.value)}><option>&gt;=</option><option>&gt;</option><option>&lt;=</option><option>&lt;</option></select></label><label>阈值<input disabled={busy} type="number" step="0.1" value={threshold} onChange={e=>setThreshold(Number(e.target.value))}/></label></div><div className="rule-current">当前值 <b>{current[metric]==null?'—':Number(current[metric]).toFixed(2)}</b></div></div>
      <div className="dialog-foot"><button className="ghost-action" disabled={busy} onClick={()=>setOpen(false)}>取消</button><button className="primary-action" disabled={busy} onClick={save}>{busy?<><LoaderCircle className="spin" size={14}/>创建中</>:<>创建监控</>}</button></div>
    </div></div>}
  </>
}
