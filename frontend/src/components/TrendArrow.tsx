import { ArrowDownRight,ArrowUpRight,Minus } from "lucide-react";

export function TrendArrow({delta}:{delta:number}){
  const v=Number(delta||0);
  if(v>0)return <span className="trend-arrow up"><ArrowUpRight size={16}/><b>+{Math.round(v)}</b></span>;
  if(v<0)return <span className="trend-arrow down"><ArrowDownRight size={16}/><b>{Math.round(v)}</b></span>;
  return <span className="trend-arrow flat"><Minus size={15}/><b>0</b></span>;
}
