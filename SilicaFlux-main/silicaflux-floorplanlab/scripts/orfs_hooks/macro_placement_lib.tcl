# =============================================================================
# SilicaFlux FloorplanLab -- manual SRAM macro placement (MACRO_PLACEMENT_TCL).
#
# Sourced by ORFS scripts/macro_place_util.tcl in place of automatic
# macro_placement.  Uses the OpenDB API directly so the meaning of the
# coordinates is unambiguous: setLocation() puts the lower-left corner of the
# instance bounding box (after orientation) at (x, y) microns.  Each macro is
# set FIRM.  Unknown instances, masters that do not match, and macros left
# unplaced are hard errors (the step fails; nothing is silently skipped).
# =============================================================================
proc flp_place_macros {placements} {
  set block [ord::get_db_block]
  set dbu [$block getDefUnits]
  set done {}
  # OpenDB escapes '[' ']' in hierarchical instance names; match on the
  # unescaped name so configs can use plain netlist paths.
  array set byname {}
  foreach inst [$block getInsts] {
    if {[[$inst getMaster] getType] == "BLOCK"} { set byname([string map {\\ {}} [$inst getName]]) $inst }
  }
  foreach p $placements {
    lassign $p name master x y orient
    set key [string map {\\ {}} $name]
    if {![info exists byname($key)]} { utl::error FLW 9001 "FloorplanLab: macro instance '$name' not found" }
    set inst $byname($key)
    set m [[$inst getMaster] getName]
    if {$m != $master} { utl::error FLW 9002 "FloorplanLab: $name is $m, configuration says $master" }
    $inst setOrient $orient
    $inst setLocation [expr {round($x * $dbu)}] [expr {round($y * $dbu)}]
    $inst setPlacementStatus FIRM
    lappend done [$inst getName]
    puts "FLP-MACRO: $name ($master) at ($x, $y) $orient FIRM"
  }
  set missing 0
  foreach inst [$block getInsts] {
    if {[[$inst getMaster] getType] == "BLOCK" && [lsearch -exact $done [$inst getName]] < 0} {
      puts "FLP-MACRO: ERROR macro [$inst getName] has no placement"
      incr missing
    }
  }
  if {$missing > 0} { utl::error FLW 9003 "FloorplanLab: $missing macros not placed by the manual placement" }
}
