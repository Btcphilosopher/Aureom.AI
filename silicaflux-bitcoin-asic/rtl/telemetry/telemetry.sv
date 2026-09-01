// telemetry.sv -- monitoring/counters only (section 33). This module has
// no output that feeds back into the hashing datapath and no input that
// affects hash correctness -- it is pure observation, wired as a side
// branch off miner_top.sv, and can be entirely removed (ENABLE_TELEMETRY
// = 0) without changing a single computed hash.
//
// temperature_proxy / power_proxy are EXPLICITLY digital activity
// proxies, not physical measurements: power_proxy tracks instantaneous
// active-core count (a reasonable stand-in for switching-activity-driven
// dynamic power), and temperature_proxy is a simple leaky integrator of
// it (models thermal inertia: temperature lags sustained activity,
// unlike instantaneous power). Real power/temperature require a
// technology-specific power analysis and a real thermal model -- see
// python/silicaflux_bitcoin/analysis/{area_energy_model,thermal_model}.py
// and section 32/40's rule against claiming physical measurements from
// simulation.
module telemetry #(
  parameter int NUM_CORES     = 4,
  parameter int COUNTER_WIDTH = 32
) (
  input  logic         clk,
  input  logic         rst_n,
  input  logic         enable,               // ENABLE_TELEMETRY gate

  input  logic [NUM_CORES-1:0] core_active_vec,
  input  logic          job_valid,
  input  logic          any_busy,
  input  logic          job_done_pulse,       // found | search_exhausted
  input  logic [COUNTER_WIDTH-1:0] job_hash_count,  // total_hashes_completed at job_done_pulse
  input  logic           valid_hash_event,     // pulse: found
  input  logic           error_event,          // pulse: any ERROR-state entry (section 34)

  output logic [COUNTER_WIDTH-1:0] clock_cycles,
  output logic [COUNTER_WIDTH-1:0] hashes_completed_lifetime,
  output logic [COUNTER_WIDTH-1:0] valid_hashes_count,
  output logic [COUNTER_WIDTH-1:0] error_count,
  output logic [COUNTER_WIDTH-1:0] pipeline_stalls,
  output logic [$clog2(NUM_CORES+1)-1:0] active_core_count,
  output logic [COUNTER_WIDTH-1:0] temperature_proxy,
  output logic [COUNTER_WIDTH-1:0] power_proxy
);

  localparam int ACTIVE_W = $clog2(NUM_CORES+1);
  logic [ACTIVE_W-1:0] active_count_comb;
  always_comb begin
    active_count_comb = '0;
    for (int i = 0; i < NUM_CORES; i++)
      active_count_comb = active_count_comb + { {(ACTIVE_W-1){1'b0}}, core_active_vec[i] };
  end

  // Leaky-integrator shift amount for the temperature proxy: bigger =
  // slower to respond (more thermal inertia). Purely a modelling choice.
  localparam int TEMP_SHIFT = 6;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      clock_cycles              <= '0;
      hashes_completed_lifetime <= '0;
      valid_hashes_count        <= '0;
      error_count                <= '0;
      pipeline_stalls            <= '0;
      active_core_count          <= '0;
      temperature_proxy          <= '0;
      power_proxy                <= '0;
    end else if (enable) begin
      clock_cycles     <= clock_cycles + 1'b1;
      active_core_count <= active_count_comb;
      power_proxy        <= {{(COUNTER_WIDTH-$clog2(NUM_CORES+1)){1'b0}}, active_count_comb};
      temperature_proxy  <= temperature_proxy
                             - (temperature_proxy >> TEMP_SHIFT)
                             + ({{(COUNTER_WIDTH-$clog2(NUM_CORES+1)){1'b0}}, active_count_comb} >> TEMP_SHIFT);

      if (job_done_pulse)   hashes_completed_lifetime <= hashes_completed_lifetime + job_hash_count;
      if (valid_hash_event) valid_hashes_count        <= valid_hashes_count + 1'b1;
      if (error_event)      error_count                <= error_count + 1'b1;
      if (job_valid && any_busy) pipeline_stalls        <= pipeline_stalls + 1'b1;
    end
  end

endmodule : telemetry
