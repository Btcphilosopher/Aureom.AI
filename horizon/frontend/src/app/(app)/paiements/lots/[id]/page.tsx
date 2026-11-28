"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { can, useMe } from "@/components/Shell";
import { useApi } from "@/components/StepUp";
import { Badge, Card, ErrorBox, KV, Loading, Modal, Notice, PageHeader, StatusChip } from "@/components/ui";
import { useFetch } from "@/lib/hooks";
import { fmtDate, fmtDateTime, fmtMoney } from "@/lib/format";

const APPROVAL_STATE: Record<string, [string, "green" | "grey" | "red" | "amber"]> = {
  VALID: ["Valide", "green"], EXPIRED: ["Expirée", "grey"], INVALIDATED: ["Invalidée", "red"], OTHER_VERSION: ["Autre version", "amber"],
};

export default function Lot() {
  const { id } = useParams<{ id: string }>();
  const me = useMe();
  const { call } = useApi();
  const { data: b, error, reload, setData } = useFetch(`/v1/payment-batches/${id}`);
  const [err, setErr] = useState<unknown>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [edit, setEdit] = useState<{ payment_id: string; amount: string } | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reason, setReason] = useState("");

  const act = async (fn: () => Promise<any>, ok: string) => {
    setErr(null);
    setMsg(null);
    try {
      const r = await fn();
      if (r?.batch) setData(r.batch); else if (r?.id) setData(r); else reload();
      setMsg(ok);
    } catch (e) { setErr(e); }
  };
  if (error) return <ErrorBox error={error} />;
  if (!b) return <Loading />;
  const isPreparer = me?.user.id === b.created_by_id;
  const pending = b.status === "PENDING_APPROVAL";
  return (
    <>
      <PageHeader title={`${b.reference} — ${b.label}`}
        subtitle={<>{b.kind_label} · {b.entity.name} · compte {b.debtor_account.name} · <StatusChip status={b.status} label={b.status_label} /></>} />
      <div className="grid grid-2">
        <Card title="Synthèse">
          <KV items={[
            ["Total", <strong key="t" data-testid="batch-total">{fmtMoney(b.total, 2)}</strong>],
            ["Paiements", b.payment_count],
            ["Version courante", <span key="v" data-testid="batch-version">v{b.version}</span>],
            ["Version approuvée", b.approved_version ? `v${b.approved_version}` : "—"],
            ["Date d’exécution", fmtDate(b.execution_date)],
            ["Approbations", <span key="a" data-testid="approval-count">{b.required_approvals ? `${b.valid_approvals}/${b.required_approvals}` : "—"}</span>],
            ["Préparé par", `${b.created_by} — ${fmtDateTime(b.created_at)}`],
            ["Statut", <span key="s" data-testid="batch-status">{b.status_label}</span>],
          ]} />
          {b.status_reason && <Notice tone="warn">{b.status_reason}</Notice>}
          {b.validation_issues?.map((i: any, k: number) => <Notice key={k} tone={i.blocking ? "warn" : "info"}>{i.blocking ? "Bloquant" : "Information"} — {i.message}</Notice>)}
        </Card>
        <Card title="Actions">
          <div className="stack">
            {msg && <Notice tone="ok">{msg}</Notice>}
            <ErrorBox error={err} />
            {(b.status === "DRAFT" || b.status === "TO_REVIEW") && can(me, "payment.prepare") && (
              <button className="btn btn-primary" data-testid="submit-approval"
                onClick={() => act(() => call(`/v1/payment-batches/${id}/submit-for-approval`, { body: { expected_version: b.version } }), "Lot soumis")}>
                Soumettre pour approbation (v{b.version})</button>
            )}
            {pending && (
              <>
                <p className="small">Vous approuvez précisément la <strong>version {b.version}</strong> du lot ({fmtMoney(b.total, 2)}). Une réauthentification MFA est exigée ; le préparateur ne peut pas approuver.</p>
                <label className="field"><span>Commentaire (facultatif)</span><input value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} /></label>
                <div className="row">
                  <button className="btn btn-primary" data-testid="approve"
                    onClick={() => act(() => call(`/v1/payment-batches/${id}/approvals`, { body: { decision: "APPROVE", version: b.version, comment: comment || undefined } }), "Approbation enregistrée")}>
                    Approuver la version {b.version}</button>
                  <button className="btn btn-danger" data-testid="reject"
                    onClick={() => act(() => call(`/v1/payment-batches/${id}/approvals`, { body: { decision: "REJECT", version: b.version, comment: comment || "Refusé" } }), "Lot refusé")}>
                    Refuser</button>
                </div>
                {isPreparer && <Notice tone="warn">Vous avez préparé ce lot : la séparation des tâches vous interdit de l’approuver.</Notice>}
              </>
            )}
            {["DRAFT", "TO_REVIEW", "PENDING_APPROVAL", "APPROVED", "SCHEDULED"].includes(b.status) && can(me, "payment.cancel") && (
              <button className="btn btn-ghost" onClick={() => setCancelOpen(true)} data-testid="cancel">Annuler le lot</button>
            )}
            {["APPROVED", "SCHEDULED", "PROCESSING"].includes(b.status) && (
              <Notice>Exécution prise en charge par le travailleur en arrière-plan. En démonstration sans travailleur : Administration › Démonstration › « Traiter la file ».</Notice>
            )}
            {b.eligible_approvers && (
              <div><h4 style={{ margin: "8px 0 4px" }}>Approbateurs éligibles</h4>
                <ul className="small">{b.eligible_approvers.map((e: any) => <li key={e.user_id}>{e.name} — via {e.via === "MANDATE" ? "mandat" : "délégation"}, plafond {fmtMoney(e.limit)}</li>)}</ul></div>
            )}
          </div>
        </Card>
      </div>
      <div style={{ height: 16 }} />
      <Card title="Paiements du lot">
        <div className="table-wrap">
          <table className="table table-sm" data-testid="batch-payments">
            <thead><tr><th>#</th><th>Bénéficiaire (version figée)</th><th>IBAN</th><th className="num">Montant</th><th>Motif</th><th>Statut</th><th /></tr></thead>
            <tbody>
              {b.payments.map((p: any) => (
                <tr key={p.id}>
                  <td>{p.line_no}</td>
                  <td>{p.beneficiary.name} <Badge tone={p.beneficiary.pinned_is_current_approved ? "green" : "amber"}>v{p.beneficiary.pinned_version_no}{p.beneficiary.pinned_is_current_approved ? " approuvée" : " — à revoir"}</Badge></td>
                  <td className="mono small">{p.beneficiary.iban}</td>
                  <td className="num">{fmtMoney(p.amount, 2)}</td>
                  <td className="small">{p.remittance_info}</td>
                  <td><Link href={`/paiements/${p.id}`}><StatusChip status={p.status} label={p.status_label} /></Link>{p.rejection_code && <div className="small muted">{p.rejection_code} — {p.rejection_label}</div>}</td>
                  <td>{["DRAFT", "TO_REVIEW", "PENDING_APPROVAL", "APPROVED", "SCHEDULED"].includes(p.status) && can(me, "payment.prepare") && (
                    <button className="btn btn-ghost btn-sm" onClick={() => setEdit({ payment_id: p.id, amount: p.amount.amount })}>Modifier</button>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <div style={{ height: 16 }} />
      <div className="grid grid-2">
        <Card title="Approbations">
          {b.approvals.length === 0 ? <p className="empty">Aucune décision enregistrée.</p> : (
            <table className="table table-sm" data-testid="approvals">
              <thead><tr><th>Approbateur</th><th>Décision</th><th>Version</th><th>Le</th><th>Expire</th><th>État</th></tr></thead>
              <tbody>
                {b.approvals.map((a: any) => (
                  <tr key={a.id}><td>{a.approver}<div className="small muted">{a.via === "DELEGATION" ? "par délégation" : "mandat"}</div></td>
                    <td>{a.decision === "APPROVE" ? "Approuve" : "Refuse"}</td><td>v{a.batch_version}</td><td>{fmtDateTime(a.created_at)}</td><td>{fmtDateTime(a.expires_at)}</td>
                    <td><Badge tone={APPROVAL_STATE[a.state][1]}>{APPROVAL_STATE[a.state][0]}</Badge>{a.invalidation_reason && <div className="small muted">{a.invalidation_reason}</div>}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card title="Historique du lot">
          <ul className="timeline">
            {b.events.map((e: any, i: number) => (
              <li key={i} className={["REJECTED", "CANCELLED"].includes(e.to) ? "t-red" : e.to === "TO_REVIEW" ? "t-amber" : ""}>
                <div className="t-title">{e.to_label}</div>
                <div className="t-meta">{fmtDateTime(e.at)} · {e.actor ?? e.source} · v{e.batch_version}{e.reason ? ` — ${e.reason}` : ""}</div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <Modal open={!!edit} title="Modifier le montant" onClose={() => setEdit(null)}>
        {edit && (
          <form onSubmit={(e) => { e.preventDefault(); void act(() => call(`/v1/payment-batches/${id}`, { method: "PATCH", body: { expected_version: b.version, update_payments: [{ payment_id: edit.payment_id, amount: edit.amount }] } }), "Lot modifié : nouvelle version, approbations antérieures invalidées, retour en brouillon").then(() => setEdit(null)); }}>
            <Notice tone="warn">Modification matérielle : la version du lot passera de v{b.version} à v{b.version + 1}, les approbations existantes seront invalidées et les fonds réservés libérés.</Notice>
            <label className="field"><span>Nouveau montant</span><input value={edit.amount} onChange={(e) => setEdit({ ...edit, amount: e.target.value })} pattern="\d{1,13}(\.\d{1,2})?" required /></label>
            <div className="row-end"><button className="btn btn-primary">Enregistrer</button></div>
          </form>
        )}
      </Modal>
      <Modal open={cancelOpen} title="Annuler le lot" onClose={() => setCancelOpen(false)}>
        <form onSubmit={(e) => { e.preventDefault(); void act(() => call(`/v1/payment-batches/${id}/cancel`, { body: { reason } }), "Lot annulé").then(() => setCancelOpen(false)); }}>
          <label className="field"><span>Motif (obligatoire)</span><input value={reason} onChange={(e) => setReason(e.target.value)} minLength={5} required /></label>
          <div className="row-end"><button className="btn btn-danger">Confirmer l’annulation</button></div>
        </form>
      </Modal>
    </>
  );
}
