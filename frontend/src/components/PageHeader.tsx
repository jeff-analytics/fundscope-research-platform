import type { ReactNode } from "react";

export function PageHeader({eyebrow,title,subtitle,actions}:{eyebrow?:string;title:string;subtitle?:string;actions?:ReactNode}){
  return (
    <div className="page-header">
      <div>
        {eyebrow&&<div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {subtitle&&<p>{subtitle}</p>}
      </div>
      {actions&&<div className="page-actions">{actions}</div>}
    </div>
  );
}
