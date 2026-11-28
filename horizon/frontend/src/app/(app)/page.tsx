"use client";
import Link from "next/link";
import { useState } from "react";
import ForecastChart, { type ChartData } from "@/components/ForecastChart";
import KpiExplain, { type Kpi } from "@/components/KpiExplain";
import { can, useMe } from "@/components/Shell";
import {
  IconBank, IconCalendar, IconChecklist, IconChevron, IconDoc, IconDots, IconGavel, IconInbox, IconPlus, IconTransfer,
  IconTrend, IconWallet, IconWarning,
} from "@/components/icons";
import { Badge, Drawer, ErrorBox, Loading, StatusChip } from "@/components/ui";
import { useFetch } from "@/lib/hooks";
import { FLAGS, fmtAmount, fmtDate, fmtMillions, fmtMoney, fmtShortDate } from "@/lib/format";

/** Les montants bruts (« 480000.00 EUR ») renvoyés dans les libellés sont reformatés en fr-FR. */
export function prettySubtitle(s: string): string {
  return s.replace(/(\d+\.\d{2}) (EUR|USD|GBP|CHF)/g, (_, a, c) => fmtAmount(a, c));
}

/** Ordre d'affichage du panneau : le plus gros lot à approuver, puis les alertes, puis les autres lots. */
function prioritized(items: any[]): any[] {
  const batches = items.filter((i) => i.kind === "BATCH_APPROVAL").sort((a, b) => Number(b.amount?.amount ?? 0) - Number(a.amount?.amount ?? 0));
  const critical = items.filter((i) => i.severity === "critical");
  const others = items.filter((i) => i.kind !== "BATCH_APPROVAL" && i.severity !== "critical");
  return [...critical, ...batches.slice(0, 1), ...others, ...batches.slice(1)];
}

function Wave({ tone = "#00915a" }: { tone?: string }) {
  return (
    <svg className="kpi-wave" viewBox="0 0 200 60" preserveAspectRatio="none" aria-hidden="true">
      <path d="M0 60 C40 40 70 52 110 30 S170 8 200 4 V60 Z" fill={tone} opacity="0.08" />
      <path d="M0 60 C50 50 90 56 130 40 S180 26 200 22 V60 Z" fill={tone} opacity="0.07" />
    </svg>
  );
}

function batchChip(b: any) {
  if (b.status === "COMPLETED") {
    const c = b.status_counts ?? {};
    if ((c.EXECUTED ?? 0) === b.payment_count) return <StatusChip status="EXECUTED" label="Exécuté" />;
    if ((c.REJECTED ?? 0) === b.payment_count) return <StatusChip status="REJECTED" label="Rejeté" />;
    return <Badge tone="amber">Partiel : {c.EXECUTED ?? 0} exéc. / {c.REJECTED ?? 0} rej.</Badge>;
  }
  if (b.status === "PENDING_APPROVAL" || b.status === "TO_REVIEW" || b.status === "DRAFT") return <StatusChip status="PENDING_APPROVAL" label={b.status === "DRAFT" ? "Brouillon" : "En attente"} />;
  return <StatusChip status={b.status} label={b.status_label} />;
}

export default function Dashboard() {
  const me = useMe();
  const [horizon, setHorizon] = useState(90);
  const [open, setOpen] = useState<Kpi | null>(null);
  const ov = useFetch("/v1/overview");
  const chart = useFetch<ChartData>(`/v1/forecasts/chart?horizon_days=${horizon}`);
  const batches = useFetch<{ data: any[] }>("/v1/payment-batches?limit=4");

  if (ov.error) return <ErrorBox error={ov.error} />;
  if (!ov.data) return <Loading />;
  const d = ov.data;
  const k: Record<string, Kpi> = Object.fromEntries(d.kpis.map((x: Kpi) => [x.key, x]));
  const accounts: any[] = d.accounts;
  const sims = accounts.filter((a) => a.kind === "SIMULATED").sort((a, b) =>
    (a.currency === "EUR" ? 0 : 1) - (b.currency === "EUR" ? 0 : 1) || ["FR", "DE", "IT"].indexOf(a.entity.country_code) - ["FR", "DE", "IT"].indexOf(b.entity.country_code));
  const ext = accounts.filter((a) => a.kind === "EXTERNAL_READONLY");

  const kpiCard = (key: string, icon: React.ReactNode, body: React.ReactNode, warn = false) => (
    <button className="kpi" onClick={() => setOpen(k[key])} data-testid={`kpi-${key}`} aria-haspopup="dialog"
      aria-label={`${k[key].label} — afficher le calcul et les données sources`}>
      <span className={`kpi-icon ${warn ? "warn" : ""}`}>{icon}</span>
      <span>{body}<span className="kpi-hint">Voir le calcul et les sources →</span></span>
      <Wave tone={warn ? "#d0720b" : "#00915a"} />
    </button>
  );

  return (
    <>
      <div className="page-head">
        <div className="page-title">
          <h1>La maîtrise de votre trésorerie.</h1>
          <p>{me?.organization.name ?? "Groupe Lumière"} · Consolidation en EUR · Données de démonstration</p>
        </div>
        <div className="page-actions">
          <span className="date-chip"><IconCalendar size={22} />{fmtDate(d.as_of)}</span>
          {can(me, "payment.prepare") && (
            <Link href="/paiements?nouveau=1" className="btn btn-primary btn-big" data-testid="new-payment"><IconPlus size={22} />Nouveau paiement</Link>
          )}
        </div>
      </div>

      <div className="kpis">
        {kpiCard("available_liquidity", <IconWallet size={36} />, <>
          <span className="kpi-label">{k.available_liquidity.label}</span>
          <div className="kpi-value" data-testid="kpi-liquidity-value">{fmtMillions(k.available_liquidity.value.amount)}</div>
        </>)}
        {kpiCard("payments_to_approve", <IconChecklist size={36} />, <>
          <span className="kpi-label">{k.payments_to_approve.label}</span>
          <div className="kpi-value">{k.payments_to_approve.value.count}<span className="sub">{fmtMillions(k.payments_to_approve.value.total.amount)}</span></div>
        </>)}
        {kpiCard("expected_receipts_7d", <IconInbox size={36} />, <>
          <span className="kpi-label">{k.expected_receipts_7d.label}</span>
          <div className="kpi-value">{fmtMillions(k.expected_receipts_7d.value.amount)}</div>
          <div className="kpi-sub">{k.expected_receipts_7d.sublabel}</div>
        </>)}
        {kpiCard("alerts", <IconWarning size={36} />, <>
          <span className="kpi-label">{k.alerts.label}</span>
          <div className="kpi-value">{k.alerts.value.count}</div>
        </>, true)}
      </div>

      <div className="dash-mid">
        <section className="card" data-testid="forecast-card">
          <header className="card-head">
            <h2><IconTrend size={26} /><span>Prévision de trésorerie</span></h2>
            <div className="seg" role="group" aria-label="Horizon de prévision">
              {[7, 30, 90].map((h) => (
                <button key={h} className={horizon === h ? "active" : ""} aria-pressed={horizon === h} onClick={() => setHorizon(h)}>{h} jours</button>
              ))}
            </div>
          </header>
          {chart.error ? <ErrorBox error={chart.error} /> : chart.data ? <ForecastChart data={chart.data} /> : <Loading />}
          <div className="row-end" style={{ marginTop: 4 }}><Link className="link small" href="/tresorerie">Détail des flux et scénarios →</Link></div>
        </section>

        <section className="card" id="decisions" data-testid="decision-center">
          <header className="card-head"><h2><IconGavel size={26} /><span>Centre de décisions</span></h2>
            <span className="small muted">{d.decisions.length} élément(s) prioritaires</span></header>
          {d.decisions.length === 0 && <p className="empty">Aucune décision en attente.</p>}
          <ul className="decisions">
            {prioritized(d.decisions).slice(0, 3).map((i: any) => (
              <li className="decision" key={i.key} data-testid="decision-item">
                <span className={`decision-ico ${i.severity === "critical" ? "critical" : ""}`}>
                  <IconWarning size={30} />{i.severity === "critical" ? "Critique" : i.is_alert ? "Alerte" : "Action"}
                </span>
                <div>
                  <h3>{i.title}</h3>
                  <p>{prettySubtitle(i.subtitle)}</p>
                  <div className="meta">Source : {i.source.module}{i.source.reference ? ` ${i.source.reference}` : ""} · Resp. : {i.owner} · Échéance : {fmtShortDate(i.due_date)} · État : {i.state}</div>
                  {i.acknowledgements?.length > 0 && <div className="acked">Pris en compte par {i.acknowledgements[0].by} — cause non résolue</div>}
                </div>
                <Link href={i.action.href} className="btn btn-outline">{i.action.label}<IconChevron size={16} /></Link>
              </li>
            ))}
          </ul>
          {d.decisions.length > 3 && <div className="row-end"><Link className="link small" href="/tresorerie/rapprochement#decisions">Voir les {d.decisions.length} éléments →</Link></div>}
        </section>
      </div>

      <div className="dash-bottom">
        <section className="card" data-testid="group-accounts">
          <header className="card-head"><h2><IconBank size={28} /><span>Comptes du groupe</span></h2><Link className="link small" href="/comptes">Tous les comptes →</Link></header>
          <table className="table">
            <thead><tr><th>Entité</th><th>Pays</th><th>Devise</th><th className="num">Solde disponible</th></tr></thead>
            <tbody>
              {sims.map((a) => (
                <tr key={a.id}>
                  <td><Link href={`/comptes/${a.id}`}><strong>{a.entity.name}</strong></Link>{a.currency !== "EUR" && <span className="small muted"> · {a.name.split("—")[1]?.trim()}</span>}</td>
                  <td style={{ whiteSpace: "nowrap" }}><span aria-hidden="true">{FLAGS[a.entity.country_code]}</span> {a.entity.country_name}</td>
                  <td>{a.currency}</td>
                  <td className="num strong-green">{fmtAmount(a.balance.available.amount, a.currency)}</td>
                </tr>
              ))}
              {ext.map((a) => (
                <tr key={a.id} className="sep">
                  <td><Link href={`/comptes/${a.id}`}><strong>{a.entity.name}</strong></Link><br />
                    <Badge tone={a.balance.freshness?.stale ? "amber" : "grey"} icon={<IconWarning size={13} />}>Lecture seule{a.balance.freshness?.stale ? " · données périmées" : ""}</Badge></td>
                  <td>{a.name.includes("GBP") ? <><span aria-hidden="true">🇬🇧</span> Externe</> : "Externe"}</td>
                  <td>{a.currency}</td>
                  <td className="num">{a.balance.available ? fmtAmount(a.balance.available.amount, a.currency) : "—"}<br /><span className="small muted">observé {fmtDate(a.balance.observed_at)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small muted" style={{ marginBottom: 0 }}>Les comptes externes en lecture seule ne sont pas inclus dans les liquidités disponibles.</p>
        </section>

        <section className="card" data-testid="recent-payments">
          <header className="card-head"><h2><IconTransfer size={28} /><span>Paiements récents</span></h2><Link className="link small" href="/paiements">Tous les paiements →</Link></header>
          {batches.error && <ErrorBox error={batches.error} />}
          <ul className="payments-list">
            {(batches.data?.data ?? []).map((b) => (
              <li key={b.id} className="payment-row">
                <IconDoc size={26} />
                <div><strong>{b.label}</strong><small>{fmtDate(b.created_at)} · {b.entity.name}</small></div>
                <span className="amt">{fmtMoney(b.total)}</span>
                <span>{batchChip(b)}</span>
                <Link href={`/paiements/lots/${b.id}`} className="icon-btn" aria-label={`Ouvrir ${b.reference}`}><IconDots size={20} /></Link>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <Drawer open={!!open} title={open ? `${open.label} — justification` : ""} onClose={() => setOpen(null)}>
        {open && <KpiExplain kpi={open} />}
      </Drawer>
    </>
  );
}
