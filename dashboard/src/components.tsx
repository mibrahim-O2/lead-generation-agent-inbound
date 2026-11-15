import type { ReactNode } from "react";
import {
  ROUTE_LABELS,
  STATUS_LABELS,
  type Stats,
  formatDateTime,
  formatShort,
  humanize,
  scoreLevel,
} from "./stats";
import type { ThemeChoice } from "./theme";
import type { LeadRecord, ReviewAction, Route, RunRecord, Status } from "./types";

// ------------------------------------------------------------------ small pieces

export function RouteBadge({ route }: { route: Route }) {
  return <span className={`route route-${route}`}>{ROUTE_LABELS[route]}</span>;
}

export function StatusBadge({ status }: { status: Status }) {
  return <span className={`badge status-${status}`}>{STATUS_LABELS[status]}</span>;
}

export function HotBadge() {
  return (
    <span className="hot-badge" title="Hot lead: score 7 or more">
      HOT
    </span>
  );
}

/** The score as a coloured chip plus a small bar: strong from 7, medium 4-6, muted below 4. */
export function ScoreChip({ score, hot }: { score: number; hot: boolean }) {
  const level = scoreLevel(score);
  const width = `${Math.max(0, Math.min(10, score)) * 10}%`;
  return (
    <span className="score-cell">
      <span className={`score-chip chip-${level}`} aria-label={`Score ${score} out of 10`}>
        {score}
      </span>
      <span className="score-bar" aria-hidden="true">
        <span className={`score-fill fill-${level}`} style={{ width }} />
      </span>
      {hot && <HotBadge />}
    </span>
  );
}

const THEME_OPTIONS: { value: ThemeChoice; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

export function ThemeToggle({
  value,
  onChange,
}: {
  value: ThemeChoice;
  onChange: (choice: ThemeChoice) => void;
}) {
  return (
    <div className="segmented" role="group" aria-label="Colour theme">
      {THEME_OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          className={value === option.value ? "active" : ""}
          aria-pressed={value === option.value}
          title={option.value === "system" ? "Follow your computer's setting" : undefined}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ tiles

export function StatTiles({ stats }: { stats: Stats }) {
  const tiles: { label: string; value: string; hint: string }[] = [
    { label: "Leads today", value: String(stats.leadsToday), hint: `${stats.total} in total` },
    { label: "Hot leads today", value: String(stats.hotToday), hint: "Score 7 or more" },
    {
      label: "Awaiting approval",
      value: String(stats.awaitingApproval),
      hint: "Drafts a person must review",
    },
    { label: "Needs a human", value: String(stats.needsHuman), hint: "Handed over" },
    {
      label: "Average score",
      value: stats.averageScore === null ? "-" : stats.averageScore.toFixed(1),
      hint: "Out of 10, spam excluded",
    },
  ];
  return (
    <section className="tiles" aria-label="Summary">
      {tiles.map((tile) => (
        <div className="tile" key={tile.label}>
          <div className="tile-label">{tile.label}</div>
          <div className="tile-value">{tile.value}</div>
          <div className="tile-hint">{tile.hint}</div>
        </div>
      ))}
    </section>
  );
}

// ------------------------------------------------------------------ leads table

export function LeadsTable({
  leads,
  selectedId,
  onSelect,
}: {
  leads: LeadRecord[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (leads.length === 0) {
    return <p className="empty">No leads match.</p>;
  }
  return (
    <div className="table-wrap">
      <table className="leads">
        <thead>
          <tr>
            <th scope="col">Received</th>
            <th scope="col">Lead</th>
            <th scope="col">Score</th>
            <th scope="col">Route</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {leads.map((record) => {
            const selected = record.lead.id === selectedId;
            return (
              <tr
                key={record.lead.id}
                className={selected ? "selected" : undefined}
                onClick={() => onSelect(record.lead.id)}
              >
                <td className="nowrap col-received">{formatShort(record.lead.received_at)}</td>
                <td className="nowrap col-lead">
                  <button
                    type="button"
                    className="name-button"
                    aria-pressed={selected}
                    onClick={() => onSelect(record.lead.id)}
                  >
                    {record.lead.name || "(no name)"}
                  </button>
                  <span className="cell-sub">
                    {humanize(record.intent)} · {record.lead.channel}
                  </span>
                </td>
                <td className="col-score">
                  <ScoreChip score={record.score} hot={record.is_hot} />
                </td>
                <td className="col-route">
                  <RouteBadge route={record.route} />
                </td>
                <td className="col-status">
                  <StatusBadge status={record.status} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ------------------------------------------------------------------ lead detail

function Field({
  label,
  wide = false,
  children,
}: {
  label: string;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={wide ? "wide" : undefined}>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

export function LeadDetail({
  record,
  demo,
  busy,
  onReview,
}: {
  record: LeadRecord;
  demo: boolean;
  busy: boolean;
  onReview: (action: ReviewAction) => void;
}) {
  const { lead, extracted } = record;
  const bill = extracted.monthly_bill_pkr;
  const breakdown = Object.entries(record.score_breakdown);
  const noDraft = !record.draft_reply;
  const approveWhy = noDraft ? "No draft to approve: a person writes this reply." : "";
  const busyWhy = busy ? "Saving your decision..." : "";

  return (
    <article className="detail" aria-label="Lead detail">
      <header className="detail-head">
        <div>
          <h2>{lead.name || "(no name)"}</h2>
          <p className="detail-meta">Lead {lead.id}</p>
        </div>
        <div className="detail-badges">
          <RouteBadge route={record.route} />
          <StatusBadge status={record.status} />
        </div>
      </header>

      <Section title="Contact">
        <dl className="fields">
          <Field label="Email" wide>
            {lead.email || "-"}
          </Field>
          <Field label="Phone">{lead.phone || "-"}</Field>
          <Field label="Channel">{lead.channel}</Field>
          <Field label="Received" wide>
            {formatDateTime(lead.received_at)}
          </Field>
        </dl>
      </Section>

      <Section title="Message">
        <p className="text-box">{lead.message}</p>
      </Section>

      <Section title="What the agent understood">
        <dl className="fields">
          <Field label="Intent">{humanize(record.intent)}</Field>
          <Field label="Property">{humanize(extracted.property_type)}</Field>
          <Field label="Monthly bill">
            {bill === null ? "-" : `PKR ${bill.toLocaleString()}`}
          </Field>
          <Field label="Sanctioned load">
            {extracted.sanctioned_load_kw === null ? "-" : `${extracted.sanctioned_load_kw} kW`}
          </Field>
          <Field label="Location">{extracted.location || "-"}</Field>
          <Field label="Timeline">{humanize(extracted.timeline)}</Field>
          <Field label="Interested in" wide>
            {extracted.product_interest.join(", ") || "-"}
          </Field>
          <Field label="Still missing" wide>
            {record.missing_info.map(humanize).join(", ") || "Nothing"}
          </Field>
        </dl>
      </Section>

      <Section title="Score">
        <ScoreChip score={record.score} hot={record.is_hot} />
        {breakdown.length > 0 && (
          <ul className="breakdown" aria-label="Score breakdown">
            {breakdown.map(([name, points]) => (
              <li key={name}>
                <span>{humanize(name)}</span>
                <strong>+{points}</strong>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {record.handover_reason && (
        <Section title="Handover reason">
          <p className="reason">{record.handover_reason}</p>
        </Section>
      )}

      {(record.flags.length > 0 || record.rejected_drafts.length > 0) && (
        <Section title="Review notes">
          {record.flags.length > 0 && (
            <ul className="chips" aria-label="Flags">
              {record.flags.map((flag) => (
                <li key={flag} className="flag">
                  {humanize(flag)}
                </li>
              ))}
            </ul>
          )}
          {record.rejected_drafts.length > 0 && (
            <ul className="plain">
              {record.rejected_drafts.map((rejected) => (
                <li key={rejected.attempt}>
                  Draft attempt {rejected.attempt} blocked by the safety checks:{" "}
                  {rejected.problems.map((problem) => humanize(problem.check)).join(", ")}
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}

      <Section title="Draft reply">
        {noDraft ? (
          <p className="muted">No draft. A person writes this reply.</p>
        ) : (
          <p className="text-box draft">{record.draft_reply}</p>
        )}
      </Section>

      <div className="action-box">
        <div className="actions">
          <span title={busyWhy || approveWhy || undefined}>
            <button
              type="button"
              className="btn primary"
              disabled={busy || noDraft}
              aria-describedby={noDraft ? "approve-why" : undefined}
              onClick={() => onReview("approve")}
            >
              Approve draft
            </button>
          </span>
          <span title={busyWhy || undefined}>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => onReview("reject")}
            >
              Reject draft
            </button>
          </span>
          <span title={busyWhy || undefined}>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => onReview("handover")}
            >
              Hand over to a human
            </button>
          </span>
        </div>
        {noDraft && (
          <p className="hint" id="approve-why">
            {approveWhy}
          </p>
        )}
        {busy && (
          <p className="hint" role="status">
            {busyWhy}
          </p>
        )}
        <p className="send-note">
          <strong>Nothing is ever sent from here.</strong>{" "}
          {demo
            ? "Demo data: these buttons only change this page."
            : "These buttons only record your decision in the local data."}{" "}
          A person copies the approved draft and sends it themselves.
          {record.reviewed_at && ` Last reviewed ${formatDateTime(record.reviewed_at)}.`}
        </p>
      </div>
    </article>
  );
}

// ------------------------------------------------------------------ run history

export function RunHistory({ runs }: { runs: RunRecord[] }) {
  if (runs.length === 0) {
    return <p className="empty">No runs yet.</p>;
  }
  const newest = [...runs].sort((a, b) => b.started_at.localeCompare(a.started_at));
  return (
    <div className="table-wrap">
      <table className="runs">
        <thead>
          <tr>
            <th scope="col">Started</th>
            <th scope="col">Source</th>
            <th scope="col">Model</th>
            <th scope="col" className="num">
              Leads
            </th>
            <th scope="col" className="num">
              Drafts
            </th>
            <th scope="col" className="num">
              Handovers
            </th>
            <th scope="col" className="num">
              Hot
            </th>
            <th scope="col" className="num">
              Tokens
            </th>
            <th scope="col" className="num">
              Cost est.
            </th>
            <th scope="col" className="num">
              Errors
            </th>
          </tr>
        </thead>
        <tbody>
          {newest.map((run) => (
            <tr key={run.id}>
              <td className="nowrap">{formatShort(run.started_at)}</td>
              <td>{run.source}</td>
              <td className="nowrap">
                {run.provider}/{run.model}
              </td>
              <td className="num">{run.leads_processed}</td>
              <td className="num">{run.drafts_created}</td>
              <td className="num">{run.handovers}</td>
              <td className="num">{run.hot_leads}</td>
              <td className="num">{run.total_tokens.toLocaleString()}</td>
              <td className="num">
                {run.cost_estimate_usd === null ? "-" : `$${run.cost_estimate_usd.toFixed(4)}`}
              </td>
              <td className={run.errors.length ? "num bad" : "num"}>{run.errors.length}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
