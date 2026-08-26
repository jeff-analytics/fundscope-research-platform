import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { PulsePage } from "./pages/PulsePage";
import { ExplorerPage } from "./pages/ExplorerPage";
import { FundsPage } from "./pages/FundsPage";
import { ManagersPage } from "./pages/ManagersPage";
import { WorkspacePage } from "./pages/WorkspacePage";
import { SmartMoneyPage } from "./pages/SmartMoneyPage";
import { ComparePage } from "./pages/ComparePage";
import { DataCenterPage } from "./pages/DataCenterPage";
export default function App(){return <BrowserRouter><Routes><Route element={<AppShell/>}><Route path="/" element={<PulsePage/>}/><Route path="/explorer" element={<ExplorerPage/>}/><Route path="/funds" element={<FundsPage/>}/><Route path="/managers" element={<ManagersPage/>}/><Route path="/workspace" element={<WorkspacePage/>}/><Route path="/smart-money" element={<SmartMoneyPage/>}/><Route path="/compare" element={<ComparePage/>}/><Route path="/data" element={<DataCenterPage/>}/><Route path="*" element={<Navigate to="/" replace/>}/></Route></Routes></BrowserRouter>}
