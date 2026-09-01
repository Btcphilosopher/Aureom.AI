// sha256_double_hash.sv -- Bitcoin's SHA256(SHA256(header)) primitive,
// with midstate reuse (section 14) and constant-tied SHA-256 padding
// (section 13 "double-SHA optimisation").
//
// A full 80-byte header takes THREE 64-byte block compressions:
//   block1: header[0:64)  (version+prev_hash+merkle_root[0:28)), from IV
//   block2: header[64:80) + SHA-256 padding, from block1's output state
//   digest: SHA256(header) result + SHA-256 padding, from IV
// block1 only depends on fields that are constant for an entire mining
// round (nonce is NOT in it), so its result -- the "midstate" -- can be
// computed once per job and reused for every nonce trial: feed
// use_midstate=1 with midstate_in = that cached value, and this module
// does only block2+digest (2 compressions instead of 3) per hash
// attempt. That is the actual mechanism behind section 14's
// midstate_load/midstate_valid interface; see hash_core.sv for the
// per-job cache.
//
// Constant-tied padding (section 13): SHA-256 padding is a pure function
// of message LENGTH, and both remaining messages here have a fixed
// length (the 80-byte header, and the 32-byte first-pass digest) for
// every single hash this design will ever compute. So block2's words
// W[4..15] and the digest block's words W[8..15] are hardwired literals
// below, not signals loaded from any register or port -- there is
// nothing for a nonce-search sweep to toggle in those bits, and
// downstream synthesis constant-propagation can fold away whatever
// message-schedule/round logic depends only on them. We have NOT
// hand-derived the resulting reduced boolean equations (that is a
// synthesis-tool job, quantified only by an actual synthesis run -- see
// reports/ and docs/architecture.md section 13); what we guarantee here
// is functional correctness of the tie-off, verified against the Python
// golden model in tb/integration/tb_sha256_double_hash.sv.
//
// header_block1 / header_tail4 byte order: exactly the 80-byte Bitcoin
// header wire serialization (see python/silicaflux_bitcoin/reference/
// block_header.py), split as header_block1 = header[0:64) (big-endian
// 32-bit words per FIPS 180-4 loading) and header_tail4 = header[64:80)
// as 4 big-endian 32-bit words {merkle_tail, ntime, nbits, nonce}.
module sha256_double_hash (
  input  logic         clk,
  input  logic         rst_n,

  input  logic          start,          // pulse: begin: consumes the 4 inputs below
  input  logic           use_midstate,   // 1 = skip block1, start from midstate_in
  input  logic [255:0]   midstate_in,    // valid when use_midstate=1
  input  logic [511:0]   header_block1,  // valid when use_midstate=0: header[0:64)
  input  logic [127:0]   header_tail4,   // header[64:80): {merkle_tail,ntime,nbits,nonce}

  output logic            busy,
  output logic            done,           // one-cycle pulse; pow_hash valid this cycle and held
  output logic [255:0]    pow_hash,       // SHA256(SHA256(header)), internal byte order

  output logic             midstate_out_valid,  // one-cycle pulse when a fresh midstate is computed
  output logic [255:0]     midstate_out          // block1's output state (== the reusable midstate)
);

  localparam logic [255:0] IV = { sha256_pkg::H0_0, sha256_pkg::H0_1, sha256_pkg::H0_2, sha256_pkg::H0_3,
                                   sha256_pkg::H0_4, sha256_pkg::H0_5, sha256_pkg::H0_6, sha256_pkg::H0_7 };

  typedef enum logic [1:0] { ST_IDLE, ST_BLOCK1, ST_BLOCK2, ST_DIGEST } state_e;
  state_e state_r;

  logic         use_midstate_r;
  logic [127:0] header_tail4_r;
  logic [511:0] header_block1_r;
  logic [255:0] midstate_r;
  logic [255:0] pass1_r;

  logic         comp_start_r;
  logic [255:0] comp_state_in;
  logic [511:0] comp_block;
  logic         comp_busy, comp_done;
  logic [255:0] comp_state_out;

  sha256_compressor u_comp (
    .clk(clk), .rst_n(rst_n), .start(comp_start_r),
    .state_in(comp_state_in), .block_bits(comp_block),
    .busy(comp_busy), .done(comp_done), .state_out(comp_state_out)
  );

  // Combinational operand mux: valid whenever `state_r` names the block
  // currently in flight, one cycle *after* the FSM below registers the
  // fields it depends on (header_block1_r/header_tail4_r/midstate_r/pass1_r).
  always_comb begin
    comp_state_in = '0;
    comp_block    = '0;
    unique case (state_r)
      ST_BLOCK1: begin
        comp_state_in = IV;
        comp_block    = header_block1_r;
      end
      ST_BLOCK2: begin
        comp_state_in = midstate_r;
        // header_tail4_r = {merkle_tail, ntime, nbits, nonce}; SHA-256 pad
        // for an 80-byte message: 0x80, 39 zero bytes, then the 64-bit
        // big-endian bit length 640 = 0x0000000000000280.
        comp_block    = { header_tail4_r, 32'h8000_0000, 320'h0, 32'h0000_0280 };
      end
      ST_DIGEST: begin
        comp_state_in = IV;
        // pass1_r is the 32-byte first-pass digest; SHA-256 pad for a
        // 32-byte message: 0x80, 27 zero bytes, then bit length 256 = 0x100.
        comp_block    = { pass1_r, 32'h8000_0000, 192'h0, 32'h0000_0100 };
      end
      default: ;
    endcase
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state_r            <= ST_IDLE;
      busy               <= 1'b0;
      done               <= 1'b0;
      comp_start_r       <= 1'b0;
      midstate_out_valid <= 1'b0;
      use_midstate_r     <= 1'b0;
      header_tail4_r     <= '0;
      header_block1_r    <= '0;
      midstate_r         <= '0;
      pass1_r            <= '0;
      pow_hash           <= '0;
      midstate_out       <= '0;
    end else begin
      comp_start_r       <= 1'b0;  // default: one-cycle pulse only
      done               <= 1'b0;
      midstate_out_valid <= 1'b0;

      unique case (state_r)
        ST_IDLE: begin
          if (start) begin
            use_midstate_r  <= use_midstate;
            header_tail4_r  <= header_tail4;
            header_block1_r <= header_block1;
            busy            <= 1'b1;
            if (use_midstate) begin
              midstate_r <= midstate_in;
              state_r    <= ST_BLOCK2;
            end else begin
              state_r    <= ST_BLOCK1;
            end
            comp_start_r <= 1'b1;
          end
        end

        ST_BLOCK1: begin
          if (comp_done) begin
            midstate_r         <= comp_state_out;
            midstate_out       <= comp_state_out;
            midstate_out_valid <= 1'b1;
            state_r            <= ST_BLOCK2;
            comp_start_r       <= 1'b1;
          end
        end

        ST_BLOCK2: begin
          if (comp_done) begin
            pass1_r      <= comp_state_out;
            state_r      <= ST_DIGEST;
            comp_start_r <= 1'b1;
          end
        end

        ST_DIGEST: begin
          if (comp_done) begin
            pow_hash <= comp_state_out;
            done     <= 1'b1;
            busy     <= 1'b0;
            state_r  <= ST_IDLE;
          end
        end

        default: state_r <= ST_IDLE;
      endcase
    end
  end

endmodule : sha256_double_hash
