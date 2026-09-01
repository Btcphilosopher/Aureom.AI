// miner_controller.sv -- top-level job control FSM (section 11).
//
// States: IDLE, LOAD_HEADER, INITIALISE, ARMED, HASH, REPORT, STOP, ERROR.
// This is the section-11 list (IDLE/LOAD_HEADER/INITIALISE/HASH/COMPARE/
// NEXT_NONCE/REPORT/STOP/ERROR) with one documented adaptation: COMPARE
// and NEXT_NONCE are not separate OUTER states here because that
// hash->compare->next-nonce loop already exists as real hardware one
// level down, running every cycle inside hash_core_array/hash_core
// (verified independently in tb/integration/tb_hash_core.sv and tb/
// system/tb_hash_core_array.sv) -- this controller's single HASH state
// is "the array is running that loop"; folding COMPARE/NEXT_NONCE in
// here as their own outer states would just add wait-states around a
// loop this FSM does not itself drive cycle-by-cycle. ARMED is a small,
// clearly-labelled addition (a header can be LOADed and INITIALISEd
// before the host asserts `start`) rather than silently starting the
// search the instant a header is parsed.
//
// Header loading interface (section 12): generic valid/ready + a single
// data bus, no assumed physical transport.
//   header_data[607:96] = header_block1 (version+prev_hash+merkle_root[0:28))
//   header_data[95:0]   = header_tail3  (merkle_root[28:32)+ntime+nbits)
// both in the same "raw wire bytes as SHA-256 big-endian words" packing
// used throughout rtl/ (see docs/sha256_spec_notes.md). The nonce field
// is deliberately NOT part of header_data -- the search range is
// configured separately via nonce_start_cfg/nonce_stride_cfg, matching
// how a real control plane assigns nonce work independently of the raw
// header bytes.
//
// Error handling (section 34): ERROR is entered when nbits_expand
// produces target==0 for the loaded header's nBits (a malformed/
// impossible difficulty encoding) -- error_code 4'd1, "invalid target".
// Deterministic, decoded by tb/system/tb_miner_top.sv.
module miner_controller #(
  parameter int NUM_CORES = 4
) (
  input  logic         clk,
  input  logic         rst_n,

  // Header loading interface.
  input  logic          header_valid,
  output logic           header_ready,
  input  logic [607:0]   header_data,
  input  logic            start,
  input  logic            stop,

  input  logic [31:0]     nonce_start_cfg,
  input  logic [31:0]     nonce_stride_cfg,

  output logic             busy,
  output logic             found,
  output logic [31:0]      found_nonce,
  output logic [255:0]     found_hash,
  output logic [31:0]      found_core_id,
  output logic              exhausted,
  output logic              error,
  output logic [3:0]        error_code,
  output logic [3:0]        state_out,

  // hash_core_array interface.
  output logic              arr_job_valid,
  output logic [511:0]      arr_header_block1,
  output logic [95:0]       arr_header_tail3,
  output logic [31:0]       arr_nonce_start,
  output logic [31:0]       arr_nonce_stride,
  output logic [255:0]      arr_target,
  output logic               arr_stop,
  input  logic                arr_any_busy,
  input  logic                arr_found,
  input  logic [31:0]         arr_found_nonce,
  input  logic [255:0]        arr_found_hash,
  input  logic [31:0]         arr_found_core_id,
  input  logic                 arr_search_exhausted
);

  typedef enum logic [3:0] {
    ST_IDLE        = 4'd0,
    ST_LOAD_HEADER = 4'd1,
    ST_INITIALISE  = 4'd2,
    ST_ARMED       = 4'd3,
    ST_HASH        = 4'd4,
    ST_REPORT      = 4'd5,
    ST_STOP        = 4'd6,
    ST_ERROR       = 4'd7
  } state_e;
  state_e state_r;
  assign state_out = state_r;

  logic [511:0] block1_r;
  logic [95:0]  tail3_r;
  logic [31:0]  nbits_wire_word, nbits_numeric;
  logic [255:0] target_comb, target_r;

  assign nbits_wire_word = tail3_r[31:0];
  // Byte-swap: tail3_r[31:0] holds nBits' raw wire bytes loaded as a
  // big-endian hashing word (see header comment); nbits_expand wants the
  // true little-endian-serialized NUMERIC value -- the same reversal
  // hash_core.sv applies to the nonce, in the opposite direction.
  assign nbits_numeric = { nbits_wire_word[7:0], nbits_wire_word[15:8],
                            nbits_wire_word[23:16], nbits_wire_word[31:24] };

  nbits_expand u_nbits (.bits(nbits_numeric), .target(target_comb));

  assign arr_header_block1 = block1_r;
  assign arr_header_tail3  = tail3_r;
  assign arr_target        = target_r;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state_r         <= ST_IDLE;
      header_ready    <= 1'b1;
      busy            <= 1'b0;
      found           <= 1'b0;
      exhausted       <= 1'b0;
      error           <= 1'b0;
      error_code      <= '0;
      found_nonce     <= '0;
      found_hash      <= '0;
      found_core_id   <= '0;
      block1_r        <= '0;
      tail3_r         <= '0;
      target_r        <= '0;
      arr_job_valid   <= 1'b0;
      arr_nonce_start <= '0;
      arr_nonce_stride<= '0;
      arr_stop        <= 1'b0;
    end else begin
      arr_job_valid <= 1'b0;
      found         <= 1'b0;
      exhausted     <= 1'b0;
      arr_stop      <= 1'b0;

      unique case (state_r)
        ST_IDLE: begin
          header_ready <= 1'b1;
          error        <= 1'b0;
          if (header_valid) begin
            block1_r     <= header_data[607:96];
            tail3_r      <= header_data[95:0];
            header_ready <= 1'b0;
            busy         <= 1'b1;
            state_r      <= ST_LOAD_HEADER;
          end
        end

        ST_LOAD_HEADER: begin
          // One-cycle transitional state: registers above are valid now;
          // nbits_numeric/target_comb are already combinationally derived.
          state_r <= ST_INITIALISE;
        end

        ST_INITIALISE: begin
          target_r <= target_comb;
          if (target_comb == 256'd0) begin
            error      <= 1'b1;
            error_code <= 4'd1;  // invalid target
            busy       <= 1'b0;
            state_r    <= ST_ERROR;
          end else begin
            arr_nonce_start  <= nonce_start_cfg;
            arr_nonce_stride <= nonce_stride_cfg;
            state_r          <= ST_ARMED;
          end
        end

        ST_ARMED: begin
          if (stop) begin
            busy    <= 1'b0;
            state_r <= ST_IDLE;
          end else if (start) begin
            arr_job_valid <= 1'b1;
            state_r       <= ST_HASH;
          end
        end

        ST_HASH: begin
          if (stop) begin
            arr_stop <= 1'b1;
            state_r  <= ST_STOP;
          end else if (arr_found) begin
            found         <= 1'b1;
            found_nonce   <= arr_found_nonce;
            found_hash    <= arr_found_hash;
            found_core_id <= arr_found_core_id;
            busy          <= 1'b0;
            state_r       <= ST_REPORT;
          end else if (arr_search_exhausted) begin
            exhausted <= 1'b1;
            busy      <= 1'b0;
            state_r   <= ST_REPORT;
          end
        end

        ST_REPORT: begin
          // Results are held on found_nonce/found_hash/found_core_id
          // (not re-cleared here) for the host to sample; one cycle
          // later we're ready for the next header.
          state_r <= ST_IDLE;
        end

        ST_STOP: begin
          busy    <= 1'b0;
          state_r <= ST_IDLE;
        end

        ST_ERROR: begin
          // Sticky until the host loads a new header -- handled exactly
          // like ST_IDLE's own header_valid branch (not a bounce through
          // IDLE first, which would need a second, separate header_valid
          // pulse once header_ready finally read 1).
          header_ready <= 1'b1;
          if (header_valid) begin
            block1_r     <= header_data[607:96];
            tail3_r      <= header_data[95:0];
            header_ready <= 1'b0;
            busy         <= 1'b1;
            error        <= 1'b0;
            state_r      <= ST_LOAD_HEADER;
          end
        end

        default: state_r <= ST_IDLE;
      endcase
    end
  end

endmodule : miner_controller
