import { useEffect, useMemo, useRef, useState } from "react";
import {
  flexRender, getCoreRowModel, getSortedRowModel,
  useReactTable, type ColumnDef, type SortingState
} from "@tanstack/react-table";
import { ArrowDownUp } from "lucide-react";

export function DataTable<T extends object>({data,columns,maxHeight=420,onRowClick,rowClassName,virtualizeAt=300}:{data:T[];columns:ColumnDef<T,any>[];maxHeight?:number;onRowClick?:(row:T)=>void;rowClassName?:(row:T)=>string;virtualizeAt?:number}){
  const [sorting,setSorting]=useState<SortingState>([]);const[scrollTop,setScrollTop]=useState(0);const wrapRef=useRef<HTMLDivElement|null>(null);
  const memoData=useMemo(()=>data,[data]);
  const table=useReactTable({data:memoData,columns,state:{sorting},onSortingChange:setSorting,getCoreRowModel:getCoreRowModel(),getSortedRowModel:getSortedRowModel()});
  const rows=table.getRowModel().rows;const virtual=rows.length>virtualizeAt;const rowHeight=43;const overscan=8;
  const start=virtual?Math.max(0,Math.floor(scrollTop/rowHeight)-overscan):0;const visibleCount=virtual?Math.ceil(maxHeight/rowHeight)+overscan*2:rows.length;const end=virtual?Math.min(rows.length,start+visibleCount):rows.length;const visibleRows=rows.slice(start,end);const topPad=virtual?start*rowHeight:0;const bottomPad=virtual?Math.max(0,(rows.length-end)*rowHeight):0;
  useEffect(()=>{setScrollTop(0);if(wrapRef.current)wrapRef.current.scrollTop=0},[sorting,memoData]);
  return (
    <div className="table-shell">
      <div ref={wrapRef} className="table-wrap" style={{maxHeight}} onScroll={e=>virtual&&setScrollTop(e.currentTarget.scrollTop)}>
        <table>
          <thead>{table.getHeaderGroups().map(group=><tr key={group.id}>{group.headers.map(header=><th key={header.id}>{header.isPlaceholder?null:<button className={header.column.getCanSort()?"sortable":""} onClick={header.column.getToggleSortingHandler()}>{flexRender(header.column.columnDef.header,header.getContext())}{header.column.getCanSort()&&<ArrowDownUp size={12}/>}</button>}</th>)}</tr>)}</thead>
          <tbody>
            {topPad>0&&<tr aria-hidden="true"><td colSpan={Math.max(1,columns.length)} style={{height:topPad,padding:0,border:0}}/></tr>}
            {visibleRows.map(row=><tr key={row.id} className={`${onRowClick?"clickable-row":""} ${rowClassName?.(row.original)||""}`.trim()} onClick={()=>onRowClick?.(row.original)}>{row.getVisibleCells().map(cell=><td key={cell.id}>{flexRender(cell.column.columnDef.cell,cell.getContext())}</td>)}</tr>)}
            {bottomPad>0&&<tr aria-hidden="true"><td colSpan={Math.max(1,columns.length)} style={{height:bottomPad,padding:0,border:0}}/></tr>}
          </tbody>
        </table>
      </div>
      {virtual&&<div className="table-window-meta">已启用大表窗口渲染 · {rows.length.toLocaleString()} 行</div>}
    </div>
  );
}
