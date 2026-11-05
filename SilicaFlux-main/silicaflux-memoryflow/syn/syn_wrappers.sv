// =============================================================================
// SilicaFlux MemoryFlow :: synthesis wrappers (parameter sets for Yosys)
// Each wrapper fixes the parameters of one block so Yosys can synthesise it
// as a parameter-free top.  SRAM arrays use IMPL=1 (foundry-macro tiling) so
// macros stay blackboxes and the reported cells are LOGIC ONLY; macro area is
// added by memoryflow.models.area from the macro tiling plan.
// =============================================================================
`default_nettype none

// 256 KiB scratchpad: 8 banks x 4096 words x 64 b, SECDED, 3 ports
module syn_spm_256k (
  input  logic clk, rst_n,
  input  logic [2:0] req_valid, req_we, rsp_ready,
  input  logic [95:0] req_addr,
  input  logic [191:0] req_wdata,
  input  logic [23:0] req_wstrb,
  output logic [2:0] req_ready, rsp_valid, rsp_err, rsp_corr,
  output logic [191:0] rsp_rdata,
  input  logic mbist_start,
  output logic mbist_done, mbist_fail
);
  logic [15:0] cc, cu; logic [31:0] c1, c2; logic mb; logic [7:0] fb; logic [11:0] fa;
  sf_spm_banked #(.NPORTS(3), .NBANKS(8), .DW(64), .BANK_DEPTH(4096), .ECC_MODE(2),
                  .INTERLEAVE(1), .RSP_DEPTH(4), .IMPL(1), .MACRO_W(72), .MACRO_D(2048)) u (
    .clk, .rst_n, .req_valid, .req_ready, .req_we, .req_addr, .req_wdata, .req_wstrb,
    .rsp_valid, .rsp_ready, .rsp_rdata, .rsp_err, .rsp_corr,
    .inj_en(1'b0), .inj_bank(3'd0), .inj_mask(72'd0), .cnt_corr(cc), .cnt_uncorr(cu),
    .mbist_start, .mbist_bg(72'd0), .mbist_busy(mb), .mbist_done, .mbist_fail,
    .mbist_fail_bank(fb), .mbist_fail_addr(fa), .cnt_conflict_cycles(c1), .cnt_stall_cycles(c2),
    .lp_sleep(1'b0));
endmodule

// 4-channel DMA, 2 engines, 16-deep data FIFOs
module syn_dma (
  input  logic clk, rst_n, psel, penable, pwrite,
  input  logic [11:0] paddr, input logic [31:0] pwdata, output logic [31:0] prdata,
  output logic pready, pslverr, irq,
  output logic rd_req_valid, input logic rd_req_ready, output logic [31:0] rd_req_addr,
  input  logic rd_rsp_valid, output logic rd_rsp_ready, input logic [63:0] rd_rsp_rdata, input logic rd_rsp_err,
  output logic wr_req_valid, input logic wr_req_ready, output logic [31:0] wr_req_addr,
  output logic [63:0] wr_req_wdata, output logic [7:0] wr_req_wstrb,
  input  logic wr_rsp_valid, output logic wr_rsp_ready, input logic wr_rsp_err,
  output logic [3:0] so_valid, input logic [3:0] so_ready, output logic [63:0] so_data,
  output logic [7:0] so_strb, output logic so_last,
  input  logic [1:0] si_valid, output logic [1:0] si_ready, input logic [127:0] si_data
);
  sf_dma #(.NCH(4)) u (.*);
endmodule

module syn_tensor_8x8 (
  input  logic clk, rst_n, a_valid, b_valid, c_ready,
  input  logic [63:0] a_data, b_data, input logic [15:0] cfg_k,
  output logic a_ready, b_ready, c_valid, c_last, output logic [63:0] c_data,
  output logic [31:0] cnt_mac
);
  logic [31:0] x1, x2, x3;
  sf_tensor_array #(.TR(8), .TC(8), .ACC_DBUF(1'b1)) u (
    .clk, .rst_n, .cfg_k, .perf_clear(1'b0), .a_valid, .a_ready, .a_data, .b_valid, .b_ready, .b_data,
    .c_valid, .c_ready, .c_data, .c_last, .cnt_mac, .cnt_stall_in(x1), .cnt_stall_acc(x2), .cnt_tiles(x3));
endmodule

module syn_vec4x16 (
  input  logic clk, rst_n, a_valid, a_last, b_valid, r_ready,
  input  logic [1:0] cfg_op, input logic [15:0] cfg_alpha,
  input  logic [63:0] a_data, b_data,
  output logic a_ready, b_ready, r_valid, r_last, output logic [63:0] r_data
);
  logic [31:0] x1, x2, x3;
  sf_vec_unit u (.clk, .rst_n, .cfg_op, .cfg_alpha, .perf_clear(1'b0), .a_valid, .a_ready, .a_data, .a_last,
                 .b_valid, .b_ready, .b_data, .r_valid, .r_ready, .r_data, .r_last,
                 .cnt_active(x1), .cnt_starve(x2), .cnt_ostall(x3));
endmodule

module syn_router2 (
  input  logic clk, rst_n, req_valid, req_we, rsp_ready,
  input  logic [31:0] req_addr, input logic [63:0] req_wdata, input logic [7:0] req_wstrb,
  output logic req_ready, rsp_valid, rsp_err, output logic [63:0] rsp_rdata,
  output logic [1:0] s_req_valid, input logic [1:0] s_req_ready, output logic [1:0] s_req_we,
  output logic [63:0] s_req_addr, output logic [127:0] s_req_wdata, output logic [15:0] s_req_wstrb,
  input  logic [1:0] s_rsp_valid, output logic [1:0] s_rsp_ready, input logic [127:0] s_rsp_rdata,
  input  logic [1:0] s_rsp_err
);
  sf_mem_router #(.NS(2), .BASES({32'h8000_0000, 32'h0}), .SIZES({32'h8000_0000, 32'h0004_0000})) u (.*);
endmodule

module syn_ecc64 (input logic [63:0] d, output logic [71:0] c, input logic [71:0] r,
                  output logic [63:0] o, output logic ce, ue);
  logic [6:0] syn;
  sf_ecc_secded_enc #(.K(64)) e (.data(d), .code(c));
  sf_ecc_secded_dec #(.K(64)) x (.code(r), .data(o), .err_corr(ce), .err_uncorr(ue), .syndrome(syn));
endmodule

// whole subsystem, SPM as macros
module syn_memflow_top (
  input  logic clk, rst_n, psel, penable, pwrite,
  input  logic [12:0] paddr, input logic [31:0] pwdata, output logic [31:0] prdata,
  output logic pready, pslverr, irq,
  input  logic h_req_valid, h_req_we, h_rsp_ready, input logic [31:0] h_req_addr,
  input  logic [63:0] h_req_wdata, input logic [7:0] h_req_wstrb,
  output logic h_req_ready, h_rsp_valid, h_rsp_err, output logic [63:0] h_rsp_rdata,
  output logic xr_req_valid, input logic xr_req_ready, output logic [31:0] xr_req_addr,
  input  logic xr_rsp_valid, output logic xr_rsp_ready, input logic [63:0] xr_rsp_rdata, input logic xr_rsp_err,
  output logic xw_req_valid, input logic xw_req_ready, output logic [31:0] xw_req_addr,
  output logic [63:0] xw_req_wdata, output logic [7:0] xw_req_wstrb,
  input  logic xw_rsp_valid, output logic xw_rsp_ready, input logic xw_rsp_err
);
  sf_memflow_top #(.SPM_NBANKS(8), .SPM_BANK_DEPTH(4096), .SPM_INTERLEAVE(1), .SPM_IMPL(1)) u (.*);
endmodule

`default_nettype wire
