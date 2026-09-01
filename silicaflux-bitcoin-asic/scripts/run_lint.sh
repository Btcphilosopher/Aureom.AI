#!/usr/bin/env bash
# scripts/run_lint.sh -- verilator --lint-only over the full synthesizable
# RTL tree (rtl/**/*.sv, excluding rtl/generated/ which is SilicaFlux-
# generated config data, not a module). Section 39: "lint" stage of the
# abstract SystemVerilog -> lint -> elaboration -> synthesis -> timing ->
# area flow. Requires `verilator` on PATH; if missing, says so and exits
# non-zero rather than pretending to have linted anything.
set -uo pipefail
cd "$(dirname "$0")/.."

if ! command -v verilator >/dev/null 2>&1; then
  echo "verilator not found on PATH -- cannot lint. Install it (e.g. 'apt-get install verilator') and re-run." >&2
  exit 1
fi

# sha256_pkg.sv must be listed first: it's a `package`, and Verilator
# (unlike Icarus) requires a package to appear in a file processed before
# any file that references `sha256_pkg::...` -- plain alphabetical sort
# puts rtl/pipeline/... ahead of rtl/sha256/sha256_pkg.sv and breaks that.
RTL_FILES="rtl/sha256/sha256_pkg.sv $(find rtl -name '*.sv' ! -path 'rtl/generated/*' ! -name 'sha256_pkg.sv' | sort)"
FAIL=0

for top_file in \
  "rtl/top/miner_top.sv:miner_top" \
  "rtl/pipeline/sha256_pipeline.sv:sha256_pipeline"
do
  top="${top_file##*:}"
  echo "=== verilator --lint-only --top-module ${top} ==="
  # -Wno-DECLFILENAME: several modules intentionally share one file
  # (rtl/sha256/sha256_sigma.sv holds 4 related modules) -- see that
  # file's own header comment for why. -Wno-UNUSEDPARAM/-UNUSEDSIGNAL:
  # sha256_pkg.sv's constants are consumed selectively per module (K via
  # a function, H0 via named scalars), not every module needs every one.
  verilator --lint-only -Wall -Wno-DECLFILENAME -Wno-UNUSEDPARAM -Wno-UNUSEDSIGNAL -Wno-PINCONNECTEMPTY \
    --top-module "${top}" ${RTL_FILES} || FAIL=1
done

if [ "${FAIL}" -eq 0 ]; then
  echo "[PASS] verilator lint: no errors"
else
  echo "[FAIL] verilator lint: see warnings/errors above"
fi
exit ${FAIL}
