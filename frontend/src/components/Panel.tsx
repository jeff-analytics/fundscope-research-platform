import type { ReactNode } from "react";

export function Panel({title,meta,children,className=""}:{title:string;meta?:ReactNode;children:ReactNode;className?:string}){
  return (
    <section className={`panel ${className}`}>
      <header><h3>{title}</h3>{meta&&<div className="panel-meta">{meta}</div>}</header>
      <div className="panel-body">{children}</div>
    </section>
  );
}
