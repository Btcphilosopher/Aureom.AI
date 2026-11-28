// Emblème original HORIZON : soleil levant sur une ligne d'horizon (aucune marque tierce).
export default function Emblem({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <rect width="40" height="40" rx="6" fill="#00915a" />
      <path d="M9 25a11 11 0 0 1 22 0" fill="none" stroke="#fff" strokeWidth="2.6" />
      <path d="M6 29h28" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M20 9v4M11.5 12.5l2.4 2.8M28.5 12.5l-2.4 2.8" stroke="#bfeedb" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
