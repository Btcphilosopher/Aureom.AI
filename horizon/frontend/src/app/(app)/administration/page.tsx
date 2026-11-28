"use client";
import { useState } from "react";
import { can, useMe } from "@/components/Shell";
import { useApi } from "@/components/StepUp";
import { Badge, Card, ErrorBox, Loading, Notice, PageHeader, Pager, Tabs } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import { fmtDateTime, fmtMoney } from "@/lib/format";

function Users() {
  const me = useMe();
  const { call } = useApi();
  const users = useFetch<{ data: any[] }>("/v1/admin/users");
  const [err, setErr] = useState<unknown>(null);
  const grant = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErr(null);
    const f = Object.fromEntries(Array.from(new FormData(e.currentTarget).entries()).filter(([, v]) => v !== ""));
    try { await call("/v1/admin/role-assignments", { body: f }); users.reload(); } catch (e2) { setErr(e2); }
  };
  const revoke = async (id: string) => {
    setErr(null);
    try { await call(`/v1/admin/role-assignments/${id}/revoke`, { method: "POST" }); users.reload(); } catch (e2) { setErr(e2); }
  };
  if (users.error) return <ErrorBox error={users.error} title="Gestion des utilisateurs réservée au rôle Administration" />;
  if (!users.data) return <Loading />;
  return (
    <div className="stack">
      <Card title="Utilisateurs, rôles, mandats et plafonds">
        <Notice>Le rôle Administration gère les accès mais ne confère <strong>aucun</strong> droit de préparation ni d’approbation de paiement. Un administrateur ne peut pas s’attribuer de rôle.</Notice>
        <table className="table table-sm" data-testid="admin-users">
          <thead><tr><th>Utilisateur</th><th>MFA</th><th>Rôles (périmètre · plafond · mandat)</th></tr></thead>
          <tbody>{users.data.data.map((u) => (
            <tr key={u.id}><td><strong>{u.full_name}</strong><div className="small muted">{u.title} · {u.email}</div></td><td><Badge tone="green">{u.mfa}</Badge></td>
              <td><ul className="small" style={{ margin: 0, paddingLeft: 16 }}>{u.roles.map((r: any) => (
                <li key={r.id} style={{ textDecoration: r.revoked_at ? "line-through" : undefined }}>
                  <strong>{r.role_label}</strong> — {r.entity}{r.account_id ? " (compte restreint)" : ""}{r.approval_limit ? ` · plafond ${fmtMoney(r.approval_limit, 0)}` : ""}{r.mandate_reference ? ` · ${r.mandate_reference}` : ""}
                  {!r.revoked_at && can(me, "admin.users") && <button className="btn btn-ghost btn-sm" style={{ marginLeft: 8 }} onClick={() => revoke(r.id)}>Révoquer</button>}
                </li>))}</ul></td></tr>
          ))}</tbody>
        </table>
      </Card>
      <Card title="Attribuer un rôle (MFA requise)">
        <form onSubmit={grant} className="form-grid">
          <label className="field"><span>Utilisateur</span><select name="user_id">{users.data.data.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></label>
          <label className="field"><span>Rôle</span><select name="role"><option value="VIEWER">Consultation</option><option value="PREPARER">Préparation</option><option value="APPROVER">Approbation</option><option value="AUDITOR">Audit</option><option value="ADMIN">Administration</option></select></label>
          <label className="field"><span>Entité</span><select name="entity_id"><option value="">Toutes</option>{me?.entities.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label>
          <label className="field"><span>Plafond (Approbation)</span><input name="approval_limit" pattern="\d{1,13}(\.\d{1,2})?" /></label>
          <label className="field"><span>Référence du mandat</span><input name="mandate_reference" /></label>
          <button className="btn btn-primary">Attribuer</button>
        </form>
        <ErrorBox error={err} />
      </Card>
    </div>
  );
}

function DelegationForm({ onDone }: { onDone: () => void }) {
  const me = useMe();
  const { call } = useApi();
  const dir = useFetch<{ data: { id: string; full_name: string; title: string }[] }>("/v1/directory");
  const [err, setErr] = useState<unknown>(null);
  const [ok, setOk] = useState(false);
  if (!me || !can(me, "payment.approve")) {
    return <Notice>Seul un approbateur peut déléguer son propre droit d’approbation.</Notice>;
  }
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErr(null);
    setOk(false);
    const f = Object.fromEntries(new FormData(e.currentTarget).entries()) as Record<string, string>;
    try {
      await call("/v1/delegations", { body: { ...f, valid_days: Number(f.valid_days) } });
      setOk(true);
      onDone();
    } catch (e2) { setErr(e2); }
  };
  return (
    <form className="form-grid" onSubmit={submit} data-testid="delegation-form">
      <label>Délégataire
        <select name="delegate_user_id" required>
          {(dir.data?.data ?? []).filter((u) => u.id !== me.user.id).map((u) => <option key={u.id} value={u.id}>{u.full_name} — {u.title}</option>)}
        </select>
      </label>
      <label>Entité
        <select name="entity_id" required>{me.entities.map((en: any) => <option key={en.id} value={en.id}>{en.name}</option>)}</select>
      </label>
      <label>Plafond délégué (EUR)<input name="max_amount" required pattern="^\d{1,13}(\.\d{1,2})?$" placeholder="200000.00" /></label>
      <label>Durée (jours)<input name="valid_days" type="number" min={1} max={30} defaultValue={7} required /></label>
      <label className="span-2">Motif<input name="reason" required minLength={5} placeholder="Congés, absence…" /></label>
      <div className="span-2"><button className="btn btn-primary" type="submit">Déléguer (réauthentification)</button></div>
      {ok && <Notice tone="ok">Délégation enregistrée et auditée.</Notice>}
      {err ? <ErrorBox error={err} /> : null}
    </form>
  );
}

function Policies() {
  const pol = useFetch<{ data: any[] }>("/v1/admin/approval-policies");
  const del = useFetch<{ data: any[] }>("/v1/delegations");
  return (
    <div className="stack">
      <Card title="Politiques d’approbation">
        {pol.error && <ErrorBox error={pol.error} />}
        {pol.data && (
          <table className="table table-sm" data-testid="policies"><thead><tr><th>Règle</th><th>Portée</th><th className="num">À partir de</th><th>Approbateurs distincts</th><th>Validité</th></tr></thead>
            <tbody>{pol.data.data.map((r) => <tr key={r.id}><td>{r.name}</td><td>{r.scope}{r.scope === "Entité" ? ` — ${r.entity}` : ""}</td><td className="num">{fmtMoney(r.min_amount, 0)}</td><td>{r.required_approvals}</td><td>{r.approval_validity_hours} h</td></tr>)}</tbody></table>
        )}
        <Notice>La règle la plus spécifique s’applique (compte &gt; entité &gt; groupe), puis le seuil le plus élevé atteint par le montant du lot.</Notice>
      </Card>
      <Card title="Délégations d’approbation">
        {del.error && <ErrorBox error={del.error} />}
        {del.data && (del.data.data.length === 0 ? <p className="empty">Aucune délégation.</p> : (
          <table className="table table-sm"><thead><tr><th>Délégant</th><th>Délégataire</th><th>Entité</th><th className="num">Plafond</th><th>Période</th><th>État</th></tr></thead>
            <tbody>{del.data.data.map((d) => <tr key={d.id}><td>{d.delegator}</td><td>{d.delegate}</td><td>{d.entity}</td><td className="num">{fmtMoney(d.max_amount, 0)}</td><td className="small">{fmtDateTime(d.valid_from)} → {fmtDateTime(d.valid_to)}</td><td><Badge tone={d.active ? "green" : "grey"}>{d.active ? "Active" : "Inactive"}</Badge></td></tr>)}</tbody></table>
        ))}
        <p className="small muted">Une délégation est temporaire, plafonnée au plafond du délégant et ne vaut que si le délégant détient lui-même le droit.</p>
        <DelegationForm onDone={del.reload} />
      </Card>
    </div>
  );
}

function Audit() {
  const me = useMe();
  const { call } = useApi();
  const [cursor, setCursor] = useState<string | null>(null);
  const [stack, setStack] = useState<(string | null)[]>([]);
  const [action, setAction] = useState("");
  const ev = useFetch<{ data: any[]; page: any }>(`/v1/audit-events?limit=25${cursor ? `&cursor=${cursor}` : ""}${action ? `&action=${encodeURIComponent(action)}` : ""}`);
  const [chain, setChain] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [exp, setExp] = useState<string | null>(null);
  const verify = async () => { setErr(null); try { setChain(await call("/v1/audit-events/verify")); } catch (e) { setErr(e); } };
  const exportReport = async () => {
    setErr(null);
    try {
      const res = await apiFetch<Response>("/v1/reports/treasury-export", { method: "POST", raw: true });
      const blob = await res.blob();
      const name = res.headers.get("content-disposition")?.split("filename=")[1]?.replaceAll('"', "") ?? "horizon-rapport.zip";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = name; a.click();
      URL.revokeObjectURL(url);
      setExp(`${name} — SHA-256 ${res.headers.get("x-report-sha256")}`);
    } catch (e) { setErr(e); }
  };
  return (
    <div className="stack">
      <Card title="Journal d’audit chaîné" actions={<div className="row">
        <button className="btn btn-ghost" onClick={verify} data-testid="verify-chain">Vérifier la chaîne</button>
        {can(me, "report.export") && <button className="btn btn-primary" onClick={exportReport} data-testid="export-report">Exporter rapport + piste d’audit</button>}</div>}>
        <ErrorBox error={err} />
        {chain && <Notice tone={chain.valid ? "ok" : "warn"}>{chain.valid ? `Chaîne intègre : ${chain.checked} événements vérifiés.` : `Chaîne rompue à l’événement ${chain.broken_at_event_id}.`}</Notice>}
        {exp && <Notice tone="ok">Archive téléchargée : {exp}</Notice>}
        {ev.error ? <ErrorBox error={ev.error} title="Consultation réservée aux rôles Audit et Administration" /> : (
          <>
            <label className="field" style={{ maxWidth: 320 }}><span>Filtrer par action (préfixe)</span>
              <input value={action} onChange={(e) => { setAction(e.target.value); setCursor(null); setStack([]); }} placeholder="ex. approval, access.denied" /></label>
            {!ev.data ? <Loading /> : (
              <>
                <div className="table-wrap"><table className="table table-sm" data-testid="audit-events">
                  <thead><tr><th>#</th><th>Horodatage</th><th>Acteur</th><th>Action</th><th>Objet</th><th>Résultat</th><th>Détails (expurgés)</th><th>Hash</th></tr></thead>
                  <tbody>{ev.data.data.map((e) => (
                    <tr key={e.id}><td>{e.id}</td><td className="small">{fmtDateTime(e.at)}</td><td>{e.actor}</td><td className="mono small">{e.action}</td>
                      <td className="small">{e.object_type}{e.object_id ? ` · ${String(e.object_id).slice(0, 12)}` : ""}</td>
                      <td><Badge tone={e.outcome === "SUCCESS" ? "green" : e.outcome === "DENIED" ? "red" : "amber"}>{e.outcome}</Badge></td>
                      <td className="small mono" style={{ maxWidth: 260, wordBreak: "break-all" }}>{JSON.stringify(e.details).slice(0, 140)}</td><td className="mono small">{e.hash.slice(0, 10)}…</td></tr>
                  ))}</tbody></table></div>
                <Pager page={ev.data.page} onPrev={stack.length ? () => { const s = [...stack]; const p = s.pop() ?? null; setStack(s); setCursor(p); } : undefined}
                  onNext={() => { setStack([...stack, cursor]); setCursor(ev.data!.page.next_cursor); }} />
              </>
            )}
          </>
        )}
      </Card>
    </div>
  );
}

function Demo() {
  const { call } = useApi();
  const jobs = useFetch<{ data: any[] }>("/v1/demo/jobs");
  const events = useFetch<{ data: any[] }>("/v1/demo/simulator/events");
  const executed = useFetch<{ data: any[] }>("/v1/payments?status=EXECUTED&limit=50");
  const receipts = useFetch<{ data: any[] }>("/v1/expected-receipts?limit=100");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const reload = () => { jobs.reload(); events.reload(); executed.reload(); receipts.reload(); };
  const run = async (fn: () => Promise<any>, label: (r: any) => string) => {
    setErr(null); setMsg(null);
    try { const r = await fn(); setMsg(label(r)); reload(); } catch (e) { setErr(e); }
  };
  return (
    <div className="stack">
      <Notice tone="warn">Contrôles réservés à l’environnement de démonstration (désactivés hors démonstration). Ils pilotent le simulateur bancaire fictif.</Notice>
      {msg && <Notice tone="ok">{msg}</Notice>}
      <ErrorBox error={err} />
      <div className="grid grid-2">
        <Card title="File de tâches">
          <button className="btn btn-primary" data-testid="run-jobs" onClick={() => run(() => call("/v1/demo/run-jobs", { method: "POST" }), (r) => `${r.processed} tâche(s) traitée(s)`)}>Traiter la file</button>
          {jobs.data && <table className="table table-sm mt"><thead><tr><th>Tâche</th><th>État</th><th>Essais</th></tr></thead>
            <tbody>{jobs.data.data.slice(0, 12).map((j) => <tr key={j.id}><td className="mono small">{j.kind}</td><td>{j.status}</td><td>{j.attempts}</td></tr>)}</tbody></table>}
        </Card>
        <Card title="Injecter une panne (résultat inconnu)">
          <form className="stack" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); void run(() => call("/v1/demo/simulator/faults", { body: { kind: f.get("kind"), match_remittance: f.get("match") || undefined } }), () => "Panne injectée : elle s’appliquera à la prochaine soumission correspondante"); }}>
            <label className="field"><span>Type</span><select name="kind"><option value="TIMEOUT_AFTER_RECORD">Délai dépassé APRÈS enregistrement de l’ordre</option><option value="TIMEOUT_BEFORE_RECORD">Délai dépassé AVANT enregistrement</option></select></label>
            <label className="field"><span>Motif du paiement ciblé (facultatif)</span><input name="match" /></label>
            <div className="row-end"><button className="btn btn-ghost">Injecter</button></div>
          </form>
        </Card>
        <Card title="Retour de fonds">
          <form className="stack" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); void run(() => call("/v1/demo/simulator/returns", { body: { payment_id: f.get("payment_id"), reason_code: "MD06" } }), () => "Retour de fonds simulé et comptabilisé"); }}>
            <label className="field"><span>Paiement exécuté</span><select name="payment_id" required>{executed.data?.data.map((p) => <option key={p.id} value={p.id}>{p.end_to_end_id} — {p.beneficiary.name} — {fmtMoney(p.amount, 0)}</option>)}</select></label>
            <div className="row-end"><button className="btn btn-ghost" disabled={!executed.data?.data.length}>Simuler le retour</button></div>
          </form>
        </Card>
        <Card title="Encaissement attendu reçu">
          <form className="stack" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); void run(() => call("/v1/demo/simulator/incoming", { body: { expected_receipt_id: f.get("rid") } }), () => "Crédit reçu, comptabilisé et rapproché de l’encaissement attendu"); }}>
            <label className="field"><span>Encaissement attendu</span><select name="rid" required>{receipts.data?.data.filter((r) => r.status === "EXPECTED").map((r) => <option key={r.id} value={r.id}>{r.counterparty} — {fmtMoney(r.amount, 0)}</option>)}</select></label>
            <div className="row-end"><button className="btn btn-ghost">Simuler la réception</button></div>
          </form>
        </Card>
      </div>
      <Card title="Événements du système destinataire (simulé)">
        {events.data && (
          <table className="table table-sm" data-testid="sim-events"><thead><tr><th>Émis</th><th>Type</th><th>Clé</th><th>Livraisons</th><th>Traitement</th><th /></tr></thead>
            <tbody>{events.data.data.map((e) => (
              <tr key={e.event_id}><td className="small">{fmtDateTime(e.at)}</td><td className="mono small">{e.type}</td><td className="mono small">{e.submission_key?.slice(0, 16) ?? "—"}</td>
                <td>{e.delivered_count}{e.duplicate_deliveries ? ` (dont ${e.duplicate_deliveries} doublon(s) ignoré(s))` : ""}</td><td>{e.inbox_outcome ?? "—"}</td>
                <td><button className="btn btn-ghost btn-sm" onClick={() => run(() => call("/v1/demo/simulator/redeliver", { body: { event_id: e.event_id } }), (r) => `Redélivré : ${r.outcome}`)}>Redélivrer</button></td></tr>
            ))}</tbody></table>
        )}
      </Card>
    </div>
  );
}

export default function Administration() {
  const [tab, setTab] = useState("users");
  return (
    <>
      <PageHeader title="Administration" subtitle="Utilisateurs, mandats, politiques d’approbation, audit et contrôles de démonstration" />
      <Tabs tabs={[{ id: "users", label: "Utilisateurs et rôles" }, { id: "policies", label: "Politiques et délégations" }, { id: "audit", label: "Audit et rapports" }, { id: "demo", label: "Démonstration" }]} value={tab} onChange={setTab} />
      {tab === "users" && <Users />}
      {tab === "policies" && <Policies />}
      {tab === "audit" && <Audit />}
      {tab === "demo" && <Demo />}
    </>
  );
}
