# =============================================================================
# SilicaFlux FloorplanLab -- preliminary PDN for IHP SG13G2 (design-level PDN_TCL)
#
# Derived from (a) ORFS ab2aaf0f flow/platforms/ihp-sg13g2/pdn.tcl (std-cell
# rails Metal1 0.44/7.56, Metal5 + TopMetal1 straps/ring) and (b) the macro
# methodology of ORFS d0e5b3c flow/designs/ihp-sg13g2/i2c-gpio-expander/pdn.tcl
# (global-connect the macro PG pins, a -macro grid that connects the macro's
# Metal4 PG pins upward).  Only layers present in sg13g2_tech.lef are used and
# every width/pitch is passed in by FloorplanLab after validation against the
# tech LEF (python/floorplanlab/validate.py).  PRELIMINARY: no EM/IR signoff.
# Parameters come from environment variables FLP_PDN_* written into the run's
# config.mk by FloorplanLab (defaults = the ORFS platform values).
# =============================================================================
proc flp_env {name default} {
  if {[info exists ::env($name)] && $::env($name) != ""} { return $::env($name) }
  return $default
}

# ---------------------------------------------------------------- global connections
# standard cells (identical to the platform script)
add_global_connection -net {VDD} -pin_pattern {^VDD$} -power
add_global_connection -net {VDD} -pin_pattern {^VDDPE$}
add_global_connection -net {VDD} -pin_pattern {^VDDCE$}
add_global_connection -net {VSS} -pin_pattern {^VSS$} -ground
add_global_connection -net {VSS} -pin_pattern {^VSSE$}
# RM_IHPSG13 SRAM macros: VDD! (periphery), VDDARRAY! (array), VSS!
add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern {^VDD!$} -power
add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern {^VDDARRAY!$} -power
add_global_connection -net {VSS} -inst_pattern {.*} -pin_pattern {^VSS!$} -ground
global_connect

set_voltage_domain -name {CORE} -power {VDD} -ground {VSS}

# ---------------------------------------------------------------- core grid
set rail_layer   [flp_env FLP_PDN_RAIL_LAYER Metal1]
set rail_w       [flp_env FLP_PDN_RAIL_WIDTH 0.44]
set rail_p       [flp_env FLP_PDN_RAIL_PITCH 7.56]
set s1_layer     [flp_env FLP_PDN_STRAP1_LAYER Metal5]
set s1_w         [flp_env FLP_PDN_STRAP1_WIDTH 2.2]
set s1_p         [flp_env FLP_PDN_STRAP1_PITCH 75.6]
set s1_o         [flp_env FLP_PDN_STRAP1_OFFSET 13.6]
set s2_layer     [flp_env FLP_PDN_STRAP2_LAYER TopMetal1]
set s2_w         [flp_env FLP_PDN_STRAP2_WIDTH 1.8]
set s2_p         [flp_env FLP_PDN_STRAP2_PITCH 75.6]
set s2_o         [flp_env FLP_PDN_STRAP2_OFFSET 13.57]
set use_ring     [flp_env FLP_PDN_RING 1]
set ring_layers  [flp_env FLP_PDN_RING_LAYERS {Metal5 TopMetal1}]
set ring_w       [flp_env FLP_PDN_RING_WIDTH 5.0]
set ring_s       [flp_env FLP_PDN_RING_SPACING 2.0]
set ring_o       [flp_env FLP_PDN_RING_OFFSET 4.5]
set mconnect     [flp_env FLP_PDN_MACRO_CONNECT {Metal4 TopMetal1}]
set mhalo        [flp_env FLP_PDN_MACRO_HALO 0]

define_pdn_grid -name {grid} -voltage_domains {CORE}
if {$use_ring} {
  add_pdn_ring -grid {grid} -layers $ring_layers -widths $ring_w -spacings $ring_s -core_offsets $ring_o
  set ext {-extend_to_core_ring}
} else {
  set ext {}
}
add_pdn_stripe -grid {grid} -layer $rail_layer -width $rail_w -pitch $rail_p -offset 0 -followpins {*}$ext
add_pdn_stripe -grid {grid} -layer $s1_layer -width $s1_w -pitch $s1_p -offset $s1_o {*}$ext
add_pdn_stripe -grid {grid} -layer $s2_layer -width $s2_w -pitch $s2_p -offset $s2_o {*}$ext
add_pdn_connect -grid {grid} -layers [list $rail_layer $s1_layer]
add_pdn_connect -grid {grid} -layers [list $s1_layer $s2_layer]

# ---------------------------------------------------------------- SRAM macro grid
# RM_IHPSG13 PG pins are VERTICAL Metal4 stripes (checked in the LEF): VSS!
# full height, VDDARRAY! over the array, and VDD! (periphery) only ~38.8 um
# tall at the pin edge.  Vertical Metal5 straps run parallel to them, so the
# connection goes UP to horizontal TopMetal1 (ORFS d0e5b3c i2c-gpio-expander
# methodology: add_pdn_connect Metal4 -> TopMetal1).  The core TopMetal1 pitch
# (75.6 um) would cross the 38.8 um VDD! band of only some macros, so the
# macro grid adds its own dense TopMetal1 straps (pitch FLP_PDN_MACRO_STRAP_PITCH)
# over each macro; they tie into the core grid through the Metal5 straps that
# continue over the macros (-grid_over_boundary).  post_pdn.tcl then checks,
# pin NAME by pin name, that every macro PG pin has vias landing on it.
set ms_layer [flp_env FLP_PDN_MACRO_STRAP_LAYER TopMetal1]
set ms_w     [flp_env FLP_PDN_MACRO_STRAP_WIDTH 1.8]
set ms_p     [flp_env FLP_PDN_MACRO_STRAP_PITCH 20.0]
set ms_o     [flp_env FLP_PDN_MACRO_STRAP_OFFSET 5.0]
set srams {}
foreach inst [[ord::get_db_block] getInsts] {
  set m [$inst getMaster]
  if {[$m getType] == "BLOCK" && [string match RM_IHPSG13_* [$m getName]]} {
    if {[lsearch $srams [$m getName]] < 0} { lappend srams [$m getName] }
  }
}
if {[llength $srams] > 0} {
  define_pdn_grid -name {sram_grid} -voltage_domains {CORE} -macro -cells $srams \
    -halo [list $mhalo $mhalo $mhalo $mhalo] -grid_over_boundary
  add_pdn_stripe -grid {sram_grid} -layer $ms_layer -width $ms_w -pitch $ms_p -offset $ms_o
  add_pdn_connect -grid {sram_grid} -layers $mconnect
  add_pdn_connect -grid {sram_grid} -layers [list $s1_layer $ms_layer]
  puts "FLP-PDN: macro grid sram_grid for cells: $srams ($ms_layer straps w=$ms_w p=$ms_p; connect $mconnect, $s1_layer-$ms_layer)"
} else {
  puts "FLP-PDN: no RM_IHPSG13 macros present (logic-only design)"
}
