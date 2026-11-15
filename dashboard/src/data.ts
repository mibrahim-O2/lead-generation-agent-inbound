import demoData from "./demo-data.json";
import type { DashboardData, LeadRecord, ReviewAction, Status } from "./types";

/**
 * Two modes, decided when the site is built:
 * - DEMO: no VITE_API_URL. Bundled dummy data, no network requests at all.
 * - LOCAL: VITE_API_URL points at the local FastAPI server (make serve).
 *
 * VITE_* values are baked into the public JavaScript, so they must never hold
 * a key or any other secret. The API URL is not a secret.
 */
export const API_URL = (import.meta.env.VITE_API_URL ?? "").trim().replace(/\/+$/, "");
export const MODE: "demo" | "local" = API_URL ? "local" : "demo";

const REVIEW_STATUS: Record<ReviewAction, Status> = {
  approve: "approved",
  reject: "rejected",
  handover: "needs_human",
};

const DAY_MS = 24 * 60 * 60 * 1000;

function shift(iso: string, byMs: number): string {
  const time = new Date(iso).getTime();
  return Number.isNaN(time) ? iso : new Date(time + byMs).toISOString();
}

/**
 * Move the demo data forward by whole days so its newest lead falls on today.
 * Without this the "today" tiles would always read zero on the demo site.
 */
export function rebaseToToday(data: DashboardData, now: Date): DashboardData {
  const newest = Math.max(...data.leads.map((record) => new Date(record.processed_at).getTime()));
  if (!Number.isFinite(newest)) return data;
  const startOfDay = (time: number) => new Date(time).setHours(0, 0, 0, 0);
  const byMs = Math.round((startOfDay(now.getTime()) - startOfDay(newest)) / DAY_MS) * DAY_MS;
  return {
    pending: data.pending.map((lead) => ({ ...lead, received_at: shift(lead.received_at, byMs) })),
    leads: data.leads.map((record) => ({
      ...record,
      processed_at: shift(record.processed_at, byMs),
      lead: { ...record.lead, received_at: shift(record.lead.received_at, byMs) },
    })),
    runs: data.runs.map((run) => ({
      ...run,
      started_at: shift(run.started_at, byMs),
      finished_at: shift(run.finished_at, byMs),
    })),
  };
}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `The API answered ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function loadData(): Promise<DashboardData> {
  if (MODE === "demo") {
    return rebaseToToday(demoData as unknown as DashboardData, new Date());
  }
  const [leads, runs] = await Promise.all([
    getJson<{ leads: LeadRecord[]; pending: DashboardData["pending"] }>("/leads"),
    getJson<{ runs: DashboardData["runs"] }>("/runs"),
  ]);
  return { leads: leads.leads, pending: leads.pending, runs: runs.runs };
}

/** What a review does to a record. Used directly in demo mode, where nothing is saved. */
export function applyReview(record: LeadRecord, action: ReviewAction, now: Date): LeadRecord {
  return { ...record, status: REVIEW_STATUS[action], reviewed_at: now.toISOString() };
}

/**
 * Record a human decision. This never sends anything to the customer: it only
 * changes the status. In demo mode the change stays in the browser's memory.
 */
export async function reviewLead(record: LeadRecord, action: ReviewAction): Promise<LeadRecord> {
  if (MODE === "demo") {
    return applyReview(record, action, new Date());
  }
  const result = await getJson<{ lead: LeadRecord }>(
    `/leads/${encodeURIComponent(record.lead.id)}/review`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    },
  );
  return result.lead;
}
