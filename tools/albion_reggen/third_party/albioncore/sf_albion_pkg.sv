// =============================================================================
//  sf_albion_pkg.sv  --  SilicaFlux Albion common package
// -----------------------------------------------------------------------------
//  Project   : Aureom.AI / SilicaFlux Albion (AlbionCore foundation)
//  Role      : Single source of truth for the Albion Link Protocol (ALP) v1:
//              address / data / tag / domain types, operation codes, status
//              codes, memory attributes, address-space identifiers, region
//              attributes, device capability fields and the pure functions that
//              define request legality and response well-formedness.
//
//  Contract  : docs/albion/ARCHITECTURE_CONTRACT.md  (rule ids "ALP-xxx-nn")
//  C / Rust  : include/albion/albion_proto.h and .rs are GENERATED from this
//              file by tools/albion/build/gen_proto.py; do not edit them.
//
//  Baseline  : 64-bit address, 128-bit data, 16-bit byte mask, 8-bit tag,
//              8-bit protection-domain id.  The package types are FIXED.
//              Other bus widths are supported only through the explicit width
//              adapter (sf_albion_width_adapter) or a future generated package;
//              never by overriding these widths.
//
//  Tool rules (see docs/albion/NAMING_RULES.md, section "Tool compatibility"):
//    * synthesizable-subset only: no classes, no dynamic types, no `define.
//    * struct fields are plain logic vectors; enums name the code points and
//      are used in comparisons / case labels.  They are never cast, because
//      the Yosys 0.33 front end rejects enum casts.
//    * modules reference this package with scoped names (sf_albion_pkg::NAME);
//      there is no wildcard import, so the package cannot collide with the
//      many other sf_* / silicaflux_* packages already in the repository.
//    * functions assign to their own name (no `return`, a Yosys 0.33 limit).
//    * Yosys 0.33 cannot elaborate a call whose FORMAL argument is a package
//      struct.  Every checking function therefore exists twice: a `_bits`
//      version taking a flat vector (the synthesizable API, used by rtl/ and by
//      formal) and a struct-argument wrapper for simulation convenience that
//      simply forwards to it.  Layout offsets are published as SF_*_LSB
//      constants and verified against the structs by tb_sf_albion_pkg.
//    * Yosys 0.33 resolves the identifiers inside a package function in the
//      CALLER's scope, so an unqualified enum member silently becomes an
//      undriven wire.  Inside function bodies every package item is therefore
//      written with its full scope (sf_albion_pkg::NAME).  The synthesis flow
//      fails on any "implicitly declared" / "no driver" report.
//
//  This file contains no process-node, timing or performance claims.
// =============================================================================
`default_nettype none

// A constants package: not every constant is used by every consumer, and the
// checking functions take whole structs while reading only some of the fields.
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off UNUSEDSIGNAL */
package sf_albion_pkg;

  // ===========================================================================
  // 1. Identity and versioning
  // ===========================================================================
  localparam int unsigned SF_ALBION_LIB_MAJOR   = 0;   // library release
  localparam int unsigned SF_ALBION_LIB_MINOR   = 1;
  localparam int unsigned SF_ALBION_LIB_PATCH   = 0;
  localparam int unsigned SF_ALP_VERSION_MAJOR  = 1;   // Albion Link Protocol
  localparam int unsigned SF_ALP_VERSION_MINOR  = 0;

  // ===========================================================================
  // 2. Baseline widths (fixed)
  // ===========================================================================
  localparam int unsigned SF_ADDR_W    = 64;
  localparam int unsigned SF_DATA_W    = 128;
  localparam int unsigned SF_BE_W      = SF_DATA_W / 8;   // 16 byte lanes
  localparam int unsigned SF_LANE_W    = 4;               // log2(SF_BE_W)
  localparam int unsigned SF_TAG_W     = 8;
  localparam int unsigned SF_DOM_W     = 8;
  localparam int unsigned SF_OP_W      = 4;
  localparam int unsigned SF_ATTR_W    = 8;
  localparam int unsigned SF_STATUS_W  = 4;
  localparam int unsigned SF_CMETA_W   = 8;
  localparam int unsigned SF_REGATTR_W = 8;
  localparam int unsigned SF_CAPS_W    = 64;
  // Hard upper bound on outstanding transactions per link: one per tag value.
  localparam int unsigned SF_MAX_OUTSTANDING_LIMIT = 256;  // = 2 ** SF_TAG_W

  // ===========================================================================
  // 3. Basic types
  // ===========================================================================
  typedef logic [SF_ADDR_W-1:0]   sf_addr_t;
  typedef logic [SF_DATA_W-1:0]   sf_data_t;
  typedef logic [SF_BE_W-1:0]     sf_be_t;
  typedef logic [SF_TAG_W-1:0]    sf_tag_t;
  typedef logic [SF_DOM_W-1:0]    sf_dom_t;
  typedef logic [SF_OP_W-1:0]     sf_op_t;
  typedef logic [SF_STATUS_W-1:0] sf_status_t;

  // ===========================================================================
  // 4. Operation codes
  // ===========================================================================
  //  READ and WRITE are the only operations defined in ALP v1.
  //  Code 4'h0 is deliberately INVALID so that an all-zero (uninitialised or
  //  corrupted) request is never mistaken for a legal operation.
  //  Codes 4'h4..4'h7 are RESERVED for a future atomic family and 4'h8..4'hF
  //  for future use.  NO atomic semantics are defined or may be implemented
  //  until an atomicity specification has been written and formally verified
  //  (ALP-ATM-01).  Every reserved code is answered with SF_ST_BAD_OPCODE.
  typedef enum logic [3:0] {
    SF_OP_NONE  = 4'h0,
    SF_OP_READ  = 4'h1,
    SF_OP_WRITE = 4'h2
  } sf_op_e;

  localparam sf_op_t SF_OP_RESERVED_ATOMIC_FIRST = 4'h4;
  localparam sf_op_t SF_OP_RESERVED_ATOMIC_LAST  = 4'h7;

  // ===========================================================================
  // 5. Status / error codes
  // ===========================================================================
  //  Carried in every response.  SF_ST_OKAY is the only success code; for any
  //  other status the response data field is all-zero (ALP-RSP-05).
  typedef enum logic [3:0] {
    SF_ST_OKAY          = 4'h0,  // completed successfully
    SF_ST_DECODE_ERR    = 4'h1,  // address maps to no region / no target
    SF_ST_ACCESS_DENIED = 4'h2,  // region permission, privilege, security or domain check failed
    SF_ST_BAD_OPCODE    = 4'h3,  // opcode not READ/WRITE (reserved, atomic family, or NONE)
    SF_ST_BAD_BE        = 4'h4,  // byte-enable mask is zero
    SF_ST_ALIGN_ERR     = 4'h5,  // address is not aligned to the data word
    SF_ST_BAD_ATTR      = 4'h6,  // reserved attribute bits set, or memory type not allowed
    SF_ST_TARGET_ERR    = 4'h7,  // generic target / device failure
    SF_ST_TIMEOUT       = 4'h8,  // target did not complete within its watchdog window
    SF_ST_CANCELLED     = 4'h9,  // locally synthesised completion for an abandoned request
    SF_ST_ECC_UNCORR    = 4'hA,  // uncorrectable data error; data is poisoned
    SF_ST_PROTOCOL_ERR  = 4'hB   // link protocol violation detected by a component
  } sf_status_e;

  // ===========================================================================
  // 6. Protection domains
  // ===========================================================================
  //  8-bit domain id carried in every request.  Ranges:
  //    0x00        root domain  (platform root of trust / secure monitor)
  //    0x01        management   (control-plane firmware, e.g. ControlCore)
  //    0x02        system DMA   (the platform DMA engine acting for itself)
  //    0x03..0x0F  reserved system domains
  //    0x10..0xFE  tenant domains
  //    0xFF        invalid      (never legal on the wire)
  localparam sf_dom_t SF_DOM_ROOT         = 8'h00;
  localparam sf_dom_t SF_DOM_MGMT         = 8'h01;
  localparam sf_dom_t SF_DOM_SYS_DMA      = 8'h02;
  localparam sf_dom_t SF_DOM_SYSTEM_LAST  = 8'h0F;
  localparam sf_dom_t SF_DOM_TENANT_FIRST = 8'h10;
  localparam sf_dom_t SF_DOM_TENANT_LAST  = 8'hFE;
  localparam sf_dom_t SF_DOM_INVALID      = 8'hFF;

  // ===========================================================================
  // 7. Memory types, address spaces and access attributes
  // ===========================================================================
  typedef enum logic [1:0] {
    SF_MEM_NORMAL_WB = 2'd0,  // normal memory, cacheable write-back
    SF_MEM_NORMAL_NC = 2'd1,  // normal memory, non-cacheable
    SF_MEM_DEVICE    = 2'd2   // device memory: strongly ordered, no merging or speculation
  } sf_mem_type_e;                // 2'd3 is reserved

  //  Address-space identifiers.  Every region of the memory map belongs to
  //  exactly one address space; the id is not carried on the wire in ALP v1.
  typedef enum logic [3:0] {
    SF_AS_DEVICE   = 4'h0,  // device-local memory (SRAM, scratchpads)
    SF_AS_CONFIG   = 4'h1,  // control / status registers (MMIO)
    SF_AS_EXTERNAL = 4'h2,  // external memory reached through an adapter
    SF_AS_HOST     = 4'h3,  // host physical memory (reserved; DMA / PCIe path)
    SF_AS_SECURE   = 4'h4   // secure-only memory and key storage
  } sf_asid_e;

  //  Per-request access attributes (initiator-assigned).
  typedef struct packed {
    logic       rsvd;      // [7]   must be 0           (else SF_ST_BAD_ATTR)
    logic [1:0] qos;       // [6:5] priority class hint, 0 = lowest .. 3 = highest
    logic       instr;     // [4]   instruction fetch (execute intent)
    logic       secure;    // [3]   1 = secure access
    logic       priv;      // [2]   1 = privileged access
    logic [1:0] mem_type;  // [1:0] sf_mem_type_e; 2'd3 reserved (else SF_ST_BAD_ATTR)
  } sf_attr_t;

  //  Per-region attributes (memory-map side).
  typedef struct packed {
    logic [1:0] mem_type;     // [7:6] sf_mem_type_e of the region
    logic       cacheable;    // [5]   initiators may cache this region
    logic       secure_only;  // [4]   only secure accesses allowed
    logic       priv_only;    // [3]   only privileged accesses allowed
    logic       exec;         // [2]   instruction fetch allowed
    logic       write;        // [1]   writes allowed
    logic       read;         // [0]   reads allowed
  } sf_region_attr_t;

  // ===========================================================================
  // 8. Request / response payloads
  // ===========================================================================
  //  Field order is MSB -> LSB.  Total 236 bits.
  typedef struct packed {
    sf_op_t   op;      // [235:232] operation
    sf_tag_t  tag;     // [231:224] initiator transaction tag (opaque to targets)
    sf_dom_t  dom;     // [223:216] protection domain
    sf_attr_t attr;    // [215:208] access attributes
    sf_addr_t addr;    // [207:144] byte address, lane-aligned (addr[3:0] == 0)
    sf_be_t   be;      // [143:128] byte-lane enables
    sf_data_t data;    // [127:0]   write data (don't-care for reads, ignored)
  } sf_req_t;

  //  Completion metadata.
  typedef struct packed {
    logic [3:0] rsvd;       // [7:4] must be 0
    logic       corrected;  // [3]   a correctable error was repaired (informational)
    logic       poisoned;   // [2]   data lanes must not be consumed (== status ECC_UNCORR)
    logic       last;       // [1]   last beat of the transaction (always 1 in ALP v1)
    logic       is_write;   // [0]   0 = read completion, 1 = write completion
  } sf_cmeta_t;

  //  Field order is MSB -> LSB.  Total 148 bits.
  typedef struct packed {
    sf_tag_t    tag;     // [147:140] echoed request tag
    sf_status_t status;  // [139:136] sf_status_e
    sf_cmeta_t  meta;    // [135:128] completion metadata
    sf_data_t   data;    // [127:0]   read data; all-zero for writes and for non-OKAY status
  } sf_rsp_t;

  localparam int unsigned SF_REQ_W = SF_OP_W + SF_TAG_W + SF_DOM_W + SF_ATTR_W
                                   + SF_ADDR_W + SF_BE_W + SF_DATA_W;   // 236
  localparam int unsigned SF_RSP_W = SF_TAG_W + SF_STATUS_W + SF_CMETA_W
                                   + SF_DATA_W;                          // 148

  //  Bit offsets inside the flat 236-bit request vector and the flat 148-bit
  //  response vector.  Verified against the packed structs by tb_sf_albion_pkg.
  localparam int unsigned SF_REQ_OP_LSB     = 232;
  localparam int unsigned SF_REQ_TAG_LSB    = 224;
  localparam int unsigned SF_REQ_DOM_LSB    = 216;
  localparam int unsigned SF_REQ_ATTR_LSB   = 208;
  localparam int unsigned SF_REQ_ADDR_LSB   = 144;
  localparam int unsigned SF_REQ_BE_LSB     = 128;
  localparam int unsigned SF_REQ_DATA_LSB   = 0;
  localparam int unsigned SF_RSP_TAG_LSB    = 140;
  localparam int unsigned SF_RSP_STATUS_LSB = 136;
  localparam int unsigned SF_RSP_META_LSB   = 128;
  localparam int unsigned SF_RSP_DATA_LSB   = 0;

  //  Bit positions inside the 8-bit attribute byte (sf_attr_t).
  localparam int unsigned SF_ATTR_MEMTYPE_LSB = 0;   // [1:0]
  localparam int unsigned SF_ATTR_PRIV_BIT    = 2;
  localparam int unsigned SF_ATTR_SECURE_BIT  = 3;
  localparam int unsigned SF_ATTR_INSTR_BIT   = 4;
  localparam int unsigned SF_ATTR_QOS_LSB     = 5;   // [6:5]
  localparam int unsigned SF_ATTR_RSVD_BIT    = 7;

  //  Bit positions inside the 8-bit region attribute byte (sf_region_attr_t).
  localparam int unsigned SF_RATTR_READ_BIT        = 0;
  localparam int unsigned SF_RATTR_WRITE_BIT       = 1;
  localparam int unsigned SF_RATTR_EXEC_BIT        = 2;
  localparam int unsigned SF_RATTR_PRIV_ONLY_BIT   = 3;
  localparam int unsigned SF_RATTR_SECURE_ONLY_BIT = 4;
  localparam int unsigned SF_RATTR_CACHEABLE_BIT   = 5;
  localparam int unsigned SF_RATTR_MEMTYPE_LSB     = 6;   // [7:6]

  //  Bit positions inside the 8-bit completion metadata byte (sf_cmeta_t).
  localparam int unsigned SF_CMETA_IS_WRITE_BIT  = 0;
  localparam int unsigned SF_CMETA_LAST_BIT      = 1;
  localparam int unsigned SF_CMETA_POISONED_BIT  = 2;
  localparam int unsigned SF_CMETA_CORRECTED_BIT = 3;

  // ===========================================================================
  // 9. Device capability fields
  // ===========================================================================
  //  A device (or a profile) advertises what it implements in one 64-bit word.
  //  Capabilities never claim a feature the hardware lacks: unsupported
  //  features are 0.
  typedef struct packed {
    logic [3:0]  proto_major;      // [63:60] ALP major version
    logic [3:0]  proto_minor;      // [59:56] ALP minor version
    logic [7:0]  addr_w;           // [55:48] address width in bits
    logic [3:0]  data_bytes_log2;  // [47:44] log2(data bytes): 4 = 16 bytes = 128 bit
    logic [3:0]  tag_w;            // [43:40] tag width in bits
    logic [3:0]  dom_w;            // [39:36] domain-id width in bits
    logic [3:0]  rsvd;             // [35:32] reserved, 0
    logic [15:0] max_outstanding;  // [31:16] outstanding transactions per link
    logic [15:0] features;         // [15:0]  SF_FEAT_* bit map
  } sf_caps_t;

  //  Bit positions inside sf_caps_t.features.
  localparam int unsigned SF_FEAT_READ         = 0;
  localparam int unsigned SF_FEAT_WRITE        = 1;
  localparam int unsigned SF_FEAT_ATOMIC       = 2;   // always 0 in ALP v1
  localparam int unsigned SF_FEAT_OUT_OF_ORDER = 3;   // always 0 in ALP v1
  localparam int unsigned SF_FEAT_ECC          = 4;
  localparam int unsigned SF_FEAT_POISON       = 5;
  localparam int unsigned SF_FEAT_CDC          = 6;
  localparam int unsigned SF_FEAT_DOMAIN_CHECK = 7;

  //  Features that ALP v1 defines semantics for.
  localparam logic [15:0] SF_FEATURES_ALP_V1 = 16'h0003;   // READ | WRITE

  // ===========================================================================
  // 10. Pure functions
  // ===========================================================================

  //  True for the two defined operations.
  function automatic logic sf_op_is_valid(input sf_op_t op);
    sf_op_is_valid = (op == sf_albion_pkg::SF_OP_READ) || (op == sf_albion_pkg::SF_OP_WRITE);
  endfunction

  //  True for any status other than OKAY.
  function automatic logic sf_status_is_error(input sf_status_t st);
    sf_status_is_error = (st != sf_albion_pkg::SF_ST_OKAY);
  endfunction

  //  Domain classification helpers.
  function automatic logic sf_dom_is_valid(input sf_dom_t d);
    sf_dom_is_valid = (d != sf_albion_pkg::SF_DOM_INVALID);
  endfunction

  function automatic logic sf_dom_is_system(input sf_dom_t d);
    sf_dom_is_system = (d <= sf_albion_pkg::SF_DOM_SYSTEM_LAST);
  endfunction

  function automatic logic sf_dom_is_tenant(input sf_dom_t d);
    sf_dom_is_tenant = (d >= sf_albion_pkg::SF_DOM_TENANT_FIRST) && (d <= sf_albion_pkg::SF_DOM_TENANT_LAST);
  endfunction

  //  Request legality  (ALP-LEG-01, ALP-LEG-02, ALP-ATM-01).
  //  `r` is the flat 236-bit request vector (see SF_REQ_*_LSB).
  //  Returns SF_ST_OKAY for a well-formed request, otherwise the status the
  //  target / error responder must return.  Precedence, highest first:
  //    1. opcode      -> SF_ST_BAD_OPCODE
  //    2. alignment   -> SF_ST_ALIGN_ERR      (addr[3:0] != 0)
  //    3. byte enable -> SF_ST_BAD_BE         (be == 0)
  //    4. attributes  -> SF_ST_BAD_ATTR       (rsvd bit set or mem_type == 3)
  //    5. domain      -> SF_ST_ACCESS_DENIED  (dom == SF_DOM_INVALID)
  function automatic sf_status_t sf_req_check_bits(input logic [SF_REQ_W-1:0] r);
    logic [sf_albion_pkg::SF_OP_W-1:0]   op;
    logic [sf_albion_pkg::SF_LANE_W-1:0] lane;
    logic [sf_albion_pkg::SF_BE_W-1:0]   be;
    logic [sf_albion_pkg::SF_ATTR_W-1:0] attr;
    logic [sf_albion_pkg::SF_DOM_W-1:0]  dom;
    begin
      op   = r[sf_albion_pkg::SF_REQ_OP_LSB   +: sf_albion_pkg::SF_OP_W];
      lane = r[sf_albion_pkg::SF_REQ_ADDR_LSB +: sf_albion_pkg::SF_LANE_W];
      be   = r[sf_albion_pkg::SF_REQ_BE_LSB   +: sf_albion_pkg::SF_BE_W];
      attr = r[sf_albion_pkg::SF_REQ_ATTR_LSB +: sf_albion_pkg::SF_ATTR_W];
      dom  = r[sf_albion_pkg::SF_REQ_DOM_LSB  +: sf_albion_pkg::SF_DOM_W];
      sf_req_check_bits = sf_albion_pkg::SF_ST_OKAY;
      if (!sf_op_is_valid(op)) begin
        sf_req_check_bits = sf_albion_pkg::SF_ST_BAD_OPCODE;
      end else if (lane != 4'h0) begin
        sf_req_check_bits = sf_albion_pkg::SF_ST_ALIGN_ERR;
      end else if (be == 16'h0000) begin
        sf_req_check_bits = sf_albion_pkg::SF_ST_BAD_BE;
      end else if (attr[sf_albion_pkg::SF_ATTR_RSVD_BIT] ||
                   (attr[sf_albion_pkg::SF_ATTR_MEMTYPE_LSB +: 2] == 2'd3)) begin
        sf_req_check_bits = sf_albion_pkg::SF_ST_BAD_ATTR;
      end else if (!sf_dom_is_valid(dom)) begin
        sf_req_check_bits = sf_albion_pkg::SF_ST_ACCESS_DENIED;
      end
    end
  endfunction

  //  Region access check, applied to an already-legal request.
  //  `ra` is the 8-bit region attribute word (see SF_RATTR_*), `r` the flat
  //  request vector.  Returns SF_ST_OKAY or:
  //    SF_ST_ACCESS_DENIED  read/write/execute not permitted, privilege or
  //                         security level insufficient
  //    SF_ST_BAD_ATTR       region is device memory but the request is not
  //                         marked as device memory
  //  Precedence: read/write permission, execute, privilege, security, then
  //  memory type.
  function automatic sf_status_t sf_access_check_bits(input logic [SF_REGATTR_W-1:0] ra,
                                                      input logic [SF_REQ_W-1:0]     r);
    logic [sf_albion_pkg::SF_OP_W-1:0]   op;
    logic [sf_albion_pkg::SF_ATTR_W-1:0] attr;
    begin
      op   = r[sf_albion_pkg::SF_REQ_OP_LSB   +: sf_albion_pkg::SF_OP_W];
      attr = r[sf_albion_pkg::SF_REQ_ATTR_LSB +: sf_albion_pkg::SF_ATTR_W];
      sf_access_check_bits = sf_albion_pkg::SF_ST_OKAY;
      if ((op == sf_albion_pkg::SF_OP_READ) && !ra[sf_albion_pkg::SF_RATTR_READ_BIT]) begin
        sf_access_check_bits = sf_albion_pkg::SF_ST_ACCESS_DENIED;
      end else if ((op == sf_albion_pkg::SF_OP_WRITE) && !ra[sf_albion_pkg::SF_RATTR_WRITE_BIT]) begin
        sf_access_check_bits = sf_albion_pkg::SF_ST_ACCESS_DENIED;
      end else if (attr[sf_albion_pkg::SF_ATTR_INSTR_BIT] && !ra[sf_albion_pkg::SF_RATTR_EXEC_BIT]) begin
        sf_access_check_bits = sf_albion_pkg::SF_ST_ACCESS_DENIED;
      end else if (ra[sf_albion_pkg::SF_RATTR_PRIV_ONLY_BIT] && !attr[sf_albion_pkg::SF_ATTR_PRIV_BIT]) begin
        sf_access_check_bits = sf_albion_pkg::SF_ST_ACCESS_DENIED;
      end else if (ra[sf_albion_pkg::SF_RATTR_SECURE_ONLY_BIT] && !attr[sf_albion_pkg::SF_ATTR_SECURE_BIT]) begin
        sf_access_check_bits = sf_albion_pkg::SF_ST_ACCESS_DENIED;
      end else if ((ra[sf_albion_pkg::SF_RATTR_MEMTYPE_LSB +: 2] == 2'(sf_albion_pkg::SF_MEM_DEVICE)) &&
                   (attr[sf_albion_pkg::SF_ATTR_MEMTYPE_LSB +: 2] != 2'(sf_albion_pkg::SF_MEM_DEVICE))) begin
        sf_access_check_bits = sf_albion_pkg::SF_ST_BAD_ATTR;
      end
    end
  endfunction

  //  Response well-formedness  (ALP-RSP-05).  `r` is the flat 148-bit
  //  response vector.  True when the response obeys every static format rule:
  //    * meta.rsvd == 0 and meta.last == 1
  //    * status is a defined code
  //    * non-OKAY status  -> data is all-zero
  //    * write completion -> data is all-zero
  //    * poisoned <-> status == SF_ST_ECC_UNCORR
  function automatic logic sf_rsp_wellformed_bits(input logic [SF_RSP_W-1:0] r);
    logic [sf_albion_pkg::SF_STATUS_W-1:0] status;
    logic [sf_albion_pkg::SF_CMETA_W-1:0]  meta;
    logic                   data_zero;
    begin
      status    = r[sf_albion_pkg::SF_RSP_STATUS_LSB +: sf_albion_pkg::SF_STATUS_W];
      meta      = r[sf_albion_pkg::SF_RSP_META_LSB   +: sf_albion_pkg::SF_CMETA_W];
      data_zero = (r[sf_albion_pkg::SF_RSP_DATA_LSB  +: sf_albion_pkg::SF_DATA_W] == '0);
      sf_rsp_wellformed_bits = (status <= sf_albion_pkg::SF_ST_PROTOCOL_ERR)
                            && (meta[7:4] == 4'h0)
                            && meta[sf_albion_pkg::SF_CMETA_LAST_BIT]
                            && (status == sf_albion_pkg::SF_ST_OKAY || data_zero)
                            && (!meta[sf_albion_pkg::SF_CMETA_IS_WRITE_BIT] || data_zero)
                            && (meta[sf_albion_pkg::SF_CMETA_POISONED_BIT] ==
                                (status == sf_albion_pkg::SF_ST_ECC_UNCORR));
    end
  endfunction

  //  Struct-argument conveniences for simulation and testbenches.  They only
  //  forward to the _bits functions above.  RTL must call the _bits versions.
  function automatic sf_status_t sf_req_check(input sf_req_t r);
    sf_req_check = sf_req_check_bits(r);
  endfunction

  function automatic sf_status_t sf_access_check(input sf_region_attr_t ra,
                                                 input sf_req_t         r);
    sf_access_check = sf_access_check_bits(ra, r);
  endfunction

  function automatic logic sf_rsp_wellformed(input sf_rsp_t r);
    sf_rsp_wellformed = sf_rsp_wellformed_bits(r);
  endfunction

endpackage
/* verilator lint_on UNUSEDSIGNAL */
/* verilator lint_on UNUSEDPARAM */

`default_nettype wire
