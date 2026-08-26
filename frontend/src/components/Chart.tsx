import ReactECharts from "echarts-for-react";

export function Chart({option,height=320,onEvents}:{option:any;height?:number;onEvents?:Record<string,(params:any)=>void>}){
  return <ReactECharts
    option={{
      animationDuration:380,
      animationEasing:"cubicOut",
      textStyle:{
        fontFamily:'-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",Arial,sans-serif',
        fontSize:12,
        color:"#667085"
      },
      ...option
    }}
    style={{height}}
    opts={{renderer:"canvas"}}
    onEvents={onEvents}
    notMerge
  />
}
