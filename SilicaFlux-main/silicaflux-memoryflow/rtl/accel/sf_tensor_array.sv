// =============================================================================
// SilicaFlux MemoryFlow :: sf_tensor_array
// Output-stationary outer-product tensor engine (TR x TC MAC array).
//
// Each step k consumes one A beat (column A[:,k], TR int8) and one B beat
// (row B[k,:], TC int8) and performs TR*TC MACs:
//        C[i][j] += A[i,k] * B[k,j]
// Operand reuse: every A element is reused TC times and every B element TR
// times inside the array (register blocking) -> on-chip operand traffic per
// MAC is (TR+TC)/(TR*TC) bytes instead of 2.
//
// Tensor accumulation buffer: TR*TC x ACCW accumulators.  With ACC_DBUF=1 two
// banks ping-pong: the array computes tile n+1 while tile n drains, hiding
// the drain time (TR*TC*ACCW/DW beats).  With ACC_DBUF=0 compute stalls for
// the drain -- the RTL testbench measures both.
// Drain order: row-major, DW/ACCW accumulators per beat, last on final beat.
//
// cfg_k = K steps per tile (latched at the first step of each tile).
// Perf: cnt_mac (steps), cnt_stall_in (bank free, operands missing),
//       cnt_stall_acc (operands ready, no free accumulator bank).
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none

module sf_tensor_array #(
  parameter int DW       = 64,
  parameter int TR       = 8,
  parameter int TC       = 8,
  parameter int IW       = 8,
  parameter int ACCW     = 32,
  parameter bit ACC_DBUF = 1'b1,
  parameter int IN_FIFO  = 16,
  localparam int NBANK   = ACC_DBUF ? 2 : 1,
  localparam int NACC    = TR * TC,
  localparam int EPB     = DW / ACCW,              // accumulators per out beat
  localparam int NOUT    = NACC / EPB,             // beats per tile drain
  localparam int OW      = (NOUT > 1) ? $clog2(NOUT) : 1
) (
  input  logic          clk,
  input  logic          rst_n,
  input  logic [15:0]   cfg_k,
  input  logic          perf_clear,
  input  logic          a_valid,
  output logic          a_ready,
  input  logic [DW-1:0] a_data,
  input  logic          b_valid,
  output logic          b_ready,
  input  logic [DW-1:0] b_data,
  output logic          c_valid,
  input  logic          c_ready,
  output logic [DW-1:0] c_data,
  output logic          c_last,
  output logic [31:0]   cnt_mac,
  output logic [31:0]   cnt_stall_in,
  output logic [31:0]   cnt_stall_acc,
  output logic [31:0]   cnt_tiles
);
  localparam int CW = $clog2(IN_FIFO + 1);

  // ---------------------------------------------------------------- inputs
  logic          fa_valid, fb_valid, step;
  logic [DW-1:0] fa_dout, fb_dout;
  logic [CW-1:0] fa_cnt_unused, fb_cnt_unused;

  sf_fifo #(.WIDTH(DW), .DEPTH(IN_FIFO)) u_fa (
    .clk, .rst_n, .push_valid(a_valid), .push_ready(a_ready), .push_data(a_data),
    .pop_valid(fa_valid), .pop_ready(step), .pop_data(fa_dout), .count(fa_cnt_unused));
  sf_fifo #(.WIDTH(DW), .DEPTH(IN_FIFO)) u_fb (
    .clk, .rst_n, .push_valid(b_valid), .push_ready(b_ready), .push_data(b_data),
    .pop_valid(fb_valid), .pop_ready(step), .pop_data(fb_dout), .count(fb_cnt_unused));

  // ---------------------------------------------------------------- banks
  logic [ACCW-1:0] acc [NBANK][NACC];
  logic [NBANK-1:0] full;            // bank holds a finished tile
  logic             cb, db;          // compute bank, drain bank
  logic [15:0]      kcnt, klat;

  wire cbank_free = !full[cb];
  assign step = fa_valid && fb_valid && cbank_free;
  wire first  = (kcnt == 16'd0);
  wire [15:0] kk = first ? ((cfg_k == 16'd0) ? 16'd1 : cfg_k) : klat;
  wire tile_end = step && (kcnt == kk - 16'd1);

  // MAC array: one always_ff per accumulator (constant indices)
  genvar gb, gi, gj;
  generate
    for (gb = 0; gb < NBANK; gb++) begin : g_bank
      for (gi = 0; gi < TR; gi++) begin : g_i
        for (gj = 0; gj < TC; gj++) begin : g_j
          wire signed [IW-1:0]   ai = fa_dout[gi*IW +: IW];
          wire signed [IW-1:0]   bj = fb_dout[gj*IW +: IW];
          wire signed [2*IW-1:0] p  = ai * bj;
          always_ff @(posedge clk) begin
            if (step && (NBANK == 1 || cb == 1'(gb)))
              acc[gb][gi*TC + gj] <= (first ? '0 : acc[gb][gi*TC + gj]) + ACCW'(p);
          end
        end
      end
    end
  endgenerate

  // ---------------------------------------------------------------- drain
  logic [OW-1:0] oidx;
  wire           draining = full[db];
  logic          o_s_ready;
  wire           o_fire = draining && o_s_ready;
  logic [DW-1:0] o_beat;

  always_comb begin
    o_beat = '0;
    for (int e = 0; e < EPB; e++)
      o_beat[e*ACCW +: ACCW] = acc[db][32'(oidx) * EPB + e];
  end

  sf_skid_buffer #(.WIDTH(DW + 1)) u_out (
    .clk, .rst_n,
    .s_valid(draining), .s_ready(o_s_ready), .s_data({oidx == OW'(NOUT - 1), o_beat}),
    .m_valid(c_valid), .m_ready(c_ready), .m_data({c_last, c_data}));

  wire drain_end = o_fire && (oidx == OW'(NOUT - 1));

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      full          <= '0;
      cb            <= 1'b0;
      db            <= 1'b0;
      kcnt          <= '0;
      klat          <= 16'd1;
      oidx          <= '0;
      cnt_mac       <= '0;
      cnt_stall_in  <= '0;
      cnt_stall_acc <= '0;
      cnt_tiles     <= '0;
    end else begin
      if (step) begin
        if (first) klat <= kk;
        kcnt <= tile_end ? 16'd0 : kcnt + 16'd1;
      end
      // bank state (set on tile end, clear on drain end; may coincide on
      // different banks only)
      for (int b = 0; b < NBANK; b++) begin
        if (tile_end && cb == 1'(b))       full[b] <= 1'b1;
        else if (drain_end && db == 1'(b)) full[b] <= 1'b0;
      end
      if (tile_end && ACC_DBUF)  cb <= ~cb;
      if (drain_end && ACC_DBUF) db <= ~db;
      if (o_fire) oidx <= drain_end ? '0 : oidx + OW'(1);

      if (perf_clear) begin
        cnt_mac       <= '0;
        cnt_stall_in  <= '0;
        cnt_stall_acc <= '0;
        cnt_tiles     <= '0;
      end else begin
        if (step)                                        cnt_mac       <= cnt_mac + 32'd1;
        if (cbank_free && !(fa_valid && fb_valid))       cnt_stall_in  <= cnt_stall_in + 32'd1;
        if (!cbank_free && fa_valid && fb_valid)         cnt_stall_acc <= cnt_stall_acc + 32'd1;
        if (drain_end)                                   cnt_tiles     <= cnt_tiles + 32'd1;
      end
    end
  end

`ifndef SYNTHESIS
  // pragma translate_off
  always_ff @(posedge clk) begin
    if (tile_end && drain_end && cb == db)
      $error("sf_tensor_array: bank %0d filled and drained in same cycle", cb);
  end
  // pragma translate_on
`endif

endmodule

`default_nettype wire
