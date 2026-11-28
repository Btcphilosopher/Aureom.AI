"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { can, useMe } from "@/components/Shell";
import { useApi } from "@/components/StepUp";
import { Card, ErrorBox, Loading, Notice, PageHeader, StatusChip } from "@/components/ui";
import { useFetch } from "@/lib/hooks";
import { fmtDate, fmtMoney } from "@/lib/format";

export default function Commerce() {
  const me = useMe();
  const router = useRouter();
  const { call } = useApi();
  const files = useFetch<{ data: any[]; disclaimer: string }>("/v1/trade-files");
  const [err, setErr] = useState<unknown>(null);
  const create = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErr(null);
    const f = Object.fromEntries(Array.from(new FormData(e.currentTarget).entries()).filter(([, v]) => v !== ""));
    try { const r = await call<any>("/v1/trade-files", { body: f }); router.push(`/commerce-international/${r.id}`); } catch (e2) { setErr(e2); }
  };
  return (
    <>
      <PageHeader title="Commerce international" subtitle="Dossiers documentaires : parties, documents, échéances, demandes, tâches et décisions" />
      {files.data && <Notice tone="warn">{files.data.disclaimer}</Notice>}
      <Card title="Dossiers">
        {files.error && <ErrorBox error={files.error} />}
        {!files.data ? <Loading /> : (
          <table className="table" data-testid="trade-files">
            <thead><tr><th>Référence</th><th>Objet</th><th>Sens</th><th>Instrument envisagé</th><th className="num">Montant</th><th>Responsable</th><th>État</th></tr></thead>
            <tbody>{files.data.data.map((f) => (
              <tr key={f.id}><td><Link className="link mono" href={`/commerce-international/${f.id}`}>{f.reference}</Link></td><td>{f.title}</td>
                <td>{f.direction === "IMPORT" ? "Import" : "Export"}</td><td className="small">{f.instrument_considered || "—"}</td>
                <td className="num">{f.amount ? fmtMoney(f.amount, 0) : "—"}</td><td>{f.owner ?? "—"}</td><td><StatusChip status={f.status} label={f.status === "OPEN" ? "Ouvert" : f.status} /></td></tr>
            ))}</tbody>
          </table>
        )}
      </Card>
      {can(me, "trade.write") && (
        <Card title="Nouveau dossier" className="mt">
          <form onSubmit={create} className="stack">
            <div className="form-grid">
              <label className="field"><span>Entité</span><select name="entity_id">{me?.entities.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label>
              <label className="field"><span>Objet</span><input name="title" required /></label>
              <label className="field"><span>Sens</span><select name="direction"><option value="IMPORT">Import</option><option value="EXPORT">Export</option></select></label>
              <label className="field"><span>Instrument envisagé (information)</span><input name="instrument_considered" /></label>
              <label className="field"><span>Montant</span><input name="amount" pattern="\d{1,13}(\.\d{1,2})?" /></label>
              <label className="field"><span>Devise</span><input name="currency" pattern="[A-Z]{3}" placeholder="USD" /></label>
            </div>
            <ErrorBox error={err} />
            <p className="small muted">Créé le {fmtDate(new Date().toISOString())} — aucune demande n’est adressée à un établissement.</p>
            <div className="row-end"><button className="btn btn-primary">Créer le dossier</button></div>
          </form>
        </Card>
      )}
    </>
  );
}
