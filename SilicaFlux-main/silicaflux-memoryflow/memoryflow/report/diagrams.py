"""Memory-architecture block diagram (hand-laid SVG, theme-aware via CSS vars)."""
from __future__ import annotations

from memoryflow.models.hardware import SystemConfig


def _box(x, y, w, h, title, lines=(), cls="blk"):
    s = f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>'
    s += f'<text class="t" x="{x + w / 2}" y="{y + 22}" text-anchor="middle">{title}</text>'
    for i, ln in enumerate(lines):
        s += f'<text class="s" x="{x + w / 2}" y="{y + 40 + 15 * i}" text-anchor="middle">{ln}</text>'
    return s


def _path(pts, cls="ln", label="", lx=None, ly=None, anchor="start"):
    d = "M" + " L".join(f"{x},{y}" for x, y in pts)
    s = f'<path class="{cls}" d="{d}" marker-end="url(#ah{"c" if cls == "lnc" else ""})"/>'
    if label:
        s += f'<text class="s" x="{lx}" y="{ly}" text-anchor="{anchor}">{label}</text>'
    return s


def architecture_svg(cfg: SystemConfig, rtl_ref: bool = True) -> str:
    s, c, d = cfg.spm, cfg.compute, cfg.dma
    W, H = 980, 560
    p = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" '
         f'aria-label="SilicaFlux MemoryFlow memory architecture">',
         '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
         'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="ahd"/></marker>'
         '<marker id="ahc" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
         'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="ahc"/></marker></defs>',
         '<style>.blk{fill:var(--d-blk);stroke:var(--d-stroke);stroke-width:1.2}'
         '.hot{fill:var(--d-hot);stroke:var(--d-gold);stroke-width:1.6}'
         '.ext{fill:none;stroke:var(--d-stroke);stroke-width:1.2;stroke-dasharray:5 4}'
         '.t{font:600 13px var(--d-mono);fill:var(--d-text)}.s{font:10.5px var(--d-mono);fill:var(--d-text2)}'
         '.ln{stroke:var(--d-line);stroke-width:1.5;fill:none}.lnc{stroke:var(--d-cyan);stroke-width:1.7;fill:none}'
         '.ahd{fill:var(--d-line)}.ahc{fill:var(--d-cyan)}'
         '.cap{font:600 11px var(--d-mono);fill:var(--d-gold);letter-spacing:.06em}</style>']
    # left column
    p.append(_box(30, 30, 200, 62, f"SilicaFlux CPU x{c.cpu_cores}", ["L1 I/D, APB master"]))
    p.append(_box(30, 380, 200, 62, "DDR ctrl + PHY", ["licensed IP (proposed)"], "ext"))
    p.append(_box(30, 480, 200, 62, "External DRAM", [cfg.extmem.name], "ext"))
    # middle column
    p.append(_box(290, 30, 240, 62, "sf_ctrl_regs", ["perf, ECC inject, MBIST, LP"]))
    p.append(_box(290, 150, 240, 140, "sf_dma", [f"{d.channels} channels, APB regs, IRQ",
                                                 "engine 0: MEM->MEM, MM2S",
                                                 "engine 1: S2MM",
                                                 f"burst {d.burst_beats}, {d.dfifo_depth} outstanding",
                                                 f"{s.bank_width_bits}-bit beats"], "hot"))
    p.append(_box(290, 360, 240, 58, "sf_mem_router x2", ["addr decode, in-order rsp"]))
    # right column
    p.append(_box(600, 30, 160, 70, "sf_vec_unit", [f"{c.vec_lanes} x int16 lanes"]))
    p.append(_box(790, 30, 160, 70, "sf_tensor_array", [f"{c.tensor_rows}x{c.tensor_cols} int8, dbuf acc"]))
    p.append(_box(790, 160, 160, 56, "sf_reuse_buffer", ["ping-pong B replay"]))
    p.append(_box(600, 300, 350, 160, "sf_spm_banked",
                  [f"{s.capacity_bytes // 1024} KiB, {s.banks} banks x {s.bank_width_bits} b, {s.interleave}"], "hot"))
    nb = min(s.banks, 8)
    bw = (330 - 8 * (nb - 1)) / nb
    for i in range(nb):
        x = 610 + i * (bw + 8)
        p.append(f'<rect class="blk" x="{x:.1f}" y="362" width="{bw:.1f}" height="46" rx="3"/>')
        p.append(f'<text class="s" x="{x + bw / 2:.1f}" y="382" text-anchor="middle">B{i}</text>')
        p.append(f'<text class="s" x="{x + bw / 2:.1f}" y="398" text-anchor="middle">ECC</text>')
    if s.banks > 8:
        p.append(f'<text class="s" x="775" y="356" text-anchor="middle">(first 8 of {s.banks} banks shown)</text>')
    p.append('<text class="s" x="775" y="428" text-anchor="middle">RR arbitration per bank, response credits,</text>')
    p.append('<text class="s" x="775" y="443" text-anchor="middle">March C- MBIST, ECC counters + injection</text>')
    # memory-mapped paths (grey)
    p.append(_path([(230, 61), (290, 61)], "ln", "APB", 240, 55))
    p.append(_path([(258, 61), (258, 220), (290, 220)], "ln"))
    p.append(_path([(200, 92), (200, 330), (600, 330)], "ln", "CPU host (TCM) -> SPM port 2", 212, 324))
    p.append(_path([(410, 290), (410, 360)], "ln", "SF-MEM rd / wr", 418, 350))
    p.append(_path([(530, 389), (600, 389)], "ln", "ports 0/1", 538, 382))
    p.append(_path([(290, 400), (230, 410)], "ln", "EXT", 252, 396))
    p.append(_path([(130, 442), (130, 480)], "ln"))
    # accelerator streams (cyan)
    p.append(_path([(530, 165), (560, 165), (560, 112), (650, 112), (650, 100)], "lnc", "so0/so1", 564, 128))
    p.append(_path([(530, 180), (572, 180), (572, 122), (830, 122), (830, 100)], "lnc", "so2 (A)", 760, 117))
    p.append(_path([(530, 196), (790, 196)], "lnc", "so3 (B)", 700, 191))
    p.append(_path([(870, 160), (870, 100)], "lnc", "B", 876, 140))
    p.append(_path([(720, 100), (720, 140), (584, 140), (584, 250), (530, 250)], "lnc", "si0", 590, 246))
    p.append(_path([(930, 100), (930, 150), (770, 150), (770, 270), (530, 270)], "lnc", "si1 (C)", 690, 266))
    p.append(f'<text class="cap" x="290" y="{H - 30}">{"RTL REFERENCE PARAMETERISATION" if rtl_ref else "RECOMMENDED SILICAFLUX-V PROTOTYPE"}</text>')
    p.append(f'<text class="s" x="290" y="{H - 12}">cyan = accelerator streams (valid/ready/last), grey = memory-mapped (SF-MEM / APB)</text>')
    p.append("</svg>")
    return "".join(p)
