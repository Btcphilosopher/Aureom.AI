"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Emblem from "@/components/Emblem";
import Paris from "@/components/Paris";
import { ApiError, apiFetch, errorText } from "@/lib/api";

type DemoUser = { email: string; full_name: string; title: string; organization: string; current_totp: string };

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [challenge, setChallenge] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [demo, setDemo] = useState<{ enabled: boolean; password_hint?: string; users: DemoUser[]; notice?: string } | null>(null);

  useEffect(() => {
    const load = () => apiFetch("/v1/auth/demo-users").then(setDemo).catch(() => setDemo(null));
    load();
    const t = setInterval(load, 10_000);
    return () => clearInterval(t);
  }, []);

  const login = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const r = await apiFetch<{ challenge_id: string }>("/v1/auth/login", { body: { email, password } });
      setChallenge(r.challenge_id);
    } catch (e2) {
      setErr(errorText(e2));
    } finally {
      setBusy(false);
    }
  };
  const mfa = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await apiFetch("/v1/auth/mfa", { body: { challenge_id: challenge, code: code.trim() } });
      router.replace("/");
    } catch (e2) {
      setErr(errorText(e2));
      if (e2 instanceof ApiError && e2.code === "MFA_CHALLENGE_INVALID") setChallenge(null);
    } finally {
      setBusy(false);
    }
  };
  const currentDemoCode = demo?.users.find((u) => u.email === email.trim().toLowerCase())?.current_totp;

  return (
    <div className="login-page">
      <div className="login-left">
        <div>
          <div className="row"><Emblem size={42} /><span className="wordmark" style={{ color: "#fff" }}>HORIZON</span></div>
          <span className="env-pill" style={{ marginLeft: 0, display: "inline-block", marginTop: 18 }}>ENVIRONNEMENT DE DÉMONSTRATION</span>
          <h1>La maîtrise de votre trésorerie.</h1>
          <p>Poste de travail de banque d’entreprise : soldes explicables, paiements contrôlés, prévisions transparentes et responsabilité identifiable à chaque étape.</p>
          <p className="small">Concept indépendant · Données synthétiques · Aucun service bancaire réel. Ce prototype n’est le produit officiel d’aucun établissement et n’accède à aucun système bancaire.</p>
        </div>
        <div style={{ maxWidth: 360 }}><Paris /></div>
      </div>
      <div className="login-right">
        <div className="login-card">
          <h2 style={{ marginTop: 0 }}>Connexion</h2>
          <p className="muted small">Authentification organisationnelle (identifiants fictifs) puis second facteur TOTP.</p>
          {!challenge ? (
            <form onSubmit={login} className="stack" style={{ gap: 12 }}>
              <label className="field"><span>Adresse électronique</span>
                <input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required data-testid="login-email" /></label>
              <label className="field"><span>Mot de passe</span>
                <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required data-testid="login-password" /></label>
              <button className="btn btn-primary" disabled={busy} data-testid="login-submit">Continuer</button>
            </form>
          ) : (
            <form onSubmit={mfa} className="stack" style={{ gap: 12 }}>
              <label className="field"><span>Code de vérification (6 chiffres)</span>
                <input inputMode="numeric" pattern="\d{6}" maxLength={6} autoFocus value={code} onChange={(e) => setCode(e.target.value)} required data-testid="login-code" /></label>
              {currentDemoCode && <p className="demo-hint">Démonstration uniquement — code TOTP courant : <code>{currentDemoCode}</code></p>}
              <div className="row">
                <button type="button" className="btn btn-ghost" onClick={() => setChallenge(null)}>Retour</button>
                <button className="btn btn-primary" disabled={busy} data-testid="login-mfa-submit">Vérifier</button>
              </div>
            </form>
          )}
          {err && <p className="error-text" role="alert">{err}</p>}
          <p className="small muted">Ne saisissez jamais de véritables identifiants bancaires dans ce prototype.</p>
        </div>
        {demo?.enabled && (
          <div className="login-card" data-testid="demo-users">
            <h3 style={{ marginTop: 0 }}>Utilisateurs fictifs de démonstration</h3>
            <p className="small muted">{demo.notice} Mot de passe commun : <code>{demo.password_hint}</code>. Les codes TOTP ci-dessous ne sont affichés que dans l’environnement de démonstration.</p>
            <table className="demo-users">
              <tbody>
                {demo.users.map((u) => (
                  <tr key={u.email}>
                    <td><strong>{u.full_name}</strong><br /><span className="muted small">{u.title} — {u.organization}</span></td>
                    <td className="mono">{u.current_totp}</td>
                    <td className="right">
                      <button className="btn btn-ghost btn-sm" onClick={() => { setEmail(u.email); setPassword(demo.password_hint ?? ""); setChallenge(null); }}>Utiliser</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
