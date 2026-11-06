# =============================================================================
# SilicaFlux FloorplanLab -- preliminary PDN for SKY130 sky130_fd_sc_hd + OpenRAM
#
# Core grid = ORFS ab2aaf0f flow/platforms/sky130hd/pdn.tcl (met1 rails 0.48 /
# 5.44, met4 + met5 straps).  OpenRAM sky130_sram_1rw1r_128x256_8 exposes its
# vdd/gnd as met3 rings; the macro grid adds met4 straps over each macro and
# connects met3 -> met4 -> met5.  Parameters via FLP_PDN_* (validated).
# PRELIMINARY: no EM/IR signoff.
# =============================================================================
proc flp_env {name default} {
  if {[info exists ::env($name)] && $::env($name) != ""} { return $::env($name) }
  return $default
}
foreach {pat net type} {^VDD$ VDD -power ^VDDPE$ VDD {} ^VDDCE$ VDD {} VPWR VDD {} VPB VDD {}
                        ^VSS$ VSS -ground ^VSSE$ VSS {} VGND VSS {} VNB VSS {}} {
  add_global_connection -net $net -inst_pattern {.*} -pin_pattern $pat {*}$type
}
add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern {^vdd$} -power
add_global_connection -net {VSS} -inst_pattern {.*} -pin_pattern {^gnd$} -ground
global_connect
set_voltage_domain -name {CORE} -power {VDD} -ground {VSS}

set rail_layer [flp_env FLP_PDN_RAIL_LAYER met1]
set s1_layer   [flp_env FLP_PDN_STRAP1_LAYER met4]
set s2_layer   [flp_env FLP_PDN_STRAP2_LAYER met5]
define_pdn_grid -name {grid} -voltage_domains {CORE}
set ext {}
if {[flp_env FLP_PDN_RING 0]} {
  add_pdn_ring -grid {grid} -layers [flp_env FLP_PDN_RING_LAYERS {met4 met5}] \
    -widths [flp_env FLP_PDN_RING_WIDTH 5.0] -spacings [flp_env FLP_PDN_RING_SPACING 2.0] \
    -core_offsets [flp_env FLP_PDN_RING_OFFSET 2.0]
  set ext {-extend_to_core_ring}
}
add_pdn_stripe -grid {grid} -layer $rail_layer -width [flp_env FLP_PDN_RAIL_WIDTH 0.48] \
  -pitch [flp_env FLP_PDN_RAIL_PITCH 5.44] -offset 0 -followpins {*}$ext
add_pdn_stripe -grid {grid} -layer $s1_layer -width [flp_env FLP_PDN_STRAP1_WIDTH 1.6] \
  -pitch [flp_env FLP_PDN_STRAP1_PITCH 27.14] -offset [flp_env FLP_PDN_STRAP1_OFFSET 13.57] {*}$ext
add_pdn_stripe -grid {grid} -layer $s2_layer -width [flp_env FLP_PDN_STRAP2_WIDTH 1.6] \
  -pitch [flp_env FLP_PDN_STRAP2_PITCH 27.2] -offset [flp_env FLP_PDN_STRAP2_OFFSET 13.6] {*}$ext
add_pdn_connect -grid {grid} -layers [list $rail_layer $s1_layer]
add_pdn_connect -grid {grid} -layers [list $s1_layer $s2_layer]

set srams {}
foreach inst [[ord::get_db_block] getInsts] {
  set m [$inst getMaster]
  if {[$m getType] == "BLOCK" && [string match sky130_sram_* [$m getName]]} {
    if {[lsearch $srams [$m getName]] < 0} { lappend srams [$m getName] }
  }
}
if {[llength $srams] > 0} {
  set h [flp_env FLP_PDN_MACRO_HALO 2.0]
  define_pdn_grid -name {sram_grid} -voltage_domains {CORE} -macro -cells $srams \
    -halo [list $h $h $h $h] -grid_over_boundary
  add_pdn_stripe -grid {sram_grid} -layer $s1_layer -width [flp_env FLP_PDN_STRAP1_WIDTH 1.6] \
    -pitch [flp_env FLP_PDN_STRAP1_PITCH 27.14] -offset [flp_env FLP_PDN_STRAP1_OFFSET 13.57]
  add_pdn_connect -grid {sram_grid} -layers [flp_env FLP_PDN_MACRO_CONNECT {met3 met4}]
  add_pdn_connect -grid {sram_grid} -layers [list $s1_layer $s2_layer]
  puts "FLP-PDN: macro grid sram_grid for cells: $srams"
}
