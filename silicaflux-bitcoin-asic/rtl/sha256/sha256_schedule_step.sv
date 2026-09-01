// sha256_schedule_step.sv -- ONE round of message-schedule advance,
// purely combinational (no clock). This is exactly the same recurrence
// as sha256_message_schedule.sv's SLIDING_WINDOW logic, repackaged as a
// stateless building block so sha256_pipeline.sv can chain up to 64 of
// them combinationally within a pipeline stage (REGISTER_PIPELINED
// architecture, section 6): each instance advances the 16-word window by
// exactly one round, with pipeline registers inserted between chained
// instances only at stage boundaries.
//
// window_in/window_out pack 16 words as one 512-bit vector using the
// same slot convention as sha256_message_schedule's internal w_mem[]:
// slot k = window[511-32k -: 32] holds whichever W[t] has t mod 16 == k
// most recently defined -- i.e. this module's window_in/window_out are
// bit-for-bit interchangeable with sha256_message_schedule's block_bits
// port at the initial load (t_in=0) and with each other across chained
// instances.
module sha256_schedule_step (
  input  logic [511:0] window_in,
  input  logic [5:0]   t_in,    // round index this window currently represents (0..63)
  output logic [31:0]  w_out,   // W[t_in]
  output logic [511:0] window_out,
  output logic [5:0]   t_out    // t_in + 1
);

  function automatic logic [31:0] win_slot(input logic [511:0] win, input logic [3:0] k);
    win_slot = win[511 - 32*k -: 32];
  endfunction

  logic [3:0]  idx;
  logic [31:0] w_tm2, w_tm7, w_tm15, w_tm16, sigma1_val, sigma0_val, next_w;
  logic        write_slot;

  assign idx = t_in[3:0];
  assign w_tm2  = win_slot(window_in, idx - 4'd1);
  assign w_tm7  = win_slot(window_in, idx - 4'd6);
  assign w_tm15 = win_slot(window_in, idx - 4'd14);
  assign w_tm16 = win_slot(window_in, idx + 4'd1);

  sha256_small_sigma1 u_sigma1 (.x(w_tm2),  .y(sigma1_val));
  sha256_small_sigma0 u_sigma0 (.x(w_tm15), .y(sigma0_val));
  assign next_w = sigma1_val + w_tm7 + sigma0_val + w_tm16;

  assign w_out = win_slot(window_in, idx);
  assign t_out = t_in + 6'd1;
  assign write_slot = (t_in >= 6'd15);

  genvar gk;
  generate
    for (gk = 0; gk < 16; gk++) begin : g_slot
      assign window_out[511 - 32*gk -: 32] =
        (write_slot && (4'(gk) == (idx + 4'd1))) ? next_w : win_slot(window_in, 4'(gk));
    end
  endgenerate

endmodule : sha256_schedule_step
