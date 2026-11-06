// =============================================================================
// SilicaFlux-V :: small register-bus peripherals
//   sfv_gpio   N-bit GPIO with edge interrupts
//   sfv_timer  RISC-V CLINT-style mtime/mtimecmp/msip
//   sfv_intc   level interrupt controller -> MEI
// =============================================================================
`default_nettype none

// -----------------------------------------------------------------------------
//   0x00 IN (RO, synchronised)  0x04 OUT  0x08 OE (1 = output)
//   0x0C IRQ_RISE_EN  0x10 IRQ_FALL_EN  0x14 IRQ_PEND (W1C)
// -----------------------------------------------------------------------------
module sfv_gpio #(
  parameter int N = 8
) (
  input  wire logic        clk,
  input  wire logic        rst_n,
  input  wire logic        rb_sel,
  input  wire logic        rb_we,
  input  wire logic [11:0] rb_addr,
  input  wire logic [31:0] rb_wdata,
  output logic [31:0]      rb_rdata,
  output logic             rb_err,
  input  wire logic [N-1:0] gpio_i,
  output logic [N-1:0]     gpio_o,
  output logic [N-1:0]     gpio_oe,
  output logic             irq
);
  logic [N-1:0] in_s, in_q, rise_q, fall_q, pend_q;
  wire wr = rb_sel && rb_we;

  genvar g;
  for (g = 0; g < N; g++) begin : g_sync
    sfv_sync u_s (.clk, .rst_n, .d(gpio_i[g]), .q(in_s[g]));
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      in_q <= '0; gpio_o <= '0; gpio_oe <= '0; rise_q <= '0; fall_q <= '0; pend_q <= '0;
    end else begin
      in_q <= in_s;
      if (wr && rb_addr == 12'h004) gpio_o  <= rb_wdata[N-1:0];
      if (wr && rb_addr == 12'h008) gpio_oe <= rb_wdata[N-1:0];
      if (wr && rb_addr == 12'h00C) rise_q  <= rb_wdata[N-1:0];
      if (wr && rb_addr == 12'h010) fall_q  <= rb_wdata[N-1:0];
      pend_q <= (pend_q & ~((wr && rb_addr == 12'h014) ? rb_wdata[N-1:0] : {N{1'b0}}))
              | (rise_q & in_s & ~in_q) | (fall_q & ~in_s & in_q);
    end
  end
  assign irq = |pend_q;

  always_comb begin
    rb_rdata = 32'd0;
    rb_err   = 1'b0;
    case (rb_addr)
      12'h000: rb_rdata[N-1:0] = in_s;
      12'h004: rb_rdata[N-1:0] = gpio_o;
      12'h008: rb_rdata[N-1:0] = gpio_oe;
      12'h00C: rb_rdata[N-1:0] = rise_q;
      12'h010: rb_rdata[N-1:0] = fall_q;
      12'h014: rb_rdata[N-1:0] = pend_q;
      default: rb_err = 1'b1;
    endcase
  end
endmodule

// -----------------------------------------------------------------------------
//   0x00 MTIME_LO 0x04 MTIME_HI 0x08 MTIMECMP_LO 0x0C MTIMECMP_HI
//   0x10 MSIP [0]  0x14 PRESCALE [15:0] (mtime += 1 every PRESCALE+1 cycles)
// mtimecmp resets to all-ones so no timer interrupt is pending after reset.
// -----------------------------------------------------------------------------
module sfv_timer (
  input  wire logic        clk,
  input  wire logic        rst_n,
  input  wire logic        rb_sel,
  input  wire logic        rb_we,
  input  wire logic [11:0] rb_addr,
  input  wire logic [31:0] rb_wdata,
  output logic [31:0]      rb_rdata,
  output logic             rb_err,
  output logic             irq_timer,
  output logic             irq_soft
);
  logic [63:0] mtime_q, cmp_q;
  logic [15:0] pre_q, pcnt_q;
  logic        msip_q;
  wire wr = rb_sel && rb_we;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      mtime_q <= '0; cmp_q <= '1; pre_q <= '0; pcnt_q <= '0; msip_q <= 1'b0;
    end else begin
      if (pcnt_q == pre_q) begin
        pcnt_q  <= '0;
        mtime_q <= mtime_q + 64'd1;
      end else begin
        pcnt_q  <= pcnt_q + 16'd1;
      end
      if (wr) begin
        case (rb_addr)
          12'h000: mtime_q[31:0]  <= rb_wdata;
          12'h004: mtime_q[63:32] <= rb_wdata;
          12'h008: cmp_q[31:0]    <= rb_wdata;
          12'h00C: cmp_q[63:32]   <= rb_wdata;
          12'h010: msip_q         <= rb_wdata[0];
          12'h014: begin pre_q <= rb_wdata[15:0]; pcnt_q <= '0; end
          default: ;
        endcase
      end
    end
  end
  assign irq_timer = (mtime_q >= cmp_q);
  assign irq_soft  = msip_q;

  always_comb begin
    rb_rdata = 32'd0;
    rb_err   = 1'b0;
    case (rb_addr)
      12'h000: rb_rdata = mtime_q[31:0];
      12'h004: rb_rdata = mtime_q[63:32];
      12'h008: rb_rdata = cmp_q[31:0];
      12'h00C: rb_rdata = cmp_q[63:32];
      12'h010: rb_rdata = {31'd0, msip_q};
      12'h014: rb_rdata = {16'd0, pre_q};
      default: rb_err   = 1'b1;
    endcase
  end
endmodule

// -----------------------------------------------------------------------------
//   0x00 PENDING (RO, live level of each source)  0x04 ENABLE
//   0x08 CLAIM (RO): 1 + index of the lowest pending&enabled source, 0 = none
// Sources are level-sensitive and cleared at their peripheral, so no
// pending state is stored here (no lost / duplicated interrupts).
// -----------------------------------------------------------------------------
module sfv_intc #(
  parameter int N = 8
) (
  input  wire logic        clk,
  input  wire logic        rst_n,
  input  wire logic        rb_sel,
  input  wire logic        rb_we,
  input  wire logic [11:0] rb_addr,
  input  wire logic [31:0] rb_wdata,
  output logic [31:0]      rb_rdata,
  output logic             rb_err,
  input  wire logic [N-1:0] src,
  output logic             irq_ext
);
  logic [N-1:0] en_q;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) en_q <= '0;
    else if (rb_sel && rb_we && rb_addr == 12'h004) en_q <= rb_wdata[N-1:0];
  end
  wire [N-1:0] act = src & en_q;
  assign irq_ext = |act;

  logic [7:0] claim;
  always_comb begin
    claim = 8'd0;
    for (int i = N - 1; i >= 0; i--) if (act[i]) claim = 8'(i + 1);
  end

  always_comb begin
    rb_rdata = 32'd0;
    rb_err   = 1'b0;
    case (rb_addr)
      12'h000: rb_rdata[N-1:0] = src;
      12'h004: rb_rdata[N-1:0] = en_q;
      12'h008: rb_rdata[7:0]   = claim;
      default: rb_err = 1'b1;
    endcase
  end
endmodule

`default_nettype wire
