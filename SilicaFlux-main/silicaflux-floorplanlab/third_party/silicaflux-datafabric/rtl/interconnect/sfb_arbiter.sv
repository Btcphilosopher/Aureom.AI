// =============================================================================
// SilicaFlux DataFabric :: sfb_arbiter -- N-way request arbiter
//
// MODE = 0  FIXED priority: requester 0 highest.  Lower requesters can starve
//           under sustained contention from higher ones (documented; use only
//           where the high-priority requesters are rate-limited, e.g. JTAG).
// MODE = 1  ROUND ROBIN: the priority pointer moves to (winner + 1) mod N only
//           when the grant is ACCEPTED (`accept`).  A requester that keeps its
//           request asserted is accepted within N-1 accepted grants of the
//           other requesters (bounded waiting; proven in formal/datafabric).
//
// Grant lock: when the granted request was presented downstream but not
// accepted (`stall` = 1), the same requester is granted again next cycle as
// long as it still requests.  This keeps the payload seen by the slave stable
// under back-pressure (SFB2 rule R2 on the slave side).  If the locked
// requester withdraws (tolerated for the legacy CPU instruction port, see
// docs/datafabric/PROTOCOL.md), the lock is released and normal arbitration
// resumes in that cycle.
//
// N need not be a power of two.  The round-robin search uses the double-width
// rotate technique of silicaflux-memoryflow rtl/common/sf_rr_arbiter.sv
// (reused with attribution; lock and fixed-priority mode added).
// Combinational path: req -> grant (one-hot), no path from accept/stall.
// =============================================================================
`default_nettype none

module sfb_arbiter #(
  parameter int N    = 4,
  parameter int MODE = 1,                 // 0 = fixed priority, 1 = round robin
  localparam int IW  = (N > 1) ? $clog2(N) : 1
) (
  input  wire logic          clk,
  input  wire logic          rst_n,
  input  wire logic [N-1:0]  req,
  input  wire logic          stall,       // granted request presented, not accepted
  input  wire logic          accept,      // granted request accepted this cycle
  output logic      [N-1:0]  grant,       // one-hot or zero
  output logic      [IW-1:0] grant_idx,
  output logic               grant_valid
);
  logic [IW-1:0] prio_q;                  // RR: index with highest priority
  logic          lock_q;
  logic [IW-1:0] lock_idx_q;

  /* verilator lint_off UNUSEDSIGNAL */
  logic [2*N-1:0] req2;                   // upper half intentionally unused
  /* verilator lint_on UNUSEDSIGNAL */
  logic [N-1:0]   rot;
  logic [IW-1:0]  off;
  logic           found;
  logic [IW:0]    sum;

  always_comb begin
    req2      = '0;
    rot       = '0;
    off       = '0;
    found     = 1'b0;
    sum       = '0;
    grant_idx = '0;
    if (lock_q && req[lock_idx_q]) begin
      found     = 1'b1;
      grant_idx = lock_idx_q;
    end else if (MODE == 0) begin
      for (int k = N - 1; k >= 0; k--) begin
        if (req[k]) begin
          found     = 1'b1;
          grant_idx = IW'(k);
        end
      end
    end else begin
      req2 = {req, req} >> prio_q;
      rot  = req2[N-1:0];
      for (int k = N - 1; k >= 0; k--) begin
        if (rot[k]) begin
          found = 1'b1;
          off   = IW'(k);
        end
      end
      sum = {1'b0, prio_q} + {1'b0, off};
      if (sum >= (IW+1)'(N)) grant_idx = IW'(sum - (IW+1)'(N));
      else                   grant_idx = IW'(sum);
    end
    grant_valid = found;
    grant       = found ? (N'(1) << grant_idx) : '0;
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      prio_q     <= '0;
      lock_q     <= 1'b0;
      lock_idx_q <= '0;
    end else begin
      lock_q     <= grant_valid && stall && !accept;
      lock_idx_q <= grant_idx;
      if (MODE != 0 && accept && grant_valid)
        prio_q <= (grant_idx == IW'(N - 1)) ? '0 : grant_idx + IW'(1);
    end
  end
endmodule

`default_nettype wire
