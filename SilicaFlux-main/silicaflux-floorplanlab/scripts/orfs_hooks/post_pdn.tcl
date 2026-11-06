# =============================================================================
# SilicaFlux FloorplanLab -- POST_PDN_TCL hook (sourced by ORFS scripts/pdn.tcl
# right after pdngen, before 2_6_floorplan_pdn.odb is written).
#
# ORFS ab2aaf0f has its own check_power_grid loop commented out ("CI issues");
# FloorplanLab runs the documented check here and records the result in
# $FLP_OUT/pdn_checks.json.  A failing check is RECORDED (GATE 9 fails); it is
# never reported as a pass.  The ODB is still written so the failure can be
# inspected in the GUI.
# =============================================================================
source [file join $::env(FLP_SCRIPTS) analysis flp_lib.tcl]
set out [flp::env FLP_OUT [file join $::env(RESULTS_DIR) flp]]
file mkdir $out
set block [ord::get_db_block]
set nets {}
foreach net [$block getNets] {
  set t [$net getSigType]
  if {$t != "POWER" && $t != "GROUND"} { continue }
  set name [$net getName]
  set errf $out/pdn_unconnected_$name.rpt
  file delete -force $errf
  set rc [catch {check_power_grid -net $name -error_file $errf} msg]
  set unconnected 0
  if {[file exists $errf]} {
    set fh [open $errf r]; set txt [read $fh]; close $fh
    set unconnected [regexp -all -line {^\S} $txt]
  }
  set ok [expr {$rc == 0 && $msg != 0}]
  lappend nets [flp::jobj [list net [flp::jstr $name] type [flp::jstr $t] check_rc $rc \
    result [flp::jstr $msg] unconnected_report [flp::jstr $errf] unconnected_lines $unconnected \
    connected [expr {$ok ? 1 : 0}]]]
  puts "FLP-PDN: check_power_grid -net $name -> rc=$rc result=$msg unconnected_lines=$unconnected"
}

# SRAM / macro power-pin connectivity: every PG iterm of every BLOCK must be on
# the supply net the platform profile maps it to (FLP_MACRO_PG = "pin net ...").
array set want {}
foreach {p n} [flp::env FLP_MACRO_PG ""] { set want($p) $n }
set mac {}
set bad 0
foreach inst [$block getInsts] {
  set m [$inst getMaster]
  if {[$m getType] != "BLOCK"} { continue }
  foreach it [$inst getITerms] {
    set mt [$it getMTerm]
    set st [$mt getSigType]
    if {$st != "POWER" && $st != "GROUND"} { continue }
    set pin [$mt getName]
    set net [$it getNet]
    set got [expr {$net == "NULL" ? "" : [$net getName]}]
    set exp [expr {[info exists want($pin)] ? $want($pin) : ""}]
    set ok [expr {$got != "" && ($exp == "" || $got == $exp)}]
    if {!$ok} { incr bad }
    lappend mac [flp::jobj [list inst [flp::jstr [$inst getName]] pin [flp::jstr $pin] net [flp::jstr $got] \
      expected [flp::jstr $exp] ok [expr {$ok ? 1 : 0}]]]
  }
}
# Per-pin-NAME power access: check_power_grid sees one net (VDD! and VDDARRAY!
# are both VDD), so it cannot tell whether e.g. the 38.8 um-tall VDD! periphery
# stripes received any via.  For every macro PG pin name, count the PDN vias
# whose bottom layer is the pin layer and that overlap the pin's shapes
# (master geometry transformed by the instance orientation; ORIGIN 0 0).
proc flp_xform {inst x1 y1 x2 y2} {
  set b [$inst getBBox]; set m [$inst getMaster]
  set W [$m getWidth]; set H [$m getHeight]
  set bx [$b xMin]; set by [$b yMin]
  switch [$inst getOrient] {
    R0   { return [list [expr {$bx+$x1}] [expr {$by+$y1}] [expr {$bx+$x2}] [expr {$by+$y2}]] }
    MX   { return [list [expr {$bx+$x1}] [expr {$by+$H-$y2}] [expr {$bx+$x2}] [expr {$by+$H-$y1}]] }
    MY   { return [list [expr {$bx+$W-$x2}] [expr {$by+$y1}] [expr {$bx+$W-$x1}] [expr {$by+$y2}]] }
    R180 { return [list [expr {$bx+$W-$x2}] [expr {$by+$H-$y2}] [expr {$bx+$W-$x1}] [expr {$by+$H-$y1}]] }
    default { return {} }
  }
}
array set vias {}
foreach net [$block getNets] {
  set t [$net getSigType]
  if {$t != "POWER" && $t != "GROUND"} { continue }
  foreach sw [$net getSWires] {
    foreach w [$sw getWires] {
      if {![$w isVia]} { continue }
      set bl ""
      catch { set v [$w getBlockVia]; if {$v != "NULL"} { set bl [[$v getBottomLayer] getName] } }
      if {$bl == ""} { catch { set v [$w getTechVia]; if {$v != "NULL"} { set bl [[$v getBottomLayer] getName] } } }
      lappend vias([$net getName],$bl) [list [$w xMin] [$w yMin] [$w xMax] [$w yMax]]
    }
  }
}
set pin_access {}
set pin_access_errors 0
foreach inst [$block getInsts] {
  set m [$inst getMaster]
  if {[$m getType] != "BLOCK"} { continue }
  foreach it [$inst getITerms] {
    set mt [$it getMTerm]
    set st [$mt getSigType]
    if {$st != "POWER" && $st != "GROUND"} { continue }
    set net [$it getNet]
    if {$net == "NULL"} { continue }
    set n 0; set layer ""
    foreach mp [$mt getMPins] {
      foreach g [$mp getGeometry] {
        set layer [[$g getTechLayer] getName]
        set r [flp_xform $inst [$g xMin] [$g yMin] [$g xMax] [$g yMax]]
        if {$r == "" || ![info exists vias([$net getName],$layer)]} { continue }
        lassign $r px0 py0 px1 py1
        foreach v $vias([$net getName],$layer) {
          lassign $v vx0 vy0 vx1 vy1
          if {$vx0 < $px1 && $vx1 > $px0 && $vy0 < $py1 && $vy1 > $py0} { incr n }
        }
      }
    }
    if {$n == 0} { incr pin_access_errors }
    lappend pin_access [flp::jobj [list inst [flp::jstr [$inst getName]] pin [flp::jstr [$mt getName]] \
       layer [flp::jstr $layer] vias $n ok [expr {$n > 0 ? 1 : 0}]]]
  }
}
puts "FLP-PDN: macro PG pins without any via: $pin_access_errors"
flp::write_file $out/pdn_checks.json [flp::jobj [list nets [flp::jlist $nets] macro_pg [flp::jlist $mac] macro_pg_errors $bad \
  macro_pin_access [flp::jlist $pin_access] macro_pin_access_errors $pin_access_errors]]
puts "FLP-PDN: macro PG connection errors: $bad"
