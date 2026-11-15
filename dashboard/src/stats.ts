import type { LeadRecord, Route, Status } from "./types";

export interface Stats {
  leadsToday: number;
  hotToday: number;
  awaitingApproval: number;
  needsHuman: number;
  averageScore: number | null;
  total: number;
}

export function isSameLocalDay(iso: string, now: Date): boolean {
  const date = new Date(iso);
  return (
    !Number.isNaN(date.getTime()) &&
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  );
}

/** Numbers for the tiles at the top. Spam is left out of the average score. */
export function computeStats(leads: LeadRecord[], now: Date): Stats {
  const today = leads.filter((record) => isSameLocalDay(record.processed_at, now));
  const scored = leads.filter((record) => record.route !== "spam");
  const sum = scored.reduce((total, record) => total + record.score, 0);
  return {
    leadsToday: today.length,
    hotToday: today.filter((record) => record.is_hot).length,
    awaitingApproval: leads.filter((record) => record.status === "pending_approval").length,
    needsHuman: leads.filter((record) => record.status === "needs_human").length,
    averageScore: scored.length ? Math.round((sum / scored.length) * 10) / 10 : null,
    total: leads.length,
  };
}

export type ScoreLevel = "high" | "medium" | "low";

/** How strongly a score is shown: 7-10 strong, 4-6 medium, 1-3 muted. */
export function scoreLevel(score: number): ScoreLevel {
  if (score >= 7) return "high";
  if (score >= 4) return "medium";
  return "low";
}

/** Newest enquiry first, by the time it was received (the date shown in the table). */
export function newestFirst(leads: LeadRecord[]): LeadRecord[] {
  const time = (record: LeadRecord) => new Date(record.lead.received_at).getTime() || 0;
  return [...leads].sort((a, b) => time(b) - time(a));
}

export function filterLeads(leads: LeadRecord[], route: Route | "all", query: string): LeadRecord[] {
  const text = query.trim().toLowerCase();
  return leads.filter((record) => {
    if (route !== "all" && record.route !== route) return false;
    if (!text) return true;
    const haystack = [record.lead.name, record.lead.message, record.lead.id, record.lead.email]
      .join(" ")
      .toLowerCase();
    return haystack.includes(text);
  });
}

export const ROUTE_LABELS: Record<Route, string> = {
  draft_reply: "Draft reply",
  handover: "Handover",
  nurture: "Nurture",
  spam: "Spam",
};

export const STATUS_LABELS: Record<Status, string> = {
  pending_approval: "Awaiting approval",
  needs_human: "Needs a human",
  nurture: "Nurture",
  discarded: "Discarded",
  approved: "Approved",
  rejected: "Rejected",
};

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (!iso || Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Compact form for table cells: "Nov 14, 08:49". */
export function formatShort(iso: string): string {
  const date = new Date(iso);
  if (!iso || Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function humanize(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
