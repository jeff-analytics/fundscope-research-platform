export type DisclosureHolding={quarter:string;stock_code:string;weight_pct?:number|null;disclosure_scope?:string|null;[key:string]:unknown};
export const periodScope=(period:string,explicit?:string|null)=>{
 const x=String(explicit||'').toLowerCase();if(x.includes('top10')||x.includes('前十')||x.includes('十大'))return 'top10';if(x.includes('full')||x.includes('完整'))return 'full';
 const m=String(period||'').match(/Q([1-4])/i);const q=m?Number(m[1]):0;return q===1||q===3?'top10':q===2||q===4?'full':'unknown';
};
export const top10=<T extends DisclosureHolding>(rows:T[])=>rows.slice().sort((a,b)=>Number(b.weight_pct||0)-Number(a.weight_pct||0)).slice(0,10);
export const comparableSnapshots=<T extends DisclosureHolding>(oldRows:T[],newRows:T[],oldPeriod:string,newPeriod:string)=>{
 const oldScope=periodScope(oldPeriod,oldRows[0]?.disclosure_scope as string|undefined);const newScope=periodScope(newPeriod,newRows[0]?.disclosure_scope as string|undefined);const basis=oldScope==='full'&&newScope==='full'?'full_portfolio':'top10_comparable';
 return{oldRows:basis==='top10_comparable'?top10(oldRows):oldRows,newRows:basis==='top10_comparable'?top10(newRows):newRows,basis,label:basis==='top10_comparable'?'Top 10 Comparable':'Full Portfolio'};
};
export const filterConsensus=<T extends {consensus_level?:string;consensus_trend?:string}>(rows:T[],level:string,trend:string)=>rows.filter(x=>(level==='全部'||x.consensus_level===level)&&(trend==='全部'||x.consensus_trend===trend));
