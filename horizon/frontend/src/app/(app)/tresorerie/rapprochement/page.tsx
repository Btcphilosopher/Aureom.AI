"use client";
import Link from "next/link";
import { useState } from "react";
import { can, useMe } from "@/components/Shell";
import { useApi } from "@/components/StepUp";
import { Badge, Card, ErrorBox, Loading, Modal, Notice, PageHeader } from "@/components/ui";
import { useFetch } from "@/lib/hooks";
import { fmtDate, fmtDateTime, fmtMoney } from "@/lib/format";

export default function Rapprochement() {
  const me = useMe();
  const { call } = useApi();
  const cases = useFetch<{ data: any[] }>("/v1/reconciliation-cases?limit=200");
  const accounts = useFetch<{ data: any[] }>("/v1/accounts?limit=200");
  const decisions = useFetch<{ data: any[] }>("/v1/decisions");
  const [acc, setAcc] = useState("");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [resolving, setResolving] = useState<any>(null);
  const [note, setNote] = useState("");
  const [action, setAction] = useState("POST_ADJUSTMENT");

  const runReco = async () => {
    setErr(null);
    try { setRes(await call("/v1/reconciliation/runs", { body: { account_id: acc } })); cases.reload(); decisions.reload(); } catch (e) { setErr(e); }
  };
  const ack = async (id: string) => {
    setErr(null);
    try { await call(`/v1/reconciliation-cases/${id}/acknowledge`, { body: { note: "Pris en compte" } }); cases.reload(); } catch (e) { setErr(e); }
  };
  const ackDecision = async (key: string) => {
    setErr(null);
    try { await call("/v1/decisions/acknowledge", { body: { key, note: "Vu" } }); decisions.reload(); } catch (e) { setErr(e); }
  };
  const resolve = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    try { await call(`/v1/reconciliation-cases/${resolving.id}/resolve`, { body: { action, note } }); setResolving(null); setNote(""); cases.reload(); decisions.reload(); } catch (e2) { setErr(e2); }
  };

  return (
    <>
      <PageHeader title="Rapprochement et centre de décisions" subtitle="Relevé du système destinataire (simulé) ↔ registre HORIZON" />
      <ErrorBox error={err} />
      <Card title="Lancer un rapprochement">
        <div className="form-grid">
          <label className="field"><span>Compte simulé</span>
            <select value={acc} onChange={(e) => setAcc(e.target.value)}><option value="">— choisir —</option>
              {(accounts.data?.data ?? []).filter((a) => a.kind === "SIMULATED").map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
          <button className="btn btn-primary" disabled={!acc || !can(me, "reconciliation.resolve")} onClick={runReco}>Rapprocher (30 derniers jours)</button>
        </div>
        {res && <Notice tone="ok">{res.statement_lines} ligne(s) de relevé, {res.matched} rapprochée(s), {res.cases_opened} écart(s) ouvert(s) — source : {res.source}</Notice>}
      </Card>
      <div style={{ height: 16 }} />
      <Card title="Cas de rapprochement">
        <Notice>« Prendre en compte » trace que vous avez vu l’écart mais <strong>ne le résout pas</strong>. Seule une action motivée (écriture de régularisation liée ou justification) clôt le cas.</Notice>
        {!cases.data ? <Loading /> : (
          <div className="table-wrap">
            <table className="table table-sm" data-testid="reco-cases">
              <thead><tr><th>Détecté</th><th>Nature</th><th>Compte</th><th>Description</th><th className="num">Relevé</th><th className="num">Registre</th><th>Responsable · échéance</th><th>État</th><th /></tr></thead>
              <tbody>
                {cases.data.data.map((c) => (
                  <tr key={c.id}>
                    <td>{fmtDateTime(c.detected_at)}</td><td>{c.kind_label}</td><td className="small">{c.account.name}</td><td className="small">{c.description}
                      {c.payment_id && <div><Link className="link" href={`/paiements/${c.payment_id}`}>Paiement</Link></div>}</td>
                    <td className="num">{c.statement_amount ? fmtMoney(c.statement_amount, 2) : "—"}</td><td className="num">{c.ledger_amount ? fmtMoney(c.ledger_amount, 2) : "—"}</td>
                    <td className="small">{c.owner ?? "—"}<br />{fmtDate(c.due_date)}</td>
                    <td><Badge tone={c.status === "RESOLVED" ? "green" : "amber"}>{c.status_label}</Badge>{c.resolution_note && <div className="small muted">{c.resolution} — {c.resolution_note}</div>}</td>
                    <td>{c.status !== "RESOLVED" && (
                      <div className="row">
                        {c.status === "OPEN" && <button className="btn btn-ghost btn-sm" onClick={() => ack(c.id)}>Prendre en compte</button>}
                        {can(me, "reconciliation.resolve") && <button className="btn btn-primary btn-sm" onClick={() => { setResolving(c); setAction(c.kind === "MISSING_IN_LEDGER" ? "POST_ADJUSTMENT" : "EXPLAINED"); }}>Résoudre</button>}
                      </div>)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {cases.data.data.length === 0 && <p className="empty">Aucun cas.</p>}
          </div>
        )}
      </Card>
      <div style={{ height: 16 }} />
      <Card title="Centre de décisions — tous les éléments" testId="all-decisions">
        <div id="decisions" />
        {!decisions.data ? <Loading /> : (
          <table className="table table-sm">
            <thead><tr><th>Élément</th><th>Source</th><th>Responsable</th><th>Échéance</th><th>État</th><th /></tr></thead>
            <tbody>
              {decisions.data.data.map((i) => (
                <tr key={i.key}>
                  <td><Badge tone={i.severity === "critical" ? "red" : "amber"}>{i.severity === "critical" ? "Critique" : i.is_alert ? "Alerte" : "Action"}</Badge> <strong>{i.title}</strong><div className="small muted">{i.subtitle}</div></td>
                  <td>{i.source.module}</td><td className="small">{i.owner}</td><td>{fmtDate(i.due_date)}</td>
                  <td className="small">{i.state}{i.acknowledgements.length > 0 && <div className="muted">Vu par {i.acknowledgements.map((a: any) => a.by).join(", ")} — non résolu</div>}</td>
                  <td><div className="row"><Link className="btn btn-outline btn-sm" href={i.action.href}>{i.action.label}</Link>
                    {can(me, "decision.acknowledge") && <button className="btn btn-ghost btn-sm" onClick={() => ackDecision(i.key)}>Accuser réception</button>}</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Modal open={!!resolving} title="Résoudre l’écart" onClose={() => setResolving(null)}>
        {resolving && (
          <form onSubmit={resolve} className="stack">
            <p className="small">{resolving.description}</p>
            <label className="field"><span>Action</span>
              <select value={action} onChange={(e) => setAction(e.target.value)}>
                {resolving.kind === "MISSING_IN_LEDGER" && <option value="POST_ADJUSTMENT">Passer une écriture de régularisation liée</option>}
                <option value="EXPLAINED">Écart expliqué (justification)</option>
              </select></label>
            <label className="field"><span>Justification (10 caractères min.)</span><textarea value={note} onChange={(e) => setNote(e.target.value)} minLength={10} required rows={3} /></label>
            <p className="small muted">Réauthentification MFA requise.</p>
            <div className="row-end"><button className="btn btn-primary">Résoudre</button></div>
          </form>
        )}
      </Modal>
    </>
  );
}
