import { Database, FlaskConical, Keyboard, ChevronDown } from "lucide-react";
import { GlobalSearch } from "./GlobalSearch";
import { useAppStore } from "../store/useAppStore";
export function TopBar(){
 const mode=useAppStore(s=>s.mode);const setMode=useAppStore(s=>s.setMode);
 return <header className="topbar"><GlobalSearch/><div className="top-actions"><button className="top-icon-action" title="快捷键" onClick={()=>window.dispatchEvent(new Event('fundscope:shortcuts'))}><Keyboard size={16}/></button><details className="data-source-menu"><summary>{mode==='local'?<Database size={14}/>:<FlaskConical size={14}/>}<span>{mode==='local'?'本地研究':'演示数据'}</span><ChevronDown size={13}/></summary><div className="data-source-pop"><button className={mode==='local'?'active':''} onClick={()=>setMode('local')}><Database size={14}/><div><b>本地研究</b><small>使用已采集的真实基金数据</small></div></button><button className={mode==='demo'?'active':''} onClick={()=>setMode('demo')}><FlaskConical size={14}/><div><b>演示数据</b><small>仅用于查看产品交互</small></div></button></div></details></div></header>
}
