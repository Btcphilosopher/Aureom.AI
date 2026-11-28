"use client";
import { createContext, type ReactNode, useCallback, useContext, useRef, useState } from "react";
import { ApiError, apiFetch, type ApiOptions } from "@/lib/api";
import { Modal } from "./ui";
import { IconLock } from "./icons";

type Ctx = { call: <T = any>(path: string, opts?: ApiOptions) => Promise<T>; email?: string };
const StepUpContext = createContext<Ctx | null>(null);

/**
 * Exécute une requête ; si le serveur exige une réauthentification (STEP_UP_REQUIRED),
 * affiche la saisie du code MFA, appelle /v1/auth/step-up puis rejoue la requête.
 */
export function StepUpProvider({ children, email }: { children: ReactNode; email?: string }) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [demoCode, setDemoCode] = useState<string | null>(null);
  const resolver = useRef<{ ok: () => void; ko: (e: unknown) => void } | null>(null);

  const ask = useCallback(() => new Promise<void>((ok, ko) => {
    resolver.current = { ok, ko };
    setCode("");
    setErr(null);
    setOpen(true);
    apiFetch<{ users: { email: string; current_totp: string }[] }>("/v1/auth/demo-users")
      .then((d) => setDemoCode(d.users.find((u) => u.email === email)?.current_totp ?? null))
      .catch(() => setDemoCode(null));
  }), [email]);

  const call = useCallback(async <T,>(path: string, opts?: ApiOptions): Promise<T> => {
    try {
      return await apiFetch<T>(path, opts);
    } catch (e) {
      if (e instanceof ApiError && e.code === "STEP_UP_REQUIRED") {
        await ask();
        return await apiFetch<T>(path, opts);
      }
      throw e;
    }
  }, [ask]);

  const submit = async () => {
    try {
      await apiFetch("/v1/auth/step-up", { body: { code: code.trim() } });
      setOpen(false);
      resolver.current?.ok();
    } catch (e) {
      setErr(e instanceof ApiError ? `${e.message} (${e.code})` : String(e));
    }
  };
  const cancel = () => {
    setOpen(false);
    resolver.current?.ko(new ApiError(401, "STEP_UP_CANCELLED", "Réauthentification annulée"));
  };

  return (
    <StepUpContext.Provider value={{ call, email }}>
      {children}
      <Modal open={open} title="Réauthentification requise" onClose={cancel}>
        <div className="stepup">
          <IconLock size={28} />
          <p>Cette action est sensible. Saisissez le code à 6 chiffres de votre application d&apos;authentification.</p>
          <form onSubmit={(e) => { e.preventDefault(); void submit(); }}>
            <label className="field">
              <span>Code MFA</span>
              <input autoFocus inputMode="numeric" pattern="\d{6}" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)}
                aria-label="Code MFA de réauthentification" data-testid="stepup-code" />
            </label>
            {demoCode && (
              <p className="demo-hint">Démonstration uniquement — code TOTP courant de l&apos;utilisateur fictif : <code data-testid="stepup-demo-code">{demoCode}</code></p>
            )}
            {err && <p className="error-text" role="alert">{err}</p>}
            <div className="row-end">
              <button type="button" className="btn btn-ghost" onClick={cancel}>Annuler</button>
              <button type="submit" className="btn btn-primary" data-testid="stepup-submit">Confirmer</button>
            </div>
          </form>
        </div>
      </Modal>
    </StepUpContext.Provider>
  );
}

export function useApi(): Ctx {
  const c = useContext(StepUpContext);
  if (!c) return { call: apiFetch };
  return c;
}
