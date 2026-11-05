# SilicaFlux repository evidence (v2)

`memoryflow.silicaflux` answers "what does SilicaFlux actually implement?" from the files in this
repository, and keeps every answer traceable.

## Sources (`sources.py`)

Most SilicaFlux RTL lives inside archives or as `.sf` files (SystemVerilog with a custom
extension). `materialise(key)` copies every HDL member of a source set into `build/sf_src/<key>/`
and records `origin` (`archive::member` or the loose path), sha256 and line count. The repository is
never modified.

| Set | Contents | Generation |
|---|---|---|
| `sf1` | `silicaflux.zip`: the v1 cluster | Gen-1 |
| `sf25` | loose `.sf` files in `SilicaFlux-main/` and `SilicaFlux2.0/SilicaFlux2.5/` | Gen-2.5 |
| `sf2_rtl` | `silicaflux_rtl*.zip`, `silicaflux_alu.zip` (earlier 2.x tops) | Gen-2.5 |
| `sfx_ai` | SilicaFlux-AI GEMM engine | sibling |
| `sf_ml`, `testcore`, `timinglab` | ML controller, DFT (MBIST/LBIST/TAP), pipelined Gen-1 drop-ins | sibling |
| `memcache`, `soc`, `cpu`, `powerlink` | library / support blocks, not SilicaFlux-integrated | library |

## Structure checks (`hdl.py`, `inventory.static_checks`)

A light SystemVerilog extractor (not a full parser) gets module headers (parameters, ports), named
instance connections and `sf_*` / package-qualified type usage. It flags:

* **REFERENCED_ONLY**: an instance of a module defined nowhere in the repository
* **INTERFACE_DRIFT**: an instance whose named ports / parameters do not exist on the definition
* **MISSING_TYPES**: package types used by a module that no package in its source set defines
* **VARIANTS**: diverging definitions of one module in the same set

## Elaboration (`inventory.lint_top`)

Each curated block that claims to be implemented is elaborated with Verilator from repository files
only (packages resolved transitively, `include` directories for Gen-1). If Verilator rejects legal SV
it does not support, Icarus is tried; if both stop on unsupported constructs, the result is
**inconclusive**, never "fail". A curated claim that the elaboration contradicts is overridden and
reported.

## Curated blocks (`inventory.BLOCKS`)

The ten categories the brief asks about (CPU cache interface, L1/L2/LLC, scratchpad, SRAM array,
DMA, interconnect, vector register file, tensor accumulation buffer, memory controller, external
memory interface) plus ECC and MBIST. Each block names a status (IMPLEMENTED, STANDALONE,
NOT_ELABORABLE, BEHAVIOURAL, REFERENCED_ONLY, DOCUMENTED_ONLY, ABSENT) and evidence **anchors**
(set, file, regex) that are resolved to `origin:line` at run time. `tests/test_silicaflux.py` fails
if an anchor stops resolving or a curated claim contradicts elaboration.

## Documented targets (`doc_targets.py`)

Quotes from the SilicaFlux-V reduced-ASIC design, the 03-11-26 update, the process-node comparison
and the codebase research report, each with document and page. `verify_quotes()` re-reads the page
with `pdftotext` and checks the quote is there. Documented conflicts (vector/tensor in or out, 100 vs
200 MHz, SRAM density) are listed, not silently resolved.

## Characterisation (`characterise.py`, `tb/silicaflux/`)

Testbenches compile the extracted repository files unchanged; see `verification.md` for the table.
An expectation of `DEFECT` means the testbench reproduces a functional defect of the repository RTL.

## Baselines (`baselines.py`)

`SystemConfig`s for the Gen-1 cluster as built, the Gen-2.5 tile as built and integrated with
MemoryFlow's DMA, and the documented SilicaFlux-V target (with and without DRAM). Each parameter
records whether it came from the RTL, an RTL measurement, a document or a MemoryFlow assumption.
