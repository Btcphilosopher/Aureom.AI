// =============================================================================
// SilicaFlux MemoryFlow :: sf_skid_buffer
// Two-entry pipeline register slice for a valid/ready channel.  Registers
// both the forward (valid/data) path and the backward (ready) path, so it can
// be dropped onto any long interconnect wire without breaking throughput:
// sustains 1 transfer/cycle with full backpressure support.
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none

module sf_skid_buffer #(
  parameter int WIDTH = 32
) (
  input  logic             clk,
  input  logic             rst_n,
  input  logic             s_valid,
  output logic             s_ready,
  input  logic [WIDTH-1:0] s_data,
  output logic             m_valid,
  input  logic             m_ready,
  output logic [WIDTH-1:0] m_data
);
  logic             skid_valid;
  logic [WIDTH-1:0] skid_data;

  assign s_ready = ~skid_valid;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      m_valid    <= 1'b0;
      skid_valid <= 1'b0;
    end else begin
      if (m_ready || !m_valid) begin
        // output register free (or draining this cycle)
        if (skid_valid) begin
          m_valid    <= 1'b1;
          skid_valid <= 1'b0;
        end else begin
          m_valid    <= s_valid;
        end
      end else if (s_valid && s_ready) begin
        // output stalled, park incoming beat in the skid register
        skid_valid <= 1'b1;
      end
    end
  end

  always_ff @(posedge clk) begin
    if (m_ready || !m_valid) begin
      m_data <= skid_valid ? skid_data : s_data;
    end
    if (!(m_ready || !m_valid) && s_valid && s_ready) begin
      skid_data <= s_data;
    end
  end

endmodule

`default_nettype wire
