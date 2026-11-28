// Client HTTP de l'API HORIZON (même origine via les réécritures Next : /api/v1/*).
// Les requêtes non-GET portent l'en-tête anti-CSRF exigé par le serveur.

export type Money = { amount: string; currency: string; minor_units?: number };

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  requestId?: string;
  constructor(status: number, code: string, message: string, details?: unknown, requestId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

export type ApiOptions = {
  method?: string;
  body?: unknown;
  form?: FormData;
  headers?: Record<string, string>;
  raw?: boolean;
};

export async function apiFetch<T = any>(path: string, opts: ApiOptions = {}): Promise<T> {
  const method = (opts.method ?? (opts.body !== undefined || opts.form ? "POST" : "GET")).toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json", ...(opts.headers ?? {}) };
  if (method !== "GET" && method !== "HEAD") headers["X-Horizon-CSRF"] = "1";
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(`/api${path}`, { method, headers, body, credentials: "same-origin", cache: "no-store" });
  if (!res.ok) {
    let code = `HTTP_${res.status}`;
    let message = res.statusText || "Erreur";
    let details: unknown;
    let rid: string | undefined;
    try {
      const j = await res.json();
      if (j?.error) {
        code = j.error.code;
        message = j.error.message;
        details = j.error.details;
        rid = j.error.request_id;
      }
    } catch {
      /* réponse non JSON */
    }
    throw new ApiError(res.status, code, message, details, rid);
  }
  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 403) return `Accès refusé — ${e.message} (${e.code})`;
    if (e.status === 401) return `Authentification requise — ${e.message} (${e.code})`;
    return `${e.message} (${e.code})`;
  }
  return e instanceof Error ? e.message : String(e);
}
