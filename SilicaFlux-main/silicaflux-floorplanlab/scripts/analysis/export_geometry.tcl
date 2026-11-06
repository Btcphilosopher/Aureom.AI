# =============================================================================
# SilicaFlux FloorplanLab -- export geometry + connectivity from OpenDB.
#
# env: FLP_ODB, FLP_SDC, FLP_OUT, FLP_GROUPS, FLP_BINS (density grid, default 64)
# writes: $FLP_OUT/geometry.json   die/core/rows, macros, pins, PDN stripes,
#                                  std-cell density grid, per-group stats
#         $FLP_OUT/connectivity.json  group-to-group nets (+HPWL), macro links
#         $FLP_OUT/cells.csv.gz     every placed instance (name,master,kind,group,x,y,w,h)
#         $FLP_OUT/<stage>.def      DEF of the exported database
# Only OpenDB data is written; no geometry is synthesised.
# =============================================================================
source [file join $::env(FLP_SCRIPTS) analysis flp_lib.tcl]
source $::env(SCRIPTS_DIR)/load.tcl
load_design $::env(FLP_ODB) $::env(FLP_SDC)
set out [flp::env FLP_OUT .]
file mkdir $out
set block [ord::get_db_block]
set dbu [$block getDefUnits]
set die [$block getDieArea]
set core [$block getCoreArea]
set nb [flp::env FLP_BINS 64]
set cx0 [$core xMin]; set cy0 [$core yMin]; set cw [expr {[$core xMax] - $cx0}]; set ch [expr {[$core yMax] - $cy0}]
set bw [expr {double($cw) / $nb}]; set bh [expr {double($ch) / $nb}]
for {set i 0} {$i < $nb * $nb} {incr i} { set dens($i) 0.0 }

# ---------------------------------------------------------------- instances
set csv [open $out/cells.csv w]
puts $csv "name,master,kind,group,x_um,y_um,w_um,h_um,orient,status"
array set g_n {}; array set g_a {}; array set g_sx {}; array set g_sy {}
array set g_x0 {}; array set g_y0 {}; array set g_x1 {}; array set g_y1 {}
array set inst_group {}
set macros {}
foreach inst [$block getInsts] {
  set m [$inst getMaster]
  set k [flp::master_kind $m]
  set name [$inst getName]
  set b [$inst getBBox]
  set w [expr {[$b xMax] - [$b xMin]}]; set h [expr {[$b yMax] - [$b yMin]}]
  set placed [$inst isPlaced]
  if {$k == "macro"} {
    set g macro
    set pins_side {}
    lappend macros [flp::jobj [list name [flp::jstr $name] master [flp::jstr [$m getName]] \
       bbox [flp::box_um $b] orient [flp::jstr [$inst getOrient]] status [flp::jstr [$inst getPlacementStatus]] \
       group [flp::jstr [flp::group_of $name]]]]
  } else {
    set g [flp::group_of $name]
  }
  set inst_group($name) $g
  puts $csv "[string map {, ;} $name],[$m getName],$k,$g,[format %.3f [flp::um [$b xMin]]],[format %.3f [flp::um [$b yMin]]],[format %.3f [flp::um $w]],[format %.3f [flp::um $h]],[$inst getOrient],[$inst getPlacementStatus]"
  if {$k == "macro" || !$placed} { continue }
  set a [expr {double($w) * $h / ($dbu * $dbu)}]
  set xc [expr {([$b xMin] + [$b xMax]) / 2.0}]; set yc [expr {([$b yMin] + [$b yMax]) / 2.0}]
  set ix [expr {int(($xc - $cx0) / $bw)}]; set iy [expr {int(($yc - $cy0) / $bh)}]
  if {$ix >= 0 && $ix < $nb && $iy >= 0 && $iy < $nb} {
    set dens([expr {$iy * $nb + $ix}]) [expr {$dens([expr {$iy * $nb + $ix}]) + $a}]
  }
  if {![info exists g_n($g)]} { set g_n($g) 0; set g_a($g) 0.0; set g_sx($g) 0.0; set g_sy($g) 0.0
    set g_x0($g) 1e30; set g_y0($g) 1e30; set g_x1($g) -1e30; set g_y1($g) -1e30 }
  incr g_n($g)
  set g_a($g) [expr {$g_a($g) + $a}]
  set g_sx($g) [expr {$g_sx($g) + $a * $xc}]; set g_sy($g) [expr {$g_sy($g) + $a * $yc}]
  set g_x0($g) [expr {min($g_x0($g), [$b xMin])}]; set g_y0($g) [expr {min($g_y0($g), [$b yMin])}]
  set g_x1($g) [expr {max($g_x1($g), [$b xMax])}]; set g_y1($g) [expr {max($g_y1($g), [$b yMax])}]
}
close $csv
catch {exec gzip -f $out/cells.csv}

set groups {}
foreach g [lsort [array names g_n]] {
  set cxg [expr {$g_sx($g) / $g_a($g) / $dbu}]; set cyg [expr {$g_sy($g) / $g_a($g) / $dbu}]
  lappend groups $g [flp::jobj [list cells $g_n($g) area_um2 [format %.2f $g_a($g)] \
     centroid_um [flp::jlist [list [format %.2f $cxg] [format %.2f $cyg]]] \
     bbox_um [flp::jlist [list [format %.2f [flp::um $g_x0($g)]] [format %.2f [flp::um $g_y0($g)]] [format %.2f [flp::um $g_x1($g)]] [format %.2f [flp::um $g_y1($g)]]]]]]
}
set grid {}
set bin_area [expr {$bw * $bh / ($dbu * $dbu)}]
for {set iy 0} {$iy < $nb} {incr iy} {
  set row {}
  for {set ix 0} {$ix < $nb} {incr ix} { lappend row [format %.4f [expr {$dens([expr {$iy * $nb + $ix}]) / $bin_area}]] }
  lappend grid [flp::jlist $row]
}

# ---------------------------------------------------------------- pins
set pins {}
set clock_pin "null"
foreach bt [$block getBTerms] {
  set sig [$bt getSigType]
  if {$sig == "POWER" || $sig == "GROUND"} { continue }
  foreach bp [$bt getBPins] {
    foreach b [$bp getBoxes] {
      set e [flp::jobj [list name [flp::jstr [$bt getName]] dir [flp::jstr [$bt getIoType]] sig [flp::jstr $sig] \
         layer [flp::jstr [[$b getTechLayer] getName]] bbox [flp::box_um $b] edge [flp::jstr [flp::edge_of $b]]]]
      lappend pins $e
      if {[$bt getName] == [flp::env FLP_CLOCK_PORT clk]} { set clock_pin $e }
    }
  }
}

# ---------------------------------------------------------------- PDN stripes
set stripes {}
set rails {}
foreach net [$block getNets] {
  set sig [$net getSigType]
  if {$sig != "POWER" && $sig != "GROUND"} { continue }
  array unset rc
  foreach sw [$net getSWires] {
    foreach w [$sw getWires] {
      if {[$w isVia]} { continue }
      set ln [[$w getTechLayer] getName]
      if {[$w getWireShapeType] == "FOLLOWPIN"} {
        if {![info exists rc($ln)]} { set rc($ln) 0 }
        incr rc($ln)
        continue
      }
      lappend stripes [flp::jobj [list net [flp::jstr [$net getName]] layer [flp::jstr $ln] \
          shape [flp::jstr [$w getWireShapeType]] bbox [flp::box_um $w]]]
    }
  }
  foreach ln [array names rc] { lappend rails [flp::jobj [list net [flp::jstr [$net getName]] layer [flp::jstr $ln] count $rc($ln)]] }
}

# ---------------------------------------------------------------- connectivity
array set pair_n {}; array set pair_l {}
array set mac_n {}
foreach net [$block getNets] {
  set sig [$net getSigType]
  if {$sig == "POWER" || $sig == "GROUND" || $sig == "CLOCK"} { continue }
  set its [$net getITerms]
  if {[llength $its] > 64} { continue }
  set gs {}
  set x0 1e30; set y0 1e30; set x1 -1e30; set y1 -1e30; set k 0
  foreach it $its {
    set inst [$it getInst]
    set nm [$inst getName]
    set g $inst_group($nm)
    if {$g == "macro"} { set g [expr {[string match *u_tile* $nm] ? "sram_tspm" : "sram_main"}] }
    if {[lsearch $gs $g] < 0} { lappend gs $g }
    if {[$inst isPlaced]} {
      set b [$inst getBBox]
      set xc [expr {([$b xMin] + [$b xMax]) / 2.0}]; set yc [expr {([$b yMin] + [$b yMax]) / 2.0}]
      if {[[$inst getMaster] getType] == "BLOCK"} {
        # macro: use the pin's own location (more meaningful than the macro centre)
        set bb [$it getBBox]
        set xc [expr {([$bb xMin] + [$bb xMax]) / 2.0}]; set yc [expr {([$bb yMin] + [$bb yMax]) / 2.0}]
      }
      set x0 [expr {min($x0,$xc)}]; set y0 [expr {min($y0,$yc)}]; set x1 [expr {max($x1,$xc)}]; set y1 [expr {max($y1,$yc)}]
      incr k
    }
  }
  if {[llength $gs] < 2} { continue }
  set hp [expr {$k >= 2 ? (($x1 - $x0) + ($y1 - $y0)) / double($dbu) : 0.0}]
  set gs [lsort $gs]
  for {set i 0} {$i < [llength $gs]} {incr i} {
    for {set j [expr {$i + 1}]} {$j < [llength $gs]} {incr j} {
      set key "[lindex $gs $i]|[lindex $gs $j]"
      if {![info exists pair_n($key)]} { set pair_n($key) 0; set pair_l($key) 0.0 }
      incr pair_n($key)
      set pair_l($key) [expr {$pair_l($key) + $hp}]
    }
  }
}
set pairs {}
foreach key [lsort [array names pair_n]] {
  lassign [split $key |] a b
  lappend pairs [flp::jobj [list a [flp::jstr $a] b [flp::jstr $b] nets $pair_n($key) hpwl_um [format %.1f $pair_l($key)]]]
}

# ---------------------------------------------------------------- rows
set nrows 0
foreach row [$block getRows] { incr nrows }

flp::write_file $out/geometry.json [flp::jobj [list \
  source_odb [flp::jstr $::env(FLP_ODB)] dbu $dbu die_um [flp::box_um $die] core_um [flp::rect_um $core] rows $nrows \
  macros [flp::jlist $macros] io_pins [flp::jlist $pins] clock_pin $clock_pin \
  pdn_stripes [flp::jlist $stripes] pdn_followpin_rails [flp::jlist $rails] \
  density_grid [flp::jobj [list bins $nb bin_w_um [format %.3f [expr {$bw / $dbu}]] bin_h_um [format %.3f [expr {$bh / $dbu}]] \
       origin_um [flp::jlist [list [flp::um $cx0] [flp::um $cy0]]] utilisation [flp::jlist $grid]]] \
  groups [flp::jobj $groups]]]
flp::write_file $out/connectivity.json [flp::jobj [list source_odb [flp::jstr $::env(FLP_ODB)] \
  note [flp::jstr "nets (<=64 pins, excl. power/clock) touching >=2 logical groups; HPWL from placed pin/cell centres"] \
  pairs [flp::jlist $pairs]]]
set defname [file rootname [file tail $::env(FLP_ODB)]]
write_def $out/$defname.def
catch {exec gzip -f $out/$defname.def}
puts "FLP: exported geometry, connectivity, cells and DEF for $::env(FLP_ODB)"
