import { useEffect,useState } from 'react';
import { Database,Info } from 'lucide-react';
import { api } from '../lib/api';
import { useAppStore } from '../store/useAppStore';

export function DataContext({period,basis,sampleFunds,updatedAt,note}:{period?:string|null;basis?:string|null;sampleFunds?:number|null;updatedAt?:string|null;note?:string|null}){
 const mode=useAppStore(s=>s.mode);const[health,setHealth]=useState<any>(null);
 useEffect(()=>{if(mode==='local')api.health().then(setHealth).catch(()=>setHealth(null));else setHealth(null)},[mode]);
 const updated=updatedAt||health?.last_holdings_update||health?.last_market_update;
 return <div className="data-context"><div className="data-context-main"><Database size={13}/><span>{period||health?.latest_holding_period||'当前样本'}</span>{basis&&<span>{basis}</span>}{sampleFunds!=null&&<span>可比基金 {Number(sampleFunds).toLocaleString()}</span>}{updated&&<span>更新 {String(updated).slice(0,16).replace('T',' ')}</span>}</div>{note&&<span className="data-context-note" title={note}><Info size={12}/>口径说明</span>}</div>;
}
