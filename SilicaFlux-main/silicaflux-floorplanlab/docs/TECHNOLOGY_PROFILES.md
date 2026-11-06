# Technology profiles

`platforms/<name>/profile.yaml` (+ `pdn.tcl`). Paths use `${ORFS_FLOW}`, `${IHP_SRAM}`,
`${PROJECT}`, `${FOUNDRY_KIT}` from `env/tools.env` / the environment; an unset variable becomes
`<UNSET:VAR>` and fails validation (never silently empty). `python -m floorplanlab platforms`
validates all of them.

| Profile | Status | Why |
|---|---|---|
| `ihp_sg13g2` | **enabled (primary)** | ORFS platform + compiled SRAM macros (RM_IHPSG13_1P_*x64) + SilicaFlux-V wrappers |
| `sky130hd` | enabled | ORFS platform + OpenRAM `sky130_sram_1rw1r_128x256_8` + SilicaFlux-V wrappers (36 macros, 26 mm² of SRAM — release-1 finding) |
| `gf180mcu` | **disabled** | ORFS ab2aaf0f gf180 has no SRAM collateral; no SilicaFlux-V GF180 wrapper; the SRAM Wrapper Library's GF180 leaf is unreachable from `sfv_soc_df` (BACKEND/MACRO not forwarded) |
| `commercial_130`, `commercial_65` | template | no foundry kit; every path is `${FOUNDRY_KIT}/<…>` and validation fails with `UNFILLED_TEMPLATE` / `PLATFORM_NOT_ENABLED` |
| `commercial_28` | template (optional future) | same |

Open-PDK caveat: the IHP and SkyWater open PDKs are used here as published in ORFS; production
tape-out needs the foundry's released design kit, its signoff decks and a qualified flow.

## Contents per profile (IHP SG13G2, values from the ORFS platform files)

| Item | Value | Source |
|---|---|---|
| Technology LEF | `sg13g2_tech.lef` (DBU 1000, manufacturing grid 0.005 µm) | ORFS ab2aaf0f |
| Std-cell LEF / GDS | `sg13g2_stdcell.lef` / `.gds` | ORFS |
| Liberty | `sg13g2_stdcell_typ_1p20V_25C.lib` (1.20 V, 25 °C) | ORFS; **slow/fast std-cell corners absent** in this revision → single-corner STA (warning in GATE 4) |
| Site | `CoreSite` 0.48 × 3.78 µm | tech LEF (cross-checked) |
| Routing layers | Metal1 V 0.48, Metal2 H 0.42, Metal3 V 0.48, Metal4 H 0.42, Metal5 V 0.48, TopMetal1 H 2.28, TopMetal2 V 4.0 (direction, pitch) | tech LEF |
| Signal routing | Metal2–Metal5, FastRoute adjustment 0.05 | `config.mk`, `fastroute.tcl` |
| Tracks | `make_tracks.tcl` (note: Metal5 x-pitch 3.48 µm → few vertical Metal5 tracks) | ORFS |
| I/O pin layers | Metal2 (H, left/right), Metal3 (V, top/bottom) | `IO_PLACER_H/V` |
| RC assumption | `setRC.tcl` per-layer R/C for `estimate_parasitics`; RCX rules present but extraction not run | ORFS |
| Tapcell / endcap | none in the library; `cut_rows` only | `tapcell.tcl`, config comment |
| Tie cells | `sg13g2_tiehi L_HI` / `sg13g2_tielo L_LO` | `config.mk` |
| Fill cells | `sg13g2_fill_{1,2,4,8}` | `config.mk` |
| Supply | VDD 1.20 V / VSS | Liberty `nom_voltage` |
| PDN | rails Metal1 0.44/7.56; ring Metal5/TopMetal1 5.0/2.0 at 4.5; straps Metal5 2.2/75.6, TopMetal1 1.8/**30.24**; SRAM grid Metal4→TopMetal1 | platform `pdn.tcl` + FloorplanLab rules |
| SRAM macros | `RM_IHPSG13_1P_{2048,1024,512,256}x64_c2_bm_bist`: LEF, Liberty typ/slow/fast, GDS, Verilog | ORFS d0e5b3c (SHA256SUMS in the collateral dir) |
| SRAM facts | 2048x64: 784.48 × 626.70 µm; 512x64: 784.48 × 191.34 µm; SYMMETRY X Y R90; 352/348 signal pins all on the R0 bottom edge (Metal2); OBS Metal1–Metal3; PG pins vertical Metal4 (VSS! 68 full-height, VDDARRAY! 64, VDD! 64 × 38.83 µm + 4 full-height) | LEF (parsed) |
| Macro PG mapping | VDD!→VDD, VDDARRAY!→VDD, VSS!→VSS (single 1.2 V domain; assumption recorded) | profile |
| Allowed orientations | R0, MX, MY, R180 (R90 legal per LEF but excluded so PG stripes stay vertical) | profile ∩ LEF |
| Physical verification | KLayout DRC deck `drc/sg13g2.lydrc`, LVS deck present — **not run** (no GDS/detailed route in scope) | ORFS |

SKY130 hd: `unithd` 0.46 × 2.72 µm, met1–met5, tt_025C_1v80 only, `tapcell -distance 14`
`sky130_fd_sc_hd__tapvpwrvgnd_1`, tie `sky130_fd_sc_hd__conb_1`, PDN met1/met4/met5 (+ OpenRAM
met3 vdd/gnd rings connected through a met4 macro grid).

## Rules enforced from the profile (never assumed)

* Site/row height/site width cross-checked against the tech LEF.
* Routing, I/O, PDN layers must exist and be ROUTING layers; min < max.
* PDN strap widths ≥ LEF min width; pitch > 2 × width; macro PG pins covered by the connect layer
  (`PDN_MACRO_PIN_COVERAGE`); macro channels ≥ vertical strap pitch + width (`PDN_CHANNEL`).
* Macro LEF ↔ Liberty pin names consistent; macro CLASS BLOCK; every LEF PG pin mapped to a net.
* Orientation list ⊆ LEF SYMMETRY.
* No numerical node scaling exists anywhere in the code: a 65 nm or 28 nm result can only come from
  a filled, enabled commercial profile with real foundry data.
