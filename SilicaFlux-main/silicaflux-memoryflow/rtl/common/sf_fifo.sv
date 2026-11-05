// =============================================================================
// SilicaFlux MemoryFlow :: sf_fifo
// Synchronous show-ahead (first-word-fall-through) FIFO, flop-based storage.
// Valid/ready on both sides.  push_ready does NOT depend on pop_ready, so the
// FIFO breaks combinational ready chains (it is a clean elastic boundary).
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none

module sf_fifo #(
  parameter int WIDTH = 8,
  parameter int DEPTH = 4,
  localparam int CW   = $clog2(DEPTH + 1)
) (
  input  logic             clk,
  input  logic             rst_n,
  // write side
  input  logic             push_valid,
  output logic             push_ready,
  input  logic [WIDTH-1:0] push_data,
  // read side
  output logic             pop_valid,
  input  logic             pop_ready,
  output logic [WIDTH-1:0] pop_data,
  // occupancy
  output logic [CW-1:0]    count
);
  localparam int PW = (DEPTH > 1) ? $clog2(DEPTH) : 1;

  logic [WIDTH-1:0] mem [DEPTH];
  logic [PW-1:0]    wptr, rptr;
  logic [CW-1:0]    cnt;

  wire do_push = push_valid & push_ready;
  wire do_pop  = pop_valid  & pop_ready;

  assign push_ready = (cnt != CW'(DEPTH));
  assign pop_valid  = (cnt != '0);
  assign pop_data   = mem[rptr];
  assign count      = cnt;

  function automatic logic [PW-1:0] inc(input logic [PW-1:0] p);
    inc = (p == PW'(DEPTH - 1)) ? '0 : p + PW'(1);
  endfunction

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      wptr <= '0;
      rptr <= '0;
      cnt  <= '0;
    end else begin
      if (do_push) wptr <= inc(wptr);
      if (do_pop)  rptr <= inc(rptr);
      case ({do_push, do_pop})
        2'b10:   cnt <= cnt + CW'(1);
        2'b01:   cnt <= cnt - CW'(1);
        default: cnt <= cnt;
      endcase
    end
  end

  always_ff @(posedge clk) begin
    if (do_push) mem[wptr] <= push_data;
  end

endmodule

`default_nettype wire
