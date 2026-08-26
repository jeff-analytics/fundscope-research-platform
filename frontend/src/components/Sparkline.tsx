export function Sparkline({values}:{values:number[]}){
  if(!values.length)return null;
  const w=72,h=22,p=2,min=Math.min(...values),max=Math.max(...values); const span=max-min||1;
  const pts=values.map((v,i)=>`${p+i*(w-2*p)/Math.max(1,values.length-1)},${h-p-(v-min)/span*(h-2*p)}`).join(" ");
  const up=values.at(-1)!>=values[0];
  return <svg className="sparkline" viewBox={`0 0 ${w} ${h}`}><polyline fill="none" stroke={up?"var(--good)":"var(--bad)"} strokeWidth="1.5" points={pts}/></svg>
}
