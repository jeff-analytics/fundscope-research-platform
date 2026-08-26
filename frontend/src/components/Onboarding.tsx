import { Bookmark, Search, Telescope, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
const KEY='fundscope-v9-2-onboarding';
export function Onboarding(){
  const[open,setOpen]=useState(false);const navigate=useNavigate();
  useEffect(()=>{try{if(localStorage.getItem(KEY)!=='done')setOpen(true)}catch{}},[]);
  const close=()=>{try{localStorage.setItem(KEY,'done')}catch{}setOpen(false)};
  const go=(route:string)=>{close();navigate(route)};
  if(!open)return null;
  return <div className="modal-backdrop onboarding-backdrop" onMouseDown={close}><div className="onboarding-card" onMouseDown={e=>e.stopPropagation()}>
    <div className="dialog-head"><div><small>FundScope v9.2.2</small><h3>研究工作区已升级</h3></div><button onClick={close}><X size={17}/></button></div>
    <div className="onboarding-grid">
      <button onClick={()=>{close();window.dispatchEvent(new Event('fundscope:search'))}}><Search size={20}/><b>全局检索</b><span>基金、基金经理与证券统一搜索</span><kbd>Ctrl K</kbd></button>
      <button onClick={()=>go('/explorer')}><Telescope size={20}/><b>研究探索</b><span>横截面筛选、保存视图与下钻</span><kbd>Alt 2</kbd></button>
      <button onClick={()=>go('/workspace')}><Bookmark size={20}/><b>我的研究</b><span>收藏、笔记、监控与最近研究</span><kbd>Alt 5</kbd></button>
    </div>
    <div className="onboarding-foot"><button className="ghost-action" onClick={close}>关闭</button><button className="primary-action" onClick={()=>go('/explorer')}>进入研究探索</button></div>
  </div></div>
}
