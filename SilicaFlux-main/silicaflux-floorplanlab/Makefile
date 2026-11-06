# =============================================================================
# SilicaFlux FloorplanLab -- build commands
#
# Stage order follows the pinned ORFS revision (ab2aaf0f):
#   synth (1_*) -> floorplan 2_1..2_5 (init, I/O, macro, tapcell) -> PDN 2_6
#   -> place 3_1..3_5 -> pre-route STA -> preliminary global route -> export
# Every target validates inputs first, runs the real tools, records tool
# versions + logs in results/<run>/, and exits non-zero on failure or on any
# FAILED quality gate.  Skipped stages are reported NOT_RUN, never PASS.
#
#   make floorplan-check            validate configs, platforms, tools, vendored RTL
#   make floorplan-synth            ORFS/Yosys synthesis + synthesis gates
#   make floorplan-run              + die/core, I/O, SRAM macros, tapcell
#   make floorplan-pdn              + PDN generation and connectivity checks
#   make floorplan-place            + global/detailed placement, legality, pre-route STA
#   make floorplan-timing           re-run pre-route STA on the placed database
#   make floorplan-route-estimate   + preliminary global route / congestion
#   make floorplan-sweep            experiment set or search (SWEEP=...)
#   make floorplan-report           export + images + comparison reports
#   make floorplan-gui              open the database in the OpenROAD GUI
#   make floorplan-test             pytest suite
#   make floorplan-audit            repository + toolchain audit
#   make floorplan-zip              package the project as a zip
# Variables: CFG=<run yaml>  SWEEP=<sweep yaml>  JOBS=<parallel runs>
# =============================================================================
PY     ?= python3
CFG    ?= configs/silicaflux_v/experiments/A_baseline.yaml
SWEEP  ?= configs/silicaflux_v/sweeps/experiments.yaml
JOBS   ?= 3
STAGE  ?= place
FLP     = cd python && $(PY) -m floorplanlab
ABS_CFG = $(abspath $(CFG))

.PHONY: floorplan-check floorplan-synth floorplan-run floorplan-pdn floorplan-place floorplan-timing \
        floorplan-route-estimate floorplan-sweep floorplan-report floorplan-gui floorplan-test \
        floorplan-audit floorplan-zip floorplan-tools floorplan-sources clean-results

floorplan-tools:
	@test -x "$$($(PY) -c 'import sys; sys.path.insert(0,"python"); from floorplanlab.orfs import tools; print(tools()["OPENROAD_EXE"])')" \
	  || { echo "OpenROAD not installed: run env/install_toolchain.sh"; exit 1; }

floorplan-sources:
	$(PY) tools/import_sources.py --check

floorplan-check: floorplan-tools floorplan-sources
	$(FLP) platforms
	$(FLP) check $(ABS_CFG)

floorplan-synth: floorplan-tools
	$(FLP) run $(ABS_CFG) --stages check,synth

floorplan-run: floorplan-tools
	$(FLP) run $(ABS_CFG) --stages check,synth,floorplan

floorplan-pdn: floorplan-tools
	$(FLP) run $(ABS_CFG) --stages check,synth,floorplan,pdn

floorplan-place: floorplan-tools
	$(FLP) run $(ABS_CFG) --stages check,synth,floorplan,pdn,place

floorplan-timing: floorplan-tools
	$(FLP) run $(ABS_CFG) --stages timing

floorplan-route-estimate: floorplan-tools
	$(FLP) run $(ABS_CFG) --stages check,synth,floorplan,pdn,place,route

floorplan-sweep: floorplan-tools
	$(FLP) sweep $(abspath $(SWEEP)) --jobs $(JOBS)

floorplan-report:
	$(FLP) report

floorplan-gui:
	$(FLP) gui $(ABS_CFG) --stage $(STAGE)

floorplan-test:
	cd python && $(PY) -m pytest -q ../tests

floorplan-audit:
	$(FLP) audit

floorplan-zip:
	cd .. && rm -f silicaflux-floorplanlab.zip && zip -qr silicaflux-floorplanlab.zip silicaflux-floorplanlab \
	  -x 'silicaflux-floorplanlab/results/*' -x '*/__pycache__/*' -x '*.pyc' -x '*/.pytest_cache/*'
	@ls -la ../silicaflux-floorplanlab.zip

clean-results:
	rm -rf results/*
