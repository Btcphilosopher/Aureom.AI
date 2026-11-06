// =============================================================================
// SilicaFlux DataFabric :: dma_validate -- start-time transfer validation
//
// Combinational check of a transfer descriptor BEFORE any bus access (the
// VALIDATE state of both engines).  First failing rule wins:
//   ZERO_LENGTH   len == 0
//   LENGTH        len > 2**MAX_LEN_LOG2
//   SRC_ALIGN     src not aligned to the data width (DW/8 bytes)
//   DST_ALIGN     dst not aligned to the data width
//   SRC_OVERFLOW  src + len > 2**32 (the source range would wrap)
//   DST_OVERFLOW  dst + len > 2**32
//   OVERLAP       [src, src+len) and [dst, dst+len) intersect (version 1 does
//                 not implement memmove semantics, so any overlap, including
//                 src == dst, is rejected)
// Region existence is NOT checked here (the DMA has no memory map): an
// unmapped or protected address produces a bus error on first access.
// =============================================================================
`include "dma_defs.svh"
`default_nettype none

module dma_validate #(
  parameter int DW           = 32,
  parameter int MAX_LEN_LOG2 = 24,
  localparam int OFF         = (DW > 8) ? $clog2(DW / 8) : 1
) (
  input  wire logic [31:0] src,
  input  wire logic [31:0] dst,
  input  wire logic [31:0] len,
  output logic [3:0]       code
);
  logic [32:0] s_end, d_end;       // exclusive end addresses, 33 bit
  logic        too_long;
  assign s_end = {1'b0, src} + {1'b0, len};
  assign d_end = {1'b0, dst} + {1'b0, len};
  assign too_long = ({1'b0, len} > (33'd1 << MAX_LEN_LOG2));

  always_comb begin
    code = `DMA_ERR_NONE;
    if (len == 32'd0)                                   code = `DMA_ERR_ZERO_LENGTH;
    else if (too_long)                                  code = `DMA_ERR_LENGTH;
    else if (DW > 8 && src[OFF-1:0] != '0)              code = `DMA_ERR_SRC_ALIGN;
    else if (DW > 8 && dst[OFF-1:0] != '0)              code = `DMA_ERR_DST_ALIGN;
    else if (s_end > 33'h1_0000_0000)                   code = `DMA_ERR_SRC_OVERFLOW;
    else if (d_end > 33'h1_0000_0000)                   code = `DMA_ERR_DST_OVERFLOW;
    else if (({1'b0, src} < d_end) && ({1'b0, dst} < s_end)) code = `DMA_ERR_OVERLAP;
  end
endmodule

`default_nettype wire
