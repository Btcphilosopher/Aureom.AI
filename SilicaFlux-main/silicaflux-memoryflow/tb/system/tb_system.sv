// =============================================================================
// tb_system :: end-to-end SilicaFlux MemoryFlow subsystem (sf_memflow_top)
//  S1  register identification (DMA + control block)
//  S2  GEMM C(16x8) = A(16x32) * B(32x8) on the tensor array:
//      A streamed from SPM (2 row tiles), B fetched ONCE and replayed twice by
//      the reuse buffer, C streamed back to SPM; compared with Python golden.
//      B is loaded before A (producer sequencing avoids the joined-stream
//      head-of-line deadlock -- see tb_deadlock).
//  S3  vector ADD / AXPY(alpha=3) / DOT through DMA streams vs Python golden
//  S4  DMA prefetch EXT -> SPM, then compute on the prefetched operands
//  S5  ECC single-bit injection via control registers -> corrected count
//  S6  MBIST via control registers (destructive; run last) + IRQ
// =============================================================================
`timescale 1ns/1ps
`default_nettype none
`include "tb_common.svh"

module tb_system;
  localparam int VEC_IN_FIFO_P = 16;
  `include "tb_system_common.svh"

  logic [DW-1:0] g_a [64], g_b [64], g_c [64];
  logic [DW-1:0] v_a [64], v_b [64], v_add [64], v_axpy [64], v_dot [64];

  task automatic load_spm(int base, input logic [DW-1:0] w [64], int n);
    for (int i = 0; i < n; i++) host_write64(base + 8 * i, w[i]);
  endtask

  task automatic check_spm(int base, input logic [DW-1:0] w [64], int n, input string tag);
    int bad;
    logic [DW-1:0] q;
    bad = 0;
    for (int i = 0; i < n; i++) begin
      host_read64(base + 8 * i, q);
      if (q !== w[i]) begin
        bad++;
        if (bad <= 3) $display("  %s beat %0d got %h exp %h", tag, i, q, w[i]);
      end
    end
    `CHECK(bad == 0, $sformatf("%s: %0d/%0d beats match Python golden", tag, n - bad, n))
  endtask

  task automatic vec_job(logic [1:0] op, logic [15:0] alpha, int src_a, int src_b, int dst, int nbytes,
                         int out_bytes, output longint cycles);
    logic [31:0] st;
    longint t0;
    apb_write(CTL + 13'h004, 32'(op));
    apb_write(CTL + 13'h008, 32'(alpha));
    dma_setup(2, 32'h0, 32'(dst), 32'(out_bytes));
    dma_setup(0, 32'(src_a), 32'h0, 32'(nbytes));
    dma_setup(1, 32'(src_b), 32'h0, 32'(nbytes));
    t0 = cyc;
    apb_write(creg(2, 0), C_START | C_SSTR | c_sport(0) | c_burst(3));
    apb_write(creg(0, 0), C_START | C_DSTR | c_dport(0) | c_burst(3));
    apb_write(creg(1, 0), C_START | C_DSTR | c_dport(1) | c_burst(3));
    for (int ch = 0; ch < 3; ch++) begin
      dma_wait(ch, st);
      `CHECK_EQ(st[2:0], 3'b010, $sformatf("vec op %0d: channel %0d DONE", op, ch))
    end
    cycles = cyc - t0;
  endtask

  logic [31:0] rd32;
  logic [DW-1:0] q64;
  longint t0, tv;

  initial begin
    psel = 0; penable = 0; pwrite = 0; paddr = '0; pwdata = '0;
    h_req_valid = 0; h_req_we = 0; h_req_addr = '0; h_req_wdata = '0; h_req_wstrb = '0;
    $readmemh("sys_gemm_a.hex", g_a);  $readmemh("sys_gemm_b.hex", g_b);  $readmemh("sys_gemm_c.hex", g_c);
    $readmemh("sys_vec_a.hex", v_a);   $readmemh("sys_vec_b.hex", v_b);
    $readmemh("sys_vec_add.hex", v_add); $readmemh("sys_vec_axpy3.hex", v_axpy); $readmemh("sys_vec_dot.hex", v_dot);
    for (int i = 0; i < EXT_BYTES; i++) u_ext.bd_write(i, 8'h00);
    repeat (3) @(negedge clk);
    rst_n = 1;
    @(negedge clk);

    // ---------------- S1
    apb_read(DMA + 13'h000, rd32); `CHECK_EQ(rd32, 32'h5346_444D, "S1 DMA ID")
    apb_read(CTL + 13'h000, rd32); `CHECK_EQ(rd32, 32'h5346_4358, "S1 CTRL ID")

    // ---------------- S2: GEMM with operand reuse
    load_spm(32'h0000, g_a, 64);       // A: 2 row tiles x 32 column beats
    load_spm(32'h1000, g_b, 32);       // B: 32 row beats
    apb_write(CTL + 13'h00C, 32'd32);  // TEN_K
    apb_write(CTL + 13'h010, 32'd2);   // REUSE_REPLAY: B used by both row tiles
    apb_write(CTL + 13'h014, 32'd1);   // PERF_CLEAR
    dma_setup(2, 32'h0, 32'h2000, 32'd512);   // C: 2 tiles x 32 beats
    dma_setup(1, 32'h1000, 32'h0, 32'd256);   // B once
    dma_setup(0, 32'h0000, 32'h0, 32'd512);   // A
    t0 = cyc;
    apb_write(creg(2, 0), C_START | C_SSTR | c_sport(1) | c_burst(4));
    apb_write(creg(1, 0), C_START | C_DSTR | c_dport(3) | c_burst(4));
    begin
      logic [31:0] st;
      dma_wait(1, st);
      `CHECK_EQ(st[2:0], 3'b010, "S2 B operand loaded into reuse buffer")
      apb_write(creg(0, 0), C_START | C_DSTR | c_dport(2) | c_burst(4));
      dma_wait(0, st);
      `CHECK_EQ(st[2:0], 3'b010, "S2 A streamed")
      dma_wait(2, st);
      `CHECK_EQ(st[2:0], 3'b010, "S2 C written back")
    end
    tv = cyc - t0;
    apb_read(CTL + 13'h020, rd32);
    `CHECK_EQ(rd32, 32'd64, "S2 tensor MAC steps = 2 tiles x K=32")
    tb_metric("sys_gemm_16x8x32_cycles", real'(tv));
    tb_metric("sys_gemm_mac_steps", real'(rd32));
    tb_metric("sys_gemm_macs", real'(rd32) * 64.0);
    tb_metric("sys_gemm_b_bytes_dma", 256.0);
    tb_metric("sys_gemm_b_bytes_without_reuse", 512.0);
    apb_read(CTL + 13'h02C, rd32);
    `CHECK_EQ(rd32, 32'd2, "S2 two output tiles drained")
    check_spm(32'h2000, g_c, 64, "S2 GEMM C");

    // ---------------- S3: vector unit through DMA streams
    load_spm(32'h3000, v_a, 64);
    load_spm(32'h3400, v_b, 64);
    vec_job(2'd0, 16'd1, 32'h3000, 32'h3400, 32'h3800, 512, 512, tv);
    tb_metric("sys_vadd_256_cycles", real'(tv));
    check_spm(32'h3800, v_add, 64, "S3 vector ADD");
    vec_job(2'd3, 16'd3, 32'h3000, 32'h3400, 32'h3800, 512, 512, tv);
    check_spm(32'h3800, v_axpy, 64, "S3 vector AXPY alpha=3");
    vec_job(2'd2, 16'd1, 32'h3000, 32'h3400, 32'h3C00, 512, 8, tv);
    tb_metric("sys_dot_256_cycles", real'(tv));
    check_spm(32'h3C00, v_dot, 1, "S3 vector DOT");

    // ---------------- S4: prefetch EXT -> SPM, then compute
    for (int i = 0; i < 64; i++) for (int b = 0; b < 8; b++) begin
      u_ext.bd_write(i * 8 + b, v_b[i][b*8 +: 8]);
      u_ext.bd_write(512 + i * 8 + b, v_a[i][b*8 +: 8]);
    end
    begin
      logic [31:0] st;
      dma_setup(3, EXT_BASE + 32'h0, 32'h4000, 32'd512);   // B'  <- EXT (prefetch)
      t0 = cyc;
      apb_write(creg(3, 0), C_START | c_burst(4));
      dma_wait(3, st);
      `CHECK_EQ(st[2:0], 3'b010, "S4 prefetch EXT->SPM")
      tb_metric("sys_prefetch_512B_ext_cycles", real'(cyc - t0));
    end
    vec_job(2'd0, 16'd1, 32'h3000, 32'h4000, 32'h4800, 512, 512, tv);
    check_spm(32'h4800, v_add, 64, "S4 compute on prefetched operand");
    // result back to EXT
    begin
      logic [31:0] st;
      dma_setup(3, 32'h4800, EXT_BASE + 32'h2000, 32'd512);
      apb_write(creg(3, 0), C_START | c_burst(4));
      dma_wait(3, st);
      `CHECK_EQ(st[2:0], 3'b010, "S4 write-back SPM->EXT")
      begin
        int bad; bad = 0;
        for (int i = 0; i < 64; i++) for (int b = 0; b < 8; b++)
          if (u_ext.bd_read(32'h2000 + i * 8 + b) !== v_add[i][b*8 +: 8]) bad++;
        `CHECK(bad == 0, "S4 result in external memory")
      end
    end

    // ---------------- S5: ECC injection through control registers
    apb_write(CTL + 13'h044, 32'h0000_0400);       // flip stored bit 10
    apb_write(CTL + 13'h040, 32'h0000_0001);       // inj_en, bank 0
    host_write64(32'h7000, 64'h0123_4567_89AB_CDEF);  // word 0xE00 -> bank 0
    apb_write(CTL + 13'h040, 32'h0);
    host_read64(32'h7000, q64);
    `CHECK_EQ(q64, 64'h0123_4567_89AB_CDEF, "S5 single-bit error corrected on read")
    apb_read(CTL + 13'h050, rd32);
    `CHECK(rd32 >= 32'd1, "S5 SPM corrected-error counter")
    apb_read(CTL + 13'h054, rd32);
    `CHECK_EQ(rd32, 32'd0, "S5 no uncorrectable errors")
    apb_read(CTL + 13'h058, rd32);
    tb_metric("sys_spm_conflict_cycles", real'(rd32));

    // ---------------- S6: IRQ + MBIST
    begin
      logic [31:0] st;
      dma_setup(3, 32'h0, 32'h5000, 32'd64);
      apb_write(creg(3, 0), C_START | C_IRQ);
      dma_wait(3, st);
      repeat (2) @(negedge clk);
      `CHECK(irq, "S6 DMA completion interrupt")
      apb_write(creg(3, 4), 32'h2);
      @(negedge clk);
      `CHECK(!irq, "S6 interrupt cleared")
      apb_write(CTL + 13'h060, 32'h1);
      t0 = cyc;
      do apb_read(CTL + 13'h064, rd32); while (!rd32[1] && (cyc - t0) < 200000);
      `CHECK(rd32[1] && !rd32[2], "S6 MBIST March C- passes on all banks")
      tb_metric("sys_mbist_cycles", real'(cyc - t0));
    end
    tb_finish();
  end

  initial begin
    #400ms;
    $display("TIMEOUT");
    tb_finish();
  end
endmodule

`default_nettype wire
