import { create } from "zustand";

type ToastKind="success"|"error"|"info";
export type ToastItem={id:string;kind:ToastKind;title:string;message?:string;actionLabel?:string;action?:()=>void};
interface ToastState{items:ToastItem[];push:(item:Omit<ToastItem,"id">)=>void;remove:(id:string)=>void}
export const useToastStore=create<ToastState>((set,get)=>({
  items:[],
  push:(item)=>{
    const id=Math.random().toString(36).slice(2,10);
    set({items:[...get().items,{...item,id}].slice(-4)});
    window.setTimeout(()=>get().remove(id),4200);
  },
  remove:(id)=>set({items:get().items.filter(x=>x.id!==id)})
}));
