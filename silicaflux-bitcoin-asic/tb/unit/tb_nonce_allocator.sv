// tb_nonce_allocator.sv -- self-contained testbench for nonce_allocator.sv.
//
// Unlike the SHA-256 modules, nonce_allocator's correctness is pure
// arithmetic (no hashing), so this testbench computes expected values
// inline rather than cross-checking against the Python golden model, and
// additionally builds each core's full multi-round nonce sequence and
// checks for duplicates directly -- both within one NUM_CORES/parameter
// setting and (via `-P` override from scripts/run_iverilog.sh) across
// several NUM_CORES values, including a wraparound case near the 32-bit
// nonce space boundary.
`timescale 1ns/1ps

module tb_nonce_allocator #(parameter int NUM_CORES = 8);
  localparam int NONCE_WIDTH = 32;
  localparam int ROUNDS = 6;

  logic [NONCE_WIDTH-1:0] nonce_start, nonce_stride;
  logic [NUM_CORES*NONCE_WIDTH-1:0] init_flat;
  logic [NONCE_WIDTH-1:0] step;

  nonce_allocator #(.NUM_CORES(NUM_CORES), .NONCE_WIDTH(NONCE_WIDTH)) dut (
    .nonce_start(nonce_start), .nonce_stride(nonce_stride),
    .core_nonce_init_flat(init_flat), .core_nonce_step(step)
  );

  int errors;

  function automatic logic [NONCE_WIDTH-1:0] get_init(input int i);
    get_init = init_flat[(NUM_CORES-i)*NONCE_WIDTH-1 -: NONCE_WIDTH];
  endfunction

  task automatic check_case(input logic [31:0] ns, input logic [31:0] nstride);
    bit [31:0] seen_q[$];
    bit dup_found;
    logic [31:0] expect_step;
    nonce_start = ns; nonce_stride = nstride;
    #1;
    expect_step = nstride * NUM_CORES;
    if (step !== expect_step) begin
      errors++;
      $display("[FAIL] step mismatch: start=%0d stride=%0d got=%0d want=%0d", ns, nstride, step, expect_step);
    end
    seen_q.delete();
    dup_found = 0;
    for (int i = 0; i < NUM_CORES; i++) begin
      logic [31:0] init_i, expect_i;
      init_i = get_init(i);
      expect_i = ns + nstride * i;
      if (init_i !== expect_i) begin
        errors++;
        $display("[FAIL] init[%0d] mismatch: start=%0d stride=%0d got=%0d want=%0d", i, ns, nstride, init_i, expect_i);
      end
      for (int r = 0; r < ROUNDS; r++) begin
        logic [31:0] val;
        bit found_here;
        val = init_i + step * r;
        found_here = 0;
        foreach (seen_q[k]) if (seen_q[k] == val) found_here = 1;
        if (found_here) dup_found = 1;
        seen_q.push_back(val);
      end
    end
    if (dup_found) begin
      errors++;
      $display("[FAIL] duplicate nonce found: start=%0d stride=%0d NUM_CORES=%0d ROUNDS=%0d", ns, nstride, NUM_CORES, ROUNDS);
    end
  endtask

  initial begin
    errors = 0;
    check_case(32'd0, 32'd1);
    check_case(32'd1000, 32'd1);
    check_case(32'hFFFFFFF0, 32'd1);   // near-overflow wraparound
    check_case(32'd0, 32'd3);
    check_case(32'd42, 32'd7);
    check_case(32'hDEADBEEF, 32'd5);

    if (errors == 0)
      $display("[PASS] tb_nonce_allocator(NUM_CORES=%0d): init/step/no-duplicate checks all passed (6 scenarios x %0d rounds x %0d cores)",
                NUM_CORES, ROUNDS, NUM_CORES);
    else
      $display("[FAIL] tb_nonce_allocator(NUM_CORES=%0d): %0d errors", NUM_CORES, errors);
    $finish;
  end
endmodule : tb_nonce_allocator
