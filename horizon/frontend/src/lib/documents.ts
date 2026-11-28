"use client";
import type { ApiOptions } from "./api";

type Call = <T = any>(path: string, opts?: ApiOptions) => Promise<T>;

/** Crée un lien temporaire signé (droits revérifiés au téléchargement) puis l'ouvre. */
export async function openDocument(call: Call, id: string, onError: (e: unknown) => void) {
  try {
    const r = await call<{ url: string; ttl_seconds: number }>(`/v1/documents/${id}/links`, { method: "POST" });
    window.open(`/api${r.url}`, "_blank", "noopener");
  } catch (e) {
    onError(e);
  }
}
