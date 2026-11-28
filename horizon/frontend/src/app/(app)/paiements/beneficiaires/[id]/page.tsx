"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { can, useMe } from "@/components/Shell";
import { useApi } from "@/components/StepUp";
import { Badge, Card, ErrorBox, KV, Loading, Notice, PageHeader, StatusChip } from "@/components/ui";
import { useFetch } from "@/lib/hooks";
import { fmtDateTime } from "@/lib/format";

const REVIEW: Record<string, string> = { PENDING: "En revue", APPROVED: "Approuvée", REJECTED: "Rejetée", INHERITED: "Héritée (modification mineure)" };

export default function Beneficiaire() {
  const { id } = useParams<{ id: string }>();
  const me = useMe();
  const { call } = useApi();
  const { data: b, error, setData } = useFetch(`/v1/beneficiaries/${id}`);
  const [err, setErr] = useState<unknown>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const run = async (path: string, body: unknown, method = "POST", ok = "Enregistré") => {
    setErr(null); setMsg(null);
    try { setData(await call(path, { method, body })); setMsg(ok); } catch (e) { setErr(e); }
  };
  if (error) return <ErrorBox error={error} />;
  if (!b) return <Loading />;
  const v = b.current_version;
  const ver = v.verification;
  return (
    <>
      <PageHeader title={v.name} subtitle={<>{b.entity.name} · <StatusChip status={b.status} label={b.status_label} /> · version courante v{v.version_no}</>} />
      {msg && <Notice tone="ok">{msg}</Notice>}
      <ErrorBox error={err} />
      <div className="grid grid-2">
        <Card title="Coordonnées (version courante)">
          <KV items={[["Nom", v.name], ["IBAN", <span key="i" className="mono">{v.iban}</span>], ["BIC", v.bic || "—"], ["Pays", v.country_code],
            ["Adresse", v.address || "—"], ["Catégorie", v.category], ["Revue", REVIEW[v.review_status]], ["Créée par", `${v.created_by} — ${fmtDateTime(v.created_at)}`]]} />
          {b.suspended_reason && <Notice tone="warn">Suspendu : {b.suspended_reason}</Notice>}
        </Card>
        <Card title="Vérification">
          <KV items={[
            ["Format IBAN", ver?.iban_format?.format_valid ? "Valide (ISO 13616, modulo 97)" : `Invalide : ${ver?.iban_format?.issues?.join(", ")}`],
            ["Format BIC", ver?.bic_format_valid ? "Valide" : "Non valide ou absent"],
            ["Existence du compte", "Non vérifiée"], ["Identité du titulaire", ver?.name_match?.status === "NOT_PERFORMED" ? "Non vérifiée" : ver?.name_match?.status],
          ]} />
          <Notice tone="warn">La validation du format d’un IBAN ne prouve ni l’existence du compte ni l’identité de son titulaire. {ver?.name_match?.note}</Notice>
        </Card>
      </div>
      <div style={{ height: 16 }} />
      <div className="grid grid-2">
        <Card title="Actions">
          <div className="stack">
            {b.pending_review && can(me, "beneficiary.approve") && (
              <div className="row">
                <button className="btn btn-primary" data-testid="bene-approve" onClick={() => run(`/v1/beneficiaries/${id}/review`, { decision: "APPROVE", comment: "Contrôle effectué" }, "POST", "Version validée")}>Valider la version v{v.version_no}</button>
                <button className="btn btn-danger" onClick={() => run(`/v1/beneficiaries/${id}/review`, { decision: "REJECT", comment: "Coordonnées non confirmées" }, "POST", "Version rejetée")}>Rejeter</button>
              </div>
            )}
            {b.pending_review && !can(me, "beneficiary.approve") && <Notice>Revue en attente d’un approbateur (distinct de l’auteur de la modification).</Notice>}
            {can(me, "beneficiary.approve") && (
              <form className="row" onSubmit={(e) => { e.preventDefault(); void run(`/v1/beneficiaries/${id}/suspension`, { suspend: b.status !== "SUSPENDED", reason }, "POST", b.status === "SUSPENDED" ? "Réactivé" : "Suspendu"); }}>
                <label className="field" style={{ flex: 1 }}><span>Motif</span><input value={reason} onChange={(e) => setReason(e.target.value)} minLength={5} required /></label>
                <button className="btn btn-ghost">{b.status === "SUSPENDED" ? "Réactiver" : "Suspendre"}</button>
              </form>
            )}
            {can(me, "beneficiary.write") && (
              <form onSubmit={(e) => { e.preventDefault(); const f = Object.fromEntries(Array.from(new FormData(e.currentTarget).entries()).filter(([, x]) => x !== "")); void run(`/v1/beneficiaries/${id}`, f, "PATCH", "Nouvelle version créée"); }}>
                <h4 style={{ margin: "6px 0" }}>Modifier (crée une nouvelle version)</h4>
                <div className="form-grid">
                  <label className="field"><span>Nom</span><input name="name" placeholder={v.name} /></label>
                  <label className="field"><span>IBAN</span><input name="iban" placeholder={v.iban} /></label>
                  <label className="field"><span>BIC</span><input name="bic" placeholder={v.bic} /></label>
                  <label className="field"><span>Adresse (mineure)</span><input name="address" placeholder={v.address} /></label>
                  <label className="field"><span>Courriel (mineure)</span><input name="email" placeholder={v.email} /></label>
                </div>
                <p className="small muted">Nom, IBAN, BIC ou pays : modification matérielle → nouvelle revue et invalidation des approbations des lots concernés. Adresse, courriel, catégorie : version mineure qui hérite de l’approbation.</p>
                <div className="row-end"><button className="btn btn-primary">Enregistrer</button></div>
              </form>
            )}
          </div>
        </Card>
        <Card title="Historique des versions">
          <table className="table table-sm" data-testid="bene-versions">
            <thead><tr><th>Version</th><th>Nature</th><th>Champs modifiés</th><th>IBAN</th><th>Revue</th></tr></thead>
            <tbody>
              {b.versions.map((x: any) => (
                <tr key={x.id}><td>v{x.version_no}<div className="small muted">{x.created_by} · {fmtDateTime(x.created_at)}</div></td>
                  <td><Badge tone={x.change_kind === "MATERIAL" ? "amber" : "grey"}>{x.change_kind === "MATERIAL" ? "Matérielle" : x.change_kind === "MINOR" ? "Mineure" : "Création"}</Badge></td>
                  <td className="small">{x.changed_fields.join(", ")}</td><td className="mono small">{x.iban}</td>
                  <td>{REVIEW[x.review_status]}{x.reviewed_by && <div className="small muted">{x.reviewed_by} · {fmtDateTime(x.reviewed_at)}</div>}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </>
  );
}
