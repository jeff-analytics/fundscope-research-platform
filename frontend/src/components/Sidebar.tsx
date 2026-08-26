import { NavLink } from "react-router-dom";
import { Activity, Bookmark, Building2, Database, GitCompareArrows, Radar, UserRoundSearch, Telescope } from "lucide-react";
import { useAppStore } from "../store/useAppStore";
const research=[{to:"/",label:"市场脉搏",icon:Activity},{to:"/explorer",label:"研究探索",icon:Telescope},{to:"/funds",label:"基金研究",icon:Building2},{to:"/managers",label:"基金经理",icon:UserRoundSearch}];
const intelligence=[{to:"/workspace",label:"我的研究",icon:Bookmark},{to:"/smart-money",label:"机构共识",icon:Radar},{to:"/compare",label:"基金对比",icon:GitCompareArrows}];
export function Sidebar(){
  const role=useAppStore(s=>s.role);const link=(item:any)=>{const Icon=item.icon;return <NavLink key={item.to} to={item.to} end={item.to==="/"} className={({isActive})=>`nav-link ${isActive?"active":""}`}><Icon size={18} strokeWidth={1.75}/><span>{item.label}</span></NavLink>};
  return <aside className="sidebar"><div className="brand-row"><img className="brand-logo" src="/fundscope-mark.svg" alt="FundScope"/><div className="brand-copy"><b>FundScope</b></div></div><nav><div className="nav-section"><div className="nav-section-label">研究</div>{research.map(link)}</div><div className="nav-section"><div className="nav-section-label">工作区</div>{intelligence.map(link)}</div></nav><div className="sidebar-bottom">{role==='maintainer'&&<NavLink to="/data" className={({isActive})=>`nav-link ${isActive?"active":""}`}><Database size={18} strokeWidth={1.75}/><span>数据中心</span></NavLink>}<div className="sidebar-footnote">v9.2.2</div></div></aside>
}
