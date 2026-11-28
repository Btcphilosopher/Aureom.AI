// Illustration parisienne originale et discrète (trait fin) pour le bas de la navigation.
export default function Paris() {
  const s = { stroke: "rgba(214,232,255,0.55)", strokeWidth: 1.1, fill: "none" } as const;
  return (
    <svg viewBox="0 0 240 230" className="paris" aria-hidden="true" role="presentation">
      <defs>
        <linearGradient id="hill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#0f9a63" />
          <stop offset="1" stopColor="#087a4c" />
        </linearGradient>
      </defs>
      {/* tour en treillis */}
      <g {...s}>
        <path d="M174 30v8M171 38h6l2 26h-10z" />
        <path d="M169 64h10l5 40h-20z" />
        <path d="M164 104h20l12 62h-44z" />
        <path d="M160 128h28M157 146h34" />
        <path d="M166 166c2-12 14-12 16 0" />
        <path d="M171 42l6 20M177 42l-6 20M166 70l16 30M182 70l-16 30M158 110l32 52M190 110l-32 52" opacity=".55" />
      </g>
      {/* dôme */}
      <g {...s}>
        <path d="M58 92v-8M54 92h8" />
        <path d="M44 120c0-16 6-26 14-28 8 2 14 12 14 28z" />
        <path d="M40 120h36v8H40zM36 128h44v40H36z" />
        <path d="M44 136v26M52 136v26M60 136v26M68 136v26M74 136v26" opacity=".6" />
        <path d="M51 98c-3 6-5 14-5 22M65 98c3 6 5 14 5 22" opacity=".6" />
      </g>
      {/* immeubles */}
      <g {...s} opacity=".7">
        <path d="M86 168v-34h22v34M90 140h4M98 140h4M90 150h4M98 150h4M90 160h4M98 160h4" />
        <path d="M112 168v-26h18v26M116 148h3M123 148h3M116 158h3M123 158h3" />
        <path d="M200 168v-30h24v30M204 146h4M212 146h4M204 156h4M212 156h4" />
        <path d="M2 168v-28h24v28M6 148h4M14 148h4M6 158h4M14 158h4" />
      </g>
      {/* pont */}
      <g {...s}>
        <path d="M0 176h240" />
        <path d="M10 176c14-18 34-18 48 0M58 176c14-18 34-18 48 0M106 176c14-18 34-18 48 0M154 176c14-18 34-18 48 0M202 176c14-18 34-18 48 0" />
        <path d="M0 171h240" opacity=".6" />
      </g>
      {/* arbres */}
      <g fill="rgba(16,154,99,0.55)">
        <circle cx="16" cy="160" r="9" />
        <circle cx="28" cy="156" r="11" />
        <circle cx="226" cy="158" r="10" />
        <circle cx="140" cy="162" r="7" />
      </g>
      {/* eau et colline */}
      <g {...s} opacity=".45">
        <path d="M14 190h30M70 194h40M130 190h30M180 196h40" />
      </g>
      <path d="M0 212c50-16 120-24 240-10v28H0z" fill="url(#hill)" opacity=".9" />
    </svg>
  );
}
