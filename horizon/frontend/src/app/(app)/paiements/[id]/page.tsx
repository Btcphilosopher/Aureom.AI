"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { can, useMe } from "@/components/Shell";
import { useApi } from "@/components/StepUp";
import { Card, ErrorBox, KV, Loading, Notice, PageHeader, StatusChip } from "@/components/ui";
import { useFetch } from "@/lib/hooks";
import { fmtDate, fmtDateTime, fmtMoney } from "@/lib/format";

export default function Paiement() {
  const { id } = useParams<{ id: string }>();
  const me = useMe();
  const { call } = useApi();
  const { data: p, error, setData } = useFetch(`/v1/payments/${id}`);
  const [text, setText] = useState("");
  const [err, setErr] = useState<unknown>(null);
  if (error) return <ErrorBox error={error} />;
  if (!p) return <Loading />;
  const failed = p.status === "REJECTED";
  const steps: [string, string | null][] = [
    ["Soumis", p.submitted_at], ["Réception technique", p.technical_ack_at], ["Accepté par le destinataire", p.accepted_at],
    [failed ? "Rejeté" : "Exécuté selon confirmation", failed ? p.rejected_at : p.executed_at],
  ];
  return (
    <>
      <PageHeader title={`Paiement ${p.end_to_end_id}`} subtitle={<><Link className="link" href={`/paiements/lots/${p.batch_id}`}>{p.batch_reference}</Link> · {p.batch_label} · ligne {p.line_no} · <StatusChip status={p.status} label={p.status_label} /></>} />
      <div className="steps" data-testid="payment-steps">
        {steps.map(([l, at], i) => (
          <span key={i} className={`step ${at ? (failed && i === 3 ? "fail" : "done") : ""}`}>{l}{at ? ` · ${fmtDateTime(at).slice(11)}` : ""}</span>
        ))}
      </div>
      <Notice>{p.settlement_note}</Notice>
      <div className="grid grid-2">
        <Card title="Détail">
          <KV items={[
            ["Montant", fmtMoney(p.amount, 2)], ["Date d’exécution", fmtDate(p.execution_date)],
            ["Bénéficiaire", <span key="b">{p.beneficiary.name} — version figée v{p.beneficiary.pinned_version_no}</span>],
            ["IBAN (synthétique)", <span key="i" className="mono">{p.beneficiary.iban}</span>],
            ["Motif", p.remittance_info || "—"], ["Clé d’idempotence", <span key="k" className="mono small">{p.submission_key}</span>],
            ["Tentatives de soumission", p.submission_attempts], ["Référence destinataire", p.bank_reference ?? "—"],
            ["Écriture comptable", p.ledger_entry_id ? <span key="l" className="mono small">{p.ledger_entry_id.slice(0, 8)}…</span> : "—"],
            ["Résultat inconnu depuis", p.unknown_since ? fmtDateTime(p.unknown_since) : "—"],
            ["Préparé par", p.created_by], ["Retour de fonds", p.returned ? fmtMoney(p.returned, 2) : "—"],
          ]} />
        </Card>
        <Card title="Historique des statuts">
          <ul className="timeline" data-testid="payment-timeline">
            {p.events.map((e: any, i: number) => (
              <li key={i} className={e.to === "REJECTED" || e.to === "UNKNOWN" ? "t-red" : ""}>
                <div className="t-title">{e.to_label}</div>
                <div className="t-meta">{fmtDateTime(e.at)} · {e.actor ?? e.source}{e.reason ? ` — ${e.reason}` : ""}</div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      {failed && (
        <Card title="Traitement du rejet" className="mt">
          <p><strong>{p.rejection_code}</strong> — {p.rejection_label}. La réservation de fonds a été libérée ; aucun débit n’a eu lieu.</p>
          {p.rejection_resolution ? (
            <Notice tone="ok">Traité par {p.rejection_resolved_by} : {p.rejection_resolution}</Notice>
          ) : can(me, "payment.prepare") ? (
            <form onSubmit={async (e) => { e.preventDefault(); setErr(null); try { setData(await call(`/v1/payments/${id}/rejection-resolution`, { body: { resolution: text } })); } catch (e2) { setErr(e2); } }}>
              <Notice tone="warn">Un accusé de réception ne suffit pas : décrivez le traitement de la cause (coordonnées corrigées, paiement de remplacement, abandon motivé…).</Notice>
              <label className="field"><span>Justification</span><textarea value={text} onChange={(e) => setText(e.target.value)} minLength={10} required rows={3} /></label>
              <ErrorBox error={err} />
              <div className="row-end"><button className="btn btn-primary">Clore le traitement du rejet</button></div>
            </form>
          ) : <p className="muted">Traitement en attente du préparateur.</p>}
        </Card>
      )}
      {p.returns?.length > 0 && (
        <Card title="Retours de fonds">
          <table className="table table-sm"><thead><tr><th>Date</th><th className="num">Montant</th><th>Motif</th></tr></thead>
            <tbody>{p.returns.map((r: any, i: number) => <tr key={i}><td>{fmtDateTime(r.at)}</td><td className="num">{fmtMoney(r.amount, 2)}</td><td>{r.reason_code}</td></tr>)}</tbody></table>
        </Card>
      )}
    </>
  );
}
