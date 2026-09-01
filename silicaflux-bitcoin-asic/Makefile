# SilicaFlux Bitcoin SHA-256 ASIC -- top-level Makefile (section 38).
# Every target is a thin wrapper around the same Python entry points
# `python -m silicaflux_bitcoin.*` uses directly -- single source of
# truth, two ways to invoke it.
SHELL := /bin/bash
export PYTHONPATH := .:python:$(PYTHONPATH)
CONFIG ?= configs/default.yaml

.PHONY: generate vectors test simulate verify lint benchmark explore clean help

help:
	@echo "Targets:"
	@echo "  make generate   - compile a SilicaFlux config (CONFIG=$(CONFIG)) to rtl/generated/"
	@echo "  make vectors    - regenerate all tb/vectors/*.hex from the Python golden model"
	@echo "  make test       - alias for 'make simulate'"
	@echo "  make simulate   - compile+run every SystemVerilog testbench via Icarus Verilog"
	@echo "  make verify     - full pipeline: vectors -> simulate -> reports/verification_report.txt"
	@echo "  make lint       - verilator --lint-only over the synthesizable RTL tree"
	@echo "  make benchmark  - produce reports/benchmark_report.txt (section 40)"
	@echo "  make explore    - design-space sweep + real yosys synthesis -> reports/design_space_sweep.csv"
	@echo "  make clean      - remove generated vectors/reports (RTL and Python sources are untouched)"

generate:
	python3 -m silicaflux_bitcoin.generate --config $(CONFIG)

vectors:
	python3 -m silicaflux_bitcoin.vectors --out-dir tb/vectors

test: simulate

simulate:
	python3 -m silicaflux_bitcoin.simulate --json reports/simulate_results.json

verify:
	python3 -m silicaflux_bitcoin.verify --out reports/verification_report.txt

lint:
	./scripts/run_lint.sh

benchmark:
	python3 -m silicaflux_bitcoin.benchmark --out reports/benchmark_report.txt

explore:
	python3 -m silicaflux_bitcoin.explore --out reports/design_space_sweep.csv

clean:
	rm -rf tb/vectors/*.hex tb/vectors/*.svh reports/*.txt reports/*.csv reports/*.json rtl/generated/*.sv
