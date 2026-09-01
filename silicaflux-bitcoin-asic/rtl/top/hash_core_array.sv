// hash_core_array.sv -- NUM_CORES parallel hash_core instances sharing
// one job (header + target), each independently searching its own
// nonce_allocator-assigned range, with a result aggregator that latches
// whichever core finds a valid nonce first and broadcasts `stop` to the
// rest (section 8).
//
// Throughput scaling in this design comes from NUM_CORES replication of
// the ITERATIVE core (see hash_core.sv's architecture note) -- this is
// the "many independent nonce searches in flight" array from section 7/8,
// not a single deeply-pipelined engine.
module hash_core_array #(
  parameter int NUM_CORES = 4
) (
  input  logic          clk,
  input  logic          rst_n,

  input  logic           job_valid,
  input  logic [511:0]    header_block1,
  input  logic [95:0]     header_tail3,
  input  logic [31:0]     nonce_start,
  input  logic [31:0]     nonce_stride,
  input  logic [255:0]    target,
  input  logic             midstate_valid,
  input  logic [255:0]     midstate_load,
  input  logic             stop,

  output logic              any_busy,
  output logic              found,
  output logic [31:0]       found_nonce,
  output logic [255:0]      found_hash,
  output logic [31:0]       found_core_id,
  output logic               search_exhausted,          // pulses once: every core stopped and none found a match (section 34)
  output logic [31:0]       total_hashes_completed,   // telemetry only, see rtl/telemetry/telemetry.sv
  output logic [NUM_CORES-1:0] core_active_vec         // telemetry only
);

  localparam int NONCE_WIDTH = 32;

  logic [NUM_CORES*NONCE_WIDTH-1:0] core_nonce_init_flat;
  logic [NONCE_WIDTH-1:0]           core_nonce_step;

  nonce_allocator #(.NUM_CORES(NUM_CORES), .NONCE_WIDTH(NONCE_WIDTH)) u_alloc (
    .nonce_start(nonce_start), .nonce_stride(nonce_stride),
    .core_nonce_init_flat(core_nonce_init_flat), .core_nonce_step(core_nonce_step)
  );

  // Per-core internal wires. Unpacked arrays of plain (non-port) signals
  // are fine in this toolchain (see rtl/sha256/sha256_message_schedule.sv
  // header comment); every hash_core port itself stays scalar/packed.
  logic          core_stop     [0:NUM_CORES-1];
  logic          core_busy     [0:NUM_CORES-1];
  logic          core_found    [0:NUM_CORES-1];
  logic [31:0]   core_fnonce   [0:NUM_CORES-1];
  logic [255:0]  core_fhash    [0:NUM_CORES-1];
  logic          core_exhaust  [0:NUM_CORES-1];
  logic [31:0]   core_hashes   [0:NUM_CORES-1];
  logic          core_active   [0:NUM_CORES-1];

  logic [NUM_CORES-1:0] found_bits;

  genvar gi;
  generate
    for (gi = 0; gi < NUM_CORES; gi++) begin : g_core
      logic [31:0] this_nonce_init;
      assign this_nonce_init = core_nonce_init_flat[(NUM_CORES-gi)*NONCE_WIDTH-1 -: NONCE_WIDTH];

      // Any core stops when the array is told to stop, OR the moment any
      // core (including itself) reports found this same cycle -- so the
      // rest of the array halts on the same edge the winner latches.
      assign core_stop[gi] = stop || (|found_bits);

      hash_core u_hc (
        .clk(clk), .rst_n(rst_n),
        .job_valid(job_valid), .header_block1(header_block1), .header_tail3(header_tail3),
        .nonce_init(this_nonce_init), .nonce_step(core_nonce_step), .target(target),
        .midstate_valid(midstate_valid), .midstate_load(midstate_load),
        .stop(core_stop[gi]),
        .busy(core_busy[gi]), .found(core_found[gi]),
        .found_nonce(core_fnonce[gi]), .found_hash(core_fhash[gi]),
        .nonce_exhausted(core_exhaust[gi]),
        .hashes_completed(core_hashes[gi]), .core_active(core_active[gi])
      );

      assign found_bits[gi] = core_found[gi];
      assign core_active_vec[gi] = core_active[gi];
    end
  endgenerate

  // Priority-encode the lowest-index core that found a result this cycle
  // (a simultaneous multi-core find is astronomically unlikely for a real
  // target, but must still be handled deterministically).
  logic              any_found_now;
  logic [31:0]        winner_nonce;
  logic [255:0]        winner_hash;
  logic [31:0]          winner_id;

  always_comb begin
    any_found_now = 1'b0;
    winner_nonce  = '0;
    winner_hash   = '0;
    winner_id     = '0;
    for (int i = NUM_CORES - 1; i >= 0; i--) begin
      if (found_bits[i]) begin
        any_found_now = 1'b1;
        winner_nonce  = core_fnonce[i];
        winner_hash   = core_fhash[i];
        winner_id     = i[31:0];
      end
    end
  end

  logic any_busy_comb;
  always_comb begin
    any_busy_comb = 1'b0;
    for (int i = 0; i < NUM_CORES; i++) any_busy_comb |= core_busy[i];
  end

  logic [31:0] total_hashes_comb;
  always_comb begin
    total_hashes_comb = '0;
    for (int i = 0; i < NUM_CORES; i++) total_hashes_comb += core_hashes[i];
  end

  // job_active_r: sticky "a search is/was running for the current job",
  // set on job_valid and cleared once we report either found or
  // search_exhausted. Used only to detect the any_busy 1->0 edge that
  // means "every core stopped on its own without a match" (as opposed to
  // the edge is spurious at reset, or job_valid hasn't been seen yet).
  logic job_active_r, any_busy_prev_r;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      found                  <= 1'b0;
      found_nonce            <= '0;
      found_hash             <= '0;
      found_core_id          <= '0;
      any_busy               <= 1'b0;
      total_hashes_completed <= '0;
      search_exhausted       <= 1'b0;
      job_active_r           <= 1'b0;
      any_busy_prev_r        <= 1'b0;
    end else begin
      found            <= any_found_now;
      search_exhausted <= 1'b0;

      if (any_found_now) begin
        found_nonce   <= winner_nonce;
        found_hash    <= winner_hash;
        found_core_id <= winner_id;
      end

      any_busy               <= any_busy_comb;
      total_hashes_completed <= total_hashes_comb;

      if (job_valid) job_active_r <= 1'b1;
      else if (any_found_now) job_active_r <= 1'b0;

      any_busy_prev_r <= any_busy;
      if (job_active_r && any_busy_prev_r && !any_busy && !any_found_now) begin
        search_exhausted <= 1'b1;
        job_active_r     <= 1'b0;
      end
    end
  end

endmodule : hash_core_array
