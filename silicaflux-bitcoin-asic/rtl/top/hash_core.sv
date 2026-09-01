// hash_core.sv -- one independent Bitcoin nonce-search engine: repeatedly
// runs SHA256(SHA256(header)) over successive nonce values and compares
// each result against the job's target, reusing the midstate across
// every trial after the first (sections 9/10/13/14).
//
// Architecture note (honest scoping): this core is built on the
// ITERATIVE compression engine (sha256_compressor.sv, via
// sha256_double_hash.sv) -- its single-hash-at-a-time start/busy/done
// control flow maps directly onto a straightforward, fully-verified
// nonce-search FSM. The spatially-unrolled PIPELINED engine
// (rtl/pipeline/sha256_pipeline.sv) is implemented and independently
// verified across all 7 supported depths (see
// tb/integration/tb_sha256_pipeline.sv and reports/sha256_pipeline_
// sweep.log) and is drop-in compatible at the {state_in,block_bits} ->
// state_out level, but exploiting its 1-hash/cycle throughput here would
// require a multi-nonce-in-flight scoreboard (matching results back to
// the nonce that produced them) that this session did not have the
// verification budget to build and prove correct. Per this project's
// stated priority order (correctness -> verification -> architecture ->
// throughput...), that integration is left as documented future work
// rather than shipped unverified; throughput in *this* design scales by
// replicating hash_core across hash_core_array.sv's NUM_CORES instead.
//
// Nonce overflow (section 34 error handling): if nonce_reg + nonce_step
// would exceed the 32-bit nonce field, the core stops searching and
// raises nonce_exhausted rather than silently wrapping mid-job (wrapping
// is fine, and mathematically collision-free, for the *allocator*'s
// cross-core split -- see nonce_allocator.sv -- but a single job
// exhausting its whole assigned range means "ask the control plane for a
// new job", not "keep going forever").
module hash_core (
  input  logic         clk,
  input  logic         rst_n,

  // Job load: a new header + this core's nonce range + the job's target.
  input  logic          job_valid,
  input  logic [511:0]   header_block1,    // header[0:64)
  input  logic [95:0]    header_tail3,     // {merkle_tail(32), ntime(32), nbits(32)} -- fixed for the whole job
  input  logic [31:0]    nonce_init,       // this core's first nonce (from nonce_allocator)
  input  logic [31:0]    nonce_step,       // per-trial increment (nonce_allocator's core_nonce_step)
  input  logic [255:0]   target,           // pre-expanded 256-bit target (nbits_expand, shared across cores)

  // Optional direct midstate injection (section 14): if set alongside
  // job_valid, skips the internal block-1 compression for the first trial.
  input  logic           midstate_valid,
  input  logic [255:0]   midstate_load,

  input  logic           stop,             // pulse: abort the current search, return to IDLE

  output logic            busy,
  output logic            found,            // one-cycle pulse
  output logic [31:0]     found_nonce,
  output logic [255:0]    found_hash,
  output logic             nonce_exhausted,  // one-cycle pulse: ran out of assigned nonce range

  // Telemetry-facing outputs only (section 33): never read back into the
  // hashing datapath above.
  output logic [31:0]     hashes_completed,
  output logic            core_active
);

  typedef enum logic [1:0] { ST_IDLE, ST_FIRST, ST_SEARCH } state_e;
  state_e state_r;

  logic [511:0] header_block1_r;
  logic [95:0]  header_tail3_r;
  logic [31:0]  nonce_r;
  logic [31:0]  nonce_step_r;
  logic [255:0] target_r;
  logic [255:0] midstate_r;

  logic         dh_start, dh_use_midstate, dh_busy, dh_done;
  logic [255:0] dh_midstate_in, dh_pow_hash, dh_midstate_out;
  logic [127:0] dh_header_tail4;
  logic         dh_midstate_out_valid;
  logic [31:0]  nonce_wire_word;

  // nonce_r is a plain arithmetic counter (numeric nonce value, MSB-first
  // as an SV vector: nonce_r[31:24] is numerically most significant).
  // Bitcoin's header serialization is LITTLE-ENDIAN per field (see
  // python/silicaflux_bitcoin/reference/block_header.py: `nonce.to_bytes
  // (4, "little")`), so the nonce's four WIRE bytes, in order, are
  // nonce_r[7:0], nonce_r[15:8], nonce_r[23:16], nonce_r[31:24] -- the
  // reverse of nonce_r's own bit-vector byte order. Every other word this
  // design hashes (header_block1, header_tail3, the compressed digest
  // re-hashed in pass 2, ...) already arrives pre-packed in correct wire
  // byte order from wherever it was serialized (Python's serialize() in
  // testbenches, or the equivalent host-side packing in a real system),
  // so nonce_r -- built by *arithmetic*, not by byte-parsing -- is the
  // one signal in this whole design that needs an explicit byte-swap
  // before it can be used as a SHA-256 message word. Caught by
  // tb/integration/tb_hash_core.sv against real per-nonce Python vectors;
  // without this swap the core silently searches the wrong nonce
  // sequence (see docs/sha256_spec_notes.md for the full writeup).
  assign nonce_wire_word = { nonce_r[7:0], nonce_r[15:8], nonce_r[23:16], nonce_r[31:24] };
  assign dh_header_tail4 = {header_tail3_r, nonce_wire_word};

  sha256_double_hash u_dh (
    .clk(clk), .rst_n(rst_n),
    .start(dh_start), .use_midstate(dh_use_midstate),
    .midstate_in(dh_midstate_in), .header_block1(header_block1_r),
    .header_tail4(dh_header_tail4),
    .busy(dh_busy), .done(dh_done), .pow_hash(dh_pow_hash),
    .midstate_out_valid(dh_midstate_out_valid), .midstate_out(dh_midstate_out)
  );

  logic meets;
  target_compare u_cmp (.hash(dh_pow_hash), .target(target_r), .meets_target(meets));

  assign dh_midstate_in    = midstate_r;
  assign core_active       = busy;

  // Would nonce_r + nonce_step_r overflow the 32-bit nonce field?
  logic [32:0] next_nonce_wide;
  assign next_nonce_wide = {1'b0, nonce_r} + {1'b0, nonce_step_r};

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state_r          <= ST_IDLE;
      busy             <= 1'b0;
      found            <= 1'b0;
      found_nonce      <= '0;
      found_hash       <= '0;
      nonce_exhausted  <= 1'b0;
      hashes_completed <= '0;
      dh_start         <= 1'b0;
      dh_use_midstate  <= 1'b0;
      header_block1_r  <= '0;
      header_tail3_r   <= '0;
      nonce_r          <= '0;
      nonce_step_r     <= '0;
      target_r         <= '0;
      midstate_r       <= '0;
    end else begin
      dh_start        <= 1'b0;  // one-cycle pulse by default
      found           <= 1'b0;
      nonce_exhausted <= 1'b0;

      unique case (state_r)
        ST_IDLE: begin
          if (job_valid) begin
            header_block1_r  <= header_block1;
            header_tail3_r   <= header_tail3;
            nonce_r          <= nonce_init;
            nonce_step_r     <= nonce_step;
            target_r         <= target;
            hashes_completed <= '0;
            busy             <= 1'b1;
            if (midstate_valid) begin
              midstate_r      <= midstate_load;
              dh_use_midstate <= 1'b1;
              state_r         <= ST_SEARCH;
            end else begin
              dh_use_midstate <= 1'b0;
              state_r         <= ST_FIRST;
            end
            dh_start <= 1'b1;
          end
        end

        ST_FIRST: begin
          if (dh_midstate_out_valid) begin
            midstate_r <= dh_midstate_out;
          end
          if (stop) begin
            state_r <= ST_IDLE;
            busy    <= 1'b0;
          end else if (dh_done) begin
            hashes_completed <= hashes_completed + 32'd1;
            if (meets) begin
              found       <= 1'b1;
              found_nonce <= nonce_r;
              found_hash  <= dh_pow_hash;
              busy        <= 1'b0;
              state_r     <= ST_IDLE;
            end else if (next_nonce_wide[32]) begin
              // overflow: this trial's nonce was the last usable one
              nonce_exhausted <= 1'b1;
              busy            <= 1'b0;
              state_r         <= ST_IDLE;
            end else begin
              nonce_r         <= next_nonce_wide[31:0];
              dh_use_midstate <= 1'b1;
              dh_start        <= 1'b1;
              state_r         <= ST_SEARCH;
            end
          end
        end

        ST_SEARCH: begin
          if (stop) begin
            state_r <= ST_IDLE;
            busy    <= 1'b0;
          end else if (dh_done) begin
            hashes_completed <= hashes_completed + 32'd1;
            if (meets) begin
              found       <= 1'b1;
              found_nonce <= nonce_r;
              found_hash  <= dh_pow_hash;
              busy        <= 1'b0;
              state_r     <= ST_IDLE;
            end else if (next_nonce_wide[32]) begin
              nonce_exhausted <= 1'b1;
              busy            <= 1'b0;
              state_r         <= ST_IDLE;
            end else begin
              nonce_r  <= next_nonce_wide[31:0];
              dh_start <= 1'b1;
              // stays in ST_SEARCH
            end
          end
        end

        default: state_r <= ST_IDLE;
      endcase
    end
  end

endmodule : hash_core
