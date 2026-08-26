import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Mode } from "../types";

interface AppState{
  mode:Mode;
  role:"analyst"|"maintainer";
  setMode:(mode:Mode)=>void;
  setRole:(role:"analyst"|"maintainer")=>void;
}

export const useAppStore=create<AppState>()(
  persist(
    (set)=>(
      {
        mode:"demo",
        role:"maintainer",
        setMode:(mode)=>set({mode}),
        setRole:(role)=>set({role})
      }
    ),
    {name:"fundscope-v9-ui",partialize:(s)=>({mode:s.mode})}
  )
);
