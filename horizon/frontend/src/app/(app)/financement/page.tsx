"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { can, useMe } from "@/components/Shell";
import { useApi } from "@/components/StepUp";
import { Badge, Card, ErrorBox, KV, Loading, Notice, PageHeader, StatusChip } from "@/components/ui";
import { useFetch } from "@/lib/hooks";
import { useQueryParam } from "@/lib/query";
import { fmtDate, fmtMoney } from "@/lib/format";

export default function Financement() {
  const me = useMe();
  const { call } = useApi();
  const focus = useQueryParam("echeance");
  const facilities = useFetch<{ data: any[] }>("/v1/financing/facilities");
  const insts = useFetch<{ data: any[] }>("/v1/financing/installments?limit=200");
  const requests = useFetch<{ data: any[] }>("/v1/financing/requests");
  const [sim, setSim] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [msg, setMsg] = useState<React.ReactNode>(null);
  useEffect(() => { if (focus) document.getElementById(`inst-${focus}`)?.scrollIntoView({ block: "center" }); }, [focus, insts.data]);

  const prepare = async (id: string) => {
    setErr(null);
    try {
      const r = await call<any>(`/v1/financing/installments/${id}/prepare`, { method: "POST" });
      setMsg(<>Paiement préparé : <Link className="link" href={`/paiements/lots/${r.batch_id}`}>{r.batch_reference}</Link> (à soumettre pour approbation — circuit normal).</>);
      insts.reload();
    } catch (e) { setErr(e); }
  };
  const simulate = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErr(null);
    const f = new FormData(e.currentTarget);
    try { setSim(await call("/v1/financing/simulations", { body: { amount: f.get("amount"), months: Number(f.get("months")), annual_rate_pct: Number(f.get("rate")), currency: "EUR" } })); } catch (e2) { setErr(e2); }
  };
  const request = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErr(null);
    const f = Object.fromEntries(new FormData(e.currentTarget).entries());
    try { await call("/v1/financing/requests", { body: { ...f, simulation_id: sim?.id } }); requests.reload(); setMsg("Demande transmise pour revue humaine — aucun octroi automatique."); } catch (e2) { setErr(e2); }
  };

  return (
    <>
      <PageHeader title="Financement" subtitle="Contrats acceptés, utilisations, échéances — distincts des simulations et des demandes" />
      {msg && <Notice tone="ok">{msg}</Notice>}
      <ErrorBox error={err} />
      <div className="stack">
        <Card title="Contrats (fictifs)">
          {!facilities.data ? <Loading /> : (
            <div className="grid grid-2">
              {facilities.data.data.map((f) => (
                <div key={f.id} className="card" style={{ boxShadow: "none" }}>
                  <h3 style={{ marginTop: 0 }}>{f.label} <Badge tone="navy">{f.kind_label}</Badge></h3>
                  <KV items={[["Référence", f.reference], ["Prêteur", f.lender], ["Engagé", fmtMoney(f.committed, 0)], ["Utilisé", fmtMoney(f.drawn, 0)],
                    ["Disponible", fmtMoney(f.undrawn, 0)], ["Échéance finale", fmtDate(f.maturity_date)], ["Taux", f.rate_description], ["Statut", f.status_label]]} />
                  {f.document_ids?.length > 0 && <p className="small"><Link className="link" href="/documents">Contrat archivé dans Documents</Link></p>}
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card title="Échéancier">
          {!insts.data ? <Loading /> : (
            <table className="table table-sm" data-testid="installments">
              <thead><tr><th>Échéance</th><th>Contrat</th><th className="num">Principal</th><th className="num">Intérêts</th><th className="num">Total</th><th>Responsable</th><th>État</th><th /></tr></thead>
              <tbody>
                {insts.data.data.map((i) => (
                  <tr key={i.id} id={`inst-${i.id}`} style={focus === i.id ? { background: "#fff8e6" } : undefined}>
                    <td>{fmtDate(i.due_date)}<div className="small muted">J{i.days_until_due >= 0 ? "-" : "+"}{Math.abs(i.days_until_due)}</div></td>
                    <td>{i.facility} <span className="small muted">({i.facility_reference})</span></td>
                    <td className="num">{fmtMoney(i.principal, 0)}</td><td className="num">{fmtMoney(i.interest, 0)}</td><td className="num"><strong>{fmtMoney(i.total, 0)}</strong></td>
                    <td>{i.owner ?? "—"}</td><td><StatusChip status={i.status} label={i.status_label} /></td>
                    <td>{i.status === "TO_PREPARE" && can(me, "financing.prepare") && <button className="btn btn-outline btn-sm" onClick={() => prepare(i.id)}>Préparer le paiement</button>}
                      {i.payment_batch_id && <Link className="link small" href={`/paiements/lots/${i.payment_batch_id}`}>Voir le lot</Link>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <div className="grid grid-2">
          <Card title="Simulation (indicative)">
            <form onSubmit={simulate} className="stack">
              <div className="form-grid">
                <label className="field"><span>Montant (EUR)</span><input name="amount" required defaultValue="2000000.00" pattern="\d{1,13}(\.\d{1,2})?" /></label>
                <label className="field"><span>Durée (mois)</span><input name="months" type="number" min={1} max={360} defaultValue={36} /></label>
                <label className="field"><span>Taux annuel (%)</span><input name="rate" type="number" step="0.01" min={0} max={30} defaultValue={4.2} /></label>
              </div>
              <div className="row-end"><button className="btn btn-ghost">Simuler</button></div>
            </form>
            {sim && (
              <div className="stack">
                <KV items={[["Mensualité", `${Number(sim.result.monthly_payment).toLocaleString("fr-FR")} €`], ["Intérêts totaux", `${Number(sim.result.total_interest).toLocaleString("fr-FR")} €`]]} />
                <Notice tone="warn">{sim.result.disclaimer}</Notice>
              </div>
            )}
          </Card>
          <Card title="Demande de financement">
            <Notice>Une demande est transmise pour <strong>revue humaine</strong>. Aucun octroi n’est automatique ; aucune décision de crédit n’est rendue par HORIZON.</Notice>
            {can(me, "financing.prepare") ? (
              <form onSubmit={request} className="stack">
                <div className="form-grid">
                  <label className="field"><span>Entité</span><select name="entity_id">{me?.entities.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label>
                  <label className="field"><span>Nature</span><select name="kind"><option value="TERM_LOAN">Prêt amortissable</option><option value="RCF">Crédit renouvelable</option><option value="SHORT_TERM">Court terme</option></select></label>
                  <label className="field"><span>Montant</span><input name="amount" required pattern="\d{1,13}(\.\d{1,2})?" defaultValue={sim?.params?.amount ?? ""} /></label>
                </div>
                <label className="field"><span>Objet</span><textarea name="purpose" required minLength={10} rows={2} /></label>
                <div className="row-end"><button className="btn btn-primary">Transmettre pour revue</button></div>
              </form>
            ) : <p className="muted small">Réservé au rôle Préparation.</p>}
            {requests.data && requests.data.data.length > 0 && (
              <table className="table table-sm"><thead><tr><th>Nature</th><th className="num">Montant</th><th>Statut</th></tr></thead>
                <tbody>{requests.data.data.map((r) => <tr key={r.id}><td>{r.kind}</td><td className="num">{fmtMoney(r.amount, 0)}</td><td className="small">{r.status_label}</td></tr>)}</tbody></table>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
