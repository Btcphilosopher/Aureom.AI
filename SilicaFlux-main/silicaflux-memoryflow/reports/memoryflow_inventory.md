# Architecture inventory: `silicaflux-memoryflow`

**Repository evidence.** This table classifies the MemoryFlow tree itself (what MemoryFlow adds). The SilicaFlux repository inventory is `inventory.md` (memoryflow sf-inventory).

## Memory-subsystem coverage

| Category | Implemented (synthesizable) | Behavioural / blackbox |
|---|---|---|
| CPU cache interface | **none -> PROPOSED** | - |
| L2 / last-level cache | **none -> PROPOSED** | - |
| Scratchpad memory | `sf_spm_banked` | - |
| SRAM array / macro | `sf_sram_1r1w_inferred`, `sf_sram_1rw`, `sf_sram_1rw_inferred`, `sf_sram_2rw_inferred`, `sf_sram_bank` | `sf_macro_1rw_leaf` (behavioural), `sf_macro_1rw_leaf` (blackbox) |
| DMA engine | `sf_dma`, `sf_dma_engine` | - |
| Interconnect / router | `sf_mc25_vport_bridge`, `sf_rr_arbiter`, `sf_mem_router` | - |
| Vector register file | **none -> PROPOSED** | - |
| Tensor accumulation / MAC array | `sf_tensor_array` | - |
| Memory controller | **none -> PROPOSED** | - |
| External memory interface | **none -> PROPOSED** | - |
| ECC / parity | `sf_ecc_secded_dec`, `sf_ecc_secded_enc` | - |
| MBIST | `sf_mbist_march` | - |
| Data staging buffer | `sf_reuse_buffer` | - |
| Vector unit | `sf_vec_unit` | - |
| FIFO / flow control | `sf_fifo`, `sf_skid_buffer` | - |

## Proposed additions

* **CPU cache interface** -- SilicaFlux core L1 <-> SPM host port adapter (SF-MEM valid/ready); MemoryFlow provides the TCM-style host port on sf_spm_banked port 2.
* **L2 / last-level cache** -- Not recommended for SilicaFlux-V first silicon: DMA-managed SPM gives deterministic bandwidth; revisit for multi-core variants.
* **Vector register file** -- Vector RF of the SilicaFlux vector pipeline (if separate from the streaming sf_vec_unit) -- 2R1W, 32 x VLEN, sf_sram_1r1w-based.
* **Memory controller** -- Licensed DDR4/LPDDR4 controller IP behind an SF-MEM->AXI4 bridge (bridge is a proposed MemoryFlow addition).
* **External memory interface** -- DDR4 x32 PHY hard IP (mature node); HBM only for future advanced-node variants.

## All modules

| Module | File | Category | Class | Evidence | Yosys |
|---|---|---|---|---|---|
| `sf_extmem_model` | tb/common/sf_extmem_model.sv:15 | External memory model | BEHAVIOURAL | located in tb/ (simulation model) | - |
| `sf_macro_1rw_leaf` | rtl/macro_stubs/sf_macro_1rw_leaf.sv:17 | SRAM array / macro | BEHAVIOURAL | header: BEHAVIOURAL (simulation model of a hard macro) | - |
| `sf_macro_1rw_leaf` | rtl/macro_stubs/sf_macro_1rw_leaf_bb.sv:8 | SRAM array / macro | BLACKBOX | (* blackbox *) attribute; header: BLACKBOX (placeholder for foundry macro) | - |
| `sf_ctrl_regs` | rtl/top/sf_ctrl_regs.sv:22 | Control / registers | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `sf_dma` | rtl/dma/sf_dma.sv:49 | DMA engine | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `sf_dma_engine` | rtl/dma/sf_dma_engine.sv:22 | DMA engine | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `sf_reuse_buffer` | rtl/accel/sf_reuse_buffer.sv:21 | Data staging buffer | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `sf_ecc_secded_dec` | rtl/ecc/sf_ecc_secded_dec.sv:10 | ECC / parity | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `sf_ecc_secded_enc` | rtl/ecc/sf_ecc_secded_enc.sv:9 | ECC / parity | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `sf_fifo` | rtl/common/sf_fifo.sv:9 | FIFO / flow control | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `sf_skid_buffer` | rtl/common/sf_skid_buffer.sv:10 | FIFO / flow control | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `sf_mc25_vport_bridge` | rtl/bridge/sf_mc25_vport_bridge.sv:27 | Interconnect / router | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `sf_mem_router` | rtl/interconnect/sf_mem_router.sv:17 | Interconnect / router | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `sf_rr_arbiter` | rtl/common/sf_rr_arbiter.sv:11 | Interconnect / router | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `sf_mbist_march` | rtl/mbist/sf_mbist_march.sv:20 | MBIST | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `sf_sram_1r1w_inferred` | rtl/sram/sf_sram_1r1w_inferred.sv:10 | SRAM array / macro | SYNTHESIZABLE | header: SYNTHESIZABLE (inferred memory) | - |
| `sf_sram_1rw` | rtl/sram/sf_sram_1rw.sv:19 | SRAM array / macro | SYNTHESIZABLE | header: SYNTHESIZABLE (IMPL=1 requires macro views / blackbox) | - |
| `sf_sram_1rw_inferred` | rtl/sram/sf_sram_1rw_inferred.sv:21 | SRAM array / macro | SYNTHESIZABLE | header: SYNTHESIZABLE (inferred memory) | - |
| `sf_sram_2rw_inferred` | rtl/sram/sf_sram_2rw_inferred.sv:13 | SRAM array / macro | SYNTHESIZABLE | header: SYNTHESIZABLE (inferred memory) | - |
| `sf_sram_bank` | rtl/sram/sf_sram_bank.sv:28 | SRAM array / macro | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `sf_spm_banked` | rtl/spm/sf_spm_banked.sv:29 | Scratchpad memory | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `sf_memflow_top` | rtl/top/sf_memflow_top.sv:25 | Subsystem integration | SYNTHESIZABLE | header: SYNTHESIZABLE (integration) | - |
| `syn_dma` | syn/syn_wrappers.sv:34 | Synthesis wrapper | SYNTHESIZABLE | - | - |
| `syn_ecc64` | syn/syn_wrappers.sv:85 | Synthesis wrapper | SYNTHESIZABLE | - | - |
| `syn_memflow_top` | syn/syn_wrappers.sv:94 | Synthesis wrapper | SYNTHESIZABLE | - | - |
| `syn_router2` | syn/syn_wrappers.sv:73 | Synthesis wrapper | SYNTHESIZABLE | - | - |
| `syn_spm_256k` | syn/syn_wrappers.sv:11 | Synthesis wrapper | SYNTHESIZABLE | - | - |
| `syn_tensor_8x8` | syn/syn_wrappers.sv:49 | Synthesis wrapper | SYNTHESIZABLE | - | - |
| `syn_vec4x16` | syn/syn_wrappers.sv:61 | Synthesis wrapper | SYNTHESIZABLE | - | - |
| `sf_tensor_array` | rtl/accel/sf_tensor_array.sv:24 | Tensor accumulation / MAC array | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `sf_vec_unit` | rtl/accel/sf_vec_unit.sv:23 | Vector unit | SYNTHESIZABLE | header: SYNTHESIZABLE | - |
| `tb_accel` | tb/unit/tb_accel.sv:18 | testbench | TESTBENCH | - | - |
| `tb_deadlock` | tb/system/tb_deadlock.sv:17 | testbench | TESTBENCH | - | - |
| `tb_dma` | tb/unit/tb_dma.sv:22 | testbench | TESTBENCH | - | - |
| `tb_ecc` | tb/unit/tb_ecc.sv:12 | testbench | TESTBENCH | - | - |
| `tb_mbist` | tb/unit/tb_mbist.sv:12 | testbench | TESTBENCH | - | - |
| `tb_param_smoke` | tb/system/tb_param_smoke.sv:15 | testbench | TESTBENCH | - | - |
| `tb_router` | tb/unit/tb_router.sv:11 | testbench | TESTBENCH | - | - |
| `tb_sf1_memctrl` | tb/silicaflux/tb_sf1_memctrl.sv:16 | testbench | TESTBENCH | - | - |
| `tb_sf1_tensor` | tb/silicaflux/tb_sf1_tensor.sv:11 | testbench | TESTBENCH | - | - |
| `tb_sf25_dma_bridge` | tb/silicaflux/tb_sf25_dma_bridge.sv:15 | testbench | TESTBENCH | - | - |
| `tb_sf25_memctrl` | tb/silicaflux/tb_sf25_memctrl.sv:27 | testbench | TESTBENCH | - | - |
| `tb_sf25_tensor` | tb/silicaflux/tb_sf25_tensor.sv:20 | testbench | TESTBENCH | - | - |
| `tb_spm` | tb/unit/tb_spm.sv:17 | testbench | TESTBENCH | - | - |
| `tb_sram_bank` | tb/unit/tb_sram_bank.sv:15 | testbench | TESTBENCH | - | - |
| `tb_sram_prims` | tb/unit/tb_sram_prims.sv:12 | testbench | TESTBENCH | - | - |
| `tb_system` | tb/system/tb_system.sv:17 | testbench | TESTBENCH | - | - |
