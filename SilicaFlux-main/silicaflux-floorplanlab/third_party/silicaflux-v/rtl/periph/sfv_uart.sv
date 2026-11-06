// =============================================================================
// SilicaFlux-V :: sfv_uart -- 8N1 UART with TX/RX FIFOs
//
// Register map (word offsets; register-bus page, see docs/REGISTER_MAP.md):
//   0x00 DATA    W: push TX byte (dropped + TX_OVF if FIFO full)
//                R: [7:0] RX byte (pops), [31] RX_EMPTY (no pop when set)
//   0x04 STATUS  [0] TX_READY  [1] TX_IDLE (FIFO empty and shifter idle)
//                [2] RX_VALID  [3] RX_OVF (W1C) [4] FRAME_ERR (W1C)
//                [5] TX_OVF (W1C)
//   0x08 CTRL    [0] TX_IRQ_EN (irq while TX_IDLE) [1] RX_IRQ_EN (irq while
//                RX_VALID) [2] LOOPBACK (txd internally fed to rxd)
//   0x0C BAUD    [15:0] bit period in clk cycles (>= 4)
// Register map and FIFO organisation follow the repository's soc_uart.sv
// (soc_integration.tar.gz); the bus interface, counter widths and error
// handling were re-implemented for the SilicaFlux-V register bus.
// =============================================================================
`default_nettype none

module sfv_uart #(
  parameter int          FIFO_DEPTH = 4,
  parameter logic [15:0] BAUD_RESET = 16'd217        // 25 MHz / 115200
) (
  input  wire logic        clk,
  input  wire logic        rst_n,
  input  wire logic        rb_sel,
  input  wire logic        rb_we,
  input  wire logic [11:0] rb_addr,
  input  wire logic [31:0] rb_wdata,
  output logic [31:0]      rb_rdata,
  output logic             rb_err,
  output logic             txd,
  input  wire logic        rxd,
  output logic             irq
);
  localparam int CW = $clog2(FIFO_DEPTH) + 1;
  logic [15:0] baud_q;
  logic        tx_ien_q, rx_ien_q, loop_q;
  logic        rx_ovf_q, frm_err_q, tx_ovf_q;

  wire wr = rb_sel && rb_we;
  wire rd = rb_sel && !rb_we;
  wire a_data = (rb_addr == 12'h000);
  wire a_stat = (rb_addr == 12'h004);
  wire a_ctrl = (rb_addr == 12'h008);
  wire a_baud = (rb_addr == 12'h00C);

  // ------------------------------------------------------------ TX
  logic [7:0] txf_q;  logic txf_empty, txf_full; logic [CW-1:0] txf_cnt;
  logic       tx_pop;
  sfv_fifo #(.WIDTH(8), .DEPTH(FIFO_DEPTH)) u_txf (
    .clk, .rst_n, .clr(1'b0), .push(wr && a_data), .wdata(rb_wdata[7:0]),
    .pop(tx_pop), .rdata(txf_q), .empty(txf_empty), .full(txf_full), .count(txf_cnt));

  logic        tx_busy;
  logic [3:0]  tx_bit;        // 0 start, 1..8 data, 9 stop
  logic [15:0] tx_cnt;
  logic [7:0]  tx_sh;
  assign tx_pop = !tx_busy && !txf_empty;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      tx_busy <= 1'b0; tx_bit <= '0; tx_cnt <= '0; tx_sh <= '0; txd <= 1'b1;
    end else if (!tx_busy) begin
      txd <= 1'b1;
      if (tx_pop) begin
        tx_busy <= 1'b1; tx_bit <= 4'd0; tx_cnt <= baud_q - 16'd1;
        tx_sh   <= txf_q; txd <= 1'b0;                       // start bit
      end
    end else if (tx_cnt != 16'd0) begin
      tx_cnt <= tx_cnt - 16'd1;
    end else begin
      tx_cnt <= baud_q - 16'd1;
      if (tx_bit == 4'd9) begin
        tx_busy <= 1'b0; txd <= 1'b1;
      end else begin
        tx_bit <= tx_bit + 4'd1;
        if (tx_bit == 4'd8) txd <= 1'b1;                     // stop bit
        else begin txd <= tx_sh[0]; tx_sh <= {1'b0, tx_sh[7:1]}; end
      end
    end
  end

  // ------------------------------------------------------------ RX
  logic rxd_s;
  sfv_sync #(.STAGES(2), .RESET_VAL(1'b1)) u_rxs (.clk, .rst_n, .d(loop_q ? txd : rxd), .q(rxd_s));

  logic        rx_busy;
  logic [3:0]  rx_bit;
  logic [15:0] rx_cnt;
  logic [7:0]  rx_sh;
  logic        rx_push;
  logic [7:0]  rxf_q; logic rxf_empty, rxf_full; logic [CW-1:0] rxf_cnt;
  sfv_fifo #(.WIDTH(8), .DEPTH(FIFO_DEPTH)) u_rxf (
    .clk, .rst_n, .clr(1'b0), .push(rx_push), .wdata(rx_sh),
    .pop(rd && a_data), .rdata(rxf_q), .empty(rxf_empty), .full(rxf_full), .count(rxf_cnt));

  logic rx_frame_bad;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rx_busy <= 1'b0; rx_bit <= '0; rx_cnt <= '0; rx_sh <= '0;
      rx_push <= 1'b0; rx_frame_bad <= 1'b0;
    end else begin
      rx_push      <= 1'b0;
      rx_frame_bad <= 1'b0;
      if (!rx_busy) begin
        if (!rxd_s) begin                                    // start edge
          rx_busy <= 1'b1; rx_bit <= 4'd0; rx_cnt <= {1'b0, baud_q[15:1]};
        end
      end else if (rx_cnt != 16'd0) begin
        rx_cnt <= rx_cnt - 16'd1;
      end else begin
        rx_cnt <= baud_q - 16'd1;
        if (rx_bit == 4'd0) begin
          if (rxd_s) rx_busy <= 1'b0;                        // glitch: abort
          else       rx_bit  <= 4'd1;
        end else if (rx_bit <= 4'd8) begin
          rx_sh  <= {rxd_s, rx_sh[7:1]};
          rx_bit <= rx_bit + 4'd1;
        end else begin                                       // stop bit
          rx_busy <= 1'b0;
          if (rxd_s) rx_push <= 1'b1;
          else       rx_frame_bad <= 1'b1;
        end
      end
    end
  end

  // ------------------------------------------------------------ registers
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      baud_q <= BAUD_RESET; tx_ien_q <= 1'b0; rx_ien_q <= 1'b0; loop_q <= 1'b0;
      rx_ovf_q <= 1'b0; frm_err_q <= 1'b0; tx_ovf_q <= 1'b0;
    end else begin
      if (rx_push && rxf_full)       rx_ovf_q  <= 1'b1;
      if (rx_frame_bad)              frm_err_q <= 1'b1;
      if (wr && a_data && txf_full)  tx_ovf_q  <= 1'b1;
      if (wr && a_stat) begin
        if (rb_wdata[3]) rx_ovf_q  <= 1'b0;
        if (rb_wdata[4]) frm_err_q <= 1'b0;
        if (rb_wdata[5]) tx_ovf_q  <= 1'b0;
      end
      if (wr && a_ctrl) begin
        tx_ien_q <= rb_wdata[0]; rx_ien_q <= rb_wdata[1]; loop_q <= rb_wdata[2];
      end
      if (wr && a_baud) baud_q <= (rb_wdata[15:0] < 16'd4) ? 16'd4 : rb_wdata[15:0];
    end
  end

  wire tx_idle = txf_empty && !tx_busy;
  always_comb begin
    rb_rdata = 32'd0;
    rb_err   = 1'b0;
    case (rb_addr)
      12'h000: rb_rdata = {rxf_empty, 23'd0, rxf_empty ? 8'd0 : rxf_q};
      12'h004: rb_rdata = {26'd0, tx_ovf_q, frm_err_q, rx_ovf_q, !rxf_empty, tx_idle, !txf_full};
      12'h008: rb_rdata = {29'd0, loop_q, rx_ien_q, tx_ien_q};
      12'h00C: rb_rdata = {16'd0, baud_q};
      default: rb_err   = 1'b1;
    endcase
  end
  assign irq = (tx_ien_q && tx_idle) || (rx_ien_q && !rxf_empty);
  wire unused_ok = ^{txf_cnt, rxf_cnt, rb_wdata[31:16]};
endmodule

`default_nettype wire
