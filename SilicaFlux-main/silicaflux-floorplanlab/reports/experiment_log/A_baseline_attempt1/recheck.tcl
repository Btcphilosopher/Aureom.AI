source $::env(SCRIPTS_DIR)/load.tcl
load_design 2_6_floorplan_pdn.odb 1_synth.sdc
source $::env(FLP_SCRIPTS)/orfs_hooks/post_pdn.tcl
