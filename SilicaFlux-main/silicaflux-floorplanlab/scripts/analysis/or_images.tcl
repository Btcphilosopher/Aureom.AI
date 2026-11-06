# =============================================================================
# SilicaFlux FloorplanLab -- OpenROAD-rendered images (openroad -gui, offscreen Qt).
# env: FLP_ODB (absolute path), FLP_OUT.  Each view enables exactly the display
# controls named in its file name, so every picture can be labelled precisely.
# =============================================================================
read_db $::env(FLP_ODB)
set out $::env(FLP_OUT)
set b [[ord::get_db_block] getDieArea]
set area [list [ord::dbu_to_microns [$b xMin]] [ord::dbu_to_microns [$b yMin]] \
               [ord::dbu_to_microns [$b xMax]] [ord::dbu_to_microns [$b yMax]]]
proc flp_reset {} {
  gui::set_display_controls "*" visible false
  catch {gui::set_display_controls "Heat Maps/*" visible false}
  gui::set_display_controls "Misc/Scale bar" visible true
}
proc flp_shot {name} {
  if {[catch {save_image -area $::area -width 1400 $::out/$name} msg]} {
    puts "FLP-IMG: $name failed: $msg"
  } else { puts "FLP-IMG: wrote $name" }
}
# 1. placement: std cells + macros + pins
flp_reset
gui::set_display_controls "Instances/*" visible true
gui::set_display_controls "Shape Types/Pins" visible true
flp_shot or_placement.png
# 2. OpenROAD placement-density heat map (+ macro outlines)
flp_reset
gui::set_display_controls "Instances/Macro" visible true
if {[catch {gui::set_display_controls "Heat Maps/Placement Density" visible true} m]} { puts "FLP-IMG: no density heat map: $m" }
flp_shot or_placement_density.png
# 3. PDN: special nets on the strap layers + macros
flp_reset
gui::set_display_controls "Instances/Macro" visible true
foreach l {Metal5 TopMetal1 TopMetal2 met4 met5} { catch {gui::set_display_controls "Layers/$l" visible true} }
catch {gui::set_display_controls "Nets/Power" visible true}
catch {gui::set_display_controls "Nets/Ground" visible true}
catch {gui::set_display_controls "Shape Types/Special Routing" visible true}
flp_shot or_pdn.png
exit
