import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HORIZON — Banque d’entreprise et trésorerie (démonstration)",
  description: "Prototype indépendant de poste de travail de trésorerie. Données synthétiques, aucun service bancaire réel.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
