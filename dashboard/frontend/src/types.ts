export interface RailInfo {
  type?: string;
  name?: string;
  stop: boolean;
  duration?: number;
  decisions?: string[];
}

export interface LlmCall {
  task?: string;
  provider?: string;
  model?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  duration?: number;
  from_cache?: boolean;
}

export interface RequestRecord {
  id: string;
  ts: number;
  source: string;
  status: string;
  interaction_id?: string | null;
  config_id?: string | null;
  thread_id?: string | null;
  input_summary: string;
  output_summary: string;
  rails: RailInfo[];
  llm_calls: LlmCall[];
  phase_durations: Record<string, number>;
  error?: string | null;
  raw_request?: unknown;
  raw_response?: unknown;
}

export interface RecordsResponse {
  items: RequestRecord[];
  total: number;
}

export interface GuardrailsStatus {
  url: string;
  healthy: boolean;
  configs: { id: string }[] | null;
  models: unknown;
}

export interface StatusResponse {
  guardrails: GuardrailsStatus;
  ingestion: {
    trace_globs: string[];
    prom_url?: string | null;
    malformed: Record<string, number>;
    records_written: number;
    records_dropped_duplicates: number;
  };
  admin_hook: boolean;
}

export interface OverviewStats {
  count: number;
  blocked: number;
  errors: number;
  p50_ms: number | null;
  p95_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  buckets: { ts: number; count: number; blocked: number }[];
}

export interface RailFrequency {
  name: string;
  count: number;
  blocked: number;
}

export interface MetricSample {
  name: string;
  labels: Record<string, string>;
  ts: number;
  value: number;
}

export interface ChallengeRunResult {
  challenge_id?: string;
  challenge: { id?: string; input?: string; [k: string]: unknown };
  status_code: number;
  response: any;
}
