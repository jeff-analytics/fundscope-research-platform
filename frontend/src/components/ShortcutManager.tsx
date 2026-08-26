import { useEffect,useState } from "react";
import { useNavigate } from "react-router-dom";
import { X } from "lucide-react";
const items=[['Alt 1','市场脉搏','/'],['Alt 2','研究探索','/explorer'],['Alt 3','基金研究','/funds'],['Alt 4','基金经理','/managers'],['Alt 5','我的研究','/workspace'],['Alt 6','机构共识','/smart-money'],['Ctrl K','全局搜索',''],['?','快捷键','']];
export function ShortcutManager(){
 const navigate=useNavigate();const[open,setOpen]=useState(false);
 useEffect(()=>{const fn=(e:KeyboardEvent)=>{const el=e.target as HTMLElement;const typing=['INPUT','TEXTAREA','SELECT'].includes(el?.tagName)||el?.isContentEditable;if(typing&&e.key!=='Escape')return;if(e.altKey&&['1','2','3','4','5','6'].includes(e.key)){e.preventDefault();navigate(items[Number(e.key)-1][2])}if(e.key==='?'&&!e.ctrlKey&&!e.metaKey&&!e.altKey){e.preventDefault();setOpen(true)}if(e.key==='Escape')setOpen(false)};const show=()=>setOpen(true);window.addEventListener('keydown',fn);window.addEventListener('fundscope:shortcuts',show as EventListener);return()=>{window.removeEventListener('keydown',fn);window.removeEventListener('fundscope:shortcuts',show as EventListener)}},[navigate]);
 return open?<div className="modal-backdrop" onMouseDown={()=>setOpen(false)}><div className="shortcut-dialog" onMouseDown={e=>e.stopPropagation()}><div className="dialog-head"><h3>快捷操作</h3><button onClick={()=>setOpen(false)}><X size={17}/></button></div><div className="shortcut-grid">{items.map(([key,label])=><div key={key}><kbd>{key}</kbd><span>{label}</span></div>)}</div></div></div>:null;
}
