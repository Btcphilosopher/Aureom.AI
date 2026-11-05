// =============================================================================
// SilicaFlux MemoryFlow :: sf_reuse_buffer
// Double-buffered (ping-pong) operand buffer with replay -- the producer/
// consumer staging block between DMA and a compute engine.
//
//  * Two banks of DEPTH beats in one 1R1W SRAM (sf_sram_1r1w_inferred).
//  * Producer side (stream in) fills the current fill-bank; a bank is sealed
//    on in_last or when DEPTH beats were written, then filling moves to the
//    other bank as soon as it is free (double buffering: the next tile is
//    fetched while the current one is consumed).
//  * Consumer side (stream out) replays a sealed bank cfg_replay times
//    (0 -> 1), asserting out_last at the end of every pass, then frees it.
//    Replay = operand reuse: a B tile fetched once from SRAM/DRAM by the DMA
//    is fed to the tensor array for several A row-blocks, cutting DMA
//    traffic for B by a factor of cfg_replay.
//  * 1-cycle SRAM read latency is hidden by a 3-entry output FIFO with
//    in-flight accounting -> 1 beat/cycle sustained.
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none

module sf_reuse_buffer #(
  parameter int DW    = 64,
  parameter int DEPTH = 64,              // beats per bank
  localparam int AW   = $clog2(DEPTH),
  localparam int CW   = $clog2(DEPTH + 1)
) (
  input  logic          clk,
  input  logic          rst_n,
  input  logic [7:0]    cfg_replay,
  // producer
  input  logic          in_valid,
  output logic          in_ready,
  input  logic [DW-1:0] in_data,
  input  logic          in_last,
  // consumer
  output logic          out_valid,
  input  logic          out_ready,
  output logic [DW-1:0] out_data,
  output logic          out_last,
  // status
  output logic [1:0]    bank_full,
  output logic [31:0]   cnt_replayed_beats
);
  logic [1:0]    full;
  logic [CW-1:0] fill_cnt [2];
  logic          fb, rb;              // fill bank, read bank
  logic [AW-1:0] wptr;

  // ---------------------------------------------------------------- producer
  assign in_ready = !full[fb];
  wire in_fire    = in_valid && in_ready;
  wire seal       = in_fire && (in_last || wptr == AW'(DEPTH - 1));

  // ---------------------------------------------------------------- consumer
  logic [AW-1:0] rptr;
  logic [7:0]    pass;
  logic          inflight;            // read issued last cycle
  logic          inflight_last;
  logic          of_push_ready, of_valid;
  logic [DW:0]   of_dout;
  logic [1:0]    of_cnt;            // 0..3

  wire [7:0] reps   = (cfg_replay == 8'd0) ? 8'd1 : cfg_replay;
  wire       can_rd = full[rb] && (({1'b0, of_cnt} + 3'(inflight)) < 3'd3);
  wire       rd_end_of_pass = (rptr == AW'(fill_cnt[rb] - CW'(1)));
  wire       rd_final       = rd_end_of_pass && (pass == reps - 8'd1);

  logic [DW-1:0] q;
  sf_sram_1r1w_inferred #(.LANE_W(DW), .LANES(1), .DEPTH(2 * DEPTH)) u_mem (
    .clk,
    .we(in_fire), .lane_we(1'b1), .waddr({fb, wptr}), .wdata(in_data),
    .re(can_rd), .raddr({rb, rptr}), .rdata(q)
  );

  sf_fifo #(.WIDTH(DW + 1), .DEPTH(3)) u_of (
    .clk, .rst_n,
    .push_valid(inflight), .push_ready(of_push_ready), .push_data({inflight_last, q}),
    .pop_valid(of_valid), .pop_ready(out_ready), .pop_data(of_dout), .count(of_cnt));

  assign out_valid = of_valid;
  assign out_data  = of_dout[DW-1:0];
  assign out_last  = of_dout[DW];
  assign bank_full = full;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      full               <= '0;
      fb                 <= 1'b0;
      rb                 <= 1'b0;
      wptr               <= '0;
      rptr               <= '0;
      pass               <= '0;
      inflight           <= 1'b0;
      inflight_last      <= 1'b0;
      fill_cnt[0]        <= '0;
      fill_cnt[1]        <= '0;
      cnt_replayed_beats <= '0;
    end else begin
      // producer
      if (in_fire) begin
        wptr <= seal ? '0 : wptr + AW'(1);
        if (seal) begin
          fill_cnt[fb] <= CW'(wptr) + CW'(1);
          fb           <= ~fb;
        end
      end
      // consumer
      inflight      <= can_rd;
      inflight_last <= can_rd && rd_end_of_pass;
      if (can_rd) begin
        cnt_replayed_beats <= cnt_replayed_beats + 32'd1;
        if (rd_end_of_pass) begin
          rptr <= '0;
          if (rd_final) begin
            pass <= '0;
            rb   <= ~rb;
          end else begin
            pass <= pass + 8'd1;
          end
        end else begin
          rptr <= rptr + AW'(1);
        end
      end
      // bank full flags (seal sets fill bank, final read clears read bank)
      for (int b = 0; b < 2; b++) begin
        if (seal && fb == 1'(b))                full[b] <= 1'b1;
        else if (can_rd && rd_final && rb == 1'(b)) full[b] <= 1'b0;
      end
    end
  end

`ifndef SYNTHESIS
  // pragma translate_off
  always_ff @(posedge clk) begin
    if (inflight && !of_push_ready) $error("sf_reuse_buffer: output FIFO overflow");
  end
  // pragma translate_on
`endif

endmodule

`default_nettype wire
