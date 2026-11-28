"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { can, useMe } from "@/components/Shell";
import { useApi } from "@/components/StepUp";
import { Badge, Card, ErrorBox, KV, Loading, Notice, PageHeader } from "@/components/ui";
import { useFetch } from "@/lib/hooks";
import { fmtDate, fmtDateTime, fmtMoney } from "@/lib/format";
import { openDocument } from "@/lib/documents";

export default function Dossier() {
  const { id } = useParams<{ id: string }>();
  const me = useMe();
  const { call } = useApi();
  const { data: f, error, setData } = useFetch(`/v1/trade-files/${id}`);
  const [err, setErr] = useState<unknown>(null);
  const write = can(me, "trade.write");
  const post = async (path: string, body: unknown, method = "POST") => {
    setErr(null);
    try { setData(await call(`/v1/trade-files/${id}${path}`, { method, body })); } catch (e) { setErr(e); }
  };
  const formPost = (path: string) => (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const body = Object.fromEntries(Array.from(new FormData(e.currentTarget).entries()).filter(([, v]) => v !== ""));
    void post(path, body);
    e.currentTarget.reset();
  };
  if (error) return <ErrorBox error={error} />;
  if (!f) return <Loading />;
  return (
    <>
      <PageHeader title={`${f.reference} — ${f.title}`} subtitle={<>{f.direction === "IMPORT" ? "Importation" : "Exportation"} · {f.amount ? fmtMoney(f.amount, 0) : "montant non renseigné"} · responsable {f.owner}</>} />
      <Notice tone="warn"><strong>Gestion documentaire uniquement.</strong> {f.disclaimer}</Notice>
      <ErrorBox error={err} />
      <div className="grid grid-2">
        <Card title="Parties">
          <table className="table table-sm"><tbody>{f.parties.map((p: any) => <tr key={p.id}><td>{p.role}</td><td><strong>{p.name}</strong></td><td>{p.country_code}</td></tr>)}</tbody></table>
          {write && <form className="form-grid mt" onSubmit={formPost("/parties")}>
            <label className="field"><span>Rôle</span><input name="role" required /></label><label className="field"><span>Nom</span><input name="name" required /></label>
            <label className="field"><span>Pays</span><input name="country_code" required pattern="[A-Z]{2}" maxLength={2} /></label><button className="btn btn-ghost btn-sm">Ajouter</button></form>}
        </Card>
        <Card title="Échéances">
          <table className="table table-sm"><tbody>{f.deadlines.map((d: any) => <tr key={d.id}><td>{d.label}</td><td>{fmtDate(d.due_date)}</td><td><Badge tone={d.days_left < 15 ? "amber" : "grey"}>J-{d.days_left}</Badge></td></tr>)}</tbody></table>
          {write && <form className="form-grid mt" onSubmit={formPost("/deadlines")}>
            <label className="field"><span>Libellé</span><input name="label" required /></label><label className="field"><span>Date</span><input type="date" name="due_date" required /></label>
            <button className="btn btn-ghost btn-sm">Ajouter</button></form>}
        </Card>
        <Card title="Documents">
          <table className="table table-sm"><tbody>{f.documents.map((d: any) => (
            <tr key={d.id}><td>{d.title}<div className="small muted mono">SHA-256 {d.sha256.slice(0, 16)}…</div></td><td>{d.category}</td>
              <td><button className="btn btn-ghost btn-sm" onClick={() => openDocument(call, d.id, setErr)}>Lien temporaire</button></td></tr>))}</tbody></table>
          <p className="small muted">Ajout de pièces : page Documents (rattachement au dossier).</p>
        </Card>
        <Card title="Tâches">
          <table className="table table-sm"><tbody>{f.tasks.map((t: any) => (
            <tr key={t.id}><td>{t.label}<div className="small muted">{t.assignee ?? "—"} · {fmtDate(t.due_date)}</div></td>
              <td>{write ? (<select value={t.status} onChange={(e) => post(`/tasks/${t.id}`, { status: e.target.value }, "PATCH")}>
                <option value="TODO">À faire</option><option value="IN_PROGRESS">En cours</option><option value="DONE">Terminée</option></select>) : t.status}</td></tr>))}</tbody></table>
          {write && <form className="form-grid mt" onSubmit={formPost("/tasks")}>
            <label className="field"><span>Tâche</span><input name="label" required /></label><label className="field"><span>Échéance</span><input type="date" name="due_date" /></label>
            <button className="btn btn-ghost btn-sm">Ajouter</button></form>}
        </Card>
        <Card title="Demandes">
          <Notice>Une demande « transmise » l’est uniquement dans la simulation : aucun établissement ne la reçoit et aucun engagement n’en découle.</Notice>
          <ul className="timeline">{f.requests.map((r: any) => <li key={r.id}><div className="t-title">{r.kind} — {r.status_label}</div><div className="t-meta">{r.created_by} · {fmtDateTime(r.sent_at)}</div><div className="small">{r.body}</div></li>)}</ul>
          {write && <form className="stack mt" onSubmit={formPost("/requests")}>
            <label className="field"><span>Nature</span><input name="kind" defaultValue="Demande d'information" required /></label>
            <label className="field"><span>Contenu</span><textarea name="body" required minLength={5} rows={2} /></label>
            <div className="row-end"><button className="btn btn-ghost btn-sm">Transmettre (simulation)</button></div></form>}
        </Card>
        <Card title="Décisions">
          <ul className="timeline">{f.decisions.map((d: any) => <li key={d.id}><div className="t-title">{d.label}</div><div className="t-meta">{d.decided_by} · {fmtDateTime(d.at)}</div><div className="small">{d.rationale}</div></li>)}</ul>
          {f.decisions.length === 0 && <p className="empty">Aucune décision consignée.</p>}
          {write && <form className="stack mt" onSubmit={formPost("/decisions")}>
            <label className="field"><span>Décision</span><input name="label" required /></label>
            <label className="field"><span>Motivation</span><textarea name="rationale" required minLength={5} rows={2} /></label>
            <div className="row-end"><button className="btn btn-ghost btn-sm">Consigner</button></div></form>}
        </Card>
      </div>
      <Card title="Historique (journal d’audit)" className="mt">
        {f.history.length === 0 ? <p className="empty">Aucun événement.</p> : (
          <table className="table table-sm"><tbody>{f.history.map((h: any, i: number) => <tr key={i}><td>{fmtDateTime(h.at)}</td><td>{h.actor}</td><td className="mono small">{h.action}</td></tr>)}</tbody></table>
        )}
        <KV items={[["Créé le", fmtDateTime(f.created_at)]]} />
      </Card>
    </>
  );
}
