import type { ReactNode } from "react";
import {
  ROUTE_LABELS,
  STATUS_LABELS,
  formatDateTime,
  formatShort,
  humanize,
  type Stats,
} from "./stats";
import type { LeadRecord, ReviewAction, Route, RunRecord, Status } from "./types";

export function RouteBadge({ route }: { route: Route }) {
  return <span className={`badge route-${route}`}>{ROUTE_LABELS[route]}</span>;
}

export function StatusBadge({ status }: { status: Status }) {
  return <span className={`badge status-${status}`}>{STATUS_LABELS[status]}</span>;
}

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
      <table>
        <thead>
          <tr>
            <th>Received</th>
            <th>Name</th>
            <th>Intent</th>
            <th className="num">Score</th>
            <th>Route</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {leads.map((record) => (
            <tr
              key={record.lead.id}
              className={record.lead.id === selectedId ? "selected" : undefined}
              onClick={() => onSelect(record.lead.id)}
            >
              <td className="nowrap">{formatShort(record.lead.received_at)}</td>
              <td className="nowrap">
                <button
                  type="button"
                  className="link"
                  aria-pressed={record.lead.id === selectedId}
                  onClick={() => onSelect(record.lead.id)}
                >
                  {record.lead.name || "(no name)"}
                </button>
                <div className="sub">{record.lead.channel}</div>
              </td>
              <td>{humanize(record.intent)}</td>
              <td className="num">
                <span className={record.is_hot ? "score hot" : "score"}>{record.score}</span>
                {record.is_hot && <span className="hot-tag">HOT</span>}
              </td>
              <td>
                <RouteBadge route={record.route} />
              </td>
              <td>
                <StatusBadge status={record.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="field">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

const ACTIONS: { action: ReviewAction; label: string; className: string }[] = [
  { action: "approve", label: "Approve draft", className: "primary" },
  { action: "reject", label: "Reject draft", className: "" },
  { action: "handover", label: "Hand over to a human", className: "" },
];

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
  return (
    <article className="detail" aria-label="Lead detail">
      <header className="detail-head">
        <div>
          <h2>{lead.name || "(no name)"}</h2>
          <div className="sub">
            {lead.id} · {lead.channel} · received {formatDateTime(lead.received_at)}
          </div>
        </div>
        <div className="detail-badges">
          <RouteBadge route={record.route} />
          <StatusBadge status={record.status} />
        </div>
      </header>

      <dl className="fields">
        <Field label="Email">{lead.email || "-"}</Field>
        <Field label="Phone">{lead.phone || "-"}</Field>
        <Field label="Intent">{humanize(record.intent)}</Field>
        <Field label="Score">
          {record.score} / 10 {record.is_hot && <span className="hot-tag">HOT</span>}
        </Field>
      </dl>

      <h3>Message</h3>
      <p className="message">{lead.message}</p>

      <h3>What the agent understood</h3>
      <dl className="fields">
        <Field label="Property">{humanize(extracted.property_type)}</Field>
        <Field label="Monthly bill">{bill === null ? "-" : `PKR ${bill.toLocaleString()}`}</Field>
        <Field label="Sanctioned load">
          {extracted.sanctioned_load_kw === null ? "-" : `${extracted.sanctioned_load_kw} kW`}
        </Field>
        <Field label="Location">{extracted.location || "-"}</Field>
        <Field label="Timeline">{humanize(extracted.timeline)}</Field>
        <Field label="Interested in">{extracted.product_interest.join(", ") || "-"}</Field>
      </dl>

      {breakdown.length > 0 && (
        <>
          <h3>Score breakdown</h3>
          <ul className="chips">
            {breakdown.map(([name, points]) => (
              <li key={name}>
                {humanize(name)} <strong>+{points}</strong>
              </li>
            ))}
          </ul>
        </>
      )}

      {record.missing_info.length > 0 && (
        <>
          <h3>Still missing</h3>
          <ul className="chips">
            {record.missing_info.map((item) => (
              <li key={item}>{humanize(item)}</li>
            ))}
          </ul>
        </>
      )}

      {record.handover_reason && (
        <>
          <h3>Handover reason</h3>
          <p className="notice warn">{record.handover_reason}</p>
        </>
      )}

      {record.flags.length > 0 && (
        <>
          <h3>Flags</h3>
          <ul className="chips">
            {record.flags.map((flag) => (
              <li key={flag} className="flag">
                {humanize(flag)}
              </li>
            ))}
          </ul>
        </>
      )}

      {record.rejected_drafts.length > 0 && (
        <>
          <h3>Drafts blocked by the safety checks</h3>
          <ul className="plain">
            {record.rejected_drafts.map((rejected) => (
              <li key={rejected.attempt}>
                Attempt {rejected.attempt}:{" "}
                {rejected.problems.map((problem) => humanize(problem.check)).join(", ")}
              </li>
            ))}
          </ul>
        </>
      )}

      <h3>Draft reply</h3>
      {record.draft_reply ? (
        <>
          <pre className="draft">{record.draft_reply}</pre>
          <p className="sub">
            Draft only. It has not been sent. A person reviews it and sends it themselves.
          </p>
        </>
      ) : (
        <p className="empty">No draft. A person writes this reply.</p>
      )}

      <div className="actions">
        {ACTIONS.map(({ action, label, className }) => (
          <button
            key={action}
            type="button"
            className={className}
            disabled={busy || (action === "approve" && !record.draft_reply)}
            onClick={() => onReview(action)}
          >
            {label}
          </button>
        ))}
      </div>
      <p className="sub">
        {demo
          ? "Demo data: these buttons only change this page. Nothing is saved or sent."
          : "These buttons record your decision in the local data. Nothing is sent to the customer."}
        {record.reviewed_at && ` Last reviewed ${formatDateTime(record.reviewed_at)}.`}
      </p>
    </article>
  );
}

export function RunHistory({ runs }: { runs: RunRecord[] }) {
  if (runs.length === 0) {
    return <p className="empty">No runs yet.</p>;
  }
  const newest = [...runs].sort((a, b) => b.started_at.localeCompare(a.started_at));
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Started</th>
            <th>Source</th>
            <th>Model</th>
            <th className="num">Leads</th>
            <th className="num">Drafts</th>
            <th className="num">Handovers</th>
            <th className="num">Hot</th>
            <th className="num">Tokens</th>
            <th className="num">Cost est.</th>
            <th className="num">Errors</th>
          </tr>
        </thead>
        <tbody>
          {newest.map((run) => (
            <tr key={run.id}>
              <td className="nowrap">{formatShort(run.started_at)}</td>
              <td>{run.source}</td>
              <td>
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
