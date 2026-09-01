// sha256_properties.sv -- protocol/FSM invariants for miner_top.sv,
// checked continuously against a running simulation (section 27).
//
// Tooling note (why this is not SVA `assert property`/`bind`): Icarus
// Verilog 12.0 -- the simulator used throughout this project's `make
// test`/scripts/run_iverilog.sh flow -- was confirmed during bring-up to
// reject concurrent-assertion syntax (`property`/`endproperty`,
// `assert property (...)`) and the `bind` statement outright at parse
// time (isolated repro, both fail identically with plain syntax errors,
// independent of any `-g` flag). Immediate assertions (`assert (expr)
// else ...`) DO work. So every check below is written as a plain
// `always_ff` with manually-tracked previous-cycle state feeding
// immediate assertions -- functionally the same invariants a concurrent
// `disable iff (!rst_n) a |-> b` property would express, just spelled
// out by hand instead of relying on SVA temporal operators. This module
// is a plain design-style block, INSTANTIATED directly (wired to the
// signals it checks like any other submodule -- see tb/system/
// tb_miner_top.sv) rather than externally `bind`-attached.
//
// No formal (proof) tool (e.g. SymbiYosys) was run against these in this
// session -- see reports/ and docs/verification_plan.md for exactly what
// was and wasn't executed. What IS demonstrated: zero assertion failures
// across every passing testbench scenario in this project, PLUS (see
// tb/system/tb_formal_checker_selftest.sv) at least one deliberately
// injected bug is confirmed to trip the corresponding assertion --
// i.e. these checks are not vacuous.
module miner_protocol_checker (
  input logic         clk,
  input logic         rst_n,

  input logic          header_valid,
  input logic          header_ready,
  input logic          start,
  input logic          busy,
  input logic          found,
  input logic          error,
  input logic          exhausted,
  input logic [3:0]    state_out
);

  logic busy_prev, ever_loaded_r, rst_n_prev;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      busy_prev     <= 1'b0;
      ever_loaded_r <= 1'b0;
      rst_n_prev    <= 1'b0;
    end else begin
      // --- CHECK 1: found and error are mutually exclusive results. ---
      assert (!(found && error))
        else $display("[ASSERT-FAIL] %m: found and error asserted in the same cycle at t=%0t", $time);

      // --- CHECK 2: FSM state is always fully-defined (no X/Z bits --
      //     `^x !== 1'bx` is the standard reduction-XOR idiom for that,
      //     since unknown propagates through XOR) AND within the 8
      //     legal ST_IDLE..ST_ERROR encodings (0..7, see
      //     miner_controller.sv). `inside {..}` isn't used here:
      //     confirmed unsupported by this Icarus build. ---
      assert ((^state_out) !== 1'bx && state_out <= 4'd7)
        else $display("[ASSERT-FAIL] %m: state_out=%0d is not a legal (defined, in-range) FSM state at t=%0t", state_out, $time);

      // --- CHECK 3: header_ready and busy are never both asserted --
      //     "ready for a new header" must imply "not mid-job". ---
      assert (!(header_ready && busy))
        else $display("[ASSERT-FAIL] %m: header_ready and busy both 1 at t=%0t (would silently accept a header mid-job)", $time);

      // --- CHECK 4: no result (found/exhausted) before any job has ever
      //     been armed with `start` since reset -- "no result before
      //     computation". ---
      if (start) ever_loaded_r <= 1'b1;
      assert (!((found || exhausted) && !ever_loaded_r))
        else $display("[ASSERT-FAIL] %m: found/exhausted asserted before any start pulse was ever seen, t=%0t", $time);

      // --- CHECK 5: found only ever follows a cycle where busy was
      //     already 1 (a result cannot appear out of a `busy=0` idle
      //     state without a search having actually run). ---
      assert (!(found && !busy_prev))
        else $display("[ASSERT-FAIL] %m: found asserted but busy was 0 the previous cycle, t=%0t", $time);
      busy_prev <= busy;

      // --- CHECK 6: reset behaviour -- the first cycle observed with
      //     rst_n=1 must show busy/found/error all deasserted and
      //     header_ready asserted (checked once, right at the
      //     reset->run transition this checker itself observes). ---
      if (!rst_n_prev) begin
        assert (!busy && !found && !error && header_ready)
          else $display("[ASSERT-FAIL] %m: unclean state on first cycle out of reset (busy=%0d found=%0d error=%0d header_ready=%0d) at t=%0t",
                         busy, found, error, header_ready, $time);
      end
      rst_n_prev <= 1'b1;
    end
  end

endmodule : miner_protocol_checker
