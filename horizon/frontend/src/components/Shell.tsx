"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, type ReactNode, useContext, useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import Emblem from "./Emblem";
import Paris from "./Paris";
import { StepUpProvider } from "./StepUp";
import {
  IconBars, IconBell, IconDatabase, IconDoc, IconExchange, IconGear, IconGlobe, IconHome, IconLayers, IconLogout,
  IconSearch, IconTransfer, IconUser,
} from "./icons";

export type Me = {
  user: { id: string; email: string; full_name: string; title: string };
  organization: { id: string; name: string; base_currency: string };
  entities: { id: string; name: string; country_code: string; country_name: string }[];
  roles: { role: string; label: string; entity: string; entity_id: string | null; account_id: string | null; approval_limit: string | null; mandate_reference: string }[];
  permissions: string[];
};

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);
export const can = (me: Me | null, perm: string) => !!me?.permissions.includes(perm);

const NAV = [
  { href: "/", label: "Vue d’ensemble", icon: IconHome },
  { href: "/comptes", label: "Comptes", icon: IconDatabase },
  { href: "/paiements", label: "Paiements", icon: IconTransfer },
  { href: "/tresorerie", label: "Trésorerie", icon: IconBars },
  { href: "/financement", label: "Financement", icon: IconLayers },
  { href: "/change", label: "Change", icon: IconExchange },
  { href: "/commerce-international", label: "Commerce international", icon: IconGlobe },
  { href: "/documents", label: "Documents", icon: IconDoc },
  { href: "/administration", label: "Administration", icon: IconGear },
];

export default function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [alerts, setAlerts] = useState<number>(0);
  const [menu, setMenu] = useState(false);
  const [q, setQ] = useState("");

  useEffect(() => {
    apiFetch<Me>("/v1/me")
      .then(setMe)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.replace("/login");
      });
  }, [router]);
  useEffect(() => {
    if (!me || !me.permissions.includes("decision.read")) return;
    apiFetch<{ data: { is_alert: boolean }[] }>("/v1/decisions").then((d) => setAlerts(d.data.filter((x) => x.is_alert).length)).catch(() => {});
  }, [me, pathname]);

  const logout = async () => {
    try { await apiFetch("/v1/auth/logout", { method: "POST" }); } catch { /* session déjà close */ }
    router.replace("/login");
  };

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <MeContext.Provider value={me}>
      <StepUpProvider email={me?.user.email}>
        <div className="app">
          <header className="topbar">
            <div className="brand">
              <Emblem />
              <span className="wordmark">HORIZON</span>
              <span className="brand-sep" aria-hidden="true" />
              <span className="brand-sub">Banque d’entreprise &amp; trésorerie</span>
              <span className="env-pill" data-testid="env-pill">ENVIRONNEMENT DE DÉMONSTRATION</span>
            </div>
            <div className="topbar-right">
              <form className="search" role="search" onSubmit={(e) => { e.preventDefault(); router.push(`/paiements?q=${encodeURIComponent(q)}`); }}>
                <IconSearch size={18} />
                <input placeholder="Rechercher" aria-label="Rechercher un lot ou un paiement" value={q} onChange={(e) => setQ(e.target.value)} />
              </form>
              <Link href="/#decisions" className="bell" aria-label={`${alerts} alerte(s) à examiner`}>
                <IconBell size={24} />
                {alerts > 0 && <span className="bell-dot" aria-hidden="true" />}
              </Link>
              <span className="vsep" aria-hidden="true" />
              <div className="user">
                <button className="user-btn" onClick={() => setMenu((m) => !m)} aria-expanded={menu} data-testid="user-menu">
                  <span className="avatar"><IconUser size={34} /></span>
                  <span className="user-txt">
                    <strong data-testid="user-name">{me?.user.full_name ?? "…"}</strong>
                    <small>{me?.user.title ?? ""}</small>
                  </span>
                  <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" fill="none" stroke="currentColor" strokeWidth="2" /></svg>
                </button>
                {menu && me && (
                  <div className="user-menu" role="menu">
                    <div className="user-menu-head">{me.organization.name}</div>
                    <ul>{me.roles.map((r, i) => (<li key={i}>{r.label} — {r.entity}{r.approval_limit ? ` · plafond ${Number(r.approval_limit).toLocaleString("fr-FR")} €` : ""}</li>))}</ul>
                    <button className="btn btn-ghost btn-sm" onClick={logout} data-testid="logout"><IconLogout size={16} /> Se déconnecter</button>
                  </div>
                )}
              </div>
            </div>
          </header>
          <nav className="sidebar" aria-label="Navigation principale">
            <ul>
              {NAV.map(({ href, label, icon: Icon }) => (
                <li key={href}>
                  <Link href={href} className={isActive(href) ? "active" : ""} aria-current={isActive(href) ? "page" : undefined}>
                    <Icon size={24} /><span>{label}</span>
                  </Link>
                </li>
              ))}
            </ul>
            <Paris />
          </nav>
          <main className="main">
            {children}
            <footer className="foot"><span className="foot-bar" />Concept indépendant · Données synthétiques · Aucun service bancaire réel</footer>
          </main>
        </div>
      </StepUpProvider>
    </MeContext.Provider>
  );
}
