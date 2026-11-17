// =============================================================================
//  sf_albion_chan_checker.sv  --  valid/ready channel protocol checker
// -----------------------------------------------------------------------------
//  Implements ALP-REQ-02 and ALP-RSP-02 for ANY valid/ready channel:
//    once valid is asserted without ready, valid must stay asserted and the
//    payload must not change until the transfer is accepted.
//
//  Written in the synthesizable subset with immediate assertions only, so the
//  same module is used
//    * in Verilator simulation  (failed assertion aborts the run), and
//    * in Yosys formal proofs   (assert on a component's outputs, assume on
//      its inputs, selected with ASSUME_MODE).
//
//  waive_i : when high in a cycle, the stability obligation for the FOLLOWING
//            cycle is waived.  Used only for the documented flush / cancel
//            exception (ALP-CAN-03): a flush may withdraw a pending valid.
//
//  Reset (ALP-RST-01): while rst_ni is low no check is made, and the history
//  is cleared, so the first cycle after reset deassertion has no obligation.
// =============================================================================
`default_nettype none

module sf_albion_chan_checker #(
  parameter int unsigned WIDTH       = 8,
  parameter bit          ASSUME_MODE = 1'b0   // 1: constrain (formal inputs); 0: assert
) (
  input wire logic             clk_i,
  input wire logic             rst_ni,
  input wire logic             valid_i,
  input wire logic             ready_i,
  input wire logic [WIDTH-1:0] payload_i,
  input wire logic             waive_i
);
  logic             hold_q;      // previous cycle: valid && !ready && not waived
  logic [WIDTH-1:0] payload_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      hold_q    <= 1'b0;
      payload_q <= '0;
    end else begin
      hold_q    <= valid_i && !ready_i && !waive_i;
      payload_q <= payload_i;
    end
  end

  if (ASSUME_MODE) begin : gen_assume
    always_ff @(posedge clk_i) begin
      if (rst_ni && hold_q) begin
        a_valid_held:   assume (valid_i);
        a_payload_held: assume (payload_i == payload_q);
      end
    end
  end else begin : gen_assert
    always_ff @(posedge clk_i) begin
      if (rst_ni && hold_q) begin
        a_valid_held:   assert (valid_i);
        a_payload_held: assert (payload_i == payload_q);
      end
    end
  end
endmodule

`default_nettype wire
