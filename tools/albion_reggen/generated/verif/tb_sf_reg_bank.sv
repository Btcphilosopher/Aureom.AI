// =============================================================================
//  tb_sf_reg_bank.sv -- self-checking testbench (model-driven)
//  GENERATED FILE -- DO NOT EDIT.  Edit the register definition instead.
//  generator       : albion_reggen 1.0.0 (definition schema 1)
//  register map   : silicaflux_regs v1.0
//  semantic hash  : 99481283139d2dc0690f688325c0631d115617fc66330be250e7a560f5e43d39
//  definition hash: 322ccd28a62e3936e355677a25425f8609977deab94841f7ce2049bcd96525ba
//  Bus protocol    : Albion Link Protocol v1 (AlbionCore sf_albion_pkg)
// =============================================================================

`default_nettype none

// Applies stim.hex and compares every output of sf_reg_bank, in every cycle, against exp.hex
// (produced by the independent Python reference model).  The AlbionCore link checker watches the
// ALP link throughout.  Plusargs: +STIM=<file> +EXP=<file> +MASK=<file>; parameter NCYC = number of cycles.
module tb_sf_reg_bank;
  parameter int NCYC = 1;
  localparam int IN_W  = 5058;
  localparam int OUT_W = 1036;
  logic clk_i;
  logic rst_ni;
  logic req_valid_i;
  logic req_ready_o;
  sf_albion_pkg::sf_req_t req_i;
  logic rsp_valid_o;
  logic rsp_ready_i;
  sf_albion_pkg::sf_rsp_t rsp_o;
  logic [31:0] dma_src_value_o;
  logic [31:0] dma_dst_value_o;
  logic [31:0] dma_len_value_o;
  logic [7:0] dma_tag_tag_o;
  logic [0:0] dma_ctrl_abort_o;
  logic [0:0] dma_start_wr_o;
  logic [0:0] dma_start_wgate_i;
  logic [0:0] dma_status_busy_i;
  logic [0:0] dma_status_active_i;
  logic [1:0] dma_status_ctl_state_i;
  logic [2:0] dma_status_eng_state_i;
  logic [7:0] dma_status_cur_tag_i;
  logic [7:0] dma_status_fifo_level_i;
  logic [31:0] dma_bytes_done_value_i;
  logic [0:0] dma_cpl_status_valid_i;
  logic [0:0] dma_cpl_status_err_i;
  logic [3:0] dma_cpl_status_code_i;
  logic [7:0] dma_cpl_status_tag_i;
  logic [31:0] dma_cpl_err_addr_value_i;
  logic [31:0] dma_cpl_bytes_value_i;
  logic [0:0] dma_cpl_pop_wr_o;
  logic [0:0] dma_cpl_pop_wgate_i;
  logic [0:0] dma_perf_ctrl_clear_pulse_o;
  logic [0:0] dma_int_enable_cpl_o;
  logic [0:0] dma_int_enable_cpl_err_o;
  logic [0:0] dma_int_enable_bus_err_o;
  logic [0:0] dma_int_enable_tag_err_o;
  logic [0:0] dma_int_status_cpl_o;
  logic [0:0] dma_int_status_cpl_set_i;
  logic [0:0] dma_int_status_cpl_err_o;
  logic [0:0] dma_int_status_cpl_err_set_i;
  logic [0:0] dma_int_status_bus_err_o;
  logic [0:0] dma_int_status_bus_err_set_i;
  logic [0:0] dma_int_status_tag_err_o;
  logic [0:0] dma_int_status_tag_err_set_i;
  logic [511:0] dma_perf_value_i;
  logic [0:0] dma_irq_o;
  logic [3:0] tensor_info_abi_version_i;
  logic [3:0] tensor_info_log2_queue_depth_i;
  logic [7:0] tensor_info_array_rows_i;
  logic [7:0] tensor_info_array_cols_i;
  logic [0:0] tensor_info_enable_quantization_i;
  logic [0:0] tensor_info_enable_double_buffering_i;
  logic [0:0] tensor_info_perf_en_i;
  logic [15:0] tensor_caps_tile_k_i;
  logic [7:0] tensor_caps_data_width_i;
  logic [7:0] tensor_caps_acc_width_i;
  logic [31:0] tensor_opbuf_value_i;
  logic [31:0] tensor_mem_lo_value_i;
  logic [31:0] tensor_mem_last_value_i;
  logic [0:0] tensor_ctrl_err_cont_o;
  logic [0:0] tensor_ctrl_err_clear_pulse_o;
  logic [0:0] tensor_ctrl_perf_clear_pulse_o;
  logic [0:0] tensor_ctrl_abort_pulse_o;
  logic [0:0] tensor_status_busy_i;
  logic [0:0] tensor_status_err_sticky_i;
  logic [0:0] tensor_status_q_full_i;
  logic [0:0] tensor_status_q_empty_i;
  logic [0:0] tensor_status_cpl_valid_i;
  logic [0:0] tensor_status_aborting_i;
  logic [0:0] tensor_status_halted_i;
  logic [3:0] tensor_status_state_i;
  logic [7:0] tensor_status_qcount_i;
  logic [7:0] tensor_status_qfree_i;
  logic [0:0] tensor_int_enable_irq_o;
  logic [0:0] tensor_int_enable_err_o;
  logic [0:0] tensor_int_enable_done_o;
  logic [0:0] tensor_int_status_irq_o;
  logic [0:0] tensor_int_status_irq_set_i;
  logic [0:0] tensor_int_status_err_o;
  logic [0:0] tensor_int_status_err_set_i;
  logic [0:0] tensor_int_status_done_o;
  logic [0:0] tensor_int_status_done_set_i;
  logic [31:0] tensor_submitted_value_i;
  logic [31:0] tensor_kmax_value_i;
  logic [383:0] tensor_desc_value_o;
  logic [0:0] tensor_doorbell_wr_o;
  logic [0:0] tensor_doorbell_wgate_i;
  logic [191:0] tensor_cpl_value_i;
  logic [0:0] tensor_cpl_pop_wr_o;
  logic [0:0] tensor_cpl_pop_wgate_i;
  logic [639:0] tensor_perf_value_i;
  logic [575:0] tensor_dma_perf_value_i;
  logic [0:0] tensor_irq_o;
  logic [3:0] vector_info_abi_version_i;
  logic [7:0] vector_info_queue_depth_i;
  logic [7:0] vector_info_rob_depth_i;
  logic [0:0] vector_info_opset_full_i;
  logic [0:0] vector_info_overlap_en_i;
  logic [0:0] vector_info_perf_en_i;
  logic [0:0] vector_ctrl_err_cont_o;
  logic [0:0] vector_ctrl_err_clear_pulse_o;
  logic [0:0] vector_ctrl_perf_clear_pulse_o;
  logic [0:0] vector_status_busy_i;
  logic [0:0] vector_status_err_sticky_i;
  logic [0:0] vector_status_q_full_i;
  logic [0:0] vector_status_q_empty_i;
  logic [0:0] vector_status_cpl_valid_i;
  logic [0:0] vector_status_dma_down_i;
  logic [0:0] vector_status_vec_down_i;
  logic [7:0] vector_status_q_count_i;
  logic [7:0] vector_status_rob_count_i;
  logic [7:0] vector_status_q_free_i;
  logic [0:0] vector_int_enable_irq_o;
  logic [0:0] vector_int_enable_err_o;
  logic [0:0] vector_int_status_irq_o;
  logic [0:0] vector_int_status_irq_set_i;
  logic [0:0] vector_int_status_err_o;
  logic [0:0] vector_int_status_err_set_i;
  logic [31:0] vector_submitted_value_i;
  logic [255:0] vector_desc_value_o;
  logic [0:0] vector_doorbell_wr_o;
  logic [0:0] vector_doorbell_wgate_i;
  logic [127:0] vector_cpl_value_i;
  logic [0:0] vector_cpl_pop_wr_o;
  logic [0:0] vector_cpl_pop_wgate_i;
  logic [543:0] vector_perf_value_i;
  logic [0:0] vector_irq_o;
  logic [0:0] perf_ctrl_freeze_o;
  logic [0:0] perf_ctrl_snapshot_pulse_o;
  logic [0:0] perf_status_frozen_i;
  logic [0:0] perf_status_irq_i;
  logic [1471:0] perf_cnt_value_i;
  logic [31:0] sysid_build_id_value_i;
  logic [15:0] intc_pending_sources_i;
  logic [15:0] intc_enable_en_o;
  logic [7:0] intc_claim_id_i;
  logic [15:0] intc_swpend_sw_o;
  logic [2:0] intc_threshold_level_o;
  logic [15:0] intc_active_act_i;
  logic [2:0] intc_prio0_src0_o;
  logic [2:0] intc_prio0_src1_o;
  logic [2:0] intc_prio0_src2_o;
  logic [2:0] intc_prio0_src3_o;
  logic [2:0] intc_prio0_src4_o;
  logic [2:0] intc_prio0_src5_o;
  logic [2:0] intc_prio0_src6_o;
  logic [2:0] intc_prio0_src7_o;
  logic [2:0] intc_prio1_src8_o;
  logic [2:0] intc_prio1_src9_o;
  logic [2:0] intc_prio1_src10_o;
  logic [2:0] intc_prio1_src11_o;
  logic [2:0] intc_prio1_src12_o;
  logic [2:0] intc_prio1_src13_o;
  logic [2:0] intc_prio1_src14_o;
  logic [2:0] intc_prio1_src15_o;
  logic [0:0] clkrst_config_mc_en_i;
  logic [7:0] clkrst_config_nw_i;
  logic [7:0] clkrst_config_nb_i;
  logic [7:0] clkrst_config_version_i;
  logic [3:0] clkrst_status_seq_state_i;
  logic [1:0] clkrst_status_mc_state_i;
  logic [0:0] clkrst_status_run_i;
  logic [0:0] clkrst_status_pll_locked_i;
  logic [0:0] clkrst_status_core_clk_ok_i;
  logic [0:0] clkrst_status_mc_clk_ok_i;
  logic [0:0] clkrst_status_wdog_warn_i;
  logic [0:0] clkrst_status_wdog_en_i;
  logic [0:0] clkrst_status_wdog_lock_i;
  logic [0:0] clkrst_status_wdog_rst_en_i;
  logic [0:0] clkrst_status_qtimeout_i;
  logic [0:0] clkrst_status_cmd_drop_i;
  logic [0:0] clkrst_status_wdog_cfg_rejected_i;
  logic [2:0] clkrst_status_domains_released_i;
  logic [0:0] clkrst_status_snap_seen_i;
  logic [10:0] clkrst_cause_causes_i;
  logic [15:0] clkrst_rst_info_reset_count_i;
  logic [3:0] clkrst_rst_info_last_cause_i;
  logic [7:0] clkrst_rst_info_branch_released_i;
  logic [7:0] clkrst_clk_en_branch_en_o;
  logic [7:0] clkrst_clk_stat_gate_en_i;
  logic [7:0] clkrst_clk_stat_clk_request_i;
  logic [31:0] clkrst_wdog_cnt_value_i;
  logic [15:0] clkrst_clk_meas_core_edges_i;
  logic [15:0] clkrst_clk_meas_mc_edges_i;
  logic [0:0] clkrst_irq_wdog_warn_i;
  logic [3:0] sramc_ctrl_src_en_o;
  logic [0:0] sramc_ctrl_flush_o;
  logic [0:0] sramc_status_idle_i;
  logic [0:0] sramc_status_rsp_overflow_i;
  logic [0:0] sramc_status_bank_proto_i;
  logic [6:0] sramc_perf_ctrl_sel_o;
  logic [0:0] sramc_perf_ctrl_clear_pulse_o;
  logic [31:0] sramc_perf_val_value_i;

  sf_reg_bank dut (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .req_valid_i(req_valid_i),
    .req_ready_o(req_ready_o),
    .req_i(req_i),
    .rsp_valid_o(rsp_valid_o),
    .rsp_ready_i(rsp_ready_i),
    .rsp_o(rsp_o),
    .dma_src_value_o(dma_src_value_o),
    .dma_dst_value_o(dma_dst_value_o),
    .dma_len_value_o(dma_len_value_o),
    .dma_tag_tag_o(dma_tag_tag_o),
    .dma_ctrl_abort_o(dma_ctrl_abort_o),
    .dma_start_wr_o(dma_start_wr_o),
    .dma_start_wgate_i(dma_start_wgate_i),
    .dma_status_busy_i(dma_status_busy_i),
    .dma_status_active_i(dma_status_active_i),
    .dma_status_ctl_state_i(dma_status_ctl_state_i),
    .dma_status_eng_state_i(dma_status_eng_state_i),
    .dma_status_cur_tag_i(dma_status_cur_tag_i),
    .dma_status_fifo_level_i(dma_status_fifo_level_i),
    .dma_bytes_done_value_i(dma_bytes_done_value_i),
    .dma_cpl_status_valid_i(dma_cpl_status_valid_i),
    .dma_cpl_status_err_i(dma_cpl_status_err_i),
    .dma_cpl_status_code_i(dma_cpl_status_code_i),
    .dma_cpl_status_tag_i(dma_cpl_status_tag_i),
    .dma_cpl_err_addr_value_i(dma_cpl_err_addr_value_i),
    .dma_cpl_bytes_value_i(dma_cpl_bytes_value_i),
    .dma_cpl_pop_wr_o(dma_cpl_pop_wr_o),
    .dma_cpl_pop_wgate_i(dma_cpl_pop_wgate_i),
    .dma_perf_ctrl_clear_pulse_o(dma_perf_ctrl_clear_pulse_o),
    .dma_int_enable_cpl_o(dma_int_enable_cpl_o),
    .dma_int_enable_cpl_err_o(dma_int_enable_cpl_err_o),
    .dma_int_enable_bus_err_o(dma_int_enable_bus_err_o),
    .dma_int_enable_tag_err_o(dma_int_enable_tag_err_o),
    .dma_int_status_cpl_o(dma_int_status_cpl_o),
    .dma_int_status_cpl_set_i(dma_int_status_cpl_set_i),
    .dma_int_status_cpl_err_o(dma_int_status_cpl_err_o),
    .dma_int_status_cpl_err_set_i(dma_int_status_cpl_err_set_i),
    .dma_int_status_bus_err_o(dma_int_status_bus_err_o),
    .dma_int_status_bus_err_set_i(dma_int_status_bus_err_set_i),
    .dma_int_status_tag_err_o(dma_int_status_tag_err_o),
    .dma_int_status_tag_err_set_i(dma_int_status_tag_err_set_i),
    .dma_perf_value_i(dma_perf_value_i),
    .dma_irq_o(dma_irq_o),
    .tensor_info_abi_version_i(tensor_info_abi_version_i),
    .tensor_info_log2_queue_depth_i(tensor_info_log2_queue_depth_i),
    .tensor_info_array_rows_i(tensor_info_array_rows_i),
    .tensor_info_array_cols_i(tensor_info_array_cols_i),
    .tensor_info_enable_quantization_i(tensor_info_enable_quantization_i),
    .tensor_info_enable_double_buffering_i(tensor_info_enable_double_buffering_i),
    .tensor_info_perf_en_i(tensor_info_perf_en_i),
    .tensor_caps_tile_k_i(tensor_caps_tile_k_i),
    .tensor_caps_data_width_i(tensor_caps_data_width_i),
    .tensor_caps_acc_width_i(tensor_caps_acc_width_i),
    .tensor_opbuf_value_i(tensor_opbuf_value_i),
    .tensor_mem_lo_value_i(tensor_mem_lo_value_i),
    .tensor_mem_last_value_i(tensor_mem_last_value_i),
    .tensor_ctrl_err_cont_o(tensor_ctrl_err_cont_o),
    .tensor_ctrl_err_clear_pulse_o(tensor_ctrl_err_clear_pulse_o),
    .tensor_ctrl_perf_clear_pulse_o(tensor_ctrl_perf_clear_pulse_o),
    .tensor_ctrl_abort_pulse_o(tensor_ctrl_abort_pulse_o),
    .tensor_status_busy_i(tensor_status_busy_i),
    .tensor_status_err_sticky_i(tensor_status_err_sticky_i),
    .tensor_status_q_full_i(tensor_status_q_full_i),
    .tensor_status_q_empty_i(tensor_status_q_empty_i),
    .tensor_status_cpl_valid_i(tensor_status_cpl_valid_i),
    .tensor_status_aborting_i(tensor_status_aborting_i),
    .tensor_status_halted_i(tensor_status_halted_i),
    .tensor_status_state_i(tensor_status_state_i),
    .tensor_status_qcount_i(tensor_status_qcount_i),
    .tensor_status_qfree_i(tensor_status_qfree_i),
    .tensor_int_enable_irq_o(tensor_int_enable_irq_o),
    .tensor_int_enable_err_o(tensor_int_enable_err_o),
    .tensor_int_enable_done_o(tensor_int_enable_done_o),
    .tensor_int_status_irq_o(tensor_int_status_irq_o),
    .tensor_int_status_irq_set_i(tensor_int_status_irq_set_i),
    .tensor_int_status_err_o(tensor_int_status_err_o),
    .tensor_int_status_err_set_i(tensor_int_status_err_set_i),
    .tensor_int_status_done_o(tensor_int_status_done_o),
    .tensor_int_status_done_set_i(tensor_int_status_done_set_i),
    .tensor_submitted_value_i(tensor_submitted_value_i),
    .tensor_kmax_value_i(tensor_kmax_value_i),
    .tensor_desc_value_o(tensor_desc_value_o),
    .tensor_doorbell_wr_o(tensor_doorbell_wr_o),
    .tensor_doorbell_wgate_i(tensor_doorbell_wgate_i),
    .tensor_cpl_value_i(tensor_cpl_value_i),
    .tensor_cpl_pop_wr_o(tensor_cpl_pop_wr_o),
    .tensor_cpl_pop_wgate_i(tensor_cpl_pop_wgate_i),
    .tensor_perf_value_i(tensor_perf_value_i),
    .tensor_dma_perf_value_i(tensor_dma_perf_value_i),
    .tensor_irq_o(tensor_irq_o),
    .vector_info_abi_version_i(vector_info_abi_version_i),
    .vector_info_queue_depth_i(vector_info_queue_depth_i),
    .vector_info_rob_depth_i(vector_info_rob_depth_i),
    .vector_info_opset_full_i(vector_info_opset_full_i),
    .vector_info_overlap_en_i(vector_info_overlap_en_i),
    .vector_info_perf_en_i(vector_info_perf_en_i),
    .vector_ctrl_err_cont_o(vector_ctrl_err_cont_o),
    .vector_ctrl_err_clear_pulse_o(vector_ctrl_err_clear_pulse_o),
    .vector_ctrl_perf_clear_pulse_o(vector_ctrl_perf_clear_pulse_o),
    .vector_status_busy_i(vector_status_busy_i),
    .vector_status_err_sticky_i(vector_status_err_sticky_i),
    .vector_status_q_full_i(vector_status_q_full_i),
    .vector_status_q_empty_i(vector_status_q_empty_i),
    .vector_status_cpl_valid_i(vector_status_cpl_valid_i),
    .vector_status_dma_down_i(vector_status_dma_down_i),
    .vector_status_vec_down_i(vector_status_vec_down_i),
    .vector_status_q_count_i(vector_status_q_count_i),
    .vector_status_rob_count_i(vector_status_rob_count_i),
    .vector_status_q_free_i(vector_status_q_free_i),
    .vector_int_enable_irq_o(vector_int_enable_irq_o),
    .vector_int_enable_err_o(vector_int_enable_err_o),
    .vector_int_status_irq_o(vector_int_status_irq_o),
    .vector_int_status_irq_set_i(vector_int_status_irq_set_i),
    .vector_int_status_err_o(vector_int_status_err_o),
    .vector_int_status_err_set_i(vector_int_status_err_set_i),
    .vector_submitted_value_i(vector_submitted_value_i),
    .vector_desc_value_o(vector_desc_value_o),
    .vector_doorbell_wr_o(vector_doorbell_wr_o),
    .vector_doorbell_wgate_i(vector_doorbell_wgate_i),
    .vector_cpl_value_i(vector_cpl_value_i),
    .vector_cpl_pop_wr_o(vector_cpl_pop_wr_o),
    .vector_cpl_pop_wgate_i(vector_cpl_pop_wgate_i),
    .vector_perf_value_i(vector_perf_value_i),
    .vector_irq_o(vector_irq_o),
    .perf_ctrl_freeze_o(perf_ctrl_freeze_o),
    .perf_ctrl_snapshot_pulse_o(perf_ctrl_snapshot_pulse_o),
    .perf_status_frozen_i(perf_status_frozen_i),
    .perf_status_irq_i(perf_status_irq_i),
    .perf_cnt_value_i(perf_cnt_value_i),
    .sysid_build_id_value_i(sysid_build_id_value_i),
    .intc_pending_sources_i(intc_pending_sources_i),
    .intc_enable_en_o(intc_enable_en_o),
    .intc_claim_id_i(intc_claim_id_i),
    .intc_swpend_sw_o(intc_swpend_sw_o),
    .intc_threshold_level_o(intc_threshold_level_o),
    .intc_active_act_i(intc_active_act_i),
    .intc_prio0_src0_o(intc_prio0_src0_o),
    .intc_prio0_src1_o(intc_prio0_src1_o),
    .intc_prio0_src2_o(intc_prio0_src2_o),
    .intc_prio0_src3_o(intc_prio0_src3_o),
    .intc_prio0_src4_o(intc_prio0_src4_o),
    .intc_prio0_src5_o(intc_prio0_src5_o),
    .intc_prio0_src6_o(intc_prio0_src6_o),
    .intc_prio0_src7_o(intc_prio0_src7_o),
    .intc_prio1_src8_o(intc_prio1_src8_o),
    .intc_prio1_src9_o(intc_prio1_src9_o),
    .intc_prio1_src10_o(intc_prio1_src10_o),
    .intc_prio1_src11_o(intc_prio1_src11_o),
    .intc_prio1_src12_o(intc_prio1_src12_o),
    .intc_prio1_src13_o(intc_prio1_src13_o),
    .intc_prio1_src14_o(intc_prio1_src14_o),
    .intc_prio1_src15_o(intc_prio1_src15_o),
    .clkrst_config_mc_en_i(clkrst_config_mc_en_i),
    .clkrst_config_nw_i(clkrst_config_nw_i),
    .clkrst_config_nb_i(clkrst_config_nb_i),
    .clkrst_config_version_i(clkrst_config_version_i),
    .clkrst_status_seq_state_i(clkrst_status_seq_state_i),
    .clkrst_status_mc_state_i(clkrst_status_mc_state_i),
    .clkrst_status_run_i(clkrst_status_run_i),
    .clkrst_status_pll_locked_i(clkrst_status_pll_locked_i),
    .clkrst_status_core_clk_ok_i(clkrst_status_core_clk_ok_i),
    .clkrst_status_mc_clk_ok_i(clkrst_status_mc_clk_ok_i),
    .clkrst_status_wdog_warn_i(clkrst_status_wdog_warn_i),
    .clkrst_status_wdog_en_i(clkrst_status_wdog_en_i),
    .clkrst_status_wdog_lock_i(clkrst_status_wdog_lock_i),
    .clkrst_status_wdog_rst_en_i(clkrst_status_wdog_rst_en_i),
    .clkrst_status_qtimeout_i(clkrst_status_qtimeout_i),
    .clkrst_status_cmd_drop_i(clkrst_status_cmd_drop_i),
    .clkrst_status_wdog_cfg_rejected_i(clkrst_status_wdog_cfg_rejected_i),
    .clkrst_status_domains_released_i(clkrst_status_domains_released_i),
    .clkrst_status_snap_seen_i(clkrst_status_snap_seen_i),
    .clkrst_cause_causes_i(clkrst_cause_causes_i),
    .clkrst_rst_info_reset_count_i(clkrst_rst_info_reset_count_i),
    .clkrst_rst_info_last_cause_i(clkrst_rst_info_last_cause_i),
    .clkrst_rst_info_branch_released_i(clkrst_rst_info_branch_released_i),
    .clkrst_clk_en_branch_en_o(clkrst_clk_en_branch_en_o),
    .clkrst_clk_stat_gate_en_i(clkrst_clk_stat_gate_en_i),
    .clkrst_clk_stat_clk_request_i(clkrst_clk_stat_clk_request_i),
    .clkrst_wdog_cnt_value_i(clkrst_wdog_cnt_value_i),
    .clkrst_clk_meas_core_edges_i(clkrst_clk_meas_core_edges_i),
    .clkrst_clk_meas_mc_edges_i(clkrst_clk_meas_mc_edges_i),
    .clkrst_irq_wdog_warn_i(clkrst_irq_wdog_warn_i),
    .sramc_ctrl_src_en_o(sramc_ctrl_src_en_o),
    .sramc_ctrl_flush_o(sramc_ctrl_flush_o),
    .sramc_status_idle_i(sramc_status_idle_i),
    .sramc_status_rsp_overflow_i(sramc_status_rsp_overflow_i),
    .sramc_status_bank_proto_i(sramc_status_bank_proto_i),
    .sramc_perf_ctrl_sel_o(sramc_perf_ctrl_sel_o),
    .sramc_perf_ctrl_clear_pulse_o(sramc_perf_ctrl_clear_pulse_o),
    .sramc_perf_val_value_i(sramc_perf_val_value_i)
  );

  logic [15:0] outstanding;
  sf_albion_link_checker #(.MAX_OUTSTANDING(sf_reg_pkg::SF_REG_MAX_OUTSTANDING)) u_chk (
    .clk_i, .rst_ni, .req_valid_i, .req_ready_i(req_ready_o), .req_i,
    .rsp_valid_i(rsp_valid_o), .rsp_ready_i, .rsp_i(rsp_o), .waive_req_i(1'b0), .outstanding_o(outstanding)
  );

  logic [IN_W-1:0]  stim_mem [0:NCYC-1];
  logic [OUT_W-1:0] exp_mem  [0:NCYC-1];
  logic [OUT_W-1:0] msk_mem  [0:NCYC-1];
  logic [IN_W-1:0]  stim;
  logic [OUT_W-1:0] got, exp, msk;
  int errors, checks, cyc;
  string f_stim, f_exp, f_msk;

  initial begin clk_i = 1'b0; forever #5 clk_i = ~clk_i; end

  task automatic apply(input logic [IN_W-1:0] s);
    rst_ni = s[0 +: 1];
    req_valid_i = s[1 +: 1];
    rsp_ready_i = s[2 +: 1];
    req_i = s[3 +: 236];
    dma_start_wgate_i = s[239 +: 1];
    dma_status_busy_i = s[240 +: 1];
    dma_status_active_i = s[241 +: 1];
    dma_status_ctl_state_i = s[242 +: 2];
    dma_status_eng_state_i = s[244 +: 3];
    dma_status_cur_tag_i = s[247 +: 8];
    dma_status_fifo_level_i = s[255 +: 8];
    dma_bytes_done_value_i = s[263 +: 32];
    dma_cpl_status_valid_i = s[295 +: 1];
    dma_cpl_status_err_i = s[296 +: 1];
    dma_cpl_status_code_i = s[297 +: 4];
    dma_cpl_status_tag_i = s[301 +: 8];
    dma_cpl_err_addr_value_i = s[309 +: 32];
    dma_cpl_bytes_value_i = s[341 +: 32];
    dma_cpl_pop_wgate_i = s[373 +: 1];
    dma_int_status_cpl_set_i = s[374 +: 1];
    dma_int_status_cpl_err_set_i = s[375 +: 1];
    dma_int_status_bus_err_set_i = s[376 +: 1];
    dma_int_status_tag_err_set_i = s[377 +: 1];
    dma_perf_value_i = s[378 +: 512];
    tensor_info_abi_version_i = s[890 +: 4];
    tensor_info_log2_queue_depth_i = s[894 +: 4];
    tensor_info_array_rows_i = s[898 +: 8];
    tensor_info_array_cols_i = s[906 +: 8];
    tensor_info_enable_quantization_i = s[914 +: 1];
    tensor_info_enable_double_buffering_i = s[915 +: 1];
    tensor_info_perf_en_i = s[916 +: 1];
    tensor_caps_tile_k_i = s[917 +: 16];
    tensor_caps_data_width_i = s[933 +: 8];
    tensor_caps_acc_width_i = s[941 +: 8];
    tensor_opbuf_value_i = s[949 +: 32];
    tensor_mem_lo_value_i = s[981 +: 32];
    tensor_mem_last_value_i = s[1013 +: 32];
    tensor_status_busy_i = s[1045 +: 1];
    tensor_status_err_sticky_i = s[1046 +: 1];
    tensor_status_q_full_i = s[1047 +: 1];
    tensor_status_q_empty_i = s[1048 +: 1];
    tensor_status_cpl_valid_i = s[1049 +: 1];
    tensor_status_aborting_i = s[1050 +: 1];
    tensor_status_halted_i = s[1051 +: 1];
    tensor_status_state_i = s[1052 +: 4];
    tensor_status_qcount_i = s[1056 +: 8];
    tensor_status_qfree_i = s[1064 +: 8];
    tensor_int_status_irq_set_i = s[1072 +: 1];
    tensor_int_status_err_set_i = s[1073 +: 1];
    tensor_int_status_done_set_i = s[1074 +: 1];
    tensor_submitted_value_i = s[1075 +: 32];
    tensor_kmax_value_i = s[1107 +: 32];
    tensor_doorbell_wgate_i = s[1139 +: 1];
    tensor_cpl_value_i = s[1140 +: 192];
    tensor_cpl_pop_wgate_i = s[1332 +: 1];
    tensor_perf_value_i = s[1333 +: 640];
    tensor_dma_perf_value_i = s[1973 +: 576];
    vector_info_abi_version_i = s[2549 +: 4];
    vector_info_queue_depth_i = s[2553 +: 8];
    vector_info_rob_depth_i = s[2561 +: 8];
    vector_info_opset_full_i = s[2569 +: 1];
    vector_info_overlap_en_i = s[2570 +: 1];
    vector_info_perf_en_i = s[2571 +: 1];
    vector_status_busy_i = s[2572 +: 1];
    vector_status_err_sticky_i = s[2573 +: 1];
    vector_status_q_full_i = s[2574 +: 1];
    vector_status_q_empty_i = s[2575 +: 1];
    vector_status_cpl_valid_i = s[2576 +: 1];
    vector_status_dma_down_i = s[2577 +: 1];
    vector_status_vec_down_i = s[2578 +: 1];
    vector_status_q_count_i = s[2579 +: 8];
    vector_status_rob_count_i = s[2587 +: 8];
    vector_status_q_free_i = s[2595 +: 8];
    vector_int_status_irq_set_i = s[2603 +: 1];
    vector_int_status_err_set_i = s[2604 +: 1];
    vector_submitted_value_i = s[2605 +: 32];
    vector_doorbell_wgate_i = s[2637 +: 1];
    vector_cpl_value_i = s[2638 +: 128];
    vector_cpl_pop_wgate_i = s[2766 +: 1];
    vector_perf_value_i = s[2767 +: 544];
    perf_status_frozen_i = s[3311 +: 1];
    perf_status_irq_i = s[3312 +: 1];
    perf_cnt_value_i = s[3313 +: 1472];
    sysid_build_id_value_i = s[4785 +: 32];
    intc_pending_sources_i = s[4817 +: 16];
    intc_claim_id_i = s[4833 +: 8];
    intc_active_act_i = s[4841 +: 16];
    clkrst_config_mc_en_i = s[4857 +: 1];
    clkrst_config_nw_i = s[4858 +: 8];
    clkrst_config_nb_i = s[4866 +: 8];
    clkrst_config_version_i = s[4874 +: 8];
    clkrst_status_seq_state_i = s[4882 +: 4];
    clkrst_status_mc_state_i = s[4886 +: 2];
    clkrst_status_run_i = s[4888 +: 1];
    clkrst_status_pll_locked_i = s[4889 +: 1];
    clkrst_status_core_clk_ok_i = s[4890 +: 1];
    clkrst_status_mc_clk_ok_i = s[4891 +: 1];
    clkrst_status_wdog_warn_i = s[4892 +: 1];
    clkrst_status_wdog_en_i = s[4893 +: 1];
    clkrst_status_wdog_lock_i = s[4894 +: 1];
    clkrst_status_wdog_rst_en_i = s[4895 +: 1];
    clkrst_status_qtimeout_i = s[4896 +: 1];
    clkrst_status_cmd_drop_i = s[4897 +: 1];
    clkrst_status_wdog_cfg_rejected_i = s[4898 +: 1];
    clkrst_status_domains_released_i = s[4899 +: 3];
    clkrst_status_snap_seen_i = s[4902 +: 1];
    clkrst_cause_causes_i = s[4903 +: 11];
    clkrst_rst_info_reset_count_i = s[4914 +: 16];
    clkrst_rst_info_last_cause_i = s[4930 +: 4];
    clkrst_rst_info_branch_released_i = s[4934 +: 8];
    clkrst_clk_stat_gate_en_i = s[4942 +: 8];
    clkrst_clk_stat_clk_request_i = s[4950 +: 8];
    clkrst_wdog_cnt_value_i = s[4958 +: 32];
    clkrst_clk_meas_core_edges_i = s[4990 +: 16];
    clkrst_clk_meas_mc_edges_i = s[5006 +: 16];
    clkrst_irq_wdog_warn_i = s[5022 +: 1];
    sramc_status_idle_i = s[5023 +: 1];
    sramc_status_rsp_overflow_i = s[5024 +: 1];
    sramc_status_bank_proto_i = s[5025 +: 1];
    sramc_perf_val_value_i = s[5026 +: 32];
  endtask

  always_comb begin
    got[0 +: 1] = req_ready_o;
    got[1 +: 1] = rsp_valid_o;
    got[2 +: 148] = rsp_o;
    got[150 +: 32] = dma_src_value_o;
    got[182 +: 32] = dma_dst_value_o;
    got[214 +: 32] = dma_len_value_o;
    got[246 +: 8] = dma_tag_tag_o;
    got[254 +: 1] = dma_ctrl_abort_o;
    got[255 +: 1] = dma_start_wr_o;
    got[256 +: 1] = dma_cpl_pop_wr_o;
    got[257 +: 1] = dma_perf_ctrl_clear_pulse_o;
    got[258 +: 1] = dma_int_enable_cpl_o;
    got[259 +: 1] = dma_int_enable_cpl_err_o;
    got[260 +: 1] = dma_int_enable_bus_err_o;
    got[261 +: 1] = dma_int_enable_tag_err_o;
    got[262 +: 1] = dma_int_status_cpl_o;
    got[263 +: 1] = dma_int_status_cpl_err_o;
    got[264 +: 1] = dma_int_status_bus_err_o;
    got[265 +: 1] = dma_int_status_tag_err_o;
    got[266 +: 1] = dma_irq_o;
    got[267 +: 1] = tensor_ctrl_err_cont_o;
    got[268 +: 1] = tensor_ctrl_err_clear_pulse_o;
    got[269 +: 1] = tensor_ctrl_perf_clear_pulse_o;
    got[270 +: 1] = tensor_ctrl_abort_pulse_o;
    got[271 +: 1] = tensor_int_enable_irq_o;
    got[272 +: 1] = tensor_int_enable_err_o;
    got[273 +: 1] = tensor_int_enable_done_o;
    got[274 +: 1] = tensor_int_status_irq_o;
    got[275 +: 1] = tensor_int_status_err_o;
    got[276 +: 1] = tensor_int_status_done_o;
    got[277 +: 384] = tensor_desc_value_o;
    got[661 +: 1] = tensor_doorbell_wr_o;
    got[662 +: 1] = tensor_cpl_pop_wr_o;
    got[663 +: 1] = tensor_irq_o;
    got[664 +: 1] = vector_ctrl_err_cont_o;
    got[665 +: 1] = vector_ctrl_err_clear_pulse_o;
    got[666 +: 1] = vector_ctrl_perf_clear_pulse_o;
    got[667 +: 1] = vector_int_enable_irq_o;
    got[668 +: 1] = vector_int_enable_err_o;
    got[669 +: 1] = vector_int_status_irq_o;
    got[670 +: 1] = vector_int_status_err_o;
    got[671 +: 256] = vector_desc_value_o;
    got[927 +: 1] = vector_doorbell_wr_o;
    got[928 +: 1] = vector_cpl_pop_wr_o;
    got[929 +: 1] = vector_irq_o;
    got[930 +: 1] = perf_ctrl_freeze_o;
    got[931 +: 1] = perf_ctrl_snapshot_pulse_o;
    got[932 +: 16] = intc_enable_en_o;
    got[948 +: 16] = intc_swpend_sw_o;
    got[964 +: 3] = intc_threshold_level_o;
    got[967 +: 3] = intc_prio0_src0_o;
    got[970 +: 3] = intc_prio0_src1_o;
    got[973 +: 3] = intc_prio0_src2_o;
    got[976 +: 3] = intc_prio0_src3_o;
    got[979 +: 3] = intc_prio0_src4_o;
    got[982 +: 3] = intc_prio0_src5_o;
    got[985 +: 3] = intc_prio0_src6_o;
    got[988 +: 3] = intc_prio0_src7_o;
    got[991 +: 3] = intc_prio1_src8_o;
    got[994 +: 3] = intc_prio1_src9_o;
    got[997 +: 3] = intc_prio1_src10_o;
    got[1000 +: 3] = intc_prio1_src11_o;
    got[1003 +: 3] = intc_prio1_src12_o;
    got[1006 +: 3] = intc_prio1_src13_o;
    got[1009 +: 3] = intc_prio1_src14_o;
    got[1012 +: 3] = intc_prio1_src15_o;
    got[1015 +: 8] = clkrst_clk_en_branch_en_o;
    got[1023 +: 4] = sramc_ctrl_src_en_o;
    got[1027 +: 1] = sramc_ctrl_flush_o;
    got[1028 +: 7] = sramc_perf_ctrl_sel_o;
    got[1035 +: 1] = sramc_perf_ctrl_clear_pulse_o;
  end

  task automatic compare(input int c);
    logic [OUT_W-1:0] diff;
    diff = (got ^ exp) & msk;
    checks += $countones(msk);
    if (diff != '0) begin
      errors++;
      if (diff[0 +: 1] != '0) $display("MISMATCH cycle %0d req_ready: got=%h exp=%h", c, got[0 +: 1], exp[0 +: 1]);
      if (diff[1 +: 1] != '0) $display("MISMATCH cycle %0d rsp_valid: got=%h exp=%h", c, got[1 +: 1], exp[1 +: 1]);
      if (diff[2 +: 148] != '0) $display("MISMATCH cycle %0d rsp: got=%h exp=%h", c, got[2 +: 148], exp[2 +: 148]);
      if (diff[150 +: 32] != '0) $display("MISMATCH cycle %0d dma_src_value_o: got=%h exp=%h", c, got[150 +: 32], exp[150 +: 32]);
      if (diff[182 +: 32] != '0) $display("MISMATCH cycle %0d dma_dst_value_o: got=%h exp=%h", c, got[182 +: 32], exp[182 +: 32]);
      if (diff[214 +: 32] != '0) $display("MISMATCH cycle %0d dma_len_value_o: got=%h exp=%h", c, got[214 +: 32], exp[214 +: 32]);
      if (diff[246 +: 8] != '0) $display("MISMATCH cycle %0d dma_tag_tag_o: got=%h exp=%h", c, got[246 +: 8], exp[246 +: 8]);
      if (diff[254 +: 1] != '0) $display("MISMATCH cycle %0d dma_ctrl_abort_o: got=%h exp=%h", c, got[254 +: 1], exp[254 +: 1]);
      if (diff[255 +: 1] != '0) $display("MISMATCH cycle %0d dma_start_wr_o: got=%h exp=%h", c, got[255 +: 1], exp[255 +: 1]);
      if (diff[256 +: 1] != '0) $display("MISMATCH cycle %0d dma_cpl_pop_wr_o: got=%h exp=%h", c, got[256 +: 1], exp[256 +: 1]);
      if (diff[257 +: 1] != '0) $display("MISMATCH cycle %0d dma_perf_ctrl_clear_pulse_o: got=%h exp=%h", c, got[257 +: 1], exp[257 +: 1]);
      if (diff[258 +: 1] != '0) $display("MISMATCH cycle %0d dma_int_enable_cpl_o: got=%h exp=%h", c, got[258 +: 1], exp[258 +: 1]);
      if (diff[259 +: 1] != '0) $display("MISMATCH cycle %0d dma_int_enable_cpl_err_o: got=%h exp=%h", c, got[259 +: 1], exp[259 +: 1]);
      if (diff[260 +: 1] != '0) $display("MISMATCH cycle %0d dma_int_enable_bus_err_o: got=%h exp=%h", c, got[260 +: 1], exp[260 +: 1]);
      if (diff[261 +: 1] != '0) $display("MISMATCH cycle %0d dma_int_enable_tag_err_o: got=%h exp=%h", c, got[261 +: 1], exp[261 +: 1]);
      if (diff[262 +: 1] != '0) $display("MISMATCH cycle %0d dma_int_status_cpl_o: got=%h exp=%h", c, got[262 +: 1], exp[262 +: 1]);
      if (diff[263 +: 1] != '0) $display("MISMATCH cycle %0d dma_int_status_cpl_err_o: got=%h exp=%h", c, got[263 +: 1], exp[263 +: 1]);
      if (diff[264 +: 1] != '0) $display("MISMATCH cycle %0d dma_int_status_bus_err_o: got=%h exp=%h", c, got[264 +: 1], exp[264 +: 1]);
      if (diff[265 +: 1] != '0) $display("MISMATCH cycle %0d dma_int_status_tag_err_o: got=%h exp=%h", c, got[265 +: 1], exp[265 +: 1]);
      if (diff[266 +: 1] != '0) $display("MISMATCH cycle %0d dma_irq_o: got=%h exp=%h", c, got[266 +: 1], exp[266 +: 1]);
      if (diff[267 +: 1] != '0) $display("MISMATCH cycle %0d tensor_ctrl_err_cont_o: got=%h exp=%h", c, got[267 +: 1], exp[267 +: 1]);
      if (diff[268 +: 1] != '0) $display("MISMATCH cycle %0d tensor_ctrl_err_clear_pulse_o: got=%h exp=%h", c, got[268 +: 1], exp[268 +: 1]);
      if (diff[269 +: 1] != '0) $display("MISMATCH cycle %0d tensor_ctrl_perf_clear_pulse_o: got=%h exp=%h", c, got[269 +: 1], exp[269 +: 1]);
      if (diff[270 +: 1] != '0) $display("MISMATCH cycle %0d tensor_ctrl_abort_pulse_o: got=%h exp=%h", c, got[270 +: 1], exp[270 +: 1]);
      if (diff[271 +: 1] != '0) $display("MISMATCH cycle %0d tensor_int_enable_irq_o: got=%h exp=%h", c, got[271 +: 1], exp[271 +: 1]);
      if (diff[272 +: 1] != '0) $display("MISMATCH cycle %0d tensor_int_enable_err_o: got=%h exp=%h", c, got[272 +: 1], exp[272 +: 1]);
      if (diff[273 +: 1] != '0) $display("MISMATCH cycle %0d tensor_int_enable_done_o: got=%h exp=%h", c, got[273 +: 1], exp[273 +: 1]);
      if (diff[274 +: 1] != '0) $display("MISMATCH cycle %0d tensor_int_status_irq_o: got=%h exp=%h", c, got[274 +: 1], exp[274 +: 1]);
      if (diff[275 +: 1] != '0) $display("MISMATCH cycle %0d tensor_int_status_err_o: got=%h exp=%h", c, got[275 +: 1], exp[275 +: 1]);
      if (diff[276 +: 1] != '0) $display("MISMATCH cycle %0d tensor_int_status_done_o: got=%h exp=%h", c, got[276 +: 1], exp[276 +: 1]);
      if (diff[277 +: 384] != '0) $display("MISMATCH cycle %0d tensor_desc_value_o: got=%h exp=%h", c, got[277 +: 384], exp[277 +: 384]);
      if (diff[661 +: 1] != '0) $display("MISMATCH cycle %0d tensor_doorbell_wr_o: got=%h exp=%h", c, got[661 +: 1], exp[661 +: 1]);
      if (diff[662 +: 1] != '0) $display("MISMATCH cycle %0d tensor_cpl_pop_wr_o: got=%h exp=%h", c, got[662 +: 1], exp[662 +: 1]);
      if (diff[663 +: 1] != '0) $display("MISMATCH cycle %0d tensor_irq_o: got=%h exp=%h", c, got[663 +: 1], exp[663 +: 1]);
      if (diff[664 +: 1] != '0) $display("MISMATCH cycle %0d vector_ctrl_err_cont_o: got=%h exp=%h", c, got[664 +: 1], exp[664 +: 1]);
      if (diff[665 +: 1] != '0) $display("MISMATCH cycle %0d vector_ctrl_err_clear_pulse_o: got=%h exp=%h", c, got[665 +: 1], exp[665 +: 1]);
      if (diff[666 +: 1] != '0) $display("MISMATCH cycle %0d vector_ctrl_perf_clear_pulse_o: got=%h exp=%h", c, got[666 +: 1], exp[666 +: 1]);
      if (diff[667 +: 1] != '0) $display("MISMATCH cycle %0d vector_int_enable_irq_o: got=%h exp=%h", c, got[667 +: 1], exp[667 +: 1]);
      if (diff[668 +: 1] != '0) $display("MISMATCH cycle %0d vector_int_enable_err_o: got=%h exp=%h", c, got[668 +: 1], exp[668 +: 1]);
      if (diff[669 +: 1] != '0) $display("MISMATCH cycle %0d vector_int_status_irq_o: got=%h exp=%h", c, got[669 +: 1], exp[669 +: 1]);
      if (diff[670 +: 1] != '0) $display("MISMATCH cycle %0d vector_int_status_err_o: got=%h exp=%h", c, got[670 +: 1], exp[670 +: 1]);
      if (diff[671 +: 256] != '0) $display("MISMATCH cycle %0d vector_desc_value_o: got=%h exp=%h", c, got[671 +: 256], exp[671 +: 256]);
      if (diff[927 +: 1] != '0) $display("MISMATCH cycle %0d vector_doorbell_wr_o: got=%h exp=%h", c, got[927 +: 1], exp[927 +: 1]);
      if (diff[928 +: 1] != '0) $display("MISMATCH cycle %0d vector_cpl_pop_wr_o: got=%h exp=%h", c, got[928 +: 1], exp[928 +: 1]);
      if (diff[929 +: 1] != '0) $display("MISMATCH cycle %0d vector_irq_o: got=%h exp=%h", c, got[929 +: 1], exp[929 +: 1]);
      if (diff[930 +: 1] != '0) $display("MISMATCH cycle %0d perf_ctrl_freeze_o: got=%h exp=%h", c, got[930 +: 1], exp[930 +: 1]);
      if (diff[931 +: 1] != '0) $display("MISMATCH cycle %0d perf_ctrl_snapshot_pulse_o: got=%h exp=%h", c, got[931 +: 1], exp[931 +: 1]);
      if (diff[932 +: 16] != '0) $display("MISMATCH cycle %0d intc_enable_en_o: got=%h exp=%h", c, got[932 +: 16], exp[932 +: 16]);
      if (diff[948 +: 16] != '0) $display("MISMATCH cycle %0d intc_swpend_sw_o: got=%h exp=%h", c, got[948 +: 16], exp[948 +: 16]);
      if (diff[964 +: 3] != '0) $display("MISMATCH cycle %0d intc_threshold_level_o: got=%h exp=%h", c, got[964 +: 3], exp[964 +: 3]);
      if (diff[967 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio0_src0_o: got=%h exp=%h", c, got[967 +: 3], exp[967 +: 3]);
      if (diff[970 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio0_src1_o: got=%h exp=%h", c, got[970 +: 3], exp[970 +: 3]);
      if (diff[973 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio0_src2_o: got=%h exp=%h", c, got[973 +: 3], exp[973 +: 3]);
      if (diff[976 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio0_src3_o: got=%h exp=%h", c, got[976 +: 3], exp[976 +: 3]);
      if (diff[979 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio0_src4_o: got=%h exp=%h", c, got[979 +: 3], exp[979 +: 3]);
      if (diff[982 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio0_src5_o: got=%h exp=%h", c, got[982 +: 3], exp[982 +: 3]);
      if (diff[985 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio0_src6_o: got=%h exp=%h", c, got[985 +: 3], exp[985 +: 3]);
      if (diff[988 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio0_src7_o: got=%h exp=%h", c, got[988 +: 3], exp[988 +: 3]);
      if (diff[991 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio1_src8_o: got=%h exp=%h", c, got[991 +: 3], exp[991 +: 3]);
      if (diff[994 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio1_src9_o: got=%h exp=%h", c, got[994 +: 3], exp[994 +: 3]);
      if (diff[997 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio1_src10_o: got=%h exp=%h", c, got[997 +: 3], exp[997 +: 3]);
      if (diff[1000 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio1_src11_o: got=%h exp=%h", c, got[1000 +: 3], exp[1000 +: 3]);
      if (diff[1003 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio1_src12_o: got=%h exp=%h", c, got[1003 +: 3], exp[1003 +: 3]);
      if (diff[1006 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio1_src13_o: got=%h exp=%h", c, got[1006 +: 3], exp[1006 +: 3]);
      if (diff[1009 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio1_src14_o: got=%h exp=%h", c, got[1009 +: 3], exp[1009 +: 3]);
      if (diff[1012 +: 3] != '0) $display("MISMATCH cycle %0d intc_prio1_src15_o: got=%h exp=%h", c, got[1012 +: 3], exp[1012 +: 3]);
      if (diff[1015 +: 8] != '0) $display("MISMATCH cycle %0d clkrst_clk_en_branch_en_o: got=%h exp=%h", c, got[1015 +: 8], exp[1015 +: 8]);
      if (diff[1023 +: 4] != '0) $display("MISMATCH cycle %0d sramc_ctrl_src_en_o: got=%h exp=%h", c, got[1023 +: 4], exp[1023 +: 4]);
      if (diff[1027 +: 1] != '0) $display("MISMATCH cycle %0d sramc_ctrl_flush_o: got=%h exp=%h", c, got[1027 +: 1], exp[1027 +: 1]);
      if (diff[1028 +: 7] != '0) $display("MISMATCH cycle %0d sramc_perf_ctrl_sel_o: got=%h exp=%h", c, got[1028 +: 7], exp[1028 +: 7]);
      if (diff[1035 +: 1] != '0) $display("MISMATCH cycle %0d sramc_perf_ctrl_clear_pulse_o: got=%h exp=%h", c, got[1035 +: 1], exp[1035 +: 1]);
    end
  endtask

  initial begin
    errors = 0; checks = 0;
    rst_ni = 1'b0; req_valid_i = 1'b0; rsp_ready_i = 1'b1; req_i = '0;
    dma_start_wgate_i = '0;
    dma_status_busy_i = '0;
    dma_status_active_i = '0;
    dma_status_ctl_state_i = '0;
    dma_status_eng_state_i = '0;
    dma_status_cur_tag_i = '0;
    dma_status_fifo_level_i = '0;
    dma_bytes_done_value_i = '0;
    dma_cpl_status_valid_i = '0;
    dma_cpl_status_err_i = '0;
    dma_cpl_status_code_i = '0;
    dma_cpl_status_tag_i = '0;
    dma_cpl_err_addr_value_i = '0;
    dma_cpl_bytes_value_i = '0;
    dma_cpl_pop_wgate_i = '0;
    dma_int_status_cpl_set_i = '0;
    dma_int_status_cpl_err_set_i = '0;
    dma_int_status_bus_err_set_i = '0;
    dma_int_status_tag_err_set_i = '0;
    dma_perf_value_i = '0;
    tensor_info_abi_version_i = '0;
    tensor_info_log2_queue_depth_i = '0;
    tensor_info_array_rows_i = '0;
    tensor_info_array_cols_i = '0;
    tensor_info_enable_quantization_i = '0;
    tensor_info_enable_double_buffering_i = '0;
    tensor_info_perf_en_i = '0;
    tensor_caps_tile_k_i = '0;
    tensor_caps_data_width_i = '0;
    tensor_caps_acc_width_i = '0;
    tensor_opbuf_value_i = '0;
    tensor_mem_lo_value_i = '0;
    tensor_mem_last_value_i = '0;
    tensor_status_busy_i = '0;
    tensor_status_err_sticky_i = '0;
    tensor_status_q_full_i = '0;
    tensor_status_q_empty_i = '0;
    tensor_status_cpl_valid_i = '0;
    tensor_status_aborting_i = '0;
    tensor_status_halted_i = '0;
    tensor_status_state_i = '0;
    tensor_status_qcount_i = '0;
    tensor_status_qfree_i = '0;
    tensor_int_status_irq_set_i = '0;
    tensor_int_status_err_set_i = '0;
    tensor_int_status_done_set_i = '0;
    tensor_submitted_value_i = '0;
    tensor_kmax_value_i = '0;
    tensor_doorbell_wgate_i = '0;
    tensor_cpl_value_i = '0;
    tensor_cpl_pop_wgate_i = '0;
    tensor_perf_value_i = '0;
    tensor_dma_perf_value_i = '0;
    vector_info_abi_version_i = '0;
    vector_info_queue_depth_i = '0;
    vector_info_rob_depth_i = '0;
    vector_info_opset_full_i = '0;
    vector_info_overlap_en_i = '0;
    vector_info_perf_en_i = '0;
    vector_status_busy_i = '0;
    vector_status_err_sticky_i = '0;
    vector_status_q_full_i = '0;
    vector_status_q_empty_i = '0;
    vector_status_cpl_valid_i = '0;
    vector_status_dma_down_i = '0;
    vector_status_vec_down_i = '0;
    vector_status_q_count_i = '0;
    vector_status_rob_count_i = '0;
    vector_status_q_free_i = '0;
    vector_int_status_irq_set_i = '0;
    vector_int_status_err_set_i = '0;
    vector_submitted_value_i = '0;
    vector_doorbell_wgate_i = '0;
    vector_cpl_value_i = '0;
    vector_cpl_pop_wgate_i = '0;
    vector_perf_value_i = '0;
    perf_status_frozen_i = '0;
    perf_status_irq_i = '0;
    perf_cnt_value_i = '0;
    sysid_build_id_value_i = '0;
    intc_pending_sources_i = '0;
    intc_claim_id_i = '0;
    intc_active_act_i = '0;
    clkrst_config_mc_en_i = '0;
    clkrst_config_nw_i = '0;
    clkrst_config_nb_i = '0;
    clkrst_config_version_i = '0;
    clkrst_status_seq_state_i = '0;
    clkrst_status_mc_state_i = '0;
    clkrst_status_run_i = '0;
    clkrst_status_pll_locked_i = '0;
    clkrst_status_core_clk_ok_i = '0;
    clkrst_status_mc_clk_ok_i = '0;
    clkrst_status_wdog_warn_i = '0;
    clkrst_status_wdog_en_i = '0;
    clkrst_status_wdog_lock_i = '0;
    clkrst_status_wdog_rst_en_i = '0;
    clkrst_status_qtimeout_i = '0;
    clkrst_status_cmd_drop_i = '0;
    clkrst_status_wdog_cfg_rejected_i = '0;
    clkrst_status_domains_released_i = '0;
    clkrst_status_snap_seen_i = '0;
    clkrst_cause_causes_i = '0;
    clkrst_rst_info_reset_count_i = '0;
    clkrst_rst_info_last_cause_i = '0;
    clkrst_rst_info_branch_released_i = '0;
    clkrst_clk_stat_gate_en_i = '0;
    clkrst_clk_stat_clk_request_i = '0;
    clkrst_wdog_cnt_value_i = '0;
    clkrst_clk_meas_core_edges_i = '0;
    clkrst_clk_meas_mc_edges_i = '0;
    clkrst_irq_wdog_warn_i = '0;
    sramc_status_idle_i = '0;
    sramc_status_rsp_overflow_i = '0;
    sramc_status_bank_proto_i = '0;
    sramc_perf_val_value_i = '0;
    if (!$value$plusargs("STIM=%s", f_stim)) $fatal(1, "missing +STIM");
    if (!$value$plusargs("EXP=%s",  f_exp))  $fatal(1, "missing +EXP");
    if (!$value$plusargs("MASK=%s", f_msk))  $fatal(1, "missing +MASK");
    $readmemh(f_stim, stim_mem);
    $readmemh(f_exp,  exp_mem);
    $readmemh(f_msk,  msk_mem);
    for (cyc = 0; cyc < NCYC; cyc++) begin
      @(negedge clk_i);
      stim = stim_mem[cyc];
      exp  = exp_mem[cyc];
      msk  = msk_mem[cyc];
      apply(stim);
      #3;
      compare(cyc);
    end
    @(negedge clk_i);
    if (errors == 0) $display("TB_RESULT: PASS cycles=%0d checks=%0d", NCYC, checks);
    else             $display("TB_RESULT: FAIL cycles=%0d errors=%0d", NCYC, errors);
    $finish;
  end
endmodule

`default_nettype wire
