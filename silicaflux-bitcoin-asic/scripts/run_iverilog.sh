#!/usr/bin/env bash
# scripts/run_iverilog.sh -- thin wrapper around the Python simulation
# runner, so `make simulate` / a plain shell invocation and
# `python -m silicaflux_bitcoin.simulate` are the exact same code path
# (single source of truth for the testbench manifest -- see
# python/silicaflux_bitcoin/simulate.py). Run from the project root.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=".:python:${PYTHONPATH:-}"
exec python3 -m silicaflux_bitcoin.simulate "$@"
