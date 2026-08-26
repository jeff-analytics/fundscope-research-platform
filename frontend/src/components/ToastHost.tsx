import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { useToastStore } from "../store/useToastStore";
export function ToastHost(){
  const items=useToastStore(s=>s.items);const remove=useToastStore(s=>s.remove);
  return <div className="toast-host">{items.map(t=>{
    const Icon=t.kind==='success'?CheckCircle2:t.kind==='error'?AlertCircle:Info;
    return <div className={`toast ${t.kind}`} key={t.id} role="status" aria-live="polite">
      <Icon size={17}/><div><b>{t.title}</b>{t.message&&<span>{t.message}</span>}{t.actionLabel&&t.action&&<button onClick={()=>{Promise.resolve(t.action?.()).finally(()=>remove(t.id))}}>{t.actionLabel}</button>}</div>
      <button className="toast-close" aria-label="关闭提示" onClick={()=>remove(t.id)}><X size={14}/></button>
    </div>
  })}</div>
}
