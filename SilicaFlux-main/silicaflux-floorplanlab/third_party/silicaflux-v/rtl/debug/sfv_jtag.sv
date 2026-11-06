// =============================================================================
// SilicaFlux-V :: JTAG test access port and debug module
//
// sfv_jtag_tap  IEEE 1149.1-style TAP controller (16-state FSM, 5-bit IR,
//               BYPASS, IDCODE).  Derived from the repository's
//               silicaflux-testcore tc_tap.sv (state encoding, capture/shift
//               on TCK rise, IR update and TDO on TCK fall); instruction set
//               replaced for SilicaFlux-V and package dependencies removed.
// sfv_jtag_dbg  TCK-domain data registers + system-clock bus master:
//   IR 0x01 IDCODE   32b  {ver, JTAG_PART, JTAG_MFR, 1}
//   IR 0x10 SBA      66b  shift-in {op[1:0], wdata[31:0], addr[31:0]} (LSB
//                         first: addr first).  op 1 = read, 2 = write,
//                         0 = poll.  Capture: {busy, err, rdata[31:0], 32'b0}
//                         of the previous command.  A new op is ignored while
//                         busy (no lost/duplicated transactions).
//   IR 0x11 DBGCTRL  8b   [0] CPU_HOLD (CPU kept in reset) [1] SYS_RESET
//                         request [2] BOOT_OVR [4:3] BOOT_OVR_MODE.
//                         Capture: [0] hold [1] sleep(WFI) [2] test_pass
//                         [3] test_fail [7:4] 0
//   IR 0x1F BYPASS, all other opcodes -> BYPASS.
// Not implemented: boundary-scan register (EXTEST / SAMPLE / PRELOAD) and the
// RISC-V External Debug (DM/DTM).  Both are recorded blockers (ISS-005/006).
//
// CDC: SBA uses a toggle request / toggle acknowledge handshake through
// two-flop synchronisers; command and result registers are quasi-static
// while the handshake is in flight (stable >= 2 destination clocks before
// they are sampled), so no multi-bit signal is synchronised directly.
// DBGCTRL bits are quasi-static levels and pass through sfv_sync.
// =============================================================================
`default_nettype none

module sfv_jtag_tap #(
  parameter int IRW = 5
) (
  input  wire logic           tck,
  input  wire logic           trst_n,
  input  wire logic           tms,
  input  wire logic           tdi,
  output logic                tdo,
  output logic                tdo_oe,
  output logic [IRW-1:0]      ir,
  output logic                capture_dr,
  output logic                shift_dr,
  output logic                update_dr,
  output logic [3:0]          state_o,     // controller state (observability)
  input  wire logic           dr_tdo       // serial output of the selected TDR
);
  // state encoding as tc_tap / IEEE 1149.1 Table 6-3 style
  localparam logic [3:0] EXIT2_DR = 4'h0, EXIT1_DR = 4'h1, SHIFT_DR = 4'h2,
                         PAUSE_DR = 4'h3, SEL_IR   = 4'h4, UPDATE_DR = 4'h5,
                         CAPT_DR  = 4'h6, SEL_DR   = 4'h7, EXIT2_IR = 4'h8,
                         EXIT1_IR = 4'h9, SHIFT_IR = 4'hA, PAUSE_IR = 4'hB,
                         RTI      = 4'hC, UPDATE_IR = 4'hD, CAPT_IR = 4'hE,
                         TLR      = 4'hF;
  localparam logic [IRW-1:0] IR_IDCODE = 5'h01;

  logic [3:0] st, nx;
  always_comb begin
    case (st)
      TLR:       nx = tms ? TLR      : RTI;
      RTI:       nx = tms ? SEL_DR   : RTI;
      SEL_DR:    nx = tms ? SEL_IR   : CAPT_DR;
      CAPT_DR:   nx = tms ? EXIT1_DR : SHIFT_DR;
      SHIFT_DR:  nx = tms ? EXIT1_DR : SHIFT_DR;
      EXIT1_DR:  nx = tms ? UPDATE_DR : PAUSE_DR;
      PAUSE_DR:  nx = tms ? EXIT2_DR : PAUSE_DR;
      EXIT2_DR:  nx = tms ? UPDATE_DR : SHIFT_DR;
      UPDATE_DR: nx = tms ? SEL_DR   : RTI;
      SEL_IR:    nx = tms ? TLR      : CAPT_IR;
      CAPT_IR:   nx = tms ? EXIT1_IR : SHIFT_IR;
      SHIFT_IR:  nx = tms ? EXIT1_IR : SHIFT_IR;
      EXIT1_IR:  nx = tms ? UPDATE_IR : PAUSE_IR;
      PAUSE_IR:  nx = tms ? EXIT2_IR : PAUSE_IR;
      EXIT2_IR:  nx = tms ? UPDATE_IR : SHIFT_IR;
      default:   nx = tms ? SEL_DR   : RTI;          // UPDATE_IR
    endcase
  end
  always_ff @(posedge tck or negedge trst_n) begin
    if (!trst_n) st <= TLR;
    else         st <= nx;
  end
  assign state_o    = st;
  assign capture_dr = (st == CAPT_DR);
  assign shift_dr   = (st == SHIFT_DR);
  assign update_dr  = (st == UPDATE_DR);

  logic [IRW-1:0] ir_sh;
  always_ff @(posedge tck or negedge trst_n) begin
    if (!trst_n)              ir_sh <= '0;
    else if (st == CAPT_IR)   ir_sh <= {{(IRW-2){1'b0}}, 2'b01};   // 1149.1: LSBs = 01
    else if (st == SHIFT_IR)  ir_sh <= {tdi, ir_sh[IRW-1:1]};
  end
  always_ff @(negedge tck or negedge trst_n) begin
    if (!trst_n)              ir <= IR_IDCODE;
    else if (st == TLR)       ir <= IR_IDCODE;
    else if (st == UPDATE_IR) ir <= ir_sh;
  end

  always_ff @(negedge tck or negedge trst_n) begin
    if (!trst_n) begin
      tdo    <= 1'b0;
      tdo_oe <= 1'b0;
    end else begin
      tdo    <= (st == SHIFT_IR) ? ir_sh[0] : dr_tdo;
      tdo_oe <= (st == SHIFT_IR) || (st == SHIFT_DR);
    end
  end
endmodule

module sfv_jtag_dbg (
  // JTAG
  input  wire logic        tck,
  input  wire logic        trst_n,
  input  wire logic        tms,
  input  wire logic        tdi,
  output logic             tdo,
  output logic             tdo_oe,
  // system
  input  wire logic        clk,
  input  wire logic        rst_n,
  output logic             m_req,
  input  wire logic        m_gnt,
  output logic [31:0]      m_addr,
  output logic             m_we,
  output logic [3:0]       m_be,
  output logic [31:0]      m_wdata,
  input  wire logic        m_rvalid,
  input  wire logic [31:0] m_rdata,
  input  wire logic        m_err,
  output logic             cpu_hold,      // sys domain
  output logic             sys_reset_req, // sys domain level
  output logic             boot_ovr,
  output logic [1:0]       boot_ovr_mode,
  input  wire logic        cpu_sleep,
  input  wire logic        test_pass,
  input  wire logic        test_fail
);
  localparam logic [4:0] IR_IDCODE = 5'h01, IR_SBA = 5'h10, IR_DBGCTRL = 5'h11;

  logic [4:0] ir;
  logic       capture_dr, shift_dr, update_dr, dr_tdo;
  logic [3:0] tap_state_unused;
  sfv_jtag_tap u_tap (
    .tck, .trst_n, .tms, .tdi, .tdo, .tdo_oe, .ir,
    .capture_dr, .shift_dr, .update_dr, .state_o(tap_state_unused), .dr_tdo
  );

  // ------------------------------------------------------------ TCK domain
  logic        byp_q;
  logic [31:0] id_sh;
  logic [65:0] sba_sh;
  logic [7:0]  ctl_sh, ctl_q;
  logic [1:0]  cmd_op_q;
  logic [31:0] cmd_addr_q, cmd_wdata_q;
  logic        req_tgl_q;            // TCK domain toggle
  logic        ack_tgl_s;            // ack toggle synchronised into TCK
  // system-domain handshake state and result (read quasi-static from TCK)
  logic        req_tgl_s, req_tgl_seen_q, ack_tgl_q_sys;
  logic [31:0] res_rdata_q;
  logic        res_err_q;
  wire         tck_busy = (req_tgl_q != ack_tgl_s);

  // TCK-domain view of sys-domain status bits (quasi-static -> synchronise)
  logic sleep_s, pass_s, fail_s;
  sfv_sync u_s_ack  (.clk(tck), .rst_n(trst_n), .d(ack_tgl_q_sys), .q(ack_tgl_s));
  sfv_sync u_s_slp  (.clk(tck), .rst_n(trst_n), .d(cpu_sleep), .q(sleep_s));
  sfv_sync u_s_pass (.clk(tck), .rst_n(trst_n), .d(test_pass), .q(pass_s));
  sfv_sync u_s_fail (.clk(tck), .rst_n(trst_n), .d(test_fail), .q(fail_s));

  always_ff @(posedge tck or negedge trst_n) begin
    if (!trst_n) begin
      byp_q <= 1'b0; id_sh <= '0; sba_sh <= '0; ctl_sh <= '0; ctl_q <= '0;
      cmd_op_q <= '0; cmd_addr_q <= '0; cmd_wdata_q <= '0; req_tgl_q <= 1'b0;
    end else begin
      if (capture_dr) begin
        byp_q  <= 1'b0;
        id_sh  <= {4'h1, sfv_pkg::JTAG_PART, sfv_pkg::JTAG_MFR, 1'b1};
        sba_sh <= {tck_busy, res_err_q, res_rdata_q, 32'd0};
        ctl_sh <= {4'd0, fail_s, pass_s, sleep_s, ctl_q[0]};
      end else if (shift_dr) begin
        byp_q  <= tdi;
        if (ir == IR_IDCODE)  id_sh  <= {tdi, id_sh[31:1]};
        if (ir == IR_SBA)     sba_sh <= {tdi, sba_sh[65:1]};
        if (ir == IR_DBGCTRL) ctl_sh <= {tdi, ctl_sh[7:1]};
      end else if (update_dr) begin
        if (ir == IR_SBA && sba_sh[65:64] != 2'b00 && !tck_busy) begin
          cmd_op_q    <= sba_sh[65:64];
          cmd_wdata_q <= sba_sh[63:32];
          cmd_addr_q  <= sba_sh[31:0];
          req_tgl_q   <= ~req_tgl_q;
        end
        if (ir == IR_DBGCTRL) ctl_q <= ctl_sh;
      end
    end
  end

  always_comb begin
    case (ir)
      IR_IDCODE:  dr_tdo = id_sh[0];
      IR_SBA:     dr_tdo = sba_sh[0];
      IR_DBGCTRL: dr_tdo = ctl_sh[0];
      default:    dr_tdo = byp_q;
    endcase
  end

  // ------------------------------------------------------------ sys domain
  sfv_sync u_s_req (.clk, .rst_n, .d(req_tgl_q), .q(req_tgl_s));
  sfv_sync u_s_hold (.clk, .rst_n, .d(ctl_q[0]), .q(cpu_hold));
  sfv_sync u_s_srst (.clk, .rst_n, .d(ctl_q[1]), .q(sys_reset_req));
  sfv_sync u_s_bovr (.clk, .rst_n, .d(ctl_q[2]), .q(boot_ovr));
  sfv_sync u_s_bm0  (.clk, .rst_n, .d(ctl_q[3]), .q(boot_ovr_mode[0]));
  sfv_sync u_s_bm1  (.clk, .rst_n, .d(ctl_q[4]), .q(boot_ovr_mode[1]));

  typedef enum logic [1:0] {D_IDLE, D_REQ, D_WAIT} dst_e;
  dst_e ds;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      ds <= D_IDLE; req_tgl_seen_q <= 1'b0; ack_tgl_q_sys <= 1'b0;
      res_rdata_q <= '0; res_err_q <= 1'b0;
    end else begin
      case (ds)
        D_IDLE: if (req_tgl_s != req_tgl_seen_q) begin
          req_tgl_seen_q <= req_tgl_s;
          ds <= D_REQ;
        end
        D_REQ:  if (m_gnt) ds <= D_WAIT;
        default: if (m_rvalid) begin
          res_rdata_q   <= m_rdata;
          res_err_q     <= m_err;
          ack_tgl_q_sys <= ~ack_tgl_q_sys;
          ds            <= D_IDLE;
        end
      endcase
    end
  end
  assign m_req   = (ds == D_REQ);
  assign m_addr  = {cmd_addr_q[31:2], 2'b00};
  assign m_we    = (cmd_op_q == 2'd2);
  assign m_be    = 4'b1111;
  assign m_wdata = cmd_wdata_q;
endmodule

`default_nettype wire
