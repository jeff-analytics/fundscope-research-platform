export function downloadCsv(filename:string,rows:any[]){
  if(!rows?.length)return;
  const keys=[...new Set(rows.flatMap(r=>Object.keys(r).filter(k=>!['meta','tags'].includes(k))) )];
  const esc=(v:any)=>{const s=Array.isArray(v)?v.join('|'):v==null?'':String(v);return `"${s.replace(/"/g,'""')}"`};
  const csv='\ufeff'+[keys.map(esc).join(','),...rows.map(r=>keys.map(k=>esc(r[k])).join(','))].join('\r\n');
  const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename;a.click();URL.revokeObjectURL(url);
}
