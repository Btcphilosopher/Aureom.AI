// =============================================================================
// SilicaFlux-V :: sfv_cpu -- 32-bit control processor
//
// ISA      : RV32I (or RV32E with RV32E=1) + Zicsr, machine mode only.
//            FENCE executes as NOP (in order, blocking stores); FENCE.I
//            flushes the 2-entry prefetch buffer (no caches).
// Pipeline : 2 stages, in order, no speculation beyond sequential prefetch.
//              IF : 1 outstanding instruction request (overlapped with its
//                   response), 2-entry fetch buffer, registered redirect.
//              EX : decode, register read, ALU / branch / CSR, load-store
//                   (blocking: the instruction completes when the data
//                   response returns), trap & interrupt entry, write-back.
//            No forwarding network is required: EX writes back before the
//            next instruction reads the register file.
//            CPI: ALU 1, load/store 2 (+wait states), taken branch / jump 3.
// Traps    : precise.  Exceptions supported (mcause):
//              0 instruction address misaligned (on the branch/jump)
//              1 instruction access fault        (bus error on fetch)
//              2 illegal instruction              (mtval = instruction)
//              3 breakpoint (EBREAK)              (mtval = pc)
//              4/6 load/store address misaligned  (mtval = address)
//              5/7 load/store access fault        (mtval = address)
//              11 environment call from M-mode
//            Interrupts: MSI(3), MTI(7), MEI(11); priority MEI > MSI > MTI.
//            mtvec direct (MODE=0) or vectored (MODE=1) mode.
// Bus      : two SFB ports (OBI-style req/gnt + rvalid), see docs/BUS.md.
//            req never depends combinationally on gnt; once asserted, req and
//            its attributes are held until gnt.
//
// Derivation: decode tables and immediate generation follow the repository's
// cpu_core.sv (cpu_core.zip, RV32I 5-stage).  Pipeline, bus interface, CSR
// file and trap logic are new (cpu_core had none of them; see
// docs/REUSE_MATRIX.md).
// =============================================================================
`default_nettype none

module sfv_cpu #(
  parameter logic [31:0] BOOT_ADDR = 32'h0000_0000,
  parameter bit          RV32E     = 1'b0,
  parameter logic [31:0] HART_ID   = 32'h0
) (
  input  wire logic        clk,
  input  wire logic        rst_n,
  // instruction port
  output logic             i_req,
  input  wire logic        i_gnt,
  output logic [31:0]      i_addr,
  input  wire logic        i_rvalid,
  input  wire logic [31:0] i_rdata,
  input  wire logic        i_err,
  // data port
  output logic             d_req,
  input  wire logic        d_gnt,
  output logic [31:0]      d_addr,
  output logic             d_we,
  output logic [3:0]       d_be,
  output logic [31:0]      d_wdata,
  input  wire logic        d_rvalid,
  input  wire logic [31:0] d_rdata,
  input  wire logic        d_err,
  // interrupts (level, synchronous to clk)
  input  wire logic        irq_ext,
  input  wire logic        irq_timer,
  input  wire logic        irq_soft,
  // status
  output logic             sleeping,      // WFI stall
  // retirement trace (verification only; unloaded in silicon -> removed)
  output logic             rt_valid,
  output logic [31:0]      rt_pc,
  output logic [31:0]      rt_insn,
  output logic             rt_trap,
  output logic [31:0]      rt_cause,
  output logic [4:0]       rt_rd,
  output logic [31:0]      rt_rd_wdata,
  output logic             rt_rd_we
);

  localparam int NREG = RV32E ? 16 : 32;

  // ===========================================================================
  // IF stage
  // ===========================================================================
  logic [31:0] f_pc_q;            // address of next fetch request
  logic        out_q;             // a request has been granted, response pending
  logic        discard_q;         // drop the pending response (stale path)
  logic [31:0] out_pc_q;          // pc of pending request

  // 2-entry fetch buffer
  logic [1:0]  fb_cnt_q;
  logic [31:0] fb0_pc_q, fb1_pc_q, fb0_ins_q, fb1_ins_q;
  logic        fb0_err_q, fb1_err_q;

  logic        ex_consume;        // EX finishes the head instruction this cycle
  logic        ex_redirect;       // flush + new pc (branch, jump, trap, mret)
  logic [31:0] ex_target;

  wire resp      = out_q && i_rvalid;
  wire resp_keep = resp && !discard_q && !ex_redirect;
  // entries remaining after this cycle (before the new request)
  wire [1:0] fb_after = ex_redirect ? 2'd0
                      : (fb_cnt_q - {1'b0, ex_consume} + {1'b0, resp_keep});
  // issue when the single outstanding slot is free (or frees now) and the
  // buffer is guaranteed to have room for the response.
  assign i_req  = (!out_q || i_rvalid) && (fb_after <= 2'd1);
  assign i_addr = f_pc_q;
  wire issue = i_req && i_gnt;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      f_pc_q    <= BOOT_ADDR;
      out_q     <= 1'b0;
      discard_q <= 1'b0;
      out_pc_q  <= '0;
    end else begin
      // outstanding tracking
      if (issue) begin
        out_q     <= 1'b1;
        out_pc_q  <= f_pc_q;
        // a request issued in the redirect cycle fetches the stale path
        discard_q <= ex_redirect;
      end else if (resp) begin
        out_q     <= 1'b0;
        discard_q <= 1'b0;
      end else if (ex_redirect && out_q) begin
        discard_q <= 1'b1;
      end
      // next fetch address
      if (ex_redirect)  f_pc_q <= ex_target;
      else if (issue)   f_pc_q <= f_pc_q + 32'd4;
    end
  end

  // buffer update: entry 0 is the head
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      fb_cnt_q <= 2'd0;
    end else begin
      fb_cnt_q <= fb_after;
    end
  end

  // buffer data (no reset needed: qualified by fb_cnt_q)
  //   load0: entry 0 receives the response; load1: entry 1 receives it;
  //   shift: entry 1 moves to entry 0 (head consumed)
  wire fb_load0 = !ex_redirect && resp_keep &&
                  ((ex_consume && fb_cnt_q != 2'd2) || (!ex_consume && fb_cnt_q == 2'd0));
  wire fb_load1 = !ex_redirect && resp_keep &&
                  ((ex_consume && fb_cnt_q == 2'd2) || (!ex_consume && fb_cnt_q == 2'd1));
  wire fb_shift = !ex_redirect && ex_consume && !fb_load0;
  always_ff @(posedge clk) begin
    if (fb_load0) begin
      fb0_pc_q  <= out_pc_q;
      fb0_ins_q <= i_rdata;
      fb0_err_q <= i_err;
    end else if (fb_shift) begin
      fb0_pc_q  <= fb1_pc_q;
      fb0_ins_q <= fb1_ins_q;
      fb0_err_q <= fb1_err_q;
    end
    if (fb_load1) begin
      fb1_pc_q  <= out_pc_q;
      fb1_ins_q <= i_rdata;
      fb1_err_q <= i_err;
    end
  end

  // ===========================================================================
  // EX stage: decode
  // ===========================================================================
  wire        hv   = (fb_cnt_q != 2'd0);
  wire [31:0] pc   = fb0_pc_q;
  wire [31:0] ins  = fb0_ins_q;
  wire        ferr = fb0_err_q;

  wire [6:0] opc    = ins[6:0];
  wire [4:0] rd     = ins[11:7];
  wire [2:0] f3     = ins[14:12];
  wire [4:0] rs1    = ins[19:15];
  wire [4:0] rs2    = ins[24:20];
  wire [6:0] f7     = ins[31:25];
  wire [11:0] csr_a = ins[31:20];

  wire [31:0] imm_i = {{20{ins[31]}}, ins[31:20]};
  wire [31:0] imm_s = {{20{ins[31]}}, ins[31:25], ins[11:7]};
  wire [31:0] imm_b = {{19{ins[31]}}, ins[31], ins[7], ins[30:25], ins[11:8], 1'b0};
  wire [31:0] imm_u = {ins[31:12], 12'b0};
  wire [31:0] imm_j = {{11{ins[31]}}, ins[31], ins[19:12], ins[20], ins[30:21], 1'b0};

  localparam logic [6:0] OP_LUI    = 7'b0110111;
  localparam logic [6:0] OP_AUIPC  = 7'b0010111;
  localparam logic [6:0] OP_JAL    = 7'b1101111;
  localparam logic [6:0] OP_JALR   = 7'b1100111;
  localparam logic [6:0] OP_BRANCH = 7'b1100011;
  localparam logic [6:0] OP_LOAD   = 7'b0000011;
  localparam logic [6:0] OP_STORE  = 7'b0100011;
  localparam logic [6:0] OP_IMM    = 7'b0010011;
  localparam logic [6:0] OP_REG    = 7'b0110011;
  localparam logic [6:0] OP_FENCE  = 7'b0001111;
  localparam logic [6:0] OP_SYSTEM = 7'b1110011;

  wire is_lui    = (opc == OP_LUI);
  wire is_auipc  = (opc == OP_AUIPC);
  wire is_jal    = (opc == OP_JAL);
  wire is_jalr   = (opc == OP_JALR)  && (f3 == 3'b000);
  wire is_branch = (opc == OP_BRANCH) && (f3 != 3'b010) && (f3 != 3'b011);
  wire is_load   = (opc == OP_LOAD)  && (f3 != 3'b011) && (f3 != 3'b110) && (f3 != 3'b111);
  wire is_store  = (opc == OP_STORE) && (f3[2] == 1'b0) && (f3 != 3'b011);
  wire is_imm    = (opc == OP_IMM) &&
                   ((f3 == 3'b001) ? (f7 == 7'b0000000) :
                    (f3 == 3'b101) ? (f7 == 7'b0000000 || f7 == 7'b0100000) : 1'b1);
  wire is_reg    = (opc == OP_REG) &&
                   ((f7 == 7'b0000000) || (f7 == 7'b0100000 && (f3 == 3'b000 || f3 == 3'b101)));
  wire is_fence  = (opc == OP_FENCE) && (f3 == 3'b000 || f3 == 3'b001);
  wire is_fencei = (opc == OP_FENCE) && (f3 == 3'b001);   // flushes prefetch
  wire is_sys    = (opc == OP_SYSTEM);
  wire is_ecall  = is_sys && (ins[31:7] == 25'h0000000);
  wire is_ebreak = is_sys && (ins[31:7] == {12'h001, 13'h0});
  wire is_mret   = is_sys && (ins[31:7] == {12'h302, 13'h0});
  wire is_wfi    = is_sys && (ins[31:7] == {12'h105, 13'h0});
  wire is_csr    = is_sys && (f3 != 3'b000) && (f3 != 3'b100);

  // register usage (for RV32E legality)
  wire uses_rs1 = is_jalr | is_branch | is_load | is_store | is_imm | is_reg |
                  (is_csr && !f3[2]);
  wire uses_rs2 = is_branch | is_store | is_reg;
  wire uses_rd  = is_lui | is_auipc | is_jal | is_jalr | is_load | is_imm |
                  is_reg | is_csr;
  wire reg_illegal = RV32E && ((uses_rs1 && rs1[4]) || (uses_rs2 && rs2[4]) ||
                               (uses_rd && rd[4]));

  // ===========================================================================
  // Register file (x0 hard-wired to zero)
  // ===========================================================================
  logic [31:0] rf [1:NREG-1];
  logic        rf_we;
  logic [31:0] rf_wdata;
  wire  [31:0] rs1_v = (rs1 == 5'd0 || (RV32E && rs1[4])) ? 32'd0 : rf[rs1[$clog2(NREG)-1:0]];
  wire  [31:0] rs2_v = (rs2 == 5'd0 || (RV32E && rs2[4])) ? 32'd0 : rf[rs2[$clog2(NREG)-1:0]];

  always_ff @(posedge clk) begin
    if (rf_we && rd != 5'd0) rf[rd[$clog2(NREG)-1:0]] <= rf_wdata;
  end

  // ===========================================================================
  // ALU
  // ===========================================================================
  wire [31:0] alu_b   = is_reg ? rs2_v : imm_i;
  wire        sub     = is_reg && f7[5] && (f3 == 3'b000);
  wire [31:0] add_res = sub ? (rs1_v - alu_b) : (rs1_v + alu_b);
  wire [4:0]  shamt   = alu_b[4:0];
  // arithmetic shift evaluated in its own signed context: inside a ternary
  // with an unsigned arm, '>>>' would silently become a logical shift.
  wire signed [31:0] rs1_s  = rs1_v;
  wire        [31:0] sra_res = rs1_s >>> shamt;
  logic [31:0] alu_res;
  always_comb begin
    case (f3)
      3'b000: alu_res = add_res;
      3'b001: alu_res = rs1_v << shamt;
      3'b010: alu_res = {31'd0, $signed(rs1_v) < $signed(alu_b)};
      3'b011: alu_res = {31'd0, rs1_v < alu_b};
      3'b100: alu_res = rs1_v ^ alu_b;
      3'b101: alu_res = f7[5] ? sra_res : (rs1_v >> shamt);
      3'b110: alu_res = rs1_v | alu_b;
      default: alu_res = rs1_v & alu_b;
    endcase
  end

  // branch comparator
  logic br_cond;
  always_comb begin
    case (f3)
      3'b000: br_cond = (rs1_v == rs2_v);
      3'b001: br_cond = (rs1_v != rs2_v);
      3'b100: br_cond = ($signed(rs1_v) <  $signed(rs2_v));
      3'b101: br_cond = ($signed(rs1_v) >= $signed(rs2_v));
      3'b110: br_cond = (rs1_v <  rs2_v);
      default: br_cond = (rs1_v >= rs2_v);
    endcase
  end

  wire [31:0] pc4      = pc + 32'd4;
  wire [31:0] br_tgt   = pc + imm_b;
  wire [31:0] jal_tgt  = pc + imm_j;
  wire [31:0] jalr_sum = rs1_v + imm_i;
  wire [31:0] jalr_tgt = {jalr_sum[31:1], 1'b0};
  wire        br_taken = is_branch && br_cond;
  wire [31:0] cf_tgt   = is_jal ? jal_tgt : (is_jalr ? jalr_tgt : br_tgt);
  wire        cf_taken = is_jal || is_jalr || br_taken;
  wire        cf_misal = cf_taken && cf_tgt[1];

  // ===========================================================================
  // Load / store unit
  // ===========================================================================
  wire [31:0] ls_addr = rs1_v + (is_store ? imm_s : imm_i);
  wire [1:0]  ls_off  = ls_addr[1:0];
  wire        ls_misal = (f3[1:0] == 2'b01) ? ls_off[0] :
                         (f3[1:0] == 2'b10) ? (ls_off != 2'b00) : 1'b0;

  logic [3:0]  st_be;
  logic [31:0] st_data;
  always_comb begin
    case (f3[1:0])
      2'b00:   begin st_be = 4'b0001 << ls_off; st_data = {4{rs2_v[7:0]}};  end
      2'b01:   begin st_be = ls_off[1] ? 4'b1100 : 4'b0011; st_data = {2{rs2_v[15:0]}}; end
      default: begin st_be = 4'b1111; st_data = rs2_v; end
    endcase
  end

  // load data alignment and extension
  logic [31:0] ld_shift, ld_val;
  always_comb begin
    ld_shift = d_rdata >> {ls_off, 3'b000};
    case (f3)
      3'b000:  ld_val = {{24{ld_shift[7]}},  ld_shift[7:0]};
      3'b001:  ld_val = {{16{ld_shift[15]}}, ld_shift[15:0]};
      3'b100:  ld_val = {24'd0, ld_shift[7:0]};
      3'b101:  ld_val = {16'd0, ld_shift[15:0]};
      default: ld_val = ld_shift;
    endcase
  end

  // EX-stage memory state:
  //   lsu_hold_q : request asserted in an earlier cycle, not yet granted
  //   lsu_wait_q : request granted, waiting for the response
  logic lsu_hold_q, lsu_wait_q;

  // ===========================================================================
  // CSR file
  // ===========================================================================
  logic        mstatus_mie_q, mstatus_mpie_q;
  logic        mie_msie_q, mie_mtie_q, mie_meie_q;
  logic [31:0] mtvec_q;            // [1] always 0
  logic [31:0] mscratch_q, mepc_q, mtval_q;
  logic        mcause_int_q;
  logic [4:0]  mcause_code_q;
  logic [63:0] mcycle_q, minstret_q;
  logic        mcinh_cy_q, mcinh_ir_q;

  wire [31:0] mip_v = {20'd0, irq_ext, 3'd0, irq_timer, 3'd0, irq_soft, 3'd0};
  wire [31:0] mie_v = {20'd0, mie_meie_q, 3'd0, mie_mtie_q, 3'd0, mie_msie_q, 3'd0};
  wire [31:0] misa_v = {2'b01, 4'd0, 26'(RV32E ? (1 << 4) : (1 << 8))};
  wire [31:0] mstatus_v = {19'd0, 2'b11, 3'd0, mstatus_mpie_q, 3'd0, mstatus_mie_q, 3'd0};

  logic        csr_exists, csr_ro;
  logic [31:0] csr_rv;
  always_comb begin
    csr_exists = 1'b1;
    csr_rv     = 32'd0;
    case (csr_a)
      12'h300: csr_rv = mstatus_v;
      12'h301: csr_rv = misa_v;
      12'h304: csr_rv = mie_v;
      12'h305: csr_rv = mtvec_q;
      12'h310: csr_rv = 32'd0;                       // mstatush
      12'h320: csr_rv = {29'd0, mcinh_ir_q, 1'b0, mcinh_cy_q};
      12'h340: csr_rv = mscratch_q;
      12'h341: csr_rv = mepc_q;
      12'h342: csr_rv = {mcause_int_q, 26'd0, mcause_code_q};
      12'h343: csr_rv = mtval_q;
      12'h344: csr_rv = mip_v;
      12'hB00, 12'hC00: csr_rv = mcycle_q[31:0];
      12'hB02, 12'hC02: csr_rv = minstret_q[31:0];
      12'hB80, 12'hC80: csr_rv = mcycle_q[63:32];
      12'hB82, 12'hC82: csr_rv = minstret_q[63:32];
      12'hF11: csr_rv = 32'd0;                       // mvendorid: non-commercial
      12'hF12: csr_rv = 32'd0;                       // marchid: not registered
      12'hF13: csr_rv = sfv_pkg::MIMPID;
      12'hF14: csr_rv = HART_ID;
      12'hF15: csr_rv = 32'd0;                       // mconfigptr
      default: csr_exists = 1'b0;
    endcase
  end
  assign csr_ro = (csr_a[11:10] == 2'b11);
  wire [31:0] csr_src  = f3[2] ? {27'd0, rs1} : rs1_v;
  wire        csr_wr   = (f3[1:0] == 2'b01) || (rs1 != 5'd0);   // CSRRW always writes
  logic [31:0] csr_wv;
  always_comb begin
    case (f3[1:0])
      2'b01:   csr_wv = csr_src;
      2'b10:   csr_wv = csr_rv | csr_src;
      default: csr_wv = csr_rv & ~csr_src;
    endcase
  end
  wire csr_illegal = is_csr && (!csr_exists || (csr_ro && csr_wr));

  // ===========================================================================
  // EX control: interrupts, exceptions, completion
  // ===========================================================================
  wire [31:0] irq_pend = mip_v & mie_v;
  wire        irq_any  = mstatus_mie_q && (irq_pend != 32'd0);
  logic [4:0] irq_code;
  always_comb begin
    if      (irq_pend[11]) irq_code = 5'd11;
    else if (irq_pend[3])  irq_code = 5'd3;
    else                   irq_code = 5'd7;
  end
  // interrupts are taken only before an instruction has started a bus access
  wire take_irq = hv && irq_any && !lsu_hold_q && !lsu_wait_q;

  wire known = is_lui | is_auipc | is_jal | is_jalr | is_branch | is_load |
               is_store | is_imm | is_reg | is_fence | is_ecall | is_ebreak |
               is_mret | is_wfi | is_csr;
  wire illegal = !known || reg_illegal || csr_illegal;
  wire is_ls   = is_load || is_store;

  // synchronous exceptions detectable at decode
  logic        exc_dec;
  logic [4:0]  exc_dec_code;
  logic [31:0] exc_dec_tval;
  always_comb begin
    exc_dec      = 1'b1;
    exc_dec_code = 5'd0;
    exc_dec_tval = 32'd0;
    if (ferr) begin
      exc_dec_code = 5'd1;  exc_dec_tval = pc;
    end else if (illegal) begin
      exc_dec_code = 5'd2;  exc_dec_tval = ins;
    end else if (is_ebreak) begin
      exc_dec_code = 5'd3;  exc_dec_tval = pc;
    end else if (is_ecall) begin
      exc_dec_code = 5'd11; exc_dec_tval = 32'd0;
    end else if (is_ls && ls_misal) begin
      exc_dec_code = is_store ? 5'd6 : 5'd4; exc_dec_tval = ls_addr;
    end else if (cf_misal) begin
      exc_dec_code = 5'd0;  exc_dec_tval = cf_tgt;
    end else begin
      exc_dec = 1'b0;
    end
  end

  // bus request
  wire ls_go = hv && !take_irq && !exc_dec && is_ls;
  assign d_req   = ls_go && !lsu_wait_q;
  assign d_addr  = {ls_addr[31:2], 2'b00};
  assign d_we    = is_store;
  assign d_be    = is_store ? st_be : 4'b1111;
  assign d_wdata = st_data;

  wire ls_done  = ls_go && lsu_wait_q && d_rvalid;
  wire ls_fault = ls_done && d_err;

  wire wfi_wake = (irq_pend != 32'd0);
  assign sleeping = hv && is_wfi && !exc_dec && !take_irq && !wfi_wake;

  // trap / completion decisions
  logic        trap;
  logic        trap_int;
  logic [4:0]  trap_code;
  logic [31:0] trap_tval;
  logic [31:0] trap_epc;
  logic        retire;      // instruction completes normally
  always_comb begin
    trap      = 1'b0;
    trap_int  = 1'b0;
    trap_code = 5'd0;
    trap_tval = 32'd0;
    trap_epc  = pc;
    retire    = 1'b0;
    if (hv) begin
      if (take_irq) begin
        trap      = 1'b1;
        trap_int  = 1'b1;
        trap_code = irq_code;
        trap_epc  = is_wfi ? pc4 : pc;
      end else if (exc_dec) begin
        trap      = 1'b1;
        trap_code = exc_dec_code;
        trap_tval = exc_dec_tval;
      end else if (is_ls) begin
        if (ls_fault) begin
          trap      = 1'b1;
          trap_code = is_store ? 5'd7 : 5'd5;
          trap_tval = ls_addr;
        end else begin
          retire = ls_done;
        end
      end else if (is_wfi) begin
        retire = wfi_wake;
      end else begin
        retire = 1'b1;
      end
    end
  end

  wire [31:0] tvec_base = {mtvec_q[31:2], 2'b00};
  wire [31:0] trap_pc   = (mtvec_q[0] && trap_int) ? (tvec_base + {25'd0, trap_code, 2'b00})
                                                   : tvec_base;

  assign ex_consume  = trap || retire;
  // FENCE.I discards the prefetch buffer so that code written by earlier
  // stores is re-fetched (stores complete before the next instruction).
  assign ex_redirect = trap || (retire && (cf_taken || is_mret || is_fencei));
  assign ex_target   = trap ? trap_pc : (is_mret ? mepc_q : (is_fencei ? pc4 : cf_tgt));

  // write-back
  always_comb begin
    rf_we    = retire && uses_rd;
    rf_wdata = alu_res;
    if (is_lui)                 rf_wdata = imm_u;
    else if (is_auipc)          rf_wdata = pc + imm_u;
    else if (is_jal || is_jalr) rf_wdata = pc4;
    else if (is_load)           rf_wdata = ld_val;
    else if (is_csr)            rf_wdata = csr_rv;
  end

  // ===========================================================================
  // Sequential EX state and CSRs
  // ===========================================================================
  wire csr_write = retire && is_csr && csr_wr;
  wire csr_wr_cyc = csr_write && (csr_a == 12'hB00 || csr_a == 12'hB80);
  wire csr_wr_ins = csr_write && (csr_a == 12'hB02 || csr_a == 12'hB82);

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      lsu_hold_q     <= 1'b0;
      lsu_wait_q     <= 1'b0;
      mstatus_mie_q  <= 1'b0;
      mstatus_mpie_q <= 1'b0;
      mie_msie_q     <= 1'b0;
      mie_mtie_q     <= 1'b0;
      mie_meie_q     <= 1'b0;
      mtvec_q        <= BOOT_ADDR;
      mscratch_q     <= '0;
      mepc_q         <= '0;
      mtval_q        <= '0;
      mcause_int_q   <= 1'b0;
      mcause_code_q  <= '0;
      mcycle_q       <= '0;
      minstret_q     <= '0;
      mcinh_cy_q     <= 1'b0;
      mcinh_ir_q     <= 1'b0;
    end else begin
      // load/store handshake state
      lsu_hold_q <= d_req && !d_gnt;
      if (d_req && d_gnt)  lsu_wait_q <= 1'b1;
      else if (d_rvalid)   lsu_wait_q <= 1'b0;

      // counters: a CSR write to either half suppresses that cycle's
      // increment of the whole 64-bit counter (priv. spec 3.3.1)
      if (!mcinh_cy_q && !csr_wr_cyc) mcycle_q <= mcycle_q + 64'd1;
      if (retire && !mcinh_ir_q && !csr_wr_ins) minstret_q <= minstret_q + 64'd1;

      if (trap) begin
        mepc_q         <= {trap_epc[31:2], 2'b00};
        mcause_int_q   <= trap_int;
        mcause_code_q  <= trap_code;
        mtval_q        <= trap_tval;
        mstatus_mpie_q <= mstatus_mie_q;
        mstatus_mie_q  <= 1'b0;
      end else if (retire && is_mret) begin
        mstatus_mie_q  <= mstatus_mpie_q;
        mstatus_mpie_q <= 1'b1;
      end else if (csr_write) begin
        case (csr_a)
          12'h300: begin
            mstatus_mie_q  <= csr_wv[3];
            mstatus_mpie_q <= csr_wv[7];
          end
          12'h304: begin
            mie_msie_q <= csr_wv[3];
            mie_mtie_q <= csr_wv[7];
            mie_meie_q <= csr_wv[11];
          end
          12'h305: mtvec_q    <= {csr_wv[31:2], 1'b0, csr_wv[0]};
          12'h320: begin
            mcinh_cy_q <= csr_wv[0];
            mcinh_ir_q <= csr_wv[2];
          end
          12'h340: mscratch_q <= csr_wv;
          12'h341: mepc_q     <= {csr_wv[31:2], 2'b00};
          12'h342: begin
            mcause_int_q  <= csr_wv[31];
            mcause_code_q <= csr_wv[4:0];
          end
          12'h343: mtval_q    <= csr_wv;
          12'hB00: mcycle_q[31:0]    <= csr_wv;
          12'hB80: mcycle_q[63:32]   <= csr_wv;
          12'hB02: minstret_q[31:0]  <= csr_wv;
          12'hB82: minstret_q[63:32] <= csr_wv;
          default: ;
        endcase
      end
    end
  end

  // ===========================================================================
  // Retirement trace
  // ===========================================================================
  assign rt_valid    = trap || retire;
  assign rt_pc       = pc;
  assign rt_insn     = ins;
  assign rt_trap     = trap;
  assign rt_cause    = {trap_int, 26'd0, trap_code};
  assign rt_rd       = rd;
  assign rt_rd_wdata = rf_wdata;
  assign rt_rd_we    = rf_we && (rd != 5'd0);

endmodule

`default_nettype wire
