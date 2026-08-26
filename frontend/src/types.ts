export type Mode = "demo" | "local";

export interface Fund {
  fund_code: string;
  fund_name: string;
  fund_type?: string;
  manager_name?: string;
  aum_yi?: number | null;
}

export interface Holding {
  fund_code: string;
  quarter: string;
  stock_code: string;
  stock_name: string;
  sector: string;
  weight_pct: number;
}

export interface Activity {
  stock_code: string;
  stock_name: string;
  sector: string;
  weight_old: number | null;
  weight_new: number | null;
  delta: number;
  activity: string;
}

export interface FundDetail {
  fund: Fund;
  periods: string[];
  holdings: Holding[];
  latest: Holding[];
  activity: Activity[];
  sector_shift: Array<{sector:string;old:number;new:number;delta:number}>;
}

export interface Manager {
  manager_name: string;
  company: string;
  career_years?: number | null;
  aum_yi?: number | null;
  best_return_pct?: number | null;
  fund_codes?: string;
}

export interface ManagerDetail {
  manager: Manager;
  fund_codes: string[];
  periods: string[];
  consensus: Array<{
    stock_code:string;stock_name:string;sector:string;
    fund_coverage:number;avg_weight:number;sum_weight:number;
  }>;
  sector_history: Array<{quarter:string;sector:string;weight_pct:number}>;
}

export interface Overview {
  fund_count:number;
  manager_count:number;
  holding_rows:number;
  latest_period:string|null;
  crowded:any[];
  coverage_change:any[];
  sector_history:Array<{quarter:string;sector:string;weight_pct:number}>;
  asset_history:Array<{quarter:string;equity:number;fixed_income:number;cash:number}>;
}

export interface SmartMoney {
  periods:string[];
  crowded:any[];
  coverage_change:any[];
  sector_history:any[];
}

export interface DataContextInfo{
  basis?:string;
  basis_label?:string;
  source?:string;
  selected_period?:string|null;
  compare_period?:string|null;
  sample_funds?:number|null;
  selected_universe_funds?:number|null;
  compare_universe_funds?:number|null;
  updated_at?:string|null;
  note?:string|null;
  progressive_pending?:boolean;
}

export interface ConsensusRow{
  stock_code:string;
  stock_name:string;
  sector:string;
  fund_count:number;
  previous_fund_count:number;
  coverage_rate_pct:number;
  previous_coverage_rate_pct:number;
  delta:number;
  coverage_delta_pp:number;
  change_per_quarter:number;
  coverage_change_per_quarter_pp:number;
  acceleration:number|null;
  market_value_yi?:number|null;
  consensus_level:"高"|"中"|"低"|string;
  consensus_trend:"新形成"|"增强"|"持续增强"|"稳定"|"弱化"|"退潮"|string;
  state:string;
}

export interface SmartMoneyResponse{
  periods:string[];
  selected_period:string|null;
  compare_period:string|null;
  prior_period?:string|null;
  comparison_gap_quarters?:number|null;
  lifecycle:ConsensusRow[];
  crowded:ConsensusRow[];
  coverage_change:any[];
  coverage_history:Array<{quarter:string;stock_code:string;stock_name:string;fund_count:number;cohort_size?:number;coverage_rate_pct?:number}>;
  sector_history:any[];
  sector_change:any[];
  summary:Record<string,number>;
  data_context:DataContextInfo;
}

export interface SecurityDetailResponse{
  security:{stock_code:string;stock_name:string;sector:string};
  periods:string[];
  selected_period:string;
  previous_period?:string|null;
  history:Array<{period:string;fund_count:number;cohort_size?:number;coverage_rate_pct?:number|null;avg_weight?:number|null;total_weight?:number}>;
  fund_changes:any[];
  current_holders:any[];
  entrants:any[];
  exits:any[];
  data_context?:DataContextInfo;
}
