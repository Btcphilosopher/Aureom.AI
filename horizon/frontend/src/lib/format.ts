import type { Money } from "./api";

const SYMBOLS: Record<string, string> = { EUR: "€", USD: "$", GBP: "£", CHF: "CHF", JPY: "¥" };

export function num(v: string | number | undefined | null): number {
  if (v === undefined || v === null || v === "") return 0;
  return typeof v === "number" ? v : Number(v);
}

/** « 12 400 000 € » — séparateurs fr-FR ; décimales affichées si non nulles (ou forcées). */
export function fmtAmount(amount: string | number | undefined | null, currency = "EUR", decimals?: number): string {
  const n = num(amount);
  const d = decimals ?? (Math.round(n * 100) % 100 === 0 ? 0 : 2);
  const s = n.toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
  return `${s} ${SYMBOLS[currency] ?? currency}`;
}

export function fmtMoney(m: Money | null | undefined, decimals?: number): string {
  if (!m) return "—";
  return fmtAmount(m.amount, m.currency, decimals);
}

/** « 24,80 M€ » */
export function fmtMillions(amount: string | number | undefined, currency = "EUR"): string {
  const n = num(amount) / 1_000_000;
  return `${n.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} M${SYMBOLS[currency] ?? currency}`;
}

const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

export function parseDate(iso: string): Date {
  return iso.length === 10 ? new Date(`${iso}T12:00:00`) : new Date(iso);
}

export function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  return parseDate(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

export function fmtShortDate(iso?: string | null): string {
  if (!iso) return "—";
  return parseDate(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function fmtDateTime(iso?: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function monthLabel(d: Date): string {
  const m = MONTHS[d.getMonth()];
  return `${m.charAt(0).toUpperCase()}${m.slice(1)} ${d.getFullYear()}`;
}

export const FLAGS: Record<string, string> = { FR: "🇫🇷", DE: "🇩🇪", IT: "🇮🇹", GB: "🇬🇧", JP: "🇯🇵", US: "🇺🇸", ES: "🇪🇸" };
