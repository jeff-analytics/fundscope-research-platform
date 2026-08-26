import React from "react";
import { AlertTriangle, RefreshCcw } from "lucide-react";

type Props={children:React.ReactNode};
type State={hasError:boolean};

export class ErrorBoundary extends React.Component<Props,State>{
  declare props: Readonly<Props>;
  state:State={hasError:false};
  static getDerivedStateFromError():State{return {hasError:true}}
  componentDidCatch(error:Error,info:React.ErrorInfo){console.error("[FundScope]",error,info)}
  render(){
    if(this.state.hasError)return <div className="fatal-state">
      <div className="fatal-icon"><AlertTriangle size={22}/></div>
      <h2>当前页面暂时无法显示</h2>
      <span>请刷新页面。如果问题仍然存在，请到数据中心运行数据检查。</span>
      <button onClick={()=>window.location.reload()}><RefreshCcw size={15}/>刷新页面</button>
    </div>;
    return this.props.children;
  }
}
