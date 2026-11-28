import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 22, ...rest }: P) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.6,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    ...rest,
  };
}

export const IconHome = (p: P) => (<svg {...base(p)}><path d="M3 11.5 12 4l9 7.5" /><path d="M5.5 10v9.5h13V10" /><path d="M10 19.5v-5h4v5" /></svg>);
export const IconDatabase = (p: P) => (<svg {...base(p)}><ellipse cx="12" cy="6" rx="7.5" ry="3" /><path d="M4.5 6v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6" /><path d="M4.5 12v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6" /></svg>);
export const IconTransfer = (p: P) => (<svg {...base(p)}><path d="M4 8h15l-4-4" /><path d="M20 16H5l4 4" /></svg>);
export const IconBars = (p: P) => (<svg {...base(p)}><path d="M5 20v-6M10 20V10M15 20V6M20 20V3" /></svg>);
export const IconLayers = (p: P) => (<svg {...base(p)}><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 13 9 5 9-5" /><path d="m3 17.5 9 5 9-5" opacity=".6" /></svg>);
export const IconExchange = (p: P) => (<svg {...base(p)}><path d="M20 9a8 8 0 0 0-14.3-3.5L4 7.5" /><path d="M4 3.5v4h4" /><path d="M4 15a8 8 0 0 0 14.3 3.5l1.7-2" /><path d="M20 20.5v-4h-4" /></svg>);
export const IconGlobe = (p: P) => (<svg {...base(p)}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3Z" /></svg>);
export const IconDoc = (p: P) => (<svg {...base(p)}><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4M9 12h6M9 15.5h6M9 19h4" /></svg>);
export const IconGear = (p: P) => (<svg {...base(p)}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" /></svg>);
export const IconSearch = (p: P) => (<svg {...base(p)}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></svg>);
export const IconBell = (p: P) => (<svg {...base(p)}><path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15Z" /><path d="M10 20.5a2 2 0 0 0 4 0" /></svg>);
export const IconUser = (p: P) => (<svg {...base(p)}><circle cx="12" cy="12" r="10" fill="currentColor" stroke="none" /><circle cx="12" cy="10" r="3.4" fill="#fff" stroke="none" /><path d="M5.6 18.6c1.4-2.4 3.6-3.6 6.4-3.6s5 1.2 6.4 3.6" stroke="#fff" strokeWidth="1.8" /></svg>);
export const IconCalendar = (p: P) => (<svg {...base(p)}><rect x="3.5" y="5" width="17" height="15.5" rx="2" /><path d="M3.5 10h17M8 3v4M16 3v4" /></svg>);
export const IconPlus = (p: P) => (<svg {...base(p)}><path d="M12 5v14M5 12h14" /></svg>);
export const IconWallet = (p: P) => (<svg {...base(p)}><path d="M4 7.5h14.5a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a1.5 1.5 0 0 1-1.5-1.5V7a2 2 0 0 1 2-2h10" /><path d="M16 13.8h4.5" /></svg>);
export const IconChecklist = (p: P) => (<svg {...base(p)}><path d="M14 20H6V3h9l4 4v6" /><path d="M9 8h6M9 11.5h5M9 15h3" /><path d="m14.5 18 2 2 4-4.5" /></svg>);
export const IconInbox = (p: P) => (<svg {...base(p)}><path d="M12 3v10m0 0-4-4m4 4 4-4" /><path d="M3.5 13v5.5A1.5 1.5 0 0 0 5 20h14a1.5 1.5 0 0 0 1.5-1.5V13" /></svg>);
export const IconWarning = (p: P) => (<svg {...base(p)}><path d="M12 3.5 2.5 20h19Z" /><path d="M12 10v4.5" /><circle cx="12" cy="17.3" r=".6" fill="currentColor" /></svg>);
export const IconTrend = (p: P) => (<svg {...base(p)}><path d="m3 17 6-6 4 4 8-8" /><path d="M15 7h6v6" /></svg>);
export const IconGavel = (p: P) => (<svg {...base(p)}><path d="m14 4 6 6M11 7l6 6M12.5 5.5l-4 4 6 6 4-4" /><path d="m8.5 9.5-5.5 5.5 3 3 5.5-5.5" /></svg>);
export const IconBank = (p: P) => (<svg {...base(p)}><path d="M3 9.5 12 4l9 5.5" /><path d="M5 10v8M9 10v8M15 10v8M19 10v8M3 20.5h18" /></svg>);
export const IconCheck = (p: P) => (<svg {...base(p)}><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>);
export const IconClock = (p: P) => (<svg {...base(p)}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></svg>);
export const IconX = (p: P) => (<svg {...base(p)}><path d="M6 6l12 12M18 6 6 18" /></svg>);
export const IconQuestion = (p: P) => (<svg {...base(p)}><circle cx="12" cy="12" r="8.5" /><path d="M9.6 9.4a2.5 2.5 0 1 1 3.3 2.4c-.6.3-.9.8-.9 1.4v.6" /><circle cx="12" cy="16.8" r=".6" fill="currentColor" /></svg>);
export const IconChevron = (p: P) => (<svg {...base(p)}><path d="m9 5 7 7-7 7" /></svg>);
export const IconDots = (p: P) => (<svg {...base(p)}><circle cx="5" cy="12" r="1.3" fill="currentColor" /><circle cx="12" cy="12" r="1.3" fill="currentColor" /><circle cx="19" cy="12" r="1.3" fill="currentColor" /></svg>);
export const IconLock = (p: P) => (<svg {...base(p)}><rect x="5" y="10.5" width="14" height="10" rx="2" /><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" /></svg>);
export const IconInfo = (p: P) => (<svg {...base(p)}><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5.5" /><circle cx="12" cy="7.8" r=".6" fill="currentColor" /></svg>);
export const IconLogout = (p: P) => (<svg {...base(p)}><path d="M14 4h5v16h-5" /><path d="M10 8l-4 4 4 4M6 12h10" /></svg>);
