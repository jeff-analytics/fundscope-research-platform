import type { Mode,SmartMoneyResponse,SecurityDetailResponse } from "../types";
function friendlyMessage(raw:any,status:number){const m=raw?.detail?.message||raw?.detail||raw?.message;if(typeof m==='string'&&m.trim())return m;if(status===404)return '没有找到对应数据';if(status>=500)return '数据服务暂时无法完成该请求';return '请求未完成，请稍后重试'}
const sleep=(ms:number)=>new Promise(r=>setTimeout(r,ms));
const responseCache=new Map<string,{expires:number,staleUntil:number,value:any}>();
const pendingGets=new Map<string,Promise<any>>();
export function invalidateApiCache(match=''){
  for(const k of [...responseCache.keys()])if(!match||k.includes(match))responseCache.delete(k);
}
async function cachedGet<T>(url:string,ttlMs=8000,timeoutMs=30000,staleMs=180000):Promise<T>{
  const now=Date.now();const cached=responseCache.get(url);
  if(cached&&cached.expires>now)return cached.value as T;
  const pending=pendingGets.get(url);if(pending)return pending as Promise<T>;
  const task=request<T>(url,undefined,timeoutMs).then(value=>{responseCache.set(url,{expires:Date.now()+ttlMs,staleUntil:Date.now()+staleMs,value});return value}).catch(err=>{
    const old=responseCache.get(url);if(old&&old.staleUntil>Date.now())return old.value as T;throw err;
  }).finally(()=>pendingGets.delete(url));
  pendingGets.set(url,task);return task;
}
async function request<T>(url:string,options?:RequestInit,timeoutMs=30000):Promise<T>{
  const method=String(options?.method||'GET').toUpperCase();
  const attempts=method==='GET'?3:1;
  let last:any=null;
  for(let i=0;i<attempts;i++){
    const c=new AbortController();const t=setTimeout(()=>c.abort(),timeoutMs);
    try{
      const res=await fetch(url,{...options,signal:c.signal,headers:{'Accept':'application/json',...(options?.headers||{})}});
      const text=await res.text();let p:any=null;if(text){try{p=JSON.parse(text)}catch{}}
      if(!res.ok){const err:any=new Error(friendlyMessage(p,res.status));err.status=res.status;throw err}
      return p as T;
    }catch(e:any){
      last=e;const transient=e?.name==='AbortError'||!e?.status||[502,503,504].includes(Number(e?.status));
      if(i<attempts-1&&transient){await sleep(i===0?220:650);continue}
      if(e?.name==='AbortError')throw new Error('数据响应时间较长，请稍后重试');
      throw e;
    }finally{clearTimeout(t)}
  }
  throw last||new Error('请求未完成，请稍后重试');
}
const post=(url:string,body:any,timeout=30000)=>request<any>(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)},timeout);
export const api={
 invalidateCache:(match='')=>invalidateApiCache(match),

 session:()=>cachedGet<any>('/api/session',30000,12000),
 search:(mode:Mode,q:string,limit=8)=>request<any>(`/api/search?mode=${mode}&q=${encodeURIComponent(q)}&limit=${limit}`),
 explorerManagers:(mode:Mode,period='')=>cachedGet<any>(`/api/explorer/managers?mode=${mode}&period=${encodeURIComponent(period)}`,600000,60000,1800000),
 fundPeerLens:(mode:Mode,code:string,period='',universe='all')=>cachedGet<any>(`/api/funds/${encodeURIComponent(code)}/peer-lens?mode=${mode}&period=${encodeURIComponent(period)}&universe=${encodeURIComponent(universe)}`,300000,60000,1800000),
 workspace:()=>request<any>('/api/workspace'),
 collections:()=>request<any[]>('/api/workspace/collections'),
 createCollection:(name:string)=>post('/api/workspace/collections',{name}),
 renameCollection:(id:string,name:string)=>request<any>(`/api/workspace/collections/${encodeURIComponent(id)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})}),
 deleteCollection:(id:string)=>request<any>(`/api/workspace/collections/${encodeURIComponent(id)}`,{method:'DELETE'}),
 collectionItems:(id:string)=>request<any[]>(`/api/workspace/collections/${encodeURIComponent(id)}/items`),
 addResearchItem:(collectionId:string,body:any)=>post(`/api/workspace/collections/${encodeURIComponent(collectionId)}/items`,body),
 updateResearchItem:(itemId:string,body:any)=>request<any>(`/api/workspace/items/${encodeURIComponent(itemId)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
 removeResearchItem:(itemId:string)=>request<any>(`/api/workspace/items/${encodeURIComponent(itemId)}`,{method:'DELETE'}),
 touchRecent:(body:any)=>post('/api/workspace/recents',body),
 recents:(limit=30)=>request<any[]>(`/api/workspace/recents?limit=${limit}`),
 savedViews:(viewType='')=>request<any[]>(`/api/workspace/views?view_type=${encodeURIComponent(viewType)}`),
 saveView:(body:any)=>post('/api/workspace/views',body),
 deleteView:(id:string)=>request<any>(`/api/workspace/views/${encodeURIComponent(id)}`,{method:'DELETE'}),
 monitorMeta:()=>request<any>('/api/workspace/monitors/meta'),
 monitors:()=>request<any[]>('/api/workspace/monitors'),
 createMonitor:(body:any)=>post('/api/workspace/monitors',body),
 updateMonitor:(id:string,body:any)=>request<any>(`/api/workspace/monitors/${encodeURIComponent(id)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
 deleteMonitor:(id:string)=>request<any>(`/api/workspace/monitors/${encodeURIComponent(id)}`,{method:'DELETE'}),
 evaluateMonitors:(mode='local')=>request<any>(`/api/workspace/monitors/evaluate?mode=${mode}`,{method:'POST'},60000),
 monitorEvents:(limit=100,unseenOnly=false)=>request<any[]>(`/api/workspace/events?limit=${limit}&unseen_only=${unseenOnly}`),
 markEventsSeen:(eventIds:string[]=[])=>post('/api/workspace/events/seen',{event_ids:eventIds}),
 audit:(limit=80)=>request<any[]>(`/api/workspace/audit?limit=${limit}`),
 overview:(mode:Mode)=>cachedGet<any>(`/api/overview?mode=${mode}`,120000,30000,600000),
 funds:(mode:Mode,q='',researchOnly=true)=>cachedGet<any[]>(`/api/funds?mode=${mode}&q=${encodeURIComponent(q)}&research_only=${researchOnly}`,120000,30000,600000),
 fund:(mode:Mode,code:string)=>cachedGet<any>(`/api/funds/${encodeURIComponent(code)}?mode=${mode}`,300000,45000,1800000),
 fundAdvanced:(mode:Mode,code:string)=>cachedGet<any>(`/api/funds/${encodeURIComponent(code)}/advanced?mode=${mode}`,300000,60000,1800000),
 fundProfile:(mode:Mode,code:string,refresh=false)=>refresh?request<any>(`/api/funds/${encodeURIComponent(code)}/profile?mode=${mode}&refresh=true`):cachedGet<any>(`/api/funds/${encodeURIComponent(code)}/profile?mode=${mode}&refresh=false`,300000,30000,1800000),
 majorChanges:(mode:Mode,code:string,years:number[]=[])=>request<any[]>(`/api/funds/${encodeURIComponent(code)}/major-changes?mode=${mode}&years=${encodeURIComponent(years.join(','))}`),
 managers:(mode:Mode,q='')=>request<any[]>(`/api/managers?mode=${mode}&q=${encodeURIComponent(q)}`),
 managerCatalog:(mode:Mode)=>cachedGet<any[]>(`/api/managers/catalog?mode=${mode}`,600000,30000,1800000),
 managerById:(mode:Mode,id:string)=>cachedGet<any>(`/api/managers/id/${encodeURIComponent(id)}?mode=${mode}`,300000,60000,1800000),
 manager:(mode:Mode,name:string)=>cachedGet<any>(`/api/managers/${encodeURIComponent(name)}?mode=${mode}`,300000,60000,1800000),
 managerStyle:(mode:Mode,name:string,company='')=>cachedGet<any>(`/api/managers/${encodeURIComponent(name)}/style?mode=${mode}&company=${encodeURIComponent(company)}`,300000,60000,1800000),
 smartMoney:(mode:Mode,period='',comparePeriod='')=>cachedGet<SmartMoneyResponse>(`/api/smart-money?mode=${mode}&period=${encodeURIComponent(period)}&compare_period=${encodeURIComponent(comparePeriod)}`,300000,75000,1800000),
 smartMoneyHistory:(mode:Mode,period:string,codes:string[],window=8)=>cachedGet<any>(`/api/smart-money/history?mode=${mode}&period=${encodeURIComponent(period)}&codes=${encodeURIComponent(codes.slice(0,12).join(','))}&window=${Math.max(2,Math.min(window,20))}`,600000,120000,1800000),
 institutionalMigration:(mode:Mode)=>cachedGet<any>(`/api/institutional-migration?mode=${mode}`,300000,45000,1800000),
 compare:(mode:Mode,a:string,b:string,q:string)=>cachedGet<any>(`/api/compare?mode=${mode}&a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}&quarter=${encodeURIComponent(q)}`,300000,60000,1800000),
 explorerFunds:(mode:Mode,period='')=>cachedGet<any>(`/api/explorer/funds?mode=${mode}&period=${encodeURIComponent(period)}`,600000,60000,1800000),
 explorerSecurities:(mode:Mode,period='')=>cachedGet<any>(`/api/explorer/securities?mode=${mode}&period=${encodeURIComponent(period)}`,600000,60000,1800000),
 securityDetail:(mode:Mode,code:string,period='')=>request<SecurityDetailResponse>(`/api/explorer/securities/${encodeURIComponent(code)}?mode=${mode}&period=${encodeURIComponent(period)}`,undefined,60000),
 fundPeers:(mode:Mode,code:string,quarter='',limit=15)=>cachedGet<any>(`/api/funds/${encodeURIComponent(code)}/peers?mode=${mode}&quarter=${encodeURIComponent(quarter)}&limit=${limit}`,300000,60000,1800000),
 fundRankTrajectory:(mode:Mode,code:string,maxNames=8,maxPeriods=12)=>cachedGet<any>(`/api/funds/${encodeURIComponent(code)}/rank-trajectory?mode=${mode}&max_names=${maxNames}&max_periods=${maxPeriods}`,300000,60000,1800000),
 presence:()=>cachedGet<any>('/api/data/presence',60000,5000),health:()=>request<any>('/api/data/health'),validate:()=>request<any>('/api/data/validate'),quality:()=>request<any>('/api/data/quality'),fundMaster:()=>request<any>('/api/data/fund-master'),storage:()=>request<any>('/api/data/storage'),openDataFolder:()=>request<any>('/api/data/open-folder',{method:'POST'}),
 startFunds:()=>request<any>('/api/tasks/funds',{method:'POST'}),startManagers:()=>request<any>('/api/tasks/managers',{method:'POST'}),startFundMaster:()=>request<any>('/api/tasks/fund-master',{method:'POST'}),
 startMarket:(quarters:number,force=false,strategy='standard')=>post('/api/tasks/market',{quarters,force,strategy}),
 holdingsPlan:(years:number[],limit:number|null,force=false,since_inception=false,fund_code:string|null=null)=>post('/api/data/holdings-plan',{years,limit,force,since_inception,fund_code}),
 startHoldings:(years:number[],limit:number|null,strategy='standard',force=false,since_inception=false,fund_code:string|null=null)=>post('/api/tasks/holdings',{years,limit,strategy,force,since_inception,fund_code}),
 startFundHistory:(fund_code:string,strategy='standard')=>post('/api/tasks/holdings',{years:[],limit:1,strategy,force:false,since_inception:true,fund_code}),
 startSecurityMaster:(limit:number|null,strategy='standard',deep=false)=>post('/api/tasks/security-master',{limit,strategy,deep}),
 startIncremental:(strategy='standard')=>post('/api/tasks/incremental',{strategy}),
 startReturnGap:(fund_code:string,years_back=3,strategy='standard')=>post('/api/tasks/return-gap',{fund_code,years_back,strategy}),
 startMajorChanges:(fund_code:string,years:number[])=>post('/api/tasks/major-changes',{fund_code,years}),
 collectionProfiles:()=>request<any[]>('/api/data/collection-profiles'),tasks:(limit=30)=>request<any[]>(`/api/tasks?limit=${limit}`),task:(id:string)=>request<any>(`/api/tasks/${id}`),pauseTask:(id:string)=>request<any>(`/api/tasks/${id}/pause`,{method:'POST'}),resumeTask:(id:string)=>request<any>(`/api/tasks/${id}/resume`,{method:'POST'}),cancelTask:(id:string)=>request<any>(`/api/tasks/${id}/cancel`,{method:'POST'}),
 importDb:async(file:File)=>{const fd=new FormData();fd.append('file',file);return request<any>('/api/data/import-db',{method:'POST',body:fd},120000)},
 snapshots:()=>request<any[]>('/api/data/snapshots'),createSnapshot:()=>request<any>('/api/data/snapshots',{method:'POST'}),restoreSnapshot:(name:string)=>request<any>(`/api/data/snapshots/${encodeURIComponent(name)}/restore`,{method:'POST'},120000)
};
