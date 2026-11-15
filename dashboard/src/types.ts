// Mirrors the Python models in src/leadgen/models.py (LeadRecord, RunRecord).

export type Route = "draft_reply" | "handover" | "nurture" | "spam";
export type Status =
  | "pending_approval"
  | "needs_human"
  | "nurture"
  | "discarded"
  | "approved"
  | "rejected";
export type ReviewAction = "approve" | "reject" | "handover";

export interface Lead {
  id: string;
  received_at: string;
  name: string;
  email: string;
  phone: string;
  channel: string;
  message: string;
}

export interface ExtractedFields {
  property_type: string;
  monthly_bill_pkr: number | null;
  sanctioned_load_kw: number | null;
  location: string | null;
  timeline: string;
  product_interest: string[];
  quote_requested: boolean;
  site_visit_requested: boolean;
  urgency: string;
}

export interface DraftProblem {
  check: string;
  found: string;
  fix: string;
}

export interface RejectedDraft {
  attempt: number;
  problems: DraftProblem[];
  body: string;
}

export interface LeadRecord {
  lead: Lead;
  intent: string;
  extracted: ExtractedFields;
  score: number;
  is_hot: boolean;
  score_breakdown: Record<string, number>;
  route: Route;
  status: Status;
  missing_info: string[];
  draft_reply: string;
  draft_language: string;
  summary: string;
  handover_reason: string;
  duplicate_of: string;
  flags: string[];
  guardrail_notes: string[];
  rejected_drafts: RejectedDraft[];
  tool_calls: string[];
  run_id: string;
  processed_at: string;
  reviewed_at: string;
  error: string;
}

export interface RunRecord {
  id: string;
  started_at: string;
  finished_at: string;
  source: string;
  dry_run: boolean;
  provider: string;
  model: string;
  leads_received: number;
  leads_processed: number;
  drafts_created: number;
  handovers: number;
  nurture: number;
  spam: number;
  hot_leads: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_estimate_usd: number | null;
  errors: string[];
  stopped_reason: string;
}

export interface DashboardData {
  leads: LeadRecord[];
  pending: Lead[];
  runs: RunRecord[];
}
