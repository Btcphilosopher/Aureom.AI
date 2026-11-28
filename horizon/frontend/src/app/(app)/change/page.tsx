"use client";
import { useEffect, useState } from "react";
import { can, useMe } from "@/components/Shell";
import { useApi } from "@/components/StepUp";
import { Badge, Card, ErrorBox, KV, Loading, Notice, PageHeader } from "@/components/ui";
import { useFetch } from "@/lib/hooks";
import { fmtDate, fmtDateTime, fmtMoney } from "@/lib/format";

const CCYS = ["EUR", "USD", "GBP", "CHF", "JPY", "SEK", "PLN"];

export default function Change() {
  const me = useMe();
  const { call } = useApi();
  const rates = useFetch<{ data: any[]; notice: string }>("/v1/fx/rates");
  const accounts = useFetch<{ data: any[] }>("/v1/accounts?limit=200");
  const [form, setForm] = useState({ base: "EUR", quote: "USD", side: "SELL", amount: "250000.00", amount_currency: "EUR", kind: "INDICATIVE", sell_account_id: "", buy_account_id: "" });
  const [q, setQ] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const sims = (accounts.data?.data ?? []).filter((a) => a.kind === "SIMULATED");
  const entity = me?.entities[0]?.id;
  const sellCcy = form.side === "SELL" ? form.base : form.quote;
  const buyCcy = form.side === "SELL" ? form.quote : form.base;

  const quote = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    const acc = sims.find((a) => a.id === form.sell_account_id);
    try {
      setQ(await call("/v1/fx-quotes", { body: {
        entity_id: acc?.entity.id ?? entity, base: form.base, quote: form.quote, side: form.side, amount: form.amount,
        amount_currency: form.amount_currency, kind: form.kind,
        sell_account_id: form.kind === "EXECUTABLE_SIMULATED" ? form.sell_account_id || undefined : undefined,
        buy_account_id: form.kind === "EXECUTABLE_SIMULATED" ? form.buy_account_id || undefined : undefined,
      } }));
    } catch (e2) { setErr(e2); }
  };
  const accept = async () => {
    setErr(null);
    try { setQ(await call(`/v1/fx-quotes/${q.id}/accept`, { method: "POST" })); } catch (e2) { setErr(e2); }
  };
  const remaining = q ? Math.max(0, Math.floor((new Date(q.expires_at).getTime() - now) / 1000)) : 0;
  const set = (k: string, v: string) => setForm({ ...form, [k]: v });

  return (
    <>
      <PageHeader title="Change" subtitle="Simulateur de devis — taux indicatifs et offres exécutables SIMULÉES (aucun ordre réel)" />
      <Notice tone="warn">Démonstration : aucun ordre n’est transmis à un marché ou à une banque. Une offre « exécutable simulée » acceptée ne fait que comptabiliser une conversion entre deux comptes simulés du registre.</Notice>
      <div className="grid grid-2">
        <Card title="Simulateur de devis">
          <form onSubmit={quote} className="stack" data-testid="fx-form">
            <div className="form-grid">
              <label className="field"><span>Devise de base</span><select value={form.base} onChange={(e) => set("base", e.target.value)}>{CCYS.map((c) => <option key={c}>{c}</option>)}</select></label>
              <label className="field"><span>Devise de cotation</span><select value={form.quote} onChange={(e) => set("quote", e.target.value)}>{CCYS.map((c) => <option key={c}>{c}</option>)}</select></label>
              <label className="field"><span>Sens (devise de base)</span><select value={form.side} onChange={(e) => set("side", e.target.value)}><option value="SELL">Vendre {form.base}</option><option value="BUY">Acheter {form.base}</option></select></label>
              <label className="field"><span>Montant</span><input value={form.amount} onChange={(e) => set("amount", e.target.value)} pattern="\d{1,13}(\.\d{1,2})?" required /></label>
              <label className="field"><span>Exprimé en</span><select value={form.amount_currency} onChange={(e) => set("amount_currency", e.target.value)}><option>{form.base}</option><option>{form.quote}</option></select></label>
              <label className="field"><span>Type</span><select value={form.kind} onChange={(e) => set("kind", e.target.value)} data-testid="fx-kind">
                <option value="INDICATIVE">Taux indicatif (information)</option><option value="EXECUTABLE_SIMULATED">Offre exécutable (simulée, 30 s)</option></select></label>
            </div>
            {form.kind === "EXECUTABLE_SIMULATED" && (
              <div className="form-grid">
                <label className="field"><span>Compte débité ({sellCcy})</span><select value={form.sell_account_id} onChange={(e) => set("sell_account_id", e.target.value)} required>
                  <option value="">— choisir —</option>{sims.filter((a) => a.currency === sellCcy).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
                <label className="field"><span>Compte crédité ({buyCcy})</span><select value={form.buy_account_id} onChange={(e) => set("buy_account_id", e.target.value)} required>
                  <option value="">— choisir —</option>{sims.filter((a) => a.currency === buyCcy).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
              </div>
            )}
            <ErrorBox error={err} />
            <div className="row-end"><button className="btn btn-primary" disabled={!can(me, "fx.quote")} data-testid="fx-submit">Obtenir un devis</button></div>
            {!can(me, "fx.quote") && <p className="small muted">Réservé au rôle Préparation.</p>}
          </form>
        </Card>
        <Card title="Devis">
          {!q ? <p className="empty">Aucun devis demandé.</p> : (
            <div className="stack" data-testid="fx-quote">
              <div className="row"><Badge tone={q.kind === "INDICATIVE" ? "grey" : "blue"}>{q.kind_label}</Badge>
                <Badge tone={q.status === "OPEN" && remaining > 0 ? "green" : q.status === "ACCEPTED_SIMULATED" ? "navy" : "grey"}>
                  {q.status === "OPEN" ? (remaining > 0 ? `Valide encore ${remaining} s` : "Expiré") : q.status === "ACCEPTED_SIMULATED" ? "Accepté (simulation)" : q.status}</Badge></div>
              <KV items={[["Paire", q.pair], ["Sens", q.side === "SELL" ? "Vente de la devise de base" : "Achat de la devise de base"],
                ["Vous vendez", fmtMoney(q.sell, 2)], ["Vous recevez", fmtMoney(q.buy, 2)], ["Taux médian", q.mid_rate], ["Taux client", q.client_rate],
                ["Frais (marge)", `${q.fee_bps} pb = ${fmtMoney(q.fee, 2)}`], ["Source", q.source], ["Créé", fmtDateTime(q.created_at)], ["Expiration", fmtDateTime(q.expires_at)]]} />
              {q.kind === "INDICATIVE" && <Notice>Un taux indicatif est une information : il ne peut pas être accepté.</Notice>}
              {q.kind === "EXECUTABLE_SIMULATED" && q.status === "OPEN" && (
                <button className="btn btn-primary" disabled={remaining <= 0 || !can(me, "fx.execute_simulated")} onClick={accept}>Accepter l’offre simulée (MFA)</button>
              )}
              {q.kind === "EXECUTABLE_SIMULATED" && !can(me, "fx.execute_simulated") && <p className="small muted">L’acceptation requiert le rôle Approbation (séparation préparation / exécution).</p>}
              {q.ledger_entry_id && <Notice tone="ok">Conversion comptabilisée dans le registre simulé (écriture équilibrée par devise via les positions de change).</Notice>}
            </div>
          )}
        </Card>
      </div>
      <div style={{ height: 16 }} />
      <Card title="Taux du jour (indicatifs)">
        {!rates.data ? <Loading /> : (
          <>
            <table className="table table-sm" data-testid="fx-rates"><thead><tr><th>Paire</th><th className="num">Taux</th><th>Date</th><th>Source</th><th>Identifiant</th></tr></thead>
              <tbody>{rates.data.data.map((r) => <tr key={r.id}><td>{r.pair}</td><td className="num">{r.rate}</td><td>{fmtDate(r.as_of)}</td><td className="small">{r.source}</td><td className="mono small">{r.id.slice(0, 8)}</td></tr>)}</tbody></table>
            <Notice>{rates.data.notice}</Notice>
          </>
        )}
      </Card>
    </>
  );
}
