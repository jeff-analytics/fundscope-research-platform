import { Chart } from './Chart';

function pct(v:any){return v==null?'—':`${Number(v).toFixed(2)}%`}

export function RebalanceBoard({activity}:{activity:any[]}){
  const rows=(activity||[]).slice().sort((a,b)=>Math.abs(Number(b.delta||0))-Math.abs(Number(a.delta||0))).slice(0,12);
  const entered=(activity||[]).filter(x=>x.activity==='新进入披露');
  const exited=(activity||[]).filter(x=>x.activity==='退出披露');
  const up=(activity||[]).filter(x=>x.activity==='权重上升').sort((a,b)=>b.delta-a.delta);
  const down=(activity||[]).filter(x=>x.activity==='权重下降').sort((a,b)=>a.delta-b.delta);
  const max=Math.max(1,...rows.flatMap(x=>[Number(x.weight_old||0),Number(x.weight_new||0)]));
  const option:any={
    tooltip:{
      trigger:'item',confine:true,backgroundColor:'#fff',borderColor:'#dfe3e8',textStyle:{color:'#344054'},
      formatter:(p:any)=>{const r=rows[p.dataIndex];if(!r)return'';return `<b>${r.stock_name}</b><br/>前期 ${pct(r.weight_old)}<br/>本期 ${pct(r.weight_new)}<br/>变化 ${Number(r.delta)>=0?'+':''}${Number(r.delta).toFixed(2)} pp`}
    },
    grid:{left:112,right:74,top:14,bottom:36},
    xAxis:{type:'value',min:0,max:Math.ceil(max*1.15),axisLabel:{formatter:'{value}%',color:'#98a2b3'},splitLine:{lineStyle:{color:'#eef0f3'}}},
    yAxis:{type:'category',data:rows.map(x=>x.stock_name),inverse:true,axisLabel:{color:'#344054',fontSize:12},axisLine:{show:false},axisTick:{show:false}},
    series:[{
      type:'custom',silent:false,data:rows.map((r,i)=>[Number(r.weight_old||0),Number(r.weight_new||0),i,Number(r.delta||0)]),
      renderItem:(params:any,api:any)=>{
        const old=Number(api.value(0)||0),cur=Number(api.value(1)||0),idx=Number(api.value(2)),delta=Number(api.value(3)||0);
        const p0=api.coord([old,idx]),p1=api.coord([cur,idx]);const c=delta>=0?'#2f8f70':'#c95b66';
        const xText=Math.min(api.getWidth()-58,Math.max(p0[0],p1[0])+10);
        return {type:'group',children:[
          {type:'line',shape:{x1:p0[0],y1:p0[1],x2:p1[0],y2:p1[1]},style:{stroke:c,lineWidth:5,opacity:.22,lineCap:'round'}},
          {type:'circle',shape:{cx:p0[0],cy:p0[1],r:5},style:{fill:'#fff',stroke:'#98a2b3',lineWidth:2}},
          {type:'circle',shape:{cx:p1[0],cy:p1[1],r:6},style:{fill:c,stroke:'#fff',lineWidth:2,shadowBlur:5,shadowColor:'rgba(16,24,40,.12)'}},
          {type:'text',style:{x:xText,y:p1[1],text:`${delta>=0?'+':''}${delta.toFixed(2)}`,fill:c,font:'600 12px sans-serif',verticalAlign:'middle'}}
        ]}
      }
    }]
  };
  return <div className="rebalance-board">
    <div className="rebalance-summary">
      <div className="enter"><span>新进入披露</span><b>{entered.length}</b><small>{entered.slice(0,3).map(x=>x.stock_name).join(' · ')||'—'}</small></div>
      <div className="increase"><span>权重上升</span><b>{up.length}</b><small>{up[0]?`${up[0].stock_name} +${Number(up[0].delta).toFixed(2)}`:'—'}</small></div>
      <div className="decrease"><span>权重下降</span><b>{down.length}</b><small>{down[0]?`${down[0].stock_name} ${Number(down[0].delta).toFixed(2)}`:'—'}</small></div>
      <div className="exit"><span>退出披露</span><b>{exited.length}</b><small>{exited.slice(0,3).map(x=>x.stock_name).join(' · ')||'—'}</small></div>
    </div>
    <div className="rebalance-main">
      <div className="rebalance-chart">
        <div className="rebalance-legend"><span><i className="old"/>前期权重</span><span><i className="new"/>本期权重</span></div>
        <Chart height={Math.max(390,rows.length*34+55)} option={option}/>
      </div>
      <div className="rebalance-leaders">
        <section><header><b>增配最明显</b><span>pp</span></header>{up.slice(0,6).map((x,i)=><div key={x.stock_code}><em>{String(i+1).padStart(2,'0')}</em><span><b>{x.stock_name}</b><small>{pct(x.weight_old)} → {pct(x.weight_new)}</small></span><strong className="positive">+{Number(x.delta).toFixed(2)}</strong></div>)}</section>
        <section><header><b>减配最明显</b><span>pp</span></header>{down.slice(0,6).map((x,i)=><div key={x.stock_code}><em>{String(i+1).padStart(2,'0')}</em><span><b>{x.stock_name}</b><small>{pct(x.weight_old)} → {pct(x.weight_new)}</small></span><strong className="negative">{Number(x.delta).toFixed(2)}</strong></div>)}</section>
      </div>
    </div>
  </div>
}

export function MajorChangeBoard({rows}:{rows:any[]}){
  const latestYear=Math.max(0,...(rows||[]).map(x=>Number(x.requested_year)||0));
  const filtered=(rows||[]).filter(x=>Number(x.requested_year)===latestYear);
  const buys=filtered.filter(x=>x.direction==='buy').sort((a,b)=>Number(b.amount_wan||0)-Number(a.amount_wan||0)).slice(0,8);
  const sells=filtered.filter(x=>x.direction==='sell').sort((a,b)=>Number(b.amount_wan||0)-Number(a.amount_wan||0)).slice(0,8);
  const max=Math.max(1,...[...buys,...sells].map(x=>Number(x.amount_wan||0)));
  const side=(title:string,data:any[],tone:'buy'|'sell')=><section className={`major-side ${tone}`}><header><b>{title}</b>{latestYear>0&&<span>{latestYear}</span>}</header>{data.map((x,i)=><div key={`${tone}-${x.stock_code}-${i}`}><span className="major-rank">{String(i+1).padStart(2,'0')}</span><span className="major-name"><b>{x.stock_name}</b><small>{x.stock_code}</small></span><span className="major-bar"><i style={{width:`${Math.max(4,Number(x.amount_wan||0)/max*100)}%`}}/></span><strong>{Number(x.amount_wan||0).toLocaleString(undefined,{maximumFractionDigits:0})} 万</strong></div>)}</section>;
  return <div className="major-change-board">{side('累计买入',buys,'buy')}{side('累计卖出',sells,'sell')}</div>
}
