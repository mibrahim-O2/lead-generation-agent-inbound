import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LeadDetail, LeadsTable, RunHistory, StatTiles, ThemeToggle } from "./components";
import { API_URL, MODE, loadData, reviewLead } from "./data";
import { ROUTE_LABELS, computeStats, filterLeads, newestFirst } from "./stats";
import { type ThemeChoice, applyThemeChoice, readThemeChoice, saveThemeChoice } from "./theme";
import type { DashboardData, ReviewAction, Route } from "./types";

const REFRESH_MS = 5000;
const ROUTES: (Route | "all")[] = ["all", "draft_reply", "handover", "nurture", "spam"];

export function App() {
  const demo = MODE === "demo";
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [route, setRoute] = useState<Route | "all">("all");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [theme, setTheme] = useState<ThemeChoice>(() => readThemeChoice());
  const detailRef = useRef<HTMLDivElement>(null);

  // On narrow screens the detail panel sits below the list, so bring it into view.
  function selectLead(id: string) {
    setSelectedId(id);
    if (window.matchMedia?.("(max-width: 1180px)").matches) {
      window.requestAnimationFrame(() =>
        detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    }
  }

  useEffect(() => {
    applyThemeChoice(theme);
    saveThemeChoice(theme); // fails quietly when the browser blocks storage
  }, [theme]);

  const refresh = useCallback(async () => {
    try {
      setData(await loadData());
      setUpdatedAt(new Date());
      setError("");
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem));
    }
  }, []);

  useEffect(() => {
    void refresh();
    if (demo) return; // demo data never changes, and demo mode makes no requests
    const timer = window.setInterval(() => void refresh(), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [demo, refresh]);

  const leads = useMemo(() => newestFirst(data?.leads ?? []), [data]);
  const visible = useMemo(() => filterLeads(leads, route, query), [leads, route, query]);
  const stats = useMemo(() => computeStats(leads, new Date()), [leads]);
  const selected = leads.find((record) => record.lead.id === selectedId) ?? visible[0] ?? null;

  async function review(action: ReviewAction) {
    if (!selected || !data) return;
    setBusy(true);
    try {
      const updated = await reviewLead(selected, action);
      setData({
        ...data,
        leads: data.leads.map((record) => (record.lead.id === updated.lead.id ? updated : record)),
      });
      setError("");
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Lead Agent Dashboard</h1>
          <p className="lede">Inbound enquiries, scored and drafted. A person approves and sends.</p>
        </div>
        <div className="top-right">
          <span className={demo ? "mode demo" : "mode local"}>
            {demo ? "Demo data" : "Local mode"}
          </span>
          <ThemeToggle value={theme} onChange={setTheme} />
          {!demo && (
            <button type="button" className="btn" onClick={() => void refresh()}>
              Refresh
            </button>
          )}
        </div>
      </header>

      {demo ? (
        <p className="banner">
          <strong>Demo data.</strong> Everything on this page is fictional sample data bundled with
          the site. It makes no network requests, and the buttons only change this page.
        </p>
      ) : (
        <p className="status-line">
          Connected to {API_URL}
          {updatedAt && ` · updated ${updatedAt.toLocaleTimeString()}`}
          {data && data.pending.length > 0 && ` · ${data.pending.length} queued, not processed yet`}
        </p>
      )}

      {error && (
        <p className="banner error" role="alert">
          {demo
            ? error
            : `Cannot reach the local API at ${API_URL}: ${error}. Start it with "make serve".`}
        </p>
      )}

      {data === null && !error && <p className="empty">Loading...</p>}

      {data && (
        <>
          <StatTiles stats={stats} />

          <section className="panel">
            <div className="panel-head">
              <h2>Leads</h2>
              <div className="filters">
                <div className="segmented" role="group" aria-label="Filter by route">
                  {ROUTES.map((option) => (
                    <button
                      key={option}
                      type="button"
                      className={route === option ? "active" : ""}
                      aria-pressed={route === option}
                      onClick={() => setRoute(option)}
                    >
                      {option === "all" ? "All" : ROUTE_LABELS[option]}
                    </button>
                  ))}
                </div>
                <input
                  type="search"
                  placeholder="Search name or message"
                  aria-label="Search leads"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </div>
            </div>
            <div className="split">
              <LeadsTable
                leads={visible}
                selectedId={selected?.lead.id ?? null}
                onSelect={selectLead}
              />
              <div ref={detailRef} className="detail-slot">
                {selected ? (
                  <LeadDetail
                  record={selected}
                  demo={demo}
                  busy={busy}
                  onReview={(action) => void review(action)}
                />
                ) : (
                  <p className="empty">Select a lead to see its draft.</p>
                )}
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Run history</h2>
            </div>
            <RunHistory runs={data.runs} />
          </section>
        </>
      )}

      <footer>
        Fictional company and dummy data. This dashboard never sends anything.
      </footer>
    </div>
  );
}
