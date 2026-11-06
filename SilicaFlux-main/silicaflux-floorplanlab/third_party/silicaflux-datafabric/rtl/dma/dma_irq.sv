`default_nettype none

// =============================================================================
// SilicaFlux DataFabric :: dma_irq -- DMA interrupt status/enable.  status[i] is set by its event (set wins
// over a same-cycle write-one-to-clear), cleared by writing 1; irq is the
// level OR of enabled pending bits (bit 0 completion, bit 1 error).
// =============================================================================
module dma_irq (
  input  wire logic       clk,
  input  wire logic       rst_n,
  input  wire logic       set_done,
  input  wire logic       set_err,
  input  wire logic       clr_wr,
  input  wire logic [1:0] clr_mask,
  input  wire logic [1:0] enable,
  output logic      [1:0] status,
  output logic            irq
);
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) status <= '0;
    else        status <= ((clr_wr ? (status & ~clr_mask) : status)) | {set_err, set_done};
  end
  assign irq = |(status & enable);
endmodule

`default_nettype wire
