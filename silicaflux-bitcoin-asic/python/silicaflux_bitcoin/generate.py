"""
python -m silicaflux_bitcoin.generate --config configs/<name>.yaml [--out PATH]

Loads a SilicaFlux architecture config, validates it, lowers it to IR,
and emits the generated SystemVerilog config package. This is the
"SilicaFlux architecture -> intermediate representation -> RTL generator
-> SystemVerilog" pipeline described in section 16 of the project brief,
run end-to-end.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from silicaflux.architecture.spec import MinerArchitecture
from silicaflux.compiler.lower import lower
from silicaflux.generators.sv_emitter import emit_config_package

DEFAULT_OUT = Path("rtl/generated/silicaflux_config_pkg.sv")


def generate(config_path: Path, out_path: Path = DEFAULT_OUT) -> MinerArchitecture:
    data = yaml.safe_load(config_path.read_text())
    arch = MinerArchitecture.from_dict(data)
    design = lower(arch)
    text = emit_config_package(design)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    return arch


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compile a SilicaFlux architecture config to SystemVerilog.")
    ap.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    arch = generate(args.config, args.out)
    print(f"[silicaflux.generate] {args.config} -> {args.out}  "
          f"(architecture={arch.name}, num_cores={arch.num_cores}, "
          f"core_arch={arch.pipeline.architecture.value}, "
          f"pipeline_depth={arch.pipeline.pipeline_depth})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
