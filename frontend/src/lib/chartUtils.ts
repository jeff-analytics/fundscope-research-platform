export function periodKey(value:string){
  const m=String(value||"").match(/(20\d{2})Q([1-4])/i);
  return m?Number(m[1])*10+Number(m[2]):0;
}

export function sortPeriods(values:string[]){
  return [...new Set(values.filter(Boolean))].sort((a,b)=>periodKey(a)-periodKey(b));
}

export function stripFlowSuffix(name:string){
  return String(name||"").replace(/\s*·\s*[增减]$/,"" );
}

export function compactLabel(value:string,max=16){
  const text=String(value||"");
  return text.length>max?`${text.slice(0,max-1)}…`:text;
}

export function categoryGrid(left=18,right=18,top=16,bottom=24){
  return {left,right,top,bottom,containLabel:true};
}
