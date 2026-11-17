// =============================================================================
//  sf_reg_bank.sv -- register bank (ALP v1 target)
//  GENERATED FILE -- DO NOT EDIT.  Edit the register definition instead.
//  generator       : albion_reggen 1.0.0 (definition schema 1)
//  register map   : silicaflux_regs v1.0
//  semantic hash  : 99481283139d2dc0690f688325c0631d115617fc66330be250e7a560f5e43d39
//  definition hash: 322ccd28a62e3936e355677a25425f8609977deab94841f7ce2049bcd96525ba
//  Bus protocol    : Albion Link Protocol v1 (AlbionCore sf_albion_pkg)
// =============================================================================

`default_nettype none

// Instantiate this module.  It contains sf_reg_interface and sf_reg_decoder.
// Timing: every hardware output is a flip-flop; hardware inputs are sampled at the clock edge
// that ends the accept cycle of the transaction they influence.  Software/hardware update
// conflicts are resolved per field by its 'precedence' (see the generated register documentation).
/* verilator lint_off UNUSEDSIGNAL */
module sf_reg_bank (
  input  wire logic                   clk_i,
  input  wire logic                   rst_ni,
  // ---- ALP v1 link (target)
  input  wire logic                   req_valid_i,
  output logic                        req_ready_o,
  input  sf_albion_pkg::sf_req_t      req_i,
  output logic                        rsp_valid_o,
  input  wire logic                   rsp_ready_i,
  output sf_albion_pkg::sf_rsp_t      rsp_o,
  // ---- hardware side: dma
  output logic      [31:0] dma_src_value_o,
  output logic      [31:0] dma_dst_value_o,
  output logic      [31:0] dma_len_value_o,
  output logic      [7:0] dma_tag_tag_o,
  output logic      [0:0] dma_ctrl_abort_o,
  output logic      [0:0] dma_start_wr_o,
  input  wire logic [0:0] dma_start_wgate_i,
  input  wire logic [0:0] dma_status_busy_i,
  input  wire logic [0:0] dma_status_active_i,
  input  wire logic [1:0] dma_status_ctl_state_i,
  input  wire logic [2:0] dma_status_eng_state_i,
  input  wire logic [7:0] dma_status_cur_tag_i,
  input  wire logic [7:0] dma_status_fifo_level_i,
  input  wire logic [31:0] dma_bytes_done_value_i,
  input  wire logic [0:0] dma_cpl_status_valid_i,
  input  wire logic [0:0] dma_cpl_status_err_i,
  input  wire logic [3:0] dma_cpl_status_code_i,
  input  wire logic [7:0] dma_cpl_status_tag_i,
  input  wire logic [31:0] dma_cpl_err_addr_value_i,
  input  wire logic [31:0] dma_cpl_bytes_value_i,
  output logic      [0:0] dma_cpl_pop_wr_o,
  input  wire logic [0:0] dma_cpl_pop_wgate_i,
  output logic      [0:0] dma_perf_ctrl_clear_pulse_o,
  output logic      [0:0] dma_int_enable_cpl_o,
  output logic      [0:0] dma_int_enable_cpl_err_o,
  output logic      [0:0] dma_int_enable_bus_err_o,
  output logic      [0:0] dma_int_enable_tag_err_o,
  output logic      [0:0] dma_int_status_cpl_o,
  input  wire logic [0:0] dma_int_status_cpl_set_i,
  output logic      [0:0] dma_int_status_cpl_err_o,
  input  wire logic [0:0] dma_int_status_cpl_err_set_i,
  output logic      [0:0] dma_int_status_bus_err_o,
  input  wire logic [0:0] dma_int_status_bus_err_set_i,
  output logic      [0:0] dma_int_status_tag_err_o,
  input  wire logic [0:0] dma_int_status_tag_err_set_i,
  input  wire logic [511:0] dma_perf_value_i,
  output logic      [0:0] dma_irq_o,
  // ---- hardware side: tensor
  input  wire logic [3:0] tensor_info_abi_version_i,
  input  wire logic [3:0] tensor_info_log2_queue_depth_i,
  input  wire logic [7:0] tensor_info_array_rows_i,
  input  wire logic [7:0] tensor_info_array_cols_i,
  input  wire logic [0:0] tensor_info_enable_quantization_i,
  input  wire logic [0:0] tensor_info_enable_double_buffering_i,
  input  wire logic [0:0] tensor_info_perf_en_i,
  input  wire logic [15:0] tensor_caps_tile_k_i,
  input  wire logic [7:0] tensor_caps_data_width_i,
  input  wire logic [7:0] tensor_caps_acc_width_i,
  input  wire logic [31:0] tensor_opbuf_value_i,
  input  wire logic [31:0] tensor_mem_lo_value_i,
  input  wire logic [31:0] tensor_mem_last_value_i,
  output logic      [0:0] tensor_ctrl_err_cont_o,
  output logic      [0:0] tensor_ctrl_err_clear_pulse_o,
  output logic      [0:0] tensor_ctrl_perf_clear_pulse_o,
  output logic      [0:0] tensor_ctrl_abort_pulse_o,
  input  wire logic [0:0] tensor_status_busy_i,
  input  wire logic [0:0] tensor_status_err_sticky_i,
  input  wire logic [0:0] tensor_status_q_full_i,
  input  wire logic [0:0] tensor_status_q_empty_i,
  input  wire logic [0:0] tensor_status_cpl_valid_i,
  input  wire logic [0:0] tensor_status_aborting_i,
  input  wire logic [0:0] tensor_status_halted_i,
  input  wire logic [3:0] tensor_status_state_i,
  input  wire logic [7:0] tensor_status_qcount_i,
  input  wire logic [7:0] tensor_status_qfree_i,
  output logic      [0:0] tensor_int_enable_irq_o,
  output logic      [0:0] tensor_int_enable_err_o,
  output logic      [0:0] tensor_int_enable_done_o,
  output logic      [0:0] tensor_int_status_irq_o,
  input  wire logic [0:0] tensor_int_status_irq_set_i,
  output logic      [0:0] tensor_int_status_err_o,
  input  wire logic [0:0] tensor_int_status_err_set_i,
  output logic      [0:0] tensor_int_status_done_o,
  input  wire logic [0:0] tensor_int_status_done_set_i,
  input  wire logic [31:0] tensor_submitted_value_i,
  input  wire logic [31:0] tensor_kmax_value_i,
  output logic      [383:0] tensor_desc_value_o,
  output logic      [0:0] tensor_doorbell_wr_o,
  input  wire logic [0:0] tensor_doorbell_wgate_i,
  input  wire logic [191:0] tensor_cpl_value_i,
  output logic      [0:0] tensor_cpl_pop_wr_o,
  input  wire logic [0:0] tensor_cpl_pop_wgate_i,
  input  wire logic [639:0] tensor_perf_value_i,
  input  wire logic [575:0] tensor_dma_perf_value_i,
  output logic      [0:0] tensor_irq_o,
  // ---- hardware side: vector
  input  wire logic [3:0] vector_info_abi_version_i,
  input  wire logic [7:0] vector_info_queue_depth_i,
  input  wire logic [7:0] vector_info_rob_depth_i,
  input  wire logic [0:0] vector_info_opset_full_i,
  input  wire logic [0:0] vector_info_overlap_en_i,
  input  wire logic [0:0] vector_info_perf_en_i,
  output logic      [0:0] vector_ctrl_err_cont_o,
  output logic      [0:0] vector_ctrl_err_clear_pulse_o,
  output logic      [0:0] vector_ctrl_perf_clear_pulse_o,
  input  wire logic [0:0] vector_status_busy_i,
  input  wire logic [0:0] vector_status_err_sticky_i,
  input  wire logic [0:0] vector_status_q_full_i,
  input  wire logic [0:0] vector_status_q_empty_i,
  input  wire logic [0:0] vector_status_cpl_valid_i,
  input  wire logic [0:0] vector_status_dma_down_i,
  input  wire logic [0:0] vector_status_vec_down_i,
  input  wire logic [7:0] vector_status_q_count_i,
  input  wire logic [7:0] vector_status_rob_count_i,
  input  wire logic [7:0] vector_status_q_free_i,
  output logic      [0:0] vector_int_enable_irq_o,
  output logic      [0:0] vector_int_enable_err_o,
  output logic      [0:0] vector_int_status_irq_o,
  input  wire logic [0:0] vector_int_status_irq_set_i,
  output logic      [0:0] vector_int_status_err_o,
  input  wire logic [0:0] vector_int_status_err_set_i,
  input  wire logic [31:0] vector_submitted_value_i,
  output logic      [255:0] vector_desc_value_o,
  output logic      [0:0] vector_doorbell_wr_o,
  input  wire logic [0:0] vector_doorbell_wgate_i,
  input  wire logic [127:0] vector_cpl_value_i,
  output logic      [0:0] vector_cpl_pop_wr_o,
  input  wire logic [0:0] vector_cpl_pop_wgate_i,
  input  wire logic [543:0] vector_perf_value_i,
  output logic      [0:0] vector_irq_o,
  // ---- hardware side: perf
  output logic      [0:0] perf_ctrl_freeze_o,
  output logic      [0:0] perf_ctrl_snapshot_pulse_o,
  input  wire logic [0:0] perf_status_frozen_i,
  input  wire logic [0:0] perf_status_irq_i,
  input  wire logic [1471:0] perf_cnt_value_i,
  // ---- hardware side: sysid
  input  wire logic [31:0] sysid_build_id_value_i,
  // ---- hardware side: intc
  input  wire logic [15:0] intc_pending_sources_i,
  output logic      [15:0] intc_enable_en_o,
  input  wire logic [7:0] intc_claim_id_i,
  output logic      [15:0] intc_swpend_sw_o,
  output logic      [2:0] intc_threshold_level_o,
  input  wire logic [15:0] intc_active_act_i,
  output logic      [2:0] intc_prio0_src0_o,
  output logic      [2:0] intc_prio0_src1_o,
  output logic      [2:0] intc_prio0_src2_o,
  output logic      [2:0] intc_prio0_src3_o,
  output logic      [2:0] intc_prio0_src4_o,
  output logic      [2:0] intc_prio0_src5_o,
  output logic      [2:0] intc_prio0_src6_o,
  output logic      [2:0] intc_prio0_src7_o,
  output logic      [2:0] intc_prio1_src8_o,
  output logic      [2:0] intc_prio1_src9_o,
  output logic      [2:0] intc_prio1_src10_o,
  output logic      [2:0] intc_prio1_src11_o,
  output logic      [2:0] intc_prio1_src12_o,
  output logic      [2:0] intc_prio1_src13_o,
  output logic      [2:0] intc_prio1_src14_o,
  output logic      [2:0] intc_prio1_src15_o,
  // ---- hardware side: clkrst
  input  wire logic [0:0] clkrst_config_mc_en_i,
  input  wire logic [7:0] clkrst_config_nw_i,
  input  wire logic [7:0] clkrst_config_nb_i,
  input  wire logic [7:0] clkrst_config_version_i,
  input  wire logic [3:0] clkrst_status_seq_state_i,
  input  wire logic [1:0] clkrst_status_mc_state_i,
  input  wire logic [0:0] clkrst_status_run_i,
  input  wire logic [0:0] clkrst_status_pll_locked_i,
  input  wire logic [0:0] clkrst_status_core_clk_ok_i,
  input  wire logic [0:0] clkrst_status_mc_clk_ok_i,
  input  wire logic [0:0] clkrst_status_wdog_warn_i,
  input  wire logic [0:0] clkrst_status_wdog_en_i,
  input  wire logic [0:0] clkrst_status_wdog_lock_i,
  input  wire logic [0:0] clkrst_status_wdog_rst_en_i,
  input  wire logic [0:0] clkrst_status_qtimeout_i,
  input  wire logic [0:0] clkrst_status_cmd_drop_i,
  input  wire logic [0:0] clkrst_status_wdog_cfg_rejected_i,
  input  wire logic [2:0] clkrst_status_domains_released_i,
  input  wire logic [0:0] clkrst_status_snap_seen_i,
  input  wire logic [10:0] clkrst_cause_causes_i,
  input  wire logic [15:0] clkrst_rst_info_reset_count_i,
  input  wire logic [3:0] clkrst_rst_info_last_cause_i,
  input  wire logic [7:0] clkrst_rst_info_branch_released_i,
  output logic      [7:0] clkrst_clk_en_branch_en_o,
  input  wire logic [7:0] clkrst_clk_stat_gate_en_i,
  input  wire logic [7:0] clkrst_clk_stat_clk_request_i,
  input  wire logic [31:0] clkrst_wdog_cnt_value_i,
  input  wire logic [15:0] clkrst_clk_meas_core_edges_i,
  input  wire logic [15:0] clkrst_clk_meas_mc_edges_i,
  input  wire logic [0:0] clkrst_irq_wdog_warn_i,
  // ---- hardware side: sramc
  output logic      [3:0] sramc_ctrl_src_en_o,
  output logic      [0:0] sramc_ctrl_flush_o,
  input  wire logic [0:0] sramc_status_idle_i,
  input  wire logic [0:0] sramc_status_rsp_overflow_i,
  input  wire logic [0:0] sramc_status_bank_proto_i,
  output logic      [6:0] sramc_perf_ctrl_sel_o,
  output logic      [0:0] sramc_perf_ctrl_clear_pulse_o,
  input  wire logic [31:0] sramc_perf_val_value_i
);

  // ---- ALP front end
  logic                                  acc_valid;
  logic [sf_albion_pkg::SF_REQ_W-1:0]    acc_req;
  logic [sf_albion_pkg::SF_STATUS_W-1:0] acc_legal;
  logic [sf_albion_pkg::SF_STATUS_W-1:0] acc_status;
  logic [sf_albion_pkg::SF_DATA_W-1:0]   acc_rdata;
  sf_reg_interface u_if (
    .clk_i, .rst_ni, .req_valid_i, .req_ready_o, .req_i, .rsp_valid_o, .rsp_ready_i, .rsp_o,
    .acc_valid_o(acc_valid), .acc_req_o(acc_req), .acc_legal_o(acc_legal),
    .acc_status_i(acc_status), .acc_rdata_i(acc_rdata)
  );

  // ---- decode
  logic [192:0] reg_sel;
  logic [sf_albion_pkg::SF_STATUS_W-1:0] dec_status;
  sf_reg_decoder u_dec (.req_i(acc_req), .reg_sel_o(reg_sel), .status_o(dec_status));

  logic        acc_is_write;
  logic        acc_is_read;
  logic [15:0] acc_be;
  assign acc_is_write = (acc_req[sf_albion_pkg::SF_REQ_OP_LSB +: sf_albion_pkg::SF_OP_W] == sf_albion_pkg::SF_OP_WRITE);
  assign acc_is_read  = (acc_req[sf_albion_pkg::SF_REQ_OP_LSB +: sf_albion_pkg::SF_OP_W] == sf_albion_pkg::SF_OP_READ);
  assign acc_be       = acc_req[sf_albion_pkg::SF_REQ_BE_LSB +: sf_albion_pkg::SF_BE_W];

  // ---- write gates (hardware 'ready'): a gated write whose gate is low is refused with TARGET_ERR
  logic [192:0] gate_ok;
  localparam logic [192:0] GATED = 193'h0000000000000000002100000000000004080000000000820;
  assign gate_ok[0] = 1'b1;
  assign gate_ok[1] = 1'b1;
  assign gate_ok[2] = 1'b1;
  assign gate_ok[3] = 1'b1;
  assign gate_ok[4] = 1'b1;
  assign gate_ok[5] = dma_start_wgate_i[0 +: 1];
  assign gate_ok[6] = 1'b1;
  assign gate_ok[7] = 1'b1;
  assign gate_ok[8] = 1'b1;
  assign gate_ok[9] = 1'b1;
  assign gate_ok[10] = 1'b1;
  assign gate_ok[11] = dma_cpl_pop_wgate_i[0 +: 1];
  assign gate_ok[12] = 1'b1;
  assign gate_ok[13] = 1'b1;
  assign gate_ok[14] = 1'b1;
  assign gate_ok[15] = 1'b1;
  assign gate_ok[16] = 1'b1;
  assign gate_ok[17] = 1'b1;
  assign gate_ok[18] = 1'b1;
  assign gate_ok[19] = 1'b1;
  assign gate_ok[20] = 1'b1;
  assign gate_ok[21] = 1'b1;
  assign gate_ok[22] = 1'b1;
  assign gate_ok[23] = 1'b1;
  assign gate_ok[24] = 1'b1;
  assign gate_ok[25] = 1'b1;
  assign gate_ok[26] = 1'b1;
  assign gate_ok[27] = 1'b1;
  assign gate_ok[28] = 1'b1;
  assign gate_ok[29] = 1'b1;
  assign gate_ok[30] = 1'b1;
  assign gate_ok[31] = 1'b1;
  assign gate_ok[32] = 1'b1;
  assign gate_ok[33] = 1'b1;
  assign gate_ok[34] = 1'b1;
  assign gate_ok[35] = 1'b1;
  assign gate_ok[36] = 1'b1;
  assign gate_ok[37] = 1'b1;
  assign gate_ok[38] = 1'b1;
  assign gate_ok[39] = 1'b1;
  assign gate_ok[40] = 1'b1;
  assign gate_ok[41] = 1'b1;
  assign gate_ok[42] = 1'b1;
  assign gate_ok[43] = 1'b1;
  assign gate_ok[44] = 1'b1;
  assign gate_ok[45] = 1'b1;
  assign gate_ok[46] = 1'b1;
  assign gate_ok[47] = 1'b1;
  assign gate_ok[48] = 1'b1;
  assign gate_ok[49] = 1'b1;
  assign gate_ok[50] = 1'b1;
  assign gate_ok[51] = 1'b1;
  assign gate_ok[52] = 1'b1;
  assign gate_ok[53] = 1'b1;
  assign gate_ok[54] = 1'b1;
  assign gate_ok[55] = tensor_doorbell_wgate_i[0 +: 1];
  assign gate_ok[56] = 1'b1;
  assign gate_ok[57] = 1'b1;
  assign gate_ok[58] = 1'b1;
  assign gate_ok[59] = 1'b1;
  assign gate_ok[60] = 1'b1;
  assign gate_ok[61] = 1'b1;
  assign gate_ok[62] = tensor_cpl_pop_wgate_i[0 +: 1];
  assign gate_ok[63] = 1'b1;
  assign gate_ok[64] = 1'b1;
  assign gate_ok[65] = 1'b1;
  assign gate_ok[66] = 1'b1;
  assign gate_ok[67] = 1'b1;
  assign gate_ok[68] = 1'b1;
  assign gate_ok[69] = 1'b1;
  assign gate_ok[70] = 1'b1;
  assign gate_ok[71] = 1'b1;
  assign gate_ok[72] = 1'b1;
  assign gate_ok[73] = 1'b1;
  assign gate_ok[74] = 1'b1;
  assign gate_ok[75] = 1'b1;
  assign gate_ok[76] = 1'b1;
  assign gate_ok[77] = 1'b1;
  assign gate_ok[78] = 1'b1;
  assign gate_ok[79] = 1'b1;
  assign gate_ok[80] = 1'b1;
  assign gate_ok[81] = 1'b1;
  assign gate_ok[82] = 1'b1;
  assign gate_ok[83] = 1'b1;
  assign gate_ok[84] = 1'b1;
  assign gate_ok[85] = 1'b1;
  assign gate_ok[86] = 1'b1;
  assign gate_ok[87] = 1'b1;
  assign gate_ok[88] = 1'b1;
  assign gate_ok[89] = 1'b1;
  assign gate_ok[90] = 1'b1;
  assign gate_ok[91] = 1'b1;
  assign gate_ok[92] = 1'b1;
  assign gate_ok[93] = 1'b1;
  assign gate_ok[94] = 1'b1;
  assign gate_ok[95] = 1'b1;
  assign gate_ok[96] = 1'b1;
  assign gate_ok[97] = 1'b1;
  assign gate_ok[98] = 1'b1;
  assign gate_ok[99] = 1'b1;
  assign gate_ok[100] = 1'b1;
  assign gate_ok[101] = 1'b1;
  assign gate_ok[102] = 1'b1;
  assign gate_ok[103] = 1'b1;
  assign gate_ok[104] = 1'b1;
  assign gate_ok[105] = 1'b1;
  assign gate_ok[106] = 1'b1;
  assign gate_ok[107] = 1'b1;
  assign gate_ok[108] = 1'b1;
  assign gate_ok[109] = 1'b1;
  assign gate_ok[110] = 1'b1;
  assign gate_ok[111] = 1'b1;
  assign gate_ok[112] = 1'b1;
  assign gate_ok[113] = 1'b1;
  assign gate_ok[114] = 1'b1;
  assign gate_ok[115] = 1'b1;
  assign gate_ok[116] = vector_doorbell_wgate_i[0 +: 1];
  assign gate_ok[117] = 1'b1;
  assign gate_ok[118] = 1'b1;
  assign gate_ok[119] = 1'b1;
  assign gate_ok[120] = 1'b1;
  assign gate_ok[121] = vector_cpl_pop_wgate_i[0 +: 1];
  assign gate_ok[122] = 1'b1;
  assign gate_ok[123] = 1'b1;
  assign gate_ok[124] = 1'b1;
  assign gate_ok[125] = 1'b1;
  assign gate_ok[126] = 1'b1;
  assign gate_ok[127] = 1'b1;
  assign gate_ok[128] = 1'b1;
  assign gate_ok[129] = 1'b1;
  assign gate_ok[130] = 1'b1;
  assign gate_ok[131] = 1'b1;
  assign gate_ok[132] = 1'b1;
  assign gate_ok[133] = 1'b1;
  assign gate_ok[134] = 1'b1;
  assign gate_ok[135] = 1'b1;
  assign gate_ok[136] = 1'b1;
  assign gate_ok[137] = 1'b1;
  assign gate_ok[138] = 1'b1;
  assign gate_ok[139] = 1'b1;
  assign gate_ok[140] = 1'b1;
  assign gate_ok[141] = 1'b1;
  assign gate_ok[142] = 1'b1;
  assign gate_ok[143] = 1'b1;
  assign gate_ok[144] = 1'b1;
  assign gate_ok[145] = 1'b1;
  assign gate_ok[146] = 1'b1;
  assign gate_ok[147] = 1'b1;
  assign gate_ok[148] = 1'b1;
  assign gate_ok[149] = 1'b1;
  assign gate_ok[150] = 1'b1;
  assign gate_ok[151] = 1'b1;
  assign gate_ok[152] = 1'b1;
  assign gate_ok[153] = 1'b1;
  assign gate_ok[154] = 1'b1;
  assign gate_ok[155] = 1'b1;
  assign gate_ok[156] = 1'b1;
  assign gate_ok[157] = 1'b1;
  assign gate_ok[158] = 1'b1;
  assign gate_ok[159] = 1'b1;
  assign gate_ok[160] = 1'b1;
  assign gate_ok[161] = 1'b1;
  assign gate_ok[162] = 1'b1;
  assign gate_ok[163] = 1'b1;
  assign gate_ok[164] = 1'b1;
  assign gate_ok[165] = 1'b1;
  assign gate_ok[166] = 1'b1;
  assign gate_ok[167] = 1'b1;
  assign gate_ok[168] = 1'b1;
  assign gate_ok[169] = 1'b1;
  assign gate_ok[170] = 1'b1;
  assign gate_ok[171] = 1'b1;
  assign gate_ok[172] = 1'b1;
  assign gate_ok[173] = 1'b1;
  assign gate_ok[174] = 1'b1;
  assign gate_ok[175] = 1'b1;
  assign gate_ok[176] = 1'b1;
  assign gate_ok[177] = 1'b1;
  assign gate_ok[178] = 1'b1;
  assign gate_ok[179] = 1'b1;
  assign gate_ok[180] = 1'b1;
  assign gate_ok[181] = 1'b1;
  assign gate_ok[182] = 1'b1;
  assign gate_ok[183] = 1'b1;
  assign gate_ok[184] = 1'b1;
  assign gate_ok[185] = 1'b1;
  assign gate_ok[186] = 1'b1;
  assign gate_ok[187] = 1'b1;
  assign gate_ok[188] = 1'b1;
  assign gate_ok[189] = 1'b1;
  assign gate_ok[190] = 1'b1;
  assign gate_ok[191] = 1'b1;
  assign gate_ok[192] = 1'b1;
  logic gate_fail;
  assign gate_fail = acc_is_write && (|(reg_sel & GATED & ~gate_ok));

  // ---- final status: ALP legality > decode/region/permission > hardware gate
  always_comb begin
    if (acc_legal != sf_albion_pkg::SF_ST_OKAY)       acc_status = acc_legal;
    else if (dec_status != sf_albion_pkg::SF_ST_OKAY) acc_status = dec_status;
    else if (gate_fail)                               acc_status = sf_albion_pkg::SF_ST_TARGET_ERR;
    else                                              acc_status = sf_albion_pkg::SF_ST_OKAY;
  end
  logic wr_commit, rd_commit;
  assign wr_commit = acc_valid && (acc_status == sf_albion_pkg::SF_ST_OKAY) && acc_is_write;
  assign rd_commit = acc_valid && (acc_status == sf_albion_pkg::SF_ST_OKAY) && acc_is_read;

  logic [127:0] rd_acc;
  logic [127:0] be_mask;
  always_comb begin
    for (int b = 0; b < 16; b++) be_mask[b*8 +: 8] = {8{acc_be[b]}};
  end

  // ======================================================================
  // r0: dma.SRC @ 64'h0000000120000000 (32-bit)
  // ======================================================================
  logic [31:0] r0_wdata, r0_wmask, r0_rdata;
  logic             r0_wr, r0_rd;
  assign r0_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r0_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r0_wr    = wr_commit && reg_sel[0];
  assign r0_rd    = rd_commit && reg_sel[0];
  // field VALUE [31:0] rw/none
  logic [31:0] r0_value_wb, r0_value_wm;
  assign r0_value_wb = r0_wdata[0 +: 32];
  assign r0_value_wm = r0_wmask[0 +: 32];
  logic [31:0] r0_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r0_value_q <= 32'h00000000;
    else if (r0_wr && (|r0_value_wm)) r0_value_q <= ((r0_value_q & ~r0_value_wm) | (r0_value_wb & r0_value_wm));
  end
  assign dma_src_value_o[0 +: 32] = r0_value_q;
  always_comb begin
    r0_rdata = 32'h0;
    r0_rdata[0 +: 32] = r0_value_q;
  end

  // ======================================================================
  // r1: dma.DST @ 64'h0000000120000004 (32-bit)
  // ======================================================================
  logic [31:0] r1_wdata, r1_wmask, r1_rdata;
  logic             r1_wr, r1_rd;
  assign r1_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r1_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r1_wr    = wr_commit && reg_sel[1];
  assign r1_rd    = rd_commit && reg_sel[1];
  // field VALUE [31:0] rw/none
  logic [31:0] r1_value_wb, r1_value_wm;
  assign r1_value_wb = r1_wdata[0 +: 32];
  assign r1_value_wm = r1_wmask[0 +: 32];
  logic [31:0] r1_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r1_value_q <= 32'h00000000;
    else if (r1_wr && (|r1_value_wm)) r1_value_q <= ((r1_value_q & ~r1_value_wm) | (r1_value_wb & r1_value_wm));
  end
  assign dma_dst_value_o[0 +: 32] = r1_value_q;
  always_comb begin
    r1_rdata = 32'h0;
    r1_rdata[0 +: 32] = r1_value_q;
  end

  // ======================================================================
  // r2: dma.LEN @ 64'h0000000120000008 (32-bit)
  // ======================================================================
  logic [31:0] r2_wdata, r2_wmask, r2_rdata;
  logic             r2_wr, r2_rd;
  assign r2_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r2_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r2_wr    = wr_commit && reg_sel[2];
  assign r2_rd    = rd_commit && reg_sel[2];
  // field VALUE [31:0] rw/none
  logic [31:0] r2_value_wb, r2_value_wm;
  assign r2_value_wb = r2_wdata[0 +: 32];
  assign r2_value_wm = r2_wmask[0 +: 32];
  logic [31:0] r2_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r2_value_q <= 32'h00000000;
    else if (r2_wr && (|r2_value_wm)) r2_value_q <= ((r2_value_q & ~r2_value_wm) | (r2_value_wb & r2_value_wm));
  end
  assign dma_len_value_o[0 +: 32] = r2_value_q;
  always_comb begin
    r2_rdata = 32'h0;
    r2_rdata[0 +: 32] = r2_value_q;
  end

  // ======================================================================
  // r3: dma.TAG @ 64'h000000012000000c (32-bit)
  // ======================================================================
  logic [31:0] r3_wdata, r3_wmask, r3_rdata;
  logic             r3_wr, r3_rd;
  assign r3_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r3_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r3_wr    = wr_commit && reg_sel[3];
  assign r3_rd    = rd_commit && reg_sel[3];
  // field TAG [7:0] rw/none
  logic [7:0] r3_tag_wb, r3_tag_wm;
  assign r3_tag_wb = r3_wdata[0 +: 8];
  assign r3_tag_wm = r3_wmask[0 +: 8];
  logic [7:0] r3_tag_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r3_tag_q <= 8'h00;
    else if (r3_wr && (|r3_tag_wm)) r3_tag_q <= ((r3_tag_q & ~r3_tag_wm) | (r3_tag_wb & r3_tag_wm));
  end
  assign dma_tag_tag_o[0 +: 8] = r3_tag_q;
  always_comb begin
    r3_rdata = 32'h0;
    r3_rdata[0 +: 8] = r3_tag_q;
  end

  // ======================================================================
  // r4: dma.CTRL @ 64'h0000000120000010 (32-bit)
  // ======================================================================
  logic [31:0] r4_wdata, r4_wmask, r4_rdata;
  logic             r4_wr, r4_rd;
  assign r4_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r4_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r4_wr    = wr_commit && reg_sel[4];
  assign r4_rd    = rd_commit && reg_sel[4];
  // field ABORT [0:0] rw/none
  logic [0:0] r4_abort_wb, r4_abort_wm;
  assign r4_abort_wb = r4_wdata[0 +: 1];
  assign r4_abort_wm = r4_wmask[0 +: 1];
  logic [0:0] r4_abort_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r4_abort_q <= 1'h0;
    else if (r4_wr && (|r4_abort_wm)) r4_abort_q <= ((r4_abort_q & ~r4_abort_wm) | (r4_abort_wb & r4_abort_wm));
  end
  assign dma_ctrl_abort_o[0 +: 1] = r4_abort_q;
  always_comb begin
    r4_rdata = 32'h0;
    r4_rdata[0 +: 1] = r4_abort_q;
  end

  // ======================================================================
  // r5: dma.START @ 64'h0000000120000014 (32-bit)
  // ======================================================================
  logic [31:0] r5_wdata, r5_wmask, r5_rdata;
  logic             r5_wr, r5_rd;
  assign r5_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r5_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r5_wr    = wr_commit && reg_sel[5];
  assign r5_rd    = rd_commit && reg_sel[5];
  // field GO [31:0] wo/none
  logic [31:0] r5_go_wb, r5_go_wm;
  assign r5_go_wb = r5_wdata[0 +: 32];
  assign r5_go_wm = r5_wmask[0 +: 32];
  logic r5_wr_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r5_wr_q <= 1'b0;
    else r5_wr_q <= r5_wr;
  end
  assign dma_start_wr_o[0 +: 1] = r5_wr_q;
  always_comb begin
    r5_rdata = 32'h0;
  end

  // ======================================================================
  // r6: dma.STATUS @ 64'h0000000120000018 (32-bit)
  // ======================================================================
  logic [31:0] r6_wdata, r6_wmask, r6_rdata;
  logic             r6_wr, r6_rd;
  assign r6_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r6_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r6_wr    = wr_commit && reg_sel[6];
  assign r6_rd    = rd_commit && reg_sel[6];
  // field BUSY [0:0] ro/input
  logic [0:0] r6_busy_wb, r6_busy_wm;
  assign r6_busy_wb = r6_wdata[0 +: 1];
  assign r6_busy_wm = r6_wmask[0 +: 1];
  // field ACTIVE [1:1] ro/input
  logic [0:0] r6_active_wb, r6_active_wm;
  assign r6_active_wb = r6_wdata[1 +: 1];
  assign r6_active_wm = r6_wmask[1 +: 1];
  // field CTL_STATE [3:2] ro/input
  logic [1:0] r6_ctl_state_wb, r6_ctl_state_wm;
  assign r6_ctl_state_wb = r6_wdata[2 +: 2];
  assign r6_ctl_state_wm = r6_wmask[2 +: 2];
  // field ENG_STATE [6:4] ro/input
  logic [2:0] r6_eng_state_wb, r6_eng_state_wm;
  assign r6_eng_state_wb = r6_wdata[4 +: 3];
  assign r6_eng_state_wm = r6_wmask[4 +: 3];
  // field CUR_TAG [15:8] ro/input
  logic [7:0] r6_cur_tag_wb, r6_cur_tag_wm;
  assign r6_cur_tag_wb = r6_wdata[8 +: 8];
  assign r6_cur_tag_wm = r6_wmask[8 +: 8];
  // field FIFO_LEVEL [23:16] ro/input
  logic [7:0] r6_fifo_level_wb, r6_fifo_level_wm;
  assign r6_fifo_level_wb = r6_wdata[16 +: 8];
  assign r6_fifo_level_wm = r6_wmask[16 +: 8];
  always_comb begin
    r6_rdata = 32'h0;
    r6_rdata[0 +: 1] = dma_status_busy_i[0 +: 1];
    r6_rdata[1 +: 1] = dma_status_active_i[0 +: 1];
    r6_rdata[2 +: 2] = dma_status_ctl_state_i[0 +: 2];
    r6_rdata[4 +: 3] = dma_status_eng_state_i[0 +: 3];
    r6_rdata[8 +: 8] = dma_status_cur_tag_i[0 +: 8];
    r6_rdata[16 +: 8] = dma_status_fifo_level_i[0 +: 8];
  end

  // ======================================================================
  // r7: dma.BYTES_DONE @ 64'h000000012000001c (32-bit)
  // ======================================================================
  logic [31:0] r7_wdata, r7_wmask, r7_rdata;
  logic             r7_wr, r7_rd;
  assign r7_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r7_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r7_wr    = wr_commit && reg_sel[7];
  assign r7_rd    = rd_commit && reg_sel[7];
  // field VALUE [31:0] ro/input
  logic [31:0] r7_value_wb, r7_value_wm;
  assign r7_value_wb = r7_wdata[0 +: 32];
  assign r7_value_wm = r7_wmask[0 +: 32];
  always_comb begin
    r7_rdata = 32'h0;
    r7_rdata[0 +: 32] = dma_bytes_done_value_i[0 +: 32];
  end

  // ======================================================================
  // r8: dma.CPL_STATUS @ 64'h0000000120000020 (32-bit)
  // ======================================================================
  logic [31:0] r8_wdata, r8_wmask, r8_rdata;
  logic             r8_wr, r8_rd;
  assign r8_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r8_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r8_wr    = wr_commit && reg_sel[8];
  assign r8_rd    = rd_commit && reg_sel[8];
  // field VALID [0:0] ro/input
  logic [0:0] r8_valid_wb, r8_valid_wm;
  assign r8_valid_wb = r8_wdata[0 +: 1];
  assign r8_valid_wm = r8_wmask[0 +: 1];
  // field ERR [1:1] ro/input
  logic [0:0] r8_err_wb, r8_err_wm;
  assign r8_err_wb = r8_wdata[1 +: 1];
  assign r8_err_wm = r8_wmask[1 +: 1];
  // field CODE [7:4] ro/input
  logic [3:0] r8_code_wb, r8_code_wm;
  assign r8_code_wb = r8_wdata[4 +: 4];
  assign r8_code_wm = r8_wmask[4 +: 4];
  // field TAG [15:8] ro/input
  logic [7:0] r8_tag_wb, r8_tag_wm;
  assign r8_tag_wb = r8_wdata[8 +: 8];
  assign r8_tag_wm = r8_wmask[8 +: 8];
  always_comb begin
    r8_rdata = 32'h0;
    r8_rdata[0 +: 1] = dma_cpl_status_valid_i[0 +: 1];
    r8_rdata[1 +: 1] = dma_cpl_status_err_i[0 +: 1];
    r8_rdata[4 +: 4] = dma_cpl_status_code_i[0 +: 4];
    r8_rdata[8 +: 8] = dma_cpl_status_tag_i[0 +: 8];
  end

  // ======================================================================
  // r9: dma.CPL_ERR_ADDR @ 64'h0000000120000024 (32-bit)
  // ======================================================================
  logic [31:0] r9_wdata, r9_wmask, r9_rdata;
  logic             r9_wr, r9_rd;
  assign r9_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r9_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r9_wr    = wr_commit && reg_sel[9];
  assign r9_rd    = rd_commit && reg_sel[9];
  // field VALUE [31:0] ro/input
  logic [31:0] r9_value_wb, r9_value_wm;
  assign r9_value_wb = r9_wdata[0 +: 32];
  assign r9_value_wm = r9_wmask[0 +: 32];
  always_comb begin
    r9_rdata = 32'h0;
    r9_rdata[0 +: 32] = dma_cpl_err_addr_value_i[0 +: 32];
  end

  // ======================================================================
  // r10: dma.CPL_BYTES @ 64'h0000000120000028 (32-bit)
  // ======================================================================
  logic [31:0] r10_wdata, r10_wmask, r10_rdata;
  logic             r10_wr, r10_rd;
  assign r10_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r10_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r10_wr    = wr_commit && reg_sel[10];
  assign r10_rd    = rd_commit && reg_sel[10];
  // field VALUE [31:0] ro/input
  logic [31:0] r10_value_wb, r10_value_wm;
  assign r10_value_wb = r10_wdata[0 +: 32];
  assign r10_value_wm = r10_wmask[0 +: 32];
  always_comb begin
    r10_rdata = 32'h0;
    r10_rdata[0 +: 32] = dma_cpl_bytes_value_i[0 +: 32];
  end

  // ======================================================================
  // r11: dma.CPL_POP @ 64'h000000012000002c (32-bit)
  // ======================================================================
  logic [31:0] r11_wdata, r11_wmask, r11_rdata;
  logic             r11_wr, r11_rd;
  assign r11_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r11_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r11_wr    = wr_commit && reg_sel[11];
  assign r11_rd    = rd_commit && reg_sel[11];
  // field POP [31:0] wo/none
  logic [31:0] r11_pop_wb, r11_pop_wm;
  assign r11_pop_wb = r11_wdata[0 +: 32];
  assign r11_pop_wm = r11_wmask[0 +: 32];
  logic r11_wr_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r11_wr_q <= 1'b0;
    else r11_wr_q <= r11_wr;
  end
  assign dma_cpl_pop_wr_o[0 +: 1] = r11_wr_q;
  always_comb begin
    r11_rdata = 32'h0;
  end

  // ======================================================================
  // r12: dma.PERF_CTRL @ 64'h0000000120000030 (32-bit)
  // ======================================================================
  logic [31:0] r12_wdata, r12_wmask, r12_rdata;
  logic             r12_wr, r12_rd;
  assign r12_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r12_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r12_wr    = wr_commit && reg_sel[12];
  assign r12_rd    = rd_commit && reg_sel[12];
  // field CLEAR [0:0] w1p
  logic [0:0] r12_clear_wb, r12_clear_wm;
  assign r12_clear_wb = r12_wdata[0 +: 1];
  assign r12_clear_wm = r12_wmask[0 +: 1];
  logic [0:0] r12_clear_pulse_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r12_clear_pulse_q <= 1'h0;
    else r12_clear_pulse_q <= {1{r12_wr}} & r12_clear_wb & r12_clear_wm;
  end
  assign dma_perf_ctrl_clear_pulse_o[0 +: 1] = r12_clear_pulse_q;
  always_comb begin
    r12_rdata = 32'h0;
  end

  // ======================================================================
  // r13: dma.INT_ENABLE @ 64'h0000000120000034 (32-bit)
  // ======================================================================
  logic [31:0] r13_wdata, r13_wmask, r13_rdata;
  logic             r13_wr, r13_rd;
  assign r13_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r13_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r13_wr    = wr_commit && reg_sel[13];
  assign r13_rd    = rd_commit && reg_sel[13];
  // field CPL [0:0] rw/none
  logic [0:0] r13_cpl_wb, r13_cpl_wm;
  assign r13_cpl_wb = r13_wdata[0 +: 1];
  assign r13_cpl_wm = r13_wmask[0 +: 1];
  logic [0:0] r13_cpl_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r13_cpl_q <= 1'h0;
    else if (r13_wr && (|r13_cpl_wm)) r13_cpl_q <= ((r13_cpl_q & ~r13_cpl_wm) | (r13_cpl_wb & r13_cpl_wm));
  end
  assign dma_int_enable_cpl_o[0 +: 1] = r13_cpl_q;
  // field CPL_ERR [1:1] rw/none
  logic [0:0] r13_cpl_err_wb, r13_cpl_err_wm;
  assign r13_cpl_err_wb = r13_wdata[1 +: 1];
  assign r13_cpl_err_wm = r13_wmask[1 +: 1];
  logic [0:0] r13_cpl_err_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r13_cpl_err_q <= 1'h0;
    else if (r13_wr && (|r13_cpl_err_wm)) r13_cpl_err_q <= ((r13_cpl_err_q & ~r13_cpl_err_wm) | (r13_cpl_err_wb & r13_cpl_err_wm));
  end
  assign dma_int_enable_cpl_err_o[0 +: 1] = r13_cpl_err_q;
  // field BUS_ERR [2:2] rw/none
  logic [0:0] r13_bus_err_wb, r13_bus_err_wm;
  assign r13_bus_err_wb = r13_wdata[2 +: 1];
  assign r13_bus_err_wm = r13_wmask[2 +: 1];
  logic [0:0] r13_bus_err_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r13_bus_err_q <= 1'h0;
    else if (r13_wr && (|r13_bus_err_wm)) r13_bus_err_q <= ((r13_bus_err_q & ~r13_bus_err_wm) | (r13_bus_err_wb & r13_bus_err_wm));
  end
  assign dma_int_enable_bus_err_o[0 +: 1] = r13_bus_err_q;
  // field TAG_ERR [3:3] rw/none
  logic [0:0] r13_tag_err_wb, r13_tag_err_wm;
  assign r13_tag_err_wb = r13_wdata[3 +: 1];
  assign r13_tag_err_wm = r13_wmask[3 +: 1];
  logic [0:0] r13_tag_err_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r13_tag_err_q <= 1'h0;
    else if (r13_wr && (|r13_tag_err_wm)) r13_tag_err_q <= ((r13_tag_err_q & ~r13_tag_err_wm) | (r13_tag_err_wb & r13_tag_err_wm));
  end
  assign dma_int_enable_tag_err_o[0 +: 1] = r13_tag_err_q;
  always_comb begin
    r13_rdata = 32'h0;
    r13_rdata[0 +: 1] = r13_cpl_q;
    r13_rdata[1 +: 1] = r13_cpl_err_q;
    r13_rdata[2 +: 1] = r13_bus_err_q;
    r13_rdata[3 +: 1] = r13_tag_err_q;
  end

  // ======================================================================
  // r14: dma.INT_STATUS @ 64'h0000000120000038 (32-bit)
  // ======================================================================
  logic [31:0] r14_wdata, r14_wmask, r14_rdata;
  logic             r14_wr, r14_rd;
  assign r14_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r14_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r14_wr    = wr_commit && reg_sel[14];
  assign r14_rd    = rd_commit && reg_sel[14];
  // field CPL [0:0] w1c/event
  logic [0:0] r14_cpl_wb, r14_cpl_wm;
  assign r14_cpl_wb = r14_wdata[0 +: 1];
  assign r14_cpl_wm = r14_wmask[0 +: 1];
  logic [0:0] r14_cpl_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r14_cpl_q <= 1'h0;
    else r14_cpl_q <= ((r14_cpl_q & ~({1{r14_wr}} & r14_cpl_wb & r14_cpl_wm)) | dma_int_status_cpl_set_i[0 +: 1]);
  end
  assign dma_int_status_cpl_o[0 +: 1] = r14_cpl_q;
  // field CPL_ERR [1:1] w1c/event
  logic [0:0] r14_cpl_err_wb, r14_cpl_err_wm;
  assign r14_cpl_err_wb = r14_wdata[1 +: 1];
  assign r14_cpl_err_wm = r14_wmask[1 +: 1];
  logic [0:0] r14_cpl_err_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r14_cpl_err_q <= 1'h0;
    else r14_cpl_err_q <= ((r14_cpl_err_q & ~({1{r14_wr}} & r14_cpl_err_wb & r14_cpl_err_wm)) | dma_int_status_cpl_err_set_i[0 +: 1]);
  end
  assign dma_int_status_cpl_err_o[0 +: 1] = r14_cpl_err_q;
  // field BUS_ERR [2:2] w1c/event
  logic [0:0] r14_bus_err_wb, r14_bus_err_wm;
  assign r14_bus_err_wb = r14_wdata[2 +: 1];
  assign r14_bus_err_wm = r14_wmask[2 +: 1];
  logic [0:0] r14_bus_err_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r14_bus_err_q <= 1'h0;
    else r14_bus_err_q <= ((r14_bus_err_q & ~({1{r14_wr}} & r14_bus_err_wb & r14_bus_err_wm)) | dma_int_status_bus_err_set_i[0 +: 1]);
  end
  assign dma_int_status_bus_err_o[0 +: 1] = r14_bus_err_q;
  // field TAG_ERR [3:3] w1c/event
  logic [0:0] r14_tag_err_wb, r14_tag_err_wm;
  assign r14_tag_err_wb = r14_wdata[3 +: 1];
  assign r14_tag_err_wm = r14_wmask[3 +: 1];
  logic [0:0] r14_tag_err_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r14_tag_err_q <= 1'h0;
    else r14_tag_err_q <= ((r14_tag_err_q & ~({1{r14_wr}} & r14_tag_err_wb & r14_tag_err_wm)) | dma_int_status_tag_err_set_i[0 +: 1]);
  end
  assign dma_int_status_tag_err_o[0 +: 1] = r14_tag_err_q;
  always_comb begin
    r14_rdata = 32'h0;
    r14_rdata[0 +: 1] = r14_cpl_q;
    r14_rdata[1 +: 1] = r14_cpl_err_q;
    r14_rdata[2 +: 1] = r14_bus_err_q;
    r14_rdata[3 +: 1] = r14_tag_err_q;
  end

  // ======================================================================
  // r15: dma.PERF[0] @ 64'h0000000120000040 (32-bit)
  // ======================================================================
  logic [31:0] r15_wdata, r15_wmask, r15_rdata;
  logic             r15_wr, r15_rd;
  assign r15_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r15_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r15_wr    = wr_commit && reg_sel[15];
  assign r15_rd    = rd_commit && reg_sel[15];
  // field VALUE [31:0] ro/input
  logic [31:0] r15_value_wb, r15_value_wm;
  assign r15_value_wb = r15_wdata[0 +: 32];
  assign r15_value_wm = r15_wmask[0 +: 32];
  always_comb begin
    r15_rdata = 32'h0;
    r15_rdata[0 +: 32] = dma_perf_value_i[0 +: 32];
  end

  // ======================================================================
  // r16: dma.PERF[1] @ 64'h0000000120000044 (32-bit)
  // ======================================================================
  logic [31:0] r16_wdata, r16_wmask, r16_rdata;
  logic             r16_wr, r16_rd;
  assign r16_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r16_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r16_wr    = wr_commit && reg_sel[16];
  assign r16_rd    = rd_commit && reg_sel[16];
  // field VALUE [31:0] ro/input
  logic [31:0] r16_value_wb, r16_value_wm;
  assign r16_value_wb = r16_wdata[0 +: 32];
  assign r16_value_wm = r16_wmask[0 +: 32];
  always_comb begin
    r16_rdata = 32'h0;
    r16_rdata[0 +: 32] = dma_perf_value_i[32 +: 32];
  end

  // ======================================================================
  // r17: dma.PERF[2] @ 64'h0000000120000048 (32-bit)
  // ======================================================================
  logic [31:0] r17_wdata, r17_wmask, r17_rdata;
  logic             r17_wr, r17_rd;
  assign r17_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r17_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r17_wr    = wr_commit && reg_sel[17];
  assign r17_rd    = rd_commit && reg_sel[17];
  // field VALUE [31:0] ro/input
  logic [31:0] r17_value_wb, r17_value_wm;
  assign r17_value_wb = r17_wdata[0 +: 32];
  assign r17_value_wm = r17_wmask[0 +: 32];
  always_comb begin
    r17_rdata = 32'h0;
    r17_rdata[0 +: 32] = dma_perf_value_i[64 +: 32];
  end

  // ======================================================================
  // r18: dma.PERF[3] @ 64'h000000012000004c (32-bit)
  // ======================================================================
  logic [31:0] r18_wdata, r18_wmask, r18_rdata;
  logic             r18_wr, r18_rd;
  assign r18_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r18_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r18_wr    = wr_commit && reg_sel[18];
  assign r18_rd    = rd_commit && reg_sel[18];
  // field VALUE [31:0] ro/input
  logic [31:0] r18_value_wb, r18_value_wm;
  assign r18_value_wb = r18_wdata[0 +: 32];
  assign r18_value_wm = r18_wmask[0 +: 32];
  always_comb begin
    r18_rdata = 32'h0;
    r18_rdata[0 +: 32] = dma_perf_value_i[96 +: 32];
  end

  // ======================================================================
  // r19: dma.PERF[4] @ 64'h0000000120000050 (32-bit)
  // ======================================================================
  logic [31:0] r19_wdata, r19_wmask, r19_rdata;
  logic             r19_wr, r19_rd;
  assign r19_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r19_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r19_wr    = wr_commit && reg_sel[19];
  assign r19_rd    = rd_commit && reg_sel[19];
  // field VALUE [31:0] ro/input
  logic [31:0] r19_value_wb, r19_value_wm;
  assign r19_value_wb = r19_wdata[0 +: 32];
  assign r19_value_wm = r19_wmask[0 +: 32];
  always_comb begin
    r19_rdata = 32'h0;
    r19_rdata[0 +: 32] = dma_perf_value_i[128 +: 32];
  end

  // ======================================================================
  // r20: dma.PERF[5] @ 64'h0000000120000054 (32-bit)
  // ======================================================================
  logic [31:0] r20_wdata, r20_wmask, r20_rdata;
  logic             r20_wr, r20_rd;
  assign r20_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r20_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r20_wr    = wr_commit && reg_sel[20];
  assign r20_rd    = rd_commit && reg_sel[20];
  // field VALUE [31:0] ro/input
  logic [31:0] r20_value_wb, r20_value_wm;
  assign r20_value_wb = r20_wdata[0 +: 32];
  assign r20_value_wm = r20_wmask[0 +: 32];
  always_comb begin
    r20_rdata = 32'h0;
    r20_rdata[0 +: 32] = dma_perf_value_i[160 +: 32];
  end

  // ======================================================================
  // r21: dma.PERF[6] @ 64'h0000000120000058 (32-bit)
  // ======================================================================
  logic [31:0] r21_wdata, r21_wmask, r21_rdata;
  logic             r21_wr, r21_rd;
  assign r21_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r21_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r21_wr    = wr_commit && reg_sel[21];
  assign r21_rd    = rd_commit && reg_sel[21];
  // field VALUE [31:0] ro/input
  logic [31:0] r21_value_wb, r21_value_wm;
  assign r21_value_wb = r21_wdata[0 +: 32];
  assign r21_value_wm = r21_wmask[0 +: 32];
  always_comb begin
    r21_rdata = 32'h0;
    r21_rdata[0 +: 32] = dma_perf_value_i[192 +: 32];
  end

  // ======================================================================
  // r22: dma.PERF[7] @ 64'h000000012000005c (32-bit)
  // ======================================================================
  logic [31:0] r22_wdata, r22_wmask, r22_rdata;
  logic             r22_wr, r22_rd;
  assign r22_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r22_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r22_wr    = wr_commit && reg_sel[22];
  assign r22_rd    = rd_commit && reg_sel[22];
  // field VALUE [31:0] ro/input
  logic [31:0] r22_value_wb, r22_value_wm;
  assign r22_value_wb = r22_wdata[0 +: 32];
  assign r22_value_wm = r22_wmask[0 +: 32];
  always_comb begin
    r22_rdata = 32'h0;
    r22_rdata[0 +: 32] = dma_perf_value_i[224 +: 32];
  end

  // ======================================================================
  // r23: dma.PERF[8] @ 64'h0000000120000060 (32-bit)
  // ======================================================================
  logic [31:0] r23_wdata, r23_wmask, r23_rdata;
  logic             r23_wr, r23_rd;
  assign r23_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r23_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r23_wr    = wr_commit && reg_sel[23];
  assign r23_rd    = rd_commit && reg_sel[23];
  // field VALUE [31:0] ro/input
  logic [31:0] r23_value_wb, r23_value_wm;
  assign r23_value_wb = r23_wdata[0 +: 32];
  assign r23_value_wm = r23_wmask[0 +: 32];
  always_comb begin
    r23_rdata = 32'h0;
    r23_rdata[0 +: 32] = dma_perf_value_i[256 +: 32];
  end

  // ======================================================================
  // r24: dma.PERF[9] @ 64'h0000000120000064 (32-bit)
  // ======================================================================
  logic [31:0] r24_wdata, r24_wmask, r24_rdata;
  logic             r24_wr, r24_rd;
  assign r24_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r24_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r24_wr    = wr_commit && reg_sel[24];
  assign r24_rd    = rd_commit && reg_sel[24];
  // field VALUE [31:0] ro/input
  logic [31:0] r24_value_wb, r24_value_wm;
  assign r24_value_wb = r24_wdata[0 +: 32];
  assign r24_value_wm = r24_wmask[0 +: 32];
  always_comb begin
    r24_rdata = 32'h0;
    r24_rdata[0 +: 32] = dma_perf_value_i[288 +: 32];
  end

  // ======================================================================
  // r25: dma.PERF[10] @ 64'h0000000120000068 (32-bit)
  // ======================================================================
  logic [31:0] r25_wdata, r25_wmask, r25_rdata;
  logic             r25_wr, r25_rd;
  assign r25_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r25_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r25_wr    = wr_commit && reg_sel[25];
  assign r25_rd    = rd_commit && reg_sel[25];
  // field VALUE [31:0] ro/input
  logic [31:0] r25_value_wb, r25_value_wm;
  assign r25_value_wb = r25_wdata[0 +: 32];
  assign r25_value_wm = r25_wmask[0 +: 32];
  always_comb begin
    r25_rdata = 32'h0;
    r25_rdata[0 +: 32] = dma_perf_value_i[320 +: 32];
  end

  // ======================================================================
  // r26: dma.PERF[11] @ 64'h000000012000006c (32-bit)
  // ======================================================================
  logic [31:0] r26_wdata, r26_wmask, r26_rdata;
  logic             r26_wr, r26_rd;
  assign r26_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r26_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r26_wr    = wr_commit && reg_sel[26];
  assign r26_rd    = rd_commit && reg_sel[26];
  // field VALUE [31:0] ro/input
  logic [31:0] r26_value_wb, r26_value_wm;
  assign r26_value_wb = r26_wdata[0 +: 32];
  assign r26_value_wm = r26_wmask[0 +: 32];
  always_comb begin
    r26_rdata = 32'h0;
    r26_rdata[0 +: 32] = dma_perf_value_i[352 +: 32];
  end

  // ======================================================================
  // r27: dma.PERF[12] @ 64'h0000000120000070 (32-bit)
  // ======================================================================
  logic [31:0] r27_wdata, r27_wmask, r27_rdata;
  logic             r27_wr, r27_rd;
  assign r27_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r27_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r27_wr    = wr_commit && reg_sel[27];
  assign r27_rd    = rd_commit && reg_sel[27];
  // field VALUE [31:0] ro/input
  logic [31:0] r27_value_wb, r27_value_wm;
  assign r27_value_wb = r27_wdata[0 +: 32];
  assign r27_value_wm = r27_wmask[0 +: 32];
  always_comb begin
    r27_rdata = 32'h0;
    r27_rdata[0 +: 32] = dma_perf_value_i[384 +: 32];
  end

  // ======================================================================
  // r28: dma.PERF[13] @ 64'h0000000120000074 (32-bit)
  // ======================================================================
  logic [31:0] r28_wdata, r28_wmask, r28_rdata;
  logic             r28_wr, r28_rd;
  assign r28_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r28_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r28_wr    = wr_commit && reg_sel[28];
  assign r28_rd    = rd_commit && reg_sel[28];
  // field VALUE [31:0] ro/input
  logic [31:0] r28_value_wb, r28_value_wm;
  assign r28_value_wb = r28_wdata[0 +: 32];
  assign r28_value_wm = r28_wmask[0 +: 32];
  always_comb begin
    r28_rdata = 32'h0;
    r28_rdata[0 +: 32] = dma_perf_value_i[416 +: 32];
  end

  // ======================================================================
  // r29: dma.PERF[14] @ 64'h0000000120000078 (32-bit)
  // ======================================================================
  logic [31:0] r29_wdata, r29_wmask, r29_rdata;
  logic             r29_wr, r29_rd;
  assign r29_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r29_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r29_wr    = wr_commit && reg_sel[29];
  assign r29_rd    = rd_commit && reg_sel[29];
  // field VALUE [31:0] ro/input
  logic [31:0] r29_value_wb, r29_value_wm;
  assign r29_value_wb = r29_wdata[0 +: 32];
  assign r29_value_wm = r29_wmask[0 +: 32];
  always_comb begin
    r29_rdata = 32'h0;
    r29_rdata[0 +: 32] = dma_perf_value_i[448 +: 32];
  end

  // ======================================================================
  // r30: dma.PERF[15] @ 64'h000000012000007c (32-bit)
  // ======================================================================
  logic [31:0] r30_wdata, r30_wmask, r30_rdata;
  logic             r30_wr, r30_rd;
  assign r30_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r30_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r30_wr    = wr_commit && reg_sel[30];
  assign r30_rd    = rd_commit && reg_sel[30];
  // field VALUE [31:0] ro/input
  logic [31:0] r30_value_wb, r30_value_wm;
  assign r30_value_wb = r30_wdata[0 +: 32];
  assign r30_value_wm = r30_wmask[0 +: 32];
  always_comb begin
    r30_rdata = 32'h0;
    r30_rdata[0 +: 32] = dma_perf_value_i[480 +: 32];
  end

  // ======================================================================
  // r31: tensor.ID @ 64'h0000000150000000 (32-bit)
  // ======================================================================
  logic [31:0] r31_wdata, r31_wmask, r31_rdata;
  logic             r31_wr, r31_rd;
  assign r31_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r31_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r31_wr    = wr_commit && reg_sel[31];
  assign r31_rd    = rd_commit && reg_sel[31];
  // field VALUE [31:0] ro/const
  logic [31:0] r31_value_wb, r31_value_wm;
  assign r31_value_wb = r31_wdata[0 +: 32];
  assign r31_value_wm = r31_wmask[0 +: 32];
  always_comb begin
    r31_rdata = 32'h0;
    r31_rdata[0 +: 32] = 32'h53465443;
  end

  // ======================================================================
  // r32: tensor.INFO @ 64'h0000000150000004 (32-bit)
  // ======================================================================
  logic [31:0] r32_wdata, r32_wmask, r32_rdata;
  logic             r32_wr, r32_rd;
  assign r32_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r32_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r32_wr    = wr_commit && reg_sel[32];
  assign r32_rd    = rd_commit && reg_sel[32];
  // field ABI_VERSION [3:0] ro/input
  logic [3:0] r32_abi_version_wb, r32_abi_version_wm;
  assign r32_abi_version_wb = r32_wdata[0 +: 4];
  assign r32_abi_version_wm = r32_wmask[0 +: 4];
  // field LOG2_QUEUE_DEPTH [7:4] ro/input
  logic [3:0] r32_log2_queue_depth_wb, r32_log2_queue_depth_wm;
  assign r32_log2_queue_depth_wb = r32_wdata[4 +: 4];
  assign r32_log2_queue_depth_wm = r32_wmask[4 +: 4];
  // field ARRAY_ROWS [15:8] ro/input
  logic [7:0] r32_array_rows_wb, r32_array_rows_wm;
  assign r32_array_rows_wb = r32_wdata[8 +: 8];
  assign r32_array_rows_wm = r32_wmask[8 +: 8];
  // field ARRAY_COLS [23:16] ro/input
  logic [7:0] r32_array_cols_wb, r32_array_cols_wm;
  assign r32_array_cols_wb = r32_wdata[16 +: 8];
  assign r32_array_cols_wm = r32_wmask[16 +: 8];
  // field ENABLE_QUANTIZATION [24:24] ro/input
  logic [0:0] r32_enable_quantization_wb, r32_enable_quantization_wm;
  assign r32_enable_quantization_wb = r32_wdata[24 +: 1];
  assign r32_enable_quantization_wm = r32_wmask[24 +: 1];
  // field ENABLE_DOUBLE_BUFFERING [25:25] ro/input
  logic [0:0] r32_enable_double_buffering_wb, r32_enable_double_buffering_wm;
  assign r32_enable_double_buffering_wb = r32_wdata[25 +: 1];
  assign r32_enable_double_buffering_wm = r32_wmask[25 +: 1];
  // field PERF_EN [26:26] ro/input
  logic [0:0] r32_perf_en_wb, r32_perf_en_wm;
  assign r32_perf_en_wb = r32_wdata[26 +: 1];
  assign r32_perf_en_wm = r32_wmask[26 +: 1];
  always_comb begin
    r32_rdata = 32'h0;
    r32_rdata[0 +: 4] = tensor_info_abi_version_i[0 +: 4];
    r32_rdata[4 +: 4] = tensor_info_log2_queue_depth_i[0 +: 4];
    r32_rdata[8 +: 8] = tensor_info_array_rows_i[0 +: 8];
    r32_rdata[16 +: 8] = tensor_info_array_cols_i[0 +: 8];
    r32_rdata[24 +: 1] = tensor_info_enable_quantization_i[0 +: 1];
    r32_rdata[25 +: 1] = tensor_info_enable_double_buffering_i[0 +: 1];
    r32_rdata[26 +: 1] = tensor_info_perf_en_i[0 +: 1];
  end

  // ======================================================================
  // r33: tensor.CAPS @ 64'h0000000150000008 (32-bit)
  // ======================================================================
  logic [31:0] r33_wdata, r33_wmask, r33_rdata;
  logic             r33_wr, r33_rd;
  assign r33_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r33_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r33_wr    = wr_commit && reg_sel[33];
  assign r33_rd    = rd_commit && reg_sel[33];
  // field TILE_K [15:0] ro/input
  logic [15:0] r33_tile_k_wb, r33_tile_k_wm;
  assign r33_tile_k_wb = r33_wdata[0 +: 16];
  assign r33_tile_k_wm = r33_wmask[0 +: 16];
  // field DATA_WIDTH [23:16] ro/input
  logic [7:0] r33_data_width_wb, r33_data_width_wm;
  assign r33_data_width_wb = r33_wdata[16 +: 8];
  assign r33_data_width_wm = r33_wmask[16 +: 8];
  // field ACC_WIDTH [31:24] ro/input
  logic [7:0] r33_acc_width_wb, r33_acc_width_wm;
  assign r33_acc_width_wb = r33_wdata[24 +: 8];
  assign r33_acc_width_wm = r33_wmask[24 +: 8];
  always_comb begin
    r33_rdata = 32'h0;
    r33_rdata[0 +: 16] = tensor_caps_tile_k_i[0 +: 16];
    r33_rdata[16 +: 8] = tensor_caps_data_width_i[0 +: 8];
    r33_rdata[24 +: 8] = tensor_caps_acc_width_i[0 +: 8];
  end

  // ======================================================================
  // r34: tensor.OPBUF @ 64'h000000015000000c (32-bit)
  // ======================================================================
  logic [31:0] r34_wdata, r34_wmask, r34_rdata;
  logic             r34_wr, r34_rd;
  assign r34_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r34_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r34_wr    = wr_commit && reg_sel[34];
  assign r34_rd    = rd_commit && reg_sel[34];
  // field VALUE [31:0] ro/input
  logic [31:0] r34_value_wb, r34_value_wm;
  assign r34_value_wb = r34_wdata[0 +: 32];
  assign r34_value_wm = r34_wmask[0 +: 32];
  always_comb begin
    r34_rdata = 32'h0;
    r34_rdata[0 +: 32] = tensor_opbuf_value_i[0 +: 32];
  end

  // ======================================================================
  // r35: tensor.MEM_LO @ 64'h0000000150000010 (32-bit)
  // ======================================================================
  logic [31:0] r35_wdata, r35_wmask, r35_rdata;
  logic             r35_wr, r35_rd;
  assign r35_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r35_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r35_wr    = wr_commit && reg_sel[35];
  assign r35_rd    = rd_commit && reg_sel[35];
  // field VALUE [31:0] ro/input
  logic [31:0] r35_value_wb, r35_value_wm;
  assign r35_value_wb = r35_wdata[0 +: 32];
  assign r35_value_wm = r35_wmask[0 +: 32];
  always_comb begin
    r35_rdata = 32'h0;
    r35_rdata[0 +: 32] = tensor_mem_lo_value_i[0 +: 32];
  end

  // ======================================================================
  // r36: tensor.MEM_LAST @ 64'h0000000150000014 (32-bit)
  // ======================================================================
  logic [31:0] r36_wdata, r36_wmask, r36_rdata;
  logic             r36_wr, r36_rd;
  assign r36_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r36_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r36_wr    = wr_commit && reg_sel[36];
  assign r36_rd    = rd_commit && reg_sel[36];
  // field VALUE [31:0] ro/input
  logic [31:0] r36_value_wb, r36_value_wm;
  assign r36_value_wb = r36_wdata[0 +: 32];
  assign r36_value_wm = r36_wmask[0 +: 32];
  always_comb begin
    r36_rdata = 32'h0;
    r36_rdata[0 +: 32] = tensor_mem_last_value_i[0 +: 32];
  end

  // ======================================================================
  // r37: tensor.CTRL @ 64'h0000000150000018 (32-bit)
  // ======================================================================
  logic [31:0] r37_wdata, r37_wmask, r37_rdata;
  logic             r37_wr, r37_rd;
  assign r37_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r37_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r37_wr    = wr_commit && reg_sel[37];
  assign r37_rd    = rd_commit && reg_sel[37];
  // field ERR_CONT [0:0] rw/none
  logic [0:0] r37_err_cont_wb, r37_err_cont_wm;
  assign r37_err_cont_wb = r37_wdata[0 +: 1];
  assign r37_err_cont_wm = r37_wmask[0 +: 1];
  logic [0:0] r37_err_cont_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r37_err_cont_q <= 1'h0;
    else if (r37_wr && (|r37_err_cont_wm)) r37_err_cont_q <= ((r37_err_cont_q & ~r37_err_cont_wm) | (r37_err_cont_wb & r37_err_cont_wm));
  end
  assign tensor_ctrl_err_cont_o[0 +: 1] = r37_err_cont_q;
  // field ERR_CLEAR [1:1] w1p
  logic [0:0] r37_err_clear_wb, r37_err_clear_wm;
  assign r37_err_clear_wb = r37_wdata[1 +: 1];
  assign r37_err_clear_wm = r37_wmask[1 +: 1];
  logic [0:0] r37_err_clear_pulse_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r37_err_clear_pulse_q <= 1'h0;
    else r37_err_clear_pulse_q <= {1{r37_wr}} & r37_err_clear_wb & r37_err_clear_wm;
  end
  assign tensor_ctrl_err_clear_pulse_o[0 +: 1] = r37_err_clear_pulse_q;
  // field PERF_CLEAR [2:2] w1p
  logic [0:0] r37_perf_clear_wb, r37_perf_clear_wm;
  assign r37_perf_clear_wb = r37_wdata[2 +: 1];
  assign r37_perf_clear_wm = r37_wmask[2 +: 1];
  logic [0:0] r37_perf_clear_pulse_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r37_perf_clear_pulse_q <= 1'h0;
    else r37_perf_clear_pulse_q <= {1{r37_wr}} & r37_perf_clear_wb & r37_perf_clear_wm;
  end
  assign tensor_ctrl_perf_clear_pulse_o[0 +: 1] = r37_perf_clear_pulse_q;
  // field ABORT [3:3] w1p
  logic [0:0] r37_abort_wb, r37_abort_wm;
  assign r37_abort_wb = r37_wdata[3 +: 1];
  assign r37_abort_wm = r37_wmask[3 +: 1];
  logic [0:0] r37_abort_pulse_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r37_abort_pulse_q <= 1'h0;
    else r37_abort_pulse_q <= {1{r37_wr}} & r37_abort_wb & r37_abort_wm;
  end
  assign tensor_ctrl_abort_pulse_o[0 +: 1] = r37_abort_pulse_q;
  always_comb begin
    r37_rdata = 32'h0;
    r37_rdata[0 +: 1] = r37_err_cont_q;
  end

  // ======================================================================
  // r38: tensor.STATUS @ 64'h000000015000001c (32-bit)
  // ======================================================================
  logic [31:0] r38_wdata, r38_wmask, r38_rdata;
  logic             r38_wr, r38_rd;
  assign r38_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r38_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r38_wr    = wr_commit && reg_sel[38];
  assign r38_rd    = rd_commit && reg_sel[38];
  // field BUSY [0:0] ro/input
  logic [0:0] r38_busy_wb, r38_busy_wm;
  assign r38_busy_wb = r38_wdata[0 +: 1];
  assign r38_busy_wm = r38_wmask[0 +: 1];
  // field ERR_STICKY [1:1] ro/input
  logic [0:0] r38_err_sticky_wb, r38_err_sticky_wm;
  assign r38_err_sticky_wb = r38_wdata[1 +: 1];
  assign r38_err_sticky_wm = r38_wmask[1 +: 1];
  // field Q_FULL [2:2] ro/input
  logic [0:0] r38_q_full_wb, r38_q_full_wm;
  assign r38_q_full_wb = r38_wdata[2 +: 1];
  assign r38_q_full_wm = r38_wmask[2 +: 1];
  // field Q_EMPTY [3:3] ro/input
  logic [0:0] r38_q_empty_wb, r38_q_empty_wm;
  assign r38_q_empty_wb = r38_wdata[3 +: 1];
  assign r38_q_empty_wm = r38_wmask[3 +: 1];
  // field CPL_VALID [4:4] ro/input
  logic [0:0] r38_cpl_valid_wb, r38_cpl_valid_wm;
  assign r38_cpl_valid_wb = r38_wdata[4 +: 1];
  assign r38_cpl_valid_wm = r38_wmask[4 +: 1];
  // field ABORTING [5:5] ro/input
  logic [0:0] r38_aborting_wb, r38_aborting_wm;
  assign r38_aborting_wb = r38_wdata[5 +: 1];
  assign r38_aborting_wm = r38_wmask[5 +: 1];
  // field HALTED [6:6] ro/input
  logic [0:0] r38_halted_wb, r38_halted_wm;
  assign r38_halted_wb = r38_wdata[6 +: 1];
  assign r38_halted_wm = r38_wmask[6 +: 1];
  // field STATE [11:8] ro/input
  logic [3:0] r38_state_wb, r38_state_wm;
  assign r38_state_wb = r38_wdata[8 +: 4];
  assign r38_state_wm = r38_wmask[8 +: 4];
  // field QCOUNT [23:16] ro/input
  logic [7:0] r38_qcount_wb, r38_qcount_wm;
  assign r38_qcount_wb = r38_wdata[16 +: 8];
  assign r38_qcount_wm = r38_wmask[16 +: 8];
  // field QFREE [31:24] ro/input
  logic [7:0] r38_qfree_wb, r38_qfree_wm;
  assign r38_qfree_wb = r38_wdata[24 +: 8];
  assign r38_qfree_wm = r38_wmask[24 +: 8];
  always_comb begin
    r38_rdata = 32'h0;
    r38_rdata[0 +: 1] = tensor_status_busy_i[0 +: 1];
    r38_rdata[1 +: 1] = tensor_status_err_sticky_i[0 +: 1];
    r38_rdata[2 +: 1] = tensor_status_q_full_i[0 +: 1];
    r38_rdata[3 +: 1] = tensor_status_q_empty_i[0 +: 1];
    r38_rdata[4 +: 1] = tensor_status_cpl_valid_i[0 +: 1];
    r38_rdata[5 +: 1] = tensor_status_aborting_i[0 +: 1];
    r38_rdata[6 +: 1] = tensor_status_halted_i[0 +: 1];
    r38_rdata[8 +: 4] = tensor_status_state_i[0 +: 4];
    r38_rdata[16 +: 8] = tensor_status_qcount_i[0 +: 8];
    r38_rdata[24 +: 8] = tensor_status_qfree_i[0 +: 8];
  end

  // ======================================================================
  // r39: tensor.INT_ENABLE @ 64'h0000000150000020 (32-bit)
  // ======================================================================
  logic [31:0] r39_wdata, r39_wmask, r39_rdata;
  logic             r39_wr, r39_rd;
  assign r39_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r39_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r39_wr    = wr_commit && reg_sel[39];
  assign r39_rd    = rd_commit && reg_sel[39];
  // field IRQ [0:0] rw/none
  logic [0:0] r39_irq_wb, r39_irq_wm;
  assign r39_irq_wb = r39_wdata[0 +: 1];
  assign r39_irq_wm = r39_wmask[0 +: 1];
  logic [0:0] r39_irq_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r39_irq_q <= 1'h0;
    else if (r39_wr && (|r39_irq_wm)) r39_irq_q <= ((r39_irq_q & ~r39_irq_wm) | (r39_irq_wb & r39_irq_wm));
  end
  assign tensor_int_enable_irq_o[0 +: 1] = r39_irq_q;
  // field ERR [1:1] rw/none
  logic [0:0] r39_err_wb, r39_err_wm;
  assign r39_err_wb = r39_wdata[1 +: 1];
  assign r39_err_wm = r39_wmask[1 +: 1];
  logic [0:0] r39_err_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r39_err_q <= 1'h0;
    else if (r39_wr && (|r39_err_wm)) r39_err_q <= ((r39_err_q & ~r39_err_wm) | (r39_err_wb & r39_err_wm));
  end
  assign tensor_int_enable_err_o[0 +: 1] = r39_err_q;
  // field DONE [2:2] rw/none
  logic [0:0] r39_done_wb, r39_done_wm;
  assign r39_done_wb = r39_wdata[2 +: 1];
  assign r39_done_wm = r39_wmask[2 +: 1];
  logic [0:0] r39_done_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r39_done_q <= 1'h0;
    else if (r39_wr && (|r39_done_wm)) r39_done_q <= ((r39_done_q & ~r39_done_wm) | (r39_done_wb & r39_done_wm));
  end
  assign tensor_int_enable_done_o[0 +: 1] = r39_done_q;
  always_comb begin
    r39_rdata = 32'h0;
    r39_rdata[0 +: 1] = r39_irq_q;
    r39_rdata[1 +: 1] = r39_err_q;
    r39_rdata[2 +: 1] = r39_done_q;
  end

  // ======================================================================
  // r40: tensor.INT_STATUS @ 64'h0000000150000024 (32-bit)
  // ======================================================================
  logic [31:0] r40_wdata, r40_wmask, r40_rdata;
  logic             r40_wr, r40_rd;
  assign r40_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r40_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r40_wr    = wr_commit && reg_sel[40];
  assign r40_rd    = rd_commit && reg_sel[40];
  // field IRQ [0:0] w1c/event
  logic [0:0] r40_irq_wb, r40_irq_wm;
  assign r40_irq_wb = r40_wdata[0 +: 1];
  assign r40_irq_wm = r40_wmask[0 +: 1];
  logic [0:0] r40_irq_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r40_irq_q <= 1'h0;
    else r40_irq_q <= ((r40_irq_q & ~({1{r40_wr}} & r40_irq_wb & r40_irq_wm)) | tensor_int_status_irq_set_i[0 +: 1]);
  end
  assign tensor_int_status_irq_o[0 +: 1] = r40_irq_q;
  // field ERR [1:1] w1c/event
  logic [0:0] r40_err_wb, r40_err_wm;
  assign r40_err_wb = r40_wdata[1 +: 1];
  assign r40_err_wm = r40_wmask[1 +: 1];
  logic [0:0] r40_err_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r40_err_q <= 1'h0;
    else r40_err_q <= ((r40_err_q & ~({1{r40_wr}} & r40_err_wb & r40_err_wm)) | tensor_int_status_err_set_i[0 +: 1]);
  end
  assign tensor_int_status_err_o[0 +: 1] = r40_err_q;
  // field DONE [2:2] w1c/event
  logic [0:0] r40_done_wb, r40_done_wm;
  assign r40_done_wb = r40_wdata[2 +: 1];
  assign r40_done_wm = r40_wmask[2 +: 1];
  logic [0:0] r40_done_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r40_done_q <= 1'h0;
    else r40_done_q <= ((r40_done_q & ~({1{r40_wr}} & r40_done_wb & r40_done_wm)) | tensor_int_status_done_set_i[0 +: 1]);
  end
  assign tensor_int_status_done_o[0 +: 1] = r40_done_q;
  always_comb begin
    r40_rdata = 32'h0;
    r40_rdata[0 +: 1] = r40_irq_q;
    r40_rdata[1 +: 1] = r40_err_q;
    r40_rdata[2 +: 1] = r40_done_q;
  end

  // ======================================================================
  // r41: tensor.SUBMITTED @ 64'h0000000150000028 (32-bit)
  // ======================================================================
  logic [31:0] r41_wdata, r41_wmask, r41_rdata;
  logic             r41_wr, r41_rd;
  assign r41_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r41_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r41_wr    = wr_commit && reg_sel[41];
  assign r41_rd    = rd_commit && reg_sel[41];
  // field VALUE [31:0] ro/input
  logic [31:0] r41_value_wb, r41_value_wm;
  assign r41_value_wb = r41_wdata[0 +: 32];
  assign r41_value_wm = r41_wmask[0 +: 32];
  always_comb begin
    r41_rdata = 32'h0;
    r41_rdata[0 +: 32] = tensor_submitted_value_i[0 +: 32];
  end

  // ======================================================================
  // r42: tensor.KMAX @ 64'h000000015000002c (32-bit)
  // ======================================================================
  logic [31:0] r42_wdata, r42_wmask, r42_rdata;
  logic             r42_wr, r42_rd;
  assign r42_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r42_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r42_wr    = wr_commit && reg_sel[42];
  assign r42_rd    = rd_commit && reg_sel[42];
  // field VALUE [31:0] ro/input
  logic [31:0] r42_value_wb, r42_value_wm;
  assign r42_value_wb = r42_wdata[0 +: 32];
  assign r42_value_wm = r42_wmask[0 +: 32];
  always_comb begin
    r42_rdata = 32'h0;
    r42_rdata[0 +: 32] = tensor_kmax_value_i[0 +: 32];
  end

  // ======================================================================
  // r43: tensor.DESC[0] @ 64'h0000000150000040 (32-bit)
  // ======================================================================
  logic [31:0] r43_wdata, r43_wmask, r43_rdata;
  logic             r43_wr, r43_rd;
  assign r43_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r43_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r43_wr    = wr_commit && reg_sel[43];
  assign r43_rd    = rd_commit && reg_sel[43];
  // field VALUE [31:0] rw/none
  logic [31:0] r43_value_wb, r43_value_wm;
  assign r43_value_wb = r43_wdata[0 +: 32];
  assign r43_value_wm = r43_wmask[0 +: 32];
  logic [31:0] r43_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r43_value_q <= 32'h00000000;
    else if (r43_wr && (|r43_value_wm)) r43_value_q <= ((r43_value_q & ~r43_value_wm) | (r43_value_wb & r43_value_wm));
  end
  assign tensor_desc_value_o[0 +: 32] = r43_value_q;
  always_comb begin
    r43_rdata = 32'h0;
    r43_rdata[0 +: 32] = r43_value_q;
  end

  // ======================================================================
  // r44: tensor.DESC[1] @ 64'h0000000150000044 (32-bit)
  // ======================================================================
  logic [31:0] r44_wdata, r44_wmask, r44_rdata;
  logic             r44_wr, r44_rd;
  assign r44_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r44_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r44_wr    = wr_commit && reg_sel[44];
  assign r44_rd    = rd_commit && reg_sel[44];
  // field VALUE [31:0] rw/none
  logic [31:0] r44_value_wb, r44_value_wm;
  assign r44_value_wb = r44_wdata[0 +: 32];
  assign r44_value_wm = r44_wmask[0 +: 32];
  logic [31:0] r44_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r44_value_q <= 32'h00000000;
    else if (r44_wr && (|r44_value_wm)) r44_value_q <= ((r44_value_q & ~r44_value_wm) | (r44_value_wb & r44_value_wm));
  end
  assign tensor_desc_value_o[32 +: 32] = r44_value_q;
  always_comb begin
    r44_rdata = 32'h0;
    r44_rdata[0 +: 32] = r44_value_q;
  end

  // ======================================================================
  // r45: tensor.DESC[2] @ 64'h0000000150000048 (32-bit)
  // ======================================================================
  logic [31:0] r45_wdata, r45_wmask, r45_rdata;
  logic             r45_wr, r45_rd;
  assign r45_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r45_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r45_wr    = wr_commit && reg_sel[45];
  assign r45_rd    = rd_commit && reg_sel[45];
  // field VALUE [31:0] rw/none
  logic [31:0] r45_value_wb, r45_value_wm;
  assign r45_value_wb = r45_wdata[0 +: 32];
  assign r45_value_wm = r45_wmask[0 +: 32];
  logic [31:0] r45_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r45_value_q <= 32'h00000000;
    else if (r45_wr && (|r45_value_wm)) r45_value_q <= ((r45_value_q & ~r45_value_wm) | (r45_value_wb & r45_value_wm));
  end
  assign tensor_desc_value_o[64 +: 32] = r45_value_q;
  always_comb begin
    r45_rdata = 32'h0;
    r45_rdata[0 +: 32] = r45_value_q;
  end

  // ======================================================================
  // r46: tensor.DESC[3] @ 64'h000000015000004c (32-bit)
  // ======================================================================
  logic [31:0] r46_wdata, r46_wmask, r46_rdata;
  logic             r46_wr, r46_rd;
  assign r46_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r46_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r46_wr    = wr_commit && reg_sel[46];
  assign r46_rd    = rd_commit && reg_sel[46];
  // field VALUE [31:0] rw/none
  logic [31:0] r46_value_wb, r46_value_wm;
  assign r46_value_wb = r46_wdata[0 +: 32];
  assign r46_value_wm = r46_wmask[0 +: 32];
  logic [31:0] r46_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r46_value_q <= 32'h00000000;
    else if (r46_wr && (|r46_value_wm)) r46_value_q <= ((r46_value_q & ~r46_value_wm) | (r46_value_wb & r46_value_wm));
  end
  assign tensor_desc_value_o[96 +: 32] = r46_value_q;
  always_comb begin
    r46_rdata = 32'h0;
    r46_rdata[0 +: 32] = r46_value_q;
  end

  // ======================================================================
  // r47: tensor.DESC[4] @ 64'h0000000150000050 (32-bit)
  // ======================================================================
  logic [31:0] r47_wdata, r47_wmask, r47_rdata;
  logic             r47_wr, r47_rd;
  assign r47_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r47_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r47_wr    = wr_commit && reg_sel[47];
  assign r47_rd    = rd_commit && reg_sel[47];
  // field VALUE [31:0] rw/none
  logic [31:0] r47_value_wb, r47_value_wm;
  assign r47_value_wb = r47_wdata[0 +: 32];
  assign r47_value_wm = r47_wmask[0 +: 32];
  logic [31:0] r47_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r47_value_q <= 32'h00000000;
    else if (r47_wr && (|r47_value_wm)) r47_value_q <= ((r47_value_q & ~r47_value_wm) | (r47_value_wb & r47_value_wm));
  end
  assign tensor_desc_value_o[128 +: 32] = r47_value_q;
  always_comb begin
    r47_rdata = 32'h0;
    r47_rdata[0 +: 32] = r47_value_q;
  end

  // ======================================================================
  // r48: tensor.DESC[5] @ 64'h0000000150000054 (32-bit)
  // ======================================================================
  logic [31:0] r48_wdata, r48_wmask, r48_rdata;
  logic             r48_wr, r48_rd;
  assign r48_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r48_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r48_wr    = wr_commit && reg_sel[48];
  assign r48_rd    = rd_commit && reg_sel[48];
  // field VALUE [31:0] rw/none
  logic [31:0] r48_value_wb, r48_value_wm;
  assign r48_value_wb = r48_wdata[0 +: 32];
  assign r48_value_wm = r48_wmask[0 +: 32];
  logic [31:0] r48_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r48_value_q <= 32'h00000000;
    else if (r48_wr && (|r48_value_wm)) r48_value_q <= ((r48_value_q & ~r48_value_wm) | (r48_value_wb & r48_value_wm));
  end
  assign tensor_desc_value_o[160 +: 32] = r48_value_q;
  always_comb begin
    r48_rdata = 32'h0;
    r48_rdata[0 +: 32] = r48_value_q;
  end

  // ======================================================================
  // r49: tensor.DESC[6] @ 64'h0000000150000058 (32-bit)
  // ======================================================================
  logic [31:0] r49_wdata, r49_wmask, r49_rdata;
  logic             r49_wr, r49_rd;
  assign r49_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r49_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r49_wr    = wr_commit && reg_sel[49];
  assign r49_rd    = rd_commit && reg_sel[49];
  // field VALUE [31:0] rw/none
  logic [31:0] r49_value_wb, r49_value_wm;
  assign r49_value_wb = r49_wdata[0 +: 32];
  assign r49_value_wm = r49_wmask[0 +: 32];
  logic [31:0] r49_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r49_value_q <= 32'h00000000;
    else if (r49_wr && (|r49_value_wm)) r49_value_q <= ((r49_value_q & ~r49_value_wm) | (r49_value_wb & r49_value_wm));
  end
  assign tensor_desc_value_o[192 +: 32] = r49_value_q;
  always_comb begin
    r49_rdata = 32'h0;
    r49_rdata[0 +: 32] = r49_value_q;
  end

  // ======================================================================
  // r50: tensor.DESC[7] @ 64'h000000015000005c (32-bit)
  // ======================================================================
  logic [31:0] r50_wdata, r50_wmask, r50_rdata;
  logic             r50_wr, r50_rd;
  assign r50_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r50_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r50_wr    = wr_commit && reg_sel[50];
  assign r50_rd    = rd_commit && reg_sel[50];
  // field VALUE [31:0] rw/none
  logic [31:0] r50_value_wb, r50_value_wm;
  assign r50_value_wb = r50_wdata[0 +: 32];
  assign r50_value_wm = r50_wmask[0 +: 32];
  logic [31:0] r50_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r50_value_q <= 32'h00000000;
    else if (r50_wr && (|r50_value_wm)) r50_value_q <= ((r50_value_q & ~r50_value_wm) | (r50_value_wb & r50_value_wm));
  end
  assign tensor_desc_value_o[224 +: 32] = r50_value_q;
  always_comb begin
    r50_rdata = 32'h0;
    r50_rdata[0 +: 32] = r50_value_q;
  end

  // ======================================================================
  // r51: tensor.DESC[8] @ 64'h0000000150000060 (32-bit)
  // ======================================================================
  logic [31:0] r51_wdata, r51_wmask, r51_rdata;
  logic             r51_wr, r51_rd;
  assign r51_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r51_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r51_wr    = wr_commit && reg_sel[51];
  assign r51_rd    = rd_commit && reg_sel[51];
  // field VALUE [31:0] rw/none
  logic [31:0] r51_value_wb, r51_value_wm;
  assign r51_value_wb = r51_wdata[0 +: 32];
  assign r51_value_wm = r51_wmask[0 +: 32];
  logic [31:0] r51_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r51_value_q <= 32'h00000000;
    else if (r51_wr && (|r51_value_wm)) r51_value_q <= ((r51_value_q & ~r51_value_wm) | (r51_value_wb & r51_value_wm));
  end
  assign tensor_desc_value_o[256 +: 32] = r51_value_q;
  always_comb begin
    r51_rdata = 32'h0;
    r51_rdata[0 +: 32] = r51_value_q;
  end

  // ======================================================================
  // r52: tensor.DESC[9] @ 64'h0000000150000064 (32-bit)
  // ======================================================================
  logic [31:0] r52_wdata, r52_wmask, r52_rdata;
  logic             r52_wr, r52_rd;
  assign r52_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r52_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r52_wr    = wr_commit && reg_sel[52];
  assign r52_rd    = rd_commit && reg_sel[52];
  // field VALUE [31:0] rw/none
  logic [31:0] r52_value_wb, r52_value_wm;
  assign r52_value_wb = r52_wdata[0 +: 32];
  assign r52_value_wm = r52_wmask[0 +: 32];
  logic [31:0] r52_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r52_value_q <= 32'h00000000;
    else if (r52_wr && (|r52_value_wm)) r52_value_q <= ((r52_value_q & ~r52_value_wm) | (r52_value_wb & r52_value_wm));
  end
  assign tensor_desc_value_o[288 +: 32] = r52_value_q;
  always_comb begin
    r52_rdata = 32'h0;
    r52_rdata[0 +: 32] = r52_value_q;
  end

  // ======================================================================
  // r53: tensor.DESC[10] @ 64'h0000000150000068 (32-bit)
  // ======================================================================
  logic [31:0] r53_wdata, r53_wmask, r53_rdata;
  logic             r53_wr, r53_rd;
  assign r53_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r53_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r53_wr    = wr_commit && reg_sel[53];
  assign r53_rd    = rd_commit && reg_sel[53];
  // field VALUE [31:0] rw/none
  logic [31:0] r53_value_wb, r53_value_wm;
  assign r53_value_wb = r53_wdata[0 +: 32];
  assign r53_value_wm = r53_wmask[0 +: 32];
  logic [31:0] r53_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r53_value_q <= 32'h00000000;
    else if (r53_wr && (|r53_value_wm)) r53_value_q <= ((r53_value_q & ~r53_value_wm) | (r53_value_wb & r53_value_wm));
  end
  assign tensor_desc_value_o[320 +: 32] = r53_value_q;
  always_comb begin
    r53_rdata = 32'h0;
    r53_rdata[0 +: 32] = r53_value_q;
  end

  // ======================================================================
  // r54: tensor.DESC[11] @ 64'h000000015000006c (32-bit)
  // ======================================================================
  logic [31:0] r54_wdata, r54_wmask, r54_rdata;
  logic             r54_wr, r54_rd;
  assign r54_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r54_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r54_wr    = wr_commit && reg_sel[54];
  assign r54_rd    = rd_commit && reg_sel[54];
  // field VALUE [31:0] rw/none
  logic [31:0] r54_value_wb, r54_value_wm;
  assign r54_value_wb = r54_wdata[0 +: 32];
  assign r54_value_wm = r54_wmask[0 +: 32];
  logic [31:0] r54_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r54_value_q <= 32'h00000000;
    else if (r54_wr && (|r54_value_wm)) r54_value_q <= ((r54_value_q & ~r54_value_wm) | (r54_value_wb & r54_value_wm));
  end
  assign tensor_desc_value_o[352 +: 32] = r54_value_q;
  always_comb begin
    r54_rdata = 32'h0;
    r54_rdata[0 +: 32] = r54_value_q;
  end

  // ======================================================================
  // r55: tensor.DOORBELL @ 64'h0000000150000070 (32-bit)
  // ======================================================================
  logic [31:0] r55_wdata, r55_wmask, r55_rdata;
  logic             r55_wr, r55_rd;
  assign r55_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r55_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r55_wr    = wr_commit && reg_sel[55];
  assign r55_rd    = rd_commit && reg_sel[55];
  // field RING [31:0] wo/none
  logic [31:0] r55_ring_wb, r55_ring_wm;
  assign r55_ring_wb = r55_wdata[0 +: 32];
  assign r55_ring_wm = r55_wmask[0 +: 32];
  logic r55_wr_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r55_wr_q <= 1'b0;
    else r55_wr_q <= r55_wr;
  end
  assign tensor_doorbell_wr_o[0 +: 1] = r55_wr_q;
  always_comb begin
    r55_rdata = 32'h0;
  end

  // ======================================================================
  // r56: tensor.CPL[0] @ 64'h0000000150000080 (32-bit)
  // ======================================================================
  logic [31:0] r56_wdata, r56_wmask, r56_rdata;
  logic             r56_wr, r56_rd;
  assign r56_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r56_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r56_wr    = wr_commit && reg_sel[56];
  assign r56_rd    = rd_commit && reg_sel[56];
  // field VALUE [31:0] ro/input
  logic [31:0] r56_value_wb, r56_value_wm;
  assign r56_value_wb = r56_wdata[0 +: 32];
  assign r56_value_wm = r56_wmask[0 +: 32];
  always_comb begin
    r56_rdata = 32'h0;
    r56_rdata[0 +: 32] = tensor_cpl_value_i[0 +: 32];
  end

  // ======================================================================
  // r57: tensor.CPL[1] @ 64'h0000000150000084 (32-bit)
  // ======================================================================
  logic [31:0] r57_wdata, r57_wmask, r57_rdata;
  logic             r57_wr, r57_rd;
  assign r57_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r57_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r57_wr    = wr_commit && reg_sel[57];
  assign r57_rd    = rd_commit && reg_sel[57];
  // field VALUE [31:0] ro/input
  logic [31:0] r57_value_wb, r57_value_wm;
  assign r57_value_wb = r57_wdata[0 +: 32];
  assign r57_value_wm = r57_wmask[0 +: 32];
  always_comb begin
    r57_rdata = 32'h0;
    r57_rdata[0 +: 32] = tensor_cpl_value_i[32 +: 32];
  end

  // ======================================================================
  // r58: tensor.CPL[2] @ 64'h0000000150000088 (32-bit)
  // ======================================================================
  logic [31:0] r58_wdata, r58_wmask, r58_rdata;
  logic             r58_wr, r58_rd;
  assign r58_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r58_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r58_wr    = wr_commit && reg_sel[58];
  assign r58_rd    = rd_commit && reg_sel[58];
  // field VALUE [31:0] ro/input
  logic [31:0] r58_value_wb, r58_value_wm;
  assign r58_value_wb = r58_wdata[0 +: 32];
  assign r58_value_wm = r58_wmask[0 +: 32];
  always_comb begin
    r58_rdata = 32'h0;
    r58_rdata[0 +: 32] = tensor_cpl_value_i[64 +: 32];
  end

  // ======================================================================
  // r59: tensor.CPL[3] @ 64'h000000015000008c (32-bit)
  // ======================================================================
  logic [31:0] r59_wdata, r59_wmask, r59_rdata;
  logic             r59_wr, r59_rd;
  assign r59_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r59_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r59_wr    = wr_commit && reg_sel[59];
  assign r59_rd    = rd_commit && reg_sel[59];
  // field VALUE [31:0] ro/input
  logic [31:0] r59_value_wb, r59_value_wm;
  assign r59_value_wb = r59_wdata[0 +: 32];
  assign r59_value_wm = r59_wmask[0 +: 32];
  always_comb begin
    r59_rdata = 32'h0;
    r59_rdata[0 +: 32] = tensor_cpl_value_i[96 +: 32];
  end

  // ======================================================================
  // r60: tensor.CPL[4] @ 64'h0000000150000090 (32-bit)
  // ======================================================================
  logic [31:0] r60_wdata, r60_wmask, r60_rdata;
  logic             r60_wr, r60_rd;
  assign r60_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r60_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r60_wr    = wr_commit && reg_sel[60];
  assign r60_rd    = rd_commit && reg_sel[60];
  // field VALUE [31:0] ro/input
  logic [31:0] r60_value_wb, r60_value_wm;
  assign r60_value_wb = r60_wdata[0 +: 32];
  assign r60_value_wm = r60_wmask[0 +: 32];
  always_comb begin
    r60_rdata = 32'h0;
    r60_rdata[0 +: 32] = tensor_cpl_value_i[128 +: 32];
  end

  // ======================================================================
  // r61: tensor.CPL[5] @ 64'h0000000150000094 (32-bit)
  // ======================================================================
  logic [31:0] r61_wdata, r61_wmask, r61_rdata;
  logic             r61_wr, r61_rd;
  assign r61_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r61_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r61_wr    = wr_commit && reg_sel[61];
  assign r61_rd    = rd_commit && reg_sel[61];
  // field VALUE [31:0] ro/input
  logic [31:0] r61_value_wb, r61_value_wm;
  assign r61_value_wb = r61_wdata[0 +: 32];
  assign r61_value_wm = r61_wmask[0 +: 32];
  always_comb begin
    r61_rdata = 32'h0;
    r61_rdata[0 +: 32] = tensor_cpl_value_i[160 +: 32];
  end

  // ======================================================================
  // r62: tensor.CPL_POP @ 64'h0000000150000098 (32-bit)
  // ======================================================================
  logic [31:0] r62_wdata, r62_wmask, r62_rdata;
  logic             r62_wr, r62_rd;
  assign r62_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r62_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r62_wr    = wr_commit && reg_sel[62];
  assign r62_rd    = rd_commit && reg_sel[62];
  // field POP [31:0] wo/none
  logic [31:0] r62_pop_wb, r62_pop_wm;
  assign r62_pop_wb = r62_wdata[0 +: 32];
  assign r62_pop_wm = r62_wmask[0 +: 32];
  logic r62_wr_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r62_wr_q <= 1'b0;
    else r62_wr_q <= r62_wr;
  end
  assign tensor_cpl_pop_wr_o[0 +: 1] = r62_wr_q;
  always_comb begin
    r62_rdata = 32'h0;
  end

  // ======================================================================
  // r63: tensor.PERF[0] @ 64'h0000000150000100 (32-bit)
  // ======================================================================
  logic [31:0] r63_wdata, r63_wmask, r63_rdata;
  logic             r63_wr, r63_rd;
  assign r63_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r63_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r63_wr    = wr_commit && reg_sel[63];
  assign r63_rd    = rd_commit && reg_sel[63];
  // field VALUE [31:0] ro/input
  logic [31:0] r63_value_wb, r63_value_wm;
  assign r63_value_wb = r63_wdata[0 +: 32];
  assign r63_value_wm = r63_wmask[0 +: 32];
  always_comb begin
    r63_rdata = 32'h0;
    r63_rdata[0 +: 32] = tensor_perf_value_i[0 +: 32];
  end

  // ======================================================================
  // r64: tensor.PERF[1] @ 64'h0000000150000104 (32-bit)
  // ======================================================================
  logic [31:0] r64_wdata, r64_wmask, r64_rdata;
  logic             r64_wr, r64_rd;
  assign r64_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r64_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r64_wr    = wr_commit && reg_sel[64];
  assign r64_rd    = rd_commit && reg_sel[64];
  // field VALUE [31:0] ro/input
  logic [31:0] r64_value_wb, r64_value_wm;
  assign r64_value_wb = r64_wdata[0 +: 32];
  assign r64_value_wm = r64_wmask[0 +: 32];
  always_comb begin
    r64_rdata = 32'h0;
    r64_rdata[0 +: 32] = tensor_perf_value_i[32 +: 32];
  end

  // ======================================================================
  // r65: tensor.PERF[2] @ 64'h0000000150000108 (32-bit)
  // ======================================================================
  logic [31:0] r65_wdata, r65_wmask, r65_rdata;
  logic             r65_wr, r65_rd;
  assign r65_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r65_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r65_wr    = wr_commit && reg_sel[65];
  assign r65_rd    = rd_commit && reg_sel[65];
  // field VALUE [31:0] ro/input
  logic [31:0] r65_value_wb, r65_value_wm;
  assign r65_value_wb = r65_wdata[0 +: 32];
  assign r65_value_wm = r65_wmask[0 +: 32];
  always_comb begin
    r65_rdata = 32'h0;
    r65_rdata[0 +: 32] = tensor_perf_value_i[64 +: 32];
  end

  // ======================================================================
  // r66: tensor.PERF[3] @ 64'h000000015000010c (32-bit)
  // ======================================================================
  logic [31:0] r66_wdata, r66_wmask, r66_rdata;
  logic             r66_wr, r66_rd;
  assign r66_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r66_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r66_wr    = wr_commit && reg_sel[66];
  assign r66_rd    = rd_commit && reg_sel[66];
  // field VALUE [31:0] ro/input
  logic [31:0] r66_value_wb, r66_value_wm;
  assign r66_value_wb = r66_wdata[0 +: 32];
  assign r66_value_wm = r66_wmask[0 +: 32];
  always_comb begin
    r66_rdata = 32'h0;
    r66_rdata[0 +: 32] = tensor_perf_value_i[96 +: 32];
  end

  // ======================================================================
  // r67: tensor.PERF[4] @ 64'h0000000150000110 (32-bit)
  // ======================================================================
  logic [31:0] r67_wdata, r67_wmask, r67_rdata;
  logic             r67_wr, r67_rd;
  assign r67_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r67_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r67_wr    = wr_commit && reg_sel[67];
  assign r67_rd    = rd_commit && reg_sel[67];
  // field VALUE [31:0] ro/input
  logic [31:0] r67_value_wb, r67_value_wm;
  assign r67_value_wb = r67_wdata[0 +: 32];
  assign r67_value_wm = r67_wmask[0 +: 32];
  always_comb begin
    r67_rdata = 32'h0;
    r67_rdata[0 +: 32] = tensor_perf_value_i[128 +: 32];
  end

  // ======================================================================
  // r68: tensor.PERF[5] @ 64'h0000000150000114 (32-bit)
  // ======================================================================
  logic [31:0] r68_wdata, r68_wmask, r68_rdata;
  logic             r68_wr, r68_rd;
  assign r68_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r68_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r68_wr    = wr_commit && reg_sel[68];
  assign r68_rd    = rd_commit && reg_sel[68];
  // field VALUE [31:0] ro/input
  logic [31:0] r68_value_wb, r68_value_wm;
  assign r68_value_wb = r68_wdata[0 +: 32];
  assign r68_value_wm = r68_wmask[0 +: 32];
  always_comb begin
    r68_rdata = 32'h0;
    r68_rdata[0 +: 32] = tensor_perf_value_i[160 +: 32];
  end

  // ======================================================================
  // r69: tensor.PERF[6] @ 64'h0000000150000118 (32-bit)
  // ======================================================================
  logic [31:0] r69_wdata, r69_wmask, r69_rdata;
  logic             r69_wr, r69_rd;
  assign r69_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r69_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r69_wr    = wr_commit && reg_sel[69];
  assign r69_rd    = rd_commit && reg_sel[69];
  // field VALUE [31:0] ro/input
  logic [31:0] r69_value_wb, r69_value_wm;
  assign r69_value_wb = r69_wdata[0 +: 32];
  assign r69_value_wm = r69_wmask[0 +: 32];
  always_comb begin
    r69_rdata = 32'h0;
    r69_rdata[0 +: 32] = tensor_perf_value_i[192 +: 32];
  end

  // ======================================================================
  // r70: tensor.PERF[7] @ 64'h000000015000011c (32-bit)
  // ======================================================================
  logic [31:0] r70_wdata, r70_wmask, r70_rdata;
  logic             r70_wr, r70_rd;
  assign r70_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r70_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r70_wr    = wr_commit && reg_sel[70];
  assign r70_rd    = rd_commit && reg_sel[70];
  // field VALUE [31:0] ro/input
  logic [31:0] r70_value_wb, r70_value_wm;
  assign r70_value_wb = r70_wdata[0 +: 32];
  assign r70_value_wm = r70_wmask[0 +: 32];
  always_comb begin
    r70_rdata = 32'h0;
    r70_rdata[0 +: 32] = tensor_perf_value_i[224 +: 32];
  end

  // ======================================================================
  // r71: tensor.PERF[8] @ 64'h0000000150000120 (32-bit)
  // ======================================================================
  logic [31:0] r71_wdata, r71_wmask, r71_rdata;
  logic             r71_wr, r71_rd;
  assign r71_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r71_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r71_wr    = wr_commit && reg_sel[71];
  assign r71_rd    = rd_commit && reg_sel[71];
  // field VALUE [31:0] ro/input
  logic [31:0] r71_value_wb, r71_value_wm;
  assign r71_value_wb = r71_wdata[0 +: 32];
  assign r71_value_wm = r71_wmask[0 +: 32];
  always_comb begin
    r71_rdata = 32'h0;
    r71_rdata[0 +: 32] = tensor_perf_value_i[256 +: 32];
  end

  // ======================================================================
  // r72: tensor.PERF[9] @ 64'h0000000150000124 (32-bit)
  // ======================================================================
  logic [31:0] r72_wdata, r72_wmask, r72_rdata;
  logic             r72_wr, r72_rd;
  assign r72_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r72_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r72_wr    = wr_commit && reg_sel[72];
  assign r72_rd    = rd_commit && reg_sel[72];
  // field VALUE [31:0] ro/input
  logic [31:0] r72_value_wb, r72_value_wm;
  assign r72_value_wb = r72_wdata[0 +: 32];
  assign r72_value_wm = r72_wmask[0 +: 32];
  always_comb begin
    r72_rdata = 32'h0;
    r72_rdata[0 +: 32] = tensor_perf_value_i[288 +: 32];
  end

  // ======================================================================
  // r73: tensor.PERF[10] @ 64'h0000000150000128 (32-bit)
  // ======================================================================
  logic [31:0] r73_wdata, r73_wmask, r73_rdata;
  logic             r73_wr, r73_rd;
  assign r73_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r73_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r73_wr    = wr_commit && reg_sel[73];
  assign r73_rd    = rd_commit && reg_sel[73];
  // field VALUE [31:0] ro/input
  logic [31:0] r73_value_wb, r73_value_wm;
  assign r73_value_wb = r73_wdata[0 +: 32];
  assign r73_value_wm = r73_wmask[0 +: 32];
  always_comb begin
    r73_rdata = 32'h0;
    r73_rdata[0 +: 32] = tensor_perf_value_i[320 +: 32];
  end

  // ======================================================================
  // r74: tensor.PERF[11] @ 64'h000000015000012c (32-bit)
  // ======================================================================
  logic [31:0] r74_wdata, r74_wmask, r74_rdata;
  logic             r74_wr, r74_rd;
  assign r74_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r74_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r74_wr    = wr_commit && reg_sel[74];
  assign r74_rd    = rd_commit && reg_sel[74];
  // field VALUE [31:0] ro/input
  logic [31:0] r74_value_wb, r74_value_wm;
  assign r74_value_wb = r74_wdata[0 +: 32];
  assign r74_value_wm = r74_wmask[0 +: 32];
  always_comb begin
    r74_rdata = 32'h0;
    r74_rdata[0 +: 32] = tensor_perf_value_i[352 +: 32];
  end

  // ======================================================================
  // r75: tensor.PERF[12] @ 64'h0000000150000130 (32-bit)
  // ======================================================================
  logic [31:0] r75_wdata, r75_wmask, r75_rdata;
  logic             r75_wr, r75_rd;
  assign r75_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r75_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r75_wr    = wr_commit && reg_sel[75];
  assign r75_rd    = rd_commit && reg_sel[75];
  // field VALUE [31:0] ro/input
  logic [31:0] r75_value_wb, r75_value_wm;
  assign r75_value_wb = r75_wdata[0 +: 32];
  assign r75_value_wm = r75_wmask[0 +: 32];
  always_comb begin
    r75_rdata = 32'h0;
    r75_rdata[0 +: 32] = tensor_perf_value_i[384 +: 32];
  end

  // ======================================================================
  // r76: tensor.PERF[13] @ 64'h0000000150000134 (32-bit)
  // ======================================================================
  logic [31:0] r76_wdata, r76_wmask, r76_rdata;
  logic             r76_wr, r76_rd;
  assign r76_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r76_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r76_wr    = wr_commit && reg_sel[76];
  assign r76_rd    = rd_commit && reg_sel[76];
  // field VALUE [31:0] ro/input
  logic [31:0] r76_value_wb, r76_value_wm;
  assign r76_value_wb = r76_wdata[0 +: 32];
  assign r76_value_wm = r76_wmask[0 +: 32];
  always_comb begin
    r76_rdata = 32'h0;
    r76_rdata[0 +: 32] = tensor_perf_value_i[416 +: 32];
  end

  // ======================================================================
  // r77: tensor.PERF[14] @ 64'h0000000150000138 (32-bit)
  // ======================================================================
  logic [31:0] r77_wdata, r77_wmask, r77_rdata;
  logic             r77_wr, r77_rd;
  assign r77_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r77_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r77_wr    = wr_commit && reg_sel[77];
  assign r77_rd    = rd_commit && reg_sel[77];
  // field VALUE [31:0] ro/input
  logic [31:0] r77_value_wb, r77_value_wm;
  assign r77_value_wb = r77_wdata[0 +: 32];
  assign r77_value_wm = r77_wmask[0 +: 32];
  always_comb begin
    r77_rdata = 32'h0;
    r77_rdata[0 +: 32] = tensor_perf_value_i[448 +: 32];
  end

  // ======================================================================
  // r78: tensor.PERF[15] @ 64'h000000015000013c (32-bit)
  // ======================================================================
  logic [31:0] r78_wdata, r78_wmask, r78_rdata;
  logic             r78_wr, r78_rd;
  assign r78_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r78_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r78_wr    = wr_commit && reg_sel[78];
  assign r78_rd    = rd_commit && reg_sel[78];
  // field VALUE [31:0] ro/input
  logic [31:0] r78_value_wb, r78_value_wm;
  assign r78_value_wb = r78_wdata[0 +: 32];
  assign r78_value_wm = r78_wmask[0 +: 32];
  always_comb begin
    r78_rdata = 32'h0;
    r78_rdata[0 +: 32] = tensor_perf_value_i[480 +: 32];
  end

  // ======================================================================
  // r79: tensor.PERF[16] @ 64'h0000000150000140 (32-bit)
  // ======================================================================
  logic [31:0] r79_wdata, r79_wmask, r79_rdata;
  logic             r79_wr, r79_rd;
  assign r79_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r79_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r79_wr    = wr_commit && reg_sel[79];
  assign r79_rd    = rd_commit && reg_sel[79];
  // field VALUE [31:0] ro/input
  logic [31:0] r79_value_wb, r79_value_wm;
  assign r79_value_wb = r79_wdata[0 +: 32];
  assign r79_value_wm = r79_wmask[0 +: 32];
  always_comb begin
    r79_rdata = 32'h0;
    r79_rdata[0 +: 32] = tensor_perf_value_i[512 +: 32];
  end

  // ======================================================================
  // r80: tensor.PERF[17] @ 64'h0000000150000144 (32-bit)
  // ======================================================================
  logic [31:0] r80_wdata, r80_wmask, r80_rdata;
  logic             r80_wr, r80_rd;
  assign r80_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r80_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r80_wr    = wr_commit && reg_sel[80];
  assign r80_rd    = rd_commit && reg_sel[80];
  // field VALUE [31:0] ro/input
  logic [31:0] r80_value_wb, r80_value_wm;
  assign r80_value_wb = r80_wdata[0 +: 32];
  assign r80_value_wm = r80_wmask[0 +: 32];
  always_comb begin
    r80_rdata = 32'h0;
    r80_rdata[0 +: 32] = tensor_perf_value_i[544 +: 32];
  end

  // ======================================================================
  // r81: tensor.PERF[18] @ 64'h0000000150000148 (32-bit)
  // ======================================================================
  logic [31:0] r81_wdata, r81_wmask, r81_rdata;
  logic             r81_wr, r81_rd;
  assign r81_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r81_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r81_wr    = wr_commit && reg_sel[81];
  assign r81_rd    = rd_commit && reg_sel[81];
  // field VALUE [31:0] ro/input
  logic [31:0] r81_value_wb, r81_value_wm;
  assign r81_value_wb = r81_wdata[0 +: 32];
  assign r81_value_wm = r81_wmask[0 +: 32];
  always_comb begin
    r81_rdata = 32'h0;
    r81_rdata[0 +: 32] = tensor_perf_value_i[576 +: 32];
  end

  // ======================================================================
  // r82: tensor.PERF[19] @ 64'h000000015000014c (32-bit)
  // ======================================================================
  logic [31:0] r82_wdata, r82_wmask, r82_rdata;
  logic             r82_wr, r82_rd;
  assign r82_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r82_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r82_wr    = wr_commit && reg_sel[82];
  assign r82_rd    = rd_commit && reg_sel[82];
  // field VALUE [31:0] ro/input
  logic [31:0] r82_value_wb, r82_value_wm;
  assign r82_value_wb = r82_wdata[0 +: 32];
  assign r82_value_wm = r82_wmask[0 +: 32];
  always_comb begin
    r82_rdata = 32'h0;
    r82_rdata[0 +: 32] = tensor_perf_value_i[608 +: 32];
  end

  // ======================================================================
  // r83: tensor.DMA_PERF[0] @ 64'h0000000150000200 (32-bit)
  // ======================================================================
  logic [31:0] r83_wdata, r83_wmask, r83_rdata;
  logic             r83_wr, r83_rd;
  assign r83_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r83_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r83_wr    = wr_commit && reg_sel[83];
  assign r83_rd    = rd_commit && reg_sel[83];
  // field VALUE [31:0] ro/input
  logic [31:0] r83_value_wb, r83_value_wm;
  assign r83_value_wb = r83_wdata[0 +: 32];
  assign r83_value_wm = r83_wmask[0 +: 32];
  always_comb begin
    r83_rdata = 32'h0;
    r83_rdata[0 +: 32] = tensor_dma_perf_value_i[0 +: 32];
  end

  // ======================================================================
  // r84: tensor.DMA_PERF[1] @ 64'h0000000150000204 (32-bit)
  // ======================================================================
  logic [31:0] r84_wdata, r84_wmask, r84_rdata;
  logic             r84_wr, r84_rd;
  assign r84_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r84_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r84_wr    = wr_commit && reg_sel[84];
  assign r84_rd    = rd_commit && reg_sel[84];
  // field VALUE [31:0] ro/input
  logic [31:0] r84_value_wb, r84_value_wm;
  assign r84_value_wb = r84_wdata[0 +: 32];
  assign r84_value_wm = r84_wmask[0 +: 32];
  always_comb begin
    r84_rdata = 32'h0;
    r84_rdata[0 +: 32] = tensor_dma_perf_value_i[32 +: 32];
  end

  // ======================================================================
  // r85: tensor.DMA_PERF[2] @ 64'h0000000150000208 (32-bit)
  // ======================================================================
  logic [31:0] r85_wdata, r85_wmask, r85_rdata;
  logic             r85_wr, r85_rd;
  assign r85_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r85_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r85_wr    = wr_commit && reg_sel[85];
  assign r85_rd    = rd_commit && reg_sel[85];
  // field VALUE [31:0] ro/input
  logic [31:0] r85_value_wb, r85_value_wm;
  assign r85_value_wb = r85_wdata[0 +: 32];
  assign r85_value_wm = r85_wmask[0 +: 32];
  always_comb begin
    r85_rdata = 32'h0;
    r85_rdata[0 +: 32] = tensor_dma_perf_value_i[64 +: 32];
  end

  // ======================================================================
  // r86: tensor.DMA_PERF[3] @ 64'h000000015000020c (32-bit)
  // ======================================================================
  logic [31:0] r86_wdata, r86_wmask, r86_rdata;
  logic             r86_wr, r86_rd;
  assign r86_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r86_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r86_wr    = wr_commit && reg_sel[86];
  assign r86_rd    = rd_commit && reg_sel[86];
  // field VALUE [31:0] ro/input
  logic [31:0] r86_value_wb, r86_value_wm;
  assign r86_value_wb = r86_wdata[0 +: 32];
  assign r86_value_wm = r86_wmask[0 +: 32];
  always_comb begin
    r86_rdata = 32'h0;
    r86_rdata[0 +: 32] = tensor_dma_perf_value_i[96 +: 32];
  end

  // ======================================================================
  // r87: tensor.DMA_PERF[4] @ 64'h0000000150000210 (32-bit)
  // ======================================================================
  logic [31:0] r87_wdata, r87_wmask, r87_rdata;
  logic             r87_wr, r87_rd;
  assign r87_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r87_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r87_wr    = wr_commit && reg_sel[87];
  assign r87_rd    = rd_commit && reg_sel[87];
  // field VALUE [31:0] ro/input
  logic [31:0] r87_value_wb, r87_value_wm;
  assign r87_value_wb = r87_wdata[0 +: 32];
  assign r87_value_wm = r87_wmask[0 +: 32];
  always_comb begin
    r87_rdata = 32'h0;
    r87_rdata[0 +: 32] = tensor_dma_perf_value_i[128 +: 32];
  end

  // ======================================================================
  // r88: tensor.DMA_PERF[5] @ 64'h0000000150000214 (32-bit)
  // ======================================================================
  logic [31:0] r88_wdata, r88_wmask, r88_rdata;
  logic             r88_wr, r88_rd;
  assign r88_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r88_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r88_wr    = wr_commit && reg_sel[88];
  assign r88_rd    = rd_commit && reg_sel[88];
  // field VALUE [31:0] ro/input
  logic [31:0] r88_value_wb, r88_value_wm;
  assign r88_value_wb = r88_wdata[0 +: 32];
  assign r88_value_wm = r88_wmask[0 +: 32];
  always_comb begin
    r88_rdata = 32'h0;
    r88_rdata[0 +: 32] = tensor_dma_perf_value_i[160 +: 32];
  end

  // ======================================================================
  // r89: tensor.DMA_PERF[6] @ 64'h0000000150000218 (32-bit)
  // ======================================================================
  logic [31:0] r89_wdata, r89_wmask, r89_rdata;
  logic             r89_wr, r89_rd;
  assign r89_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r89_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r89_wr    = wr_commit && reg_sel[89];
  assign r89_rd    = rd_commit && reg_sel[89];
  // field VALUE [31:0] ro/input
  logic [31:0] r89_value_wb, r89_value_wm;
  assign r89_value_wb = r89_wdata[0 +: 32];
  assign r89_value_wm = r89_wmask[0 +: 32];
  always_comb begin
    r89_rdata = 32'h0;
    r89_rdata[0 +: 32] = tensor_dma_perf_value_i[192 +: 32];
  end

  // ======================================================================
  // r90: tensor.DMA_PERF[7] @ 64'h000000015000021c (32-bit)
  // ======================================================================
  logic [31:0] r90_wdata, r90_wmask, r90_rdata;
  logic             r90_wr, r90_rd;
  assign r90_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r90_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r90_wr    = wr_commit && reg_sel[90];
  assign r90_rd    = rd_commit && reg_sel[90];
  // field VALUE [31:0] ro/input
  logic [31:0] r90_value_wb, r90_value_wm;
  assign r90_value_wb = r90_wdata[0 +: 32];
  assign r90_value_wm = r90_wmask[0 +: 32];
  always_comb begin
    r90_rdata = 32'h0;
    r90_rdata[0 +: 32] = tensor_dma_perf_value_i[224 +: 32];
  end

  // ======================================================================
  // r91: tensor.DMA_PERF[8] @ 64'h0000000150000220 (32-bit)
  // ======================================================================
  logic [31:0] r91_wdata, r91_wmask, r91_rdata;
  logic             r91_wr, r91_rd;
  assign r91_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r91_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r91_wr    = wr_commit && reg_sel[91];
  assign r91_rd    = rd_commit && reg_sel[91];
  // field VALUE [31:0] ro/input
  logic [31:0] r91_value_wb, r91_value_wm;
  assign r91_value_wb = r91_wdata[0 +: 32];
  assign r91_value_wm = r91_wmask[0 +: 32];
  always_comb begin
    r91_rdata = 32'h0;
    r91_rdata[0 +: 32] = tensor_dma_perf_value_i[256 +: 32];
  end

  // ======================================================================
  // r92: tensor.DMA_PERF[9] @ 64'h0000000150000224 (32-bit)
  // ======================================================================
  logic [31:0] r92_wdata, r92_wmask, r92_rdata;
  logic             r92_wr, r92_rd;
  assign r92_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r92_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r92_wr    = wr_commit && reg_sel[92];
  assign r92_rd    = rd_commit && reg_sel[92];
  // field VALUE [31:0] ro/input
  logic [31:0] r92_value_wb, r92_value_wm;
  assign r92_value_wb = r92_wdata[0 +: 32];
  assign r92_value_wm = r92_wmask[0 +: 32];
  always_comb begin
    r92_rdata = 32'h0;
    r92_rdata[0 +: 32] = tensor_dma_perf_value_i[288 +: 32];
  end

  // ======================================================================
  // r93: tensor.DMA_PERF[10] @ 64'h0000000150000228 (32-bit)
  // ======================================================================
  logic [31:0] r93_wdata, r93_wmask, r93_rdata;
  logic             r93_wr, r93_rd;
  assign r93_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r93_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r93_wr    = wr_commit && reg_sel[93];
  assign r93_rd    = rd_commit && reg_sel[93];
  // field VALUE [31:0] ro/input
  logic [31:0] r93_value_wb, r93_value_wm;
  assign r93_value_wb = r93_wdata[0 +: 32];
  assign r93_value_wm = r93_wmask[0 +: 32];
  always_comb begin
    r93_rdata = 32'h0;
    r93_rdata[0 +: 32] = tensor_dma_perf_value_i[320 +: 32];
  end

  // ======================================================================
  // r94: tensor.DMA_PERF[11] @ 64'h000000015000022c (32-bit)
  // ======================================================================
  logic [31:0] r94_wdata, r94_wmask, r94_rdata;
  logic             r94_wr, r94_rd;
  assign r94_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r94_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r94_wr    = wr_commit && reg_sel[94];
  assign r94_rd    = rd_commit && reg_sel[94];
  // field VALUE [31:0] ro/input
  logic [31:0] r94_value_wb, r94_value_wm;
  assign r94_value_wb = r94_wdata[0 +: 32];
  assign r94_value_wm = r94_wmask[0 +: 32];
  always_comb begin
    r94_rdata = 32'h0;
    r94_rdata[0 +: 32] = tensor_dma_perf_value_i[352 +: 32];
  end

  // ======================================================================
  // r95: tensor.DMA_PERF[12] @ 64'h0000000150000230 (32-bit)
  // ======================================================================
  logic [31:0] r95_wdata, r95_wmask, r95_rdata;
  logic             r95_wr, r95_rd;
  assign r95_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r95_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r95_wr    = wr_commit && reg_sel[95];
  assign r95_rd    = rd_commit && reg_sel[95];
  // field VALUE [31:0] ro/input
  logic [31:0] r95_value_wb, r95_value_wm;
  assign r95_value_wb = r95_wdata[0 +: 32];
  assign r95_value_wm = r95_wmask[0 +: 32];
  always_comb begin
    r95_rdata = 32'h0;
    r95_rdata[0 +: 32] = tensor_dma_perf_value_i[384 +: 32];
  end

  // ======================================================================
  // r96: tensor.DMA_PERF[13] @ 64'h0000000150000234 (32-bit)
  // ======================================================================
  logic [31:0] r96_wdata, r96_wmask, r96_rdata;
  logic             r96_wr, r96_rd;
  assign r96_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r96_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r96_wr    = wr_commit && reg_sel[96];
  assign r96_rd    = rd_commit && reg_sel[96];
  // field VALUE [31:0] ro/input
  logic [31:0] r96_value_wb, r96_value_wm;
  assign r96_value_wb = r96_wdata[0 +: 32];
  assign r96_value_wm = r96_wmask[0 +: 32];
  always_comb begin
    r96_rdata = 32'h0;
    r96_rdata[0 +: 32] = tensor_dma_perf_value_i[416 +: 32];
  end

  // ======================================================================
  // r97: tensor.DMA_PERF[14] @ 64'h0000000150000238 (32-bit)
  // ======================================================================
  logic [31:0] r97_wdata, r97_wmask, r97_rdata;
  logic             r97_wr, r97_rd;
  assign r97_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r97_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r97_wr    = wr_commit && reg_sel[97];
  assign r97_rd    = rd_commit && reg_sel[97];
  // field VALUE [31:0] ro/input
  logic [31:0] r97_value_wb, r97_value_wm;
  assign r97_value_wb = r97_wdata[0 +: 32];
  assign r97_value_wm = r97_wmask[0 +: 32];
  always_comb begin
    r97_rdata = 32'h0;
    r97_rdata[0 +: 32] = tensor_dma_perf_value_i[448 +: 32];
  end

  // ======================================================================
  // r98: tensor.DMA_PERF[15] @ 64'h000000015000023c (32-bit)
  // ======================================================================
  logic [31:0] r98_wdata, r98_wmask, r98_rdata;
  logic             r98_wr, r98_rd;
  assign r98_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r98_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r98_wr    = wr_commit && reg_sel[98];
  assign r98_rd    = rd_commit && reg_sel[98];
  // field VALUE [31:0] ro/input
  logic [31:0] r98_value_wb, r98_value_wm;
  assign r98_value_wb = r98_wdata[0 +: 32];
  assign r98_value_wm = r98_wmask[0 +: 32];
  always_comb begin
    r98_rdata = 32'h0;
    r98_rdata[0 +: 32] = tensor_dma_perf_value_i[480 +: 32];
  end

  // ======================================================================
  // r99: tensor.DMA_PERF[16] @ 64'h0000000150000240 (32-bit)
  // ======================================================================
  logic [31:0] r99_wdata, r99_wmask, r99_rdata;
  logic             r99_wr, r99_rd;
  assign r99_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r99_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r99_wr    = wr_commit && reg_sel[99];
  assign r99_rd    = rd_commit && reg_sel[99];
  // field VALUE [31:0] ro/input
  logic [31:0] r99_value_wb, r99_value_wm;
  assign r99_value_wb = r99_wdata[0 +: 32];
  assign r99_value_wm = r99_wmask[0 +: 32];
  always_comb begin
    r99_rdata = 32'h0;
    r99_rdata[0 +: 32] = tensor_dma_perf_value_i[512 +: 32];
  end

  // ======================================================================
  // r100: tensor.DMA_PERF[17] @ 64'h0000000150000244 (32-bit)
  // ======================================================================
  logic [31:0] r100_wdata, r100_wmask, r100_rdata;
  logic             r100_wr, r100_rd;
  assign r100_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r100_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r100_wr    = wr_commit && reg_sel[100];
  assign r100_rd    = rd_commit && reg_sel[100];
  // field VALUE [31:0] ro/input
  logic [31:0] r100_value_wb, r100_value_wm;
  assign r100_value_wb = r100_wdata[0 +: 32];
  assign r100_value_wm = r100_wmask[0 +: 32];
  always_comb begin
    r100_rdata = 32'h0;
    r100_rdata[0 +: 32] = tensor_dma_perf_value_i[544 +: 32];
  end

  // ======================================================================
  // r101: vector.ID @ 64'h0000000150001000 (32-bit)
  // ======================================================================
  logic [31:0] r101_wdata, r101_wmask, r101_rdata;
  logic             r101_wr, r101_rd;
  assign r101_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r101_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r101_wr    = wr_commit && reg_sel[101];
  assign r101_rd    = rd_commit && reg_sel[101];
  // field VALUE [31:0] ro/const
  logic [31:0] r101_value_wb, r101_value_wm;
  assign r101_value_wb = r101_wdata[0 +: 32];
  assign r101_value_wm = r101_wmask[0 +: 32];
  always_comb begin
    r101_rdata = 32'h0;
    r101_rdata[0 +: 32] = 32'h53464351;
  end

  // ======================================================================
  // r102: vector.INFO @ 64'h0000000150001004 (32-bit)
  // ======================================================================
  logic [31:0] r102_wdata, r102_wmask, r102_rdata;
  logic             r102_wr, r102_rd;
  assign r102_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r102_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r102_wr    = wr_commit && reg_sel[102];
  assign r102_rd    = rd_commit && reg_sel[102];
  // field ABI_VERSION [3:0] ro/input
  logic [3:0] r102_abi_version_wb, r102_abi_version_wm;
  assign r102_abi_version_wb = r102_wdata[0 +: 4];
  assign r102_abi_version_wm = r102_wmask[0 +: 4];
  // field QUEUE_DEPTH [15:8] ro/input
  logic [7:0] r102_queue_depth_wb, r102_queue_depth_wm;
  assign r102_queue_depth_wb = r102_wdata[8 +: 8];
  assign r102_queue_depth_wm = r102_wmask[8 +: 8];
  // field ROB_DEPTH [23:16] ro/input
  logic [7:0] r102_rob_depth_wb, r102_rob_depth_wm;
  assign r102_rob_depth_wb = r102_wdata[16 +: 8];
  assign r102_rob_depth_wm = r102_wmask[16 +: 8];
  // field OPSET_FULL [24:24] ro/input
  logic [0:0] r102_opset_full_wb, r102_opset_full_wm;
  assign r102_opset_full_wb = r102_wdata[24 +: 1];
  assign r102_opset_full_wm = r102_wmask[24 +: 1];
  // field OVERLAP_EN [25:25] ro/input
  logic [0:0] r102_overlap_en_wb, r102_overlap_en_wm;
  assign r102_overlap_en_wb = r102_wdata[25 +: 1];
  assign r102_overlap_en_wm = r102_wmask[25 +: 1];
  // field PERF_EN [26:26] ro/input
  logic [0:0] r102_perf_en_wb, r102_perf_en_wm;
  assign r102_perf_en_wb = r102_wdata[26 +: 1];
  assign r102_perf_en_wm = r102_wmask[26 +: 1];
  always_comb begin
    r102_rdata = 32'h0;
    r102_rdata[0 +: 4] = vector_info_abi_version_i[0 +: 4];
    r102_rdata[8 +: 8] = vector_info_queue_depth_i[0 +: 8];
    r102_rdata[16 +: 8] = vector_info_rob_depth_i[0 +: 8];
    r102_rdata[24 +: 1] = vector_info_opset_full_i[0 +: 1];
    r102_rdata[25 +: 1] = vector_info_overlap_en_i[0 +: 1];
    r102_rdata[26 +: 1] = vector_info_perf_en_i[0 +: 1];
  end

  // ======================================================================
  // r103: vector.CTRL @ 64'h0000000150001008 (32-bit)
  // ======================================================================
  logic [31:0] r103_wdata, r103_wmask, r103_rdata;
  logic             r103_wr, r103_rd;
  assign r103_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r103_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r103_wr    = wr_commit && reg_sel[103];
  assign r103_rd    = rd_commit && reg_sel[103];
  // field ERR_CONT [0:0] rw/none
  logic [0:0] r103_err_cont_wb, r103_err_cont_wm;
  assign r103_err_cont_wb = r103_wdata[0 +: 1];
  assign r103_err_cont_wm = r103_wmask[0 +: 1];
  logic [0:0] r103_err_cont_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r103_err_cont_q <= 1'h0;
    else if (r103_wr && (|r103_err_cont_wm)) r103_err_cont_q <= ((r103_err_cont_q & ~r103_err_cont_wm) | (r103_err_cont_wb & r103_err_cont_wm));
  end
  assign vector_ctrl_err_cont_o[0 +: 1] = r103_err_cont_q;
  // field ERR_CLEAR [1:1] w1p
  logic [0:0] r103_err_clear_wb, r103_err_clear_wm;
  assign r103_err_clear_wb = r103_wdata[1 +: 1];
  assign r103_err_clear_wm = r103_wmask[1 +: 1];
  logic [0:0] r103_err_clear_pulse_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r103_err_clear_pulse_q <= 1'h0;
    else r103_err_clear_pulse_q <= {1{r103_wr}} & r103_err_clear_wb & r103_err_clear_wm;
  end
  assign vector_ctrl_err_clear_pulse_o[0 +: 1] = r103_err_clear_pulse_q;
  // field PERF_CLEAR [2:2] w1p
  logic [0:0] r103_perf_clear_wb, r103_perf_clear_wm;
  assign r103_perf_clear_wb = r103_wdata[2 +: 1];
  assign r103_perf_clear_wm = r103_wmask[2 +: 1];
  logic [0:0] r103_perf_clear_pulse_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r103_perf_clear_pulse_q <= 1'h0;
    else r103_perf_clear_pulse_q <= {1{r103_wr}} & r103_perf_clear_wb & r103_perf_clear_wm;
  end
  assign vector_ctrl_perf_clear_pulse_o[0 +: 1] = r103_perf_clear_pulse_q;
  always_comb begin
    r103_rdata = 32'h0;
    r103_rdata[0 +: 1] = r103_err_cont_q;
  end

  // ======================================================================
  // r104: vector.STATUS @ 64'h000000015000100c (32-bit)
  // ======================================================================
  logic [31:0] r104_wdata, r104_wmask, r104_rdata;
  logic             r104_wr, r104_rd;
  assign r104_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r104_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r104_wr    = wr_commit && reg_sel[104];
  assign r104_rd    = rd_commit && reg_sel[104];
  // field BUSY [0:0] ro/input
  logic [0:0] r104_busy_wb, r104_busy_wm;
  assign r104_busy_wb = r104_wdata[0 +: 1];
  assign r104_busy_wm = r104_wmask[0 +: 1];
  // field ERR_STICKY [1:1] ro/input
  logic [0:0] r104_err_sticky_wb, r104_err_sticky_wm;
  assign r104_err_sticky_wb = r104_wdata[1 +: 1];
  assign r104_err_sticky_wm = r104_wmask[1 +: 1];
  // field Q_FULL [2:2] ro/input
  logic [0:0] r104_q_full_wb, r104_q_full_wm;
  assign r104_q_full_wb = r104_wdata[2 +: 1];
  assign r104_q_full_wm = r104_wmask[2 +: 1];
  // field Q_EMPTY [3:3] ro/input
  logic [0:0] r104_q_empty_wb, r104_q_empty_wm;
  assign r104_q_empty_wb = r104_wdata[3 +: 1];
  assign r104_q_empty_wm = r104_wmask[3 +: 1];
  // field CPL_VALID [4:4] ro/input
  logic [0:0] r104_cpl_valid_wb, r104_cpl_valid_wm;
  assign r104_cpl_valid_wb = r104_wdata[4 +: 1];
  assign r104_cpl_valid_wm = r104_wmask[4 +: 1];
  // field DMA_DOWN [5:5] ro/input
  logic [0:0] r104_dma_down_wb, r104_dma_down_wm;
  assign r104_dma_down_wb = r104_wdata[5 +: 1];
  assign r104_dma_down_wm = r104_wmask[5 +: 1];
  // field VEC_DOWN [6:6] ro/input
  logic [0:0] r104_vec_down_wb, r104_vec_down_wm;
  assign r104_vec_down_wb = r104_wdata[6 +: 1];
  assign r104_vec_down_wm = r104_wmask[6 +: 1];
  // field Q_COUNT [15:8] ro/input
  logic [7:0] r104_q_count_wb, r104_q_count_wm;
  assign r104_q_count_wb = r104_wdata[8 +: 8];
  assign r104_q_count_wm = r104_wmask[8 +: 8];
  // field ROB_COUNT [23:16] ro/input
  logic [7:0] r104_rob_count_wb, r104_rob_count_wm;
  assign r104_rob_count_wb = r104_wdata[16 +: 8];
  assign r104_rob_count_wm = r104_wmask[16 +: 8];
  // field Q_FREE [31:24] ro/input
  logic [7:0] r104_q_free_wb, r104_q_free_wm;
  assign r104_q_free_wb = r104_wdata[24 +: 8];
  assign r104_q_free_wm = r104_wmask[24 +: 8];
  always_comb begin
    r104_rdata = 32'h0;
    r104_rdata[0 +: 1] = vector_status_busy_i[0 +: 1];
    r104_rdata[1 +: 1] = vector_status_err_sticky_i[0 +: 1];
    r104_rdata[2 +: 1] = vector_status_q_full_i[0 +: 1];
    r104_rdata[3 +: 1] = vector_status_q_empty_i[0 +: 1];
    r104_rdata[4 +: 1] = vector_status_cpl_valid_i[0 +: 1];
    r104_rdata[5 +: 1] = vector_status_dma_down_i[0 +: 1];
    r104_rdata[6 +: 1] = vector_status_vec_down_i[0 +: 1];
    r104_rdata[8 +: 8] = vector_status_q_count_i[0 +: 8];
    r104_rdata[16 +: 8] = vector_status_rob_count_i[0 +: 8];
    r104_rdata[24 +: 8] = vector_status_q_free_i[0 +: 8];
  end

  // ======================================================================
  // r105: vector.INT_ENABLE @ 64'h0000000150001010 (32-bit)
  // ======================================================================
  logic [31:0] r105_wdata, r105_wmask, r105_rdata;
  logic             r105_wr, r105_rd;
  assign r105_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r105_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r105_wr    = wr_commit && reg_sel[105];
  assign r105_rd    = rd_commit && reg_sel[105];
  // field IRQ [0:0] rw/none
  logic [0:0] r105_irq_wb, r105_irq_wm;
  assign r105_irq_wb = r105_wdata[0 +: 1];
  assign r105_irq_wm = r105_wmask[0 +: 1];
  logic [0:0] r105_irq_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r105_irq_q <= 1'h0;
    else if (r105_wr && (|r105_irq_wm)) r105_irq_q <= ((r105_irq_q & ~r105_irq_wm) | (r105_irq_wb & r105_irq_wm));
  end
  assign vector_int_enable_irq_o[0 +: 1] = r105_irq_q;
  // field ERR [1:1] rw/none
  logic [0:0] r105_err_wb, r105_err_wm;
  assign r105_err_wb = r105_wdata[1 +: 1];
  assign r105_err_wm = r105_wmask[1 +: 1];
  logic [0:0] r105_err_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r105_err_q <= 1'h0;
    else if (r105_wr && (|r105_err_wm)) r105_err_q <= ((r105_err_q & ~r105_err_wm) | (r105_err_wb & r105_err_wm));
  end
  assign vector_int_enable_err_o[0 +: 1] = r105_err_q;
  always_comb begin
    r105_rdata = 32'h0;
    r105_rdata[0 +: 1] = r105_irq_q;
    r105_rdata[1 +: 1] = r105_err_q;
  end

  // ======================================================================
  // r106: vector.INT_STATUS @ 64'h0000000150001014 (32-bit)
  // ======================================================================
  logic [31:0] r106_wdata, r106_wmask, r106_rdata;
  logic             r106_wr, r106_rd;
  assign r106_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r106_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r106_wr    = wr_commit && reg_sel[106];
  assign r106_rd    = rd_commit && reg_sel[106];
  // field IRQ [0:0] w1c/event
  logic [0:0] r106_irq_wb, r106_irq_wm;
  assign r106_irq_wb = r106_wdata[0 +: 1];
  assign r106_irq_wm = r106_wmask[0 +: 1];
  logic [0:0] r106_irq_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r106_irq_q <= 1'h0;
    else r106_irq_q <= ((r106_irq_q & ~({1{r106_wr}} & r106_irq_wb & r106_irq_wm)) | vector_int_status_irq_set_i[0 +: 1]);
  end
  assign vector_int_status_irq_o[0 +: 1] = r106_irq_q;
  // field ERR [1:1] w1c/event
  logic [0:0] r106_err_wb, r106_err_wm;
  assign r106_err_wb = r106_wdata[1 +: 1];
  assign r106_err_wm = r106_wmask[1 +: 1];
  logic [0:0] r106_err_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r106_err_q <= 1'h0;
    else r106_err_q <= ((r106_err_q & ~({1{r106_wr}} & r106_err_wb & r106_err_wm)) | vector_int_status_err_set_i[0 +: 1]);
  end
  assign vector_int_status_err_o[0 +: 1] = r106_err_q;
  always_comb begin
    r106_rdata = 32'h0;
    r106_rdata[0 +: 1] = r106_irq_q;
    r106_rdata[1 +: 1] = r106_err_q;
  end

  // ======================================================================
  // r107: vector.SUBMITTED @ 64'h0000000150001018 (32-bit)
  // ======================================================================
  logic [31:0] r107_wdata, r107_wmask, r107_rdata;
  logic             r107_wr, r107_rd;
  assign r107_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r107_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r107_wr    = wr_commit && reg_sel[107];
  assign r107_rd    = rd_commit && reg_sel[107];
  // field VALUE [31:0] ro/input
  logic [31:0] r107_value_wb, r107_value_wm;
  assign r107_value_wb = r107_wdata[0 +: 32];
  assign r107_value_wm = r107_wmask[0 +: 32];
  always_comb begin
    r107_rdata = 32'h0;
    r107_rdata[0 +: 32] = vector_submitted_value_i[0 +: 32];
  end

  // ======================================================================
  // r108: vector.DESC[0] @ 64'h0000000150001020 (32-bit)
  // ======================================================================
  logic [31:0] r108_wdata, r108_wmask, r108_rdata;
  logic             r108_wr, r108_rd;
  assign r108_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r108_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r108_wr    = wr_commit && reg_sel[108];
  assign r108_rd    = rd_commit && reg_sel[108];
  // field VALUE [31:0] rw/none
  logic [31:0] r108_value_wb, r108_value_wm;
  assign r108_value_wb = r108_wdata[0 +: 32];
  assign r108_value_wm = r108_wmask[0 +: 32];
  logic [31:0] r108_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r108_value_q <= 32'h00000000;
    else if (r108_wr && (|r108_value_wm)) r108_value_q <= ((r108_value_q & ~r108_value_wm) | (r108_value_wb & r108_value_wm));
  end
  assign vector_desc_value_o[0 +: 32] = r108_value_q;
  always_comb begin
    r108_rdata = 32'h0;
    r108_rdata[0 +: 32] = r108_value_q;
  end

  // ======================================================================
  // r109: vector.DESC[1] @ 64'h0000000150001024 (32-bit)
  // ======================================================================
  logic [31:0] r109_wdata, r109_wmask, r109_rdata;
  logic             r109_wr, r109_rd;
  assign r109_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r109_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r109_wr    = wr_commit && reg_sel[109];
  assign r109_rd    = rd_commit && reg_sel[109];
  // field VALUE [31:0] rw/none
  logic [31:0] r109_value_wb, r109_value_wm;
  assign r109_value_wb = r109_wdata[0 +: 32];
  assign r109_value_wm = r109_wmask[0 +: 32];
  logic [31:0] r109_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r109_value_q <= 32'h00000000;
    else if (r109_wr && (|r109_value_wm)) r109_value_q <= ((r109_value_q & ~r109_value_wm) | (r109_value_wb & r109_value_wm));
  end
  assign vector_desc_value_o[32 +: 32] = r109_value_q;
  always_comb begin
    r109_rdata = 32'h0;
    r109_rdata[0 +: 32] = r109_value_q;
  end

  // ======================================================================
  // r110: vector.DESC[2] @ 64'h0000000150001028 (32-bit)
  // ======================================================================
  logic [31:0] r110_wdata, r110_wmask, r110_rdata;
  logic             r110_wr, r110_rd;
  assign r110_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r110_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r110_wr    = wr_commit && reg_sel[110];
  assign r110_rd    = rd_commit && reg_sel[110];
  // field VALUE [31:0] rw/none
  logic [31:0] r110_value_wb, r110_value_wm;
  assign r110_value_wb = r110_wdata[0 +: 32];
  assign r110_value_wm = r110_wmask[0 +: 32];
  logic [31:0] r110_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r110_value_q <= 32'h00000000;
    else if (r110_wr && (|r110_value_wm)) r110_value_q <= ((r110_value_q & ~r110_value_wm) | (r110_value_wb & r110_value_wm));
  end
  assign vector_desc_value_o[64 +: 32] = r110_value_q;
  always_comb begin
    r110_rdata = 32'h0;
    r110_rdata[0 +: 32] = r110_value_q;
  end

  // ======================================================================
  // r111: vector.DESC[3] @ 64'h000000015000102c (32-bit)
  // ======================================================================
  logic [31:0] r111_wdata, r111_wmask, r111_rdata;
  logic             r111_wr, r111_rd;
  assign r111_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r111_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r111_wr    = wr_commit && reg_sel[111];
  assign r111_rd    = rd_commit && reg_sel[111];
  // field VALUE [31:0] rw/none
  logic [31:0] r111_value_wb, r111_value_wm;
  assign r111_value_wb = r111_wdata[0 +: 32];
  assign r111_value_wm = r111_wmask[0 +: 32];
  logic [31:0] r111_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r111_value_q <= 32'h00000000;
    else if (r111_wr && (|r111_value_wm)) r111_value_q <= ((r111_value_q & ~r111_value_wm) | (r111_value_wb & r111_value_wm));
  end
  assign vector_desc_value_o[96 +: 32] = r111_value_q;
  always_comb begin
    r111_rdata = 32'h0;
    r111_rdata[0 +: 32] = r111_value_q;
  end

  // ======================================================================
  // r112: vector.DESC[4] @ 64'h0000000150001030 (32-bit)
  // ======================================================================
  logic [31:0] r112_wdata, r112_wmask, r112_rdata;
  logic             r112_wr, r112_rd;
  assign r112_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r112_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r112_wr    = wr_commit && reg_sel[112];
  assign r112_rd    = rd_commit && reg_sel[112];
  // field VALUE [31:0] rw/none
  logic [31:0] r112_value_wb, r112_value_wm;
  assign r112_value_wb = r112_wdata[0 +: 32];
  assign r112_value_wm = r112_wmask[0 +: 32];
  logic [31:0] r112_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r112_value_q <= 32'h00000000;
    else if (r112_wr && (|r112_value_wm)) r112_value_q <= ((r112_value_q & ~r112_value_wm) | (r112_value_wb & r112_value_wm));
  end
  assign vector_desc_value_o[128 +: 32] = r112_value_q;
  always_comb begin
    r112_rdata = 32'h0;
    r112_rdata[0 +: 32] = r112_value_q;
  end

  // ======================================================================
  // r113: vector.DESC[5] @ 64'h0000000150001034 (32-bit)
  // ======================================================================
  logic [31:0] r113_wdata, r113_wmask, r113_rdata;
  logic             r113_wr, r113_rd;
  assign r113_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r113_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r113_wr    = wr_commit && reg_sel[113];
  assign r113_rd    = rd_commit && reg_sel[113];
  // field VALUE [31:0] rw/none
  logic [31:0] r113_value_wb, r113_value_wm;
  assign r113_value_wb = r113_wdata[0 +: 32];
  assign r113_value_wm = r113_wmask[0 +: 32];
  logic [31:0] r113_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r113_value_q <= 32'h00000000;
    else if (r113_wr && (|r113_value_wm)) r113_value_q <= ((r113_value_q & ~r113_value_wm) | (r113_value_wb & r113_value_wm));
  end
  assign vector_desc_value_o[160 +: 32] = r113_value_q;
  always_comb begin
    r113_rdata = 32'h0;
    r113_rdata[0 +: 32] = r113_value_q;
  end

  // ======================================================================
  // r114: vector.DESC[6] @ 64'h0000000150001038 (32-bit)
  // ======================================================================
  logic [31:0] r114_wdata, r114_wmask, r114_rdata;
  logic             r114_wr, r114_rd;
  assign r114_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r114_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r114_wr    = wr_commit && reg_sel[114];
  assign r114_rd    = rd_commit && reg_sel[114];
  // field VALUE [31:0] rw/none
  logic [31:0] r114_value_wb, r114_value_wm;
  assign r114_value_wb = r114_wdata[0 +: 32];
  assign r114_value_wm = r114_wmask[0 +: 32];
  logic [31:0] r114_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r114_value_q <= 32'h00000000;
    else if (r114_wr && (|r114_value_wm)) r114_value_q <= ((r114_value_q & ~r114_value_wm) | (r114_value_wb & r114_value_wm));
  end
  assign vector_desc_value_o[192 +: 32] = r114_value_q;
  always_comb begin
    r114_rdata = 32'h0;
    r114_rdata[0 +: 32] = r114_value_q;
  end

  // ======================================================================
  // r115: vector.DESC[7] @ 64'h000000015000103c (32-bit)
  // ======================================================================
  logic [31:0] r115_wdata, r115_wmask, r115_rdata;
  logic             r115_wr, r115_rd;
  assign r115_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r115_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r115_wr    = wr_commit && reg_sel[115];
  assign r115_rd    = rd_commit && reg_sel[115];
  // field VALUE [31:0] rw/none
  logic [31:0] r115_value_wb, r115_value_wm;
  assign r115_value_wb = r115_wdata[0 +: 32];
  assign r115_value_wm = r115_wmask[0 +: 32];
  logic [31:0] r115_value_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r115_value_q <= 32'h00000000;
    else if (r115_wr && (|r115_value_wm)) r115_value_q <= ((r115_value_q & ~r115_value_wm) | (r115_value_wb & r115_value_wm));
  end
  assign vector_desc_value_o[224 +: 32] = r115_value_q;
  always_comb begin
    r115_rdata = 32'h0;
    r115_rdata[0 +: 32] = r115_value_q;
  end

  // ======================================================================
  // r116: vector.DOORBELL @ 64'h0000000150001040 (32-bit)
  // ======================================================================
  logic [31:0] r116_wdata, r116_wmask, r116_rdata;
  logic             r116_wr, r116_rd;
  assign r116_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r116_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r116_wr    = wr_commit && reg_sel[116];
  assign r116_rd    = rd_commit && reg_sel[116];
  // field RING [31:0] wo/none
  logic [31:0] r116_ring_wb, r116_ring_wm;
  assign r116_ring_wb = r116_wdata[0 +: 32];
  assign r116_ring_wm = r116_wmask[0 +: 32];
  logic r116_wr_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r116_wr_q <= 1'b0;
    else r116_wr_q <= r116_wr;
  end
  assign vector_doorbell_wr_o[0 +: 1] = r116_wr_q;
  always_comb begin
    r116_rdata = 32'h0;
  end

  // ======================================================================
  // r117: vector.CPL[0] @ 64'h0000000150001050 (32-bit)
  // ======================================================================
  logic [31:0] r117_wdata, r117_wmask, r117_rdata;
  logic             r117_wr, r117_rd;
  assign r117_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r117_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r117_wr    = wr_commit && reg_sel[117];
  assign r117_rd    = rd_commit && reg_sel[117];
  // field VALUE [31:0] ro/input
  logic [31:0] r117_value_wb, r117_value_wm;
  assign r117_value_wb = r117_wdata[0 +: 32];
  assign r117_value_wm = r117_wmask[0 +: 32];
  always_comb begin
    r117_rdata = 32'h0;
    r117_rdata[0 +: 32] = vector_cpl_value_i[0 +: 32];
  end

  // ======================================================================
  // r118: vector.CPL[1] @ 64'h0000000150001054 (32-bit)
  // ======================================================================
  logic [31:0] r118_wdata, r118_wmask, r118_rdata;
  logic             r118_wr, r118_rd;
  assign r118_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r118_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r118_wr    = wr_commit && reg_sel[118];
  assign r118_rd    = rd_commit && reg_sel[118];
  // field VALUE [31:0] ro/input
  logic [31:0] r118_value_wb, r118_value_wm;
  assign r118_value_wb = r118_wdata[0 +: 32];
  assign r118_value_wm = r118_wmask[0 +: 32];
  always_comb begin
    r118_rdata = 32'h0;
    r118_rdata[0 +: 32] = vector_cpl_value_i[32 +: 32];
  end

  // ======================================================================
  // r119: vector.CPL[2] @ 64'h0000000150001058 (32-bit)
  // ======================================================================
  logic [31:0] r119_wdata, r119_wmask, r119_rdata;
  logic             r119_wr, r119_rd;
  assign r119_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r119_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r119_wr    = wr_commit && reg_sel[119];
  assign r119_rd    = rd_commit && reg_sel[119];
  // field VALUE [31:0] ro/input
  logic [31:0] r119_value_wb, r119_value_wm;
  assign r119_value_wb = r119_wdata[0 +: 32];
  assign r119_value_wm = r119_wmask[0 +: 32];
  always_comb begin
    r119_rdata = 32'h0;
    r119_rdata[0 +: 32] = vector_cpl_value_i[64 +: 32];
  end

  // ======================================================================
  // r120: vector.CPL[3] @ 64'h000000015000105c (32-bit)
  // ======================================================================
  logic [31:0] r120_wdata, r120_wmask, r120_rdata;
  logic             r120_wr, r120_rd;
  assign r120_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r120_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r120_wr    = wr_commit && reg_sel[120];
  assign r120_rd    = rd_commit && reg_sel[120];
  // field VALUE [31:0] ro/input
  logic [31:0] r120_value_wb, r120_value_wm;
  assign r120_value_wb = r120_wdata[0 +: 32];
  assign r120_value_wm = r120_wmask[0 +: 32];
  always_comb begin
    r120_rdata = 32'h0;
    r120_rdata[0 +: 32] = vector_cpl_value_i[96 +: 32];
  end

  // ======================================================================
  // r121: vector.CPL_POP @ 64'h0000000150001060 (32-bit)
  // ======================================================================
  logic [31:0] r121_wdata, r121_wmask, r121_rdata;
  logic             r121_wr, r121_rd;
  assign r121_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r121_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r121_wr    = wr_commit && reg_sel[121];
  assign r121_rd    = rd_commit && reg_sel[121];
  // field POP [31:0] wo/none
  logic [31:0] r121_pop_wb, r121_pop_wm;
  assign r121_pop_wb = r121_wdata[0 +: 32];
  assign r121_pop_wm = r121_wmask[0 +: 32];
  logic r121_wr_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r121_wr_q <= 1'b0;
    else r121_wr_q <= r121_wr;
  end
  assign vector_cpl_pop_wr_o[0 +: 1] = r121_wr_q;
  always_comb begin
    r121_rdata = 32'h0;
  end

  // ======================================================================
  // r122: vector.PERF[0] @ 64'h0000000150001080 (32-bit)
  // ======================================================================
  logic [31:0] r122_wdata, r122_wmask, r122_rdata;
  logic             r122_wr, r122_rd;
  assign r122_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r122_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r122_wr    = wr_commit && reg_sel[122];
  assign r122_rd    = rd_commit && reg_sel[122];
  // field VALUE [31:0] ro/input
  logic [31:0] r122_value_wb, r122_value_wm;
  assign r122_value_wb = r122_wdata[0 +: 32];
  assign r122_value_wm = r122_wmask[0 +: 32];
  always_comb begin
    r122_rdata = 32'h0;
    r122_rdata[0 +: 32] = vector_perf_value_i[0 +: 32];
  end

  // ======================================================================
  // r123: vector.PERF[1] @ 64'h0000000150001084 (32-bit)
  // ======================================================================
  logic [31:0] r123_wdata, r123_wmask, r123_rdata;
  logic             r123_wr, r123_rd;
  assign r123_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r123_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r123_wr    = wr_commit && reg_sel[123];
  assign r123_rd    = rd_commit && reg_sel[123];
  // field VALUE [31:0] ro/input
  logic [31:0] r123_value_wb, r123_value_wm;
  assign r123_value_wb = r123_wdata[0 +: 32];
  assign r123_value_wm = r123_wmask[0 +: 32];
  always_comb begin
    r123_rdata = 32'h0;
    r123_rdata[0 +: 32] = vector_perf_value_i[32 +: 32];
  end

  // ======================================================================
  // r124: vector.PERF[2] @ 64'h0000000150001088 (32-bit)
  // ======================================================================
  logic [31:0] r124_wdata, r124_wmask, r124_rdata;
  logic             r124_wr, r124_rd;
  assign r124_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r124_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r124_wr    = wr_commit && reg_sel[124];
  assign r124_rd    = rd_commit && reg_sel[124];
  // field VALUE [31:0] ro/input
  logic [31:0] r124_value_wb, r124_value_wm;
  assign r124_value_wb = r124_wdata[0 +: 32];
  assign r124_value_wm = r124_wmask[0 +: 32];
  always_comb begin
    r124_rdata = 32'h0;
    r124_rdata[0 +: 32] = vector_perf_value_i[64 +: 32];
  end

  // ======================================================================
  // r125: vector.PERF[3] @ 64'h000000015000108c (32-bit)
  // ======================================================================
  logic [31:0] r125_wdata, r125_wmask, r125_rdata;
  logic             r125_wr, r125_rd;
  assign r125_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r125_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r125_wr    = wr_commit && reg_sel[125];
  assign r125_rd    = rd_commit && reg_sel[125];
  // field VALUE [31:0] ro/input
  logic [31:0] r125_value_wb, r125_value_wm;
  assign r125_value_wb = r125_wdata[0 +: 32];
  assign r125_value_wm = r125_wmask[0 +: 32];
  always_comb begin
    r125_rdata = 32'h0;
    r125_rdata[0 +: 32] = vector_perf_value_i[96 +: 32];
  end

  // ======================================================================
  // r126: vector.PERF[4] @ 64'h0000000150001090 (32-bit)
  // ======================================================================
  logic [31:0] r126_wdata, r126_wmask, r126_rdata;
  logic             r126_wr, r126_rd;
  assign r126_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r126_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r126_wr    = wr_commit && reg_sel[126];
  assign r126_rd    = rd_commit && reg_sel[126];
  // field VALUE [31:0] ro/input
  logic [31:0] r126_value_wb, r126_value_wm;
  assign r126_value_wb = r126_wdata[0 +: 32];
  assign r126_value_wm = r126_wmask[0 +: 32];
  always_comb begin
    r126_rdata = 32'h0;
    r126_rdata[0 +: 32] = vector_perf_value_i[128 +: 32];
  end

  // ======================================================================
  // r127: vector.PERF[5] @ 64'h0000000150001094 (32-bit)
  // ======================================================================
  logic [31:0] r127_wdata, r127_wmask, r127_rdata;
  logic             r127_wr, r127_rd;
  assign r127_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r127_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r127_wr    = wr_commit && reg_sel[127];
  assign r127_rd    = rd_commit && reg_sel[127];
  // field VALUE [31:0] ro/input
  logic [31:0] r127_value_wb, r127_value_wm;
  assign r127_value_wb = r127_wdata[0 +: 32];
  assign r127_value_wm = r127_wmask[0 +: 32];
  always_comb begin
    r127_rdata = 32'h0;
    r127_rdata[0 +: 32] = vector_perf_value_i[160 +: 32];
  end

  // ======================================================================
  // r128: vector.PERF[6] @ 64'h0000000150001098 (32-bit)
  // ======================================================================
  logic [31:0] r128_wdata, r128_wmask, r128_rdata;
  logic             r128_wr, r128_rd;
  assign r128_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r128_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r128_wr    = wr_commit && reg_sel[128];
  assign r128_rd    = rd_commit && reg_sel[128];
  // field VALUE [31:0] ro/input
  logic [31:0] r128_value_wb, r128_value_wm;
  assign r128_value_wb = r128_wdata[0 +: 32];
  assign r128_value_wm = r128_wmask[0 +: 32];
  always_comb begin
    r128_rdata = 32'h0;
    r128_rdata[0 +: 32] = vector_perf_value_i[192 +: 32];
  end

  // ======================================================================
  // r129: vector.PERF[7] @ 64'h000000015000109c (32-bit)
  // ======================================================================
  logic [31:0] r129_wdata, r129_wmask, r129_rdata;
  logic             r129_wr, r129_rd;
  assign r129_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r129_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r129_wr    = wr_commit && reg_sel[129];
  assign r129_rd    = rd_commit && reg_sel[129];
  // field VALUE [31:0] ro/input
  logic [31:0] r129_value_wb, r129_value_wm;
  assign r129_value_wb = r129_wdata[0 +: 32];
  assign r129_value_wm = r129_wmask[0 +: 32];
  always_comb begin
    r129_rdata = 32'h0;
    r129_rdata[0 +: 32] = vector_perf_value_i[224 +: 32];
  end

  // ======================================================================
  // r130: vector.PERF[8] @ 64'h00000001500010a0 (32-bit)
  // ======================================================================
  logic [31:0] r130_wdata, r130_wmask, r130_rdata;
  logic             r130_wr, r130_rd;
  assign r130_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r130_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r130_wr    = wr_commit && reg_sel[130];
  assign r130_rd    = rd_commit && reg_sel[130];
  // field VALUE [31:0] ro/input
  logic [31:0] r130_value_wb, r130_value_wm;
  assign r130_value_wb = r130_wdata[0 +: 32];
  assign r130_value_wm = r130_wmask[0 +: 32];
  always_comb begin
    r130_rdata = 32'h0;
    r130_rdata[0 +: 32] = vector_perf_value_i[256 +: 32];
  end

  // ======================================================================
  // r131: vector.PERF[9] @ 64'h00000001500010a4 (32-bit)
  // ======================================================================
  logic [31:0] r131_wdata, r131_wmask, r131_rdata;
  logic             r131_wr, r131_rd;
  assign r131_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r131_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r131_wr    = wr_commit && reg_sel[131];
  assign r131_rd    = rd_commit && reg_sel[131];
  // field VALUE [31:0] ro/input
  logic [31:0] r131_value_wb, r131_value_wm;
  assign r131_value_wb = r131_wdata[0 +: 32];
  assign r131_value_wm = r131_wmask[0 +: 32];
  always_comb begin
    r131_rdata = 32'h0;
    r131_rdata[0 +: 32] = vector_perf_value_i[288 +: 32];
  end

  // ======================================================================
  // r132: vector.PERF[10] @ 64'h00000001500010a8 (32-bit)
  // ======================================================================
  logic [31:0] r132_wdata, r132_wmask, r132_rdata;
  logic             r132_wr, r132_rd;
  assign r132_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r132_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r132_wr    = wr_commit && reg_sel[132];
  assign r132_rd    = rd_commit && reg_sel[132];
  // field VALUE [31:0] ro/input
  logic [31:0] r132_value_wb, r132_value_wm;
  assign r132_value_wb = r132_wdata[0 +: 32];
  assign r132_value_wm = r132_wmask[0 +: 32];
  always_comb begin
    r132_rdata = 32'h0;
    r132_rdata[0 +: 32] = vector_perf_value_i[320 +: 32];
  end

  // ======================================================================
  // r133: vector.PERF[11] @ 64'h00000001500010ac (32-bit)
  // ======================================================================
  logic [31:0] r133_wdata, r133_wmask, r133_rdata;
  logic             r133_wr, r133_rd;
  assign r133_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r133_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r133_wr    = wr_commit && reg_sel[133];
  assign r133_rd    = rd_commit && reg_sel[133];
  // field VALUE [31:0] ro/input
  logic [31:0] r133_value_wb, r133_value_wm;
  assign r133_value_wb = r133_wdata[0 +: 32];
  assign r133_value_wm = r133_wmask[0 +: 32];
  always_comb begin
    r133_rdata = 32'h0;
    r133_rdata[0 +: 32] = vector_perf_value_i[352 +: 32];
  end

  // ======================================================================
  // r134: vector.PERF[12] @ 64'h00000001500010b0 (32-bit)
  // ======================================================================
  logic [31:0] r134_wdata, r134_wmask, r134_rdata;
  logic             r134_wr, r134_rd;
  assign r134_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r134_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r134_wr    = wr_commit && reg_sel[134];
  assign r134_rd    = rd_commit && reg_sel[134];
  // field VALUE [31:0] ro/input
  logic [31:0] r134_value_wb, r134_value_wm;
  assign r134_value_wb = r134_wdata[0 +: 32];
  assign r134_value_wm = r134_wmask[0 +: 32];
  always_comb begin
    r134_rdata = 32'h0;
    r134_rdata[0 +: 32] = vector_perf_value_i[384 +: 32];
  end

  // ======================================================================
  // r135: vector.PERF[13] @ 64'h00000001500010b4 (32-bit)
  // ======================================================================
  logic [31:0] r135_wdata, r135_wmask, r135_rdata;
  logic             r135_wr, r135_rd;
  assign r135_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r135_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r135_wr    = wr_commit && reg_sel[135];
  assign r135_rd    = rd_commit && reg_sel[135];
  // field VALUE [31:0] ro/input
  logic [31:0] r135_value_wb, r135_value_wm;
  assign r135_value_wb = r135_wdata[0 +: 32];
  assign r135_value_wm = r135_wmask[0 +: 32];
  always_comb begin
    r135_rdata = 32'h0;
    r135_rdata[0 +: 32] = vector_perf_value_i[416 +: 32];
  end

  // ======================================================================
  // r136: vector.PERF[14] @ 64'h00000001500010b8 (32-bit)
  // ======================================================================
  logic [31:0] r136_wdata, r136_wmask, r136_rdata;
  logic             r136_wr, r136_rd;
  assign r136_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r136_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r136_wr    = wr_commit && reg_sel[136];
  assign r136_rd    = rd_commit && reg_sel[136];
  // field VALUE [31:0] ro/input
  logic [31:0] r136_value_wb, r136_value_wm;
  assign r136_value_wb = r136_wdata[0 +: 32];
  assign r136_value_wm = r136_wmask[0 +: 32];
  always_comb begin
    r136_rdata = 32'h0;
    r136_rdata[0 +: 32] = vector_perf_value_i[448 +: 32];
  end

  // ======================================================================
  // r137: vector.PERF[15] @ 64'h00000001500010bc (32-bit)
  // ======================================================================
  logic [31:0] r137_wdata, r137_wmask, r137_rdata;
  logic             r137_wr, r137_rd;
  assign r137_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r137_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r137_wr    = wr_commit && reg_sel[137];
  assign r137_rd    = rd_commit && reg_sel[137];
  // field VALUE [31:0] ro/input
  logic [31:0] r137_value_wb, r137_value_wm;
  assign r137_value_wb = r137_wdata[0 +: 32];
  assign r137_value_wm = r137_wmask[0 +: 32];
  always_comb begin
    r137_rdata = 32'h0;
    r137_rdata[0 +: 32] = vector_perf_value_i[480 +: 32];
  end

  // ======================================================================
  // r138: vector.PERF[16] @ 64'h00000001500010c0 (32-bit)
  // ======================================================================
  logic [31:0] r138_wdata, r138_wmask, r138_rdata;
  logic             r138_wr, r138_rd;
  assign r138_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r138_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r138_wr    = wr_commit && reg_sel[138];
  assign r138_rd    = rd_commit && reg_sel[138];
  // field VALUE [31:0] ro/input
  logic [31:0] r138_value_wb, r138_value_wm;
  assign r138_value_wb = r138_wdata[0 +: 32];
  assign r138_value_wm = r138_wmask[0 +: 32];
  always_comb begin
    r138_rdata = 32'h0;
    r138_rdata[0 +: 32] = vector_perf_value_i[512 +: 32];
  end

  // ======================================================================
  // r139: perf.CTRL @ 64'h0000000170000000 (32-bit)
  // ======================================================================
  logic [31:0] r139_wdata, r139_wmask, r139_rdata;
  logic             r139_wr, r139_rd;
  assign r139_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r139_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r139_wr    = wr_commit && reg_sel[139];
  assign r139_rd    = rd_commit && reg_sel[139];
  // field FREEZE [0:0] rw/none
  logic [0:0] r139_freeze_wb, r139_freeze_wm;
  assign r139_freeze_wb = r139_wdata[0 +: 1];
  assign r139_freeze_wm = r139_wmask[0 +: 1];
  logic [0:0] r139_freeze_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r139_freeze_q <= 1'h0;
    else if (r139_wr && (|r139_freeze_wm)) r139_freeze_q <= ((r139_freeze_q & ~r139_freeze_wm) | (r139_freeze_wb & r139_freeze_wm));
  end
  assign perf_ctrl_freeze_o[0 +: 1] = r139_freeze_q;
  // field SNAPSHOT [1:1] w1p
  logic [0:0] r139_snapshot_wb, r139_snapshot_wm;
  assign r139_snapshot_wb = r139_wdata[1 +: 1];
  assign r139_snapshot_wm = r139_wmask[1 +: 1];
  logic [0:0] r139_snapshot_pulse_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r139_snapshot_pulse_q <= 1'h0;
    else r139_snapshot_pulse_q <= {1{r139_wr}} & r139_snapshot_wb & r139_snapshot_wm;
  end
  assign perf_ctrl_snapshot_pulse_o[0 +: 1] = r139_snapshot_pulse_q;
  always_comb begin
    r139_rdata = 32'h0;
    r139_rdata[0 +: 1] = r139_freeze_q;
  end

  // ======================================================================
  // r140: perf.STATUS @ 64'h0000000170000004 (32-bit)
  // ======================================================================
  logic [31:0] r140_wdata, r140_wmask, r140_rdata;
  logic             r140_wr, r140_rd;
  assign r140_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r140_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r140_wr    = wr_commit && reg_sel[140];
  assign r140_rd    = rd_commit && reg_sel[140];
  // field FROZEN [0:0] ro/input
  logic [0:0] r140_frozen_wb, r140_frozen_wm;
  assign r140_frozen_wb = r140_wdata[0 +: 1];
  assign r140_frozen_wm = r140_wmask[0 +: 1];
  // field IRQ [1:1] ro/input
  logic [0:0] r140_irq_wb, r140_irq_wm;
  assign r140_irq_wb = r140_wdata[1 +: 1];
  assign r140_irq_wm = r140_wmask[1 +: 1];
  always_comb begin
    r140_rdata = 32'h0;
    r140_rdata[0 +: 1] = perf_status_frozen_i[0 +: 1];
    r140_rdata[1 +: 1] = perf_status_irq_i[0 +: 1];
  end

  // ======================================================================
  // r141: perf.CNT[0] @ 64'h0000000170000100 (64-bit)
  // ======================================================================
  logic [63:0] r141_wdata, r141_wmask, r141_rdata;
  logic             r141_wr, r141_rd;
  assign r141_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 64];
  assign r141_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}, {8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r141_wr    = wr_commit && reg_sel[141];
  assign r141_rd    = rd_commit && reg_sel[141];
  // field VALUE [63:0] ro/input
  logic [63:0] r141_value_wb, r141_value_wm;
  assign r141_value_wb = r141_wdata[0 +: 64];
  assign r141_value_wm = r141_wmask[0 +: 64];
  always_comb begin
    r141_rdata = 64'h0;
    r141_rdata[0 +: 64] = perf_cnt_value_i[0 +: 64];
  end

  // ======================================================================
  // r142: perf.CNT[1] @ 64'h0000000170000108 (64-bit)
  // ======================================================================
  logic [63:0] r142_wdata, r142_wmask, r142_rdata;
  logic             r142_wr, r142_rd;
  assign r142_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 64];
  assign r142_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}, {8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r142_wr    = wr_commit && reg_sel[142];
  assign r142_rd    = rd_commit && reg_sel[142];
  // field VALUE [63:0] ro/input
  logic [63:0] r142_value_wb, r142_value_wm;
  assign r142_value_wb = r142_wdata[0 +: 64];
  assign r142_value_wm = r142_wmask[0 +: 64];
  always_comb begin
    r142_rdata = 64'h0;
    r142_rdata[0 +: 64] = perf_cnt_value_i[64 +: 64];
  end

  // ======================================================================
  // r143: perf.CNT[2] @ 64'h0000000170000110 (64-bit)
  // ======================================================================
  logic [63:0] r143_wdata, r143_wmask, r143_rdata;
  logic             r143_wr, r143_rd;
  assign r143_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 64];
  assign r143_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}, {8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r143_wr    = wr_commit && reg_sel[143];
  assign r143_rd    = rd_commit && reg_sel[143];
  // field VALUE [63:0] ro/input
  logic [63:0] r143_value_wb, r143_value_wm;
  assign r143_value_wb = r143_wdata[0 +: 64];
  assign r143_value_wm = r143_wmask[0 +: 64];
  always_comb begin
    r143_rdata = 64'h0;
    r143_rdata[0 +: 64] = perf_cnt_value_i[128 +: 64];
  end

  // ======================================================================
  // r144: perf.CNT[3] @ 64'h0000000170000118 (64-bit)
  // ======================================================================
  logic [63:0] r144_wdata, r144_wmask, r144_rdata;
  logic             r144_wr, r144_rd;
  assign r144_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 64];
  assign r144_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}, {8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r144_wr    = wr_commit && reg_sel[144];
  assign r144_rd    = rd_commit && reg_sel[144];
  // field VALUE [63:0] ro/input
  logic [63:0] r144_value_wb, r144_value_wm;
  assign r144_value_wb = r144_wdata[0 +: 64];
  assign r144_value_wm = r144_wmask[0 +: 64];
  always_comb begin
    r144_rdata = 64'h0;
    r144_rdata[0 +: 64] = perf_cnt_value_i[192 +: 64];
  end

  // ======================================================================
  // r145: perf.CNT[4] @ 64'h0000000170000120 (64-bit)
  // ======================================================================
  logic [63:0] r145_wdata, r145_wmask, r145_rdata;
  logic             r145_wr, r145_rd;
  assign r145_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 64];
  assign r145_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}, {8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r145_wr    = wr_commit && reg_sel[145];
  assign r145_rd    = rd_commit && reg_sel[145];
  // field VALUE [63:0] ro/input
  logic [63:0] r145_value_wb, r145_value_wm;
  assign r145_value_wb = r145_wdata[0 +: 64];
  assign r145_value_wm = r145_wmask[0 +: 64];
  always_comb begin
    r145_rdata = 64'h0;
    r145_rdata[0 +: 64] = perf_cnt_value_i[256 +: 64];
  end

  // ======================================================================
  // r146: perf.CNT[5] @ 64'h0000000170000128 (64-bit)
  // ======================================================================
  logic [63:0] r146_wdata, r146_wmask, r146_rdata;
  logic             r146_wr, r146_rd;
  assign r146_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 64];
  assign r146_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}, {8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r146_wr    = wr_commit && reg_sel[146];
  assign r146_rd    = rd_commit && reg_sel[146];
  // field VALUE [63:0] ro/input
  logic [63:0] r146_value_wb, r146_value_wm;
  assign r146_value_wb = r146_wdata[0 +: 64];
  assign r146_value_wm = r146_wmask[0 +: 64];
  always_comb begin
    r146_rdata = 64'h0;
    r146_rdata[0 +: 64] = perf_cnt_value_i[320 +: 64];
  end

  // ======================================================================
  // r147: perf.CNT[6] @ 64'h0000000170000130 (64-bit)
  // ======================================================================
  logic [63:0] r147_wdata, r147_wmask, r147_rdata;
  logic             r147_wr, r147_rd;
  assign r147_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 64];
  assign r147_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}, {8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r147_wr    = wr_commit && reg_sel[147];
  assign r147_rd    = rd_commit && reg_sel[147];
  // field VALUE [63:0] ro/input
  logic [63:0] r147_value_wb, r147_value_wm;
  assign r147_value_wb = r147_wdata[0 +: 64];
  assign r147_value_wm = r147_wmask[0 +: 64];
  always_comb begin
    r147_rdata = 64'h0;
    r147_rdata[0 +: 64] = perf_cnt_value_i[384 +: 64];
  end

  // ======================================================================
  // r148: perf.CNT[7] @ 64'h0000000170000138 (64-bit)
  // ======================================================================
  logic [63:0] r148_wdata, r148_wmask, r148_rdata;
  logic             r148_wr, r148_rd;
  assign r148_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 64];
  assign r148_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}, {8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r148_wr    = wr_commit && reg_sel[148];
  assign r148_rd    = rd_commit && reg_sel[148];
  // field VALUE [63:0] ro/input
  logic [63:0] r148_value_wb, r148_value_wm;
  assign r148_value_wb = r148_wdata[0 +: 64];
  assign r148_value_wm = r148_wmask[0 +: 64];
  always_comb begin
    r148_rdata = 64'h0;
    r148_rdata[0 +: 64] = perf_cnt_value_i[448 +: 64];
  end

  // ======================================================================
  // r149: perf.CNT[8] @ 64'h0000000170000140 (64-bit)
  // ======================================================================
  logic [63:0] r149_wdata, r149_wmask, r149_rdata;
  logic             r149_wr, r149_rd;
  assign r149_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 64];
  assign r149_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}, {8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r149_wr    = wr_commit && reg_sel[149];
  assign r149_rd    = rd_commit && reg_sel[149];
  // field VALUE [63:0] ro/input
  logic [63:0] r149_value_wb, r149_value_wm;
  assign r149_value_wb = r149_wdata[0 +: 64];
  assign r149_value_wm = r149_wmask[0 +: 64];
  always_comb begin
    r149_rdata = 64'h0;
    r149_rdata[0 +: 64] = perf_cnt_value_i[512 +: 64];
  end

  // ======================================================================
  // r150: perf.CNT[9] @ 64'h0000000170000148 (64-bit)
  // ======================================================================
  logic [63:0] r150_wdata, r150_wmask, r150_rdata;
  logic             r150_wr, r150_rd;
  assign r150_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 64];
  assign r150_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}, {8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r150_wr    = wr_commit && reg_sel[150];
  assign r150_rd    = rd_commit && reg_sel[150];
  // field VALUE [63:0] ro/input
  logic [63:0] r150_value_wb, r150_value_wm;
  assign r150_value_wb = r150_wdata[0 +: 64];
  assign r150_value_wm = r150_wmask[0 +: 64];
  always_comb begin
    r150_rdata = 64'h0;
    r150_rdata[0 +: 64] = perf_cnt_value_i[576 +: 64];
  end

  // ======================================================================
  // r151: perf.CNT[10] @ 64'h0000000170000150 (64-bit)
  // ======================================================================
  logic [63:0] r151_wdata, r151_wmask, r151_rdata;
  logic             r151_wr, r151_rd;
  assign r151_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 64];
  assign r151_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}, {8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r151_wr    = wr_commit && reg_sel[151];
  assign r151_rd    = rd_commit && reg_sel[151];
  // field VALUE [63:0] ro/input
  logic [63:0] r151_value_wb, r151_value_wm;
  assign r151_value_wb = r151_wdata[0 +: 64];
  assign r151_value_wm = r151_wmask[0 +: 64];
  always_comb begin
    r151_rdata = 64'h0;
    r151_rdata[0 +: 64] = perf_cnt_value_i[640 +: 64];
  end

  // ======================================================================
  // r152: perf.CNT[11] @ 64'h0000000170000158 (64-bit)
  // ======================================================================
  logic [63:0] r152_wdata, r152_wmask, r152_rdata;
  logic             r152_wr, r152_rd;
  assign r152_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 64];
  assign r152_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}, {8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r152_wr    = wr_commit && reg_sel[152];
  assign r152_rd    = rd_commit && reg_sel[152];
  // field VALUE [63:0] ro/input
  logic [63:0] r152_value_wb, r152_value_wm;
  assign r152_value_wb = r152_wdata[0 +: 64];
  assign r152_value_wm = r152_wmask[0 +: 64];
  always_comb begin
    r152_rdata = 64'h0;
    r152_rdata[0 +: 64] = perf_cnt_value_i[704 +: 64];
  end

  // ======================================================================
  // r153: perf.CNT[12] @ 64'h0000000170000160 (64-bit)
  // ======================================================================
  logic [63:0] r153_wdata, r153_wmask, r153_rdata;
  logic             r153_wr, r153_rd;
  assign r153_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 64];
  assign r153_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}, {8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r153_wr    = wr_commit && reg_sel[153];
  assign r153_rd    = rd_commit && reg_sel[153];
  // field VALUE [63:0] ro/input
  logic [63:0] r153_value_wb, r153_value_wm;
  assign r153_value_wb = r153_wdata[0 +: 64];
  assign r153_value_wm = r153_wmask[0 +: 64];
  always_comb begin
    r153_rdata = 64'h0;
    r153_rdata[0 +: 64] = perf_cnt_value_i[768 +: 64];
  end

  // ======================================================================
  // r154: perf.CNT[13] @ 64'h0000000170000168 (64-bit)
  // ======================================================================
  logic [63:0] r154_wdata, r154_wmask, r154_rdata;
  logic             r154_wr, r154_rd;
  assign r154_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 64];
  assign r154_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}, {8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r154_wr    = wr_commit && reg_sel[154];
  assign r154_rd    = rd_commit && reg_sel[154];
  // field VALUE [63:0] ro/input
  logic [63:0] r154_value_wb, r154_value_wm;
  assign r154_value_wb = r154_wdata[0 +: 64];
  assign r154_value_wm = r154_wmask[0 +: 64];
  always_comb begin
    r154_rdata = 64'h0;
    r154_rdata[0 +: 64] = perf_cnt_value_i[832 +: 64];
  end

  // ======================================================================
  // r155: perf.CNT[14] @ 64'h0000000170000170 (64-bit)
  // ======================================================================
  logic [63:0] r155_wdata, r155_wmask, r155_rdata;
  logic             r155_wr, r155_rd;
  assign r155_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 64];
  assign r155_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}, {8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r155_wr    = wr_commit && reg_sel[155];
  assign r155_rd    = rd_commit && reg_sel[155];
  // field VALUE [63:0] ro/input
  logic [63:0] r155_value_wb, r155_value_wm;
  assign r155_value_wb = r155_wdata[0 +: 64];
  assign r155_value_wm = r155_wmask[0 +: 64];
  always_comb begin
    r155_rdata = 64'h0;
    r155_rdata[0 +: 64] = perf_cnt_value_i[896 +: 64];
  end

  // ======================================================================
  // r156: perf.CNT[15] @ 64'h0000000170000178 (64-bit)
  // ======================================================================
  logic [63:0] r156_wdata, r156_wmask, r156_rdata;
  logic             r156_wr, r156_rd;
  assign r156_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 64];
  assign r156_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}, {8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r156_wr    = wr_commit && reg_sel[156];
  assign r156_rd    = rd_commit && reg_sel[156];
  // field VALUE [63:0] ro/input
  logic [63:0] r156_value_wb, r156_value_wm;
  assign r156_value_wb = r156_wdata[0 +: 64];
  assign r156_value_wm = r156_wmask[0 +: 64];
  always_comb begin
    r156_rdata = 64'h0;
    r156_rdata[0 +: 64] = perf_cnt_value_i[960 +: 64];
  end

  // ======================================================================
  // r157: perf.CNT[16] @ 64'h0000000170000180 (64-bit)
  // ======================================================================
  logic [63:0] r157_wdata, r157_wmask, r157_rdata;
  logic             r157_wr, r157_rd;
  assign r157_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 64];
  assign r157_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}, {8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r157_wr    = wr_commit && reg_sel[157];
  assign r157_rd    = rd_commit && reg_sel[157];
  // field VALUE [63:0] ro/input
  logic [63:0] r157_value_wb, r157_value_wm;
  assign r157_value_wb = r157_wdata[0 +: 64];
  assign r157_value_wm = r157_wmask[0 +: 64];
  always_comb begin
    r157_rdata = 64'h0;
    r157_rdata[0 +: 64] = perf_cnt_value_i[1024 +: 64];
  end

  // ======================================================================
  // r158: perf.CNT[17] @ 64'h0000000170000188 (64-bit)
  // ======================================================================
  logic [63:0] r158_wdata, r158_wmask, r158_rdata;
  logic             r158_wr, r158_rd;
  assign r158_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 64];
  assign r158_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}, {8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r158_wr    = wr_commit && reg_sel[158];
  assign r158_rd    = rd_commit && reg_sel[158];
  // field VALUE [63:0] ro/input
  logic [63:0] r158_value_wb, r158_value_wm;
  assign r158_value_wb = r158_wdata[0 +: 64];
  assign r158_value_wm = r158_wmask[0 +: 64];
  always_comb begin
    r158_rdata = 64'h0;
    r158_rdata[0 +: 64] = perf_cnt_value_i[1088 +: 64];
  end

  // ======================================================================
  // r159: perf.CNT[18] @ 64'h0000000170000190 (64-bit)
  // ======================================================================
  logic [63:0] r159_wdata, r159_wmask, r159_rdata;
  logic             r159_wr, r159_rd;
  assign r159_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 64];
  assign r159_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}, {8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r159_wr    = wr_commit && reg_sel[159];
  assign r159_rd    = rd_commit && reg_sel[159];
  // field VALUE [63:0] ro/input
  logic [63:0] r159_value_wb, r159_value_wm;
  assign r159_value_wb = r159_wdata[0 +: 64];
  assign r159_value_wm = r159_wmask[0 +: 64];
  always_comb begin
    r159_rdata = 64'h0;
    r159_rdata[0 +: 64] = perf_cnt_value_i[1152 +: 64];
  end

  // ======================================================================
  // r160: perf.CNT[19] @ 64'h0000000170000198 (64-bit)
  // ======================================================================
  logic [63:0] r160_wdata, r160_wmask, r160_rdata;
  logic             r160_wr, r160_rd;
  assign r160_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 64];
  assign r160_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}, {8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r160_wr    = wr_commit && reg_sel[160];
  assign r160_rd    = rd_commit && reg_sel[160];
  // field VALUE [63:0] ro/input
  logic [63:0] r160_value_wb, r160_value_wm;
  assign r160_value_wb = r160_wdata[0 +: 64];
  assign r160_value_wm = r160_wmask[0 +: 64];
  always_comb begin
    r160_rdata = 64'h0;
    r160_rdata[0 +: 64] = perf_cnt_value_i[1216 +: 64];
  end

  // ======================================================================
  // r161: perf.CNT[20] @ 64'h00000001700001a0 (64-bit)
  // ======================================================================
  logic [63:0] r161_wdata, r161_wmask, r161_rdata;
  logic             r161_wr, r161_rd;
  assign r161_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 64];
  assign r161_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}, {8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r161_wr    = wr_commit && reg_sel[161];
  assign r161_rd    = rd_commit && reg_sel[161];
  // field VALUE [63:0] ro/input
  logic [63:0] r161_value_wb, r161_value_wm;
  assign r161_value_wb = r161_wdata[0 +: 64];
  assign r161_value_wm = r161_wmask[0 +: 64];
  always_comb begin
    r161_rdata = 64'h0;
    r161_rdata[0 +: 64] = perf_cnt_value_i[1280 +: 64];
  end

  // ======================================================================
  // r162: perf.CNT[21] @ 64'h00000001700001a8 (64-bit)
  // ======================================================================
  logic [63:0] r162_wdata, r162_wmask, r162_rdata;
  logic             r162_wr, r162_rd;
  assign r162_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 64];
  assign r162_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}, {8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r162_wr    = wr_commit && reg_sel[162];
  assign r162_rd    = rd_commit && reg_sel[162];
  // field VALUE [63:0] ro/input
  logic [63:0] r162_value_wb, r162_value_wm;
  assign r162_value_wb = r162_wdata[0 +: 64];
  assign r162_value_wm = r162_wmask[0 +: 64];
  always_comb begin
    r162_rdata = 64'h0;
    r162_rdata[0 +: 64] = perf_cnt_value_i[1344 +: 64];
  end

  // ======================================================================
  // r163: perf.CNT[22] @ 64'h00000001700001b0 (64-bit)
  // ======================================================================
  logic [63:0] r163_wdata, r163_wmask, r163_rdata;
  logic             r163_wr, r163_rd;
  assign r163_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 64];
  assign r163_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}, {8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r163_wr    = wr_commit && reg_sel[163];
  assign r163_rd    = rd_commit && reg_sel[163];
  // field VALUE [63:0] ro/input
  logic [63:0] r163_value_wb, r163_value_wm;
  assign r163_value_wb = r163_wdata[0 +: 64];
  assign r163_value_wm = r163_wmask[0 +: 64];
  always_comb begin
    r163_rdata = 64'h0;
    r163_rdata[0 +: 64] = perf_cnt_value_i[1408 +: 64];
  end

  // ======================================================================
  // r164: sysid.ID @ 64'h0000000180000000 (32-bit)
  // ======================================================================
  logic [31:0] r164_wdata, r164_wmask, r164_rdata;
  logic             r164_wr, r164_rd;
  assign r164_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r164_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r164_wr    = wr_commit && reg_sel[164];
  assign r164_rd    = rd_commit && reg_sel[164];
  // field VALUE [31:0] ro/const
  logic [31:0] r164_value_wb, r164_value_wm;
  assign r164_value_wb = r164_wdata[0 +: 32];
  assign r164_value_wm = r164_wmask[0 +: 32];
  always_comb begin
    r164_rdata = 32'h0;
    r164_rdata[0 +: 32] = 32'h53464c58;
  end

  // ======================================================================
  // r165: sysid.REGMAP_VERSION @ 64'h0000000180000004 (32-bit)
  // ======================================================================
  logic [31:0] r165_wdata, r165_wmask, r165_rdata;
  logic             r165_wr, r165_rd;
  assign r165_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r165_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r165_wr    = wr_commit && reg_sel[165];
  assign r165_rd    = rd_commit && reg_sel[165];
  // field MINOR [15:0] ro/const
  logic [15:0] r165_minor_wb, r165_minor_wm;
  assign r165_minor_wb = r165_wdata[0 +: 16];
  assign r165_minor_wm = r165_wmask[0 +: 16];
  // field MAJOR [31:16] ro/const
  logic [15:0] r165_major_wb, r165_major_wm;
  assign r165_major_wb = r165_wdata[16 +: 16];
  assign r165_major_wm = r165_wmask[16 +: 16];
  always_comb begin
    r165_rdata = 32'h0;
    r165_rdata[0 +: 16] = 16'h0000;
    r165_rdata[16 +: 16] = 16'h0001;
  end

  // ======================================================================
  // r166: sysid.ALP_VERSION @ 64'h0000000180000008 (32-bit)
  // ======================================================================
  logic [31:0] r166_wdata, r166_wmask, r166_rdata;
  logic             r166_wr, r166_rd;
  assign r166_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r166_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r166_wr    = wr_commit && reg_sel[166];
  assign r166_rd    = rd_commit && reg_sel[166];
  // field MAJOR [7:0] ro/const
  logic [7:0] r166_major_wb, r166_major_wm;
  assign r166_major_wb = r166_wdata[0 +: 8];
  assign r166_major_wm = r166_wmask[0 +: 8];
  // field MINOR [15:8] ro/const
  logic [7:0] r166_minor_wb, r166_minor_wm;
  assign r166_minor_wb = r166_wdata[8 +: 8];
  assign r166_minor_wm = r166_wmask[8 +: 8];
  always_comb begin
    r166_rdata = 32'h0;
    r166_rdata[0 +: 8] = 8'h01;
    r166_rdata[8 +: 8] = 8'h00;
  end

  // ======================================================================
  // r167: sysid.LIB_VERSION @ 64'h000000018000000c (32-bit)
  // ======================================================================
  logic [31:0] r167_wdata, r167_wmask, r167_rdata;
  logic             r167_wr, r167_rd;
  assign r167_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r167_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r167_wr    = wr_commit && reg_sel[167];
  assign r167_rd    = rd_commit && reg_sel[167];
  // field MAJOR [7:0] ro/const
  logic [7:0] r167_major_wb, r167_major_wm;
  assign r167_major_wb = r167_wdata[0 +: 8];
  assign r167_major_wm = r167_wmask[0 +: 8];
  // field MINOR [15:8] ro/const
  logic [7:0] r167_minor_wb, r167_minor_wm;
  assign r167_minor_wb = r167_wdata[8 +: 8];
  assign r167_minor_wm = r167_wmask[8 +: 8];
  // field PATCH [23:16] ro/const
  logic [7:0] r167_patch_wb, r167_patch_wm;
  assign r167_patch_wb = r167_wdata[16 +: 8];
  assign r167_patch_wm = r167_wmask[16 +: 8];
  always_comb begin
    r167_rdata = 32'h0;
    r167_rdata[0 +: 8] = 8'h00;
    r167_rdata[8 +: 8] = 8'h01;
    r167_rdata[16 +: 8] = 8'h00;
  end

  // ======================================================================
  // r168: sysid.ALP_CAPS @ 64'h0000000180000010 (64-bit)
  // ======================================================================
  logic [63:0] r168_wdata, r168_wmask, r168_rdata;
  logic             r168_wr, r168_rd;
  assign r168_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 64];
  assign r168_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}, {8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r168_wr    = wr_commit && reg_sel[168];
  assign r168_rd    = rd_commit && reg_sel[168];
  // field FEATURES [15:0] ro/const
  logic [15:0] r168_features_wb, r168_features_wm;
  assign r168_features_wb = r168_wdata[0 +: 16];
  assign r168_features_wm = r168_wmask[0 +: 16];
  // field MAX_OUTSTANDING [31:16] ro/const
  logic [15:0] r168_max_outstanding_wb, r168_max_outstanding_wm;
  assign r168_max_outstanding_wb = r168_wdata[16 +: 16];
  assign r168_max_outstanding_wm = r168_wmask[16 +: 16];
  // field RSVD [35:32] ro/const
  logic [3:0] r168_rsvd_wb, r168_rsvd_wm;
  assign r168_rsvd_wb = r168_wdata[32 +: 4];
  assign r168_rsvd_wm = r168_wmask[32 +: 4];
  // field DOM_W [39:36] ro/const
  logic [3:0] r168_dom_w_wb, r168_dom_w_wm;
  assign r168_dom_w_wb = r168_wdata[36 +: 4];
  assign r168_dom_w_wm = r168_wmask[36 +: 4];
  // field TAG_W [43:40] ro/const
  logic [3:0] r168_tag_w_wb, r168_tag_w_wm;
  assign r168_tag_w_wb = r168_wdata[40 +: 4];
  assign r168_tag_w_wm = r168_wmask[40 +: 4];
  // field DATA_BYTES_LOG2 [47:44] ro/const
  logic [3:0] r168_data_bytes_log2_wb, r168_data_bytes_log2_wm;
  assign r168_data_bytes_log2_wb = r168_wdata[44 +: 4];
  assign r168_data_bytes_log2_wm = r168_wmask[44 +: 4];
  // field ADDR_W [55:48] ro/const
  logic [7:0] r168_addr_w_wb, r168_addr_w_wm;
  assign r168_addr_w_wb = r168_wdata[48 +: 8];
  assign r168_addr_w_wm = r168_wmask[48 +: 8];
  // field PROTO_MINOR [59:56] ro/const
  logic [3:0] r168_proto_minor_wb, r168_proto_minor_wm;
  assign r168_proto_minor_wb = r168_wdata[56 +: 4];
  assign r168_proto_minor_wm = r168_wmask[56 +: 4];
  // field PROTO_MAJOR [63:60] ro/const
  logic [3:0] r168_proto_major_wb, r168_proto_major_wm;
  assign r168_proto_major_wb = r168_wdata[60 +: 4];
  assign r168_proto_major_wm = r168_wmask[60 +: 4];
  always_comb begin
    r168_rdata = 64'h0;
    r168_rdata[0 +: 16] = 16'h0003;
    r168_rdata[16 +: 16] = 16'h0002;
    r168_rdata[32 +: 4] = 4'h0;
    r168_rdata[36 +: 4] = 4'h8;
    r168_rdata[40 +: 4] = 4'h8;
    r168_rdata[44 +: 4] = 4'h4;
    r168_rdata[48 +: 8] = 8'h40;
    r168_rdata[56 +: 4] = 4'h0;
    r168_rdata[60 +: 4] = 4'h1;
  end

  // ======================================================================
  // r169: sysid.REGMAP_HASH @ 64'h0000000180000018 (64-bit)
  // ======================================================================
  logic [63:0] r169_wdata, r169_wmask, r169_rdata;
  logic             r169_wr, r169_rd;
  assign r169_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 64];
  assign r169_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}, {8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r169_wr    = wr_commit && reg_sel[169];
  assign r169_rd    = rd_commit && reg_sel[169];
  // field VALUE [63:0] ro/const
  logic [63:0] r169_value_wb, r169_value_wm;
  assign r169_value_wb = r169_wdata[0 +: 64];
  assign r169_value_wm = r169_wmask[0 +: 64];
  always_comb begin
    r169_rdata = 64'h0;
    r169_rdata[0 +: 64] = 64'h99481283139d2dc0;
  end

  // ======================================================================
  // r170: sysid.BUILD_ID @ 64'h0000000180000020 (32-bit)
  // ======================================================================
  logic [31:0] r170_wdata, r170_wmask, r170_rdata;
  logic             r170_wr, r170_rd;
  assign r170_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r170_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r170_wr    = wr_commit && reg_sel[170];
  assign r170_rd    = rd_commit && reg_sel[170];
  // field VALUE [31:0] ro/input
  logic [31:0] r170_value_wb, r170_value_wm;
  assign r170_value_wb = r170_wdata[0 +: 32];
  assign r170_value_wm = r170_wmask[0 +: 32];
  always_comb begin
    r170_rdata = 32'h0;
    r170_rdata[0 +: 32] = sysid_build_id_value_i[0 +: 32];
  end

  // ======================================================================
  // r171: intc.PENDING @ 64'h0000000180001000 (32-bit)
  // ======================================================================
  logic [31:0] r171_wdata, r171_wmask, r171_rdata;
  logic             r171_wr, r171_rd;
  assign r171_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r171_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r171_wr    = wr_commit && reg_sel[171];
  assign r171_rd    = rd_commit && reg_sel[171];
  // field SOURCES [15:0] ro/input
  logic [15:0] r171_sources_wb, r171_sources_wm;
  assign r171_sources_wb = r171_wdata[0 +: 16];
  assign r171_sources_wm = r171_wmask[0 +: 16];
  always_comb begin
    r171_rdata = 32'h0;
    r171_rdata[0 +: 16] = intc_pending_sources_i[0 +: 16];
  end

  // ======================================================================
  // r172: intc.ENABLE @ 64'h0000000180001004 (32-bit)
  // ======================================================================
  logic [31:0] r172_wdata, r172_wmask, r172_rdata;
  logic             r172_wr, r172_rd;
  assign r172_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r172_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r172_wr    = wr_commit && reg_sel[172];
  assign r172_rd    = rd_commit && reg_sel[172];
  // field EN [15:0] rw/none
  logic [15:0] r172_en_wb, r172_en_wm;
  assign r172_en_wb = r172_wdata[0 +: 16];
  assign r172_en_wm = r172_wmask[0 +: 16];
  logic [15:0] r172_en_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r172_en_q <= 16'h0000;
    else if (r172_wr && (|r172_en_wm)) r172_en_q <= ((r172_en_q & ~r172_en_wm) | (r172_en_wb & r172_en_wm));
  end
  assign intc_enable_en_o[0 +: 16] = r172_en_q;
  always_comb begin
    r172_rdata = 32'h0;
    r172_rdata[0 +: 16] = r172_en_q;
  end

  // ======================================================================
  // r173: intc.CLAIM @ 64'h0000000180001008 (32-bit)
  // ======================================================================
  logic [31:0] r173_wdata, r173_wmask, r173_rdata;
  logic             r173_wr, r173_rd;
  assign r173_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r173_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r173_wr    = wr_commit && reg_sel[173];
  assign r173_rd    = rd_commit && reg_sel[173];
  // field ID [7:0] ro/input
  logic [7:0] r173_id_wb, r173_id_wm;
  assign r173_id_wb = r173_wdata[0 +: 8];
  assign r173_id_wm = r173_wmask[0 +: 8];
  always_comb begin
    r173_rdata = 32'h0;
    r173_rdata[0 +: 8] = intc_claim_id_i[0 +: 8];
  end

  // ======================================================================
  // r174: intc.SWPEND @ 64'h000000018000100c (32-bit)
  // ======================================================================
  logic [31:0] r174_wdata, r174_wmask, r174_rdata;
  logic             r174_wr, r174_rd;
  assign r174_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r174_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r174_wr    = wr_commit && reg_sel[174];
  assign r174_rd    = rd_commit && reg_sel[174];
  // field SW [15:0] rw/none
  logic [15:0] r174_sw_wb, r174_sw_wm;
  assign r174_sw_wb = r174_wdata[0 +: 16];
  assign r174_sw_wm = r174_wmask[0 +: 16];
  logic [15:0] r174_sw_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r174_sw_q <= 16'h0000;
    else if (r174_wr && (|r174_sw_wm)) r174_sw_q <= ((r174_sw_q & ~r174_sw_wm) | (r174_sw_wb & r174_sw_wm));
  end
  assign intc_swpend_sw_o[0 +: 16] = r174_sw_q;
  always_comb begin
    r174_rdata = 32'h0;
    r174_rdata[0 +: 16] = r174_sw_q;
  end

  // ======================================================================
  // r175: intc.THRESHOLD @ 64'h0000000180001010 (32-bit)
  // ======================================================================
  logic [31:0] r175_wdata, r175_wmask, r175_rdata;
  logic             r175_wr, r175_rd;
  assign r175_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r175_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r175_wr    = wr_commit && reg_sel[175];
  assign r175_rd    = rd_commit && reg_sel[175];
  // field LEVEL [2:0] rw/none
  logic [2:0] r175_level_wb, r175_level_wm;
  assign r175_level_wb = r175_wdata[0 +: 3];
  assign r175_level_wm = r175_wmask[0 +: 3];
  logic [2:0] r175_level_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r175_level_q <= 3'h0;
    else if (r175_wr && (|r175_level_wm)) r175_level_q <= ((r175_level_q & ~r175_level_wm) | (r175_level_wb & r175_level_wm));
  end
  assign intc_threshold_level_o[0 +: 3] = r175_level_q;
  always_comb begin
    r175_rdata = 32'h0;
    r175_rdata[0 +: 3] = r175_level_q;
  end

  // ======================================================================
  // r176: intc.ACTIVE @ 64'h0000000180001014 (32-bit)
  // ======================================================================
  logic [31:0] r176_wdata, r176_wmask, r176_rdata;
  logic             r176_wr, r176_rd;
  assign r176_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r176_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r176_wr    = wr_commit && reg_sel[176];
  assign r176_rd    = rd_commit && reg_sel[176];
  // field ACT [15:0] ro/input
  logic [15:0] r176_act_wb, r176_act_wm;
  assign r176_act_wb = r176_wdata[0 +: 16];
  assign r176_act_wm = r176_wmask[0 +: 16];
  always_comb begin
    r176_rdata = 32'h0;
    r176_rdata[0 +: 16] = intc_active_act_i[0 +: 16];
  end

  // ======================================================================
  // r177: intc.PRIO0 @ 64'h0000000180001020 (32-bit)
  // ======================================================================
  logic [31:0] r177_wdata, r177_wmask, r177_rdata;
  logic             r177_wr, r177_rd;
  assign r177_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r177_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r177_wr    = wr_commit && reg_sel[177];
  assign r177_rd    = rd_commit && reg_sel[177];
  // field SRC0 [2:0] rw/none
  logic [2:0] r177_src0_wb, r177_src0_wm;
  assign r177_src0_wb = r177_wdata[0 +: 3];
  assign r177_src0_wm = r177_wmask[0 +: 3];
  logic [2:0] r177_src0_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r177_src0_q <= 3'h1;
    else if (r177_wr && (|r177_src0_wm)) r177_src0_q <= ((r177_src0_q & ~r177_src0_wm) | (r177_src0_wb & r177_src0_wm));
  end
  assign intc_prio0_src0_o[0 +: 3] = r177_src0_q;
  // field SRC1 [6:4] rw/none
  logic [2:0] r177_src1_wb, r177_src1_wm;
  assign r177_src1_wb = r177_wdata[4 +: 3];
  assign r177_src1_wm = r177_wmask[4 +: 3];
  logic [2:0] r177_src1_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r177_src1_q <= 3'h1;
    else if (r177_wr && (|r177_src1_wm)) r177_src1_q <= ((r177_src1_q & ~r177_src1_wm) | (r177_src1_wb & r177_src1_wm));
  end
  assign intc_prio0_src1_o[0 +: 3] = r177_src1_q;
  // field SRC2 [10:8] rw/none
  logic [2:0] r177_src2_wb, r177_src2_wm;
  assign r177_src2_wb = r177_wdata[8 +: 3];
  assign r177_src2_wm = r177_wmask[8 +: 3];
  logic [2:0] r177_src2_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r177_src2_q <= 3'h1;
    else if (r177_wr && (|r177_src2_wm)) r177_src2_q <= ((r177_src2_q & ~r177_src2_wm) | (r177_src2_wb & r177_src2_wm));
  end
  assign intc_prio0_src2_o[0 +: 3] = r177_src2_q;
  // field SRC3 [14:12] rw/none
  logic [2:0] r177_src3_wb, r177_src3_wm;
  assign r177_src3_wb = r177_wdata[12 +: 3];
  assign r177_src3_wm = r177_wmask[12 +: 3];
  logic [2:0] r177_src3_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r177_src3_q <= 3'h1;
    else if (r177_wr && (|r177_src3_wm)) r177_src3_q <= ((r177_src3_q & ~r177_src3_wm) | (r177_src3_wb & r177_src3_wm));
  end
  assign intc_prio0_src3_o[0 +: 3] = r177_src3_q;
  // field SRC4 [18:16] rw/none
  logic [2:0] r177_src4_wb, r177_src4_wm;
  assign r177_src4_wb = r177_wdata[16 +: 3];
  assign r177_src4_wm = r177_wmask[16 +: 3];
  logic [2:0] r177_src4_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r177_src4_q <= 3'h1;
    else if (r177_wr && (|r177_src4_wm)) r177_src4_q <= ((r177_src4_q & ~r177_src4_wm) | (r177_src4_wb & r177_src4_wm));
  end
  assign intc_prio0_src4_o[0 +: 3] = r177_src4_q;
  // field SRC5 [22:20] rw/none
  logic [2:0] r177_src5_wb, r177_src5_wm;
  assign r177_src5_wb = r177_wdata[20 +: 3];
  assign r177_src5_wm = r177_wmask[20 +: 3];
  logic [2:0] r177_src5_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r177_src5_q <= 3'h1;
    else if (r177_wr && (|r177_src5_wm)) r177_src5_q <= ((r177_src5_q & ~r177_src5_wm) | (r177_src5_wb & r177_src5_wm));
  end
  assign intc_prio0_src5_o[0 +: 3] = r177_src5_q;
  // field SRC6 [26:24] rw/none
  logic [2:0] r177_src6_wb, r177_src6_wm;
  assign r177_src6_wb = r177_wdata[24 +: 3];
  assign r177_src6_wm = r177_wmask[24 +: 3];
  logic [2:0] r177_src6_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r177_src6_q <= 3'h1;
    else if (r177_wr && (|r177_src6_wm)) r177_src6_q <= ((r177_src6_q & ~r177_src6_wm) | (r177_src6_wb & r177_src6_wm));
  end
  assign intc_prio0_src6_o[0 +: 3] = r177_src6_q;
  // field SRC7 [30:28] rw/none
  logic [2:0] r177_src7_wb, r177_src7_wm;
  assign r177_src7_wb = r177_wdata[28 +: 3];
  assign r177_src7_wm = r177_wmask[28 +: 3];
  logic [2:0] r177_src7_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r177_src7_q <= 3'h1;
    else if (r177_wr && (|r177_src7_wm)) r177_src7_q <= ((r177_src7_q & ~r177_src7_wm) | (r177_src7_wb & r177_src7_wm));
  end
  assign intc_prio0_src7_o[0 +: 3] = r177_src7_q;
  always_comb begin
    r177_rdata = 32'h0;
    r177_rdata[0 +: 3] = r177_src0_q;
    r177_rdata[4 +: 3] = r177_src1_q;
    r177_rdata[8 +: 3] = r177_src2_q;
    r177_rdata[12 +: 3] = r177_src3_q;
    r177_rdata[16 +: 3] = r177_src4_q;
    r177_rdata[20 +: 3] = r177_src5_q;
    r177_rdata[24 +: 3] = r177_src6_q;
    r177_rdata[28 +: 3] = r177_src7_q;
  end

  // ======================================================================
  // r178: intc.PRIO1 @ 64'h0000000180001024 (32-bit)
  // ======================================================================
  logic [31:0] r178_wdata, r178_wmask, r178_rdata;
  logic             r178_wr, r178_rd;
  assign r178_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r178_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r178_wr    = wr_commit && reg_sel[178];
  assign r178_rd    = rd_commit && reg_sel[178];
  // field SRC8 [2:0] rw/none
  logic [2:0] r178_src8_wb, r178_src8_wm;
  assign r178_src8_wb = r178_wdata[0 +: 3];
  assign r178_src8_wm = r178_wmask[0 +: 3];
  logic [2:0] r178_src8_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r178_src8_q <= 3'h1;
    else if (r178_wr && (|r178_src8_wm)) r178_src8_q <= ((r178_src8_q & ~r178_src8_wm) | (r178_src8_wb & r178_src8_wm));
  end
  assign intc_prio1_src8_o[0 +: 3] = r178_src8_q;
  // field SRC9 [6:4] rw/none
  logic [2:0] r178_src9_wb, r178_src9_wm;
  assign r178_src9_wb = r178_wdata[4 +: 3];
  assign r178_src9_wm = r178_wmask[4 +: 3];
  logic [2:0] r178_src9_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r178_src9_q <= 3'h1;
    else if (r178_wr && (|r178_src9_wm)) r178_src9_q <= ((r178_src9_q & ~r178_src9_wm) | (r178_src9_wb & r178_src9_wm));
  end
  assign intc_prio1_src9_o[0 +: 3] = r178_src9_q;
  // field SRC10 [10:8] rw/none
  logic [2:0] r178_src10_wb, r178_src10_wm;
  assign r178_src10_wb = r178_wdata[8 +: 3];
  assign r178_src10_wm = r178_wmask[8 +: 3];
  logic [2:0] r178_src10_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r178_src10_q <= 3'h1;
    else if (r178_wr && (|r178_src10_wm)) r178_src10_q <= ((r178_src10_q & ~r178_src10_wm) | (r178_src10_wb & r178_src10_wm));
  end
  assign intc_prio1_src10_o[0 +: 3] = r178_src10_q;
  // field SRC11 [14:12] rw/none
  logic [2:0] r178_src11_wb, r178_src11_wm;
  assign r178_src11_wb = r178_wdata[12 +: 3];
  assign r178_src11_wm = r178_wmask[12 +: 3];
  logic [2:0] r178_src11_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r178_src11_q <= 3'h1;
    else if (r178_wr && (|r178_src11_wm)) r178_src11_q <= ((r178_src11_q & ~r178_src11_wm) | (r178_src11_wb & r178_src11_wm));
  end
  assign intc_prio1_src11_o[0 +: 3] = r178_src11_q;
  // field SRC12 [18:16] rw/none
  logic [2:0] r178_src12_wb, r178_src12_wm;
  assign r178_src12_wb = r178_wdata[16 +: 3];
  assign r178_src12_wm = r178_wmask[16 +: 3];
  logic [2:0] r178_src12_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r178_src12_q <= 3'h1;
    else if (r178_wr && (|r178_src12_wm)) r178_src12_q <= ((r178_src12_q & ~r178_src12_wm) | (r178_src12_wb & r178_src12_wm));
  end
  assign intc_prio1_src12_o[0 +: 3] = r178_src12_q;
  // field SRC13 [22:20] rw/none
  logic [2:0] r178_src13_wb, r178_src13_wm;
  assign r178_src13_wb = r178_wdata[20 +: 3];
  assign r178_src13_wm = r178_wmask[20 +: 3];
  logic [2:0] r178_src13_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r178_src13_q <= 3'h1;
    else if (r178_wr && (|r178_src13_wm)) r178_src13_q <= ((r178_src13_q & ~r178_src13_wm) | (r178_src13_wb & r178_src13_wm));
  end
  assign intc_prio1_src13_o[0 +: 3] = r178_src13_q;
  // field SRC14 [26:24] rw/none
  logic [2:0] r178_src14_wb, r178_src14_wm;
  assign r178_src14_wb = r178_wdata[24 +: 3];
  assign r178_src14_wm = r178_wmask[24 +: 3];
  logic [2:0] r178_src14_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r178_src14_q <= 3'h1;
    else if (r178_wr && (|r178_src14_wm)) r178_src14_q <= ((r178_src14_q & ~r178_src14_wm) | (r178_src14_wb & r178_src14_wm));
  end
  assign intc_prio1_src14_o[0 +: 3] = r178_src14_q;
  // field SRC15 [30:28] rw/none
  logic [2:0] r178_src15_wb, r178_src15_wm;
  assign r178_src15_wb = r178_wdata[28 +: 3];
  assign r178_src15_wm = r178_wmask[28 +: 3];
  logic [2:0] r178_src15_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r178_src15_q <= 3'h1;
    else if (r178_wr && (|r178_src15_wm)) r178_src15_q <= ((r178_src15_q & ~r178_src15_wm) | (r178_src15_wb & r178_src15_wm));
  end
  assign intc_prio1_src15_o[0 +: 3] = r178_src15_q;
  always_comb begin
    r178_rdata = 32'h0;
    r178_rdata[0 +: 3] = r178_src8_q;
    r178_rdata[4 +: 3] = r178_src9_q;
    r178_rdata[8 +: 3] = r178_src10_q;
    r178_rdata[12 +: 3] = r178_src11_q;
    r178_rdata[16 +: 3] = r178_src12_q;
    r178_rdata[20 +: 3] = r178_src13_q;
    r178_rdata[24 +: 3] = r178_src14_q;
    r178_rdata[28 +: 3] = r178_src15_q;
  end

  // ======================================================================
  // r179: clkrst.ID @ 64'h0000000180002000 (32-bit)
  // ======================================================================
  logic [31:0] r179_wdata, r179_wmask, r179_rdata;
  logic             r179_wr, r179_rd;
  assign r179_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r179_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r179_wr    = wr_commit && reg_sel[179];
  assign r179_rd    = rd_commit && reg_sel[179];
  // field VALUE [31:0] ro/const
  logic [31:0] r179_value_wb, r179_value_wm;
  assign r179_value_wb = r179_wdata[0 +: 32];
  assign r179_value_wm = r179_wmask[0 +: 32];
  always_comb begin
    r179_rdata = 32'h0;
    r179_rdata[0 +: 32] = 32'h53464354;
  end

  // ======================================================================
  // r180: clkrst.CONFIG @ 64'h0000000180002004 (32-bit)
  // ======================================================================
  logic [31:0] r180_wdata, r180_wmask, r180_rdata;
  logic             r180_wr, r180_rd;
  assign r180_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r180_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r180_wr    = wr_commit && reg_sel[180];
  assign r180_rd    = rd_commit && reg_sel[180];
  // field MC_EN [0:0] ro/input
  logic [0:0] r180_mc_en_wb, r180_mc_en_wm;
  assign r180_mc_en_wb = r180_wdata[0 +: 1];
  assign r180_mc_en_wm = r180_wmask[0 +: 1];
  // field NW [15:8] ro/input
  logic [7:0] r180_nw_wb, r180_nw_wm;
  assign r180_nw_wb = r180_wdata[8 +: 8];
  assign r180_nw_wm = r180_wmask[8 +: 8];
  // field NB [23:16] ro/input
  logic [7:0] r180_nb_wb, r180_nb_wm;
  assign r180_nb_wb = r180_wdata[16 +: 8];
  assign r180_nb_wm = r180_wmask[16 +: 8];
  // field VERSION [31:24] ro/input
  logic [7:0] r180_version_wb, r180_version_wm;
  assign r180_version_wb = r180_wdata[24 +: 8];
  assign r180_version_wm = r180_wmask[24 +: 8];
  always_comb begin
    r180_rdata = 32'h0;
    r180_rdata[0 +: 1] = clkrst_config_mc_en_i[0 +: 1];
    r180_rdata[8 +: 8] = clkrst_config_nw_i[0 +: 8];
    r180_rdata[16 +: 8] = clkrst_config_nb_i[0 +: 8];
    r180_rdata[24 +: 8] = clkrst_config_version_i[0 +: 8];
  end

  // ======================================================================
  // r181: clkrst.STATUS @ 64'h0000000180002008 (32-bit)
  // ======================================================================
  logic [31:0] r181_wdata, r181_wmask, r181_rdata;
  logic             r181_wr, r181_rd;
  assign r181_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r181_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r181_wr    = wr_commit && reg_sel[181];
  assign r181_rd    = rd_commit && reg_sel[181];
  // field SEQ_STATE [3:0] ro/input
  logic [3:0] r181_seq_state_wb, r181_seq_state_wm;
  assign r181_seq_state_wb = r181_wdata[0 +: 4];
  assign r181_seq_state_wm = r181_wmask[0 +: 4];
  // field MC_STATE [5:4] ro/input
  logic [1:0] r181_mc_state_wb, r181_mc_state_wm;
  assign r181_mc_state_wb = r181_wdata[4 +: 2];
  assign r181_mc_state_wm = r181_wmask[4 +: 2];
  // field RUN [6:6] ro/input
  logic [0:0] r181_run_wb, r181_run_wm;
  assign r181_run_wb = r181_wdata[6 +: 1];
  assign r181_run_wm = r181_wmask[6 +: 1];
  // field PLL_LOCKED [7:7] ro/input
  logic [0:0] r181_pll_locked_wb, r181_pll_locked_wm;
  assign r181_pll_locked_wb = r181_wdata[7 +: 1];
  assign r181_pll_locked_wm = r181_wmask[7 +: 1];
  // field CORE_CLK_OK [8:8] ro/input
  logic [0:0] r181_core_clk_ok_wb, r181_core_clk_ok_wm;
  assign r181_core_clk_ok_wb = r181_wdata[8 +: 1];
  assign r181_core_clk_ok_wm = r181_wmask[8 +: 1];
  // field MC_CLK_OK [9:9] ro/input
  logic [0:0] r181_mc_clk_ok_wb, r181_mc_clk_ok_wm;
  assign r181_mc_clk_ok_wb = r181_wdata[9 +: 1];
  assign r181_mc_clk_ok_wm = r181_wmask[9 +: 1];
  // field WDOG_WARN [10:10] ro/input
  logic [0:0] r181_wdog_warn_wb, r181_wdog_warn_wm;
  assign r181_wdog_warn_wb = r181_wdata[10 +: 1];
  assign r181_wdog_warn_wm = r181_wmask[10 +: 1];
  // field WDOG_EN [11:11] ro/input
  logic [0:0] r181_wdog_en_wb, r181_wdog_en_wm;
  assign r181_wdog_en_wb = r181_wdata[11 +: 1];
  assign r181_wdog_en_wm = r181_wmask[11 +: 1];
  // field WDOG_LOCK [12:12] ro/input
  logic [0:0] r181_wdog_lock_wb, r181_wdog_lock_wm;
  assign r181_wdog_lock_wb = r181_wdata[12 +: 1];
  assign r181_wdog_lock_wm = r181_wmask[12 +: 1];
  // field WDOG_RST_EN [13:13] ro/input
  logic [0:0] r181_wdog_rst_en_wb, r181_wdog_rst_en_wm;
  assign r181_wdog_rst_en_wb = r181_wdata[13 +: 1];
  assign r181_wdog_rst_en_wm = r181_wmask[13 +: 1];
  // field QTIMEOUT [14:14] ro/input
  logic [0:0] r181_qtimeout_wb, r181_qtimeout_wm;
  assign r181_qtimeout_wb = r181_wdata[14 +: 1];
  assign r181_qtimeout_wm = r181_wmask[14 +: 1];
  // field CMD_DROP [15:15] ro/input
  logic [0:0] r181_cmd_drop_wb, r181_cmd_drop_wm;
  assign r181_cmd_drop_wb = r181_wdata[15 +: 1];
  assign r181_cmd_drop_wm = r181_wmask[15 +: 1];
  // field WDOG_CFG_REJECTED [16:16] ro/input
  logic [0:0] r181_wdog_cfg_rejected_wb, r181_wdog_cfg_rejected_wm;
  assign r181_wdog_cfg_rejected_wb = r181_wdata[16 +: 1];
  assign r181_wdog_cfg_rejected_wm = r181_wmask[16 +: 1];
  // field DOMAINS_RELEASED [19:17] ro/input
  logic [2:0] r181_domains_released_wb, r181_domains_released_wm;
  assign r181_domains_released_wb = r181_wdata[17 +: 3];
  assign r181_domains_released_wm = r181_wmask[17 +: 3];
  // field SNAP_SEEN [31:31] ro/input
  logic [0:0] r181_snap_seen_wb, r181_snap_seen_wm;
  assign r181_snap_seen_wb = r181_wdata[31 +: 1];
  assign r181_snap_seen_wm = r181_wmask[31 +: 1];
  always_comb begin
    r181_rdata = 32'h0;
    r181_rdata[0 +: 4] = clkrst_status_seq_state_i[0 +: 4];
    r181_rdata[4 +: 2] = clkrst_status_mc_state_i[0 +: 2];
    r181_rdata[6 +: 1] = clkrst_status_run_i[0 +: 1];
    r181_rdata[7 +: 1] = clkrst_status_pll_locked_i[0 +: 1];
    r181_rdata[8 +: 1] = clkrst_status_core_clk_ok_i[0 +: 1];
    r181_rdata[9 +: 1] = clkrst_status_mc_clk_ok_i[0 +: 1];
    r181_rdata[10 +: 1] = clkrst_status_wdog_warn_i[0 +: 1];
    r181_rdata[11 +: 1] = clkrst_status_wdog_en_i[0 +: 1];
    r181_rdata[12 +: 1] = clkrst_status_wdog_lock_i[0 +: 1];
    r181_rdata[13 +: 1] = clkrst_status_wdog_rst_en_i[0 +: 1];
    r181_rdata[14 +: 1] = clkrst_status_qtimeout_i[0 +: 1];
    r181_rdata[15 +: 1] = clkrst_status_cmd_drop_i[0 +: 1];
    r181_rdata[16 +: 1] = clkrst_status_wdog_cfg_rejected_i[0 +: 1];
    r181_rdata[17 +: 3] = clkrst_status_domains_released_i[0 +: 3];
    r181_rdata[31 +: 1] = clkrst_status_snap_seen_i[0 +: 1];
  end

  // ======================================================================
  // r182: clkrst.CAUSE @ 64'h000000018000200c (32-bit)
  // ======================================================================
  logic [31:0] r182_wdata, r182_wmask, r182_rdata;
  logic             r182_wr, r182_rd;
  assign r182_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r182_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r182_wr    = wr_commit && reg_sel[182];
  assign r182_rd    = rd_commit && reg_sel[182];
  // field CAUSES [10:0] ro/input
  logic [10:0] r182_causes_wb, r182_causes_wm;
  assign r182_causes_wb = r182_wdata[0 +: 11];
  assign r182_causes_wm = r182_wmask[0 +: 11];
  always_comb begin
    r182_rdata = 32'h0;
    r182_rdata[0 +: 11] = clkrst_cause_causes_i[0 +: 11];
  end

  // ======================================================================
  // r183: clkrst.RST_INFO @ 64'h0000000180002010 (32-bit)
  // ======================================================================
  logic [31:0] r183_wdata, r183_wmask, r183_rdata;
  logic             r183_wr, r183_rd;
  assign r183_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r183_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r183_wr    = wr_commit && reg_sel[183];
  assign r183_rd    = rd_commit && reg_sel[183];
  // field RESET_COUNT [15:0] ro/input
  logic [15:0] r183_reset_count_wb, r183_reset_count_wm;
  assign r183_reset_count_wb = r183_wdata[0 +: 16];
  assign r183_reset_count_wm = r183_wmask[0 +: 16];
  // field LAST_CAUSE [19:16] ro/input
  logic [3:0] r183_last_cause_wb, r183_last_cause_wm;
  assign r183_last_cause_wb = r183_wdata[16 +: 4];
  assign r183_last_cause_wm = r183_wmask[16 +: 4];
  // field BRANCH_RELEASED [31:24] ro/input
  logic [7:0] r183_branch_released_wb, r183_branch_released_wm;
  assign r183_branch_released_wb = r183_wdata[24 +: 8];
  assign r183_branch_released_wm = r183_wmask[24 +: 8];
  always_comb begin
    r183_rdata = 32'h0;
    r183_rdata[0 +: 16] = clkrst_rst_info_reset_count_i[0 +: 16];
    r183_rdata[16 +: 4] = clkrst_rst_info_last_cause_i[0 +: 4];
    r183_rdata[24 +: 8] = clkrst_rst_info_branch_released_i[0 +: 8];
  end

  // ======================================================================
  // r184: clkrst.CLK_EN @ 64'h0000000180002018 (32-bit)
  // ======================================================================
  logic [31:0] r184_wdata, r184_wmask, r184_rdata;
  logic             r184_wr, r184_rd;
  assign r184_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r184_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r184_wr    = wr_commit && reg_sel[184];
  assign r184_rd    = rd_commit && reg_sel[184];
  // field BRANCH_EN [7:0] rw/none
  logic [7:0] r184_branch_en_wb, r184_branch_en_wm;
  assign r184_branch_en_wb = r184_wdata[0 +: 8];
  assign r184_branch_en_wm = r184_wmask[0 +: 8];
  logic [7:0] r184_branch_en_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r184_branch_en_q <= 8'hff;
    else if (r184_wr && (|r184_branch_en_wm)) r184_branch_en_q <= ((r184_branch_en_q & ~r184_branch_en_wm) | (r184_branch_en_wb & r184_branch_en_wm));
  end
  assign clkrst_clk_en_branch_en_o[0 +: 8] = r184_branch_en_q;
  always_comb begin
    r184_rdata = 32'h0;
    r184_rdata[0 +: 8] = r184_branch_en_q;
  end

  // ======================================================================
  // r185: clkrst.CLK_STAT @ 64'h000000018000201c (32-bit)
  // ======================================================================
  logic [31:0] r185_wdata, r185_wmask, r185_rdata;
  logic             r185_wr, r185_rd;
  assign r185_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r185_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r185_wr    = wr_commit && reg_sel[185];
  assign r185_rd    = rd_commit && reg_sel[185];
  // field GATE_EN [7:0] ro/input
  logic [7:0] r185_gate_en_wb, r185_gate_en_wm;
  assign r185_gate_en_wb = r185_wdata[0 +: 8];
  assign r185_gate_en_wm = r185_wmask[0 +: 8];
  // field CLK_REQUEST [15:8] ro/input
  logic [7:0] r185_clk_request_wb, r185_clk_request_wm;
  assign r185_clk_request_wb = r185_wdata[8 +: 8];
  assign r185_clk_request_wm = r185_wmask[8 +: 8];
  always_comb begin
    r185_rdata = 32'h0;
    r185_rdata[0 +: 8] = clkrst_clk_stat_gate_en_i[0 +: 8];
    r185_rdata[8 +: 8] = clkrst_clk_stat_clk_request_i[0 +: 8];
  end

  // ======================================================================
  // r186: clkrst.WDOG_CNT @ 64'h000000018000202c (32-bit)
  // ======================================================================
  logic [31:0] r186_wdata, r186_wmask, r186_rdata;
  logic             r186_wr, r186_rd;
  assign r186_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 96 +: 32];
  assign r186_wmask = {{8{acc_be[15]}}, {8{acc_be[14]}}, {8{acc_be[13]}}, {8{acc_be[12]}}};
  assign r186_wr    = wr_commit && reg_sel[186];
  assign r186_rd    = rd_commit && reg_sel[186];
  // field VALUE [31:0] ro/input
  logic [31:0] r186_value_wb, r186_value_wm;
  assign r186_value_wb = r186_wdata[0 +: 32];
  assign r186_value_wm = r186_wmask[0 +: 32];
  always_comb begin
    r186_rdata = 32'h0;
    r186_rdata[0 +: 32] = clkrst_wdog_cnt_value_i[0 +: 32];
  end

  // ======================================================================
  // r187: clkrst.CLK_MEAS @ 64'h0000000180002030 (32-bit)
  // ======================================================================
  logic [31:0] r187_wdata, r187_wmask, r187_rdata;
  logic             r187_wr, r187_rd;
  assign r187_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r187_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r187_wr    = wr_commit && reg_sel[187];
  assign r187_rd    = rd_commit && reg_sel[187];
  // field CORE_EDGES [15:0] ro/input
  logic [15:0] r187_core_edges_wb, r187_core_edges_wm;
  assign r187_core_edges_wb = r187_wdata[0 +: 16];
  assign r187_core_edges_wm = r187_wmask[0 +: 16];
  // field MC_EDGES [31:16] ro/input
  logic [15:0] r187_mc_edges_wb, r187_mc_edges_wm;
  assign r187_mc_edges_wb = r187_wdata[16 +: 16];
  assign r187_mc_edges_wm = r187_wmask[16 +: 16];
  always_comb begin
    r187_rdata = 32'h0;
    r187_rdata[0 +: 16] = clkrst_clk_meas_core_edges_i[0 +: 16];
    r187_rdata[16 +: 16] = clkrst_clk_meas_mc_edges_i[0 +: 16];
  end

  // ======================================================================
  // r188: clkrst.IRQ @ 64'h0000000180002034 (32-bit)
  // ======================================================================
  logic [31:0] r188_wdata, r188_wmask, r188_rdata;
  logic             r188_wr, r188_rd;
  assign r188_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r188_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r188_wr    = wr_commit && reg_sel[188];
  assign r188_rd    = rd_commit && reg_sel[188];
  // field WDOG_WARN [0:0] ro/input
  logic [0:0] r188_wdog_warn_wb, r188_wdog_warn_wm;
  assign r188_wdog_warn_wb = r188_wdata[0 +: 1];
  assign r188_wdog_warn_wm = r188_wmask[0 +: 1];
  always_comb begin
    r188_rdata = 32'h0;
    r188_rdata[0 +: 1] = clkrst_irq_wdog_warn_i[0 +: 1];
  end

  // ======================================================================
  // r189: sramc.CTRL @ 64'h0000000180003000 (32-bit)
  // ======================================================================
  logic [31:0] r189_wdata, r189_wmask, r189_rdata;
  logic             r189_wr, r189_rd;
  assign r189_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r189_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r189_wr    = wr_commit && reg_sel[189];
  assign r189_rd    = rd_commit && reg_sel[189];
  // field SRC_EN [3:0] rw/none
  logic [3:0] r189_src_en_wb, r189_src_en_wm;
  assign r189_src_en_wb = r189_wdata[0 +: 4];
  assign r189_src_en_wm = r189_wmask[0 +: 4];
  logic [3:0] r189_src_en_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r189_src_en_q <= 4'hf;
    else if (r189_wr && (|r189_src_en_wm)) r189_src_en_q <= ((r189_src_en_q & ~r189_src_en_wm) | (r189_src_en_wb & r189_src_en_wm));
  end
  assign sramc_ctrl_src_en_o[0 +: 4] = r189_src_en_q;
  // field FLUSH [8:8] rw/none
  logic [0:0] r189_flush_wb, r189_flush_wm;
  assign r189_flush_wb = r189_wdata[8 +: 1];
  assign r189_flush_wm = r189_wmask[8 +: 1];
  logic [0:0] r189_flush_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r189_flush_q <= 1'h0;
    else if (r189_wr && (|r189_flush_wm)) r189_flush_q <= ((r189_flush_q & ~r189_flush_wm) | (r189_flush_wb & r189_flush_wm));
  end
  assign sramc_ctrl_flush_o[0 +: 1] = r189_flush_q;
  always_comb begin
    r189_rdata = 32'h0;
    r189_rdata[0 +: 4] = r189_src_en_q;
    r189_rdata[8 +: 1] = r189_flush_q;
  end

  // ======================================================================
  // r190: sramc.STATUS @ 64'h0000000180003008 (32-bit)
  // ======================================================================
  logic [31:0] r190_wdata, r190_wmask, r190_rdata;
  logic             r190_wr, r190_rd;
  assign r190_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 64 +: 32];
  assign r190_wmask = {{8{acc_be[11]}}, {8{acc_be[10]}}, {8{acc_be[9]}}, {8{acc_be[8]}}};
  assign r190_wr    = wr_commit && reg_sel[190];
  assign r190_rd    = rd_commit && reg_sel[190];
  // field IDLE [0:0] ro/input
  logic [0:0] r190_idle_wb, r190_idle_wm;
  assign r190_idle_wb = r190_wdata[0 +: 1];
  assign r190_idle_wm = r190_wmask[0 +: 1];
  // field RSP_OVERFLOW [1:1] ro/input
  logic [0:0] r190_rsp_overflow_wb, r190_rsp_overflow_wm;
  assign r190_rsp_overflow_wb = r190_wdata[1 +: 1];
  assign r190_rsp_overflow_wm = r190_wmask[1 +: 1];
  // field BANK_PROTO [2:2] ro/input
  logic [0:0] r190_bank_proto_wb, r190_bank_proto_wm;
  assign r190_bank_proto_wb = r190_wdata[2 +: 1];
  assign r190_bank_proto_wm = r190_wmask[2 +: 1];
  always_comb begin
    r190_rdata = 32'h0;
    r190_rdata[0 +: 1] = sramc_status_idle_i[0 +: 1];
    r190_rdata[1 +: 1] = sramc_status_rsp_overflow_i[0 +: 1];
    r190_rdata[2 +: 1] = sramc_status_bank_proto_i[0 +: 1];
  end

  // ======================================================================
  // r191: sramc.PERF_CTRL @ 64'h0000000180003010 (32-bit)
  // ======================================================================
  logic [31:0] r191_wdata, r191_wmask, r191_rdata;
  logic             r191_wr, r191_rd;
  assign r191_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 0 +: 32];
  assign r191_wmask = {{8{acc_be[3]}}, {8{acc_be[2]}}, {8{acc_be[1]}}, {8{acc_be[0]}}};
  assign r191_wr    = wr_commit && reg_sel[191];
  assign r191_rd    = rd_commit && reg_sel[191];
  // field SEL [6:0] rw/none
  logic [6:0] r191_sel_wb, r191_sel_wm;
  assign r191_sel_wb = r191_wdata[0 +: 7];
  assign r191_sel_wm = r191_wmask[0 +: 7];
  logic [6:0] r191_sel_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r191_sel_q <= 7'h00;
    else if (r191_wr && (|r191_sel_wm)) r191_sel_q <= ((r191_sel_q & ~r191_sel_wm) | (r191_sel_wb & r191_sel_wm));
  end
  assign sramc_perf_ctrl_sel_o[0 +: 7] = r191_sel_q;
  // field CLEAR [8:8] w1p
  logic [0:0] r191_clear_wb, r191_clear_wm;
  assign r191_clear_wb = r191_wdata[8 +: 1];
  assign r191_clear_wm = r191_wmask[8 +: 1];
  logic [0:0] r191_clear_pulse_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) r191_clear_pulse_q <= 1'h0;
    else r191_clear_pulse_q <= {1{r191_wr}} & r191_clear_wb & r191_clear_wm;
  end
  assign sramc_perf_ctrl_clear_pulse_o[0 +: 1] = r191_clear_pulse_q;
  always_comb begin
    r191_rdata = 32'h0;
    r191_rdata[0 +: 7] = r191_sel_q;
  end

  // ======================================================================
  // r192: sramc.PERF_VAL @ 64'h0000000180003014 (32-bit)
  // ======================================================================
  logic [31:0] r192_wdata, r192_wmask, r192_rdata;
  logic             r192_wr, r192_rd;
  assign r192_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + 32 +: 32];
  assign r192_wmask = {{8{acc_be[7]}}, {8{acc_be[6]}}, {8{acc_be[5]}}, {8{acc_be[4]}}};
  assign r192_wr    = wr_commit && reg_sel[192];
  assign r192_rd    = rd_commit && reg_sel[192];
  // field VALUE [31:0] ro/input
  logic [31:0] r192_value_wb, r192_value_wm;
  assign r192_value_wb = r192_wdata[0 +: 32];
  assign r192_value_wm = r192_wmask[0 +: 32];
  always_comb begin
    r192_rdata = 32'h0;
    r192_rdata[0 +: 32] = sramc_perf_val_value_i[0 +: 32];
  end

  // ---- read data: OR of the selected registers, then lane-masked (ALP-RSP-07)
  logic [127:0] rd_raw;
  always_comb begin
    rd_raw = 128'h0;
    if (reg_sel[0]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r0_rdata;
    if (reg_sel[1]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r1_rdata;
    if (reg_sel[2]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r2_rdata;
    if (reg_sel[3]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r3_rdata;
    if (reg_sel[4]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r4_rdata;
    if (reg_sel[5]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r5_rdata;
    if (reg_sel[6]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r6_rdata;
    if (reg_sel[7]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r7_rdata;
    if (reg_sel[8]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r8_rdata;
    if (reg_sel[9]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r9_rdata;
    if (reg_sel[10]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r10_rdata;
    if (reg_sel[11]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r11_rdata;
    if (reg_sel[12]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r12_rdata;
    if (reg_sel[13]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r13_rdata;
    if (reg_sel[14]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r14_rdata;
    if (reg_sel[15]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r15_rdata;
    if (reg_sel[16]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r16_rdata;
    if (reg_sel[17]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r17_rdata;
    if (reg_sel[18]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r18_rdata;
    if (reg_sel[19]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r19_rdata;
    if (reg_sel[20]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r20_rdata;
    if (reg_sel[21]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r21_rdata;
    if (reg_sel[22]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r22_rdata;
    if (reg_sel[23]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r23_rdata;
    if (reg_sel[24]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r24_rdata;
    if (reg_sel[25]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r25_rdata;
    if (reg_sel[26]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r26_rdata;
    if (reg_sel[27]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r27_rdata;
    if (reg_sel[28]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r28_rdata;
    if (reg_sel[29]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r29_rdata;
    if (reg_sel[30]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r30_rdata;
    if (reg_sel[31]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r31_rdata;
    if (reg_sel[32]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r32_rdata;
    if (reg_sel[33]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r33_rdata;
    if (reg_sel[34]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r34_rdata;
    if (reg_sel[35]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r35_rdata;
    if (reg_sel[36]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r36_rdata;
    if (reg_sel[37]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r37_rdata;
    if (reg_sel[38]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r38_rdata;
    if (reg_sel[39]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r39_rdata;
    if (reg_sel[40]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r40_rdata;
    if (reg_sel[41]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r41_rdata;
    if (reg_sel[42]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r42_rdata;
    if (reg_sel[43]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r43_rdata;
    if (reg_sel[44]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r44_rdata;
    if (reg_sel[45]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r45_rdata;
    if (reg_sel[46]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r46_rdata;
    if (reg_sel[47]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r47_rdata;
    if (reg_sel[48]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r48_rdata;
    if (reg_sel[49]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r49_rdata;
    if (reg_sel[50]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r50_rdata;
    if (reg_sel[51]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r51_rdata;
    if (reg_sel[52]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r52_rdata;
    if (reg_sel[53]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r53_rdata;
    if (reg_sel[54]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r54_rdata;
    if (reg_sel[55]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r55_rdata;
    if (reg_sel[56]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r56_rdata;
    if (reg_sel[57]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r57_rdata;
    if (reg_sel[58]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r58_rdata;
    if (reg_sel[59]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r59_rdata;
    if (reg_sel[60]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r60_rdata;
    if (reg_sel[61]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r61_rdata;
    if (reg_sel[62]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r62_rdata;
    if (reg_sel[63]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r63_rdata;
    if (reg_sel[64]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r64_rdata;
    if (reg_sel[65]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r65_rdata;
    if (reg_sel[66]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r66_rdata;
    if (reg_sel[67]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r67_rdata;
    if (reg_sel[68]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r68_rdata;
    if (reg_sel[69]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r69_rdata;
    if (reg_sel[70]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r70_rdata;
    if (reg_sel[71]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r71_rdata;
    if (reg_sel[72]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r72_rdata;
    if (reg_sel[73]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r73_rdata;
    if (reg_sel[74]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r74_rdata;
    if (reg_sel[75]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r75_rdata;
    if (reg_sel[76]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r76_rdata;
    if (reg_sel[77]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r77_rdata;
    if (reg_sel[78]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r78_rdata;
    if (reg_sel[79]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r79_rdata;
    if (reg_sel[80]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r80_rdata;
    if (reg_sel[81]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r81_rdata;
    if (reg_sel[82]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r82_rdata;
    if (reg_sel[83]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r83_rdata;
    if (reg_sel[84]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r84_rdata;
    if (reg_sel[85]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r85_rdata;
    if (reg_sel[86]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r86_rdata;
    if (reg_sel[87]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r87_rdata;
    if (reg_sel[88]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r88_rdata;
    if (reg_sel[89]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r89_rdata;
    if (reg_sel[90]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r90_rdata;
    if (reg_sel[91]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r91_rdata;
    if (reg_sel[92]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r92_rdata;
    if (reg_sel[93]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r93_rdata;
    if (reg_sel[94]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r94_rdata;
    if (reg_sel[95]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r95_rdata;
    if (reg_sel[96]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r96_rdata;
    if (reg_sel[97]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r97_rdata;
    if (reg_sel[98]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r98_rdata;
    if (reg_sel[99]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r99_rdata;
    if (reg_sel[100]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r100_rdata;
    if (reg_sel[101]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r101_rdata;
    if (reg_sel[102]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r102_rdata;
    if (reg_sel[103]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r103_rdata;
    if (reg_sel[104]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r104_rdata;
    if (reg_sel[105]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r105_rdata;
    if (reg_sel[106]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r106_rdata;
    if (reg_sel[107]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r107_rdata;
    if (reg_sel[108]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r108_rdata;
    if (reg_sel[109]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r109_rdata;
    if (reg_sel[110]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r110_rdata;
    if (reg_sel[111]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r111_rdata;
    if (reg_sel[112]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r112_rdata;
    if (reg_sel[113]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r113_rdata;
    if (reg_sel[114]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r114_rdata;
    if (reg_sel[115]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r115_rdata;
    if (reg_sel[116]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r116_rdata;
    if (reg_sel[117]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r117_rdata;
    if (reg_sel[118]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r118_rdata;
    if (reg_sel[119]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r119_rdata;
    if (reg_sel[120]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r120_rdata;
    if (reg_sel[121]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r121_rdata;
    if (reg_sel[122]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r122_rdata;
    if (reg_sel[123]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r123_rdata;
    if (reg_sel[124]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r124_rdata;
    if (reg_sel[125]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r125_rdata;
    if (reg_sel[126]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r126_rdata;
    if (reg_sel[127]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r127_rdata;
    if (reg_sel[128]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r128_rdata;
    if (reg_sel[129]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r129_rdata;
    if (reg_sel[130]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r130_rdata;
    if (reg_sel[131]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r131_rdata;
    if (reg_sel[132]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r132_rdata;
    if (reg_sel[133]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r133_rdata;
    if (reg_sel[134]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r134_rdata;
    if (reg_sel[135]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r135_rdata;
    if (reg_sel[136]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r136_rdata;
    if (reg_sel[137]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r137_rdata;
    if (reg_sel[138]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r138_rdata;
    if (reg_sel[139]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r139_rdata;
    if (reg_sel[140]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r140_rdata;
    if (reg_sel[141]) rd_raw[0 +: 64] = rd_raw[0 +: 64] | r141_rdata;
    if (reg_sel[142]) rd_raw[64 +: 64] = rd_raw[64 +: 64] | r142_rdata;
    if (reg_sel[143]) rd_raw[0 +: 64] = rd_raw[0 +: 64] | r143_rdata;
    if (reg_sel[144]) rd_raw[64 +: 64] = rd_raw[64 +: 64] | r144_rdata;
    if (reg_sel[145]) rd_raw[0 +: 64] = rd_raw[0 +: 64] | r145_rdata;
    if (reg_sel[146]) rd_raw[64 +: 64] = rd_raw[64 +: 64] | r146_rdata;
    if (reg_sel[147]) rd_raw[0 +: 64] = rd_raw[0 +: 64] | r147_rdata;
    if (reg_sel[148]) rd_raw[64 +: 64] = rd_raw[64 +: 64] | r148_rdata;
    if (reg_sel[149]) rd_raw[0 +: 64] = rd_raw[0 +: 64] | r149_rdata;
    if (reg_sel[150]) rd_raw[64 +: 64] = rd_raw[64 +: 64] | r150_rdata;
    if (reg_sel[151]) rd_raw[0 +: 64] = rd_raw[0 +: 64] | r151_rdata;
    if (reg_sel[152]) rd_raw[64 +: 64] = rd_raw[64 +: 64] | r152_rdata;
    if (reg_sel[153]) rd_raw[0 +: 64] = rd_raw[0 +: 64] | r153_rdata;
    if (reg_sel[154]) rd_raw[64 +: 64] = rd_raw[64 +: 64] | r154_rdata;
    if (reg_sel[155]) rd_raw[0 +: 64] = rd_raw[0 +: 64] | r155_rdata;
    if (reg_sel[156]) rd_raw[64 +: 64] = rd_raw[64 +: 64] | r156_rdata;
    if (reg_sel[157]) rd_raw[0 +: 64] = rd_raw[0 +: 64] | r157_rdata;
    if (reg_sel[158]) rd_raw[64 +: 64] = rd_raw[64 +: 64] | r158_rdata;
    if (reg_sel[159]) rd_raw[0 +: 64] = rd_raw[0 +: 64] | r159_rdata;
    if (reg_sel[160]) rd_raw[64 +: 64] = rd_raw[64 +: 64] | r160_rdata;
    if (reg_sel[161]) rd_raw[0 +: 64] = rd_raw[0 +: 64] | r161_rdata;
    if (reg_sel[162]) rd_raw[64 +: 64] = rd_raw[64 +: 64] | r162_rdata;
    if (reg_sel[163]) rd_raw[0 +: 64] = rd_raw[0 +: 64] | r163_rdata;
    if (reg_sel[164]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r164_rdata;
    if (reg_sel[165]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r165_rdata;
    if (reg_sel[166]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r166_rdata;
    if (reg_sel[167]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r167_rdata;
    if (reg_sel[168]) rd_raw[0 +: 64] = rd_raw[0 +: 64] | r168_rdata;
    if (reg_sel[169]) rd_raw[64 +: 64] = rd_raw[64 +: 64] | r169_rdata;
    if (reg_sel[170]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r170_rdata;
    if (reg_sel[171]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r171_rdata;
    if (reg_sel[172]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r172_rdata;
    if (reg_sel[173]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r173_rdata;
    if (reg_sel[174]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r174_rdata;
    if (reg_sel[175]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r175_rdata;
    if (reg_sel[176]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r176_rdata;
    if (reg_sel[177]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r177_rdata;
    if (reg_sel[178]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r178_rdata;
    if (reg_sel[179]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r179_rdata;
    if (reg_sel[180]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r180_rdata;
    if (reg_sel[181]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r181_rdata;
    if (reg_sel[182]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r182_rdata;
    if (reg_sel[183]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r183_rdata;
    if (reg_sel[184]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r184_rdata;
    if (reg_sel[185]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r185_rdata;
    if (reg_sel[186]) rd_raw[96 +: 32] = rd_raw[96 +: 32] | r186_rdata;
    if (reg_sel[187]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r187_rdata;
    if (reg_sel[188]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r188_rdata;
    if (reg_sel[189]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r189_rdata;
    if (reg_sel[190]) rd_raw[64 +: 32] = rd_raw[64 +: 32] | r190_rdata;
    if (reg_sel[191]) rd_raw[0 +: 32] = rd_raw[0 +: 32] | r191_rdata;
    if (reg_sel[192]) rd_raw[32 +: 32] = rd_raw[32 +: 32] | r192_rdata;
  end
  assign acc_rdata = rd_raw & be_mask;

  assign dma_irq_o = (|(r14_cpl_q & r13_cpl_q)) | (|(r14_cpl_err_q & r13_cpl_err_q)) | (|(r14_bus_err_q & r13_bus_err_q)) | (|(r14_tag_err_q & r13_tag_err_q));  // dma
  assign tensor_irq_o = (|(r40_irq_q & r39_irq_q)) | (|(r40_err_q & r39_err_q)) | (|(r40_done_q & r39_done_q));  // tensor
  assign vector_irq_o = (|(r106_irq_q & r105_irq_q)) | (|(r106_err_q & r105_err_q));  // vector
endmodule
/* verilator lint_on UNUSEDSIGNAL */

`default_nettype wire
