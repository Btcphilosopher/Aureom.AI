"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Badge, Card, ErrorBox, KV, Loading, Notice, PageHeader, Pager } from "@/components/ui";
import { useFetch } from "@/lib/hooks";
import { fmtAmount, fmtDate, fmtDateTime, fmtMoney, num } from "@/lib/format";

function Spark({ data }: { data: { date: string; booked: { amount: string } }[] }) {
  if (data.length < 2) return null;
  const vals = data.map((d) => num(d.booked.amount));
  const lo = Math.min(...vals), hi = Math.max(...vals) || 1;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1)) * 600},${110 - ((v - lo) / (hi - lo || 1)) * 100}`).join(" ");
  return (
    <svg viewBox="0 0 600 120" width="100%" role="img" aria-label="Historique du solde comptabilisé">
      <polyline points={pts} fill="none" stroke="#00764a" strokeWidth="2" />
      <text x="0" y="118" fontSize="11" fill="#6c7988">{fmtDate(data[0].date)}</text>
      <text x="600" y="118" fontSize="11" fill="#6c7988" textAnchor="end">{fmtDate(data[data.length - 1].date)}</text>
      <text x="4" y="12" fontSize="11" fill="#6c7988">max {fmtAmount(hi, "EUR", 0)} · min {fmtAmount(lo, "EUR", 0)}</text>
    </svg>
  );
}

export default function Compte() {
  const { id } = useParams<{ id: string }>();
  const [cursor, setCursor] = useState<string | null>(null);
  const [stack, setStack] = useState<(string | null)[]>([]);
  const acc = useFetch(`/v1/accounts/${id}`);
  const tx = useFetch<{ data: any[]; page: any; note?: string }>(`/v1/accounts/${id}/transactions?limit=25${cursor ? `&cursor=${cursor}` : ""}`);
  const hist = useFetch<{ data: any[] }>(`/v1/accounts/${id}/balance-history?days=60`);
  if (acc.error) return <ErrorBox error={acc.error} />;
  if (!acc.data) return <Loading />;
  const a = acc.data;
  const b = a.balance;
  return (
    <>
      <PageHeader title={a.name} subtitle={<>{a.entity.name} · <span className="mono">{a.iban}</span> · {a.bic} · <Badge tone={a.kind === "SIMULATED" ? "navy" : "amber"}>{a.kind_label}</Badge></>} />
      <div className="grid grid-2">
        <Card title="Soldes">
          <KV items={[
            ["Solde comptabilisé", fmtMoney(b.booked, 2)],
            ["Montants réservés", b.reserved ? fmtMoney(b.reserved, 2) : "Non applicable"],
            ["Solde disponible", <strong key="a" data-testid="available">{fmtMoney(b.available, 2)}</strong>],
            ["Opérations en attente", b.pending_operations ? `${b.pending_operations.count} — ${fmtMoney(b.pending_operations.outgoing, 2)}` : "—"],
            ["Source", b.source],
            ["Observé le", fmtDateTime(b.observed_at)],
            ["Fraîcheur", <Badge key="f" tone={b.freshness?.stale ? "red" : "green"}>{b.freshness?.label} {b.freshness?.age_hours != null ? `(${b.freshness.age_hours} h)` : ""}</Badge>],
            ["Devise", a.currency],
          ]} />
          <Notice>{b.available_rule}</Notice>
          {b.pending_operations && <p className="small muted">{b.pending_operations.note}</p>}
          {a.kind === "EXTERNAL_READONLY" && <Notice tone="warn">Compte externe en lecture seule : HORIZON ne peut ni le débiter ni l’additionner aux comptes simulés.</Notice>}
        </Card>
        <Card title={a.kind === "SIMULATED" ? "Historique du solde comptabilisé (60 jours)" : "Relevés reçus"}>
          {a.kind === "SIMULATED" ? (hist.data ? <Spark data={hist.data.data} /> : <Loading />) : (
            <table className="table table-sm">
              <thead><tr><th>Observé le</th><th className="num">Solde</th><th>Source</th><th>Référence</th></tr></thead>
              <tbody>{(a.snapshots ?? []).map((s: any, i: number) => (<tr key={i}><td>{fmtDateTime(s.observed_at)}</td><td className="num">{fmtMoney(s.booked, 2)}</td><td>{s.source}</td><td className="mono">{s.statement_reference}</td></tr>))}</tbody>
            </table>
          )}
        </Card>
      </div>
      <div style={{ height: 16 }} />
      <Card title="Écritures du registre affectant le compte">
        {tx.error && <ErrorBox error={tx.error} />}
        {tx.data?.note && <Notice>{tx.data.note}</Notice>}
        {tx.data && (
          <>
            <div className="table-wrap">
              <table className="table table-sm" data-testid="transactions">
                <thead><tr><th>N°</th><th>Journal</th><th>Date de valeur</th><th>Libellé</th><th className="num">Montant</th><th>Référence</th></tr></thead>
                <tbody>
                  {tx.data.data.map((t) => (
                    <tr key={t.entry_id}>
                      <td className="mono">{t.entry_number}</td><td><Badge>{t.journal}</Badge></td><td>{fmtDate(t.value_date)}</td>
                      <td>{t.description}{t.reverses_entry_id && <Badge tone="amber">Contrepassation</Badge>}</td>
                      <td className={`num ${t.direction === "CREDIT" ? "strong-green" : ""}`}>{fmtMoney(t.amount, 2)}</td>
                      <td className="small muted">{t.reference_type ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={tx.data.page}
              onPrev={stack.length ? () => { const s = [...stack]; const prev = s.pop() ?? null; setStack(s); setCursor(prev); } : undefined}
              onNext={() => { setStack([...stack, cursor]); setCursor(tx.data!.page.next_cursor); }} />
          </>
        )}
      </Card>
    </>
  );
}
