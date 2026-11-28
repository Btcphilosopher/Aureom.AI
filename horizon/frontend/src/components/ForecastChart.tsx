"use client";
import { useMemo, useRef, useState } from "react";
import { fmtAmount, fmtDate, monthLabel, num, parseDate } from "@/lib/format";

export type ChartData = {
  as_of: string;
  horizon_days: number;
  observed: { date: string; value: string }[];
  forecast: { date: string; value: string }[];
  band: { date: string; low: string; high: string }[];
  band_method: string;
};

const W = 760;
const H = 285;
const M = { l: 58, r: 16, t: 34, b: 30 };

function niceStep(range: number): number {
  const raw = range / 5;
  const pow = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / pow;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * pow;
}

/** Graphique SVG : historique (trait plein), prévision centrale (tirets), fourchette (enveloppe des scénarios). */
export default function ForecastChart({ data }: { data: ChartData }) {
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<{ x: number; y: number; label: string } | null>(null);

  const g = useMemo(() => {
    const all = [...data.observed.map((p) => p.date), ...data.forecast.map((p) => p.date)];
    const t0 = parseDate(all[0]).getTime();
    const t1 = parseDate(all[all.length - 1]).getTime();
    const vals = [
      ...data.observed.map((p) => num(p.value)), ...data.forecast.map((p) => num(p.value)),
      ...data.band.flatMap((b) => [num(b.low), num(b.high)]),
    ];
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = (hi - lo) * 0.12 || 1_000_000;
    lo -= pad; hi += pad;
    const step = niceStep(hi - lo);
    lo = Math.floor(lo / step) * step;
    hi = Math.ceil(hi / step) * step;
    const x = (d: string) => M.l + ((parseDate(d).getTime() - t0) / Math.max(1, t1 - t0)) * (W - M.l - M.r);
    const y = (v: number) => M.t + (1 - (v - lo) / (hi - lo)) * (H - M.t - M.b);
    const ticks: number[] = [];
    for (let v = lo; v <= hi + 1; v += step) ticks.push(v);
    // libellés de l'axe des abscisses
    const xt: { x: number; label: string }[] = [];
    if (data.horizon_days <= 7) {
      all.filter((_, i) => i % 3 === 0).forEach((d) => xt.push({ x: x(d), label: parseDate(d).toLocaleDateString("fr-FR", { day: "2-digit", month: "short" }) }));
    } else {
      const seen = new Set<string>();
      all.forEach((d) => {
        const dt = parseDate(d);
        const key = `${dt.getFullYear()}-${dt.getMonth()}`;
        if (!seen.has(key) && dt.getDate() <= 7 && x(d) > M.l + 20) { seen.add(key); xt.push({ x: x(d), label: monthLabel(dt) }); }
        else seen.add(key);
      });
    }
    const line = (pts: { date: string; value: string }[]) => pts.map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${y(num(p.value)).toFixed(1)}`).join(" ");
    const band = data.band.length
      ? `M${data.band.map((b) => `${x(b.date).toFixed(1)},${y(num(b.high)).toFixed(1)}`).join(" L")} L${[...data.band].reverse().map((b) => `${x(b.date).toFixed(1)},${y(num(b.low)).toFixed(1)}`).join(" L")} Z`
      : "";
    const obsArea = data.observed.length
      ? `${line(data.observed)} L${x(data.observed[data.observed.length - 1].date).toFixed(1)},${(H - M.b).toFixed(1)} L${x(data.observed[0].date).toFixed(1)},${(H - M.b).toFixed(1)} Z`
      : "";
    return { x, y, ticks, xt, obs: line(data.observed), fc: line(data.forecast), band, obsArea, bx: x(data.as_of) };
  }, [data]);

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = ref.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const pts = [...data.observed.map((p) => ({ ...p, kind: "Observé" })), ...data.forecast.slice(1).map((p) => ({ ...p, kind: "Prévision centrale" }))];
    let best = pts[0];
    for (const p of pts) if (Math.abs(g.x(p.date) - px) < Math.abs(g.x(best.date) - px)) best = p;
    const b = data.band.find((z) => z.date === best.date);
    setHover({
      x: (g.x(best.date) / W) * rect.width, y: (g.y(num(best.value)) / H) * rect.height,
      label: `${fmtDate(best.date)} · ${best.kind} : ${fmtAmount(best.value, "EUR", 0)}${b && best.kind !== "Observé" ? ` · fourchette ${fmtAmount(b.low, "EUR", 0)} – ${fmtAmount(b.high, "EUR", 0)}` : ""}`,
    });
  };

  return (
    <div className="chart-wrap">
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} width="100%" role="img" onMouseMove={onMove} onMouseLeave={() => setHover(null)}
        aria-label={`Prévision de trésorerie sur ${data.horizon_days} jours : historique observé jusqu'au ${fmtDate(data.as_of)}, puis prévision centrale et fourchette de scénarios`}
        data-testid="forecast-chart">
        <text x={M.l - 40} y={M.t - 16} fontSize="12" fill="#4a5868">M€</text>
        {g.ticks.map((v) => (
          <g key={v}>
            <line x1={M.l} x2={W - M.r} y1={g.y(v)} y2={g.y(v)} stroke="#e7ebef" />
            <text x={M.l - 10} y={g.y(v) + 4} fontSize="12" textAnchor="end" fill="#4a5868">{(v / 1_000_000).toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</text>
          </g>
        ))}
        <line x1={M.l} x2={M.l} y1={M.t} y2={H - M.b} stroke="#c9d2db" />
        <path d={g.obsArea} fill="#00915a" opacity="0.09" />
        <path d={g.band} fill="#bfe8d3" opacity="0.75" />
        <path d={g.obs} fill="none" stroke="#00764a" strokeWidth="2.2" />
        <path d={g.fc} fill="none" stroke="#00764a" strokeWidth="2" strokeDasharray="6 5" />
        <line x1={g.bx} x2={g.bx} y1={M.t - 8} y2={H - M.b} stroke="#3b4a5a" strokeDasharray="4 4" />
        <g>
          <rect x={g.bx - 92} y={M.t - 28} width={76} height={20} rx={10} fill="#eef1f4" />
          <text x={g.bx - 54} y={M.t - 14} fontSize="12" textAnchor="middle" fill="#142233">Observé</text>
          <rect x={g.bx + 16} y={M.t - 28} width={80} height={20} rx={10} fill="#e8f6ef" />
          <text x={g.bx + 56} y={M.t - 14} fontSize="12" textAnchor="middle" fill="#0b4d33">Prévision</text>
        </g>
        {g.xt.map((t, i) => (<text key={i} x={t.x} y={H - 8} fontSize="12.5" textAnchor="middle" fill="#142233">{t.label}</text>))}
      </svg>
      {hover && <div className="chart-tip" style={{ left: Math.min(hover.x + 12, 420), top: Math.max(hover.y - 40, 0) }}>{hover.label}</div>}
      <div className="chart-legend">
        <span><i className="lg-line" />Solde de trésorerie (observé)</span>
        <span><i className="lg-dash" />Prévision (scénario central)</span>
        <span><i className="lg-band" />Fourchette (enveloppe des scénarios)</span>
      </div>
      <p className="band-method" data-testid="band-method">{data.band_method}</p>
    </div>
  );
}
