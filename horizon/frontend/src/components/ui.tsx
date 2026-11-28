"use client";
import Link from "next/link";
import { type ReactNode, useEffect } from "react";
import { ApiError, errorText } from "@/lib/api";
import { IconCheck, IconClock, IconInfo, IconLock, IconQuestion, IconWarning, IconX } from "./icons";

export function Card({ title, icon, actions, children, className = "", testId }: {
  title?: ReactNode; icon?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; testId?: string;
}) {
  return (
    <section className={`card ${className}`} data-testid={testId}>
      {(title || actions) && (
        <header className="card-head">
          <h2>{icon}<span>{title}</span></h2>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div className="page-title">
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

type Tone = "green" | "amber" | "red" | "grey" | "blue" | "navy";

export function Badge({ tone = "grey", children, icon }: { tone?: Tone; children: ReactNode; icon?: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{icon}{children}</span>;
}

const PAY_TONE: Record<string, Tone> = {
  EXECUTED: "green", COMPLETED: "green", ACTIVE: "green", RESOLVED: "green", PAID: "green", ACCEPTED_SIMULATED: "green",
  APPROVED: "blue", SCHEDULED: "blue", SUBMITTED: "blue", ACCEPTED: "blue", PROCESSING: "blue", PREPARED: "blue",
  PENDING_APPROVAL: "amber", TO_REVIEW: "amber", DRAFT: "grey", PENDING_REVIEW: "amber", OPEN: "amber",
  ACKNOWLEDGED: "amber", TO_PREPARE: "amber", SUSPENDED: "red",
  REJECTED: "red", UNKNOWN: "red", CANCELLED: "grey", EXPIRED: "grey",
};

export function StatusChip({ status, label }: { status: string; label?: string }) {
  const tone = PAY_TONE[status] ?? "grey";
  const icon =
    tone === "green" ? <IconCheck size={14} /> :
    tone === "red" ? (status === "UNKNOWN" ? <IconQuestion size={14} /> : <IconX size={14} />) :
    tone === "amber" ? <IconClock size={14} /> : tone === "blue" ? <IconClock size={14} /> : null;
  return <Badge tone={tone} icon={icon}><span data-status={status}>{label ?? status}</span></Badge>;
}

export function ErrorBox({ error, title }: { error: unknown; title?: string }) {
  if (!error) return null;
  const forbidden = error instanceof ApiError && error.status === 403;
  return (
    <div className={`alert ${forbidden ? "alert-lock" : "alert-error"}`} role="alert">
      {forbidden ? <IconLock size={18} /> : <IconWarning size={18} />}
      <div>
        <strong>{title ?? (forbidden ? "Action non autorisée" : "Erreur")}</strong>
        <div>{errorText(error)}</div>
        {error instanceof ApiError && error.details != null && typeof error.details === "object" && (
          <details><summary>Détails</summary><pre>{JSON.stringify(error.details, null, 2)}</pre></details>
        )}
      </div>
    </div>
  );
}

export function Notice({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" | "ok" }) {
  return (
    <div className={`notice notice-${tone}`}>
      {tone === "warn" ? <IconWarning size={18} /> : tone === "ok" ? <IconCheck size={18} /> : <IconInfo size={18} />}
      <div>{children}</div>
    </div>
  );
}

export function Loading({ label = "Chargement…" }: { label?: string }) {
  return <div className="loading" aria-busy="true">{label}</div>;
}

export function Modal({ open, title, onClose, children, wide }: {
  open: boolean; title: ReactNode; onClose: () => void; children: ReactNode; wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="overlay" onMouseDown={onClose}>
      <div className={`modal ${wide ? "modal-wide" : ""}`} role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined}
        onMouseDown={(e) => e.stopPropagation()}>
        <header className="modal-head"><h3>{title}</h3><button className="icon-btn" onClick={onClose} aria-label="Fermer"><IconX size={18} /></button></header>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function Drawer({ open, title, onClose, children }: { open: boolean; title: ReactNode; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="overlay overlay-right" onMouseDown={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" onMouseDown={(e) => e.stopPropagation()} data-testid="drawer">
        <header className="modal-head"><h3>{title}</h3><button className="icon-btn" onClick={onClose} aria-label="Fermer"><IconX size={18} /></button></header>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}

export function KV({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="kv">
      {items.map(([k, v], i) => (<div key={i}><dt>{k}</dt><dd>{v}</dd></div>))}
    </dl>
  );
}

export function Tabs({ tabs, value, onChange }: { tabs: { id: string; label: string }[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} className={value === t.id ? "active" : ""} onClick={() => onChange(t.id)}>{t.label}</button>
      ))}
    </div>
  );
}

export function Pager({ page, onPrev, onNext }: { page?: { total: number; next_cursor: string | null; limit: number }; onPrev?: () => void; onNext?: () => void }) {
  if (!page) return null;
  return (
    <div className="pager">
      <span>{page.total} élément(s)</span>
      <button className="btn btn-ghost btn-sm" onClick={onPrev} disabled={!onPrev}>Précédent</button>
      <button className="btn btn-ghost btn-sm" onClick={onNext} disabled={!page.next_cursor}>Suivant</button>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function A({ href, children }: { href: string; children: ReactNode }) {
  return <Link href={href} className="link">{children}</Link>;
}
