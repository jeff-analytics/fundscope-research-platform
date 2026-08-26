import { useEffect } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { ErrorBoundary } from "./ErrorBoundary";
import { ToastHost } from "./ToastHost";
import { ShortcutManager } from "./ShortcutManager";
import { MobileNav } from "./MobileNav";
import { Onboarding } from "./Onboarding";
import { api } from "../lib/api";
import { useAppStore } from "../store/useAppStore";

export function AppShell(){
  const setRole=useAppStore(s=>s.setRole);const mode=useAppStore(s=>s.mode);const setMode=useAppStore(s=>s.setMode);
  useEffect(()=>{
    let cancelled=false;const timers:number[]=[];
    api.session().then(x=>{if(!cancelled)setRole(x?.role==='analyst'?'analyst':'maintainer')}).catch(()=>{});
    api.presence().then(p=>{
      if(cancelled)return;const nextMode=(mode==='demo'&&p?.has_local_data)?'local':mode;if(nextMode!==mode)setMode(nextMode);
      // Warm the most frequently opened cross-sectional research entry points after the shell is ready.
      // The API layer deduplicates requests, so an immediate user click simply joins this work.
      const warmMode=nextMode;
      timers.push(window.setTimeout(()=>{api.explorerFunds(warmMode,'').catch(()=>{})},1200));
      timers.push(window.setTimeout(()=>{api.managerCatalog(warmMode).then(rows=>{const first=rows?.[0];if(!first?.manager_id)return;api.managerById(warmMode,first.manager_id).then(d=>api.managerStyle(warmMode,d?.manager?.manager_name||first.manager_name,d?.manager?.company||first.company||'').catch(()=>{})).catch(()=>{})}).catch(()=>{})},2600));
    }).catch(()=>{});
    return()=>{cancelled=true;timers.forEach(t=>window.clearTimeout(t))};
  },[]);
  return (
    <div className="app-shell">
      <Sidebar/>
      <div className="workspace">
        <TopBar/>
        <main className="content"><ErrorBoundary><Outlet/></ErrorBoundary></main>
      </div>
      <MobileNav/><ToastHost/><ShortcutManager/><Onboarding/>
    </div>
  );
}
