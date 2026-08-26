import { useEffect, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { api } from "../lib/api";
import { useAppStore } from "../store/useAppStore";
import { PageHeader } from "../components/PageHeader";
import { MetricStrip } from "../components/MetricStrip";
import { Panel } from "../components/Panel";
import { Chart } from "../components/Chart";
import { DataTable } from "../components/DataTable";
import { Loading, EmptyState, ErrorState } from "../components/Loading";
import { FundPicker } from "../components/RemotePicker";
import { categoryGrid } from "../lib/chartUtils";
import { DataContext } from "../components/DataContext";
import { periodScope } from "../lib/research";
import { formatNumber } from "../lib/format";

export function ComparePage(){
  const mode=useAppStore(s=>s.mode);
  const [a,setA]=useState("");const[b,setB]=useState("");
  const [da,setDa]=useState<any>(null);const[dbb,setDb]=useState<any>(null);
  const [quarter,setQuarter]=useState("");const[result,setResult]=useState<any>(null);
  const [error,setError]=useState("");

  useEffect(()=>{api.funds(mode).then(x=>{if(x[0])setA(String(x[0].fund_code));if(x[1])setB(String(x[1].fund_code))}).catch(e=>setError(e?.message||String(e)))},[mode]);
  useEffect(()=>{if(a)api.fund(mode,a).then(setDa).catch(e=>setError(e?.message||String(e)))},[a,mode]);
  useEffect(()=>{if(b)api.fund(mode,b).then(setDb).catch(e=>setError(e?.message||String(e)))},[b,mode]);
  useEffect(()=>{if(!da||!dbb)return;const common=da.periods.filter((p:string)=>dbb.periods.includes(p));setQuarter(common[common.length-1]||"")},[da,dbb]);
  useEffect(()=>{if(a&&b&&quarter){setResult(null);api.compare(mode,a,b,quarter).then(setResult).catch(e=>setError(e?.message||String(e)))}},[a,b,quarter,mode]);

  if(error)return <ErrorState message={error}/>;
  const commonPeriods=da&&dbb?da.periods.filter((p:string)=>dbb.periods.includes(p)):[];
  const cols:ColumnDef<any>[]=[
    {accessorKey:"stock_name",header:"证券"},
    ...(result?.sector_mapped?[{accessorKey:"sector",header:"行业"} as ColumnDef<any>]:[]),
    {accessorKey:a,header:"基金 A",cell:({getValue})=><span className="num">{getValue()!=null?`${Number(getValue()).toFixed(2)}%`:"—"}</span>},
    {accessorKey:b,header:"基金 B",cell:({getValue})=><span className="num">{getValue()!=null?`${Number(getValue()).toFixed(2)}%`:"—"}</span>}
  ];

  return <>
    <PageHeader eyebrow="横向研究" title="基金对比"/>
    {quarter&&<DataContext period={quarter} basis={periodScope(quarter)==='top10'?'Top 10 Disclosure':'Full Portfolio Disclosure'} note="同一报告期横向比较使用该报告期公开披露范围；跨期调仓分析另按可比披露口径处理。"/>}
    <div className="compare-toolbar modern">
      <div><label>基金 A</label><FundPicker value={a} onChange={setA} label="选择基金 A"/></div>
      <span>对比</span>
      <div><label>基金 B</label><FundPicker value={b} onChange={setB} label="选择基金 B"/></div>
      <label className="quarter-select">报告期<select value={quarter} onChange={e=>setQuarter(e.target.value)}>{commonPeriods.map((p:string)=><option key={p}>{p}</option>)}</select></label>
    </div>

    {!quarter?<EmptyState title="没有共同报告期" body="这两只基金当前没有可直接比较的持仓报告期。"/>:!result?<Loading label="正在计算基金对比"/>:<>
      <MetricStrip items={[
        {label:"共同证券",value:result.overlap,sub:"两只基金均披露"},
        {label:"合计证券",value:result.union,sub:"去重后的证券数量"},
        {label:"持仓重合率",value:`${formatNumber(result.overlap_ratio)}%`,sub:"共同证券 / 合集"},
        {label:result.sector_mapped?"行业相似度":"报告期",value:result.sector_mapped?`${formatNumber(result.sector_similarity)}%`:quarter,sub:result.sector_mapped?"行业配置余弦相似度":"当前可比披露期"}
      ]}/>
      <div className="grid two-equal">
        <Panel title={result.sector_mapped?"行业配置差异":"持仓重合结构"} meta={<span>{result.sector_mapped?"披露权重":"当前报告期"}</span>}>
          {result.sector_mapped?<Chart height={430} option={{
            tooltip:{trigger:"axis",axisPointer:{type:"shadow"}},legend:{top:0,textStyle:{color:"#667085"}},
            grid:categoryGrid(18,18,46,22),
            xAxis:{type:"value",axisLabel:{formatter:"{value}%",color:"#98a2b3"},splitLine:{lineStyle:{color:"#eef0f3"}}},
            yAxis:{type:"category",data:result.sectors.map((x:any)=>x.sector),axisLabel:{color:"#475467"},axisLine:{show:false},axisTick:{show:false}},
            series:[
              {name:"基金 A",type:"bar",barWidth:8,data:result.sectors.map((x:any)=>x.weight_a),itemStyle:{color:"#315c94"}},
              {name:"基金 B",type:"bar",barWidth:8,data:result.sectors.map((x:any)=>x.weight_b),itemStyle:{color:"#4f7f70"}}
            ]
          }}/>:<div className="overlap-visual"><strong>{result.overlap_ratio}%</strong><span>持仓重合率</span><div><i style={{width:`${Math.min(100,result.overlap_ratio)}%`}}/></div></div>}
        </Panel>
        <Panel title="共同持仓" meta={<span>{quarter}</span>}>
          {result.common.length?<DataTable data={result.common} columns={cols} maxHeight={430}/>:<EmptyState title="没有共同持仓" body="这两只基金在当前报告期没有共同披露证券。"/>}
        </Panel>
      </div>
    </>}
  </>;
}
