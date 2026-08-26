import { Chart } from "./Chart";
import { stripFlowSuffix } from "../lib/chartUtils";

export function SankeyChart({nodes,links,height}:{nodes:any[];links:any[];height?:number}){
  const h=height??Math.max(460,Math.min(680,180+Math.max(1,nodes.length)*24));
  const data=(nodes||[]).map((n:any)=>({
    name:n.name,
    itemStyle:{color:n.side==='source'?'#c95b66':'#2f8f70',borderColor:'#fff',borderWidth:1},
    label:{
      position:n.side==='source'?'right':'left',
      align:n.side==='source'?'left':'right',
      distance:8,
      width:150,
      overflow:'truncate',
      color:'#344054',
      fontSize:12,
      backgroundColor:'rgba(255,255,255,.88)',
      padding:[2,4],
      borderRadius:3,
      formatter:(p:any)=>stripFlowSuffix(String(p.name||''))
    }
  }));
  return <Chart height={h} option={{
    tooltip:{
      trigger:'item',confine:true,backgroundColor:'#fff',borderColor:'#dfe3e8',textStyle:{color:'#344054'},
      formatter:(p:any)=>{
        if(p.dataType==='edge') return `${stripFlowSuffix(p.data.source)} → ${stripFlowSuffix(p.data.target)}<br/>配置变化：${Number(p.data.value||0).toFixed(2)} pp`;
        return stripFlowSuffix(String(p.name||''));
      }
    },
    series:[{
      type:'sankey',left:26,right:26,top:24,bottom:24,nodeAlign:'justify',layoutIterations:64,
      nodeWidth:13,nodeGap:18,draggable:false,emphasis:{focus:'adjacency'},data,links,
      lineStyle:{color:'gradient',curveness:.50,opacity:.27}
    }]
  }}/>;
}
