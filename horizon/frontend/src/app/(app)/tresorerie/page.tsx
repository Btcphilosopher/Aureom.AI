"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { can, useMe } from "@/components/Shell";
import { useApi } from "@/components/StepUp";
import { Badge, Card, ErrorBox, Loading, Notice, PageHeader, Tabs } from "@/components/ui";
import { useFetch } from "@/lib/hooks";
import { fmtDate, fmtDateTime, fmtMoney } from "@/lib/format";

const SRC: Record<string, string> = { payment: "Paiement", expected_receipt: "Encaissement attendu", financing_installment: "Échéance de financement", recurring_assumption: "Hypothèse récurrente" };

export default function Tresorerie() {
  const me = useMe();
  const { call } = useApi();
  const [tab, setTab] = useState("forecast");
  const sc = useFetch<{ data: any[] }>("/v1/cashflow-scenarios");
  const [scenario, setScenario] = useState("");
  const [horizon, setHorizon] = useState(30);
  const [run, setRun] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const receipts = useFetch<{ data: any[] }>(tab === "receipts" ? "/v1/expected-receipts?limit=200" : null);
  const recurring = useFetch<{ data: any[] }>(tab === "recurring" ? "/v1/recurring-assumptions" : null);
  useEffect(() => { if (sc.data && !scenario) setScenario(sc.data.data.find((s) => s.is_baseline)?.id ?? sc.data.data[0]?.id ?? ""); }, [sc.data, scenario]);

  const compute = async () => {
    setErr(null);
    try { setRun(await call("/v1/forecasts", { body: { scenario_id: scenario, horizon_days: horizon } })); } catch (e) { setErr(e); }
  };
  const createScenario = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErr(null);
    const f = new FormData(e.currentTarget);
    try {
      await call("/v1/cashflow-scenarios", { body: {
        code: String(f.get("code")).toUpperCase(), name: f.get("name"), description: f.get("description"),
        receipts_haircut_pct: Number(f.get("haircut")), receipts_delay_days: Number(f.get("delay")), disbursements_uplift_pct: Number(f.get("uplift")),
        include_pending_approval: f.get("pending") === "on", include_low_confidence: f.get("low") === "on",
      } });
      sc.reload();
      (e.target as HTMLFormElement).reset();
    } catch (e2) { setErr(e2); }
  };

  return (
    <>
      <PageHeader title="Trésorerie" subtitle="Prévisions déterministes et explicables — horizons 7, 30 et 90 jours"
        actions={<Link href="/tresorerie/rapprochement" className="btn btn-outline">Rapprochement</Link>} />
      <Tabs tabs={[{ id: "forecast", label: "Prévision" }, { id: "scenarios", label: "Scénarios" }, { id: "receipts", label: "Encaissements attendus" }, { id: "recurring", label: "Hypothèses récurrentes" }]} value={tab} onChange={setTab} />
      <ErrorBox error={err} />
      {tab === "forecast" && (
        <div className="stack">
          <Card title="Calculer une prévision">
            <div className="form-grid">
              <label className="field"><span>Scénario</span>
                <select value={scenario} onChange={(e) => setScenario(e.target.value)} data-testid="scenario">{sc.data?.data.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
              <label className="field"><span>Horizon</span>
                <select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>{[7, 30, 90].map((h) => <option key={h} value={h}>{h} jours</option>)}</select></label>
              <button className="btn btn-primary" onClick={compute} data-testid="run-forecast">Calculer et figer</button>
            </div>
          </Card>
          {run && (
            <>
              <Card title={`Prévision ${run.scenario.name} — ${run.horizon_days} jours (arrêté au ${fmtDate(run.as_of)})`}>
                <p className="small muted">Identifiant {run.id} · méthode {run.method} · calculée le {fmtDateTime(run.created_at)}</p>
                <div className="grid grid-3">
                  <div><div className="muted small">Point de départ (solde comptabilisé)</div><strong>{fmtMoney(run.inputs.starting_balance, 0)}</strong></div>
                  <div><div className="muted small">Solde de fin d’horizon</div><strong data-testid="forecast-ending">{fmtMoney(run.series[run.series.length - 1].closing, 0)}</strong></div>
                  <div><div className="muted small">Taux utilisés</div><span className="small">{run.inputs.rates.map((r: any) => `${r.pair} ${r.rate} (${r.as_of})`).join(" · ") || "—"}</span></div>
                </div>
                <h4>Flux pris en compte ({run.lines.length})</h4>
                <div className="table-wrap">
                  <table className="table table-sm" data-testid="forecast-lines">
                    <thead><tr><th>Date</th><th>Libellé</th><th>Source</th><th>Compte</th><th className="num">Montant (EUR)</th><th>Note</th></tr></thead>
                    <tbody>
                      {run.lines.map((l: any, i: number) => (
                        <tr key={i}><td>{fmtDate(l.date)}{l.overdue && <div><Badge tone="amber">échu au {fmtDate(l.original_date)}</Badge></div>}</td>
                          <td>{l.label}</td><td><Badge>{SRC[l.source_type] ?? l.source_type}</Badge></td><td className="small">{l.account}</td>
                          <td className={`num ${l.amount_minor > 0 ? "strong-green" : ""}`}>{fmtMoney(l.amount, 0)}</td><td className="small muted">{l.note ?? ""}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <h4>Éléments exclus (anti double comptage)</h4>
                <ul className="small" data-testid="forecast-excluded">{run.excluded.map((x: any, i: number) => <li key={i}><strong>{x.label ?? x.source_type}</strong> — {x.reason}{x.count ? ` (${x.count})` : ""}</li>)}</ul>
              </Card>
              <Card title="Méthode"><pre>{run.method_description ?? "Voir la documentation : prévision déterministe, point de départ = solde comptabilisé, fourchette = enveloppe des scénarios."}</pre></Card>
            </>
          )}
        </div>
      )}
      {tab === "scenarios" && (
        <div className="stack">
          <Card title="Scénarios">
            {!sc.data ? <Loading /> : (
              <table className="table table-sm"><thead><tr><th>Code</th><th>Nom</th><th>Décote encaissements</th><th>Retard</th><th>Majoration décaissements</th><th>En attente d’approbation</th><th>Confiance faible</th></tr></thead>
                <tbody>{sc.data.data.map((s) => (<tr key={s.id}><td className="mono">{s.code}</td><td><strong>{s.name}</strong><div className="small muted">{s.description}</div></td>
                  <td>{s.receipts_haircut_pct} %</td><td>{s.receipts_delay_days} j</td><td>{s.disbursements_uplift_pct} %</td><td>{s.include_pending_approval ? "Inclus" : "Exclus"}</td><td>{s.include_low_confidence ? "Inclus" : "Exclus"}</td></tr>))}</tbody></table>
            )}
            <Notice>La fourchette du tableau de bord est l’enveloppe quotidienne des scénarios Prudent, Central et Favorable — ce n’est pas un intervalle statistique.</Notice>
          </Card>
          {can(me, "forecast.write") && (
            <Card title="Nouveau scénario">
              <form onSubmit={createScenario} className="stack">
                <div className="form-grid">
                  <label className="field"><span>Code</span><input name="code" required pattern="[A-Za-z0-9_]{2,30}" /></label>
                  <label className="field"><span>Nom</span><input name="name" required /></label>
                  <label className="field"><span>Décote encaissements (%)</span><input name="haircut" type="number" min={0} max={100} defaultValue={0} /></label>
                  <label className="field"><span>Retard encaissements (jours)</span><input name="delay" type="number" min={0} max={90} defaultValue={0} /></label>
                  <label className="field"><span>Majoration décaissements récurrents (%)</span><input name="uplift" type="number" min={0} max={100} defaultValue={0} /></label>
                </div>
                <label className="field"><span>Description</span><input name="description" /></label>
                <div className="row"><label className="check"><input type="checkbox" name="pending" defaultChecked /> Inclure les paiements en attente d’approbation</label>
                  <label className="check"><input type="checkbox" name="low" /> Inclure les encaissements à confiance faible</label></div>
                <div className="row-end"><button className="btn btn-primary">Créer</button></div>
              </form>
            </Card>
          )}
        </div>
      )}
      {tab === "receipts" && (
        <Card title="Encaissements attendus">
          {!receipts.data ? <Loading /> : (
            <table className="table table-sm"><thead><tr><th>Date attendue</th><th>Contrepartie</th><th>Référence</th><th>Compte</th><th>Confiance</th><th className="num">Montant</th><th>État</th></tr></thead>
              <tbody>{receipts.data.data.map((r) => (<tr key={r.id}><td>{fmtDate(r.expected_date)}</td><td>{r.counterparty}</td><td className="mono">{r.reference}</td><td className="small">{r.account}</td>
                <td>{r.confidence}</td><td className="num">{fmtMoney(r.amount, 0)}</td><td><Badge tone={r.status === "RECEIVED" ? "green" : "amber"}>{r.status === "RECEIVED" ? "Reçu (rapproché)" : "Attendu"}</Badge></td></tr>))}</tbody></table>
          )}
        </Card>
      )}
      {tab === "recurring" && (
        <Card title="Hypothèses récurrentes">
          {!recurring.data ? <Loading /> : (
            <table className="table table-sm"><thead><tr><th>Libellé</th><th>Catégorie</th><th>Sens</th><th>Jour du mois</th><th>Compte</th><th className="num">Montant</th></tr></thead>
              <tbody>{recurring.data.data.map((a) => (<tr key={a.id}><td>{a.label}</td><td>{a.category}</td><td>{a.direction === "IN" ? "Encaissement" : "Décaissement"}</td><td>{a.day_of_month}</td><td className="small">{a.account}</td><td className="num">{fmtMoney(a.amount, 0)}</td></tr>))}</tbody></table>
          )}
          <Notice>Une occurrence réalisée par un paiement (référence de prévision) ou déjà comptabilisée sort automatiquement de la prévision.</Notice>
        </Card>
      )}
    </>
  );
}
