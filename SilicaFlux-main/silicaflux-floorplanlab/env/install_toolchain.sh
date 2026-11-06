#!/usr/bin/env bash
# Reproduce the pinned FloorplanLab toolchain (env/tools.lock.yaml) on Ubuntu 24.04.
# Installs under ${EDA_ROOT:-/opt/eda}.  Every download is verified before use.
set -euo pipefail
EDA_ROOT=${EDA_ROOT:-/opt/eda}
ORFS_REV=ab2aaf0fb8513f6f6fa8898ba65ae9599a26e621
SRAM_REV=d0e5b3c13e4bb9bdbd33493d5e87656dcae66384
MM_URL=https://conda.anaconda.org/conda-forge/linux-64/micromamba-2.10.0-0.tar.bz2
MM_SHA=9a97976244929bbae28fb1fae504e74a3e7e6d1932870e3a03321f01b7fbd07b
mkdir -p "$EDA_ROOT"

echo "[1/5] apt: yosys 0.33, iverilog, verilator, klayout, tcl"
if command -v apt-get >/dev/null; then
  sudo_cmd=""; [ "$(id -u)" -ne 0 ] && sudo_cmd=sudo
  $sudo_cmd apt-get update -q
  DEBIAN_FRONTEND=noninteractive $sudo_cmd apt-get install -y yosys iverilog verilator tcl tcllib klayout
fi

echo "[2/5] micromamba 2.10.0 (sha256-verified)"
if [ ! -x "$EDA_ROOT/mamba/bin/micromamba" ]; then
  tmp=$(mktemp -d)
  curl -sSfL -o "$tmp/mm.tar.bz2" "$MM_URL"
  echo "$MM_SHA  $tmp/mm.tar.bz2" | sha256sum -c -
  mkdir -p "$EDA_ROOT/mamba" && tar xjf "$tmp/mm.tar.bz2" -C "$EDA_ROOT/mamba" bin/micromamba
fi

echo "[3/5] OpenROAD 2.0-12331-g6011bbe77 + Yosys 0.38+92 (litex-hub)"
if [ ! -x "$EDA_ROOT/env/bin/openroad" ]; then
  printf 'channel_priority: flexible\n' > "$EDA_ROOT/condarc"
  [ -f /root/.ccr/ca-bundle.crt ] && printf 'ssl_verify: /root/.ccr/ca-bundle.crt\n' >> "$EDA_ROOT/condarc"
  MAMBA_ROOT_PREFIX="$EDA_ROOT/mamba" CONDARC="$EDA_ROOT/condarc" "$EDA_ROOT/mamba/bin/micromamba" create -y \
    -p "$EDA_ROOT/env" --override-channels -c litex-hub -c https://repo.anaconda.com/pkgs/main \
    "openroad=2.0_12331_g6011bbe77" "yosys=0.38_93_g84116c9a3" "python=3.10"
fi
"$EDA_ROOT/env/bin/openroad" -version | grep -q 2.0-12331-g6011bbe77

echo "[4/5] ORFS $ORFS_REV (sparse)"
if [ ! -d "$EDA_ROOT/orfs/.git" ]; then
  git clone --filter=blob:none --no-checkout https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts.git "$EDA_ROOT/orfs"
fi
cd "$EDA_ROOT/orfs"
git sparse-checkout init --no-cone
printf '%s\n' /flow/Makefile /flow/scripts/ /flow/util/ /flow/platforms/ihp-sg13g2/ /flow/platforms/sky130hd/ \
  /flow/platforms/sky130ram/sky130_sram_1rw1r_128x256_8/ '/flow/platforms/sky130ram/*.md' /flow/platforms/gf180/ \
  /flow/designs/ihp-sg13g2/gcd/ /flow/designs/sky130hd/gcd/ /flow/designs/src/gcd/ /flow/test/ /env.sh /README.md /LICENSE \
  > .git/info/sparse-checkout
git checkout -q "$ORFS_REV"

echo "[5/5] IHP SG13G2 SRAM collateral from ORFS $SRAM_REV"
C="$EDA_ROOT/collateral/ihp-sg13g2-sram-d0e5b3c"
mkdir -p "$C"/{lef,lib,gds,verilog}
for s in 2048 1024 512 256; do
  m=RM_IHPSG13_1P_${s}x64_c2_bm_bist
  git show "$SRAM_REV:flow/platforms/ihp-sg13g2/lef/$m.lef" > "$C/lef/$m.lef"
  git show "$SRAM_REV:flow/platforms/ihp-sg13g2/gds/$m.gds" > "$C/gds/$m.gds"
  git show "$SRAM_REV:flow/platforms/ihp-sg13g2/verilog/$m.v" > "$C/verilog/$m.v"
  for c in typ_1p20V_25C slow_1p08V_125C fast_1p32V_m55C; do
    git show "$SRAM_REV:flow/platforms/ihp-sg13g2/lib/${m}_$c.lib" > "$C/lib/${m}_$c.lib"
  done
done
git show "$SRAM_REV:flow/platforms/ihp-sg13g2/lef/sg13g2_tech.lef" > "$C/sg13g2_tech_d0e5b3c.lef.ref"
if ! diff <(grep -E '^LAYER' flow/platforms/ihp-sg13g2/lef/sg13g2_tech.lef) <(grep -E '^LAYER' "$C/sg13g2_tech_d0e5b3c.lef.ref") >/dev/null; then
  echo "ERROR: tech LEF layer stacks differ between ORFS $ORFS_REV and $SRAM_REV" >&2; exit 1
fi
(cd "$C" && find . -type f ! -name SHA256SUMS -exec sha256sum {} \; | sort -k2 > SHA256SUMS)
echo "toolchain ready under $EDA_ROOT"
