"use client";
import { useState } from "react";
import { can, useMe } from "@/components/Shell";
import { useApi } from "@/components/StepUp";
import { Card, ErrorBox, Loading, Notice, PageHeader } from "@/components/ui";
import { openDocument } from "@/lib/documents";
import { useFetch } from "@/lib/hooks";
import { fmtDateTime } from "@/lib/format";

export default function Documents() {
  const me = useMe();
  const { call } = useApi();
  const docs = useFetch<{ data: any[]; page: any }>("/v1/documents?limit=200");
  const files = useFetch<{ data: any[] }>("/v1/trade-files");
  const [err, setErr] = useState<unknown>(null);
  const [ok, setOk] = useState<string | null>(null);
  const upload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErr(null);
    const fd = new FormData(e.currentTarget);
    if (!fd.get("trade_file_id")) fd.delete("trade_file_id");
    try { const d = await call<any>("/v1/documents", { form: fd }); setOk(`Document enregistré — SHA-256 ${d.sha256}`); docs.reload(); (e.target as HTMLFormElement).reset(); } catch (e2) { setErr(e2); }
  };
  return (
    <>
      <PageHeader title="Documents" subtitle="Stockage objet protégé (chiffré au repos) — accès par lien temporaire signé" />
      <Notice>Chaque téléchargement passe par un lien signé valable quelques minutes ; les droits de l’utilisateur sont revérifiés au moment de l’accès et l’opération est journalisée.</Notice>
      <ErrorBox error={err} />
      {ok && <Notice tone="ok">{ok}</Notice>}
      <Card title="Documents accessibles">
        {!docs.data ? <Loading /> : (
          <table className="table table-sm" data-testid="documents">
            <thead><tr><th>Titre</th><th>Catégorie</th><th>Fichier</th><th>Taille</th><th>Empreinte SHA-256</th><th>Déposé</th><th /></tr></thead>
            <tbody>{docs.data.data.map((d) => (
              <tr key={d.id}><td><strong>{d.title}</strong></td><td>{d.category}</td><td className="small">{d.filename}</td><td>{(d.size_bytes / 1024).toFixed(1)} Ko</td>
                <td className="mono small">{d.sha256.slice(0, 20)}…</td><td className="small">{d.uploaded_by}<br />{fmtDateTime(d.uploaded_at)}</td>
                <td><button className="btn btn-outline btn-sm" onClick={() => openDocument(call, d.id, setErr)} data-testid="doc-link">Lien temporaire</button></td></tr>
            ))}</tbody>
          </table>
        )}
      </Card>
      {can(me, "document.write") && (
        <Card title="Déposer un document" className="mt">
          <form onSubmit={upload} className="stack">
            <div className="form-grid">
              <label className="field"><span>Entité</span><select name="entity_id">{me?.entities.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label>
              <label className="field"><span>Titre</span><input name="title" required /></label>
              <label className="field"><span>Catégorie</span><input name="category" defaultValue="Divers" /></label>
              <label className="field"><span>Dossier (facultatif)</span><select name="trade_file_id"><option value="">—</option>{files.data?.data.map((f) => <option key={f.id} value={f.id}>{f.reference}</option>)}</select></label>
              <label className="field"><span>Fichier (PDF, PNG, JPEG, CSV, TXT, XML ≤ 10 Mo)</span><input type="file" name="file" required /></label>
            </div>
            <div className="row-end"><button className="btn btn-primary">Déposer</button></div>
          </form>
        </Card>
      )}
    </>
  );
}
