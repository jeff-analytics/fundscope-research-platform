import { Activity, Bookmark, Building2, Telescope, UserRoundSearch } from "lucide-react";
import { NavLink } from "react-router-dom";
const items=[['/',Activity,'脉搏'],['/explorer',Telescope,'探索'],['/funds',Building2,'基金'],['/managers',UserRoundSearch,'经理'],['/workspace',Bookmark,'研究']];
export function MobileNav(){return <nav className="mobile-nav">{items.map(([to,I,label]:any)=><NavLink key={to} to={to} end={to==='/'} className={({isActive})=>isActive?'active':''}><I size={18}/><span>{label}</span></NavLink>)}</nav>}
