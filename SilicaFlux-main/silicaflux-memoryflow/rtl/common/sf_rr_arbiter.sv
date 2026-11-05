// =============================================================================
// SilicaFlux MemoryFlow :: sf_rr_arbiter
// N-way round-robin arbiter.  Combinational one-hot grant from `req`; the
// priority pointer advances past the winner only when `accept` is high
// (i.e. the granted transfer actually completed its handshake).  This keeps
// grants stable under backpressure and guarantees starvation freedom:
// any persistent requester is served within N accepted grants.
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none

module sf_rr_arbiter #(
  parameter int N = 4,
  localparam int IW = (N > 1) ? $clog2(N) : 1
) (
  input  logic          clk,
  input  logic          rst_n,
  input  logic [N-1:0]  req,
  input  logic          accept,     // grant was consumed this cycle
  output logic [N-1:0]  grant,      // one-hot (or zero)
  output logic [IW-1:0] grant_idx,
  output logic          grant_valid
);
  // `prio` = index that has highest priority this cycle.
  logic [IW-1:0] prio;

  // Double-width rotate trick: search req rotated by prio.
  /* verilator lint_off UNUSEDSIGNAL */
  logic [2*N-1:0] req2;     // upper half intentionally unused
  /* verilator lint_on UNUSEDSIGNAL */
  logic [N-1:0]   rot;
  logic [IW-1:0]  off;
  logic           found;

  always_comb begin
    req2  = {req, req} >> prio;
    rot   = req2[N-1:0];
    off   = '0;
    found = 1'b0;
    for (int k = 0; k < N; k++) begin
      if (!found && rot[k]) begin
        found = 1'b1;
        off   = IW'(k);
      end
    end
    grant_valid = found;
    // grant_idx = (prio + off) mod N
    if ({1'b0, prio} + {1'b0, off} >= (IW+1)'(N))
      grant_idx = IW'({1'b0, prio} + {1'b0, off} - (IW+1)'(N));
    else
      grant_idx = prio + off;
    grant = found ? (N'(1) << grant_idx) : '0;
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      prio <= '0;
    end else if (accept && grant_valid) begin
      prio <= (grant_idx == IW'(N - 1)) ? '0 : grant_idx + IW'(1);
    end
  end

endmodule

`default_nettype wire
