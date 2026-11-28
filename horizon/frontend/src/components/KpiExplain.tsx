"use client";
import { fmtDate, fmtMoney } from "@/lib/format";
import type { Money } from "@/lib/api";
import { A, Badge, Notice } from "./ui";

type Rate = { rate: string; as_of: string; source: string; pair: string };
export type Kpi = { key: string; label: string; sublabel?: string; value: any; explain: any };

function RateCell({ r }: { r?: Rate }) {
  if (!r) return <>—</>;
  return <span className="small">{r.pair} = {r.rate}<br /><span className="muted">{r.as_of} · {r.source}</span></span>;
}

/** Justification d'un indicateur : formule, composantes, taux, exclusions, sources. */
export default function KpiExplain({ kpi }: { kpi: Kpi }) {
  const ex = kpi.explain;
  return (
    <div className="stack" data-testid={`explain-${kpi.key}`}>
      <div>
        <div className="muted small">Formule</div>
        <div className="formula" data-testid="kpi-formula">{ex.formula}</div>
      </div>
      {kpi.key === "available_liquidity" && (
        <>
          <table className="table table-sm">
            <thead><tr><th>Compte simulé</th><th className="num">Comptabilisé</th><th className="num">Réservé</th><th className="num">Disponible</th><th className="num">En EUR</th><th>Taux</th></tr></thead>
            <tbody>
              {ex.components.map((c: any) => (
                <tr key={c.account_id}><td><A href={`/comptes/${c.account_id}`}>{c.account}</A></td><td className="num">{fmtMoney(c.booked, 2)}</td><td className="num">{fmtMoney(c.reserved, 2)}</td>
                  <td className="num">{fmtMoney(c.available, 2)}</td><td className="num"><strong>{fmtMoney(c.available_in_base, 2)}</strong></td><td><RateCell r={c.rate} /></td></tr>
              ))}
              <tr className="sep"><td colSpan={4}><strong>Total</strong></td><td className="num"><strong>{fmtMoney(kpi.value, 2)}</strong></td><td /></tr>
            </tbody>
          </table>
          <h4>Exclus de l’indicateur</h4>
          <table className="table table-sm">
            <thead><tr><th>Compte</th><th>Motif</th><th className="num">Observé (EUR)</th><th>Fraîcheur</th></tr></thead>
            <tbody>
              {ex.excluded.map((e: any, i: number) => (
                <tr key={i}><td>{e.account}</td><td>{e.reason}</td><td className="num">{fmtMoney(e.observed_in_base, 2)}</td>
                  <td>{e.freshness ? <Badge tone={e.freshness.stale ? "red" : "green"}>{e.freshness.label} ({e.freshness.age_hours} h)</Badge> : "—"}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="small">Estimation consolidée incluant les comptes externes : <strong>{fmtMoney(ex.consolidated_estimate_including_external, 2)}</strong> (présentée séparément).</p>
          {ex.warnings?.map((w: string) => <Notice key={w} tone="warn">{w}</Notice>)}
        </>
      )}
      {kpi.key === "payments_to_approve" && (
        <table className="table table-sm">
          <thead><tr><th>Lot</th><th className="num">Paiements</th><th className="num">Total</th><th className="num">En EUR</th><th>Taux</th></tr></thead>
          <tbody>
            {ex.components.map((c: any) => (
              <tr key={c.batch_id}><td><A href={`/paiements/lots/${c.batch_id}`}>{c.reference}</A> — {c.label}</td><td className="num">{c.payment_count}</td>
                <td className="num">{fmtMoney(c.total, 2)}</td><td className="num">{fmtMoney(c.total_in_base, 2)}</td><td><RateCell r={c.rate} /></td></tr>
            ))}
            <tr className="sep"><td><strong>Total</strong></td><td className="num"><strong>{kpi.value.count}</strong></td><td /><td className="num"><strong>{fmtMoney(kpi.value.total, 2)}</strong></td><td /></tr>
          </tbody>
        </table>
      )}
      {kpi.key === "expected_receipts_7d" && (
        <>
          <table className="table table-sm">
            <thead><tr><th>Contrepartie</th><th>Référence</th><th>Date attendue</th><th>Confiance</th><th className="num">Montant</th><th>Taux</th></tr></thead>
            <tbody>
              {ex.components.map((c: any) => (
                <tr key={c.id}><td>{c.counterparty}</td><td className="mono">{c.reference}</td><td>{fmtDate(c.expected_date)}</td>
                  <td><Badge tone={c.confidence === "HIGH" ? "green" : c.confidence === "MEDIUM" ? "amber" : "grey"}>{({ HIGH: "Haute", MEDIUM: "Moyenne", LOW: "Faible" } as Record<string, string>)[c.confidence] ?? c.confidence}</Badge></td>
                  <td className="num">{fmtMoney(c.amount, 2)}</td><td><RateCell r={c.rate} /></td></tr>
              ))}
              <tr className="sep"><td colSpan={4}><strong>Total</strong></td><td className="num"><strong>{fmtMoney(kpi.value as Money, 2)}</strong></td><td /></tr>
            </tbody>
          </table>
          {ex.note && <Notice>{ex.note}</Notice>}
        </>
      )}
      {kpi.key === "alerts" && (
        <table className="table table-sm">
          <thead><tr><th>Alerte</th><th>Source</th><th>Responsable</th><th>Échéance</th><th>État</th></tr></thead>
          <tbody>
            {ex.components.map((c: any) => (
              <tr key={c.key}><td><strong>{c.title}</strong><br /><span className="small muted">{c.subtitle}</span></td><td>{c.source.module}</td>
                <td>{c.owner}</td><td>{fmtDate(c.due_date)}</td><td>{c.state}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="small muted">Sources : {ex.sources?.join(" · ")}</p>
    </div>
  );
}
