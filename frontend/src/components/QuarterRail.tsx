import { Pause, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

export function QuarterRail({periods,value,onChange,playable=false}:{periods:string[];value:string;onChange:(v:string)=>void;playable?:boolean}){
  const [playing,setPlaying]=useState(false);
  useEffect(()=>{if(!playable&&playing)setPlaying(false)},[playable,playing]);
  useEffect(()=>{
    if(!playable||!playing||periods.length<2)return;
    const id=setInterval(()=>{const idx=Math.max(0,periods.indexOf(value));onChange(periods[(idx+1)%periods.length])},1200);
    return()=>clearInterval(id);
  },[playing,periods,value,onChange]);
  const visible=useMemo(()=>{
    if(periods.length<=12)return periods;
    const idx=Math.max(0,periods.indexOf(value));let start=Math.max(0,idx-6);start=Math.min(start,periods.length-12);return periods.slice(start,start+12)
  },[periods,value]);
  return <div className="quarter-wrap">
    {playable&&<button className="play-button" onClick={()=>setPlaying(v=>!v)}>{playing?<Pause size={15}/>:<Play size={15}/>}<span>{playing?"暂停":"播放季度"}</span></button>}
    <div className="quarter-rail">{visible.map((p,i)=><button key={p} className={p===value?"selected":""} onClick={()=>onChange(p)}><span>{p}</span><i/>{i<visible.length-1&&<b/>}</button>)}</div>
    {periods.length>12&&<select className="quarter-jump" value={value} onChange={e=>onChange(e.target.value)} aria-label="选择报告期">{periods.slice().reverse().map(p=><option key={p} value={p}>{p}</option>)}</select>}
  </div>
}
