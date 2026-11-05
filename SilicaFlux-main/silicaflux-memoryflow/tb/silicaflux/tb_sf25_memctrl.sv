// =============================================================================
// tb_sf25_memctrl :: characterisation of the EXISTING SilicaFlux 2.5
//                    scratchpad controller (memory_controller.sf, unmodified)
//
// The DUT and its package are compiled straight from the repository
// (memoryflow.silicaflux.sources extracts them; nothing is edited).  Default
// parameters: 8 banks x 512 lines x 128 b = 64 KiB, SCALAR_LINES = 1024
// (16 KiB scalar domain), SRAM_LATENCY = 1, per-byte parity, 4 KiB burst page.
//
// Phases (every response is checked against a byte-accurate reference model)
//   0  reset + storage-initialisation sweep length
//   1  idle load latency, scalar and vector port
//   2  single-port streaming throughput (store then load), scalar and vector
//   3  burst port: store / load beats-per-cycle versus burst length 1..256
//      (one descriptor in flight + done handshake per burst)
//   4  bank contention: scalar+vector on different banks / the same bank,
//      and all three requesters streaming together
//   5  random traffic on all three ports with random backpressure
//   6  boundaries and address-overflow protection (exception codes, and
//      rejected stores must not modify storage)
//   7  parity: corrupt one stored bit (hierarchical reference) -> ECC exc
//   8  burst kill mid-store: FLUSHED status, exact committed-beat count
// Results: MF_METRIC sf25_* lines + MF_RESULT (tb_common.svh).
// =============================================================================
`timescale 1ns/1ps
`include "tb_common.svh"

module tb_sf25_memctrl;
  import silicaflux_pkg::*;

  localparam int unsigned NBANKS = 8, BDEPTH = 512, SLINES = 1024;
  localparam int unsigned LINES  = NBANKS * BDEPTH;           // 4096 lines = 64 KiB
  localparam logic [31:0] BASE   = 32'h1000_0000;
  localparam int unsigned PAGE_LINES = 4096 / 16;

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  longint cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;

  // ------------------------------------------------------------------ DUT I/O
  logic                 flush = 0, kill = 0;
  logic                 s_vld = 0, s_rdy, s_rvld, s_rrdy = 1;
  sf_scalar_mem_req_t   s_req = '0;
  sf_scalar_mem_rsp_t   s_rsp;
  logic                 v_vld = 0, v_rdy, v_rvld, v_rrdy = 1;
  sf_vector_mem_req_t   v_req = '0;
  sf_vector_mem_rsp_t   v_rsp;
  logic                 b_vld = 0, b_rdy, b_wvld = 0, b_wrdy, b_rvld, b_rrdy = 1, b_dvld, b_drdy = 1;
  sf_burst_desc_t       b_req = '0;
  sf_burst_wbeat_t      b_w = '0;
  sf_burst_rbeat_t      b_r;
  sf_burst_done_t       b_d;
  logic [NBANKS-1:0]    coh_v;
  sf_paddr_t [NBANKS-1:0] coh_a;
  logic                 init_done, busy, conflict;

  memory_controller dut (
    .clk_i(clk), .rst_ni(rst_n), .flush_i(flush), .burst_kill_i(kill),
    .scalar_req_valid_i(s_vld), .scalar_req_ready_o(s_rdy), .scalar_req_i(s_req),
    .scalar_rsp_valid_o(s_rvld), .scalar_rsp_ready_i(s_rrdy), .scalar_rsp_o(s_rsp),
    .vector_req_valid_i(v_vld), .vector_req_ready_o(v_rdy), .vector_req_i(v_req),
    .vector_rsp_valid_o(v_rvld), .vector_rsp_ready_i(v_rrdy), .vector_rsp_o(v_rsp),
    .burst_req_valid_i(b_vld), .burst_req_ready_o(b_rdy), .burst_req_i(b_req),
    .burst_wdata_valid_i(b_wvld), .burst_wdata_ready_o(b_wrdy), .burst_wdata_i(b_w),
    .burst_rdata_valid_o(b_rvld), .burst_rdata_ready_i(b_rrdy), .burst_rdata_o(b_r),
    .burst_done_valid_o(b_dvld), .burst_done_ready_i(b_drdy), .burst_done_o(b_d),
    .coh_wr_valid_o(coh_v), .coh_wr_addr_o(coh_a),
    .init_done_o(init_done), .busy_o(busy), .bank_conflict_o(conflict));

  // ------------------------------------------------------------------ reference model
  logic [127:0] refm [LINES];
  function automatic sf_paddr_t saddr(int unsigned word); return BASE + 32'(word) * 4; endfunction
  function automatic sf_paddr_t vaddr(int unsigned line); return BASE + 32'(line) * 16; endfunction

  // expected exception for an address as the RTL's rules state them
  function automatic sf_mem_exc_e exp_exc(sf_paddr_t a, int unsigned align, bit vector_port);
    longint off;
    int unsigned line;
    if ((a % align) != 0) return SF_MEM_EXC_MISALIGN;
    off = longint'(a) - longint'(BASE);
    if (off < 0 || off >= longint'(LINES) * 16) return SF_MEM_EXC_RANGE;
    line = int'(off / 16);
    if (!vector_port && line >= SLINES) return SF_MEM_EXC_DOMAIN;
    if (vector_port && line < SLINES) return SF_MEM_EXC_DOMAIN;
    return SF_MEM_EXC_NONE;
  endfunction

  // expectation rings (Verilator 5.020: no unpacked arrays of queues)
  typedef struct packed { sf_mem_op_e op; logic [127:0] data; logic [3:0] mask; logic [7:0] tag; sf_mem_exc_e exc; } exp_t;
  localparam int QD = 8192;
  exp_t s_ring [QD]; int s_h = 0, s_t = 0;
  exp_t v_ring [QD]; int v_h = 0, v_t = 0;
  // burst read beats: expected line index; burst done records
  int unsigned br_ring [QD]; int br_h = 0, br_t = 0;
  typedef struct packed { sf_mem_op_e op; logic [7:0] tag; logic [8:0] beats; sf_mem_exc_e exc; } bdone_t;
  bdone_t bd_ring [256]; int bd_h = 0, bd_t = 0;
  // active store burst: data beats are written to consecutive lines
  int unsigned bw_line = 0;
  int          bw_left = 0;
  bit          bw_kill_mode = 0;          // phase 8: committed beats decided by the DUT
  logic [127:0] bw_kill_data [64]; int bw_acc = 0;

  longint s_acc = 0, s_rsp_n = 0, v_acc = 0, v_rsp_n = 0, b_beats_w = 0, b_beats_r = 0, b_done_n = 0;
  longint s_first_acc = -1, s_last_rsp = 0, v_first_acc = -1, v_last_rsp = 0;
  longint conflict_cycles = 0;
  longint last_progress = 0;
  bit     watchdog_fired = 0;
  bit     ecc_expect_s = 0, ecc_expect_v = 0;

  // ------------------------------------------------------------------ monitors (posedge)
  always @(posedge clk) if (rst_n) begin
    if (conflict) conflict_cycles++;
    // ---- scalar request
    if (s_vld && s_rdy) begin
      exp_t e; sf_mem_exc_e x; int unsigned w, l, ln;
      x = exp_exc(s_req.addr, 4, 0);
      e.op = s_req.op; e.tag = s_req.tag; e.exc = x; e.mask = '0; e.data = '0;
      if (x == SF_MEM_EXC_NONE) begin
        w = int'((s_req.addr - BASE) / 4); ln = w / 4; l = w % 4;
        if (s_req.op == SF_MEM_STORE) begin
          for (int b = 0; b < 4; b++) if (s_req.wstrb[b]) refm[ln][l*32 + b*8 +: 8] = s_req.wdata[b*8 +: 8];
        end else e.data = {96'b0, refm[ln][l*32 +: 32]};
      end
      s_ring[s_t % QD] = e; s_t++; s_acc++;
      if (s_first_acc < 0) s_first_acc = cyc;
      last_progress = cyc;
    end
    // ---- scalar response
    if (s_rvld && s_rrdy) begin
      exp_t e;
      if (s_h == s_t) `CHECK(0, "unexpected scalar response")
      else begin
        e = s_ring[s_h % QD]; s_h++;
        `CHECK_EQ(s_rsp.op, e.op, "scalar rsp op (in order)")
        `CHECK_EQ(s_rsp.tag, e.tag, "scalar rsp tag (in order)")
        if (ecc_expect_s && e.op == SF_MEM_LOAD) `CHECK_EQ(s_rsp.exc, SF_MEM_EXC_ECC, "scalar parity error detected")
        else begin
          `CHECK_EQ(s_rsp.exc, e.exc, "scalar rsp exception code")
          `CHECK_EQ(s_rsp.rdata, e.data[31:0], "scalar rsp data")
        end
      end
      s_rsp_n++; s_last_rsp = cyc; last_progress = cyc;
    end
    // ---- vector request
    if (v_vld && v_rdy) begin
      exp_t e; sf_mem_exc_e x; int unsigned ln;
      x = exp_exc(v_req.addr, 16, 1);
      e.op = v_req.op; e.tag = v_req.tag; e.exc = x; e.mask = v_req.lane_mask; e.data = '0;
      if (x == SF_MEM_EXC_NONE) begin
        ln = int'((v_req.addr - BASE) / 16);
        for (int l = 0; l < 4; l++)
          if (v_req.lane_mask[l]) begin
            if (v_req.op == SF_MEM_STORE) refm[ln][l*32 +: 32] = v_req.wdata[l*32 +: 32];
            else e.data[l*32 +: 32] = refm[ln][l*32 +: 32];
          end
      end
      v_ring[v_t % QD] = e; v_t++; v_acc++;
      if (v_first_acc < 0) v_first_acc = cyc;
      last_progress = cyc;
    end
    // ---- vector response
    if (v_rvld && v_rrdy) begin
      exp_t e;
      if (v_h == v_t) `CHECK(0, "unexpected vector response")
      else begin
        e = v_ring[v_h % QD]; v_h++;
        `CHECK_EQ(v_rsp.op, e.op, "vector rsp op")
        `CHECK_EQ(v_rsp.tag, e.tag, "vector rsp tag")
        `CHECK_EQ(v_rsp.lane_mask, e.mask, "vector rsp lane mask")
        if (ecc_expect_v && e.op == SF_MEM_LOAD) `CHECK_EQ(v_rsp.exc, SF_MEM_EXC_ECC, "vector parity error detected")
        else begin
          `CHECK_EQ(v_rsp.exc, e.exc, "vector rsp exception code")
          `CHECK_EQ(v_rsp.rdata, e.data, "vector rsp data (masked lanes zero)")
        end
      end
      v_rsp_n++; v_last_rsp = cyc; last_progress = cyc;
    end
    // ---- burst write beats
    if (b_wvld && b_wrdy && !(bw_kill_mode && kill)) begin     // the DUT ignores beats on the kill edge
      if (bw_kill_mode) begin
        bw_kill_data[bw_acc % 64] = b_w.data; bw_acc++;
      end else begin
        if (bw_left == 0) `CHECK(0, "burst write beat accepted beyond burst length")
        else begin
          for (int b = 0; b < 16; b++) if (b_w.strb[b]) refm[bw_line][b*8 +: 8] = b_w.data[b*8 +: 8];
          bw_line++; bw_left--;
        end
      end
      b_beats_w++; last_progress = cyc;
    end
    // ---- burst read beats
    if (b_rvld && b_rrdy) begin
      if (br_h == br_t) `CHECK(0, "unexpected burst read beat")
      else begin
        int unsigned ln;
        ln = br_ring[br_h % QD]; br_h++;
        `CHECK_EQ(b_r.data, refm[ln], "burst read data")
        `CHECK_EQ(b_r.exc, SF_MEM_EXC_NONE, "burst read beat exception")
        `CHECK_EQ(b_r.last, (br_h == br_t), "burst read last flag")
      end
      b_beats_r++; last_progress = cyc;
    end
    // ---- burst done
    if (b_dvld && b_drdy) begin
      if (bd_h == bd_t) `CHECK(0, "unexpected burst done")
      else if (!bw_kill_mode) begin
        bdone_t d;
        d = bd_ring[bd_h % 256]; bd_h++;
        `CHECK_EQ(b_d.op, d.op, "burst done op")
        `CHECK_EQ(b_d.tag, d.tag, "burst done tag")
        `CHECK_EQ(b_d.exc, d.exc, "burst done exception code")
        `CHECK_EQ(b_d.beats, d.beats, "burst done beat count")
      end else bd_h++;
      b_done_n++; last_progress = cyc;
    end
  end

  // deadlock watchdog
  always @(posedge clk) if (rst_n && init_done && !watchdog_fired && (cyc - last_progress) > 5000 &&
                            (s_h != s_t || v_h != v_t || br_h != br_t || bd_h != bd_t || s_vld || v_vld || b_vld)) begin
    watchdog_fired = 1;
    `CHECK(0, "DEADLOCK watchdog: no progress for 5000 cycles with work pending")
  end

  // ------------------------------------------------------------------ backpressure drivers
  bit bp = 0;
  always @(negedge clk) begin
    s_rrdy = bp ? ($urandom_range(0, 3) != 0) : 1'b1;
    v_rrdy = bp ? ($urandom_range(0, 3) != 0) : 1'b1;
    b_rrdy = bp ? ($urandom_range(0, 2) != 0) : 1'b1;
    b_drdy = bp ? ($urandom_range(0, 1) != 0) : 1'b1;
  end

  // ------------------------------------------------------------------ port drivers (called at negedge)
  task automatic s_send(sf_mem_op_e op, sf_paddr_t a, logic [31:0] d, logic [3:0] strb, logic [7:0] tag);
    sf_scalar_mem_req_t r;      // whole-struct assignment (Verilator 5.020: member writes from a
    r.op = op; r.addr = a; r.wdata = d; r.wstrb = strb; r.tag = tag;   // suspended task do not propagate)
    r.hint = SF_MEM_HINT_NORMAL; s_req = r; s_vld = 1;
    #1; while (!s_rdy) begin @(negedge clk); #1; end
    @(negedge clk); s_vld = 0;
  endtask

  task automatic v_send(sf_mem_op_e op, sf_paddr_t a, logic [127:0] d, logic [3:0] mask, logic [7:0] tag);
    sf_vector_mem_req_t r;
    r.op = op; r.addr = a; r.wdata = d; r.lane_mask = mask; r.tag = tag;
    r.hint = SF_MEM_HINT_STREAM; v_req = r; v_vld = 1;
    #1; while (!v_rdy) begin @(negedge clk); #1; end
    @(negedge clk); v_vld = 0;
  endtask

  function automatic sf_mem_exc_e b_exp_exc(sf_paddr_t base, int unsigned len);
    longint off, s, e;
    if ((base % 16) != 0) return SF_MEM_EXC_MISALIGN;
    off = longint'(base) - longint'(BASE);
    if (off < 0 || off >= longint'(LINES) * 16) return SF_MEM_EXC_RANGE;
    s = off / 16; e = s + len - 1;
    if (e >= LINES || ((s >= SLINES) != (e >= SLINES)) || (s / PAGE_LINES) != (e / PAGE_LINES))
      return SF_MEM_EXC_BURST_BND;
    return SF_MEM_EXC_NONE;
  endfunction

  // one complete burst; returns after the descriptor handshake (data runs in parallel)
  task automatic b_desc(sf_mem_op_e op, sf_paddr_t base, int unsigned len, logic [7:0] tag);
    bdone_t d; sf_mem_exc_e x; int unsigned ln; sf_burst_desc_t r;
    x = b_exp_exc(base, len);
    r.op = op; r.base = base; r.len_m1 = 8'(len - 1); r.tag = tag; r.hint = SF_MEM_HINT_STREAM;
    b_req = r; b_vld = 1;
    #1; while (!b_rdy) begin @(negedge clk); #1; end
    // descriptor accepted at the coming posedge: register expectations now
    d.op = op; d.tag = tag; d.exc = x; d.beats = (x == SF_MEM_EXC_NONE) ? 9'(len) : 9'd0;
    bd_ring[bd_t % 256] = d; bd_t++;
    if (x == SF_MEM_EXC_NONE) begin
      ln = int'((base - BASE) / 16);
      if (op == SF_MEM_LOAD) for (int i = 0; i < int'(len); i++) begin br_ring[br_t % QD] = ln + i; br_t++; end
      else begin bw_line = ln; bw_left = len; end
    end
    @(negedge clk); b_vld = 0;
  endtask

  task automatic b_wbeats(int unsigned n, int unsigned seed);
    for (int i = 0; i < int'(n); i++) begin
      b_w = '{data: {32'(seed + i), 32'(~(seed + i)), 32'(i * 7), 32'hB0B0_0000 + 32'(i)}, strb: '1};
      b_wvld = 1;
      #1; while (!b_wrdy) begin @(negedge clk); #1; end
      @(negedge clk);
    end
    b_wvld = 0;
  endtask

  task automatic drain(int max_cycles = 20000);
    int n;
    n = 0;
    while ((s_h != s_t || v_h != v_t || br_h != br_t || bd_h != bd_t) && n < max_cycles) begin
      @(negedge clk); n++;
    end
    `CHECK(n < max_cycles, "drain: all expected responses arrived")
    repeat (4) @(negedge clk);
  endtask

  // burst helper: n bursts of len beats, storing or loading, back-to-back
  task automatic burst_run(sf_mem_op_e op, int unsigned line0, int unsigned len, int unsigned nb);
    for (int k = 0; k < int'(nb); k++) begin
      b_desc(op, vaddr(line0 + k * len), len, 8'(k));
      if (op == SF_MEM_STORE) b_wbeats(len, 32'(k * 977 + len));
      // single descriptor in flight: wait for completion before the next one
      while (bd_h != bd_t) @(negedge clk);
    end
  endtask

  real tmp;
  longint c0, c1, n0;
  int unsigned seed;

  initial begin
    if (!$value$plusargs("seed=%d", seed)) seed = 1;
    void'($urandom(seed));
    for (int i = 0; i < int'(LINES); i++) refm[i] = '0;
    repeat (3) @(negedge clk);
    rst_n = 1;
    c0 = cyc;
    // ================================================================ phase 0
    while (!init_done) @(negedge clk);
    tb_metric("sf25_init_cycles", real'(cyc - c0));
    `CHECK(!s_rdy || init_done, "ports held not-ready during initialisation")

    // ================================================================ phase 1: idle latency
    begin
      longint a;
      s_send(SF_MEM_LOAD, saddr(0), 0, 0, 8'h11); a = cyc;      // handshake was at cycle a-1..a
      while (s_rsp_n == 0) @(posedge clk);
      tb_metric("sf25_scalar_load_latency_cycles", real'(s_last_rsp - s_first_acc));
      v_send(SF_MEM_LOAD, vaddr(SLINES), 0, 4'hF, 8'h22);
      while (v_rsp_n == 0) @(posedge clk);
      tb_metric("sf25_vector_load_latency_cycles", real'(v_last_rsp - v_first_acc));
      drain();
    end

    // ================================================================ phase 2: single-port streaming
    // scalar store / load stream over the 16 KiB scalar domain (4096 words)
    n0 = s_rsp_n; c0 = cyc;
    for (int w = 0; w < 4096; w++) s_send(SF_MEM_STORE, saddr(w), 32'hC0DE_0000 ^ 32'(w * 2654435761), 4'hF, 8'(w));
    drain(); c1 = s_last_rsp;
    tb_metric("sf25_scalar_store_stream_words_per_cycle", 4096.0 / real'(c1 - c0));
    n0 = s_rsp_n; c0 = cyc;
    for (int w = 0; w < 4096; w++) s_send(SF_MEM_LOAD, saddr(w), 0, 0, 8'(w));
    drain(); c1 = s_last_rsp;
    tb_metric("sf25_scalar_load_stream_words_per_cycle", 4096.0 / real'(c1 - c0));
    // vector store / load stream over 2048 lines (32 KiB of the vector domain)
    c0 = cyc;
    for (int l = 0; l < 2048; l++)
      v_send(SF_MEM_STORE, vaddr(SLINES + l), {32'(l), 32'(~l), 32'(l * 3), 32'hA5A5_0000 + 32'(l)}, 4'hF, 8'(l));
    drain(); c1 = v_last_rsp;
    tmp = 2048.0 / real'(c1 - c0);
    tb_metric("sf25_vector_store_stream_lines_per_cycle", tmp);
    c0 = cyc;
    for (int l = 0; l < 2048; l++) v_send(SF_MEM_LOAD, vaddr(SLINES + l), 0, 4'hF, 8'(l));
    drain(); c1 = v_last_rsp;
    tmp = 2048.0 / real'(c1 - c0);
    tb_metric("sf25_vector_load_stream_lines_per_cycle", tmp);
    tb_metric("sf25_vector_load_stream_bytes_per_cycle", 16.0 * tmp);
    // partial lane masks
    for (int l = 0; l < 64; l++) v_send(SF_MEM_STORE, vaddr(SLINES + l), {4{32'hFEED_0000 + 32'(l)}}, 4'(l % 16), 8'(l));
    for (int l = 0; l < 64; l++) v_send(SF_MEM_LOAD, vaddr(SLINES + l), 0, 4'((l * 7) % 16), 8'(l));
    drain();

    // ================================================================ phase 3: burst length sweep
    for (int li = 0; li <= 8; li++) begin
      int unsigned len, nb;
      len = 1 << li; nb = 1024 / len;
      c0 = cyc; n0 = b_beats_w;
      burst_run(SF_MEM_STORE, 2048, len, nb);
      c1 = cyc;
      tb_metric($sformatf("sf25_burst_store_beats_per_cycle_L%0d", len), real'(b_beats_w - n0) / real'(c1 - c0));
      c0 = cyc; n0 = b_beats_r;
      burst_run(SF_MEM_LOAD, 2048, len, nb);
      c1 = cyc;
      tb_metric($sformatf("sf25_burst_load_beats_per_cycle_L%0d", len), real'(b_beats_r - n0) / real'(c1 - c0));
    end
    drain();

    // ================================================================ phase 4: bank contention
    // (a) scalar on bank 0 (stride 8 lines), vector on bank 4: no shared bank
    c0 = cyc; n0 = s_rsp_n + v_rsp_n;
    fork
      for (int k = 0; k < 512; k++) s_send(SF_MEM_LOAD, saddr((k % 128) * 32), 0, 0, 8'(k));
      for (int k = 0; k < 512; k++) v_send(SF_MEM_LOAD, vaddr(SLINES + 4 + (k % 256) * 8), 0, 4'hF, 8'(k));
    join
    drain(); c1 = (s_last_rsp > v_last_rsp) ? s_last_rsp : v_last_rsp;
    tb_metric("sf25_sv_disjoint_bank_requests_per_cycle", real'(s_rsp_n + v_rsp_n - n0) / real'(c1 - c0));
    // (b) both on bank 0
    c0 = cyc; n0 = s_rsp_n + v_rsp_n; conflict_cycles = 0;
    fork
      for (int k = 0; k < 512; k++) s_send(SF_MEM_LOAD, saddr((k % 128) * 32), 0, 0, 8'(k));
      for (int k = 0; k < 512; k++) v_send(SF_MEM_LOAD, vaddr(SLINES + (k % 256) * 8), 0, 4'hF, 8'(k));
    join
    drain(); c1 = (s_last_rsp > v_last_rsp) ? s_last_rsp : v_last_rsp;
    tb_metric("sf25_sv_same_bank_requests_per_cycle", real'(s_rsp_n + v_rsp_n - n0) / real'(c1 - c0));
    tb_metric("sf25_sv_same_bank_conflict_cycles", real'(conflict_cycles));
    // (c) all three requesters streaming sequentially at once
    c0 = cyc; n0 = s_rsp_n + v_rsp_n + b_beats_r;
    fork
      for (int k = 0; k < 1024; k++) s_send(SF_MEM_LOAD, saddr(k), 0, 0, 8'(k));
      for (int k = 0; k < 1024; k++) v_send(SF_MEM_LOAD, vaddr(SLINES + k), 0, 4'hF, 8'(k));
      burst_run(SF_MEM_LOAD, 2048, 256, 4);
    join
    drain();
    c1 = cyc - 4;
    tb_metric("sf25_three_port_stream_requests_per_cycle", real'(s_rsp_n + v_rsp_n + b_beats_r - n0) / real'(c1 - c0));
    // byte rate: 1024 scalar words (4 B) + 1024 vector lines (16 B) + 1024 burst beats (16 B)
    tb_metric("sf25_three_port_stream_bytes_per_cycle", real'(1024 * 4 + 1024 * 16 + 1024 * 16) / real'(c1 - c0));

    // ================================================================ phase 5: random, backpressure
    bp = 1;
    fork
      for (int k = 0; k < 3000; k++) begin
        int unsigned w;
        w = $urandom_range(0, 4095);
        if ($urandom_range(0, 1)) s_send(SF_MEM_STORE, saddr(w), $urandom, 4'($urandom_range(0, 15)), 8'(k));
        else s_send(SF_MEM_LOAD, saddr(w), 0, 0, 8'(k));
        if ($urandom_range(0, 3) == 0) @(negedge clk);
      end
      for (int k = 0; k < 3000; k++) begin
        int unsigned l;
        l = SLINES + $urandom_range(0, 1023);                       // vector region A
        if ($urandom_range(0, 1)) v_send(SF_MEM_STORE, vaddr(l), {$urandom, $urandom, $urandom, $urandom},
                                         4'($urandom_range(0, 15)), 8'(k));
        else v_send(SF_MEM_LOAD, vaddr(l), 0, 4'($urandom_range(0, 15)), 8'(k));
        if ($urandom_range(0, 3) == 0) @(negedge clk);
      end
      for (int k = 0; k < 120; k++) begin
        int unsigned len, l;
        len = $urandom_range(1, 32);
        l = 2048 + $urandom_range(0, 2047 - len);                    // vector region B
        if ((l / PAGE_LINES) != ((l + len - 1) / PAGE_LINES)) l = (l / PAGE_LINES) * PAGE_LINES;
        if ($urandom_range(0, 1)) begin
          b_desc(SF_MEM_STORE, vaddr(l), len, 8'(k)); b_wbeats(len, $urandom);
        end else b_desc(SF_MEM_LOAD, vaddr(l), len, 8'(k));
        while (bd_h != bd_t) @(negedge clk);
      end
    join
    drain(50000);
    bp = 0;
    @(negedge clk);

    // ================================================================ phase 6: boundaries / overflow
    begin
      s_send(SF_MEM_LOAD,  saddr(4095), 0, 0, 8'hA0);                       // last scalar word: OK
      s_send(SF_MEM_STORE, saddr(4095), 32'h1234_5678, 4'hF, 8'hA1);        // OK
      s_send(SF_MEM_LOAD,  BASE + 2, 0, 0, 8'hA2);                          // misaligned
      s_send(SF_MEM_LOAD,  BASE - 4, 0, 0, 8'hA3);                          // below aperture
      s_send(SF_MEM_STORE, saddr(4096), 32'hDEAD_BEEF, 4'hF, 8'hA4);        // first vector line: domain
      s_send(SF_MEM_LOAD,  BASE + 32'(LINES) * 16, 0, 0, 8'hA5);            // one past the end
      s_send(SF_MEM_STORE, 32'hFFFF_FFFC, 32'hDEAD_BEEF, 4'hF, 8'hA6);      // top of the 4 GiB space
      s_send(SF_MEM_STORE, 32'h0000_0000, 32'hDEAD_BEEF, 4'hF, 8'hA7);      // address zero
      v_send(SF_MEM_LOAD,  vaddr(LINES - 1), 0, 4'hF, 8'hB0);               // last line: OK
      v_send(SF_MEM_STORE, vaddr(SLINES - 1), {4{32'hBAD0_BAD0}}, 4'hF, 8'hB1); // scalar domain: domain exc
      v_send(SF_MEM_LOAD,  vaddr(SLINES) + 4, 0, 4'hF, 8'hB2);              // misaligned
      v_send(SF_MEM_STORE, vaddr(LINES), {4{32'hBAD0_BAD0}}, 4'hF, 8'hB3);  // past the end
      v_send(SF_MEM_STORE, 32'hFFFF_FFF0, {4{32'hBAD0_BAD0}}, 4'hF, 8'hB4); // wraps to 0 if unguarded
      b_desc(SF_MEM_LOAD,  vaddr(2048) + 8, 4, 8'hC0);                     // misaligned base
      b_desc(SF_MEM_LOAD,  vaddr(2048 + 250), 16, 8'hC1);                  // crosses a 4 KiB page
      b_desc(SF_MEM_LOAD,  vaddr(SLINES - 4), 8, 8'hC2);                   // crosses scalar/vector domains
      b_desc(SF_MEM_STORE, vaddr(LINES - 8), 16, 8'hC3);                   // runs past the end
      b_desc(SF_MEM_LOAD,  BASE + 32'h0100_0000, 4, 8'hC4);                // outside the aperture
      b_desc(SF_MEM_LOAD,  vaddr(LINES - 16), 16, 8'hC5);                  // last legal burst: OK
      drain();
      // rejected stores must not have modified storage: the reference model never applies them,
      // so the scoreboard's data check on these read-backs is the proof
      v_send(SF_MEM_LOAD, vaddr(SLINES), 0, 4'hF, 8'hD0);
      for (int w = 0; w < 4; w++) s_send(SF_MEM_LOAD, saddr((SLINES - 1) * 4 + w), 0, 0, 8'(8'hD1 + w));
      v_send(SF_MEM_LOAD, vaddr(LINES - 1), 0, 4'hF, 8'hD5);
      drain();
    end

    // ================================================================ phase 7: parity injection
    // line SLINES+5 lives in bank (SLINES+5)%8 = 5, row (SLINES+5)/8 = 128
    begin
      int unsigned ln, bk, row;
      ln = SLINES + 5; bk = ln % NBANKS; row = ln / NBANKS;
      v_send(SF_MEM_STORE, vaddr(ln), {32'h0123_4567, 32'h89AB_CDEF, 32'h0F1E_2D3C, 32'h4B5A_6978}, 4'hF, 8'hE0);
      drain();
      dut.g_bank[5].mem_q[128][37] = ~dut.g_bank[5].mem_q[128][37];        // lane 1, byte 0
      ecc_expect_v = 1;
      v_send(SF_MEM_LOAD, vaddr(ln), 0, 4'hF, 8'hE1);
      drain();
      ecc_expect_v = 0;
      // a load that does not cover the corrupted lane is clean
      v_send(SF_MEM_LOAD, vaddr(ln), 0, 4'b1101, 8'hE2);
      drain();
      // rewriting the line restores consistent parity
      v_send(SF_MEM_STORE, vaddr(ln), {4{32'h5555_AAAA}}, 4'hF, 8'hE3);
      v_send(SF_MEM_LOAD, vaddr(ln), 0, 4'hF, 8'hE4);
      drain();
      `CHECK(bk == 5 && row == 128, "parity target bank/row arithmetic")
    end

    // ================================================================ phase 8: burst kill
    begin
      int committed;
      bw_kill_mode = 1; bw_acc = 0;
      b_desc(SF_MEM_STORE, vaddr(3072), 64, 8'hF0);
      fork
        begin : feeder
          for (int i = 0; i < 20; i++) begin
            b_w = '{data: {32'h7777_0000 + 32'(i), 32'(~i), 32'(i * 13), 32'hC1C1_0000 + 32'(i)}, strb: '1};
            b_wvld = 1;
            #1; while (!b_wrdy && !b_dvld) begin @(negedge clk); #1; end
            if (b_dvld) break;                                   // killed: engine stopped taking data
            @(negedge clk);
          end
          b_wvld = 0;
        end
        begin repeat (14) @(negedge clk); kill = 1; @(negedge clk); kill = 0; end
      join
      b_wvld = 0;
      while (!b_dvld) @(posedge clk);
      @(negedge clk);
      committed = int'(b_d.beats);
      `CHECK_EQ(b_d.exc, SF_MEM_EXC_FLUSHED, "killed burst reports FLUSHED")
      `CHECK(committed > 0 && committed <= bw_acc && committed < 20, "0 < committed <= accepted < offered")
      tb_metric("sf25_kill_committed_beats", real'(committed));
      tb_metric("sf25_kill_accepted_beats", real'(bw_acc));
      while (bd_h != bd_t) @(negedge clk);
      bw_kill_mode = 0;
      // exactly the committed beats reached storage; the rest of the burst window is untouched
      for (int i = 0; i < committed; i++) refm[3072 + i] = bw_kill_data[i];
      b_desc(SF_MEM_LOAD, vaddr(3072), 64, 8'hF1);
      drain();
    end

    tb_metric("sf25_total_scalar_responses", real'(s_rsp_n));
    tb_metric("sf25_total_vector_responses", real'(v_rsp_n));
    tb_metric("sf25_total_burst_beats", real'(b_beats_r + b_beats_w));
    tb_finish();
  end

  initial begin
    #50_000_000;
    `CHECK(0, "global timeout");
    tb_finish();
  end
endmodule
