export function MetricStrip({items}:{items:Array<{label:string;value:string|number;sub?:string;accent?:"up"|"down"|"neutral"}>}){
  return <div className="metric-strip">{items.map((x,i)=>
    <div className="metric-cell" key={`${x.label}-${i}`}>
      <span className="metric-label">{x.label}</span>
      <b className={`metric-value ${x.accent||""}`}>{x.value}</b>
      {x.sub&&<small>{x.sub}</small>}
    </div>
  )}</div>
}
