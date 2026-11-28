"use client";
import { useEffect, useState } from "react";

/** Lecture des paramètres d'URL côté client (évite une frontière Suspense pour useSearchParams). */
export function useQueryParam(name: string): string | null {
  const [v, setV] = useState<string | null>(null);
  useEffect(() => {
    setV(new URLSearchParams(window.location.search).get(name));
  }, [name]);
  return v;
}
