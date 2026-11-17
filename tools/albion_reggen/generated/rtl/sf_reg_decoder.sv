// =============================================================================
//  sf_reg_decoder.sv -- address decode, region check, permission verdict
//  GENERATED FILE -- DO NOT EDIT.  Edit the register definition instead.
//  generator       : albion_reggen 1.0.0 (definition schema 1)
//  register map   : silicaflux_regs v1.0
//  semantic hash  : 99481283139d2dc0690f688325c0631d115617fc66330be250e7a560f5e43d39
//  definition hash: 322ccd28a62e3936e355677a25425f8609977deab94841f7ce2049bcd96525ba
//  Bus protocol    : Albion Link Protocol v1 (AlbionCore sf_albion_pkg)
// =============================================================================

`default_nettype none

// Pure combinational.  Inputs: the flat ALP request.  Outputs:
//   reg_sel_o  one bit per register instance whose byte lanes the request touches
//   status_o   verdict that does NOT depend on hardware state, in ALP precedence order:
//                1. address outside every peripheral window       -> DECODE_ERR
//                2. region/peripheral access check (sf_access_check_bits):
//                   read/write/exec, privilege, security          -> ACCESS_DENIED
//                                               device mem type  -> BAD_ATTR
//                3. an enabled byte lane that belongs to no register -> DECODE_ERR
//                4. write to a register with no writable field, or
//                   read of a register with no readable field     -> ACCESS_DENIED
// The ALP legality check (opcode, alignment, byte enables, attributes, domain) has
// precedence over all of this and is applied by sf_reg_interface.
/* verilator lint_off UNUSEDSIGNAL */
module sf_reg_decoder (
  input  wire logic [sf_albion_pkg::SF_REQ_W-1:0]    req_i,
  output logic      [192:0]                      reg_sel_o,
  output logic      [sf_albion_pkg::SF_STATUS_W-1:0] status_o
);
  logic [63:0] addr;
  logic [15:0] be;
  logic        is_write;
  logic        is_read;
  assign addr     = req_i[sf_albion_pkg::SF_REQ_ADDR_LSB +: sf_albion_pkg::SF_ADDR_W];
  assign be       = req_i[sf_albion_pkg::SF_REQ_BE_LSB   +: sf_albion_pkg::SF_BE_W];
  assign is_write = (req_i[sf_albion_pkg::SF_REQ_OP_LSB +: sf_albion_pkg::SF_OP_W] == sf_albion_pkg::SF_OP_WRITE);
  assign is_read  = (req_i[sf_albion_pkg::SF_REQ_OP_LSB +: sf_albion_pkg::SF_OP_W] == sf_albion_pkg::SF_OP_READ);

  // ---- peripheral windows (8)
  logic [7:0] p_hit;
  assign p_hit[0] = (addr[63:12] == sf_reg_pkg::SF_DMA_BASE[63:12]);  // dma
  assign p_hit[1] = (addr[63:12] == sf_reg_pkg::SF_TENSOR_BASE[63:12]);  // tensor
  assign p_hit[2] = (addr[63:12] == sf_reg_pkg::SF_VECTOR_BASE[63:12]);  // vector
  assign p_hit[3] = (addr[63:12] == sf_reg_pkg::SF_PERF_BASE[63:12]);  // perf
  assign p_hit[4] = (addr[63:12] == sf_reg_pkg::SF_SYSID_BASE[63:12]);  // sysid
  assign p_hit[5] = (addr[63:12] == sf_reg_pkg::SF_INTC_BASE[63:12]);  // intc
  assign p_hit[6] = (addr[63:12] == sf_reg_pkg::SF_CLKRST_BASE[63:12]);  // clkrst
  assign p_hit[7] = (addr[63:12] == sf_reg_pkg::SF_SRAMC_BASE[63:12]);  // sramc

  // ---- register instances (193): word hit and byte-lane touch
  logic [192:0] word_hit;
  logic [15:0] covered;
  assign word_hit[0] = (addr[63:4] == sf_reg_pkg::SF_DMA_SRC_ADDR[63:4]);  // dma.SRC
  assign word_hit[1] = (addr[63:4] == sf_reg_pkg::SF_DMA_DST_ADDR[63:4]);  // dma.DST
  assign word_hit[2] = (addr[63:4] == sf_reg_pkg::SF_DMA_LEN_ADDR[63:4]);  // dma.LEN
  assign word_hit[3] = (addr[63:4] == sf_reg_pkg::SF_DMA_TAG_ADDR[63:4]);  // dma.TAG
  assign word_hit[4] = (addr[63:4] == sf_reg_pkg::SF_DMA_CTRL_ADDR[63:4]);  // dma.CTRL
  assign word_hit[5] = (addr[63:4] == sf_reg_pkg::SF_DMA_START_ADDR[63:4]);  // dma.START
  assign word_hit[6] = (addr[63:4] == sf_reg_pkg::SF_DMA_STATUS_ADDR[63:4]);  // dma.STATUS
  assign word_hit[7] = (addr[63:4] == sf_reg_pkg::SF_DMA_BYTES_DONE_ADDR[63:4]);  // dma.BYTES_DONE
  assign word_hit[8] = (addr[63:4] == sf_reg_pkg::SF_DMA_CPL_STATUS_ADDR[63:4]);  // dma.CPL_STATUS
  assign word_hit[9] = (addr[63:4] == sf_reg_pkg::SF_DMA_CPL_ERR_ADDR_ADDR[63:4]);  // dma.CPL_ERR_ADDR
  assign word_hit[10] = (addr[63:4] == sf_reg_pkg::SF_DMA_CPL_BYTES_ADDR[63:4]);  // dma.CPL_BYTES
  assign word_hit[11] = (addr[63:4] == sf_reg_pkg::SF_DMA_CPL_POP_ADDR[63:4]);  // dma.CPL_POP
  assign word_hit[12] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_CTRL_ADDR[63:4]);  // dma.PERF_CTRL
  assign word_hit[13] = (addr[63:4] == sf_reg_pkg::SF_DMA_INT_ENABLE_ADDR[63:4]);  // dma.INT_ENABLE
  assign word_hit[14] = (addr[63:4] == sf_reg_pkg::SF_DMA_INT_STATUS_ADDR[63:4]);  // dma.INT_STATUS
  assign word_hit[15] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_0_ADDR[63:4]);  // dma.PERF[0]
  assign word_hit[16] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_1_ADDR[63:4]);  // dma.PERF[1]
  assign word_hit[17] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_2_ADDR[63:4]);  // dma.PERF[2]
  assign word_hit[18] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_3_ADDR[63:4]);  // dma.PERF[3]
  assign word_hit[19] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_4_ADDR[63:4]);  // dma.PERF[4]
  assign word_hit[20] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_5_ADDR[63:4]);  // dma.PERF[5]
  assign word_hit[21] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_6_ADDR[63:4]);  // dma.PERF[6]
  assign word_hit[22] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_7_ADDR[63:4]);  // dma.PERF[7]
  assign word_hit[23] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_8_ADDR[63:4]);  // dma.PERF[8]
  assign word_hit[24] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_9_ADDR[63:4]);  // dma.PERF[9]
  assign word_hit[25] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_10_ADDR[63:4]);  // dma.PERF[10]
  assign word_hit[26] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_11_ADDR[63:4]);  // dma.PERF[11]
  assign word_hit[27] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_12_ADDR[63:4]);  // dma.PERF[12]
  assign word_hit[28] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_13_ADDR[63:4]);  // dma.PERF[13]
  assign word_hit[29] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_14_ADDR[63:4]);  // dma.PERF[14]
  assign word_hit[30] = (addr[63:4] == sf_reg_pkg::SF_DMA_PERF_15_ADDR[63:4]);  // dma.PERF[15]
  assign word_hit[31] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_ID_ADDR[63:4]);  // tensor.ID
  assign word_hit[32] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_INFO_ADDR[63:4]);  // tensor.INFO
  assign word_hit[33] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_CAPS_ADDR[63:4]);  // tensor.CAPS
  assign word_hit[34] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_OPBUF_ADDR[63:4]);  // tensor.OPBUF
  assign word_hit[35] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_MEM_LO_ADDR[63:4]);  // tensor.MEM_LO
  assign word_hit[36] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_MEM_LAST_ADDR[63:4]);  // tensor.MEM_LAST
  assign word_hit[37] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_CTRL_ADDR[63:4]);  // tensor.CTRL
  assign word_hit[38] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_STATUS_ADDR[63:4]);  // tensor.STATUS
  assign word_hit[39] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_INT_ENABLE_ADDR[63:4]);  // tensor.INT_ENABLE
  assign word_hit[40] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_INT_STATUS_ADDR[63:4]);  // tensor.INT_STATUS
  assign word_hit[41] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_SUBMITTED_ADDR[63:4]);  // tensor.SUBMITTED
  assign word_hit[42] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_KMAX_ADDR[63:4]);  // tensor.KMAX
  assign word_hit[43] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DESC_0_ADDR[63:4]);  // tensor.DESC[0]
  assign word_hit[44] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DESC_1_ADDR[63:4]);  // tensor.DESC[1]
  assign word_hit[45] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DESC_2_ADDR[63:4]);  // tensor.DESC[2]
  assign word_hit[46] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DESC_3_ADDR[63:4]);  // tensor.DESC[3]
  assign word_hit[47] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DESC_4_ADDR[63:4]);  // tensor.DESC[4]
  assign word_hit[48] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DESC_5_ADDR[63:4]);  // tensor.DESC[5]
  assign word_hit[49] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DESC_6_ADDR[63:4]);  // tensor.DESC[6]
  assign word_hit[50] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DESC_7_ADDR[63:4]);  // tensor.DESC[7]
  assign word_hit[51] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DESC_8_ADDR[63:4]);  // tensor.DESC[8]
  assign word_hit[52] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DESC_9_ADDR[63:4]);  // tensor.DESC[9]
  assign word_hit[53] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DESC_10_ADDR[63:4]);  // tensor.DESC[10]
  assign word_hit[54] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DESC_11_ADDR[63:4]);  // tensor.DESC[11]
  assign word_hit[55] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DOORBELL_ADDR[63:4]);  // tensor.DOORBELL
  assign word_hit[56] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_CPL_0_ADDR[63:4]);  // tensor.CPL[0]
  assign word_hit[57] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_CPL_1_ADDR[63:4]);  // tensor.CPL[1]
  assign word_hit[58] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_CPL_2_ADDR[63:4]);  // tensor.CPL[2]
  assign word_hit[59] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_CPL_3_ADDR[63:4]);  // tensor.CPL[3]
  assign word_hit[60] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_CPL_4_ADDR[63:4]);  // tensor.CPL[4]
  assign word_hit[61] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_CPL_5_ADDR[63:4]);  // tensor.CPL[5]
  assign word_hit[62] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_CPL_POP_ADDR[63:4]);  // tensor.CPL_POP
  assign word_hit[63] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_0_ADDR[63:4]);  // tensor.PERF[0]
  assign word_hit[64] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_1_ADDR[63:4]);  // tensor.PERF[1]
  assign word_hit[65] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_2_ADDR[63:4]);  // tensor.PERF[2]
  assign word_hit[66] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_3_ADDR[63:4]);  // tensor.PERF[3]
  assign word_hit[67] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_4_ADDR[63:4]);  // tensor.PERF[4]
  assign word_hit[68] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_5_ADDR[63:4]);  // tensor.PERF[5]
  assign word_hit[69] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_6_ADDR[63:4]);  // tensor.PERF[6]
  assign word_hit[70] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_7_ADDR[63:4]);  // tensor.PERF[7]
  assign word_hit[71] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_8_ADDR[63:4]);  // tensor.PERF[8]
  assign word_hit[72] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_9_ADDR[63:4]);  // tensor.PERF[9]
  assign word_hit[73] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_10_ADDR[63:4]);  // tensor.PERF[10]
  assign word_hit[74] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_11_ADDR[63:4]);  // tensor.PERF[11]
  assign word_hit[75] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_12_ADDR[63:4]);  // tensor.PERF[12]
  assign word_hit[76] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_13_ADDR[63:4]);  // tensor.PERF[13]
  assign word_hit[77] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_14_ADDR[63:4]);  // tensor.PERF[14]
  assign word_hit[78] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_15_ADDR[63:4]);  // tensor.PERF[15]
  assign word_hit[79] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_16_ADDR[63:4]);  // tensor.PERF[16]
  assign word_hit[80] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_17_ADDR[63:4]);  // tensor.PERF[17]
  assign word_hit[81] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_18_ADDR[63:4]);  // tensor.PERF[18]
  assign word_hit[82] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_PERF_19_ADDR[63:4]);  // tensor.PERF[19]
  assign word_hit[83] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_0_ADDR[63:4]);  // tensor.DMA_PERF[0]
  assign word_hit[84] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_1_ADDR[63:4]);  // tensor.DMA_PERF[1]
  assign word_hit[85] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_2_ADDR[63:4]);  // tensor.DMA_PERF[2]
  assign word_hit[86] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_3_ADDR[63:4]);  // tensor.DMA_PERF[3]
  assign word_hit[87] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_4_ADDR[63:4]);  // tensor.DMA_PERF[4]
  assign word_hit[88] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_5_ADDR[63:4]);  // tensor.DMA_PERF[5]
  assign word_hit[89] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_6_ADDR[63:4]);  // tensor.DMA_PERF[6]
  assign word_hit[90] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_7_ADDR[63:4]);  // tensor.DMA_PERF[7]
  assign word_hit[91] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_8_ADDR[63:4]);  // tensor.DMA_PERF[8]
  assign word_hit[92] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_9_ADDR[63:4]);  // tensor.DMA_PERF[9]
  assign word_hit[93] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_10_ADDR[63:4]);  // tensor.DMA_PERF[10]
  assign word_hit[94] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_11_ADDR[63:4]);  // tensor.DMA_PERF[11]
  assign word_hit[95] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_12_ADDR[63:4]);  // tensor.DMA_PERF[12]
  assign word_hit[96] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_13_ADDR[63:4]);  // tensor.DMA_PERF[13]
  assign word_hit[97] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_14_ADDR[63:4]);  // tensor.DMA_PERF[14]
  assign word_hit[98] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_15_ADDR[63:4]);  // tensor.DMA_PERF[15]
  assign word_hit[99] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_16_ADDR[63:4]);  // tensor.DMA_PERF[16]
  assign word_hit[100] = (addr[63:4] == sf_reg_pkg::SF_TENSOR_DMA_PERF_17_ADDR[63:4]);  // tensor.DMA_PERF[17]
  assign word_hit[101] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_ID_ADDR[63:4]);  // vector.ID
  assign word_hit[102] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_INFO_ADDR[63:4]);  // vector.INFO
  assign word_hit[103] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_CTRL_ADDR[63:4]);  // vector.CTRL
  assign word_hit[104] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_STATUS_ADDR[63:4]);  // vector.STATUS
  assign word_hit[105] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_INT_ENABLE_ADDR[63:4]);  // vector.INT_ENABLE
  assign word_hit[106] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_INT_STATUS_ADDR[63:4]);  // vector.INT_STATUS
  assign word_hit[107] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_SUBMITTED_ADDR[63:4]);  // vector.SUBMITTED
  assign word_hit[108] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_DESC_0_ADDR[63:4]);  // vector.DESC[0]
  assign word_hit[109] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_DESC_1_ADDR[63:4]);  // vector.DESC[1]
  assign word_hit[110] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_DESC_2_ADDR[63:4]);  // vector.DESC[2]
  assign word_hit[111] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_DESC_3_ADDR[63:4]);  // vector.DESC[3]
  assign word_hit[112] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_DESC_4_ADDR[63:4]);  // vector.DESC[4]
  assign word_hit[113] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_DESC_5_ADDR[63:4]);  // vector.DESC[5]
  assign word_hit[114] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_DESC_6_ADDR[63:4]);  // vector.DESC[6]
  assign word_hit[115] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_DESC_7_ADDR[63:4]);  // vector.DESC[7]
  assign word_hit[116] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_DOORBELL_ADDR[63:4]);  // vector.DOORBELL
  assign word_hit[117] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_CPL_0_ADDR[63:4]);  // vector.CPL[0]
  assign word_hit[118] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_CPL_1_ADDR[63:4]);  // vector.CPL[1]
  assign word_hit[119] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_CPL_2_ADDR[63:4]);  // vector.CPL[2]
  assign word_hit[120] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_CPL_3_ADDR[63:4]);  // vector.CPL[3]
  assign word_hit[121] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_CPL_POP_ADDR[63:4]);  // vector.CPL_POP
  assign word_hit[122] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_0_ADDR[63:4]);  // vector.PERF[0]
  assign word_hit[123] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_1_ADDR[63:4]);  // vector.PERF[1]
  assign word_hit[124] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_2_ADDR[63:4]);  // vector.PERF[2]
  assign word_hit[125] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_3_ADDR[63:4]);  // vector.PERF[3]
  assign word_hit[126] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_4_ADDR[63:4]);  // vector.PERF[4]
  assign word_hit[127] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_5_ADDR[63:4]);  // vector.PERF[5]
  assign word_hit[128] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_6_ADDR[63:4]);  // vector.PERF[6]
  assign word_hit[129] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_7_ADDR[63:4]);  // vector.PERF[7]
  assign word_hit[130] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_8_ADDR[63:4]);  // vector.PERF[8]
  assign word_hit[131] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_9_ADDR[63:4]);  // vector.PERF[9]
  assign word_hit[132] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_10_ADDR[63:4]);  // vector.PERF[10]
  assign word_hit[133] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_11_ADDR[63:4]);  // vector.PERF[11]
  assign word_hit[134] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_12_ADDR[63:4]);  // vector.PERF[12]
  assign word_hit[135] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_13_ADDR[63:4]);  // vector.PERF[13]
  assign word_hit[136] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_14_ADDR[63:4]);  // vector.PERF[14]
  assign word_hit[137] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_15_ADDR[63:4]);  // vector.PERF[15]
  assign word_hit[138] = (addr[63:4] == sf_reg_pkg::SF_VECTOR_PERF_16_ADDR[63:4]);  // vector.PERF[16]
  assign word_hit[139] = (addr[63:4] == sf_reg_pkg::SF_PERF_CTRL_ADDR[63:4]);  // perf.CTRL
  assign word_hit[140] = (addr[63:4] == sf_reg_pkg::SF_PERF_STATUS_ADDR[63:4]);  // perf.STATUS
  assign word_hit[141] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_0_ADDR[63:4]);  // perf.CNT[0]
  assign word_hit[142] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_1_ADDR[63:4]);  // perf.CNT[1]
  assign word_hit[143] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_2_ADDR[63:4]);  // perf.CNT[2]
  assign word_hit[144] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_3_ADDR[63:4]);  // perf.CNT[3]
  assign word_hit[145] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_4_ADDR[63:4]);  // perf.CNT[4]
  assign word_hit[146] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_5_ADDR[63:4]);  // perf.CNT[5]
  assign word_hit[147] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_6_ADDR[63:4]);  // perf.CNT[6]
  assign word_hit[148] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_7_ADDR[63:4]);  // perf.CNT[7]
  assign word_hit[149] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_8_ADDR[63:4]);  // perf.CNT[8]
  assign word_hit[150] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_9_ADDR[63:4]);  // perf.CNT[9]
  assign word_hit[151] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_10_ADDR[63:4]);  // perf.CNT[10]
  assign word_hit[152] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_11_ADDR[63:4]);  // perf.CNT[11]
  assign word_hit[153] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_12_ADDR[63:4]);  // perf.CNT[12]
  assign word_hit[154] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_13_ADDR[63:4]);  // perf.CNT[13]
  assign word_hit[155] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_14_ADDR[63:4]);  // perf.CNT[14]
  assign word_hit[156] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_15_ADDR[63:4]);  // perf.CNT[15]
  assign word_hit[157] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_16_ADDR[63:4]);  // perf.CNT[16]
  assign word_hit[158] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_17_ADDR[63:4]);  // perf.CNT[17]
  assign word_hit[159] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_18_ADDR[63:4]);  // perf.CNT[18]
  assign word_hit[160] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_19_ADDR[63:4]);  // perf.CNT[19]
  assign word_hit[161] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_20_ADDR[63:4]);  // perf.CNT[20]
  assign word_hit[162] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_21_ADDR[63:4]);  // perf.CNT[21]
  assign word_hit[163] = (addr[63:4] == sf_reg_pkg::SF_PERF_CNT_22_ADDR[63:4]);  // perf.CNT[22]
  assign word_hit[164] = (addr[63:4] == sf_reg_pkg::SF_SYSID_ID_ADDR[63:4]);  // sysid.ID
  assign word_hit[165] = (addr[63:4] == sf_reg_pkg::SF_SYSID_REGMAP_VERSION_ADDR[63:4]);  // sysid.REGMAP_VERSION
  assign word_hit[166] = (addr[63:4] == sf_reg_pkg::SF_SYSID_ALP_VERSION_ADDR[63:4]);  // sysid.ALP_VERSION
  assign word_hit[167] = (addr[63:4] == sf_reg_pkg::SF_SYSID_LIB_VERSION_ADDR[63:4]);  // sysid.LIB_VERSION
  assign word_hit[168] = (addr[63:4] == sf_reg_pkg::SF_SYSID_ALP_CAPS_ADDR[63:4]);  // sysid.ALP_CAPS
  assign word_hit[169] = (addr[63:4] == sf_reg_pkg::SF_SYSID_REGMAP_HASH_ADDR[63:4]);  // sysid.REGMAP_HASH
  assign word_hit[170] = (addr[63:4] == sf_reg_pkg::SF_SYSID_BUILD_ID_ADDR[63:4]);  // sysid.BUILD_ID
  assign word_hit[171] = (addr[63:4] == sf_reg_pkg::SF_INTC_PENDING_ADDR[63:4]);  // intc.PENDING
  assign word_hit[172] = (addr[63:4] == sf_reg_pkg::SF_INTC_ENABLE_ADDR[63:4]);  // intc.ENABLE
  assign word_hit[173] = (addr[63:4] == sf_reg_pkg::SF_INTC_CLAIM_ADDR[63:4]);  // intc.CLAIM
  assign word_hit[174] = (addr[63:4] == sf_reg_pkg::SF_INTC_SWPEND_ADDR[63:4]);  // intc.SWPEND
  assign word_hit[175] = (addr[63:4] == sf_reg_pkg::SF_INTC_THRESHOLD_ADDR[63:4]);  // intc.THRESHOLD
  assign word_hit[176] = (addr[63:4] == sf_reg_pkg::SF_INTC_ACTIVE_ADDR[63:4]);  // intc.ACTIVE
  assign word_hit[177] = (addr[63:4] == sf_reg_pkg::SF_INTC_PRIO0_ADDR[63:4]);  // intc.PRIO0
  assign word_hit[178] = (addr[63:4] == sf_reg_pkg::SF_INTC_PRIO1_ADDR[63:4]);  // intc.PRIO1
  assign word_hit[179] = (addr[63:4] == sf_reg_pkg::SF_CLKRST_ID_ADDR[63:4]);  // clkrst.ID
  assign word_hit[180] = (addr[63:4] == sf_reg_pkg::SF_CLKRST_CONFIG_ADDR[63:4]);  // clkrst.CONFIG
  assign word_hit[181] = (addr[63:4] == sf_reg_pkg::SF_CLKRST_STATUS_ADDR[63:4]);  // clkrst.STATUS
  assign word_hit[182] = (addr[63:4] == sf_reg_pkg::SF_CLKRST_CAUSE_ADDR[63:4]);  // clkrst.CAUSE
  assign word_hit[183] = (addr[63:4] == sf_reg_pkg::SF_CLKRST_RST_INFO_ADDR[63:4]);  // clkrst.RST_INFO
  assign word_hit[184] = (addr[63:4] == sf_reg_pkg::SF_CLKRST_CLK_EN_ADDR[63:4]);  // clkrst.CLK_EN
  assign word_hit[185] = (addr[63:4] == sf_reg_pkg::SF_CLKRST_CLK_STAT_ADDR[63:4]);  // clkrst.CLK_STAT
  assign word_hit[186] = (addr[63:4] == sf_reg_pkg::SF_CLKRST_WDOG_CNT_ADDR[63:4]);  // clkrst.WDOG_CNT
  assign word_hit[187] = (addr[63:4] == sf_reg_pkg::SF_CLKRST_CLK_MEAS_ADDR[63:4]);  // clkrst.CLK_MEAS
  assign word_hit[188] = (addr[63:4] == sf_reg_pkg::SF_CLKRST_IRQ_ADDR[63:4]);  // clkrst.IRQ
  assign word_hit[189] = (addr[63:4] == sf_reg_pkg::SF_SRAMC_CTRL_ADDR[63:4]);  // sramc.CTRL
  assign word_hit[190] = (addr[63:4] == sf_reg_pkg::SF_SRAMC_STATUS_ADDR[63:4]);  // sramc.STATUS
  assign word_hit[191] = (addr[63:4] == sf_reg_pkg::SF_SRAMC_PERF_CTRL_ADDR[63:4]);  // sramc.PERF_CTRL
  assign word_hit[192] = (addr[63:4] == sf_reg_pkg::SF_SRAMC_PERF_VAL_ADDR[63:4]);  // sramc.PERF_VAL
  assign reg_sel_o[0] = word_hit[0] && (|(be & 16'h000f));
  assign reg_sel_o[1] = word_hit[1] && (|(be & 16'h00f0));
  assign reg_sel_o[2] = word_hit[2] && (|(be & 16'h0f00));
  assign reg_sel_o[3] = word_hit[3] && (|(be & 16'hf000));
  assign reg_sel_o[4] = word_hit[4] && (|(be & 16'h000f));
  assign reg_sel_o[5] = word_hit[5] && (|(be & 16'h00f0));
  assign reg_sel_o[6] = word_hit[6] && (|(be & 16'h0f00));
  assign reg_sel_o[7] = word_hit[7] && (|(be & 16'hf000));
  assign reg_sel_o[8] = word_hit[8] && (|(be & 16'h000f));
  assign reg_sel_o[9] = word_hit[9] && (|(be & 16'h00f0));
  assign reg_sel_o[10] = word_hit[10] && (|(be & 16'h0f00));
  assign reg_sel_o[11] = word_hit[11] && (|(be & 16'hf000));
  assign reg_sel_o[12] = word_hit[12] && (|(be & 16'h000f));
  assign reg_sel_o[13] = word_hit[13] && (|(be & 16'h00f0));
  assign reg_sel_o[14] = word_hit[14] && (|(be & 16'h0f00));
  assign reg_sel_o[15] = word_hit[15] && (|(be & 16'h000f));
  assign reg_sel_o[16] = word_hit[16] && (|(be & 16'h00f0));
  assign reg_sel_o[17] = word_hit[17] && (|(be & 16'h0f00));
  assign reg_sel_o[18] = word_hit[18] && (|(be & 16'hf000));
  assign reg_sel_o[19] = word_hit[19] && (|(be & 16'h000f));
  assign reg_sel_o[20] = word_hit[20] && (|(be & 16'h00f0));
  assign reg_sel_o[21] = word_hit[21] && (|(be & 16'h0f00));
  assign reg_sel_o[22] = word_hit[22] && (|(be & 16'hf000));
  assign reg_sel_o[23] = word_hit[23] && (|(be & 16'h000f));
  assign reg_sel_o[24] = word_hit[24] && (|(be & 16'h00f0));
  assign reg_sel_o[25] = word_hit[25] && (|(be & 16'h0f00));
  assign reg_sel_o[26] = word_hit[26] && (|(be & 16'hf000));
  assign reg_sel_o[27] = word_hit[27] && (|(be & 16'h000f));
  assign reg_sel_o[28] = word_hit[28] && (|(be & 16'h00f0));
  assign reg_sel_o[29] = word_hit[29] && (|(be & 16'h0f00));
  assign reg_sel_o[30] = word_hit[30] && (|(be & 16'hf000));
  assign reg_sel_o[31] = word_hit[31] && (|(be & 16'h000f));
  assign reg_sel_o[32] = word_hit[32] && (|(be & 16'h00f0));
  assign reg_sel_o[33] = word_hit[33] && (|(be & 16'h0f00));
  assign reg_sel_o[34] = word_hit[34] && (|(be & 16'hf000));
  assign reg_sel_o[35] = word_hit[35] && (|(be & 16'h000f));
  assign reg_sel_o[36] = word_hit[36] && (|(be & 16'h00f0));
  assign reg_sel_o[37] = word_hit[37] && (|(be & 16'h0f00));
  assign reg_sel_o[38] = word_hit[38] && (|(be & 16'hf000));
  assign reg_sel_o[39] = word_hit[39] && (|(be & 16'h000f));
  assign reg_sel_o[40] = word_hit[40] && (|(be & 16'h00f0));
  assign reg_sel_o[41] = word_hit[41] && (|(be & 16'h0f00));
  assign reg_sel_o[42] = word_hit[42] && (|(be & 16'hf000));
  assign reg_sel_o[43] = word_hit[43] && (|(be & 16'h000f));
  assign reg_sel_o[44] = word_hit[44] && (|(be & 16'h00f0));
  assign reg_sel_o[45] = word_hit[45] && (|(be & 16'h0f00));
  assign reg_sel_o[46] = word_hit[46] && (|(be & 16'hf000));
  assign reg_sel_o[47] = word_hit[47] && (|(be & 16'h000f));
  assign reg_sel_o[48] = word_hit[48] && (|(be & 16'h00f0));
  assign reg_sel_o[49] = word_hit[49] && (|(be & 16'h0f00));
  assign reg_sel_o[50] = word_hit[50] && (|(be & 16'hf000));
  assign reg_sel_o[51] = word_hit[51] && (|(be & 16'h000f));
  assign reg_sel_o[52] = word_hit[52] && (|(be & 16'h00f0));
  assign reg_sel_o[53] = word_hit[53] && (|(be & 16'h0f00));
  assign reg_sel_o[54] = word_hit[54] && (|(be & 16'hf000));
  assign reg_sel_o[55] = word_hit[55] && (|(be & 16'h000f));
  assign reg_sel_o[56] = word_hit[56] && (|(be & 16'h000f));
  assign reg_sel_o[57] = word_hit[57] && (|(be & 16'h00f0));
  assign reg_sel_o[58] = word_hit[58] && (|(be & 16'h0f00));
  assign reg_sel_o[59] = word_hit[59] && (|(be & 16'hf000));
  assign reg_sel_o[60] = word_hit[60] && (|(be & 16'h000f));
  assign reg_sel_o[61] = word_hit[61] && (|(be & 16'h00f0));
  assign reg_sel_o[62] = word_hit[62] && (|(be & 16'h0f00));
  assign reg_sel_o[63] = word_hit[63] && (|(be & 16'h000f));
  assign reg_sel_o[64] = word_hit[64] && (|(be & 16'h00f0));
  assign reg_sel_o[65] = word_hit[65] && (|(be & 16'h0f00));
  assign reg_sel_o[66] = word_hit[66] && (|(be & 16'hf000));
  assign reg_sel_o[67] = word_hit[67] && (|(be & 16'h000f));
  assign reg_sel_o[68] = word_hit[68] && (|(be & 16'h00f0));
  assign reg_sel_o[69] = word_hit[69] && (|(be & 16'h0f00));
  assign reg_sel_o[70] = word_hit[70] && (|(be & 16'hf000));
  assign reg_sel_o[71] = word_hit[71] && (|(be & 16'h000f));
  assign reg_sel_o[72] = word_hit[72] && (|(be & 16'h00f0));
  assign reg_sel_o[73] = word_hit[73] && (|(be & 16'h0f00));
  assign reg_sel_o[74] = word_hit[74] && (|(be & 16'hf000));
  assign reg_sel_o[75] = word_hit[75] && (|(be & 16'h000f));
  assign reg_sel_o[76] = word_hit[76] && (|(be & 16'h00f0));
  assign reg_sel_o[77] = word_hit[77] && (|(be & 16'h0f00));
  assign reg_sel_o[78] = word_hit[78] && (|(be & 16'hf000));
  assign reg_sel_o[79] = word_hit[79] && (|(be & 16'h000f));
  assign reg_sel_o[80] = word_hit[80] && (|(be & 16'h00f0));
  assign reg_sel_o[81] = word_hit[81] && (|(be & 16'h0f00));
  assign reg_sel_o[82] = word_hit[82] && (|(be & 16'hf000));
  assign reg_sel_o[83] = word_hit[83] && (|(be & 16'h000f));
  assign reg_sel_o[84] = word_hit[84] && (|(be & 16'h00f0));
  assign reg_sel_o[85] = word_hit[85] && (|(be & 16'h0f00));
  assign reg_sel_o[86] = word_hit[86] && (|(be & 16'hf000));
  assign reg_sel_o[87] = word_hit[87] && (|(be & 16'h000f));
  assign reg_sel_o[88] = word_hit[88] && (|(be & 16'h00f0));
  assign reg_sel_o[89] = word_hit[89] && (|(be & 16'h0f00));
  assign reg_sel_o[90] = word_hit[90] && (|(be & 16'hf000));
  assign reg_sel_o[91] = word_hit[91] && (|(be & 16'h000f));
  assign reg_sel_o[92] = word_hit[92] && (|(be & 16'h00f0));
  assign reg_sel_o[93] = word_hit[93] && (|(be & 16'h0f00));
  assign reg_sel_o[94] = word_hit[94] && (|(be & 16'hf000));
  assign reg_sel_o[95] = word_hit[95] && (|(be & 16'h000f));
  assign reg_sel_o[96] = word_hit[96] && (|(be & 16'h00f0));
  assign reg_sel_o[97] = word_hit[97] && (|(be & 16'h0f00));
  assign reg_sel_o[98] = word_hit[98] && (|(be & 16'hf000));
  assign reg_sel_o[99] = word_hit[99] && (|(be & 16'h000f));
  assign reg_sel_o[100] = word_hit[100] && (|(be & 16'h00f0));
  assign reg_sel_o[101] = word_hit[101] && (|(be & 16'h000f));
  assign reg_sel_o[102] = word_hit[102] && (|(be & 16'h00f0));
  assign reg_sel_o[103] = word_hit[103] && (|(be & 16'h0f00));
  assign reg_sel_o[104] = word_hit[104] && (|(be & 16'hf000));
  assign reg_sel_o[105] = word_hit[105] && (|(be & 16'h000f));
  assign reg_sel_o[106] = word_hit[106] && (|(be & 16'h00f0));
  assign reg_sel_o[107] = word_hit[107] && (|(be & 16'h0f00));
  assign reg_sel_o[108] = word_hit[108] && (|(be & 16'h000f));
  assign reg_sel_o[109] = word_hit[109] && (|(be & 16'h00f0));
  assign reg_sel_o[110] = word_hit[110] && (|(be & 16'h0f00));
  assign reg_sel_o[111] = word_hit[111] && (|(be & 16'hf000));
  assign reg_sel_o[112] = word_hit[112] && (|(be & 16'h000f));
  assign reg_sel_o[113] = word_hit[113] && (|(be & 16'h00f0));
  assign reg_sel_o[114] = word_hit[114] && (|(be & 16'h0f00));
  assign reg_sel_o[115] = word_hit[115] && (|(be & 16'hf000));
  assign reg_sel_o[116] = word_hit[116] && (|(be & 16'h000f));
  assign reg_sel_o[117] = word_hit[117] && (|(be & 16'h000f));
  assign reg_sel_o[118] = word_hit[118] && (|(be & 16'h00f0));
  assign reg_sel_o[119] = word_hit[119] && (|(be & 16'h0f00));
  assign reg_sel_o[120] = word_hit[120] && (|(be & 16'hf000));
  assign reg_sel_o[121] = word_hit[121] && (|(be & 16'h000f));
  assign reg_sel_o[122] = word_hit[122] && (|(be & 16'h000f));
  assign reg_sel_o[123] = word_hit[123] && (|(be & 16'h00f0));
  assign reg_sel_o[124] = word_hit[124] && (|(be & 16'h0f00));
  assign reg_sel_o[125] = word_hit[125] && (|(be & 16'hf000));
  assign reg_sel_o[126] = word_hit[126] && (|(be & 16'h000f));
  assign reg_sel_o[127] = word_hit[127] && (|(be & 16'h00f0));
  assign reg_sel_o[128] = word_hit[128] && (|(be & 16'h0f00));
  assign reg_sel_o[129] = word_hit[129] && (|(be & 16'hf000));
  assign reg_sel_o[130] = word_hit[130] && (|(be & 16'h000f));
  assign reg_sel_o[131] = word_hit[131] && (|(be & 16'h00f0));
  assign reg_sel_o[132] = word_hit[132] && (|(be & 16'h0f00));
  assign reg_sel_o[133] = word_hit[133] && (|(be & 16'hf000));
  assign reg_sel_o[134] = word_hit[134] && (|(be & 16'h000f));
  assign reg_sel_o[135] = word_hit[135] && (|(be & 16'h00f0));
  assign reg_sel_o[136] = word_hit[136] && (|(be & 16'h0f00));
  assign reg_sel_o[137] = word_hit[137] && (|(be & 16'hf000));
  assign reg_sel_o[138] = word_hit[138] && (|(be & 16'h000f));
  assign reg_sel_o[139] = word_hit[139] && (|(be & 16'h000f));
  assign reg_sel_o[140] = word_hit[140] && (|(be & 16'h00f0));
  assign reg_sel_o[141] = word_hit[141] && (|(be & 16'h00ff));
  assign reg_sel_o[142] = word_hit[142] && (|(be & 16'hff00));
  assign reg_sel_o[143] = word_hit[143] && (|(be & 16'h00ff));
  assign reg_sel_o[144] = word_hit[144] && (|(be & 16'hff00));
  assign reg_sel_o[145] = word_hit[145] && (|(be & 16'h00ff));
  assign reg_sel_o[146] = word_hit[146] && (|(be & 16'hff00));
  assign reg_sel_o[147] = word_hit[147] && (|(be & 16'h00ff));
  assign reg_sel_o[148] = word_hit[148] && (|(be & 16'hff00));
  assign reg_sel_o[149] = word_hit[149] && (|(be & 16'h00ff));
  assign reg_sel_o[150] = word_hit[150] && (|(be & 16'hff00));
  assign reg_sel_o[151] = word_hit[151] && (|(be & 16'h00ff));
  assign reg_sel_o[152] = word_hit[152] && (|(be & 16'hff00));
  assign reg_sel_o[153] = word_hit[153] && (|(be & 16'h00ff));
  assign reg_sel_o[154] = word_hit[154] && (|(be & 16'hff00));
  assign reg_sel_o[155] = word_hit[155] && (|(be & 16'h00ff));
  assign reg_sel_o[156] = word_hit[156] && (|(be & 16'hff00));
  assign reg_sel_o[157] = word_hit[157] && (|(be & 16'h00ff));
  assign reg_sel_o[158] = word_hit[158] && (|(be & 16'hff00));
  assign reg_sel_o[159] = word_hit[159] && (|(be & 16'h00ff));
  assign reg_sel_o[160] = word_hit[160] && (|(be & 16'hff00));
  assign reg_sel_o[161] = word_hit[161] && (|(be & 16'h00ff));
  assign reg_sel_o[162] = word_hit[162] && (|(be & 16'hff00));
  assign reg_sel_o[163] = word_hit[163] && (|(be & 16'h00ff));
  assign reg_sel_o[164] = word_hit[164] && (|(be & 16'h000f));
  assign reg_sel_o[165] = word_hit[165] && (|(be & 16'h00f0));
  assign reg_sel_o[166] = word_hit[166] && (|(be & 16'h0f00));
  assign reg_sel_o[167] = word_hit[167] && (|(be & 16'hf000));
  assign reg_sel_o[168] = word_hit[168] && (|(be & 16'h00ff));
  assign reg_sel_o[169] = word_hit[169] && (|(be & 16'hff00));
  assign reg_sel_o[170] = word_hit[170] && (|(be & 16'h000f));
  assign reg_sel_o[171] = word_hit[171] && (|(be & 16'h000f));
  assign reg_sel_o[172] = word_hit[172] && (|(be & 16'h00f0));
  assign reg_sel_o[173] = word_hit[173] && (|(be & 16'h0f00));
  assign reg_sel_o[174] = word_hit[174] && (|(be & 16'hf000));
  assign reg_sel_o[175] = word_hit[175] && (|(be & 16'h000f));
  assign reg_sel_o[176] = word_hit[176] && (|(be & 16'h00f0));
  assign reg_sel_o[177] = word_hit[177] && (|(be & 16'h000f));
  assign reg_sel_o[178] = word_hit[178] && (|(be & 16'h00f0));
  assign reg_sel_o[179] = word_hit[179] && (|(be & 16'h000f));
  assign reg_sel_o[180] = word_hit[180] && (|(be & 16'h00f0));
  assign reg_sel_o[181] = word_hit[181] && (|(be & 16'h0f00));
  assign reg_sel_o[182] = word_hit[182] && (|(be & 16'hf000));
  assign reg_sel_o[183] = word_hit[183] && (|(be & 16'h000f));
  assign reg_sel_o[184] = word_hit[184] && (|(be & 16'h0f00));
  assign reg_sel_o[185] = word_hit[185] && (|(be & 16'hf000));
  assign reg_sel_o[186] = word_hit[186] && (|(be & 16'hf000));
  assign reg_sel_o[187] = word_hit[187] && (|(be & 16'h000f));
  assign reg_sel_o[188] = word_hit[188] && (|(be & 16'h00f0));
  assign reg_sel_o[189] = word_hit[189] && (|(be & 16'h000f));
  assign reg_sel_o[190] = word_hit[190] && (|(be & 16'h0f00));
  assign reg_sel_o[191] = word_hit[191] && (|(be & 16'h000f));
  assign reg_sel_o[192] = word_hit[192] && (|(be & 16'h00f0));
  always_comb begin
    covered = 16'h0000;
    if (word_hit[0]) covered = covered | 16'h000f;
    if (word_hit[1]) covered = covered | 16'h00f0;
    if (word_hit[2]) covered = covered | 16'h0f00;
    if (word_hit[3]) covered = covered | 16'hf000;
    if (word_hit[4]) covered = covered | 16'h000f;
    if (word_hit[5]) covered = covered | 16'h00f0;
    if (word_hit[6]) covered = covered | 16'h0f00;
    if (word_hit[7]) covered = covered | 16'hf000;
    if (word_hit[8]) covered = covered | 16'h000f;
    if (word_hit[9]) covered = covered | 16'h00f0;
    if (word_hit[10]) covered = covered | 16'h0f00;
    if (word_hit[11]) covered = covered | 16'hf000;
    if (word_hit[12]) covered = covered | 16'h000f;
    if (word_hit[13]) covered = covered | 16'h00f0;
    if (word_hit[14]) covered = covered | 16'h0f00;
    if (word_hit[15]) covered = covered | 16'h000f;
    if (word_hit[16]) covered = covered | 16'h00f0;
    if (word_hit[17]) covered = covered | 16'h0f00;
    if (word_hit[18]) covered = covered | 16'hf000;
    if (word_hit[19]) covered = covered | 16'h000f;
    if (word_hit[20]) covered = covered | 16'h00f0;
    if (word_hit[21]) covered = covered | 16'h0f00;
    if (word_hit[22]) covered = covered | 16'hf000;
    if (word_hit[23]) covered = covered | 16'h000f;
    if (word_hit[24]) covered = covered | 16'h00f0;
    if (word_hit[25]) covered = covered | 16'h0f00;
    if (word_hit[26]) covered = covered | 16'hf000;
    if (word_hit[27]) covered = covered | 16'h000f;
    if (word_hit[28]) covered = covered | 16'h00f0;
    if (word_hit[29]) covered = covered | 16'h0f00;
    if (word_hit[30]) covered = covered | 16'hf000;
    if (word_hit[31]) covered = covered | 16'h000f;
    if (word_hit[32]) covered = covered | 16'h00f0;
    if (word_hit[33]) covered = covered | 16'h0f00;
    if (word_hit[34]) covered = covered | 16'hf000;
    if (word_hit[35]) covered = covered | 16'h000f;
    if (word_hit[36]) covered = covered | 16'h00f0;
    if (word_hit[37]) covered = covered | 16'h0f00;
    if (word_hit[38]) covered = covered | 16'hf000;
    if (word_hit[39]) covered = covered | 16'h000f;
    if (word_hit[40]) covered = covered | 16'h00f0;
    if (word_hit[41]) covered = covered | 16'h0f00;
    if (word_hit[42]) covered = covered | 16'hf000;
    if (word_hit[43]) covered = covered | 16'h000f;
    if (word_hit[44]) covered = covered | 16'h00f0;
    if (word_hit[45]) covered = covered | 16'h0f00;
    if (word_hit[46]) covered = covered | 16'hf000;
    if (word_hit[47]) covered = covered | 16'h000f;
    if (word_hit[48]) covered = covered | 16'h00f0;
    if (word_hit[49]) covered = covered | 16'h0f00;
    if (word_hit[50]) covered = covered | 16'hf000;
    if (word_hit[51]) covered = covered | 16'h000f;
    if (word_hit[52]) covered = covered | 16'h00f0;
    if (word_hit[53]) covered = covered | 16'h0f00;
    if (word_hit[54]) covered = covered | 16'hf000;
    if (word_hit[55]) covered = covered | 16'h000f;
    if (word_hit[56]) covered = covered | 16'h000f;
    if (word_hit[57]) covered = covered | 16'h00f0;
    if (word_hit[58]) covered = covered | 16'h0f00;
    if (word_hit[59]) covered = covered | 16'hf000;
    if (word_hit[60]) covered = covered | 16'h000f;
    if (word_hit[61]) covered = covered | 16'h00f0;
    if (word_hit[62]) covered = covered | 16'h0f00;
    if (word_hit[63]) covered = covered | 16'h000f;
    if (word_hit[64]) covered = covered | 16'h00f0;
    if (word_hit[65]) covered = covered | 16'h0f00;
    if (word_hit[66]) covered = covered | 16'hf000;
    if (word_hit[67]) covered = covered | 16'h000f;
    if (word_hit[68]) covered = covered | 16'h00f0;
    if (word_hit[69]) covered = covered | 16'h0f00;
    if (word_hit[70]) covered = covered | 16'hf000;
    if (word_hit[71]) covered = covered | 16'h000f;
    if (word_hit[72]) covered = covered | 16'h00f0;
    if (word_hit[73]) covered = covered | 16'h0f00;
    if (word_hit[74]) covered = covered | 16'hf000;
    if (word_hit[75]) covered = covered | 16'h000f;
    if (word_hit[76]) covered = covered | 16'h00f0;
    if (word_hit[77]) covered = covered | 16'h0f00;
    if (word_hit[78]) covered = covered | 16'hf000;
    if (word_hit[79]) covered = covered | 16'h000f;
    if (word_hit[80]) covered = covered | 16'h00f0;
    if (word_hit[81]) covered = covered | 16'h0f00;
    if (word_hit[82]) covered = covered | 16'hf000;
    if (word_hit[83]) covered = covered | 16'h000f;
    if (word_hit[84]) covered = covered | 16'h00f0;
    if (word_hit[85]) covered = covered | 16'h0f00;
    if (word_hit[86]) covered = covered | 16'hf000;
    if (word_hit[87]) covered = covered | 16'h000f;
    if (word_hit[88]) covered = covered | 16'h00f0;
    if (word_hit[89]) covered = covered | 16'h0f00;
    if (word_hit[90]) covered = covered | 16'hf000;
    if (word_hit[91]) covered = covered | 16'h000f;
    if (word_hit[92]) covered = covered | 16'h00f0;
    if (word_hit[93]) covered = covered | 16'h0f00;
    if (word_hit[94]) covered = covered | 16'hf000;
    if (word_hit[95]) covered = covered | 16'h000f;
    if (word_hit[96]) covered = covered | 16'h00f0;
    if (word_hit[97]) covered = covered | 16'h0f00;
    if (word_hit[98]) covered = covered | 16'hf000;
    if (word_hit[99]) covered = covered | 16'h000f;
    if (word_hit[100]) covered = covered | 16'h00f0;
    if (word_hit[101]) covered = covered | 16'h000f;
    if (word_hit[102]) covered = covered | 16'h00f0;
    if (word_hit[103]) covered = covered | 16'h0f00;
    if (word_hit[104]) covered = covered | 16'hf000;
    if (word_hit[105]) covered = covered | 16'h000f;
    if (word_hit[106]) covered = covered | 16'h00f0;
    if (word_hit[107]) covered = covered | 16'h0f00;
    if (word_hit[108]) covered = covered | 16'h000f;
    if (word_hit[109]) covered = covered | 16'h00f0;
    if (word_hit[110]) covered = covered | 16'h0f00;
    if (word_hit[111]) covered = covered | 16'hf000;
    if (word_hit[112]) covered = covered | 16'h000f;
    if (word_hit[113]) covered = covered | 16'h00f0;
    if (word_hit[114]) covered = covered | 16'h0f00;
    if (word_hit[115]) covered = covered | 16'hf000;
    if (word_hit[116]) covered = covered | 16'h000f;
    if (word_hit[117]) covered = covered | 16'h000f;
    if (word_hit[118]) covered = covered | 16'h00f0;
    if (word_hit[119]) covered = covered | 16'h0f00;
    if (word_hit[120]) covered = covered | 16'hf000;
    if (word_hit[121]) covered = covered | 16'h000f;
    if (word_hit[122]) covered = covered | 16'h000f;
    if (word_hit[123]) covered = covered | 16'h00f0;
    if (word_hit[124]) covered = covered | 16'h0f00;
    if (word_hit[125]) covered = covered | 16'hf000;
    if (word_hit[126]) covered = covered | 16'h000f;
    if (word_hit[127]) covered = covered | 16'h00f0;
    if (word_hit[128]) covered = covered | 16'h0f00;
    if (word_hit[129]) covered = covered | 16'hf000;
    if (word_hit[130]) covered = covered | 16'h000f;
    if (word_hit[131]) covered = covered | 16'h00f0;
    if (word_hit[132]) covered = covered | 16'h0f00;
    if (word_hit[133]) covered = covered | 16'hf000;
    if (word_hit[134]) covered = covered | 16'h000f;
    if (word_hit[135]) covered = covered | 16'h00f0;
    if (word_hit[136]) covered = covered | 16'h0f00;
    if (word_hit[137]) covered = covered | 16'hf000;
    if (word_hit[138]) covered = covered | 16'h000f;
    if (word_hit[139]) covered = covered | 16'h000f;
    if (word_hit[140]) covered = covered | 16'h00f0;
    if (word_hit[141]) covered = covered | 16'h00ff;
    if (word_hit[142]) covered = covered | 16'hff00;
    if (word_hit[143]) covered = covered | 16'h00ff;
    if (word_hit[144]) covered = covered | 16'hff00;
    if (word_hit[145]) covered = covered | 16'h00ff;
    if (word_hit[146]) covered = covered | 16'hff00;
    if (word_hit[147]) covered = covered | 16'h00ff;
    if (word_hit[148]) covered = covered | 16'hff00;
    if (word_hit[149]) covered = covered | 16'h00ff;
    if (word_hit[150]) covered = covered | 16'hff00;
    if (word_hit[151]) covered = covered | 16'h00ff;
    if (word_hit[152]) covered = covered | 16'hff00;
    if (word_hit[153]) covered = covered | 16'h00ff;
    if (word_hit[154]) covered = covered | 16'hff00;
    if (word_hit[155]) covered = covered | 16'h00ff;
    if (word_hit[156]) covered = covered | 16'hff00;
    if (word_hit[157]) covered = covered | 16'h00ff;
    if (word_hit[158]) covered = covered | 16'hff00;
    if (word_hit[159]) covered = covered | 16'h00ff;
    if (word_hit[160]) covered = covered | 16'hff00;
    if (word_hit[161]) covered = covered | 16'h00ff;
    if (word_hit[162]) covered = covered | 16'hff00;
    if (word_hit[163]) covered = covered | 16'h00ff;
    if (word_hit[164]) covered = covered | 16'h000f;
    if (word_hit[165]) covered = covered | 16'h00f0;
    if (word_hit[166]) covered = covered | 16'h0f00;
    if (word_hit[167]) covered = covered | 16'hf000;
    if (word_hit[168]) covered = covered | 16'h00ff;
    if (word_hit[169]) covered = covered | 16'hff00;
    if (word_hit[170]) covered = covered | 16'h000f;
    if (word_hit[171]) covered = covered | 16'h000f;
    if (word_hit[172]) covered = covered | 16'h00f0;
    if (word_hit[173]) covered = covered | 16'h0f00;
    if (word_hit[174]) covered = covered | 16'hf000;
    if (word_hit[175]) covered = covered | 16'h000f;
    if (word_hit[176]) covered = covered | 16'h00f0;
    if (word_hit[177]) covered = covered | 16'h000f;
    if (word_hit[178]) covered = covered | 16'h00f0;
    if (word_hit[179]) covered = covered | 16'h000f;
    if (word_hit[180]) covered = covered | 16'h00f0;
    if (word_hit[181]) covered = covered | 16'h0f00;
    if (word_hit[182]) covered = covered | 16'hf000;
    if (word_hit[183]) covered = covered | 16'h000f;
    if (word_hit[184]) covered = covered | 16'h0f00;
    if (word_hit[185]) covered = covered | 16'hf000;
    if (word_hit[186]) covered = covered | 16'hf000;
    if (word_hit[187]) covered = covered | 16'h000f;
    if (word_hit[188]) covered = covered | 16'h00f0;
    if (word_hit[189]) covered = covered | 16'h000f;
    if (word_hit[190]) covered = covered | 16'h0f00;
    if (word_hit[191]) covered = covered | 16'h000f;
    if (word_hit[192]) covered = covered | 16'h00f0;
  end

  localparam logic [192:0] NOT_WRITABLE = 193'h15ef92ffffffff7fffde0097fffffffffbf00065fffff87c0;
  localparam logic [192:0] NOT_READABLE = 193'h0000000000000000002100000000000004080000000001820;
  logic hole, deny;
  assign hole = |(be & ~covered);
  assign deny = (is_write && (|(reg_sel_o & NOT_WRITABLE))) || (is_read && (|(reg_sel_o & NOT_READABLE)));

  logic [sf_albion_pkg::SF_STATUS_W-1:0] region_status;
  always_comb begin
    region_status = sf_albion_pkg::SF_ST_OKAY;
    if (p_hit[0]) region_status = sf_albion_pkg::sf_access_check_bits(sf_reg_pkg::SF_DMA_REGION_ATTR, req_i);
    if (p_hit[1]) region_status = sf_albion_pkg::sf_access_check_bits(sf_reg_pkg::SF_TENSOR_REGION_ATTR, req_i);
    if (p_hit[2]) region_status = sf_albion_pkg::sf_access_check_bits(sf_reg_pkg::SF_VECTOR_REGION_ATTR, req_i);
    if (p_hit[3]) region_status = sf_albion_pkg::sf_access_check_bits(sf_reg_pkg::SF_PERF_REGION_ATTR, req_i);
    if (p_hit[4]) region_status = sf_albion_pkg::sf_access_check_bits(sf_reg_pkg::SF_SYSID_REGION_ATTR, req_i);
    if (p_hit[5]) region_status = sf_albion_pkg::sf_access_check_bits(sf_reg_pkg::SF_INTC_REGION_ATTR, req_i);
    if (p_hit[6]) region_status = sf_albion_pkg::sf_access_check_bits(sf_reg_pkg::SF_CLKRST_REGION_ATTR, req_i);
    if (p_hit[7]) region_status = sf_albion_pkg::sf_access_check_bits(sf_reg_pkg::SF_SRAMC_REGION_ATTR, req_i);
    if (!(|p_hit))                                       status_o = sf_albion_pkg::SF_ST_DECODE_ERR;
    else if (region_status != sf_albion_pkg::SF_ST_OKAY) status_o = region_status;
    else if (hole)                                       status_o = sf_albion_pkg::SF_ST_DECODE_ERR;
    else if (deny)                                       status_o = sf_albion_pkg::SF_ST_ACCESS_DENIED;
    else                                                 status_o = sf_albion_pkg::SF_ST_OKAY;
  end
endmodule
/* verilator lint_on UNUSEDSIGNAL */

`default_nettype wire
