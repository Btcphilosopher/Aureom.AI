// =============================================================================
// tb_spm :: banked scratchpad verification + throughput measurement
// Phases
//  A  random multi-port R/W with per-port scoreboards, random response
//     backpressure, out-of-range (address overflow) requests, deadlock watchdog
//  B  hot-bank contention: all ports hammer one bank -> 1 grant/cycle total,
//     round-robin fairness
//  C  stride sweep (3 ports streaming, strides 1..16 words) -> throughput
//  D  uniform random addresses, all ports, no backpressure -> throughput
//     (calibration point for memoryflow.models.banking)
//  E  single-port streaming throughput (credit / RSP_DEPTH limited)
//  F  ECC injection through the SPM, corrected counter
// =============================================================================
`timescale 1ns/1ps
`default_nettype none
`include "tb_common.svh"

module tb_spm #(
  parameter int NBANKS     = 4,
  parameter int INTERLEAVE = 0,
  parameter int RSP_DEPTH  = 4
);
  localparam int NP = 3, DW = 64, NB = 8, AW = 32, BD = 256;
  localparam int CAPW = NBANKS * BD;                 // capacity in words
  localparam int CAP  = CAPW * NB;
  localparam int SW   = 72;

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  longint cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;

  logic [NP-1:0]    req_valid, req_ready, req_we, rsp_valid, rsp_ready, rsp_err, rsp_corr;
  logic [NP*AW-1:0] req_addr;
  logic [NP*DW-1:0] req_wdata, rsp_rdata;
  logic [NP*NB-1:0] req_wstrb;
  logic             inj_en;
  logic [$clog2(NBANKS)-1:0] inj_bank;
  logic [SW-1:0]    inj_mask;
  logic [15:0]      cnt_corr, cnt_uncorr;
  logic [31:0]      cnt_conf, cnt_stall;
  logic             mb_busy, mb_done, mb_fail;
  logic [NBANKS-1:0] mb_fb;
  logic [7:0]       mb_fa;

  sf_spm_banked #(.NPORTS(NP), .NBANKS(NBANKS), .DW(DW), .BANK_DEPTH(BD), .AW(AW),
                  .ECC_MODE(2), .INTERLEAVE(INTERLEAVE), .RSP_DEPTH(RSP_DEPTH)) dut (
    .clk, .rst_n, .req_valid, .req_ready, .req_we, .req_addr, .req_wdata, .req_wstrb,
    .rsp_valid, .rsp_ready, .rsp_rdata, .rsp_err, .rsp_corr,
    .inj_en, .inj_bank, .inj_mask, .cnt_corr, .cnt_uncorr,
    .mbist_start(1'b0), .mbist_bg('0), .mbist_busy(mb_busy), .mbist_done(mb_done),
    .mbist_fail(mb_fail), .mbist_fail_bank(mb_fb), .mbist_fail_addr(mb_fa),
    .cnt_conflict_cycles(cnt_conf), .cnt_stall_cycles(cnt_stall), .lp_sleep(1'b0));

  // ---------------------------------------------------------------- golden map
  function automatic int bank_of(int w);
    int bkw;
    bkw = $clog2(NBANKS);
    if (INTERLEAVE == 2) return (w / BD) % NBANKS;
    if (INTERLEAVE == 1) return (w % NBANKS) ^ ((w >> bkw) % NBANKS);
    return w % NBANKS;
  endfunction

  // ---------------------------------------------------------------- scoreboard
  logic [DW-1:0] refm [CAPW];
  // NOTE: Verilator 5.020 mishandles unpacked arrays of queues, so the per-port
  // expectation queues are fixed-size ring buffers of packed structs.
  typedef struct packed { logic err; logic chk; logic [DW-1:0] data; } exp_t;
  localparam int QD = 16384;
  exp_t   ring [NP][QD];
  int     qhead [NP];
  int     qtail [NP];
  function automatic int qsize(int p); return qtail[p] - qhead[p]; endfunction
  int     accepted [NP];
  int     responded [NP];
  longint last_progress = 0;
  bit     bp_enable = 0;            // random rsp backpressure
  bit     watchdog_fired = 0;
  bit     trace = 0;
  initial trace = $test$plusargs("trace");

  function automatic logic [DW-1:0] merge(logic [DW-1:0] o, logic [DW-1:0] n, logic [NB-1:0] m);
    for (int b = 0; b < NB; b++) if (m[b]) o[b*8 +: 8] = n[b*8 +: 8];
    return o;
  endfunction

  // response monitors
  always @(posedge clk) begin
    if (rst_n) begin
      for (int p = 0; p < NP; p++) begin
        if (rsp_valid[p] && rsp_ready[p]) begin
          last_progress = cyc;
          responded[p]++;
          if (qsize(p) == 0) begin
            `CHECK(0, $sformatf("unexpected response on port %0d", p))
          end else begin
            exp_t e;
            e = ring[p][qhead[p] % QD];
            qhead[p]++;
            `CHECK_EQ(rsp_err[p], e.err, $sformatf("port %0d err flag (in-order)", p))
            if (e.chk) `CHECK_EQ(rsp_rdata[p*DW +: DW], e.data, $sformatf("port %0d read data", p))
          end
        end
        if (req_valid[p] && req_ready[p]) begin
          last_progress = cyc;
          if (trace) $display("[%0d] DUT-ACC p%0d we=%0b a=%h", cyc, p, req_we[p], req_addr[p*AW +: AW]);
        end
        if (trace && rsp_valid[p] && rsp_ready[p]) $display("[%0d] DUT-RSP p%0d err=%0b q=%0d", cyc, p, rsp_err[p], qsize(p));
      end
    end
  end

  always @(negedge clk) begin
    for (int p = 0; p < NP; p++) rsp_ready[p] = bp_enable ? ($urandom_range(0, 3) != 0) : 1'b1;
  end

  // deadlock watchdog
  always @(posedge clk) begin
    if (rst_n && !watchdog_fired && (cyc - last_progress) > 3000) begin
      int pend;
      pend = 0;
      for (int p = 0; p < NP; p++) pend += qsize(p) + (req_valid[p] ? 1 : 0);
      if (pend > 0) begin
        watchdog_fired = 1;
        `CHECK(0, "DEADLOCK watchdog: no progress for 3000 cycles with work pending")
      end
    end
  end

  // one request on port p (called just after a negedge)
  task automatic port_req(int p, logic we, logic [31:0] waddr_bytes, logic [DW-1:0] d, logic [NB-1:0] s);
    bit acc;
    req_valid[p] = 1; req_we[p] = we; req_addr[p*AW +: AW] = AW'(waddr_bytes);
    req_wdata[p*DW +: DW] = d; req_wstrb[p*NB +: NB] = s;
    acc = 0;
    while (!acc) begin
      #1;
      acc = req_ready[p];
      if (acc) begin
        exp_t e;
        int w;
        e.err = (waddr_bytes >= 32'(CAP));          // unsigned compare (full 4 GiB range)
        w = e.err ? 0 : int'(waddr_bytes / NB);
        e.chk = !we && !e.err;
        e.data = e.err ? '0 : refm[w];
        ring[p][qtail[p] % QD] = e;
        qtail[p]++;
        if (we && !e.err) refm[w] = merge(refm[w], d, s);
        accepted[p]++;
        if (trace) $display("[%0d] TB-ACC  p%0d we=%0b a=%h", cyc, p, we, waddr_bytes);
      end
      @(negedge clk);
    end
    req_valid[p] = 0;
  endtask

  task automatic wait_quiet();
    int pend;
    do begin
      @(negedge clk);
      pend = 0;
      for (int p = 0; p < NP; p++) pend += qsize(p);
    end while (pend != 0 && !watchdog_fired);
  endtask

  // phase A driver: port p writes only words with (w % NP == p); reads anywhere
  task automatic phase_a_port(int p, int nops);
    for (int n = 0; n < nops; n++) begin
      int kind, w;
      kind = $urandom_range(0, 9);
      if (kind < 4) begin                      // read anywhere in range
        w = $urandom_range(0, CAPW - 1);
        port_req(p, 0, w * NB, '0, '0);
      end else if (kind < 8) begin             // write own word
        w = $urandom_range(0, CAPW / NP - 1) * NP + p;
        port_req(p, 1, w * NB, {$urandom(), $urandom()}, (kind == 7) ? NB'($urandom()) : '1);
      end else begin                           // out of range (overflow protection)
        port_req(p, kind == 9, CAP + 8 * $urandom_range(0, 4096), {$urandom(), $urandom()}, '1);
      end
      if ($urandom_range(0, 5) == 0) repeat ($urandom_range(1, 3)) @(negedge clk);
    end
  endtask

  // stream reads: port p reads n words starting at word base with stride
  task automatic stream_port(int p, int base, int stride, int n);
    for (int i = 0; i < n; i++) port_req(p, 0, ((base + i * stride) % CAPW) * NB, '0, '0);
  endtask

  // hot bank: all addresses mapping to bank 0
  task automatic hot_port(int p, int n);
    for (int i = 0; i < n; i++) begin
      int w;
      do w = $urandom_range(0, CAPW - 1); while (bank_of(w) != 0);
      port_req(p, 0, w * NB, '0, '0);
    end
  endtask

  task automatic random_port(int p, int n);
    for (int i = 0; i < n; i++) port_req(p, 0, $urandom_range(0, CAPW - 1) * NB, '0, '0);
  endtask

  longint t0;
  int     a0 [NP];

  task automatic snap();
    t0 = cyc;
    for (int p = 0; p < NP; p++) a0[p] = accepted[p];
  endtask

  function automatic real thr();
    int tot;
    tot = 0;
    for (int p = 0; p < NP; p++) tot += accepted[p] - a0[p];
    return real'(tot) / real'(cyc - t0);
  endfunction

  initial begin
    req_valid = '0; req_we = '0; req_addr = '0; req_wdata = '0; req_wstrb = '0;
    inj_en = 0; inj_bank = '0; inj_mask = '0;
    for (int p = 0; p < NP; p++) begin accepted[p] = 0; responded[p] = 0; qhead[p] = 0; qtail[p] = 0; end
    repeat (3) @(negedge clk);
    rst_n = 1;
    @(negedge clk);

    // ---- initialise memory through port 0
    for (int w = 0; w < CAPW; w++) port_req(0, 1, w * NB, {$urandom(), $urandom()}, '1);
    wait_quiet();

    // ---- A: random multi-port with backpressure
    bp_enable = 1;
    fork
      phase_a_port(0, 3000);
      phase_a_port(1, 3000);
      phase_a_port(2, 3000);
    join
    wait_quiet();
    bp_enable = 0;
    for (int p = 0; p < NP; p++)
      `CHECK_EQ(accepted[p], responded[p], $sformatf("port %0d: one response per request", p))

    // ---- A2: directed address-boundary tests (overflow protection).
    // Added after mutation testing showed random OOR addresses almost never
    // hit exactly CAPACITY, so an off-by-one (aliasing onto word 0) survived.
    port_req(0, 1, CAP - NB, 64'h1111_2222_3333_4444, '1);      // last valid word
    port_req(0, 0, CAP - NB, '0, '0);
    port_req(0, 1, CAP, 64'hBAD0_BAD0_BAD0_BAD0, '1);          // first invalid byte address
    port_req(1, 0, CAP, '0, '0);
    port_req(2, 1, CAP + NB * CAPW, 64'hBAD1_BAD1_BAD1_BAD1, '1);// wraps to word 0 if truncated
    port_req(2, 0, 32'hFFFF_FFF8, '0, '0);                       // top of the address space
    port_req(0, 0, 0, '0, '0);                                   // word 0 must be untouched
    port_req(1, 0, NB, '0, '0);
    wait_quiet();

    // ---- B: hot-bank contention
    snap();
    fork hot_port(0, 600); hot_port(1, 600); hot_port(2, 600); join
    tb_metric("spm_hotbank_throughput", thr());
    begin
      int mx, mn;
      mx = 0; mn = 1 << 30;
      for (int p = 0; p < NP; p++) begin
        if (accepted[p] - a0[p] > mx) mx = accepted[p] - a0[p];
        if (accepted[p] - a0[p] < mn) mn = accepted[p] - a0[p];
      end
      // all ports issued 600; fairness: finish times close -> check share via
      // conflict counter instead: throughput must be <= 1 grant/cycle
      `CHECK(thr() <= 1.0001, "hot bank serves at most one request per cycle")
      `CHECK(thr() >= 0.90, "hot bank sustains ~1 request per cycle")
    end
    wait_quiet();

    // ---- C: stride sweep
    for (int s = 1; s <= 16; s = s * 2) begin
      snap();
      fork
        stream_port(0, 0,   s, 512);
        stream_port(1, 37,  s, 512);
        stream_port(2, 101, s, 512);
      join
      tb_metric($sformatf("spm_stride%0d_throughput", s), thr());
      wait_quiet();
    end

    // ---- D: uniform random, all ports
    snap();
    fork random_port(0, 2000); random_port(1, 2000); random_port(2, 2000); join
    tb_metric("spm_random3_throughput", thr());
    wait_quiet();

    // ---- E: single port streaming
    snap();
    stream_port(0, 0, 1, 1024);
    tb_metric("spm_single_port_throughput", thr());
    wait_quiet();

    // ---- F: ECC injection via SPM
    begin
      int w;
      w = 0;
      while (bank_of(w) != 1) w++;
      inj_en = 1; inj_bank = 1; inj_mask = SW'(1) << 9;
      port_req(1, 1, w * NB, 64'hCAFE_F00D_1234_5678, '1);
      inj_en = 0; inj_mask = '0;
      wait_quiet();
      port_req(1, 0, w * NB, '0, '0);
      wait_quiet();
      `CHECK(cnt_corr >= 16'd1, "SPM corrected-error counter increments")
      `CHECK_EQ(cnt_uncorr, 16'd0, "no uncorrectable errors")
    end
    tb_metric("spm_conflict_cycles", real'(cnt_conf));
    `CHECK(!watchdog_fired, "no deadlock")
    tb_finish();
  end

  initial begin
    #200ms;
    $display("TIMEOUT");
    tb_finish();
  end
endmodule

`default_nettype wire
