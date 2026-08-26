import { Check,LoaderCircle,Pause,Play,Square,TriangleAlert } from "lucide-react";
import { api } from "../lib/api";

export function TaskProgressButton({task,idleLabel,onClick,disabled=false,onTaskChange}:{task:any;idleLabel:string;onClick:()=>void|Promise<void>;disabled?:boolean;onTaskChange?:(task:any)=>void}){
 const status=String(task?.status||'');
 const active=task&&['queued','running','paused','cooling'].includes(status);
 const running=status==='running';
 const paused=status==='paused';
 const cooling=status==='cooling';
 const queued=status==='queued';
 const success=status==='success';
 const error=status==='error';
 const pct=Math.round(Number(task?.progress||0));
 const update=async(action:'pause'|'resume'|'cancel')=>{
   if(!task?.task_id)return;
   if(action==='pause')await api.pauseTask(task.task_id);
   else if(action==='resume')await api.resumeTask(task.task_id);
   else await api.cancelTask(task.task_id);
   const latest=await api.task(task.task_id);
   onTaskChange?.(latest);
   window.dispatchEvent(new CustomEvent('fundscope-task-updated'));
 };
 const label=queued?'等待中':paused?'已暂停':cooling?(task?.message||'冷却中'):running?`${pct}%`:success?'完成':error?'重试':idleLabel;
 return <div className={`task-control ${active?'active':''}`}>
   <button className={`task-progress-button ${active?'running':''} ${paused?'paused':''} ${cooling?'cooling':''} ${success?'done':''} ${error?'failed':''}`} onClick={onClick} disabled={disabled||active}>
     {active&&<span className="task-progress-fill" style={{width:`${pct}%`}}/>}
     <span className="task-progress-content">
       {running||queued||cooling?<LoaderCircle className={cooling?'':'spin'} size={14}/>:paused?<Pause size={14}/>:success?<Check size={14}/>:error?<TriangleAlert size={14}/>:null}
       {label}
     </span>
   </button>
   {active&&<div className="task-inline-actions">
     {(running||cooling)&&<button type="button" className="task-icon-button" title="暂停" onClick={()=>update('pause')}><Pause size={14}/></button>}
     {paused&&<button type="button" className="task-icon-button resume" title="继续" onClick={()=>update('resume')}><Play size={14}/></button>}
     <button type="button" className="task-icon-button cancel" title="取消" onClick={()=>update('cancel')}><Square size={13}/></button>
   </div>}
 </div>
}
