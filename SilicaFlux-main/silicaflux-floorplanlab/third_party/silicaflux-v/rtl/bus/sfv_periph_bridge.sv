// =============================================================================
// SilicaFlux-V :: sfv_periph_bridge -- SFB slave -> register bus
//
// Register bus (per 4 KiB page p, p = addr[16:12]):
//   rb_sel[p]  one-cycle access strobe (req & gnt), rb_we, rb_addr[11:0],
//   rb_wdata, broadcast to all pages; the page returns rb_rdata/rb_err
//   combinationally in the same cycle.  Write and read side effects occur at
//   the end of the strobe cycle.  The bridge registers the response
//   (rvalid one cycle after grant) and never stalls (gnt = 1).
// Rules: peripheral registers are 32-bit; a write with be != 4'b1111, or any
//   access to a page not present in PAGE_EN, returns a bus error and has no
//   side effect.
// =============================================================================
`default_nettype none

module sfv_periph_bridge #(
  parameter int          NP      = 32,
  parameter logic [31:0] PAGE_EN = 32'h0003_003F
) (
  input  wire logic           clk,
  input  wire logic           rst_n,
  // SFB slave
  input  wire logic           req,
  output logic                gnt,
  input  wire logic [31:0]    addr,
  input  wire logic           we,
  input  wire logic [3:0]     be,
  input  wire logic [31:0]    wdata,
  output logic                rvalid,
  output logic [31:0]         rdata,
  output logic                err,
  // register bus
  output logic [NP-1:0]       rb_sel,
  output logic                rb_we,
  output logic [11:0]         rb_addr,
  output logic [31:0]         rb_wdata,
  input  wire logic [NP*32-1:0] rb_rdata,
  input  wire logic [NP-1:0]  rb_err
);
  wire [4:0] page    = addr[16:12];
  wire       present = PAGE_EN[page];
  wire       bad_be  = we && (be != 4'b1111);
  wire       go      = req && present && !bad_be;

  assign gnt      = 1'b1;
  assign rb_we    = we;
  assign rb_addr  = addr[11:0];
  assign rb_wdata = wdata;
  always_comb begin
    rb_sel = '0;
    if (go) rb_sel[page] = 1'b1;
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rvalid <= 1'b0;
      rdata  <= '0;
      err    <= 1'b0;
    end else begin
      rvalid <= req;
      rdata  <= (go && !we) ? rb_rdata[page*32 +: 32] : 32'd0;
      err    <= req && (!go || rb_err[page]);
    end
  end
endmodule

`default_nettype wire
