# =============================================================================
# SilicaFlux FloorplanLab -- PRELIMINARY global-routing / congestion estimate.
#
# Runs FastRoute (global_route) on the placed design (3_place.odb) with the
# platform's layer range and layer adjustments (FASTROUTE_TCL).  This happens
# BEFORE CTS: the clock net is routed as an ordinary signal net and clocks stay
# ideal.  -allow_congestion lets the router finish so overflow can be MEASURED
# and reported; overflow is never hidden.  No detailed routing is performed.
# Outputs (FLP_OUT): grt_congestion.rpt (OpenROAD congestion report),
# route_guide (guides), grt_timing_setup.rpt, route_metrics.json.
# =============================================================================
source [file join $::env(FLP_SCRIPTS) analysis flp_lib.tcl]
source $::env(SCRIPTS_DIR)/load.tcl
load_design 3_place.odb 3_place.sdc
set out [flp::env FLP_OUT .]
file mkdir $out

if {[info exist ::env(FASTROUTE_TCL)]} {
  source $::env(FASTROUTE_TCL)
} else {
  set_global_routing_layer_adjustment $::env(MIN_ROUTING_LAYER)-$::env(MAX_ROUTING_LAYER) 0.5
  set_routing_layers -signal $::env(MIN_ROUTING_LAYER)-$::env(MAX_ROUTING_LAYER)
}
# Threading: left at the OpenROAD default (1), exactly like ORFS global_route.tcl.
# With set_thread_count 4 this OpenROAD build crashed (SIGSEGV in OpenSTA's
# multi-threaded GraphDelayCalc during the overflow-removal iterations, run
# B_core_area_plus attempt 1).  Arguments = ORFS defaults + -allow_congestion
# (iterations: FLP_GRT_ITERS from the run spec, default 50).
set t0 [clock seconds]
set rc [catch {global_route -congestion_iterations [flp::env FLP_GRT_ITERS 30] \
                            -congestion_report_iter_step 5 \
                            -congestion_report_file $out/grt_congestion.rpt \
                            -guide_file $out/route.guide \
                            -allow_congestion -verbose} msg]
set secs [expr {[clock seconds] - $t0}]
puts "FLP-GRT: global_route rc=$rc ($secs s) $msg"

set wl_rpt $out/grt_wirelength.rpt
set timing "null"
if {$rc == 0} {
  catch {report_wire_length -global_route -file $wl_rpt} wmsg
  estimate_parasitics -global_routing
  set wns [sta::worst_slack -max]
  set tns [sta::total_negative_slack -max]
  set whs [sta::worst_slack -min]
  report_checks -path_delay max -group_count 10 -endpoint_count 1 -fields {slew cap input_pins fanout} -digits 3 > $out/grt_timing_setup.rpt
  report_checks -path_delay min -group_count 5 -digits 3 > $out/grt_timing_hold.rpt
  set timing [flp::jobj [list label [flp::jstr "PRE-CTS TIMING with global-route parasitics (ideal clocks)"] \
     wns_ns [flp::jnum [format %.4f $wns]] tns_ns [flp::jnum [format %.4f $tns]] whs_ns [flp::jnum [format %.4f $whs]]]]
  write_db $::env(RESULTS_DIR)/flp_grt.odb
}
flp::write_file $out/route_metrics.json [flp::jobj [list \
  label [flp::jstr "PRELIMINARY GLOBAL ROUTE (pre-CTS, no detailed routing)"] \
  completed [expr {$rc == 0 ? 1 : 0}] message [flp::jstr $msg] seconds $secs \
  congestion_report [flp::jstr $out/grt_congestion.rpt] wirelength_report [flp::jstr $wl_rpt] timing $timing]]
puts "FLP: wrote $out/route_metrics.json"
