`default_nettype none

// =============================================================================
// sfb_skid_buffer -- two-entry valid/ready register slice.
// Logic reused unchanged from silicaflux-memoryflow rtl/common/sf_skid_buffer.sv
// (ports re-declared `wire logic` per the SilicaFlux-V coding rules).
// Registers the forward (valid/data) and backward (ready) paths; 1 transfer
// per cycle; payload stable while m_valid && !m_ready.  Storage not reset.
// =============================================================================
module sfb_skid_buffer #(
  parameter int WIDTH = 32
) (
  input  wire logic             clk,
  input  wire logic             rst_n,
  input  wire logic             s_valid,
  output logic                  s_ready,
  input  wire logic [WIDTH-1:0] s_data,
  output logic                  m_valid,
  input  wire logic             m_ready,
  output logic [WIDTH-1:0]      m_data
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
        if (skid_valid) begin
          m_valid    <= 1'b1;
          skid_valid <= 1'b0;
        end else begin
          m_valid    <= s_valid;
        end
      end else if (s_valid && s_ready) begin
        skid_valid <= 1'b1;
      end
    end
  end

  always_ff @(posedge clk) begin
    if (m_ready || !m_valid) m_data <= skid_valid ? skid_data : s_data;
    if (!(m_ready || !m_valid) && s_valid && s_ready) skid_data <= s_data;
  end
endmodule

`default_nettype wire
