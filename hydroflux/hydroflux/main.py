"""
HydroFlux command-line interface.

    hydroflux run --example reservoir
    hydroflux run --example tidal-barrage
    hydroflux run --config my_system.yaml --data my_flows.csv --objective max_revenue
"""

from __future__ import annotations

import argparse
import sys

from hydroflux.core.config import HydroSystemConfig
from hydroflux.data.data import read_resource_timeseries
from hydroflux.reporting.reporting import summarize


def _run_example(name: str) -> int:
    if name == "reservoir":
        from examples.reservoir_hydro_example import main as run

        run()
    elif name == "tidal-barrage":
        from examples.tidal_barrage_example import main as run

        run()
    else:
        print(f"Unknown example '{name}'. Available: reservoir, tidal-barrage", file=sys.stderr)
        return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hydroflux", description="HydroFlux hydroelectric & tidal optimisation engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a simulation or optimisation")
    run_parser.add_argument("--example", choices=["reservoir", "tidal-barrage"], help="Run a bundled example")
    run_parser.add_argument("--config", help="Path to a HydroSystemConfig YAML/JSON file")
    run_parser.add_argument("--data", help="Path to resource time-series data (CSV/Parquet/JSON/NetCDF)")
    run_parser.add_argument("--objective", default="max_revenue", help="Optimisation objective preset")
    run_parser.add_argument("--optimise", action="store_true", help="Optimise the operating policy instead of a single simulation")

    args = parser.parse_args(argv)

    if args.command == "run":
        if args.example:
            return _run_example(args.example)
        if not args.config or not args.data:
            print("Provide --example, or both --config and --data.", file=sys.stderr)
            return 1

        config = HydroSystemConfig.from_yaml(args.config) if args.config.endswith((".yaml", ".yml")) else HydroSystemConfig.from_json(args.config)
        resource = read_resource_timeseries(args.data)

        import hydroflux

        if args.optimise:
            result = hydroflux.optimize(config, resource, objective=args.objective)
        else:
            result = hydroflux.simulate(config, resource)
        print(summarize(result))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
