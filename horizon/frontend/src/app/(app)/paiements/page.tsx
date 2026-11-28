"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { can, useMe } from "@/components/Shell";
import { useApi } from "@/components/StepUp";
import { Badge, Card, ErrorBox, Loading, Notice, PageHeader, StatusChip, Tabs } from "@/components/ui";
import { IconPlus } from "@/components/icons";
import { newIdempotencyKey } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import { useQueryParam } from "@/lib/query";
import { fmtDate, fmtMoney } from "@/lib/format";

const STATUSES = ["", "DRAFT", "TO_REVIEW", "PENDING_APPROVAL", "APPROVED", "SCHEDULED", "PROCESSING", "COMPLETED", "REJECTED", "CANCELLED"];
const LABELS: Record<string, string> = { "": "Tous", DRAFT: "Brouillon", TO_REVIEW: "À vérifier", PENDING_APPROVAL: "En attente d’approbation", APPROVED: "Approuvé", SCHEDULED: "Planifié", PROCESSING: "En traitement", COMPLETED: "Terminé", REJECTED: "Refusé", CANCELLED: "Annulé" };

function NewPayment({ onDone }: { onDone: (id: string) => void }) {
  const { call } = useApi();
  const accounts = useFetch<{ data: any[] }>("/v1/accounts?limit=200");
  const benes = useFetch<{ data: any[] }>("/v1/beneficiaries?limit=200");
  const [acc, setAcc] = useState("");
  const [label, setLabel] = useState("");
  const [date, setDate] = useState("");
  const [lines, setLines] = useState([{ beneficiary_id: "", amount: "", remittance_info: "" }]);
  const [err, setErr] = useState<unknown>(null);
  const [key] = useState(newIdempotencyKey);
  const sims = (accounts.data?.data ?? []).filter((a) => a.kind === "SIMULATED");
  const account = sims.find((a) => a.id === acc);
  const options = (benes.data?.data ?? []).filter((b) => account && b.entity.id === account.entity.id && b.status !== "REJECTED");
  const total = lines.reduce((s, l) => s + (Number(l.amount) || 0), 0);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      const b = await call<any>("/v1/payment-batches", {
        body: { debtor_account_id: acc, label: label || undefined, execution_date: date || undefined, payments: lines },
        headers: { "Idempotency-Key": key },
      });
      onDone(b.id);
    } catch (e2) { setErr(e2); }
  };
  return (
    <form onSubmit={submit} className="stack" data-testid="new-payment-form">
      <div className="form-grid">
        <label className="field"><span>Compte débité (simulé)</span>
          <select required value={acc} onChange={(e) => setAcc(e.target.value)} data-testid="np-account">
            <option value="">— choisir —</option>
            {sims.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.currency}) — dispo {fmtMoney(a.balance.available)}</option>)}
          </select></label>
        <label className="field"><span>Libellé</span><input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="ex. Règlement fournisseurs" data-testid="np-label" /></label>
        <label className="field"><span>Date d’exécution</span><input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
      </div>
      <div className="lines">
        {lines.map((l, i) => (
          <div className="line" key={i}>
            <label className="field"><span>Bénéficiaire {i + 1}</span>
              <select required value={l.beneficiary_id} onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, beneficiary_id: e.target.value } : x))} data-testid={`np-bene-${i}`}>
                <option value="">— {account ? "choisir" : "choisir d’abord le compte"} —</option>
                {options.map((b) => <option key={b.id} value={b.id}>{b.current_version.name} — {b.status_label}</option>)}
              </select></label>
            <label className="field"><span>Montant ({account?.currency ?? "EUR"})</span>
              <input required inputMode="decimal" pattern="\d{1,13}(\.\d{1,2})?" value={l.amount} onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, amount: e.target.value } : x))} placeholder="60000.00" data-testid={`np-amount-${i}`} /></label>
            <label className="field"><span>Référence / motif</span>
              <input maxLength={140} value={l.remittance_info} onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, remittance_info: e.target.value } : x))} /></label>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setLines(lines.filter((_, j) => j !== i))} disabled={lines.length === 1}>Retirer</button>
          </div>
        ))}
      </div>
      <div className="row">
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setLines([...lines, { beneficiary_id: "", amount: "", remittance_info: "" }])}>+ Ajouter une ligne</button>
        <span className="muted small">Total indicatif : {total.toLocaleString("fr-FR", { minimumFractionDigits: 2 })} · {lines.length} paiement(s) · clé d’idempotence <code>{key.slice(0, 8)}…</code></span>
      </div>
      <Notice>Le lot est créé en <strong>Brouillon</strong>. Il devra être soumis pour approbation ; un bénéficiaire non validé fera passer le lot « À vérifier ».</Notice>
      <ErrorBox error={err} />
      <div className="row-end"><button className="btn btn-primary" data-testid="np-submit">Créer le lot</button></div>
    </form>
  );
}

function CsvImport({ onDone }: { onDone: (id: string) => void }) {
  const { call } = useApi();
  const accounts = useFetch<{ data: any[] }>("/v1/accounts?limit=200");
  const [err, setErr] = useState<unknown>(null);
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErr(null);
    const fd = new FormData(e.currentTarget);
    try {
      const b = await call<any>("/v1/payment-batches/import-csv", { form: fd, headers: { "Idempotency-Key": newIdempotencyKey() } });
      onDone(b.id);
    } catch (e2) { setErr(e2); }
  };
  return (
    <form onSubmit={submit} className="stack">
      <Notice>Format attendu (séparateur « ; » ou « , ») : <code>iban;montant;libelle</code>. Chaque IBAN doit correspondre à un bénéficiaire déjà enregistré pour l’entité du compte : aucun bénéficiaire n’est créé implicitement. Une seule ligne invalide bloque l’import (rapport détaillé par ligne).</Notice>
      <div className="form-grid">
        <label className="field"><span>Compte débité</span>
          <select name="debtor_account_id" required>
            {(accounts.data?.data ?? []).filter((a) => a.kind === "SIMULATED").map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select></label>
        <label className="field"><span>Libellé</span><input name="label" defaultValue="Import CSV" /></label>
        <label className="field"><span>Fichier CSV</span><input type="file" name="file" accept=".csv,text/csv" required /></label>
      </div>
      <ErrorBox error={err} />
      <div className="row-end"><button className="btn btn-primary">Importer</button></div>
    </form>
  );
}

function Beneficiaries() {
  const me = useMe();
  const { call } = useApi();
  const list = useFetch<{ data: any[] }>("/v1/beneficiaries?limit=200");
  const [err, setErr] = useState<unknown>(null);
  const [iban, setIban] = useState("");
  const [check, setCheck] = useState<any>(null);
  const create = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErr(null);
    const f = Object.fromEntries(new FormData(e.currentTarget).entries());
    try {
      await call("/v1/beneficiaries", { body: f });
      (e.target as HTMLFormElement).reset();
      list.reload();
    } catch (e2) { setErr(e2); }
  };
  useEffect(() => {
    if (iban.replace(/\s/g, "").length < 15) { setCheck(null); return; }
    const t = setTimeout(() => call("/v1/beneficiaries/validate-iban", { body: { iban } }).then(setCheck).catch(() => {}), 300);
    return () => clearTimeout(t);
  }, [iban, call]);
  return (
    <div className="stack">
      <Card title="Bénéficiaires">
        {list.error && <ErrorBox error={list.error} />}
        {!list.data ? <Loading /> : (
          <table className="table table-sm" data-testid="beneficiaries">
            <thead><tr><th>Nom</th><th>Entité</th><th>IBAN</th><th>Version</th><th>Statut</th></tr></thead>
            <tbody>
              {list.data.data.map((b) => (
                <tr key={b.id}>
                  <td><Link className="link" href={`/paiements/beneficiaires/${b.id}`}>{b.current_version.name}</Link></td>
                  <td>{b.entity.name}</td><td className="mono">{b.current_version.iban}</td>
                  <td>v{b.current_version.version_no}{b.pending_review && <> <Badge tone="amber">modification en revue</Badge></>}</td>
                  <td><StatusChip status={b.status} label={b.status_label} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {can(me, "beneficiary.write") && (
        <Card title="Nouveau bénéficiaire">
          <form onSubmit={create} className="stack">
            <div className="form-grid">
              <label className="field"><span>Entité propriétaire</span>
                <select name="entity_id" required>{me?.entities.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label>
              <label className="field"><span>Raison sociale</span><input name="name" required minLength={2} /></label>
              <label className="field"><span>IBAN (synthétique)</span><input name="iban" required value={iban} onChange={(e) => setIban(e.target.value)} /></label>
              <label className="field"><span>BIC</span><input name="bic" maxLength={11} /></label>
              <label className="field"><span>Pays (ISO)</span><input name="country_code" required pattern="[A-Za-z]{2}" maxLength={2} defaultValue="FR" /></label>
              <label className="field"><span>Catégorie</span><input name="category" defaultValue="Fournisseur" /></label>
            </div>
            {check && (
              <Notice tone={check.format_valid ? "ok" : "warn"}>
                Format {check.format_valid ? "valide" : `invalide : ${check.issues.join(", ")}`}. <strong>{check.scope}</strong>
              </Notice>
            )}
            <p className="small muted">La création ouvre une revue : un approbateur distinct du créateur devra valider la version 1 avant tout paiement.</p>
            <ErrorBox error={err} />
            <div className="row-end"><button className="btn btn-primary">Créer (revue requise)</button></div>
          </form>
        </Card>
      )}
    </div>
  );
}

export default function Paiements() {
  const me = useMe();
  const router = useRouter();
  const nouveau = useQueryParam("nouveau");
  const q = useQueryParam("q");
  const [tab, setTab] = useState("batches");
  const [status, setStatus] = useState("");
  useEffect(() => { if (nouveau) setTab("new"); }, [nouveau]);
  const batches = useFetch<{ data: any[] }>(tab === "batches" ? `/v1/payment-batches?limit=200${status ? `&status=${status}` : ""}` : null);
  const rows = useMemo(() => (batches.data?.data ?? []).filter((b) => !q || `${b.reference} ${b.label} ${b.entity.name}`.toLowerCase().includes(q.toLowerCase())), [batches.data, q]);
  const tabs = [{ id: "batches", label: "Lots et virements" }, ...(can(me, "payment.prepare") ? [{ id: "new", label: "Nouveau paiement" }, { id: "csv", label: "Import CSV" }] : []), { id: "benes", label: "Bénéficiaires" }];
  return (
    <>
      <PageHeader title="Paiements" subtitle="Préparation, approbation à plusieurs, exécution simulée et suivi des statuts"
        actions={can(me, "payment.prepare") && <button className="btn btn-primary" onClick={() => setTab("new")}><IconPlus size={18} />Nouveau paiement</button>} />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === "batches" && (
        <Card title="Lots de paiements" actions={
          <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}><span>Statut</span>
            <select value={status} onChange={(e) => setStatus(e.target.value)} data-testid="status-filter">{STATUSES.map((s) => <option key={s} value={s}>{LABELS[s]}</option>)}</select></label>}>
          {q && <Notice>Filtre de recherche : « {q} »</Notice>}
          {batches.error && <ErrorBox error={batches.error} />}
          {!batches.data ? <Loading /> : (
            <div className="table-wrap">
              <table className="table" data-testid="batches">
                <thead><tr><th>Référence</th><th>Libellé</th><th>Entité</th><th className="num">Total</th><th>Lignes</th><th>Exécution</th><th>Approbations</th><th>Statut</th></tr></thead>
                <tbody>
                  {rows.map((b) => (
                    <tr key={b.id}>
                      <td><Link className="link mono" href={`/paiements/lots/${b.id}`}>{b.reference}</Link><br /><span className="small muted">{b.kind_label} · v{b.version}</span></td>
                      <td>{b.label}</td><td>{b.entity.name}</td><td className="num">{fmtMoney(b.total)}</td><td>{b.payment_count}</td>
                      <td>{fmtDate(b.execution_date)}</td>
                      <td>{b.required_approvals ? `${b.valid_approvals}/${b.required_approvals}` : "—"}</td>
                      <td><StatusChip status={b.status} label={b.status_label} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {rows.length === 0 && <p className="empty">Aucun lot.</p>}
            </div>
          )}
        </Card>
      )}
      {tab === "new" && <Card title="Nouveau virement ou lot"><NewPayment onDone={(id) => router.push(`/paiements/lots/${id}`)} /></Card>}
      {tab === "csv" && <Card title="Import CSV"><CsvImport onDone={(id) => router.push(`/paiements/lots/${id}`)} /></Card>}
      {tab === "benes" && <Beneficiaries />}
    </>
  );
}
