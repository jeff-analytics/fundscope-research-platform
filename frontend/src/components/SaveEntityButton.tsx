import { BookmarkPlus, Check, FolderPlus, LoaderCircle, Plus, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useToastStore } from "../store/useToastStore";

export function SaveEntityButton({entityType,entityId,entityName,meta={},compact=false}:{entityType:"fund"|"security"|"manager";entityId:string;entityName:string;meta?:any;compact?:boolean}){
  const[open,setOpen]=useState(false);const[collections,setCollections]=useState<any[]>([]);const[creating,setCreating]=useState(false);const[name,setName]=useState("");const[busy,setBusy]=useState(false);const ref=useRef<HTMLDivElement>(null);const push=useToastStore(s=>s.push);
  const load=async()=>{try{setCollections(await api.collections())}catch{setCollections([])}};
  useEffect(()=>{if(open)load()},[open]);
  useEffect(()=>{const fn=(e:MouseEvent)=>{if(open&&ref.current&&!ref.current.contains(e.target as Node))setOpen(false)};document.addEventListener('mousedown',fn);return()=>document.removeEventListener('mousedown',fn)},[open]);
  const save=async(cid:string)=>{if(busy)return;setBusy(true);try{await api.addResearchItem(cid,{entity_type:entityType,entity_id:entityId,entity_name:entityName,meta});push({kind:'success',title:'已加入研究收藏'});setOpen(false)}catch(e:any){push({kind:'error',title:'保存失败',message:e?.message||String(e)})}finally{setBusy(false)}};
  const create=async()=>{if(!name.trim()||busy)return;setBusy(true);try{const c=await api.createCollection(name.trim());setCollections(x=>[c,...x]);setName("");setCreating(false);await api.addResearchItem(c.collection_id,{entity_type:entityType,entity_id:entityId,entity_name:entityName,meta});push({kind:'success',title:'收藏夹已创建并加入研究'});setOpen(false)}catch(e:any){push({kind:'error',title:'创建失败',message:e?.message||String(e)})}finally{setBusy(false)}};
  return <div className="entity-save" ref={ref}>
    <button className={`secondary-action ${compact?'compact':''}`} disabled={busy} onClick={(e)=>{e.stopPropagation();setOpen(v=>!v)}} title="加入研究收藏">{busy?<LoaderCircle className="spin" size={15}/>:<BookmarkPlus size={15}/>} {!compact&&<span>收藏</span>}</button>
    {open&&<div className="entity-save-menu" onClick={e=>e.stopPropagation()}>
      <div className="entity-save-head"><b>加入收藏夹</b><button onClick={()=>setOpen(false)}><X size={14}/></button></div>
      <div className="entity-save-list">{collections.map(c=><button key={c.collection_id} disabled={busy} onClick={()=>save(c.collection_id)}><span>{c.name}</span><small>{c.item_count||0}</small><Check size={13}/></button>)}</div>
      {creating?<div className="entity-save-create"><input autoFocus disabled={busy} value={name} onChange={e=>setName(e.target.value)} placeholder="收藏夹名称" onKeyDown={e=>{if(e.key==='Enter')create();if(e.key==='Escape')setCreating(false)}}/><button disabled={busy} onClick={create}>{busy?<LoaderCircle className="spin" size={14}/>:<Plus size={14}/>}</button></div>:<button className="entity-save-new" disabled={busy} onClick={()=>setCreating(true)}><FolderPlus size={14}/>新建收藏夹</button>}
    </div>}
  </div>
}
