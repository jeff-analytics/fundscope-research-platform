export const formatNumber=(value:unknown,digits=2)=>value==null||!Number.isFinite(Number(value))?'—':Number(value).toFixed(digits);
export const formatPercent=(value:unknown,digits=2)=>value==null||!Number.isFinite(Number(value))?'—':`${Number(value).toFixed(digits)}%`;
export const formatSigned=(value:unknown,digits=2,suffix='')=>{if(value==null||!Number.isFinite(Number(value)))return '—';const n=Number(value);return `${n>0?'+':''}${n.toFixed(digits)}${suffix}`};
export const formatMoneyYi=(value:unknown,digits=2)=>value==null||!Number.isFinite(Number(value))?'—':`${Number(value).toFixed(digits)} 亿`;
