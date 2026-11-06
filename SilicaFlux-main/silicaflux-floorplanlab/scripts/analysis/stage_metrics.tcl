# =============================================================================
# SilicaFlux FloorplanLab -- extract stage metrics from an ORFS OpenDB.
#
# env: SCRIPTS_DIR / PLATFORM_DIR / ... (ORFS variables, from `make print-*`)
#      FLP_ODB, FLP_SDC        ODB + SDC in RESULTS_DIR to load
#      FLP_STAGE               floorplan | pdn | place | route
#      FLP_OUT                 output directory for <stage>_metrics.json etc.
#      FLP_TIMING (0/1)        run pre-route STA (placement parasitics)
#      FLP_CHECK_PLACEMENT     run check_placement
#      FLP_POWER (0/1)         vectorless power estimate (labelled assumption)
#      FLP_GROUPS              logical group prefixes
# Output JSON is consumed by python/floorplanlab/metrics.py.
# =============================================================================
source [file join $::env(FLP_SCRIPTS) analysis flp_lib.tcl]
source $::env(SCRIPTS_DIR)/load.tcl
load_design $::env(FLP_ODB) $::env(FLP_SDC)

set stage [flp::env FLP_STAGE floorplan]
set out   [flp::env FLP_OUT .]
file mkdir $out
set block [ord::get_db_block]
set tech  [ord::get_db_tech]
set dbu   [$block getDefUnits]
set die   [$block getDieArea]
set core  [$block getCoreArea]

# ---------------------------------------------------------------- rows / sites
set nrows 0; set nsites 0; set site_name ""; set site_w 0; set site_h 0
foreach row [$block getRows] {
  incr nrows
  set nsites [expr {$nsites + [$row getSiteCount]}]
  set site [$row getSite]
  set site_name [$site getName]; set site_w [flp::um [$site getWidth]]; set site_h [flp::um [$site getHeight]]
}
set row_area [expr {$nsites * $site_w * $site_h}]

# ---------------------------------------------------------------- instances
array set kind_cnt {}; array set kind_area {}; array set grp_area {}; array set grp_cnt {}
array set status_cnt {}
set macros {}
set buf_cnt 0
foreach inst [$block getInsts] {
  set m [$inst getMaster]
  set k [flp::master_kind $m]
  set a [expr {[flp::um [$m getWidth]] * [flp::um [$m getHeight]]}]
  if {![info exists kind_cnt($k)]} { set kind_cnt($k) 0; set kind_area($k) 0.0 }
  incr kind_cnt($k)
  set kind_area($k) [expr {$kind_area($k) + $a}]
  set st [$inst getPlacementStatus]
  if {![info exists status_cnt($st)]} { set status_cnt($st) 0 }
  incr status_cnt($st)
  set name [$inst getName]
  if {$k == "macro"} {
    set pins {}
    set pg_total 0; set pg_conn 0; set sig_total 0; set sig_conn 0
    foreach it [$inst getITerms] {
      set mt [$it getMTerm]
      set net [$it getNet]
      set sig [$mt getSigType]
      if {$sig == "POWER" || $sig == "GROUND"} {
        incr pg_total
        if {$net != "NULL"} { incr pg_conn; lappend pins [flp::jobj [list pin [flp::jstr [$mt getName]] net [flp::jstr [$net getName]]]] }
      } else {
        incr sig_total
        if {$net != "NULL"} { incr sig_conn }
      }
    }
    lappend macros [flp::jobj [list name [flp::jstr $name] master [flp::jstr [$m getName]] \
      bbox [flp::box_um [$inst getBBox]] orient [flp::jstr [$inst getOrient]] status [flp::jstr $st] \
      group [flp::jstr [flp::group_of $name]] pg_pins_total $pg_total pg_pins_connected $pg_conn \
      pg_connections [flp::jlist $pins] signal_pins_total $sig_total signal_pins_connected $sig_conn]]
  } elseif {$k == "std"} {
    set g [flp::group_of $name]
    if {![info exists grp_area($g)]} { set grp_area($g) 0.0; set grp_cnt($g) 0 }
    set grp_area($g) [expr {$grp_area($g) + $a}]
    incr grp_cnt($g)
    if {[string match -nocase *buf* [$m getName]] || [string match -nocase *inv* [$m getName]]} { incr buf_cnt }
  }
}
set kinds {}
foreach k [lsort [array names kind_cnt]] { lappend kinds $k [flp::jobj [list count $kind_cnt($k) area_um2 [format %.3f $kind_area($k)]]] }
set groups {}
foreach g [lsort [array names grp_area]] { lappend groups $g [flp::jobj [list count $grp_cnt($g) area_um2 [format %.3f $grp_area($g)]]] }
set statuses {}
foreach s [lsort [array names status_cnt]] { lappend statuses $s $status_cnt($s) }

# ---------------------------------------------------------------- I/O pins
set pins {}
set pins_placed 0; set pins_total 0
foreach bt [$block getBTerms] {
  set sig [$bt getSigType]
  if {$sig == "POWER" || $sig == "GROUND"} { continue }
  incr pins_total
  set bps [$bt getBPins]
  set boxes {}; set layer ""; set edge ""; set pst "NONE"
  foreach bp $bps {
    set pst [$bp getPlacementStatus]
    foreach b [$bp getBoxes] {
      set layer [[$b getTechLayer] getName]
      lappend boxes [flp::box_um $b]
      set edge [flp::edge_of $b]
    }
  }
  if {[llength $boxes] > 0} { incr pins_placed }
  lappend pins [flp::jobj [list name [flp::jstr [$bt getName]] dir [flp::jstr [$bt getIoType]] \
    layer [flp::jstr $layer] edge [flp::jstr $edge] status [flp::jstr $pst] boxes [flp::jlist $boxes]]]
}

# ---------------------------------------------------------------- PDN summary
set pdn {}
foreach net [$block getNets] {
  set sig [$net getSigType]
  if {$sig != "POWER" && $sig != "GROUND"} { continue }
  array unset lw; array unset lc
  set nvia 0
  foreach sw [$net getSWires] {
    foreach w [$sw getWires] {
      if {[$w isVia]} { incr nvia; continue }
      set ln [[$w getTechLayer] getName]
      set len [expr {max([$w getDX], [$w getDY]) / double($dbu)}]
      if {![info exists lw($ln)]} { set lw($ln) 0.0; set lc($ln) 0 }
      set lw($ln) [expr {$lw($ln) + $len}]
      incr lc($ln)
    }
  }
  set layers {}
  foreach ln [lsort [array names lw]] { lappend layers $ln [flp::jobj [list shapes $lc($ln) length_um [format %.1f $lw($ln)]]] }
  set nit 0
  foreach it [$net getITerms] { incr nit }
  lappend pdn [flp::jobj [list net [flp::jstr [$net getName]] type [flp::jstr $sig] special [expr {[$net isSpecial] ? 1 : 0}] \
     iterms $nit vias $nvia layers [flp::jobj $layers]]]
}

# ---------------------------------------------------------------- placement legality
set legality "null"
if {[flp::env FLP_CHECK_PLACEMENT 0]} {
  set rpt $out/${stage}_check_placement.rpt
  if {[catch {check_placement -verbose -report_file_name $rpt} msg]} {
    set legality [flp::jobj [list ran 1 legal 0 message [flp::jstr $msg] report [flp::jstr $rpt]]]
  } else {
    set legality [flp::jobj [list ran 1 legal 1 message [flp::jstr ""] report [flp::jstr $rpt]]]
  }
}

# ---------------------------------------------------------------- HPWL (placed cells)
set hpwl 0.0
set fanout_list {}
foreach net [$block getNets] {
  set sig [$net getSigType]
  if {$sig == "POWER" || $sig == "GROUND"} { continue }
  set its [$net getITerms]
  set n [llength $its]
  if {$n > 30} { lappend fanout_list [list [$net getName] $n] }
  if {$n < 2 && [llength [$net getBTerms]] == 0} { continue }
  set x0 1e30; set y0 1e30; set x1 -1e30; set y1 -1e30; set k 0
  foreach it $its {
    set inst [$it getInst]
    if {![$inst isPlaced]} { continue }
    set b [$inst getBBox]
    set cx [expr {([$b xMin] + [$b xMax]) / 2.0}]; set cy [expr {([$b yMin] + [$b yMax]) / 2.0}]
    set x0 [expr {min($x0,$cx)}]; set y0 [expr {min($y0,$cy)}]; set x1 [expr {max($x1,$cx)}]; set y1 [expr {max($y1,$cy)}]
    incr k
  }
  foreach bt [$net getBTerms] {
    foreach bp [$bt getBPins] { foreach b [$bp getBoxes] {
      set cx [expr {([$b xMin] + [$b xMax]) / 2.0}]; set cy [expr {([$b yMin] + [$b yMax]) / 2.0}]
      set x0 [expr {min($x0,$cx)}]; set y0 [expr {min($y0,$cy)}]; set x1 [expr {max($x1,$cx)}]; set y1 [expr {max($y1,$cy)}]
      incr k
    } }
  }
  if {$k >= 2} { set hpwl [expr {$hpwl + ($x1 - $x0) + ($y1 - $y0)}] }
}
set hpwl_um [expr {$hpwl / double($dbu)}]
set hf {}
foreach f [lrange [lsort -integer -decreasing -index 1 $fanout_list] 0 19] {
  lappend hf [flp::jobj [list net [flp::jstr [lindex $f 0]] fanout [lindex $f 1]]]
}

# ---------------------------------------------------------------- timing (pre-route)
set timing "null"
if {[flp::env FLP_TIMING 0]} {
  estimate_parasitics -placement
  set wns [sta::worst_slack -max]
  set tns [sta::total_negative_slack -max]
  set whs [sta::worst_slack -min]
  set ths [sta::total_negative_slack -min]
  report_checks -path_delay max -group_count 10 -endpoint_count 1 -fields {slew cap input_pins fanout} -digits 3 > $out/${stage}_timing_setup.rpt
  report_checks -path_delay min -group_count 5 -endpoint_count 1 -fields {slew cap input_pins fanout} -digits 3 > $out/${stage}_timing_hold.rpt
  report_checks -path_delay max -group_count 50 -format end > $out/${stage}_timing_endpoints.rpt
  report_checks -path_delay max -to [all_outputs] -group_count 3 -digits 3 > $out/${stage}_timing_outputs.rpt
  # register(+macro)-to-register paths only: the I/O-budget paths above can mask the internal critical path
  report_checks -path_delay max -from [all_registers -clock_pins] -to [all_registers -data_pins] \
    -group_count 10 -endpoint_count 1 -fields {slew cap input_pins fanout} -digits 3 > $out/${stage}_timing_reg2reg.rpt
  report_check_types -max_slew -max_capacitance -max_fanout -violators > $out/${stage}_drv.rpt
  report_clock_properties > $out/${stage}_clocks.rpt
  set clk_period [get_property [get_clocks clk] period]
  set timing [flp::jobj [list label [flp::jstr "PRE-ROUTE TIMING (placement parasitics, ideal clocks, corner [flp::env FLP_CORNER typ])"] \
    wns_ns [flp::jnum [format %.4f $wns]] tns_ns [flp::jnum [format %.4f $tns]] \
    whs_ns [flp::jnum [format %.4f $whs]] ths_ns [flp::jnum [format %.4f $ths]] \
    clock_period_ns [flp::jnum $clk_period]]]
}

# ---------------------------------------------------------------- power (labelled)
set power "null"
if {[flp::env FLP_POWER 0]} {
  set act [flp::env FLP_POWER_INPUT_ACTIVITY 0.1]
  set_power_activity -input -activity $act
  report_power > $out/${stage}_power.rpt
  set power [flp::jobj [list label [flp::jstr "VECTORLESS ESTIMATE: no switching activity file; input activity $act propagated by OpenSTA; ideal clock network; not a measured or signed-off power"] \
     report [flp::jstr $out/${stage}_power.rpt] input_activity $act]]
}

# ---------------------------------------------------------------- output
set json [flp::jobj [list \
  stage [flp::jstr $stage] odb [flp::jstr $::env(FLP_ODB)] \
  dbu $dbu die_um [flp::box_um $die] core_um [flp::rect_um $core] \
  rows $nrows sites $nsites site [flp::jstr $site_name] site_w_um $site_w site_h_um $site_h row_area_um2 [format %.3f $row_area] \
  instance_kinds [flp::jobj $kinds] std_cell_groups [flp::jobj $groups] placement_status [flp::jobj $statuses] \
  buffers_inverters $buf_cnt \
  macros [flp::jlist $macros] io_pins [flp::jlist $pins] io_pins_total $pins_total io_pins_placed $pins_placed \
  pdn_nets [flp::jlist $pdn] hpwl_um [format %.1f $hpwl_um] high_fanout_nets [flp::jlist $hf] \
  placement_check $legality timing $timing power $power]]
flp::write_file $out/${stage}_metrics.json $json
puts "FLP: wrote $out/${stage}_metrics.json"
