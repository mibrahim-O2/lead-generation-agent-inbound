import { describe, expect, it } from "vitest";
import { applyReview, rebaseToToday } from "./data";
import demoData from "./demo-data.json";
import { computeStats, filterLeads, isSameLocalDay, newestFirst } from "./stats";
import type { DashboardData, LeadRecord } from "./types";

const data = demoData as unknown as DashboardData;
const now = new Date(2026, 5, 15, 14, 0, 0);

function lead(overrides: Partial<LeadRecord>): LeadRecord {
  return { ...data.leads[0], ...overrides };
}

describe("computeStats", () => {
  it("counts today's leads, hot leads and the queues", () => {
    const today = new Date(2026, 5, 15, 9, 0, 0).toISOString();
    const yesterday = new Date(2026, 5, 14, 9, 0, 0).toISOString();
    const stats = computeStats(
      [
        lead({ processed_at: today, is_hot: true, score: 9, status: "pending_approval" }),
        lead({ processed_at: today, is_hot: false, score: 3, status: "needs_human" }),
        lead({ processed_at: yesterday, is_hot: true, score: 6, status: "pending_approval" }),
        lead({ processed_at: yesterday, score: 1, route: "spam", status: "discarded" }),
      ],
      now,
    );
    expect(stats).toEqual({
      leadsToday: 2,
      hotToday: 1,
      awaitingApproval: 2,
      needsHuman: 1,
      averageScore: 6, // (9 + 3 + 6) / 3; spam is left out
      total: 4,
    });
  });

  it("has no average when there is nothing to average", () => {
    expect(computeStats([], now).averageScore).toBeNull();
  });

  it("ignores broken dates", () => {
    expect(isSameLocalDay("not a date", now)).toBe(false);
  });
});

describe("filterLeads and newestFirst", () => {
  it("filters by route and by search text", () => {
    expect(filterLeads(data.leads, "spam", "").every((r) => r.route === "spam")).toBe(true);
    expect(filterLeads(data.leads, "all", "").length).toBe(data.leads.length);
    const found = filterLeads(data.leads, "all", "TEXTILE");
    expect(found.length).toBeGreaterThan(0);
    expect(found.every((r) => r.lead.message.toLowerCase().includes("textile"))).toBe(true);
    expect(filterLeads(data.leads, "all", "zzz-no-such-text")).toEqual([]);
  });

  it("sorts newest first without changing the input", () => {
    const before = data.leads.map((r) => r.lead.id);
    const sorted = newestFirst(data.leads);
    const times = sorted.map((r) => new Date(r.lead.received_at).getTime());
    expect(times).toEqual([...times].sort((a, b) => b - a));
    expect(data.leads.map((r) => r.lead.id)).toEqual(before);
  });
});

describe("demo data", () => {
  it("is fictional: example.com addresses only, and every route is present", () => {
    for (const record of data.leads) {
      expect(record.lead.email === "" || record.lead.email.endsWith("@example.com")).toBe(true);
    }
    expect(new Set(data.leads.map((r) => r.route))).toEqual(
      new Set(["draft_reply", "handover", "nurture", "spam"]),
    );
  });

  it("never has a draft on a handover or spam lead", () => {
    for (const record of data.leads) {
      if (record.route === "handover" || record.route === "spam") {
        expect(record.draft_reply).toBe("");
      }
    }
  });

  it("is moved forward so the newest lead is today", () => {
    const rebased = rebaseToToday(data, now);
    const stats = computeStats(rebased.leads, now);
    expect(stats.leadsToday).toBeGreaterThan(0);
    expect(rebased.leads.length).toBe(data.leads.length);
    expect(data.leads[0].processed_at.startsWith("2026-01")).toBe(true); // input untouched
  });
});

describe("applyReview", () => {
  it("only changes the status and the review time", () => {
    const record = data.leads[0];
    const approved = applyReview(record, "approve", now);
    expect(approved.status).toBe("approved");
    expect(approved.reviewed_at).toBe(now.toISOString());
    expect(approved.draft_reply).toBe(record.draft_reply);
    expect(applyReview(record, "reject", now).status).toBe("rejected");
    expect(applyReview(record, "handover", now).status).toBe("needs_human");
    expect(record.status).not.toBe("approved"); // original not modified
  });
});
