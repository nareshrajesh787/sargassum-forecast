export interface LeadForecast {
  lead_days: number;
  target_date: string;
  probability: number;
  interval_80: [number, number];
  climatology: number;
  issue_time_model_M2_fc: number;
  drift_index_P1: number | null;
  in_validated_season: boolean;
}
export interface SiteForecast {
  id: string;
  name: string;
  lat: number;
  lon: number;
  leads: LeadForecast[];
}
export interface Forecast {
  issue_date: string;
  issue_time: string;
  generated_utc: string;
  model_version: string;
  served_model: string;
  target: string;
  interval_80_definition: string;
  p1_status: string;
  disclaimer: string;
  attribution: string;
  sites: SiteForecast[];
  preview?: boolean;
  preview_note?: string;
}
export interface HeadlineRow {
  season: string;
  model: string;
  description: string;
  upper_bound: boolean;
  brier: number;
  bss_vs_climatology: number | null;
  bss_ci: [number | null, number | null];
  auc: number | null;
  auc_ci: [number | null, number | null];
  base_rate: number;
}
export interface Results {
  generated_from_commit: string;
  test_unlocked_utc: string;
  model_version: string;
  headline: { source: string; rows: HeadlineRow[]; by_lead: { model: string; lead: number; bss_vs_climatology: number; bss_ci: [number, number] }[] };
  reliability: { source: string; bins: { model: string; p_mean: number; obs_freq: number; n: number }[] };
  backtest: {
    source: string; label: string; booking_lead_days: number;
    rows: { budget_hours: number; policy: string; share_of_oracle: number; ci: [number, number];
      minus_climatology?: number; minus_climatology_ci?: [number, number]; verdict_vs_climatology?: string }[];
    all_leads_and_budgets_vs_climatology: Record<string, { better: number; worse: number; cells: number }>;
  };
  ablation: { source: string; reference: string; rows: { model: string; brier_minus_M1: number; ci: [number, number]; verdict: string }[] };
  interval_table: { source: string; rows: { bin_lo: number; bin_hi: number; n: number; mean_forecast: number; observed_freq: number; obs_p10: number; obs_p90: number }[] };
  gallery: { source: string; rows: Record<string, string | number>[] };
}
export interface TrackRecord {
  updated_utc: string;
  n: number;
  note: string;
  brier?: number;
  brier_climatology?: number;
  bss_vs_climatology?: number;
  auc?: number | null;
  event_rate?: number;
  reliability?: { bin: number; p_mean: number; obs_freq: number; n: number }[];
}
