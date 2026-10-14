export interface DocumentInfo {
  id: string;
  name: string;
  filename: string;
  pages: number;
}

export interface TaskInfo {
  id: string;
  label: string;
  endpoint: string;
  level: "basic" | "complex";
  min_docs: number;
  max_docs: number;
  description: string;
  free_allowed: boolean;
}

export interface ModelsCatalog {
  free_models: string[];
  byok_providers: Record<string, { default: string | null; suggested: string[] }>;
  headers: { provider: string; api_key: string; model: string };
  complex_tasks_require_byok: boolean;
}

export interface Health {
  status: string;
  providers: string[];
  models: Record<string, string>;
  free_models: string[];
  keys_configured: Record<string, boolean>;
}

export interface ChatSource {
  tool: string;
  document_id?: string;
  document?: string;
  page: number | null;
  page_number: number | null;
  excerpt: string;
}

export interface ChatResponse {
  answer: string;
  sources: ChatSource[];
}

export interface PageContent {
  page: number;
  content: string;
  metadata: Record<string, unknown>;
}

export interface AnalysisParams {
  task: "price_summary" | "technical" | "compare" | "backtest" | "custom";
  ticker?: string;
  tickers?: string[];
  period?: string; // 1mo, 3mo, 6mo, 1y, 3y, 1000d, 12w, ytd
  short_window?: number;
  long_window?: number;
  rsi_period?: number;
  sma_window?: number;
  prompt?: string;
}

export interface AnalysisResponse {
  task: string;
  prompt: string;
  result: string;
}

export interface StrategyParams {
  document_id: string;
  libraries?: string;
  instruction?: string;
  extract_query?: string;
  top_k?: number;
}

export interface StrategyResponse {
  plan: string;
  code: string;
  raw: string;
}

export interface FinancialModel {
  revenue_projection: number;
  growth_rate: number;
  valuation_estimate: number;
  summary: string;
}

export interface CompareMemo {
  company_a_name: string;
  company_b_name: string;
  company_a_model: FinancialModel;
  company_b_model: FinancialModel;
  comparative_analysis: { comparative_analysis: string; overall_recommendation: string };
}

export interface ResearchResult {
  report_content: string;
  review: string;
  research_notes: Record<string, string>;
}

export type ResearchEvent =
  | { type: "agent"; agent: string }
  | { type: "output"; agent: string; content: string; tools: string[] }
  | { type: "tool_result"; tool: string; output: string }
  | ({ type: "result" } & ResearchResult);

export interface AccessConfig {
  mode: "free" | "byok";
  freeModel: string; // "<provider>:<model>" or "" for the server default
  provider: string;
  model: string;
  apiKey: string;
}

export const DEFAULT_ACCESS: AccessConfig = { mode: "free", freeModel: "", provider: "anthropic", model: "", apiKey: "" };
