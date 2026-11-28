"use client";
import Link from "next/link";
import { useState } from "react";
import { Badge, Card, ErrorBox, Loading, Notice, PageHeader, Tabs } from "@/components/ui";
import { IconBank } from "@/components/icons";
import { useFetch } from "@/lib/hooks";
import { fmtDateTime, fmtMoney } from "@/lib/format";

export default function Comptes() {
  const [tab, setTab] = useState("accounts");
  const accs = useFetch<{ data: any[] }>("/v1/accounts?limit=200");
  const cons = useFetch(tab === "consolidation" ? "/v1/consolidation" : null);
  return (
    <>
      <PageHeader title="Comptes" subtitle="Soldes explicables : source, heure d’observation et fraîcheur de chaque donnée" />
      <Tabs tabs={[{ id: "accounts", label: "Comptes et soldes" }, { id: "consolidation", label: "Consolidation multidevise" }]} value={tab} onChange={setTab} />
      {tab === "accounts" && (
        <Card title="Comptes visibles" icon={<IconBank size={24} />}>
          {accs.error && <ErrorBox error={accs.error} />}
          {!accs.data ? <Loading /> : (
            <div className="table-wrap">
              <table className="table" data-testid="accounts-table">
                <thead><tr><th>Compte</th><th>Nature</th><th>IBAN (synthétique)</th><th className="num">Comptabilisé</th><th className="num">Réservé</th><th className="num">Disponible</th><th>Source · fraîcheur</th></tr></thead>
                <tbody>
                  {accs.data.data.map((a) => (
                    <tr key={a.id}>
                      <td><Link className="link" href={`/comptes/${a.id}`}>{a.name}</Link><br /><span className="small muted">{a.entity.name} · {a.currency}</span></td>
                      <td><Badge tone={a.kind === "SIMULATED" ? "navy" : "amber"}>{a.kind_label}</Badge></td>
                      <td className="mono">{a.iban}</td>
                      <td className="num">{fmtMoney(a.balance.booked, 2)}</td>
                      <td className="num">{a.balance.reserved ? fmtMoney(a.balance.reserved, 2) : "—"}</td>
                      <td className="num"><strong>{fmtMoney(a.balance.available, 2)}</strong></td>
                      <td className="small">{a.balance.source}<br />
                        <Badge tone={a.balance.freshness?.stale ? "red" : "green"}>{a.balance.freshness?.label ?? "—"}</Badge>{" "}
                        <span className="muted">{fmtDateTime(a.balance.observed_at)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Notice>Règle du solde disponible (comptes simulés) : <strong>disponible = comptabilisé − réservations actives</strong>. Les réservations naissent à l’approbation finale d’un paiement et sont consommées à son exécution ou libérées à son rejet/annulation. Les comptes externes affichent le solde déclaré par leur source, sans recalcul.</Notice>
        </Card>
      )}
      {tab === "consolidation" && (
        <Card title="Consolidation en EUR — taux identifiés et datés">
          {cons.error && <ErrorBox error={cons.error} />}
          {!cons.data ? <Loading /> : (
            <div className="stack">
              <Notice>{cons.data.method}</Notice>
              <h3>Comptes simulés (disponible)</h3>
              <table className="table table-sm">
                <thead><tr><th>Compte</th><th className="num">Disponible</th><th className="num">En EUR</th><th>Taux appliqué</th></tr></thead>
                <tbody>
                  {cons.data.simulated_components.map((c: any) => (
                    <tr key={c.account_id}><td>{c.account}</td><td className="num">{fmtMoney(c.available, 2)}</td><td className="num">{fmtMoney(c.available_in_base, 2)}</td>
                      <td className="small">{c.rate.pair} = {c.rate.rate} · {c.rate.as_of} · {c.rate.source}{c.rate.rate_id ? <span className="muted mono"> (id {c.rate.rate_id.slice(0, 8)})</span> : null}</td></tr>
                  ))}
                  <tr className="sep"><td><strong>Total disponible (simulé)</strong></td><td /><td className="num"><strong data-testid="cons-sim-total">{fmtMoney(cons.data.simulated_available, 2)}</strong></td><td /></tr>
                </tbody>
              </table>
              <h3>Comptes externes en lecture seule (observé)</h3>
              <table className="table table-sm">
                <thead><tr><th>Compte</th><th className="num">Observé</th><th className="num">En EUR</th><th>Taux appliqué</th><th>Fraîcheur</th></tr></thead>
                <tbody>
                  {cons.data.external_components.map((c: any) => (
                    <tr key={c.account_id}><td>{c.account}</td><td className="num">{fmtMoney(c.observed, 2)}</td><td className="num">{fmtMoney(c.observed_in_base, 2)}</td>
                      <td className="small">{c.rate?.pair} = {c.rate?.rate} · {c.rate?.as_of}{c.rate?.inverted ? " (inverse du taux stocké)" : ""}</td>
                      <td><Badge tone={c.freshness?.stale ? "red" : "green"}>{c.freshness?.stale ? "Périmé" : "À jour"} ({c.freshness?.age_hours} h)</Badge></td></tr>
                  ))}
                </tbody>
              </table>
              <p>Estimation consolidée incluant les comptes externes : <strong>{fmtMoney(cons.data.consolidated_estimate, 2)}</strong></p>
              {cons.data.warnings.map((w: string) => <Notice key={w} tone="warn">{w}</Notice>)}
            </div>
          )}
        </Card>
      )}
    </>
  );
}
