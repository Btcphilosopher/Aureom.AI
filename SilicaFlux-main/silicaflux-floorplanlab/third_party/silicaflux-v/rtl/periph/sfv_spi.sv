// =============================================================================
// SilicaFlux-V :: sfv_spi -- SPI master (byte transfers, modes 0-3)
//
//   0x00 DATA    W: start an 8-bit MSB-first transfer (bus error if BUSY)
//                R: byte received by the last transfer
//   0x04 STATUS  [0] BUSY  [1] DONE (W1C; also cleared by a new transfer)
//   0x08 CTRL    [0] CPOL [1] CPHA [2] IRQ_EN (irq while DONE)
//                [8] CS0 (1 = drive cs0_n low)
//   0x0C DIV     [15:0] SCK half period = DIV+1 clk cycles
// Boot from a standard SPI NOR flash (READ 0x03) uses mode 0.
// =============================================================================
`default_nettype none

module sfv_spi (
  input  wire logic        clk,
  input  wire logic        rst_n,
  input  wire logic        rb_sel,
  input  wire logic        rb_we,
  input  wire logic [11:0] rb_addr,
  input  wire logic [31:0] rb_wdata,
  output logic [31:0]      rb_rdata,
  output logic             rb_err,
  output logic             sck,
  output logic             mosi,
  input  wire logic        miso,
  output logic             cs0_n,
  output logic             irq
);
  logic        cpol_q, cpha_q, ien_q, cs_q, done_q, busy_q;
  logic [15:0] div_q, dcnt;
  logic [3:0]  edge_n;
  logic [7:0]  tx_sh, rx_sh;

  wire wr     = rb_sel && rb_we;
  wire a_data = (rb_addr == 12'h000);
  wire a_stat = (rb_addr == 12'h004);
  wire a_ctrl = (rb_addr == 12'h008);
  wire a_div  = (rb_addr == 12'h00C);
  wire start  = wr && a_data && !busy_q;

  // sample on leading edges (even) for CPHA=0, trailing edges (odd) for CPHA=1
  wire tick      = busy_q && (dcnt == 16'd0);
  wire is_lead   = !edge_n[0];
  wire do_sample = tick && (is_lead ^ cpha_q);
  wire do_shift  = tick && !(is_lead ^ cpha_q) && !(cpha_q && edge_n == 4'd0) &&
                   !(!cpha_q && edge_n == 4'd15);

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      cpol_q <= 1'b0; cpha_q <= 1'b0; ien_q <= 1'b0; cs_q <= 1'b0;
      div_q  <= 16'd3; dcnt <= '0; edge_n <= '0; busy_q <= 1'b0; done_q <= 1'b0;
      tx_sh  <= '0; rx_sh <= '0; sck <= 1'b0;
    end else begin
      if (wr && a_ctrl) begin
        cpol_q <= rb_wdata[0]; cpha_q <= rb_wdata[1]; ien_q <= rb_wdata[2]; cs_q <= rb_wdata[8];
        if (!busy_q) sck <= rb_wdata[0];
      end
      if (wr && a_div)  div_q <= rb_wdata[15:0];
      if (wr && a_stat && rb_wdata[1]) done_q <= 1'b0;
      if (start) begin
        busy_q <= 1'b1; done_q <= 1'b0; edge_n <= '0; dcnt <= div_q;
        tx_sh  <= rb_wdata[7:0]; sck <= cpol_q;
      end else if (busy_q) begin
        if (dcnt != 16'd0) dcnt <= dcnt - 16'd1;
        else begin
          dcnt   <= div_q;
          sck    <= ~sck;
          edge_n <= edge_n + 4'd1;
          if (do_sample) rx_sh <= {rx_sh[6:0], miso};
          if (do_shift)  tx_sh <= {tx_sh[6:0], 1'b0};
          if (edge_n == 4'd15) begin busy_q <= 1'b0; done_q <= 1'b1; end
        end
      end
    end
  end

  assign mosi  = tx_sh[7];
  assign cs0_n = !cs_q;
  assign irq   = ien_q && done_q;

  always_comb begin
    rb_rdata = 32'd0;
    rb_err   = 1'b0;
    case (rb_addr)
      12'h000: begin rb_rdata = {24'd0, rx_sh}; rb_err = wr && busy_q; end
      12'h004: rb_rdata = {30'd0, done_q, busy_q};
      12'h008: rb_rdata = {23'd0, cs_q, 5'd0, ien_q, cpha_q, cpol_q};
      12'h00C: rb_rdata = {16'd0, div_q};
      default: rb_err   = 1'b1;
    endcase
  end
  wire unused_ok = ^rb_wdata[31:16];
endmodule

`default_nettype wire
