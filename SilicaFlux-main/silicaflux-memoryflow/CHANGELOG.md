# Changelog

## 2.0.0 (2026-11-05): repository evidence

v1 was built without the SilicaFlux sources. v2 reads them.

### Added
* `memoryflow/silicaflux/`: extraction of the SilicaFlux HDL from its archives and `.sf` files with
  sha256 provenance; an HDL structure extractor; an evidence-anchored inventory of the memory
  subsystem (ten categories + ECC + MBIST) confirmed by Verilator elaboration; documented targets
  with page-verified quotes; a characterisation runner; as-built / documented baselines.
* `tb/silicaflux/`: self-checking testbenches for the **unmodified** SilicaFlux RTL:
  `tb_sf25_memctrl` (~150 k checks), `tb_sf25_tensor`, `tb_sf1_memctrl` (reproduces the Gen-1 DF-burst
  defect), `tb_sf1_tensor`, and `tb_sf25_dma_bridge` (MemoryFlow DMA ⇄ SilicaFlux 2.5 SPM).
* `rtl/bridge/sf_mc25_vport_bridge.sv`: SF-MEM → SilicaFlux 2.5 `memory_controller` vector port, with
  credit-reserved responses (designs out a head-of-line deadlock) and partial-lane poisoning.
* Models: `block` tensor dataflow (SilicaFlux 2.5 style) with a result-drain ceiling; DMA write path
  (Little's law on write acknowledgements) and per-workload write shares; multi-tile machines for the
  full SilicaFlux; budget presets (`--budget`); mature-node external memories (QSPI, HyperRAM ×1/×2,
  LPDDR2) and multi-channel LPDDR4X / LPDDR5; node-dependent leakage share;
  `memoryflow.models.balance` (binding resource, headroom, CPU orchestration load).
* CLI: `sf-inventory`, `sf-char`, `baselines`, `balance`, `--budget` on every budget-aware command.
* Report: SilicaFlux inventory, documented targets and conflicts, RTL characterisation, as-built vs
  documented vs recommended, node × external-memory study, full-SilicaFlux study, balance; results are
  archived in `reports/data/` on every generation.

### Changed
* Default envelope is the **documented** SilicaFlux-V target: 65 nm, 200 MHz, 8 mm² core (< 10 mm²
  die), 1 W. The v1 envelope (40 nm / 500 MHz / 12 mm² / 1.5 W) is the `v1-assumed-40` preset.
* External-memory PHY availability at the node is always enforced (v1 only checked it when
  `require_mature_dram` was set).
* `inventory.md` in the report is now the SilicaFlux inventory; the MemoryFlow self-inventory moved to
  `memoryflow_inventory.md`.
* `inspect_rtl` classifies `*bridge*` modules as interconnect.

### Unchanged
* MemoryFlow's own RTL (19/19 testbenches pass), mutation tests and synthesis wrappers.
