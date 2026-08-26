export function Loading({label="正在加载",compact=false}:{label?:string;compact?:boolean}){
  return <div className={`skeleton-stack ${compact?'compact':''}`}>
    <div className="skeleton hero"/><div className="skeleton row"/><div className="skeleton row short"/>
    <span>{label}</span>
  </div>
}
export function ErrorState({message,onRetry,compact=false}:{message?:string;onRetry?:()=>void;compact?:boolean}){
  return <div className={`state-card error ${compact?'compact':''}`}><b>当前内容暂时无法显示</b><span>{message||"请稍后重试。"}</span>{onRetry&&<button className="state-retry" onClick={onRetry}>重新加载</button>}</div>
}
export function EmptyState({title,body,compact=false}:{title:string;body:string;compact?:boolean}){
  return <div className={`state-card ${compact?'compact':''}`}><b>{title}</b><span>{body}</span></div>
}
